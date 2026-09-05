import sys
import threading

def trigger_alert(title: str, message: str):
    """Triggers an audio beep and non-blocking desktop dialog across Windows/Linux/macOS."""
    # 1. Beep
    def play_sound():
        try:
            if sys.platform == "win32":
                import winsound
                winsound.Beep(1200, 1000)
            else:
                sys.stdout.write("\a")
                sys.stdout.flush()
        except Exception:
            pass

    threading.Thread(target=play_sound, daemon=True).start()

    # 2. Desktop Notification
    def show_dialog():
        try:
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, title, 0x30 | 0x1000)
            else:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                messagebox.showwarning(title, message)
                root.destroy()
        except Exception:
            pass

    threading.Thread(target=show_dialog, daemon=True).start()