"""Tests for src/utils/job_dedup.py."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.job_dedup import (  # noqa: E402
    build_sets_from_processed,
    is_duplicate,
    job_signature,
    mark_seen,
    normalize_company,
    normalize_title,
    normalize_url,
)


# --- URL normalization --------------------------------------------------------

def test_normalize_url_strips_promotion_param():
    a = normalize_url('https://jobb.softhouse.se/jobs/7484216-erfaren-java-utvecklare/applications/new?promotion=1920600-arbetsformedlingen')
    b = normalize_url('https://jobb.softhouse.se/jobs/7484216-erfaren-java-utvecklare/applications/new?promotion=9999999-other')
    assert a == b
    assert 'promotion' not in a


def test_normalize_url_strips_utm():
    a = normalize_url('https://example.com/job/1?utm_source=foo&utm_medium=bar&keep=1')
    assert 'utm_' not in a
    assert 'keep=1' in a


def test_normalize_url_lowercases_host_keeps_path_case():
    u = normalize_url('https://Example.COM/Path/To?ref=x')
    assert u.startswith('https://example.com/Path/To')
    assert 'ref=' not in u


def test_normalize_url_handles_empty_and_none():
    assert normalize_url('') == ''
    assert normalize_url(None) == ''


def test_normalize_url_strips_trailing_slash():
    a = normalize_url('https://example.com/job/1/')
    b = normalize_url('https://example.com/job/1')
    assert a == b


# --- Company / title normalization --------------------------------------------

def test_normalize_company_strips_legal_suffix():
    assert normalize_company('Softhouse Nordic AB') == normalize_company('Softhouse Nordic Aktiebolag')
    assert 'ab' not in normalize_company('Softhouse Nordic AB').split()


def test_normalize_company_unknown_returns_empty():
    assert normalize_company('Okänt företag') == ''
    assert normalize_company('') == ''


def test_normalize_title_drops_location_tail():
    assert normalize_title('Systemutvecklare till Amaceit // Stockholm') == \
           normalize_title('Systemutvecklare')


def test_normalize_title_strips_accents_case():
    assert normalize_title('Webbutvecklare med fokus på e-handel') == \
           normalize_title('WEBBUTVECKLARE MED FOKUS PA E-HANDEL')


# --- Signature + dedup --------------------------------------------------------

def test_softhouse_repost_with_different_job_id_dedupes():
    job_a = {
        'title': 'Erfaren Java-utvecklare',
        'company': 'Softhouse Nordic AB',
        'url': 'https://jobb.softhouse.se/jobs/7484216-erfaren-java-utvecklare/applications/new?promotion=1920600',
    }
    job_b = {
        'title': 'Erfaren Java-utvecklare',
        'company': 'Softhouse Nordic AB',
        'url': 'https://jobb.softhouse.se/jobs/7609721-erfaren-java-utvecklare/applications/new?promotion=1958835',
    }
    seen_urls, seen_sigs = set(), set()
    mark_seen(job_a, seen_urls, seen_sigs)
    assert is_duplicate(job_b, seen_urls, seen_sigs), \
        'repost with new job_id should dedupe via (company, title) signature'


def test_unknown_company_falls_back_to_url():
    # Två jobb där företaget misslyckas extraheras i ena fallet — bara URL
    # avgör om de är dubletter. Olika URL = inte dublett.
    job_a = {
        'title': 'Webbutvecklare med fokus på e-handel',
        'company': 'Uppstuk',
        'url': 'https://uppstuk.se/jobs/1',
    }
    job_b = {
        'title': 'Webbutvecklare med fokus på e-handel',
        'company': 'Okänt företag',
        'url': 'https://uppstuk.se/jobs/2',
    }
    seen_urls, seen_sigs = set(), set()
    mark_seen(job_a, seen_urls, seen_sigs)
    assert not is_duplicate(job_b, seen_urls, seen_sigs), \
        'Okänt företag bör inte matcha kända företag på enbart titel'


def test_three_different_jobs_same_company_not_deduped():
    seen_urls, seen_sigs = set(), set()
    for title in ['RPA-utvecklare UiPath', 'Junior systemutvecklare .Net', 'Systemutvecklare Frontend Angular']:
        job = {
            'title': title,
            'company': 'Läkemedelsverket',
            'url': f'https://lv.se/{title.lower().replace(" ", "-")}',
        }
        assert not is_duplicate(job, seen_urls, seen_sigs)
        mark_seen(job, seen_urls, seen_sigs)
    assert len(seen_sigs) == 3


def test_build_sets_from_processed():
    processed = [
        {'company': 'Foo AB', 'title': 'Dev', 'url': 'https://foo.se/a?utm_source=x'},
        {'company': 'Bar AB', 'title': 'Eng', 'url': 'https://bar.se/b?promotion=1'},
    ]
    urls, sigs = build_sets_from_processed(processed)
    assert len(urls) == 2
    assert len(sigs) == 2
    new_job = {'company': 'Foo AB', 'title': 'Dev', 'url': 'https://foo.se/a?utm_source=y'}
    assert is_duplicate(new_job, urls, sigs)


def test_url_only_jobs_still_dedupe():
    job = {'title': '', 'company': '', 'url': 'https://x.com/1'}
    seen_urls, seen_sigs = set(), set()
    mark_seen(job, seen_urls, seen_sigs)
    job2 = {'title': '', 'company': '', 'url': 'https://x.com/1?utm_campaign=foo'}
    assert is_duplicate(job2, seen_urls, seen_sigs)


if __name__ == '__main__':
    import inspect
    mod = sys.modules[__name__]
    tests = [(name, fn) for name, fn in inspect.getmembers(mod, inspect.isfunction)
             if name.startswith('test_')]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f'  OK  {name}')
            passed += 1
        except AssertionError as e:
            print(f'  FAIL {name}: {e}')
        except Exception as e:
            print(f'  ERR  {name}: {type(e).__name__}: {e}')
    print(f'\n{passed}/{len(tests)} passed')
    sys.exit(0 if passed == len(tests) else 1)
