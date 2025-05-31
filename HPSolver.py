Version = "1.4a"
InfoText = """
Any app window must be in focus for keybinds
to function properly.

For Puzzle #2 you can input numbers right away.
Puzzle #4 entries take all 3 RGB values of a cell
with them separated by any character, besides
numbers themselves, their 'shifted' counterparts
and keybind-assigned characters.

Made by ozo
Discord: @m6ga
DM any bugs or suggestions, a forum post for the
app can be found on EUT discord (.gg/eut).
"""

import customtkinter as ctk
import keyboard
import sys
import os
import platform
import subprocess
from PIL import Image
import mss
import numpy as np
import cv2
import pytesseract
import time
import tkinter as tk
import threading
from char_predictor import predict_char
import csv
import socket

# Platform detection
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# Directories and valid chars
UNKNOWN_DIR    = "unknown_chars"
ALL_CHARS_DIR  = "all_chars"
LABEL_FILE = "char_labels.csv"
VALID_CHARS    = "0123456789!@#$%^&*()"

# Ensure directories exist
for d in (UNKNOWN_DIR, ALL_CHARS_DIR):
    os.makedirs(d, exist_ok=True)

# Detect display server on Linux
IS_WAYLAND = False
IS_X11 = False
if IS_LINUX:
    wayland_display = os.environ.get('WAYLAND_DISPLAY')
    x11_display = os.environ.get('DISPLAY')
    
    if wayland_display:
        IS_WAYLAND = True
        print("Detected Wayland display server")
    elif x11_display:
        IS_X11 = True
        print("Detected X11 display server")
    else:
        print("Could not detect display server, assuming X11")
        IS_X11 = True

# Platform-specific imports
if IS_WINDOWS:
    try:
        from ctypes import windll
        import pywinstyles as pws
        WINDOWS_FEATURES = True
    except ImportError:
        print("Windows-specific libraries not available, some features disabled")
        WINDOWS_FEATURES = False
else:
    WINDOWS_FEATURES = False

# Linux-specific imports
if IS_LINUX:
    try:
        import tkinter as tk
        if IS_X11:
            from Xlib import X, display
            from Xlib.protocol import request
            X11_FEATURES = True
        else:
            X11_FEATURES = False
    except ImportError:
        print("X11 libraries not available")
        X11_FEATURES = False


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# Cross-platform icon handling
try:
    icon_path = resource_path(r"images/M.ico")
    if not os.path.exists(icon_path):
        icon_path = None
except:
    icon_path = None

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

app = ctk.CTk()
app.geometry("463x385")
app.resizable(False, False)
app.title("HPSolver")

# Set icon only if available
if icon_path and os.path.exists(icon_path):
    try:
        if IS_WINDOWS:
            app.iconbitmap(icon_path)
        else:
            # On Linux, use a different approach for icons
            app.iconphoto(True, ctk.CTkImage(Image.open(icon_path)))
    except Exception as e:
        print(f"Could not set icon: {e}")

labels = []
replace2 = str.maketrans("!@#$%^&*()", "1234567890")


def pin_window(window, button):
    try:
        current_topmost = window.attributes('-topmost')
        window.attributes('-topmost', not current_topmost)
        button.configure(text="Unpin" if not current_topmost else "Pin")
    except Exception as e:
        print(f"Error processing pin_window: {e}")


def darken(widget, factor=0.8, bool=True):
    if bool:
        def on_enter(event):
            widget.configure(fg_color=f"#{darken_color}")
        def on_leave(event):
            widget.configure(fg_color=f"#{initial_color}")

    initial_color = widget.cget("fg_color").lstrip('#')
    rgb = tuple(int(initial_color[i:i+2], 16) for i in (0, 2, 4))
    darken_rgb = tuple(max(0, min(255, int(c * factor))) for c in rgb)
    darken_color = '{:02x}{:02x}{:02x}'.format(*darken_rgb)

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)
    return darken_color, initial_color


def titlebarify(widget, window, darkening=False):
    """Improved cross-platform window dragging"""
    if darkening:
        darken_color, initial_color = darken(widget)

    def start_move(event):
        # Store the click position relative to the widget
        widget._drag_data = {
            "x": event.x,
            "y": event.y,
            "window_x": window.winfo_x(),
            "window_y": window.winfo_y()
        }
        
        if darkening:
            widget.configure(fg_color=f"#{darken_color}")

    def on_drag(event):
        if not hasattr(widget, '_drag_data'):
            return
            
        # Calculate the movement delta from the initial click position
        delta_x = event.x - widget._drag_data["x"]
        delta_y = event.y - widget._drag_data["y"]
        
        # Calculate new window position
        new_x = widget._drag_data["window_x"] + delta_x
        new_y = widget._drag_data["window_y"] + delta_y
        
        # Update window position
        try:
            window.geometry(f"+{new_x}+{new_y}")
        except Exception as e:
            print(f"Error moving window: {e}")

    def stop_move(event):
        if darkening:
            widget.configure(fg_color=f"#{initial_color}")
        
        # Clean up drag data
        if hasattr(widget, '_drag_data'):
            delattr(widget, '_drag_data')

    widget.bind("<Button-1>", start_move)
    widget.bind("<B1-Motion>", on_drag)
    widget.bind("<ButtonRelease-1>", stop_move)


def switch_to_english():
    """Cross-platform keyboard layout switching"""
    if IS_WINDOWS and WINDOWS_FEATURES:
        try:
            LANG_EN = 0x0409
            windll.user32.ActivateKeyboardLayout(LANG_EN, 0)
        except Exception as e:
            print(f"Could not switch keyboard layout: {e}")
    elif IS_LINUX:
        try:
            if IS_WAYLAND:
                # Wayland keyboard layout switching
                subprocess.run(['gsettings', 'set', 'org.gnome.desktop.input-sources', 'current', '0'], 
                             check=False, capture_output=True)
            else:
                # X11 keyboard layout switching
                subprocess.run(['setxkbmap', 'us'], check=False, capture_output=True)
        except Exception as e:
            print(f"Could not switch keyboard layout: {e}")
    else:
        print("Note: Make sure you're using an English keyboard layout")


def get_window_id(window):
    """Get the window ID for Linux systems"""
    if not IS_LINUX:
        return None
    try:
        window.update_idletasks()
        return window.winfo_id()
    except Exception as e:
        print(f"Could not get window ID: {e}")
        return None


def set_window_clickthrough_x11(window, enable=True):
    """Set window clickthrough on X11"""
    window_id = get_window_id(window)
    if not window_id:
        return False
    
    try:
        if X11_FEATURES:
            # Method 1: Using python-xlib
            d = display.Display()
            w = d.create_resource_object('window', window_id)
            
            if enable:
                # Set window to be transparent to input events
                w.set_wm_hints(input=False)
                w.change_attributes(do_not_propagate_mask=X.NoEventMask)
            else:
                # Restore normal input handling
                w.set_wm_hints(input=True)
            
            d.sync()
            return True
        else:
            # Method 2: Using xprop commands
            hex_id = hex(window_id)
            
            if enable:
                # Set window as click-through using window properties
                subprocess.run([
                    'xprop', '-id', hex_id, '-f', '_NET_WM_WINDOW_TYPE', '32a',
                    '-set', '_NET_WM_WINDOW_TYPE', '_NET_WM_WINDOW_TYPE_DOCK'
                ], check=False, capture_output=True)
                
                # Make window below others and non-focusable
                subprocess.run([
                    'xprop', '-id', hex_id, '-f', '_NET_WM_STATE', '32a',
                    '-set', '_NET_WM_STATE', '_NET_WM_STATE_BELOW,_NET_WM_STATE_SKIP_TASKBAR'
                ], check=False, capture_output=True)
            else:
                # Restore normal window properties
                subprocess.run([
                    'xprop', '-id', hex_id, '-remove', '_NET_WM_WINDOW_TYPE'
                ], check=False, capture_output=True)
                
                subprocess.run([
                    'xprop', '-id', hex_id, '-remove', '_NET_WM_STATE'
                ], check=False, capture_output=True)
            
            return True
            
    except Exception as e:
        print(f"Could not set clickthrough on X11: {e}")
        return False


def set_window_clickthrough_wayland(window, enable=True):
    """Set window clickthrough on Wayland (limited functionality)"""
    try:
        # Wayland has very limited window manipulation capabilities
        # Most compositors don't support true clickthrough
        
        # Try compositor-specific methods
        window_id = get_window_id(window)
        if window_id:
            hex_id = hex(window_id)
            
            # Try sway-specific method
            try:
                if enable:
                    subprocess.run([
                        'swaymsg', f'[id={window_id}] floating enable, sticky enable'
                    ], check=False, capture_output=True)
                else:
                    subprocess.run([
                        'swaymsg', f'[id={window_id}] sticky disable'
                    ], check=False, capture_output=True)
                return True
            except:
                pass
            
            # Try KDE/KWin method
            try:
                if enable:
                    subprocess.run([
                        'qdbus', 'org.kde.KWin', '/KWin', 'org.kde.KWin.setKeepAbove', str(window_id), 'true'
                    ], check=False, capture_output=True)
                else:
                    subprocess.run([
                        'qdbus', 'org.kde.KWin', '/KWin', 'org.kde.KWin.setKeepAbove', str(window_id), 'false'
                    ], check=False, capture_output=True)
                return True
            except:
                pass
        
        # Fallback: Just toggle always on top
        current_topmost = window.attributes('-topmost')
        window.attributes('-topmost', enable if enable != current_topmost else not current_topmost)
        return True
        
    except Exception as e:
        print(f"Could not set clickthrough on Wayland: {e}")
        return False


