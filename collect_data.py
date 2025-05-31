import os
import platform
import subprocess
import mss
import numpy as np
import cv2
import tkinter as tk
from tkinter import messagebox
import re
import time

ALL_CHARS_DIR = "all_chars"
DEBUG_DIR = "debug"
os.makedirs(ALL_CHARS_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

IS_LINUX   = platform.system() == "Linux"
IS_WAYLAND = IS_LINUX and bool(os.environ.get("WAYLAND_DISPLAY"))

# Dummy window handles for demonstration
windows_to_hide = []

def get_next_char_idx(char_dir):
    max_idx = -1
    pat = re.compile(r"char_\d+_\d+_\d+_(\d+)\.png")
    for fname in os.listdir(char_dir):
        m = pat.match(fname)
        if m:
            idx = int(m.group(1))
            if idx > max_idx:
                max_idx = idx
    return max_idx + 1

def grab_full_screen():
    if IS_WAYLAND:
        try:
            p = subprocess.run(["grim", "-"], capture_output=True, check=True)
            arr = np.frombuffer(p.stdout, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception as e:
            print("Wayland grab failed (need grim?):", e)
            return None
    else:
        try:
            with mss.mss() as sct:
                mon = sct.monitors[0]
                shot = sct.grab(mon)
            return np.array(shot)[:, :, :3]
        except Exception as e:
            print("mss grab failed:", e)
            return None

def merge_boxes(pads, x_thresh=10, y_thresh=12):
    """
    Merge boxes that are close in x and y.
    pads: list of (x0, x1, y0, y1)
    Returns: list of merged boxes
    """
    merged = []
    used = [False] * len(pads)
    for i, (x0, x1, y0, y1) in enumerate(pads):
        if used[i]:
            continue
        group = [(x0, x1, y0, y1)]
        used[i] = True
        for j, (xx0, xx1, yy0, yy1) in enumerate(pads):
            if i == j or used[j]:
                continue
            # If horizontally aligned and close vertically, or vice versa
            x_overlap = min(x1, xx1) - max(x0, xx0)
            x_close = x_overlap > -x_thresh  # allow a little gap
            y_gap = min(abs(y1 - yy0), abs(yy1 - y0))
            y_close = y_gap < y_thresh
            if x_close and y_close:
                group.append((xx0, xx1, yy0, yy1))
                used[j] = True
        gx0 = min(g[0] for g in group)
        gx1 = max(g[1] for g in group)
        gy0 = min(g[2] for g in group)
        gy1 = max(g[3] for g in group)
        merged.append((gx0, gx1, gy0, gy1))
    return merged

def filter_contained_boxes(boxes, epsilon=2):
    """
    Remove boxes that are fully contained within another box.
    Keeps only the largest (outer) box in such cases.
    """
    keep = [True] * len(boxes)
    for i, (x0, x1, y0, y1) in enumerate(boxes):
        for j, (xx0, xx1, yy0, yy1) in enumerate(boxes):
            if i == j:
                continue
            # If box i is fully inside box j
            if (x0 >= xx0 - epsilon and x1 <= xx1 + epsilon and
                y0 >= yy0 - epsilon and y1 <= yy1 + epsilon):
                # If box j is strictly larger, mark i for removal
                if (xx1-xx0)*(yy1-yy0) > (x1-x0)*(y1-y0):
                    keep[i] = False
                    break
    return [box for k, box in zip(keep, boxes) if k]

def segment_characters(cell_img, debug_prefix=None):
    gray = cv2.cvtColor(cell_img, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(th) > 127:
        th = 255 - th
    if debug_prefix:
        cv2.imwrite(f"{debug_prefix}_thresh.png", th)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(th, connectivity=8)
    pads = []
    for i in range(1, num_labels):  # skip background
        x, y, w, h, area = stats[i]
        if area < 10:
            continue
        pads.append((x, x+w, y, y+h))

    # --- Merge close blobs (tune x_thresh and y_thresh as needed) ---
    merged_pads = merge_boxes(pads, x_thresh=10, y_thresh=12)

    filtered_pads = filter_contained_boxes(merged_pads, epsilon=2)

    chars_out, pads_out = [], []
    for x0, x1, y0, y1 in filtered_pads:
        chars_out.append(cell_img[y0:y1, x0:x1])
        pads_out.append((x0, x1, y0, y1))

    # --- Group into lines and sort left-to-right within each line ---
    if len(chars_out) > 1:
        # Use the same line grouping logic as before
        lines = []
        for pad, char in sorted(zip(pads_out, chars_out), key=lambda t: t[0][2]):  # sort by y (top)
            x0, x1, y0, y1 = pad
            placed = False
            for line in lines:
                if any(y0 <= prev_y1 for _, _, _, prev_y1 in line['pads']):
                    line['chars'].append(char)
                    line['pads'].append(pad)
                    placed = True
                    break
            if not placed:
                lines.append({'chars': [char], 'pads': [pad]})
        chars_out, pads_out = [], []
        for line in lines:
            line_sorted = sorted(zip(line['pads'], line['chars']), key=lambda t: t[0][0])
            for pad, char in line_sorted:
                pads_out.append(pad)
                chars_out.append(char)

    if debug_prefix:
        dbg = cv2.cvtColor(th, cv2.COLOR_GRAY2BGR)
        for x0, x1, y0, y1 in pads_out:
            cv2.rectangle(dbg, (x0, y0), (x1-1, y1-1), (0,255,0), 1)
        cv2.imwrite(f"{debug_prefix}_split.png", dbg)

    return chars_out, pads_out

def hide_windows(windows):
    for w in windows:
        try:
            if w and hasattr(w, "withdraw"):
                w.withdraw()
        except Exception:
            pass

def show_windows(windows):
    for w in windows:
        try:
            if w and hasattr(w, "deiconify"):
                w.deiconify()
        except Exception:
            pass

def binarize_by_bgcolor(char_img, bg_bgr=(244,168,103), threshold=30):
    # char_img: BGR or grayscale
    if len(char_img.shape) == 2:
        char_img = cv2.cvtColor(char_img, cv2.COLOR_GRAY2BGR)
    diff = np.linalg.norm(char_img.astype(np.int16) - np.array(bg_bgr, dtype=np.int16), axis=2)
    # Foreground: pixels far from background color
    bin_img = np.where(diff > threshold, 255, 0).astype(np.uint8)
    return bin_img

def take_and_dump_chars():
    # Hide all windows (add your actual window objects to windows_to_hide)
    hide_windows(windows_to_hide)
    root.update()
    import time; time.sleep(0.05)

    img = grab_full_screen()
    show_windows(windows_to_hide)
    root.update()

    if img is None:
        messagebox.showerror("Error", "Could not capture screen.")
        return

    # --- Tile detection (copy from your main pipeline) ---
    tile_bgr = np.array([244,168,103], dtype=np.int16)
    diff = np.linalg.norm(img.astype(np.int16) - tile_bgr[None,None,:], axis=2)
    tile_mask = (diff < 30).astype(np.uint8) * 255
    cv2.imwrite(os.path.join(DEBUG_DIR, "tile_mask.png"), tile_mask)

    cnts,_ = cv2.findContours(tile_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cands = []
    for cnt in cnts:
        area = cv2.contourArea(cnt)
        if area < 2000:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02*peri, True)
        if len(approx) != 4:
            continue
        x,y,ww,hh = cv2.boundingRect(approx)
        ar = ww/float(hh) if hh>0 else 0
        if not 0.7<ar<1.3:
            continue
        cands.append((area, x,y,ww,hh, approx))
    cands.sort(key=lambda t: t[0], reverse=True)
    if len(cands) < 25:
        messagebox.showerror("Error", f"Only {len(cands)} tiles found, aborting.")
        return
    tiles = cands[:25]

    ent = []
    for _,x,y,ww,hh,_ in tiles:
        ent.append({'cx':x+ww/2,'cy':y+hh/2, 'bbox':(x,y,ww,hh)})
    ent.sort(key=lambda e: e['cy'])
    rows = [ent[i*5:(i+1)*5] for i in range(5)]
    for r in rows:
        r.sort(key=lambda e: e['cx'])

    def corners(b): x,y,w,h=b; return [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
    
    buffer = 6
    tl = corners(rows[0][0]['bbox'])[0]
    tr = corners(rows[0][4]['bbox'])[1]
    br = corners(rows[4][4]['bbox'])[2]
    bl = corners(rows[4][0]['bbox'])[3]
    pts_src = np.array([tl,tr,br,bl], np.float32)
    cell_w = int(np.mean([cell['bbox'][2] for row in rows for cell in row]))
    cell_h = int(np.mean([cell['bbox'][3] for row in rows for cell in row]))
    grid_w, grid_h = cell_w*5, cell_h*5
    warp_w, warp_h = grid_w+2*buffer, grid_h+2*buffer
    pts_dst = np.array([[buffer,buffer],
                        [warp_w-buffer-1,buffer],
                        [warp_w-buffer-1,warp_h-buffer-1],
                        [buffer,warp_h-buffer-1]], np.float32)
    M = cv2.getPerspectiveTransform(pts_src, pts_dst)
    warped = cv2.warpPerspective(img, M, (warp_w, warp_h))
    cv2.imwrite(os.path.join(DEBUG_DIR,"warped.png"), warped)

    char_idx = get_next_char_idx(ALL_CHARS_DIR)
    timestamp = int(time.time())
    for i in range(5):
        for j in range(5):
            x0 = j*cell_w + buffer
            y0 = i*cell_h + buffer
            x1 = x0 + cell_w
            y1 = y0 + cell_h
            cell = warped[y0:y1, x0:x1]
            chars, _ = segment_characters(cell)
            for idx, ch in enumerate(chars):
                bin_img = binarize_by_bgcolor(ch, bg_bgr=(244,168,103), threshold=30)
                fname = f"char_{i}_{j}_{idx}_{timestamp}_{char_idx}.png"
                cv2.imwrite(os.path.join(ALL_CHARS_DIR, fname), bin_img)
                char_idx += 1
    messagebox.showinfo("Done", f"Dumped {char_idx} character images to {ALL_CHARS_DIR}/")

# --- Tkinter GUI ---
root = tk.Tk()
root.title("Character Dump Tool")
root.geometry("300x120")
btn = tk.Button(root, text="Take Screenshot and Dump Characters", font=("Arial", 14), command=take_and_dump_chars)
btn.pack(pady=30)
root.mainloop()
