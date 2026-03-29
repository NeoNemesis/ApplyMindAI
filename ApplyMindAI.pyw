#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ApplyMind AI — Desktop App
=========================
Startar Flask-servern i bakgrunden och visar ett
inbyggt webbläsarfönster (ingen terminal behövs).

Dubbelklicka app.py eller den byggda .exe-filen.
"""

import os
import sys
import time
import socket
import signal
import threading
import urllib.request
from pathlib import Path

# Fix Windows console encoding silently
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ── Ensure project root is on path ──────────────────────────
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

PORT = 5000
URL  = f'http://127.0.0.1:{PORT}'


# ============================================================
# 1. CHECK IF PORT IS FREE
# ============================================================

def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


def wait_for_server(url: str, timeout: int = 30) -> bool:
    """Wait until Flask is accepting connections"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


# ============================================================
# 2. FLASK SERVER THREAD
# ============================================================

flask_server = None

def start_flask():
    """Start Flask in a background daemon thread"""
    global flask_server

    # Silence Flask's startup banner
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    from web_app import app
    from werkzeug.serving import make_server

    flask_server = make_server('127.0.0.1', PORT, app)
    flask_server.serve_forever()


def stop_flask():
    global flask_server
    if flask_server:
        flask_server.shutdown()


# ============================================================
# 3. TRAY ICON (optional — shows in system tray)
# ============================================================

def build_tray_icon():
    """Create a simple green lightning-bolt icon with PIL"""
    try:
        from PIL import Image, ImageDraw
        size = 64
        img  = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Dark circle background
        draw.ellipse([2, 2, size-2, size-2], fill='#2C2C2C')
        # Green "J" letter
        draw.rectangle([20, 14, 44, 50], fill='#4AE54A')
        draw.rectangle([20, 14, 36, 50], fill='#2C2C2C')  # carve out
        return img
    except Exception:
        return None


def start_tray(window):
    """Run a system tray icon in its own thread"""
    try:
        import pystray
        from PIL import Image, ImageDraw

        icon_img = build_tray_icon()
        if icon_img is None:
            return

        def open_browser(icon, item):
            import webbrowser
            webbrowser.open(URL)

        def show_window(icon, item):
            try:
                window.show()
            except Exception:
                pass

        def quit_app(icon, item):
            icon.stop()
            stop_flask()
            try:
                window.destroy()
            except Exception:
                pass
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem('Öppna ApplyMind AI',  show_window, default=True),
            pystray.MenuItem('Öppna i webbläsare', open_browser),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Avsluta',            quit_app),
        )

        icon = pystray.Icon(
            name  = 'ApplyMind AI',
            icon  = icon_img,
            title = 'ApplyMind AI',
            menu  = menu,
        )
        icon.run()

    except Exception:
        pass   # Tray is optional — app works without it


# ============================================================
# 4. MAIN — PYWEBVIEW WINDOW
# ============================================================

def main():
    # ── Check if already running ─────────────────────────────
    if not is_port_free(PORT):
        # Server already up — just open a window
        import webview
        window = webview.create_window(
            'ApplyMind AI',
            URL,
            width=1280, height=820,
            min_size=(900, 600),
        )
        webview.start(debug=False)
        return

    # ── Start Flask in background ─────────────────────────────
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # ── Wait for server to be ready ───────────────────────────
    if not wait_for_server(URL, timeout=30):
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            'ApplyMind AI — Fel',
            'Kunde inte starta servern.\n\n'
            'Kontrollera att OpenAI API-nyckeln är korrekt i .env-filen.'
        )
        root.destroy()
        return

    # ── Create pywebview window ───────────────────────────────
    import webview

    window = webview.create_window(
        title      = 'ApplyMind AI',
        url        = URL,
        width      = 1300,
        height     = 840,
        min_size   = (960, 640),
        resizable  = True,
        text_select= True,
        confirm_close = False,
    )

    # Start system tray in background (optional)
    tray_thread = threading.Thread(
        target=start_tray, args=(window,), daemon=True
    )
    tray_thread.start()

    # ── Run window (blocks until closed) ─────────────────────
    webview.start(
        debug       = False,
        private_mode= False,
        storage_path= str(BASE_DIR / '.webview_cache'),
    )

    # ── Cleanup on close ─────────────────────────────────────
    stop_flask()
    os._exit(0)


if __name__ == '__main__':
    main()