def set_window_transparency_x11(window, alpha):
    """Set window transparency on X11"""
    try:
        # Method 1: Use tkinter's built-in alpha attribute
        window.attributes('-alpha', alpha)
        return True
    except Exception as e:
        print(f"Could not set transparency with tkinter: {e}")
        
        # Method 2: Use X11 properties
        window_id = get_window_id(window)
        if window_id:
            try:
                hex_id = hex(window_id)
                opacity_value = int(alpha * 0xffffffff)
                subprocess.run([
                    'xprop', '-id', hex_id, '-f', '_NET_WM_WINDOW_OPACITY', '32c',
                    '-set', '_NET_WM_WINDOW_OPACITY', str(opacity_value)
                ], check=False, capture_output=True)
                return True
            except Exception as e2:
                print(f"Could not set transparency with xprop: {e2}")
        
        return False


def set_window_transparency_wayland(window, alpha):
    """Set window transparency on Wayland"""
    try:
        # Method 1: Try tkinter alpha (works on some compositors)
        window.attributes('-alpha', alpha)
        return True
    except Exception as e:
        print(f"Transparency not supported on this Wayland compositor: {e}")
        
        # Wayland transparency is compositor-dependent
        # Most compositors don't support runtime transparency changes
        window_id = get_window_id(window)
        if window_id:
            try:
                # Try sway-specific opacity
                opacity_percent = int(alpha * 100)
                subprocess.run([
                    'swaymsg', f'[id={window_id}] opacity {alpha}'
                ], check=False, capture_output=True)
                return True
            except:
                pass
        
        return False


def set_window_clickthrough_linux(window, enable=True):
    """Cross-platform Linux clickthrough"""
    if IS_X11:
        return set_window_clickthrough_x11(window, enable)
    elif IS_WAYLAND:
        return set_window_clickthrough_wayland(window, enable)
    else:
        return False


def set_window_transparency_linux(window, alpha):
    """Cross-platform Linux transparency"""
    if IS_X11:
        return set_window_transparency_x11(window, alpha)
    elif IS_WAYLAND:
        return set_window_transparency_wayland(window, alpha)
    else:
        return False


settings_window = None
def open_settings():
    try:
        global settings_window, keybinds

        def hatch_bind(button, function):
            blacklist = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
                        '!', '@', '#', '$', '%', '^', '&', '*', '(', ')', 'Esc']
            button.configure(text="Press a key", fg_color='#144870')

            def on_key_press(event):
                new_key = " ".join([w.capitalize() for w in event.name.split()])
                if not event.name.isascii():
                    print("Invalid keybind: Non-ASCII key detected, make sure you are using an English keyboard layout.")
                elif new_key not in blacklist:
                    button.configure(text=new_key, fg_color='#1f6aa5')
                    app.unbind_all(keybinds[function])
                    keybinds[function] = new_key if len(new_key) > 1 else "<" + new_key.lower() + ">"
                    app.bind_all(keybinds[function], function)
                    print("Keybind changed to:", keybinds[function], new_key)
                else:
                    button.configure(text=keybinds[function].replace("<", "").replace(">", "") if "Return" not in keybinds[function] else "Enter")
                    print("Invalid keybind:", new_key)
                keyboard.unhook_all()

            switch_to_english()
            keyboard.on_press(on_key_press)

        if settings_window is not None and settings_window.winfo_exists():
            settings_window.lift()
            settings_window.focus_force()
            return

        settings_window = ctk.CTkToplevel(app)
        window = settings_window
        window.geometry("220x220")
        window.overrideredirect(True)
        
        # Set transparency - cross-platform
        if IS_WINDOWS:
            window.wm_attributes("-transparentcolor", "#1a1a1a")
        else:
            set_window_transparency_linux(window, 0.95)
            
        window.after(10, lambda: window.focus_force())

        mainframe = ctk.CTkFrame(window, corner_radius=10)
        mainframe.pack()

        titlebar = ctk.CTkFrame(mainframe,
                               height=25,
                               fg_color='#1f6aa5',
                               corner_radius=5)
        titlebar.pack_propagate(False)
        titlebar.pack(fill='x', pady=(5, 0), padx=5)
        titlebarify(titlebar, window, True)

        close = ctk.CTkButton(titlebar,
                             height=20,
                             width=15,
                             corner_radius=5,
                             fg_color='#002037',
                             text='Hide',
                             font=("", 10),
                             command=lambda: window.withdraw())
        close.pack(side='right', padx=2)

        pin = ctk.CTkButton(titlebar,
                           height=20,
                           width=15,
                           corner_radius=5,
                           fg_color='#002037',
                           text='Pin',
                           font=("", 10),
                           command=lambda: pin_window(window, pin))
        pin.pack(side='left', padx=2)

        grid = ctk.CTkFrame(mainframe, corner_radius=5)
        grid.pack(pady=5, padx=5)

        Solve = ctk.CTkLabel(grid, text="Solve:", font=("", 15))
        Solve.grid(row=0, column=0, pady=5, padx=5, sticky="w")

        Clear = ctk.CTkLabel(grid, text="Clear:", font=("", 15))
        Clear.grid(row=1, column=0, pady=5, padx=5, sticky="w")

        Clickthrough = ctk.CTkLabel(grid, text="Clickthrough:", font=("", 15))
        Clickthrough.grid(row=2, column=0, pady=5, padx=5, sticky="w")

        grid.columnconfigure(1, weight=1)

        SolveBind = ctk.CTkButton(grid,
                                 width=90,
                                 height=30,
                                 border_width=1,
                                 corner_radius=2,
                                 text="Enter",
                                 font=("", 15, 'bold'),
                                 command=lambda: hatch_bind(SolveBind, hatch_puzzle))
        SolveBind.grid(row=0, column=1, pady=5, padx=5)

        ClearBind = ctk.CTkButton(grid,
                                 width=90,
                                 height=30,
                                 border_width=1,
                                 corner_radius=2,
                                 text="R",
                                 font=("", 15, 'bold'),
                                 command=lambda: hatch_bind(ClearBind, clear_entries))
        ClearBind.grid(row=1, column=1, pady=5, padx=5)

        ClickthroughBind = ctk.CTkButton(grid,
                                        width=90,
                                        height=30,
                                        border_width=1,
                                        corner_radius=2,
                                        text="F1",
                                        font=("", 15, 'bold'),
                                        command=lambda: hatch_bind(ClickthroughBind, toggle_clickthrough))
        ClickthroughBind.grid(row=2, column=1, pady=5, padx=5)

        window.withdraw()

    except Exception as e:
        print(f"Error processing open_settings: {e}\n")


info_window = None
def open_info():
    try:
        global info_window
        if info_window is not None and info_window.winfo_exists():
            info_window.lift()
            info_window.focus_force()
            return

        window = ctk.CTkToplevel(app)
        info_window = window
        window.geometry("350x400")
        window.overrideredirect(True)
        
        # Set transparency - cross-platform
        if IS_WINDOWS:
            window.wm_attributes("-transparentcolor", "#1a1a1a")
        else:
            set_window_transparency_linux(window, 0.95)
            
        window.after(10, lambda: window.focus_force())

        mainframe = ctk.CTkFrame(window,
                                width=350,
                                height=400,
                                corner_radius=10)
        mainframe.pack(fill='both')

        titlebar = ctk.CTkFrame(mainframe,
                               height=25,
                               fg_color='#1f6aa5',
                               corner_radius=5)
        titlebar.pack_propagate(False)
        titlebar.pack(fill='x', pady=(5, 0), padx=5)
        titlebarify(titlebar, window, True)

        close = ctk.CTkButton(titlebar,
                             height=20,
                             width=15,
                             corner_radius=5,
                             fg_color='#002037',
                             text='Hide',
                             font=("", 10),
                             command=window.withdraw)
        close.pack(side='right', padx=2)

        pin = ctk.CTkButton(titlebar,
                           height=20,
                           width=15,
                           corner_radius=5,
                           fg_color='#002037',
                           text='Pin',
                           font=("", 10),
                           command=lambda: pin_window(window, pin))
        pin.pack(side='left', padx=2)

        versionlabel = ctk.CTkLabel(mainframe,
                                   anchor="center",
                                   width=280,
                                   text=f"Version {Version}",
                                   font=("", 20, 'bold'))
        versionlabel.pack()

        label = ctk.CTkLabel(mainframe,
                           text=InfoText,
                           font=("", 15),
                           justify="left",
                           width=280)
        label.pack(padx=5, pady=(0, 2))
        window.withdraw()

    except Exception as e:
        print(f"Error processing open_info: {e}\n")


