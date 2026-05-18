#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hittar och raderar duplicerade Job_NNN_-mappar i data_folder/output/job_master/.

Två jobb anses vara dubletter om de delar normaliserad signatur
(företag, titel) — se src/utils/job_dedup.py för normaliseringsregler.

Strategi: behåll den senast modifierade mappen (mtime), radera övriga.
Synkronisera även processed_jobs.json så raderade URL:er försvinner därifrån.

Användning:
    python cleanup_duplicate_jobs.py            # dry-run, visa vad som skulle raderas
    python cleanup_duplicate_jobs.py --apply    # radera på riktigt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

# Windows-konsoler kan default vara cp1252 — säkra UTF-8 för output
for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from src.utils.job_dedup import job_signature, JobSignature  # noqa: E402

JOB_MASTER_DIR = PROJECT_DIR / 'data_folder' / 'output' / 'job_master'
PROCESSED_FILE = JOB_MASTER_DIR / 'processed_jobs.json'

JOB_FOLDER_RE = re.compile(r'^Job_(\d+)_(.+?)_(.+)$')


def parse_folder_name(name: str) -> Tuple[str, str] | None:
    """Returnera (company, title) från mappnamn 'Job_NNN_Company_Title'."""
    m = JOB_FOLDER_RE.match(name)
    if not m:
        return None
    return m.group(2), m.group(3)


def read_job_info(folder: Path) -> Tuple[str, str] | None:
    """Läs (company, title) från job_info.txt om den finns (mer exakt)."""
    info = folder / 'job_info.txt'
    if not info.exists():
        return None
    company = title = ''
    try:
        for line in info.read_text(encoding='utf-8').splitlines():
            if 'Titel:' in line:
                title = line.split('Titel:', 1)[1].strip()
            elif 'Företag:' in line:
                company = line.split('Företag:', 1)[1].strip()
        if company or title:
            return company, title
    except Exception:
        pass
    return None


def collect_folders(root: Path) -> Dict[JobSignature, List[Tuple[Path, float]]]:
    """Gruppera Job_NNN_-mappar efter signatur."""
    groups: Dict[JobSignature, List[Tuple[Path, float]]] = defaultdict(list)
    for entry in root.iterdir():
        if not entry.is_dir() or not entry.name.startswith('Job_'):
            continue
        meta = read_job_info(entry) or parse_folder_name(entry.name)
        if not meta:
            continue
        company, title = meta
        sig = job_signature(company, title)
        if not sig[0] and not sig[1]:
            continue
        groups[sig].append((entry, entry.stat().st_mtime))
    return groups


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


def main(apply: bool) -> int:
    if not JOB_MASTER_DIR.exists():
        print(f'Hittar inte {JOB_MASTER_DIR}')
        return 1

    groups = collect_folders(JOB_MASTER_DIR)
    duplicate_groups = {sig: items for sig, items in groups.items() if len(items) > 1}

    if not duplicate_groups:
        print('Inga dubletter hittade.')
        return 0

    print(f'Hittade {len(duplicate_groups)} grupper med dubletter '
          f'({sum(len(v) - 1 for v in duplicate_groups.values())} mappar att radera)\n')

    to_delete: List[Path] = []
    for sig, items in sorted(duplicate_groups.items(), key=lambda kv: kv[0]):
        items.sort(key=lambda t: t[1], reverse=True)  # senaste först
        keep, *dupes = items
        company, title = sig
        print(f'  signatur: ({company!r}, {title!r})')
        print(f'    BEHÅLL: {keep[0].name}')
        for d in dupes:
            print(f'    RADERA: {d[0].name}')
            to_delete.append(d[0])
        print()

    if not apply:
        print('--- DRY RUN. Kör med --apply för att radera. ---')
        return 0

    deleted_folder_names = set()
    for path in to_delete:
        if not path.exists():
            # Kan ha raderats av en tidigare körning som kraschade efter rmtree
            deleted_folder_names.add(path.name)
            print(f'  [OK] redan borta: {path.name}')
            continue
        try:
            shutil.rmtree(path)
            deleted_folder_names.add(path.name)
            print(f'  [OK] raderade {path.name}')
        except Exception as e:
            print(f'  [FEL] kunde inte radera {path.name}: {e}')

    # Synka processed_jobs.json: ta bort entries vars (company, title)-signatur
    # matchar en raderad mapp och INTE har en motsvarande kvarvarande mapp.
    surviving_sigs = set()
    for entry in JOB_MASTER_DIR.iterdir():
        if not entry.is_dir() or not entry.name.startswith('Job_'):
            continue
        meta = read_job_info(entry) or parse_folder_name(entry.name)
        if meta:
            surviving_sigs.add(job_signature(*meta))

    processed = load_processed_jobs()
    before = len(processed)
    processed = [
        j for j in processed
        if job_signature(j.get('company'), j.get('title')) in surviving_sigs
        or job_signature(j.get('company'), j.get('title')) == ('', '')
    ]
    if len(processed) != before:
        write_processed_jobs(processed)
        print(f'\nSynkade processed_jobs.json: {before} → {len(processed)} entries')

    print(f'\nKlart. Raderade {len(to_delete)} duplicerade mappar.')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='Radera på riktigt')
    args = ap.parse_args()
    sys.exit(main(apply=args.apply))
