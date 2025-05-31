# label_chars.py
import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

IMG_DIR = "all_chars"
LABELS = "0123456789!@#$%^&*()@%?"  # Add more as needed
LABEL_FILE = "char_labels.csv"

# Load all images that are not yet labeled
labeled = set()
if os.path.exists(LABEL_FILE):
    with open(LABEL_FILE) as f:
        for line in f:
            fname, _ = line.strip().split(",", 1)
            labeled.add(fname)

to_label = [f for f in os.listdir(IMG_DIR) if f.endswith(".png") and f not in labeled]
to_label.sort()

class Labeler(tk.Tk):
    def __init__(self, images):
        super().__init__()
        self.title("Character Labeler")
        self.geometry("300x350")
        self.images = images
        self.idx = 0
        self.label_var = tk.StringVar()
        self.create_widgets()
        self.show_image()

    def create_widgets(self):
        self.img_label = tk.Label(self)
        self.img_label.pack(pady=10)
        self.entry = ttk.Combobox(self, values=list(LABELS), textvariable=self.label_var, font=("Arial", 24), width=3)
        self.entry.pack()
        self.entry.bind("<Return>", self.save_label)
        self.btn = tk.Button(self, text="Save Label", command=self.save_label)
        self.btn.pack(pady=10)
        self.status = tk.Label(self, text="")
        self.status.pack()

    def show_image(self):
        if self.idx >= len(self.images):
            self.status.config(text="All done!")
            self.img_label.config(image="")
            return
        img_path = os.path.join(IMG_DIR, self.images[self.idx])
        img = Image.open(img_path)
        self.tkimg = ImageTk.PhotoImage(img)
        self.img_label.config(image=self.tkimg)
        self.status.config(text=f"{self.idx+1}/{len(self.images)}: {self.images[self.idx]}")
        self.label_var.set("")

    def save_label(self, event=None):
        label = self.label_var.get().strip()
        if label not in LABELS:
            self.status.config(text="Invalid label!")
            return
        elif label == "":
            self.status.config(text="Empty label!")
        with open(LABEL_FILE, "a") as f:
            f.write(f"{self.images[self.idx]},{label}\n")
        self.idx += 1
        self.show_image()

if __name__ == "__main__":
    app = Labeler(to_label)
    app.mainloop()