class ConsoleWindow:
    def __init__(self, master):
        self.master = master
        self.window = None
        self.console_text = None
        self.master.after(200, self.setup)

    def setup(self):
        self.setup_ui()
        self.setup_redirection()
        self.write_console("Console initialized.\n")

    def setup_ui(self):
        try:
            if self.window is not None and self.window.winfo_exists():
                self.window.lift()
                self.window.focus_force()
                return

            self.window = ctk.CTkToplevel(self.master)
            self.window.geometry("550x300")
            self.window.overrideredirect(True)
            
            # Set transparency - cross-platform
            if IS_WINDOWS:
                self.window.wm_attributes("-transparentcolor", "#1a1a1a")
            else:
                set_window_transparency_linux(self.window, 0.95)
                
            self.window.after(10, lambda: self.window.focus_force())

            mainframe = ctk.CTkFrame(self.window,
                                    width=500,
                                    height=300,
                                    corner_radius=10)
            mainframe.pack_propagate(False)
            mainframe.pack(fill='both')

            # Load background image if available
            try:
                freedom_dive = ctk.CTkImage(
                    light_image=Image.open(resource_path("images/freedomdive.png")),
                    size=(550, 300))
                freedom_image = ctk.CTkLabel(mainframe,
                                           text="",
                                           image=freedom_dive)
                freedom_image.place(x=0, y=0)
            except Exception as e:
                print(f"Could not load background image: {e}")

            titlebar = ctk.CTkFrame(mainframe,
                                   height=25,
                                   fg_color='#1f6aa5',
                                   corner_radius=5)
            titlebar.pack_propagate(False)
            titlebar.pack(fill='x', pady=5, padx=5)
            titlebarify(titlebar, self.window, True)

            clear = ctk.CTkButton(titlebar,
                                 height=20,
                                 width=30,
                                 corner_radius=5,
                                 fg_color='#002037',
                                 text='Clear',
                                 font=("", 10),
                                 command=self.clear_console)
            clear.pack(side='left', padx=2)

            pin = ctk.CTkButton(titlebar,
                               height=20,
                               width=15,
                               corner_radius=5,
                               fg_color='#002037',
                               text='Pin',
                               font=("", 10),
                               command=lambda: pin_window(self.window, pin))
            pin.pack(side='left')

            close = ctk.CTkButton(titlebar,
                                 height=20,
                                 width=15,
                                 corner_radius=5,
                                 fg_color='#002037',
                                 text='Hide',
                                 font=("", 10),
                                 command=self.window.withdraw)
            close.pack(side='right', padx=2)

            self.console_text = ctk.CTkTextbox(mainframe,
                                              wrap="word",
                                              corner_radius=0,
                                              height=250,
                                              width=530,
                                              state='normal',
                                              font=("Calibri", 12, "bold"))
            
            # Apply opacity - cross-platform
            if IS_WINDOWS and WINDOWS_FEATURES:
                try:
                    pws.set_opacity(self.console_text, 0.9)
                except Exception as e:
                    print(f"Could not set opacity: {e}")
            
            self.console_text.pack(pady=(0, 10), padx=10, expand=True)
            self.console_text.configure(state='disabled')

            self.window.withdraw()

        except Exception as e:
            with open("console_error.log", "a") as f:
                f.write(f"Error setting up console UI: {e}\n")

    class NullOutput:
        def write(self, text):
            pass
        def flush(self):
            pass

    def setup_redirection(self):
        try:
            if sys.stdout is None:
                sys.stdout = self.NullOutput()
            if sys.stderr is None:
                sys.stderr = self.NullOutput()

            sys.stdout.write = self.write_console
            sys.stderr.write = self.write_console
        except Exception as e:
            with open("console_error.log", "a") as f:
                f.write(f"Error setting up redirection: {e}\n")

    def write_console(self, text):
        try:
            if self.console_text is not None:
                self.console_text.configure(state='normal')
                self.console_text.insert("end", text)
                self.console_text.see("end")
                self.console_text.configure(state='disabled')
                self.console_text.update()

            with open("output.log", "a") as f:
                f.write(f"{text}")
        except Exception as e:
            with open("console_error.log", "a") as f:
                f.write(f"Error in write_console: {e}\n")

    def clear_console(self):
        try:
            if self.console_text is not None:
                self.console_text.configure(state='normal')
                self.console_text.delete("1.0", "end")
                self.console_text.configure(state='disabled')
        except Exception as e:
            self.write_console(f"Error processing clear_console: {e}\n")

    def toggle(self):
        if self.window is not None and self.window.winfo_exists():
            if self.window.state() == 'withdrawn':
                self.window.deiconify()
                self.window.lift()
                self.window.focus_force()
            else:
                self.window.withdraw()


def change_transparency(value):
    try:
        if IS_WINDOWS:
            order_window.attributes("-alpha", float(value))
        else:
            set_window_transparency_linux(order_window, float(value))
    except Exception as e:
        print(f"Error processing change_transparency: {e}")


clickthrough = False
clickthroughlabel = None
def toggle_clickthrough(event=None):
    global clickthrough, clickthroughlabel
    try:
        if order_window is None or not order_window.winfo_exists() or order_window.state() == 'withdrawn':
            print("Order window is not open. Open the Order window to enable clickthrough.")
            return

        order_window.lift()
        order_window.focus_force()
        order_window.update_idletasks()

        if IS_WINDOWS and WINDOWS_FEATURES:
            # Windows-specific clickthrough implementation
            hwnd = windll.user32.GetForegroundWindow()
            style = windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE = -20

            if not clickthrough:
                new_style = style | 0x00000020  # WS_EX_TRANSPARENT
                windll.user32.SetWindowLongW(hwnd, -20, new_style)
                if clickthroughlabel:
                    clickthroughlabel.configure(text="Clickthrough enabled", text_color='#c4ffa8')
            else:
                new_style = style & ~0x00000020  # Remove WS_EX_TRANSPARENT
                windll.user32.SetWindowLongW(hwnd, -20, new_style)
                if clickthroughlabel:
                    clickthroughlabel.configure(text="Clickthrough disabled", text_color='#ffa8a8')
                force_focus_window(hwnd)

            windll.user32.UpdateWindow(hwnd)
            clickthrough = not clickthrough
        else:
            # Linux clickthrough implementation
            success = set_window_clickthrough_linux(order_window, not clickthrough)
            
            if success:
                clickthrough = not clickthrough
                if clickthroughlabel:
                    if clickthrough:
                        if IS_WAYLAND:
                            clickthroughlabel.configure(text="Stay-on-top enabled", text_color='#c4ffa8')
                        else:
                            clickthroughlabel.configure(text="Clickthrough enabled", text_color='#c4ffa8')
                    else:
                        if IS_WAYLAND:
                            clickthroughlabel.configure(text="Stay-on-top disabled", text_color='#ffa8a8')
                        else:
                            clickthroughlabel.configure(text="Clickthrough disabled", text_color='#ffa8a8')
            else:
                print("Failed to toggle clickthrough")
                if clickthroughlabel:
                    clickthroughlabel.configure(text="Clickthrough unavailable", text_color='#ffaa00')

    except Exception as e:
        print(f"Error processing toggle_clickthrough: {e}")


def force_focus_window(hwnd):
    """Windows-specific window focus function"""
    if IS_WINDOWS and WINDOWS_FEATURES:
        try:
            if windll.user32.IsIconic(hwnd):
                windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0003)  # HWND_TOPMOST
            windll.user32.SetForegroundWindow(hwnd)
            windll.user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0003)  # HWND_NOTOPMOST
        except Exception as e:
            print(f"Error processing force_focus_window: {e}")


