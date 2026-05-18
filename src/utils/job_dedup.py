"""
Job dedup helpers.

Två lager för att fånga "samma jobb i olika skepnad":
  1. URL-normalisering — strippar tracking-parametrar (promotion, utm_*) och
     fragment så att samma annons via olika spårningslänkar dedupas.
  2. Fuzzy signatur (företag, titel) — lowercase, ta bort vanliga suffix
     ("AB", "Aktiebolag"), "till X", "// Stockholm", normalisera whitespace
     och accenter. Fångar reposts med nya job_id och scraping-fel som
     "Okänt företag".

Används av JobMaster och cleanup-rutinen.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, Optional, Set, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


JobSignature = Tuple[str, str]  # (norm_company, norm_title)

# Query-parametrar som ALDRIG bör påverka jobbets identitet
_TRACKING_PARAM_PREFIXES = ('utm_', 'mc_', 'gclid', 'fbclid')
_TRACKING_PARAM_EXACT = {
    'promotion', 'promo', 'ref', 'refsrc', 'trk', 'trkparms', 'src',
    'source', 'campaign', 'medium', 'tk', 'rcid', 'tip', 'tag',
}

# Generiska "okänt företag"-strängar som inte säger något om identitet
_UNKNOWN_COMPANY_TOKENS = {
    'okänt företag', 'okant foretag', 'unknown', 'unknown company',
    'n/a', 'na', '-', '',
}

# Suffix som tas bort från företagsnamn vid signatur
_COMPANY_SUFFIX_RE = re.compile(
    r'\b(aktiebolag|ab|hb|kb|holding|group|sweden|sverige|nordic|nordics)\b',
    re.IGNORECASE,
)

# "till X", "// stad", "i Stockholm" — bort från titel vid signatur
_TITLE_TAIL_RE = re.compile(
    r'\s*(?://\s*[^/]+'
    r'|\s+till\s+.+'
    r'|\s+i\s+(?:Stockholm|Uppsala|Göteborg|Malmö|Solna|Sundbyberg|Lund|Linköping|Örebro|Västerås|Umeå)\s*$'
    r')',
    re.IGNORECASE,
)


def _strip_accents(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFKD', s)
        if not unicodedata.combining(c)
    )


def normalize_url(url: Optional[str]) -> str:
    """Returnera kanonisk form av URL för dedup.

    - Lowercase host
    - Strippa fragment
    - Ta bort tracking-parametrar (utm_*, promotion, ref, etc.)
    - Sortera kvarvarande query-params för stabil jämförelse
    - Strippa trailing slash i path
    """
    if not url:
        return ''
    try:
        p = urlparse(url.strip())
    except Exception:
        return url.strip().lower()

    host = (p.netloc or '').lower()
    path = (p.path or '').rstrip('/')

    keep = []
    for k, v in parse_qsl(p.query, keep_blank_values=False):
        kl = k.lower()
        if kl in _TRACKING_PARAM_EXACT:
            continue
        if any(kl.startswith(pref) for pref in _TRACKING_PARAM_PREFIXES):
            continue
        keep.append((kl, v))
    keep.sort()
    query = urlencode(keep)

    return urlunparse((p.scheme.lower() or 'https', host, path, '', query, ''))


def _normalize_token(s: Optional[str]) -> str:
    if not s:
        return ''
    s = _strip_accents(s).lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def normalize_company(company: Optional[str]) -> str:
    if not company:
        return ''
    base = company.strip()
    if _normalize_token(base) in _UNKNOWN_COMPANY_TOKENS:
        return ''  # tomt = matchar via titel + URL ändå
    cleaned = _COMPANY_SUFFIX_RE.sub(' ', base)
    return _normalize_token(cleaned)


def normalize_title(title: Optional[str]) -> str:
    if not title:
        return ''
    cleaned = _TITLE_TAIL_RE.sub('', title.strip())
    return _normalize_token(cleaned)


def job_signature(company: Optional[str], title: Optional[str]) -> JobSignature:
    """Returnera (norm_company, norm_title) som dedup-nyckel.

    Tom signatur (båda fält tomma) returneras som ('', '') och behandlas
    som icke-matchbar — anroparen får falla tillbaka på URL-jämförelse.
    """
    return (normalize_company(company), normalize_title(title))


def is_empty_signature(sig: JobSignature) -> bool:
    return not sig[0] and not sig[1]


def is_duplicate(
    job: Dict,
    seen_urls: Set[str],
    seen_signatures: Set[JobSignature],
) -> bool:
    """True om jobbet redan finns i något set:et.

    Anroparen ansvarar för att lägga till URL/signatur EFTER att jobbet
    accepterats (annars dedupas första instansen mot sig själv).
    """
    url_norm = normalize_url(job.get('url'))
    if url_norm and url_norm in seen_urls:
        return True

    sig = job_signature(job.get('company'), job.get('title'))
    if not is_empty_signature(sig) and sig in seen_signatures:
        return True

    return False


def mark_seen(
    job: Dict,
    seen_urls: Set[str],
    seen_signatures: Set[JobSignature],
) -> None:
    """Registrera jobbet som sett. Mutterar set:en på plats."""
    url_norm = normalize_url(job.get('url'))
    if url_norm:
        seen_urls.add(url_norm)
    sig = job_signature(job.get('company'), job.get('title'))
    if not is_empty_signature(sig):
        seen_signatures.add(sig)


def build_sets_from_processed(
    processed_jobs: Iterable[Dict],
) -> Tuple[Set[str], Set[JobSignature]]:
    """Bygg url- och signatur-set från en lista processade jobb."""
    urls: Set[str] = set()
    sigs: Set[JobSignature] = set()
    for job in processed_jobs:
        url_norm = normalize_url(job.get('url'))
        if url_norm:
            urls.add(url_norm)
        sig = job_signature(job.get('company'), job.get('title'))
        if not is_empty_signature(sig):
            sigs.add(sig)
    return urls, sigs
