"""
CV → taxonomiprofil via Jobtechs publika JobAd Enrichments API — och en helt
gratis "pre-score" av annonser mot profilen.

Idén (Tier 1 av den smarta sökningen): i stället för att låta LLM:en titta på
varje annons extraherar vi EN gång användarens yrken/kompetenser/egenskaper ur
CV:t + referensbrevet med Arbetsförmedlingens egen ML-tjänst (samma taxonomi
som annonserna är kodade i — funkar på både svenska och engelska). Profilen
cachas per användare och byggs bara om när CV-texten ändras.

Vid sökning poängsätts varje träff mot profilen (must_have/nice_to_have-skills
ur annonsen + omnämnanden i beskrivningen) — noll API-kostnad, LLM:en används
fortfarande bara som sista lager (ATS-filtret) på de bäst rankade jobben.

Allt är best-effort: utan nät/utan CV returneras None och sökningen beter sig
exakt som förut.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime
from pathlib import Path

ENRICH_URL = 'https://jobad-enrichments-api.jobtechdev.se/enrichtextdocuments'
PROFILE_FILENAME = 'taxonomy_profile.json'

# Max antal termer per kategori som sparas i profilen (de med högst prediction).
_MAX_TERMS = 40


def _norm(s: str) -> str:
    return (s or '').strip().lower()


def _read_source_text(data_dir: Path) -> str | None:
    """CV-yaml + referensbrev som EN textmassa. None om CV saknas."""
    resume = data_dir / 'plain_text_resume.yaml'
    if not resume.exists():
        return None
    try:
        text = resume.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return None
    letter = data_dir / 'reference_cover_letter.txt'
    if letter.exists():
        try:
            text += '\n' + letter.read_text(encoding='utf-8', errors='replace')
        except Exception:
            pass
    return text.strip() or None


def _call_enrich_api(text: str, timeout: float = 20.0) -> dict | None:
    """POST till JobAd Enrichments. Returnerar enriched_candidates eller None."""
    payload = {
        'documents_input': [{
            'doc_id': 'cv',
            'doc_headline': 'CV och personligt brev',
            # API:et är byggt för annonstexter men extraherar lika gärna ur CV.
            'doc_text': text[:40000],
        }],
        'include_terms_info': False,
    }
    req = urllib.request.Request(
        ENRICH_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json',
                 'Accept': 'application/json',
                 'User-Agent': 'ApplyMindAI/4.0'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    if isinstance(data, list) and data:
        return (data[0] or {}).get('enriched_candidates') or None
    return None


def _extract_terms(candidates: dict, key: str) -> list[dict]:
    """[{label, score}] sorterat på prediction, dedupat på normaliserad label."""
    out, seen = [], set()
    items = sorted(
        (candidates or {}).get(key, []) or [],
        key=lambda c: float((c or {}).get('prediction', 0) or 0),
        reverse=True,
    )
    for c in items:
        label = (c or {}).get('concept_label') or (c or {}).get('term') or ''
        n = _norm(label)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append({'label': label.strip(),
                    'score': round(float(c.get('prediction', 0) or 0), 3)})
        if len(out) >= _MAX_TERMS:
            break
    return out


def get_or_build_profile(data_dir: Path) -> dict | None:
    """Hämta cachad profil, eller bygg om ifall CV-texten ändrats.

    Returnerar None om CV saknas eller API:et inte gick att nå (och ingen
    cache finns) — anroparen ska då köra vidare precis som utan profil.
    """
    data_dir = Path(data_dir)
    text = _read_source_text(data_dir)
    if not text:
        return None
    source_hash = hashlib.sha1(text.encode('utf-8')).hexdigest()

    cache_file = data_dir / PROFILE_FILENAME
    cached = None
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding='utf-8'))
        except Exception:
            cached = None
    if cached and cached.get('source_hash') == source_hash:
        return cached

    try:
        candidates = _call_enrich_api(text)
    except Exception:
        # Nätfel/API nere: hellre en inaktuell profil än ingen alls.
        return cached
    if not candidates:
        return cached

    profile = {
        'source_hash':  source_hash,
        'built_at':     datetime.now().isoformat(timespec='seconds'),
        'occupations':  _extract_terms(candidates, 'occupations'),
        'competencies': _extract_terms(candidates, 'competencies'),
        'traits':       _extract_terms(candidates, 'traits'),
    }
    try:
        cache_file.write_text(json.dumps(profile, ensure_ascii=False, indent=2),
                              encoding='utf-8')
    except Exception:
        pass
    return profile


# ── Poängsättning ────────────────────────────────────────────────────────────

def _user_term_set(profile: dict) -> set[str]:
    terms = set()
    for key in ('competencies', 'occupations'):
        for t in (profile or {}).get(key, []) or []:
            n = _norm(t.get('label', ''))
            if n:
                terms.add(n)
    return terms


def _term_match(ad_term: str, user_terms: set[str]) -> bool:
    """Exakt normaliserad träff, eller innehålls-träff för längre termer
    (fångar "python" ↔ "python (programmeringsspråk)" utan att korta ord
    som "c" matchar allt)."""
    n = _norm(ad_term)
    if not n:
        return False
    if n in user_terms:
        return True
    if len(n) > 3:
        for u in user_terms:
            if len(u) > 3 and (n in u or u in n):
                return True
    return False


def score_job(profile: dict, title: str, description: str,
              must_labels: list[str], nice_labels: list[str]) -> dict:
    """Poäng 0–100 för hur väl annonsen matchar profilen, plus förklaring.

    Viktning: krav (must_have) väger tyngst, meriterande (nice_to_have)
    därefter; utan strukturerade skills faller vi tillbaka på hur många av
    användarens kompetenser som nämns i annonstexten. Yrkes-träff i titeln
    ger alltid en bonus.
    """
    user_terms = _user_term_set(profile)
    if not user_terms:
        return {'score': None, 'matched': [], 'missing_must': []}

    title_l = _norm(title)
    occupations = [_norm(o.get('label', '')) for o in profile.get('occupations', [])]
    title_bonus = any(o and (o in title_l or title_l in o) for o in occupations)

    must = [m for m in (must_labels or []) if _norm(m)]
    nice = [n for n in (nice_labels or []) if _norm(n)]
    matched_must = [m for m in must if _term_match(m, user_terms)]
    matched_nice = [n for n in nice if _term_match(n, user_terms)]
    missing_must = [m for m in must if m not in matched_must]

    if must:
        score = 70.0 * len(matched_must) / len(must)
        if nice:
            score += 20.0 * len(matched_nice) / len(nice)
        else:
            score += 10.0
    elif nice:
        score = 25.0 + 55.0 * len(matched_nice) / len(nice)
    else:
        # Ostrukturerad annons: räkna omnämnanden av användarens kompetenser.
        desc_l = _norm(description)
        mentions = [t for t in user_terms if len(t) > 3 and t in desc_l]
        denom = max(1, min(8, len(user_terms)))
        score = 20.0 + 60.0 * min(1.0, len(mentions) / denom)
        matched_must = mentions[:6]

    if title_bonus:
        score += 10.0

    return {
        'score': int(max(0, min(100, round(score)))),
        'matched': (matched_must + matched_nice)[:6],
        'missing_must': missing_must[:4],
    }


def extract_skill_labels(block: dict) -> list[str]:
    """Plocka label-strängar ur ett must_have/nice_to_have-block från en
    Jobtech-annons (items är dictar med 'label' — eller råa strängar)."""
    labels = []
    for key in ('skills', 'competencies', 'languages', 'education',
                'work_experiences'):
        for item in (block or {}).get(key, []) or []:
            if isinstance(item, dict):
                lbl = item.get('label') or item.get('concept_label') or ''
            else:
                lbl = str(item)
            lbl = lbl.strip()
            if lbl:
                labels.append(lbl)
    return labels