order_window = None
def open_order():
    try:
        global order_window, clickthroughlabel, labels

        if order_window is not None and order_window.winfo_exists():
            order_window.lift()
            order_window.focus_force()
            return

        window = ctk.CTkToplevel(app)
        order_window = window
        window.geometry("262x340")
        window.overrideredirect(True)
        
        # Set transparency - cross-platform
        if IS_WINDOWS:
            window.wm_attributes("-transparentcolor", "#1a1a1a")
        else:
            set_window_transparency_linux(window, 0.95)
            
        window.after(10, lambda: window.focus_force())

        mainframe = ctk.CTkFrame(window,
                                width=262,
                                height=340,
                                corner_radius=10)
        mainframe.pack_propagate(False)
        mainframe.pack(fill='both')

        titlebar = ctk.CTkFrame(mainframe,
                               height=25,
                               fg_color='#1f6aa5',
                               corner_radius=5)
        titlebar.pack_propagate(False)
        titlebar.pack(fill='x', pady=5, padx=5)
        titlebarify(titlebar, window, True)

        close = ctk.CTkButton(titlebar,
                             height=20,
                             width=15,
                             corner_radius=5,
                             fg_color='#002037',
                             text='Hide',
                             font=("", 10),
                             command=window.withdraw)
        close.pack(side='right', padx=2)

        pin = ctk.CTkButton(titlebar,
                           height=20,
                           width=15,
                           corner_radius=5,
                           fg_color='#002037',
                           text='Pin',
                           font=("", 10),
                           command=lambda: pin_window(window, pin))
        pin.pack(side='left', padx=2)

        frame = ctk.CTkFrame(mainframe)
        frame.pack()

        grid = ctk.CTkFrame(frame)
        grid.pack()

        for i in range(5):
            row_labels = []
            for j in range(5):
                label = ctk.CTkLabel(grid,
                                    width=50,
                                    height=50,
                                    justify="center",
                                    text="",
                                    fg_color="#025c9d",
                                    font=("", 16, "bold"))
                label.grid(row=i, column=j, padx=1, pady=1)
                row_labels.append(label)
            labels.append(row_labels)

        transparency_slider = ctk.CTkSlider(mainframe,
                                           width=200,
                                           height=5,
                                           from_=0.1,
                                           to=1,
                                           number_of_steps=10,
                                           command=change_transparency)
        transparency_slider.set(1)
        transparency_slider.pack(pady=(10, 5))

        # Update label text based on platform capabilities
        if IS_WAYLAND:
            label_text = "Stay-on-top disabled"
        else:
            label_text = "Clickthrough disabled"
            
        clickthroughlabel = ctk.CTkLabel(mainframe,
                                        text=label_text,
                                        text_color='#ffa8a8')
        clickthroughlabel.pack()
        window.withdraw()

    except Exception as e:
        print(f"Error processing open_order: {e}\n")


def toggle_window(window):
    if window is not None and window.winfo_exists():
        if window.state() == 'withdrawn':
            window.deiconify()
            window.lift()
            window.focus_force()
        else:
            window.withdraw()


# Puzzle solving functions remain the same
def hatch_puzzle(event=None):
    try:
        values = []
        checkstop = False
        puzzle = 12
        for row in entries:
            for entry in row:
                data = str(entry.get()) if entry.get() else '0'
                values.append(data)
                if not checkstop:
                    if len(data) > 4:
                        puzzle = 4
                        checkstop = True
                    elif len(data) > 3:
                        puzzle = 3
                        checkstop = True

        print(f"Entries: {values}")

        if puzzle == 4:
            print(f"Detected Puzzle #4")
            puzzle4(values)
        elif puzzle == 3:
            print(f"Detected Puzzle #3")
            puzzle3(values)
        else:
            print(f"Detected Puzzle #1/#2")
            puzzle1_2(values)
    except Exception as e:
        print(f"Error processing hatch_puzzle: {e}\n")


def puzzle1_2(values):
    try:
        replace = str.maketrans("!@#$%^&*()", "1234567890")
        values = [int(num.translate(replace)) for num in values]
        print(f"Converted: {values}")

        non_zero_values = [value for value in values if value != 0]
        order = {num: i + 1 for i, num in enumerate(sorted(non_zero_values))}
        ordered_values = [order.get(num, 0) for num in values]
        print(f"Order: {ordered_values}\n")

        if order_window is not None and order_window.winfo_exists():
            label_index = 0
            for i in range(5):
                for j in range(5):
                    labels[i][j].configure(text=str(ordered_values[label_index]) if ordered_values[label_index] != 0 else '')
                    label_index += 1

    except Exception as e:
        print(f"Error processing Puzzle #1/#2: {e}")


def puzzle3(values):
    try:
        values = [int(num) for num in values]
        binary_ones_count = [bin(i)[2:].count('1') for i in values]
        print(f"Binary 1s Counts: {binary_ones_count}")

        non_zero_values = [(i, count) for i, count in enumerate(binary_ones_count) if count != 0]
        non_zero_values.sort(key=lambda x: x[1])
        order = {pair[0]: i + 1 for i, pair in enumerate(non_zero_values)}
        ordered_values = [order.get(i, 0) for i in range(25)]
        print(f"Order: {ordered_values}")

        if order_window is not None and order_window.winfo_exists():
            label_index = 0
            for i in range(5):
                for j in range(5):
                    labels[i][j].configure(text=str(ordered_values[label_index]) if ordered_values[label_index] != 0 else '')
                    label_index += 1

    except Exception as e:
        print(f"Error processing Puzzle #3: {e}")


def puzzle4(values):
    try:
        def rgb_to_hsv(rgb):
            try:
                r, g, b = map(lambda x: int(x) / 255.0, rgb.split())
            except Exception as e:
                return 0
            cmax, cmin = max(r, g, b), min(r, g, b)
            d = cmax - cmin
            if d == 0:
                h = 0
            elif cmax == r:
                h = (60 * ((g - b) / d) + 360) % 360
            elif cmax == g:
                h = (60 * ((b - r) / d) + 120) % 360
            elif cmax == b:
                h = (60 * ((r - g) / d) + 240) % 360
            s = 0 if cmax == 0 else d * 100 / cmax
            v = cmax * 100
            return h + s + v

        values = [''.join(c if c.isdigit() else ' ' for c in num) for num in values]
        print(f"Sanitized: {values}")

        hsv_values = [rgb_to_hsv(rgb) if rgb != '0' else 0 for rgb in values]
        print(f"HSV Values: {hsv_values}")

        non_zero_values = [value for value in hsv_values if value != 0]
        order = {num: i + 1 for i, num in enumerate(sorted(non_zero_values))}
        ordered_values = [order.get(num, 0) for num in hsv_values]
        print(f"Order: {ordered_values}")

        if order_window is not None and order_window.winfo_exists():
            label_index = 0
            for i in range(5):
                for j in range(5):
                    labels[i][j].configure(text=str(ordered_values[label_index]) if ordered_values[label_index] != 0 else '')
                    label_index += 1

    except Exception as e:
        print(f"Error processing Puzzle #4: {e}")


def limit_input(entry_text, max_length):
    try:
        return (len(entry_text) <= int(max_length))
    except Exception as e:
        print(f"Error processing limit_input: {e}")


def clear_entries(event=None):
    try:
        for row in entries:
            for entry in row:
                entry.delete(0, "end")
    except Exception as e:
        print(f"Error processing clear_entries: {e}")

IS_LINUX   = platform.system() == "Linux"
IS_WAYLAND = IS_LINUX and bool(os.environ.get("WAYLAND_DISPLAY"))
IS_X11     = IS_LINUX and not IS_WAYLAND

DEBUG_DIR = os.path.join(os.path.abspath("."), "debug")

def _prep_debug_dir():
    if os.path.isdir(DEBUG_DIR):
        for f in os.listdir(DEBUG_DIR):
            try: os.remove(os.path.join(DEBUG_DIR, f))
            except: pass
    else:
        os.makedirs(DEBUG_DIR)

def grab_full_screen():
    """Cross-platform full-screen grab:
       - Wayland: uses `grim -` (install grim)
       - X11/Windows: uses mss"""
    toplevels = {
      "order":    order_window,
      "settings": settings_window,
      "info":     info_window
    }
    visible = {}
    for name, w in toplevels.items():
        visible[name] = bool(w and w.winfo_exists() and w.state()!="withdrawn")
        if visible[name]:
            w.withdraw()
    app.withdraw(); app.update(); time.sleep(0.05)

    target = None

    if IS_WAYLAND:
        try:
            p = subprocess.run(["grim", "-"], capture_output=True, check=True)
            arr = np.frombuffer(p.stdout, dtype=np.uint8)
            target = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception as e:
            print("Wayland grab failed (need grim?):", e)
    else:
        try:
            with mss.mss() as sct:
                mon = sct.monitors[0]
                shot = sct.grab(mon)            # BGRA
            target = np.array(shot)[:, :, :3]    # drop alpha → BGR
        except Exception as e:
            print("mss grab failed:", e)
    
    if target is not None:
        cv2.imwrite(os.path.join(DEBUG_DIR, "00_screenshot.png"), target)

    app.deiconify()
    for name, w in toplevels.items():
        if visible[name]:
            w.deiconify()

    return target

def scan_puzzle_grid():
    _prep_debug_dir()

    # 2) grab screen
    img = grab_full_screen()

    if img is None:
        print("Scan aborted: could not capture screen")
        return

    # 4) spawn a background thread to do the heavy lifting
    threading.Thread(target=_process_scan, args=(img,), daemon=True).start()

