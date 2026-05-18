"""
Regressionstest: säkerställer att 'text-align: justify' aldrig återinförs
i CV- eller cover-letter-mallar.

Justify orsakar oacceptabla 2-3 mellanslag mellan ord i PDF-rendering
när raderna innehåller långa orytbara termer (REST-API:er, taskit-platform,
Node.js/TypeScript-backend, m.fl.). All textinnehållande layout MÅSTE
använda 'text-align: left'.

Detta test körs som del av suite — om någon (människa eller AI) lägger
tillbaka 'justify' i en mall så failar testet.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIRS = [
    ROOT / 'src' / 'libs' / 'resume_and_cover_builder',
]
TARGET_EXTS = {'.html', '.css', '.py'}
JUSTIFY_RE = re.compile(r'text-align\s*:\s*justify', re.IGNORECASE)


def _collect_files():
    files = []
    for base in TEMPLATE_DIRS:
        if not base.exists():
            continue
        for ext in TARGET_EXTS:
            files.extend(base.rglob(f'*{ext}'))
    return files


def test_no_text_align_justify_in_templates():
    offenders = []
    for path in _collect_files():
        try:
            content = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            if JUSTIFY_RE.search(line):
                offenders.append(f'{path.relative_to(ROOT)}:{lineno}: {line.strip()}')
    assert not offenders, (
        "text-align: justify hittades i mallar — det orsakar uppblåsta "
        "mellanslag mellan ord i PDF-rendering. Använd 'text-align: left'.\n\n"
        + "\n".join(offenders)
    )


if __name__ == '__main__':
    test_no_text_align_justify_in_templates()
    print("OK: inga 'text-align: justify' i mallar.")
