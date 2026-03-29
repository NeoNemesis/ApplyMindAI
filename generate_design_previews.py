#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ApplyMind AI — Design Preview Generator
=========================================
Genererar PNG-miniatyrer för alla 10 CV-designer
med hjälp av Selenium/Chrome headless.

Kör: python generate_design_previews.py
"""

import os
import sys
import time
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR     = Path(__file__).parent
TEMPLATE_DIR = BASE_DIR / 'static' / 'design_templates'
PREVIEW_DIR  = BASE_DIR / 'static' / 'previews'
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

DESIGNS = [
    ('design_01_minimal',       'Design 1 — Minimal'),
    ('design_02_classic',       'Design 2 — Klassisk'),
    ('design_03_modern_green',  'Design 3 — Modern Grön'),
    ('design_04_dark_executive','Design 4 — Dark Executive'),
    ('design_05_nordic_blue',   'Design 5 — Nordic Blue'),
    ('design_06_creative_sidebar','Design 6 — Creative Sidebar'),
    ('design_07_tech_modern',   'Design 7 — Tech Modern'),
    ('design_08_timeline',      'Design 8 — Timeline'),
    ('design_09_infographic',   'Design 9 — Infografik'),
    ('design_10_premium_gold',  'Design 10 — Premium Gold'),
]

VIEWPORT_W = 794    # A4 width in px
VIEWPORT_H = 1123   # A4 height in px
PREVIEW_W  = 320    # thumbnail width
PREVIEW_H  = 452    # thumbnail height (A4 ratio)


def get_driver():
    """Initialize headless Chrome"""
    try:
        import undetected_chromedriver as uc
        opts = uc.ChromeOptions()
        opts.add_argument('--headless=new')
        opts.add_argument(f'--window-size={VIEWPORT_W},{VIEWPORT_H}')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--hide-scrollbars')
        opts.add_argument('--disable-web-security')
        opts.add_argument('--force-device-scale-factor=1')
        driver = uc.Chrome(options=opts)
        driver.set_window_size(VIEWPORT_W, VIEWPORT_H)
        return driver
    except Exception:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument('--headless=new')
        opts.add_argument(f'--window-size={VIEWPORT_W},{VIEWPORT_H}')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--hide-scrollbars')
        opts.add_argument('--force-device-scale-factor=1')
        driver = webdriver.Chrome(options=opts)
        driver.set_window_size(VIEWPORT_W, VIEWPORT_H)
        return driver


def take_screenshot(driver, html_path: Path, out_path: Path):
    """Navigate to HTML file, wait for fonts, capture screenshot + crop"""
    url = html_path.as_uri()
    driver.get(url)
    time.sleep(2.5)     # wait for Google Fonts to load

    # Take full-page screenshot
    body = driver.find_element('tag name', 'body')
    driver.execute_script(
        "document.body.style.overflow='hidden';"
        "document.documentElement.style.overflow='hidden';"
    )
    png_data = driver.get_screenshot_as_png()

    # Crop and resize to thumbnail
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(png_data))

    # Crop to A4 area (top of page)
    crop_h = min(VIEWPORT_H, img.height)
    img = img.crop((0, 0, VIEWPORT_W, crop_h))

    # Resize to thumbnail
    img = img.resize((PREVIEW_W, PREVIEW_H), Image.LANCZOS)

    # Add a subtle border
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, PREVIEW_W-1, PREVIEW_H-1], outline='#3a3a3a', width=1)

    img.save(str(out_path), 'PNG', optimize=True)
    return True


def main():
    print('\n' + '='*55)
    print('  ApplyMind AI — Design Preview Generator')
    print('='*55)
    print(f'  Templates: {TEMPLATE_DIR}')
    print(f'  Output:    {PREVIEW_DIR}')
    print('='*55 + '\n')

    driver = None
    generated = 0
    skipped   = 0
    failed    = 0

    try:
        print('Startar headless Chrome...')
        driver = get_driver()
        print('Chrome OK\n')

        for key, label in DESIGNS:
            html_path = TEMPLATE_DIR / f'{key}.html'
            out_path  = PREVIEW_DIR  / f'{key}.png'

            if not html_path.exists():
                print(f'  SKIP (saknas): {label}')
                skipped += 1
                continue

            print(f'  Genererar: {label}...', end=' ', flush=True)
            try:
                take_screenshot(driver, html_path, out_path)
                print(f'OK -> {out_path.name}')
                generated += 1
            except Exception as e:
                print(f'FEL: {e}')
                failed += 1

    finally:
        if driver:
            driver.quit()

    print('\n' + '='*55)
    print(f'  Genererade: {generated}')
    print(f'  Hoppade:    {skipped}')
    print(f'  Misslyckade:{failed}')
    print('='*55)
    print('\nKlart! Starta om appen för att se previews.')


if __name__ == '__main__':
    main()