def perspective_correct_and_extract_cells(img, tiles, debug_dir, cell_size=100):
    grid_size = cell_size * 5

    def get_cell_center(bbox):
        x, y, w, h = bbox
        return (x + w/2, y + h/2)

    # Get the 4 outer corners
    pts_src = np.array([
        get_cell_center(tiles[0][0]['bbox']),
        get_cell_center(tiles[0][4]['bbox']),
        get_cell_center(tiles[4][4]['bbox']),
        get_cell_center(tiles[4][0]['bbox']),
    ], dtype=np.float32)

    pts_dst = np.array([
        [0, 0],
        [grid_size-1, 0],
        [grid_size-1, grid_size-1],
        [0, grid_size-1]
    ], dtype=np.float32)

    # Draw debug overlay on original image
    debug_img = img.copy()
    for pt in pts_src:
        cv2.circle(debug_img, tuple(np.int32(pt)), 10, (0,0,255), -1)
    cv2.polylines(debug_img, [np.int32(pts_src)], isClosed=True, color=(0,255,0), thickness=3)
    cv2.imwrite(os.path.join(debug_dir, "49_grid_corners.png"), debug_img)

    # Compute and apply perspective transform
    M = cv2.getPerspectiveTransform(pts_src, pts_dst)
    warped = cv2.warpPerspective(img, M, (grid_size, grid_size))
    cv2.imwrite(os.path.join(debug_dir, "50_grid_warped.png"), warped)

    # Extract each cell
    cells = []
    for i in range(5):
        row = []
        for j in range(5):
            x0 = j * cell_size
            y0 = i * cell_size
            cell_img = warped[y0:y0+cell_size, x0:x0+cell_size]
            row.append(cell_img)
            cv2.imwrite(os.path.join(debug_dir, f"51_cell_{i}_{j}.png"), cell_img)
        cells.append(row)
    return cells

def load_templates():
    templates = {}  # label -> list of images
    with open(LABEL_FILE) as f:
        reader = csv.reader(f)
        for fname, label in reader:
            img_path = os.path.join(ALL_CHARS_DIR, fname)
            if not os.path.exists(img_path):
                continue
            img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            if np.mean(img) > 127:
                img = 255 - img
            templates.setdefault(label, []).append(img)
    return templates

