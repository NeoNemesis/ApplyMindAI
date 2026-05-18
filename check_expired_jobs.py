#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kollar varje Job_NNN_-mapp och flaggar/raderar annonser som inte längre
går att söka (404, "annons utgången", redirect till listningssida, etc.).

Konservativ: bara CLEARLY expired → raderas. Nätverksfel, 5xx, captcha,
LinkedIn login-wall etc. → markeras OKÄNT och behålls.

Användning:
    python check_expired_jobs.py            # dry-run (visar förslag)
    python check_expired_jobs.py --apply    # radera flaggade mappar
    python check_expired_jobs.py --timeout 15
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

try:
    import requests
except ImportError:
    print('FEL: requests-paketet saknas. Installera med: pip install requests')
    sys.exit(1)

JOB_MASTER_DIR = PROJECT_DIR / 'data_folder' / 'output' / 'job_master'
PROCESSED_FILE = JOB_MASTER_DIR / 'processed_jobs.json'

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'
)

# Texter som klart signalerar att annonsen inte längre kan sökas
EXPIRED_TEXT_SIGNALS = [
    'annons är inte längre tillgänglig',
    'annonsen är inte längre tillgänglig',
    'annonsen har upphört',
    'denna annons har upphört',
    'denna tjänst är tillsatt',
    'tjänsten är tillsatt',
    'rekryteringen är avslutad',
    'rekryteringen avslutad',
    'ansökan stängd',
    'sista ansökningsdag har passerat',
    'this job has expired',
    'this job is no longer available',
    'job posting is no longer available',
    'position has been filled',
    'we are no longer accepting applications',
    'application deadline has passed',
]

# Hosts där en redirect till själva root/listning typiskt = utgången annons
LISTING_REDIRECT_HOSTS = {
    'arbetsformedlingen.se': '/platsbanken',
    'jobb.ants.se': '/jobs',
}


def extract_url(folder: Path) -> str | None:
    info = folder / 'job_info.txt'
    if not info.exists():
        return None
    try:
        for line in info.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line.startswith('http://') or line.startswith('https://'):
                return line
            for prefix in ('URL:', 'Jobtech/AF URL:', 'LinkedIn URL:', 'Indeed URL:'):
                if prefix in line:
                    rest = line.split(prefix, 1)[1].strip()
                    if rest.startswith('http'):
                        return rest
    except Exception:
        return None
    return None


def classify_response(url: str, resp: requests.Response) -> Tuple[str, str]:
    """Returnera (status, reason) — status ∈ {'expired','active','unknown'}."""
    code = resp.status_code

    # Tydlig död: 404 / 410
    if code in (404, 410):
        return 'expired', f'HTTP {code}'

    # 4xx (utöver auth/rate limit) som indikerar borttagen annons
    if 400 <= code < 500 and code not in (401, 403, 429):
        return 'expired', f'HTTP {code}'

    # Auth/rate limit/server-fel — vi vet inte
    if code in (401, 403, 429) or 500 <= code < 600:
        return 'unknown', f'HTTP {code}'

    # Redirect till listning?
    final_host = urlparse(resp.url).netloc.lower()
    final_path = urlparse(resp.url).path
    for host, listing_path in LISTING_REDIRECT_HOSTS.items():
        if host in final_host and final_path.rstrip('/').endswith(listing_path.rstrip('/')):
            return 'expired', f'redirected to {host}{listing_path}'

    # Sniffa kroppen
    body = (resp.text or '').lower()
    for signal in EXPIRED_TEXT_SIGNALS:
        if signal in body:
            return 'expired', f'body: "{signal}"'

    return 'active', f'HTTP {code}'


def check_url(url: str, timeout: float) -> Tuple[str, str]:
    """Returnera (status, reason). 'unknown' vid nätverksfel."""
    if not url:
        return 'unknown', 'ingen URL i job_info.txt'
    headers = {
        'User-Agent': USER_AGENT,
        'Accept-Language': 'sv-SE,sv;q=0.9,en;q=0.8',
    }
    try:
        with requests.Session() as s:
            s.headers.update(headers)
            r = s.get(url, timeout=timeout, allow_redirects=True)
            return classify_response(url, r)
    except requests.exceptions.Timeout:
        return 'unknown', 'timeout'
    except requests.exceptions.ConnectionError:
        return 'unknown', 'connection error'
    except requests.exceptions.RequestException as e:
        return 'unknown', f'{type(e).__name__}: {str(e)[:80]}'


def load_processed_jobs() -> List[Dict]:
    if not PROCESSED_FILE.exists():
        return []
    try:
        return json.loads(PROCESSED_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []


def write_processed_jobs(jobs: List[Dict]) -> None:
    PROCESSED_FILE.write_text(
        json.dumps(jobs, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )


def main(apply: bool, timeout: float, sleep_between: float) -> int:
    if not JOB_MASTER_DIR.exists():
        print(f'Hittar inte {JOB_MASTER_DIR}')
        return 1

    folders = sorted(p for p in JOB_MASTER_DIR.iterdir()
                     if p.is_dir() and p.name.startswith('Job_'))
    if not folders:
        print('Inga Job_*-mappar hittade.')
        return 0

    print(f'Kollar {len(folders)} jobb-URL:er (timeout={timeout}s)\n')

    expired: List[Tuple[Path, str]] = []
    unknown: List[Tuple[Path, str]] = []
    active: List[Path] = []

    for i, folder in enumerate(folders, 1):
        url = extract_url(folder)
        status, reason = check_url(url or '', timeout)
        name = folder.name[:75]
        marker = {'expired': '[DEAD]', 'unknown': '[?]', 'active': '[OK]'}[status]
        print(f'  [{i:>2}/{len(folders)}] {marker:<7} {name} — {reason}')

        if status == 'expired':
            expired.append((folder, reason))
        elif status == 'unknown':
            unknown.append((folder, reason))
        else:
            active.append(folder)

        if sleep_between:
            time.sleep(sleep_between)

    print(f'\nResultat: {len(active)} aktiva, {len(expired)} utgångna, {len(unknown)} okända')

    if not expired:
        print('\nInga utgångna annonser att radera.')
        return 0

    print('\nFlaggade för radering:')
    for folder, reason in expired:
        print(f'  - {folder.name}  ({reason})')

    if not apply:
        print('\n--- DRY RUN. Kör med --apply för att radera. ---')
        return 0

    # Radera och synka processed_jobs.json
    deleted_urls = set()
    for folder, _ in expired:
        url = extract_url(folder)
        if url:
            deleted_urls.add(url)
        try:
            shutil.rmtree(folder)
            print(f'  [OK] raderade {folder.name}')
        except Exception as e:
            print(f'  [FEL] kunde inte radera {folder.name}: {e}')

    processed = load_processed_jobs()
    before = len(processed)
    processed = [j for j in processed if j.get('url') not in deleted_urls]
    if len(processed) != before:
        write_processed_jobs(processed)
        print(f'\nSynkade processed_jobs.json: {before} → {len(processed)} entries')

    print(f'\nKlart. Raderade {len(expired)} utgångna jobb-mappar.')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='Radera flaggade mappar')
    ap.add_argument('--timeout', type=float, default=10.0, help='HTTP-timeout per URL (sek)')
    ap.add_argument('--sleep', type=float, default=0.3,
                    help='Paus mellan requests (sek) för att inte överbelasta sites')
    args = ap.parse_args()
    sys.exit(main(apply=args.apply, timeout=args.timeout, sleep_between=args.sleep))