def count_holes(bin_img):
    cnts, hier = cv2.findContours(
        bin_img, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    if hier is None:
        return 0
    hole_count = 0
    for h in hier[0]:
        # h[3] != -1 → this contour has a parent → it's a hole
        if h[3] != -1:
            hole_count += 1
    return hole_count

def count_blobs(bin_img):
    # bin_img: single-channel, 0/255, foreground=255
    cnts, _ = cv2.findContours(bin_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return len(cnts)

def match_template_ncc_improved(
    char_bin,
    templates,  # label -> list of images
    ncc_thresh=0.65,
    fill_penalty_w=0.5,
    hole_penalty_w=0.7
):
    """
    Returns (best_label, best_score) or (None, score) if below ncc_thresh.
    Penalizes:
      - Non-negative fills: live=fg where tmpl=bg
      - Hole-count mismatches
    Uses all labeled images as templates.
    """
    if not templates:
        return None, None

    # blob_count = count_blobs(char_bin)
    # if blob_count == 2:
    #     return "!", 1.0
    # elif blob_count == 3:
    #     return "%", 1.0

    holes_char = count_holes(char_bin)
    best_label = None
    best_score = -1.0

    for label, tmpl_list in templates.items():
        for tmpl in tmpl_list:
            tmpl_rs = cv2.resize(tmpl, (char_bin.shape[1], char_bin.shape[0]), interpolation=cv2.INTER_AREA)
            _, tmpl_bin = cv2.threshold(tmpl_rs, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            if np.mean(tmpl_bin) > 127:
                tmpl_bin = 255 - tmpl_bin

            res = cv2.matchTemplate(
                char_bin.astype(np.float32),
                tmpl_bin.astype(np.float32),
                cv2.TM_CCOEFF_NORMED
            )
            ncc_score = float(res[0,0])

            nonneg = np.logical_and(tmpl_bin == 0, char_bin == 255)
            fill_penalty = fill_penalty_w * (np.sum(nonneg) / nonneg.size)

            holes_tmpl = count_holes(tmpl_bin)
            hole_diff = abs(holes_char - holes_tmpl)
            hole_penalty = hole_penalty_w * hole_diff / max(holes_tmpl, 1)

            score = ncc_score - fill_penalty - hole_penalty
            if score > best_score:
                best_score = score
                best_label = label

    if best_score < ncc_thresh:
        return None, best_score
    return best_label, best_score

def save_new_template(char_img, label, templates):
    fname = os.path.join(TEMPLATE_DIR, f"{label}.png")
    if not os.path.exists(fname):
        if len(char_img.shape) == 3:
            gray = cv2.cvtColor(char_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = char_img.copy()
        _, bin_img = cv2.threshold(gray, 0, 255,
                                   cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if np.mean(bin_img) > 127:
            bin_img = 255 - bin_img
        cv2.imwrite(fname, bin_img)
        print(f"Saved new template: {fname}")
        templates[label] = bin_img

def save_unknown(char_img, i, j, idx):
    fname = os.path.join(UNKNOWN_DIR, f"char_{i}_{j}_{idx}.png")
    if len(char_img.shape) == 3:
        gray = cv2.cvtColor(char_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = char_img.copy()
    _, bin_img = cv2.threshold(gray, 0, 255,
                               cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(bin_img) > 127:
        bin_img = 255 - bin_img
    cv2.imwrite(fname, bin_img)
    print(f"Saved unknown character: {fname}")

def save_all_char(char_img, i, j, idx, label):
    fname = os.path.join(ALL_CHARS_DIR,
                         f"char_{i}_{j}_{idx}_{label}.png")
    if len(char_img.shape) == 3:
        gray = cv2.cvtColor(char_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = char_img.copy()
    _, bin_img = cv2.threshold(gray, 0, 255,
                               cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(bin_img) > 127:
        bin_img = 255 - bin_img
    cv2.imwrite(fname, bin_img)

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

def group_into_lines(pads, chars, line_gap=0):
    # Sort by y (top)
    items = sorted(zip(pads, chars), key=lambda t: t[0][2])
    lines = []
    for pad, char in items:
        x0, x1, y0, y1 = pad
        placed = False
        for line in lines:
            # Get the max bottom of the current line
            max_y1 = max(p[3] for p in line['pads'])
            if y0 <= max_y1 + line_gap:
                line['chars'].append(char)
                line['pads'].append(pad)
                placed = True
                break
        if not placed:
            lines.append({'chars': [char], 'pads': [pad]})
    return lines

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
    # merged_pads = merge_boxes(pads, x_thresh=10, y_thresh=12)
    merged_pads = pads

    filtered_pads = filter_contained_boxes(merged_pads, epsilon=2)

    chars_out, pads_out = [], []
    for x0, x1, y0, y1 in filtered_pads:
        chars_out.append(cell_img[y0:y1, x0:x1])
        pads_out.append((x0, x1, y0, y1))

    # --- Group into lines and sort left-to-right within each line ---
    if len(chars_out) > 1:
        lines = group_into_lines(pads_out, chars_out, line_gap=3)
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

def unified_binarize_char(char_img,
                          white_thresh=40,
                          close_kernel=(1,1)):
    """
    Very simple “white‐text” binarizer:
      - Any pixel where R,G,B are all ≥ white_thresh → foreground (255)
      - Everything else → background (0)
      - Tiny closing to join broken strokes.

    Returns a H×W uint8 mask (0=bg, 255=fg).
    """
    # split channels
    b,g,r = cv2.split(char_img)
    # mask white pixels
    mask = ((b >= white_thresh) &
            (g >= white_thresh) &
            (r >= white_thresh)).astype(np.uint8) * 255

    # tiny closing
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, close_kernel
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask

def cluster_pads_and_chars(pads, cell_img, overlap_thresh=0.3):
    """
    Merge any pads in the *one line* whose horizontal overlap
    >= overlap_thresh×min(widths).  Return sorted-by-x0 lists
    of new_pads and new_char_imgs.
    """
    if len(pads) <= 1:
        # nothing to merge
        chars = [ cell_img[y0:y1, x0:x1] for x0,x1,y0,y1 in pads ]
        return pads, chars

    # widths of each pad
    widths = [(x1-x0) for x0,x1,y0,y1 in pads]
    n = len(pads)
    used = [False]*n
    clusters = []

    # build adjacency by horizontal overlap
    for i in range(n):
        if used[i]:
            continue
        used[i] = True
        group = [i]
        stack = [i]
        while stack:
            k = stack.pop()
            x0k,x1k,y0k,y1k = pads[k]
            wk = widths[k]
            for j in range(n):
                if used[j]:
                    continue
                x0j,x1j,y0j,y1j = pads[j]
                wj = widths[j]
                overlap = max(0, min(x1k, x1j) - max(x0k, x0j))
                if overlap >= min(wk, wj)*overlap_thresh:
                    used[j] = True
                    stack.append(j)
                    group.append(j)
        clusters.append(group)

    # now build merged pads & char crops
    merged = []
    for group in clusters:
        x0 = min(pads[i][0] for i in group)
        x1 = max(pads[i][1] for i in group)
        y0 = min(pads[i][2] for i in group)
        y1 = max(pads[i][3] for i in group)
        merged.append((x0,x1,y0,y1))

    # sort left→right
    merged.sort(key=lambda p: p[0])

    # extract char images
    chars = [ cell_img[y0:y1, x0:x1] for x0,x1,y0,y1 in merged ]
    return merged, chars

def recognize_cell(cell_img,
                   templates,
                   nn_model=predict_char,
                   debug_prefix=None):
    """
    1) raw CC segmentation → raw_chars, raw_pads
    2) group_into_lines on raw_pads → lines0
    3) for each line in lines0:
         cluster_pads_and_chars(line['pads'], cell_img)
       → collect merged_pads / merged_chars per line
    4) per-glyph binarize+template/NN → labels
    5) full debug dumps if debug_prefix≠None
    6) if only one line → return that string
       else → call parse_rgb_from_lines on the merged lines
               and join non‐empty with spaces
    """
    # 1) segment
    raw_chars, raw_pads = segment_characters(cell_img)

    # 2) group into lines (vertical grouping)
    lines0 = group_into_lines(raw_pads, raw_chars, line_gap=3)

    # 3) within each line, cluster
    all_pads, all_chars = [], []
    merged_lines = []
    for ln in lines0:
        pads_i = ln['pads']
        merged_pads, merged_chars = cluster_pads_and_chars(pads_i, cell_img)
        merged_lines.append({'pads': merged_pads, 'chars': merged_chars})
        all_pads.extend(merged_pads)
        all_chars.extend(merged_chars)

    # 4) per-glyph recognition
    labels = []
    for idx, ch in enumerate(all_chars):
        mask = unified_binarize_char(ch)
        lbl, score = match_template_ncc_improved(mask, templates)
        if not lbl:
            nn_lbl, nn_conf = nn_model(mask)
            lbl = nn_lbl if nn_conf > 0.7 else '?'
        labels.append(lbl)

        # per-glyph debug dumps
        if debug_prefix:
            cv2.imwrite(f"{debug_prefix}_char_{idx}.png", ch)
            cv2.imwrite(f"{debug_prefix}_mask_{idx}.png", mask)

    # 5) full‐cell debug
    if debug_prefix:
        os.makedirs(os.path.dirname(debug_prefix), exist_ok=True)
        cv2.imwrite(f"{debug_prefix}_cell.png", cell_img)
        dbg = cell_img.copy()
        for (x0,x1,y0,y1), lbl in zip(all_pads, labels):
            cv2.rectangle(dbg, (x0,y0), (x1,y1), (0,255,0), 1)
            cv2.putText(dbg, lbl, (x0, max(0,y0-3)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0,255,0), 1, cv2.LINE_AA)
        cv2.imwrite(f"{debug_prefix}_recognized.png", dbg)

    # 6) build line_strs from labels + merged_lines
    line_counts = [len(ln['pads']) for ln in merged_lines]
    line_strs = []
    ptr = 0
    for cnt in line_counts:
        line_strs.append("".join(labels[ptr:ptr+cnt]))
        ptr += cnt

    # single line → return raw
    if len(line_strs) == 1:
        return line_strs[0]

    # multi-line → RGB parse + drop empty + join with spaces
    rgb = parse_rgb_from_lines(merged_lines, templates)
    rgb = [c for c in rgb if c]
    return " ".join(rgb)

def _process_scan(img):
    buffer = 6

    # 1) Tile mask
    tile_bgr = np.array([244,168,103], dtype=np.int16)
    diff = np.linalg.norm(img.astype(np.int16)
                         - tile_bgr[None,None,:],
                         axis=2)
    tile_mask = (diff < 30).astype(np.uint8) * 255
    cv2.imwrite(os.path.join(DEBUG_DIR, "10_tile_mask.png"), tile_mask)

    # 2) Contours → candidate tiles
    cnts,_ = cv2.findContours(tile_mask, cv2.RETR_EXTERNAL,
                              cv2.CHAIN_APPROX_SIMPLE)
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
        print(f"Only {len(cands)} tiles found, aborting.")
        return
    tiles = cands[:25]

    # 3) Draw overlay
    dbg0 = img.copy()
    for _,x,y,ww,hh,_ in tiles:
        cv2.rectangle(dbg0,(x,y),(x+ww,y+hh),(0,255,0),2)
    cv2.imwrite(os.path.join(DEBUG_DIR, "30_tiles_overlay.png"), dbg0)

    # 4) Sort into 5×5
    ent = []
    for _,x,y,ww,hh,_ in tiles:
        ent.append({'cx':x+ww/2,'cy':y+hh/2,
                        'bbox':(x,y,ww,hh)})
    ent.sort(key=lambda e: e['cy'])
    rows = [ent[i*5:(i+1)*5] for i in range(5)]
    for r in rows:
        r.sort(key=lambda e: e['cx'])

    # 5) Perspective correction
    def corners(b): x,y,w,h=b; return [(x,y),(x+w,y),
                                     (x+w,y+h),(x,y+h)]
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

    dbg1 = img.copy()
    for p in pts_src:
        cv2.circle(dbg1, tuple(p.astype(int)), 8, (0,0,255), -1)
    cv2.polylines(dbg1,[pts_src.astype(int)],True,(0,255,0),2)
    cv2.imwrite(os.path.join(DEBUG_DIR,"49_grid_corners.png"), dbg1)

    M = cv2.getPerspectiveTransform(pts_src, pts_dst)
    warped = cv2.warpPerspective(img, M, (warp_w, warp_h))
    cv2.imwrite(os.path.join(DEBUG_DIR,"50_grid_warped.png"), warped)

    # 6) Load templates
    templates = load_templates()
    if not templates:
        print("No templates found → all via OCR")

    results = [['']*5 for _ in range(5)]
    for i in range(5):
      for j in range(5):
        cell = warped[
          buffer + i*cell_h : buffer + (i+1)*cell_h,
          buffer + j*cell_w : buffer + (j+1)*cell_w
        ]
        prefix = os.path.join(DEBUG_DIR, f"cell_{i}_{j}")
        results[i][j] = recognize_cell(
          cell, templates, predict_char, debug_prefix=prefix
        )

        def _write():
          for r in range(5):
            for c in range(5):
              e = entries[r][c]
              e.delete(0,"end")
              e.insert(0, results[r][c])
        app.after(0, _write)

def find_highlighted_cell_corners(img, threshold=5):
    """
    Find the 4 corner highlights of a cell.
    Detects both #0047A5 (BGR: 165,71,0) and #014EA7 (BGR: 167,78,1).
    """
    # Define both highlight colors in BGR
    highlight_bgrs = [
        (165, 71, 0),   # #0047A5
        (167, 78, 1),   # #014ea7
    ]
    
    # Create a combined mask for all highlight colors
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    for highlight_bgr in highlight_bgrs:
        diff = np.linalg.norm(
            img.astype(np.int16) - np.array(highlight_bgr, dtype=np.int16), axis=2
        )
        mask = cv2.bitwise_or(mask, (diff <= threshold).astype(np.uint8) * 255)
    
    # Save debug images
    cv2.imwrite(os.path.join(DEBUG_DIR, "01_corner_mask.png"), mask)
    
    # Create visualization
    result = img.copy()
    result[mask > 0] = [0, 255, 0]  # Green highlights for visibility
    cv2.imwrite(os.path.join(DEBUG_DIR, "02_corners_highlighted.png"), result)
    
    # Find contours
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # No area filtering (as in your latest code)
    centers = []
    for cnt in cnts:
        M = cv2.moments(cnt)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            centers.append((cx, cy))
    
    print(f"Found {len(centers)} corner candidates")
    
    if len(centers) != 4:
        print(f"Expected 4 corners, found {len(centers)}")
        # Save debug image with all detected centers
        debug_img = img.copy()
        for i, center in enumerate(centers):
            cv2.circle(debug_img, center, 5, (0, 255, 0), -1)
            cv2.putText(debug_img, str(i), (center[0]+10, center[1]), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.imwrite(os.path.join(DEBUG_DIR, "03_all_corners.png"), debug_img)
        return None
    
    # Sort corners: top-left, top-right, bottom-right, bottom-left
    tl = min(centers, key=lambda p: p[0] + p[1])  # smallest x+y
    br = max(centers, key=lambda p: p[0] + p[1])  # largest x+y
    tr = min(centers, key=lambda p: p[1] - p[0])  # smallest y-x (top-right)
    bl = max(centers, key=lambda p: p[1] - p[0])  # largest y-x (bottom-left)
    
    corners = [tl, tr, br, bl]
    
    # Save debug image with sorted corners
    debug_img = img.copy()
    corner_labels = ['TL', 'TR', 'BR', 'BL']
    corner_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    for corner, label, color in zip(corners, corner_labels, corner_colors):
        cv2.circle(debug_img, corner, 8, color, -1)
        cv2.putText(debug_img, label, (corner[0]+12, corner[1]), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    cv2.imwrite(os.path.join(DEBUG_DIR, "04_sorted_corners.png"), debug_img)
    
    return corners

def extract_cell_content(img, corners):
    """
    Extract the cell content using the 4 corners and highlight white text
    """
    if corners is None or len(corners) != 4:
        return None
    
    tl, tr, br, bl = corners
    
    # Create bounding box from corners
    all_x = [p[0] for p in corners]
    all_y = [p[1] for p in corners]
    
    x1, y1 = min(all_x), min(all_y)
    x2, y2 = max(all_x), max(all_y)
    
    # Add some padding inside the corners
    padding = 5
    x1 += padding
    y1 += padding
    x2 -= padding
    y2 -= padding
    
    # Ensure valid bounds
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(img.shape[1], x2)
    y2 = min(img.shape[0], y2)
    
    # Extract cell region
    cell_img = img[y1:y2, x1:x2]
    
    if cell_img.size == 0:
        print("Empty cell region")
        return None
    
    # Save the extracted cell
    cv2.imwrite(os.path.join(DEBUG_DIR, "05_extracted_cell.png"), cell_img)
    
    # Find white text in the cell
    white_text_img = isolate_white_text(cell_img)
    
    # Save debug image showing bounding box on original
    debug_img = img.copy()
    cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 255), 2)
    for corner in corners:
        cv2.circle(debug_img, corner, 5, (255, 0, 255), -1)
    cv2.imwrite(os.path.join(DEBUG_DIR, "06_cell_bounds.png"), debug_img)
    
    return cell_img, white_text_img, (x1, y1, x2, y2)

def isolate_white_text(cell_img, white_threshold=240):
    """
    Isolate white text from the cell image
    """
    # Convert to grayscale
    gray = cv2.cvtColor(cell_img, cv2.COLOR_BGR2GRAY)
    
    # Find white pixels (text)
    white_mask = gray >= white_threshold
    
    # Create result image - black background with white text
    result = np.zeros_like(cell_img)
    result[white_mask] = [255, 255, 255]  # White text
    
    # Also create a pure binary version
    binary_result = np.zeros(gray.shape, dtype=np.uint8)
    binary_result[white_mask] = 255
    
    # Save debug images
    cv2.imwrite(os.path.join(DEBUG_DIR, "07_white_text_color.png"), result)
    cv2.imwrite(os.path.join(DEBUG_DIR, "08_white_text_binary.png"), binary_result)
    
    print(f"Found {np.sum(white_mask)} white pixels in cell")
    
    return result, binary_result

def perspective_correct_single_cell(img, corners, cell_size=100):
    """
    Apply perspective correction to a single cell using its 4 corners
    
    Args:
        img: Original image
        corners: List of 4 corner points [tl, tr, br, bl]
        cell_size: Output size for the corrected cell
    
    Returns:
        corrected_cell: Perspective-corrected cell image
    """
    if corners is None or len(corners) != 4:
        print("Need exactly 4 corners for perspective correction")
        return None
    
    tl, tr, br, bl = corners
    
    # Source points (the detected corners)
    pts_src = np.array([
        tl,  # top-left
        tr,  # top-right  
        br,  # bottom-right
        bl   # bottom-left
    ], dtype=np.float32)
    
    # Destination points (perfect square)
    pts_dst = np.array([
        [0, 0],                           # top-left
        [cell_size-1, 0],                 # top-right
        [cell_size-1, cell_size-1],       # bottom-right
        [0, cell_size-1]                  # bottom-left
    ], dtype=np.float32)
    
    # Draw debug overlay showing source corners
    debug_img = img.copy()
    corner_labels = ['TL', 'TR', 'BR', 'BL']
    corner_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    
    for i, (pt, label, color) in enumerate(zip(pts_src, corner_labels, corner_colors)):
        cv2.circle(debug_img, tuple(np.int32(pt)), 8, color, -1)
        cv2.putText(debug_img, label, (int(pt[0])+12, int(pt[1])), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    # Draw the quadrilateral
    cv2.polylines(debug_img, [np.int32(pts_src)], isClosed=True, color=(0,255,255), thickness=2)
    cv2.imwrite(os.path.join(DEBUG_DIR, "09_perspective_corners.png"), debug_img)
    
    # Compute perspective transformation matrix
    M = cv2.getPerspectiveTransform(pts_src, pts_dst)
    
    # Apply perspective correction
    corrected_cell = cv2.warpPerspective(img, M, (cell_size, cell_size))
    
    # Save debug images
    cv2.imwrite(os.path.join(DEBUG_DIR, "10_corrected_cell.png"), corrected_cell)
    
    print(f"Applied perspective correction to create {cell_size}x{cell_size} cell")
    
    return corrected_cell

def extract_and_correct_cell(img, corners, cell_size=100):
    """
    Complete pipeline: extract cell content and apply perspective correction
    """
    if corners is None:
        return None
    
    # First, get the corrected cell
    corrected_cell = perspective_correct_single_cell(img, corners, cell_size)
    
    if corrected_cell is None:
        return None
    
    # Extract white text from the corrected cell
    white_text_color, white_text_binary = isolate_white_text(corrected_cell)
    
    # Save the final results
    cv2.imwrite(os.path.join(DEBUG_DIR, "11_final_corrected_cell.png"), corrected_cell)
    cv2.imwrite(os.path.join(DEBUG_DIR, "12_final_white_text.png"), white_text_binary)
    
    return {
        'corrected_cell': corrected_cell,
        'white_text_color': white_text_color,
        'white_text_binary': white_text_binary
    }

def validate_corners(corners):
    """
    Validate that the corners form a reasonable quadrilateral
    """
    if corners is None or len(corners) != 4:
        return False
    
    tl, tr, br, bl = corners
    
    # Check minimum size
    width = max(tr[0] - tl[0], br[0] - bl[0])
    height = max(bl[1] - tl[1], br[1] - tr[1])
    
    if width < 20 or height < 20:
        print(f"Warning: Cell seems too small ({width}x{height})")
        return False
    
    print(f"Corners validated. Approximate cell size: {width}x{height}")
    return True

def group_characters_into_lines(chars_out, pads_out):
    """
    Group characters into lines using the same logic as segment_characters
    Returns list of line dictionaries with chars and pads
    """
    if len(chars_out) <= 1:
        return [{'chars': chars_out, 'pads': pads_out}] if chars_out else []
    
    # Use the same line grouping logic as segment_characters
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
    
    # Sort characters within each line left-to-right
    for line in lines:
        line_sorted = sorted(zip(line['pads'], line['chars']), key=lambda t: t[0][0])
        line['pads'] = [pad for pad, char in line_sorted]
        line['chars'] = [char for pad, char in line_sorted]
    
    return lines

def detect_gaps_in_line(pads, gap_threshold_ratio=1.0):
    """
    Detect significant gaps between characters in a line
    
    Args:
        pads: List of character bounding boxes in the line
        gap_threshold_ratio: Minimum gap as ratio of average character width
    
    Returns:
        gap_positions: List of indices where significant gaps occur
    """
    if len(pads) < 2:
        return []
    
    # Calculate average character width
    char_widths = [x1 - x0 for x0, x1, y0, y1 in pads]
    avg_char_width = sum(char_widths) / len(char_widths)
    gap_threshold = avg_char_width * gap_threshold_ratio
    
    gaps = []
    for i in range(len(pads) - 1):
        current_x1 = pads[i][1]
        next_x0 = pads[i + 1][0]
        gap_size = next_x0 - current_x1
        
        if gap_size > gap_threshold:
            gaps.append(i + 1)  # Gap after character i
    
    return gaps

def recognize_line_text(chars, templates):
    """
    Recognize text from a line of characters
    
    Args:
        chars: List of character images
        templates: Template dictionary for matching
    
    Returns:
        recognized_text: String of recognized characters
    """
    recognized = []
    
    for idx, ch in enumerate(chars):
        # Binarize character using foreground color method (white text)
        tbin = unified_binarize_char(ch)
        
        # Try template matching first
        label, score = match_template_ncc_improved(tbin, templates)
        if label:
            recognized.append(label)
        else:
            # Fall back to neural network prediction
            nn_label, nn_conf = predict_char(tbin)
            if nn_conf > 0.7:
                recognized.append(nn_label)
            else:
                recognized.append('?')
                save_unknown(tbin, 0, 0, idx)
    
    return "".join(recognized)

def parse_rgb_from_lines(lines, templates):
    """
    Parse R/G/B values from detected lines
    Minimum is 2 lines, maximum is 3 lines
    
    Args:
        lines: List of line dictionaries from group_characters_into_lines
        templates: Template dictionary for character recognition
    
    Returns:
        [R_value, G_value, B_value]
    """
    if len(lines) == 3:
        # Each line is a separate R/G/B component
        r_value = recognize_line_text(lines[0]['chars'], templates)
        g_value = recognize_line_text(lines[1]['chars'], templates)
        b_value = recognize_line_text(lines[2]['chars'], templates)
        
        print(f"3 lines detected: R='{r_value}', G='{g_value}', B='{b_value}'")
        return [r_value, g_value, b_value]
    
    elif len(lines) == 2:
        # One line has two components, other has one
        # Detect which line has the gap
        line1_gaps = detect_gaps_in_line(lines[0]['pads'])
        line2_gaps = detect_gaps_in_line(lines[1]['pads'])
        
        if line1_gaps and not line2_gaps:
            # First line has two components, second line has one
            line2_text = recognize_line_text(lines[1]['chars'], templates)
            
            # Split first line at the gap
            gap_pos = line1_gaps[0]
            part1_chars = lines[0]['chars'][:gap_pos]
            part2_chars = lines[0]['chars'][gap_pos:]
            
            part1_text = recognize_line_text(part1_chars, templates)
            part2_text = recognize_line_text(part2_chars, templates)
            
            print(f"2 lines: Line1 split at gap: '{part1_text}' + '{part2_text}', Line2: '{line2_text}'")
            return [part1_text, part2_text, line2_text]
        
        elif line2_gaps and not line1_gaps:
            # Second line has two components, first line has one
            line1_text = recognize_line_text(lines[0]['chars'], templates)
            
            # Split second line at the gap
            gap_pos = line2_gaps[0]
            part1_chars = lines[1]['chars'][:gap_pos]
            part2_chars = lines[1]['chars'][gap_pos:]
            
            part1_text = recognize_line_text(part1_chars, templates)
            part2_text = recognize_line_text(part2_chars, templates)
            
            print(f"2 lines: Line1: '{line1_text}', Line2 split at gap: '{part1_text}' + '{part2_text}'")
            return [line1_text, part1_text, part2_text]
        
        else:
            # No clear gaps or multiple gaps - fall back to simple split
            # Assume first line is R, second line is G, B is empty
            line1_text = recognize_line_text(lines[0]['chars'], templates)
            line2_text = recognize_line_text(lines[1]['chars'], templates)
            
            print(f"2 lines (no clear gaps): R='{line1_text}', G='{line2_text}', B=''")
            return [line1_text, line2_text, ""]
    
    else:
        print(f"Unexpected number of lines: {len(lines)} (minimum should be 2)")
        if len(lines) == 1:
            # Fallback: try to detect gaps in the single line
            gaps = detect_gaps_in_line(lines[0]['pads'])
            
            if len(gaps) >= 2:
                # Split into three parts
                chars = lines[0]['chars']
                part1_chars = chars[:gaps[0]]
                part2_chars = chars[gaps[0]:gaps[1]]
                part3_chars = chars[gaps[1]:]
                
                part1_text = recognize_line_text(part1_chars, templates)
                part2_text = recognize_line_text(part2_chars, templates)
                part3_text = recognize_line_text(part3_chars, templates)
                
                print(f"1 line with 2 gaps (fallback): '{part1_text}', '{part2_text}', '{part3_text}'")
                return [part1_text, part2_text, part3_text]
            
            elif len(gaps) == 1:
                # Split into two parts
                chars = lines[0]['chars']
                part1_chars = chars[:gaps[0]]
                part2_chars = chars[gaps[0]:]
                
                part1_text = recognize_line_text(part1_chars, templates)
                part2_text = recognize_line_text(part2_chars, templates)
                
                print(f"1 line with 1 gap (fallback): '{part1_text}', '{part2_text}', ''")
                return [part1_text, part2_text, ""]
            
            else:
                # No gaps - single component
                line_text = recognize_line_text(lines[0]['chars'], templates)
                print(f"1 line (no gaps, fallback): '{line_text}', '', ''")
                return [line_text, "", ""]
        
        return ["", "", ""]

def single_cell_mode_capture_and_insert():
    img = grab_full_screen()
    corners = find_highlighted_cell_corners(img)
    if not corners or not validate_corners(corners):
      print("Corner detection failed"); return

    result = extract_and_correct_cell(img, corners, cell_size=90)
    if result is None:
      print("Extraction failed"); return

    corrected = result['corrected_cell']
    templates = load_templates()
    prefix = os.path.join(DEBUG_DIR, "single_cell")
    txt = recognize_cell(
      corrected, templates, predict_char, debug_prefix=prefix
    )

    for row in entries:
      for e in row:
        if not e.get():
          e.insert(0, txt)
          print(f"Inserted '{txt}'"); return
    print("No empty cell")

if IS_WAYLAND:
    def hotkey_listener_thread():
        try:
            os.unlink(SOCKET_PATH)
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(SOCKET_PATH)
        while True:
            data, _ = sock.recvfrom(1024)
            if data == b"single_cell":
                print("Received single-cell hotkey from daemon.")
                app.after(0, single_cell_mode_capture_and_insert)

    threading.Thread(target=hotkey_listener_thread, daemon=True).start()
    print("Wayland → listening for single_cell via UNIX socket")

else:
    # On Windows and X11 → use python-keyboard to register a global F8
    try:
        keyboard.add_hotkey(
            "F8",
            lambda: app.after(0, single_cell_mode_capture_and_insert),
            suppress=False
        )
        print("Registered global F8 hotkey via python-keyboard")
    except Exception as e:
        print(f"Could not register global F8 hotkey: {e}")

# -- UI Code --

frame = ctk.CTkFrame(app, bg_color='#1a1a1a')
frame.pack(pady=(32, 10))

grid1 = ctk.CTkFrame(frame, bg_color='#1a1a1a')
grid2 = ctk.CTkFrame(frame, fg_color='transparent')
grid1.pack(side="top")
grid2.pack(side="bottom", pady=5)

entries = []
for i in range(5):
    row_entries = []
    validate_cmd = app.register(lambda text: limit_input(text, 11))
    for j in range(5):
        entry = ctk.CTkEntry(
            grid1,
            justify="center",
            width=90,
            height=45,
            border_width=1,
            corner_radius=2,
            validate="key",
            validatecommand=(validate_cmd, "%P"))
        entry.grid(row=i+1, column=j)
        row_entries.append(entry)
    entries.append(row_entries)

inputlabel = ctk.CTkLabel(grid1,
                         width=100,
                         text="Input",
                         font=("", 20))
inputlabel.grid(row=0, column=0, columnspan=5, pady=5)

solve_button = ctk.CTkButton(grid2,
                           width=100,
                           text="Solve",
                           font=("", 20),
                           command=hatch_puzzle)
solve_button.grid(row=0, column=1, padx=5)

clear_button = ctk.CTkButton(grid2,
                           width=100,
                           text="Clear",
                           font=("", 20),
                           command=clear_entries)
clear_button.grid(row=0, column=0, padx=5)

order_button = ctk.CTkButton(grid2,
                            width=100,
                            text="Order",
                            font=("", 20),
                            command=lambda: toggle_window(order_window))
order_button.grid(row=2, column=0, columnspan=2, pady=5)

info_button = ctk.CTkButton(app,
                           width=20,
                           height=20,
                           text="?",
                           font=("", 15),
                           command=lambda: toggle_window(info_window))
info_button.place(x=5, y=5)

# Load settings icon if available
try:
    settings_icon = ctk.CTkImage(
        light_image=Image.open(resource_path("images/settings.png")),
        size=(15, 15))
    settings_button = ctk.CTkButton(app,
                                   width=20,
                                   height=20,
                                   text="",
                                   image=settings_icon,
                                   command=lambda: toggle_window(settings_window))
except Exception as e:
    print(f"Could not load settings icon: {e}")
    settings_button = ctk.CTkButton(app,
                                   width=20,
                                   height=20,
                                   text="⚙",
                                   font=("", 12),
                                   command=lambda: toggle_window(settings_window))

settings_button.place(x=32, y=5)

pin_button = ctk.CTkButton(app,
                          width=40,
                          height=20,
                          text="Pin",
                          font=("", 15),
                          command=lambda: pin_window(app, pin_button))
pin_button.place(x=67, y=5)

console = ConsoleWindow(app)
console_button = ctk.CTkButton(app,
                              width=80,
                              height=20,
                              text="Console",
                              font=("", 15),
                              command=console.toggle)
console_button.place(x=375, y=5)

scan_button = ctk.CTkButton(
    grid2, width=100, text="Scan", font=("", 20),
    command=scan_puzzle_grid
)
scan_button.grid(row=1, column=1, padx=5)

keybinds = {
    toggle_clickthrough: "<F1>",
    hatch_puzzle: "<Return>",
    clear_entries: "r"
}

for function, key in keybinds.items():
    app.bind_all(key, function)

# Preloading top level windows
open_settings()
open_info()
open_order()

print(f"HPSolver Started on {platform.system()}")
if IS_LINUX:
    if IS_WAYLAND:
        print("Wayland detected - limited clickthrough (stay-on-top only)")
    else:
        print("X11 detected - full clickthrough support available")

app.mainloop()
