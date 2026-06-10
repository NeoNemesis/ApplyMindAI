#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ApplyMind AI — Webbgränssnitt
============================
Flask-baserat webbgränssnitt för ApplyMind AI jobbsökningssystem.

Starta: python web_app.py
URL:    http://localhost:5000
"""

import base64
import os
import sys

# Tvinga UTF-8 på Windows-konsolen så emojis i loggar inte kraschar
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import re
import json
import yaml
import shutil
import threading
import queue
import time
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote as _url_quote
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_file, Response, jsonify, stream_with_context,
    session, g
)

# Fix Windows console encoding (stdout is None when launched via pythonw.exe)
if sys.platform == 'win32' and sys.stdout is not None:
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

_secret = os.environ.get('FLASK_SECRET', '')
_dev_placeholder = 'applymind-ai-dev-secret-change-in-prod-2026'
if os.environ.get('FLASK_ENV') == 'production' and (not _secret or _secret == _dev_placeholder):
    raise RuntimeError(
        "FLASK_SECRET måste sättas till ett slumpmässigt 32+ teckens värde i produktion. "
        "Generera: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = _secret or _dev_placeholder

# ── Database + Auth ───────────────────────────────────────────
from models import db, User, AuditLog
from flask_login import LoginManager, current_user, login_required
from flask_migrate import Migrate
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _limiter_available = True
except ImportError:
    _limiter_available = False
from auth import auth_bp

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    f"sqlite:///{BASE_DIR / 'instance' / 'applymind.db'}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
_is_prod = os.environ.get('FLASK_ENV') == 'production'
app.config['REMEMBER_COOKIE_SECURE']   = _is_prod
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE']    = _is_prod
app.config['SESSION_COOKIE_SAMESITE']  = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY']  = True

db.init_app(app)
migrate = Migrate(app, db)

if _limiter_available:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[],
        storage_uri="memory://",
    )
else:
    class _NoopLimiter:
        def limit(self, *a, **kw):
            return lambda f: f
    limiter = _NoopLimiter()

login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Du måste logga in för att komma åt den sidan.'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))

app.register_blueprint(auth_bp)

from admin import admin_bp
app.register_blueprint(admin_bp)

# Create DB tables on first run
with app.app_context():
    (BASE_DIR / 'instance').mkdir(exist_ok=True)
    db.create_all()

# ── i18n helpers ─────────────────────────────────────────────
from src.i18n import get_translations, LANGUAGE_NAMES

@app.before_request
def load_language():
    """Load language from session or query param into g.t (translations)"""
    if 'lang' in request.args:
        session['lang'] = request.args['lang']
    lang = session.get('lang', 'sv')
    g.lang = lang
    g.t    = get_translations(lang)
    g.languages = LANGUAGE_NAMES

@app.context_processor
def inject_globals():
    return dict(
        t            = getattr(g, 't', get_translations('sv')),
        lang         = getattr(g, 'lang', 'sv'),
        languages    = LANGUAGE_NAMES,
        app_name     = 'ApplyMind AI',
        current_user = current_user,
    )

# ============================================================
# PATHS — per-user helpers
# ============================================================
# Legacy global paths (used as fallback / for unauthenticated contexts)
DATA_DIR        = BASE_DIR / 'data_folder'
OUTPUT_DIR      = DATA_DIR / 'output' / 'job_master'

INSTANCE_UPLOADS = BASE_DIR / 'instance' / 'uploads'


def _user_data_dir(user_id: int | None = None) -> Path:
    """Return per-user data directory, creating it if needed."""
    uid = user_id
    if uid is None:
        try:
            from flask_login import current_user as _cu
            if _cu.is_authenticated:
                uid = _cu.id
        except Exception:
            pass
    if uid is None:
        return DATA_DIR          # legacy fallback
    path = INSTANCE_UPLOADS / f'user_{uid}' / 'data'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _user_output_dir(user_id: int | None = None) -> Path:
    """Return per-user output/job_master directory, creating it if needed."""
    uid = user_id
    if uid is None:
        try:
            from flask_login import current_user as _cu
            if _cu.is_authenticated:
                uid = _cu.id
        except Exception:
            pass
    if uid is None:
        return OUTPUT_DIR        # legacy fallback
    path = INSTANCE_UPLOADS / f'user_{uid}' / 'output' / 'job_master'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _u(filename: str) -> Path:
    """Shortcut: per-user data dir + filename."""
    return _user_data_dir() / filename


def _o(filename: str) -> Path:
    """Shortcut: per-user output dir + filename."""
    return _user_output_dir() / filename


# Named path helpers (replace hardcoded globals in route handlers)
def RESUME_YAML()     -> Path: return _u('plain_text_resume.yaml')
def PREFS_YAML()      -> Path: return _u('work_preferences.yaml')
def COVER_LETTER()    -> Path: return _u('reference_cover_letter.txt')
def PROCESSED_JOBS()  -> Path: return _o('processed_jobs.json')
def FOUND_JOBS()      -> Path: return _o('found_jobs.json')
def OPENAI_CALLS()    -> Path: return _o('open_ai_calls.json')
def TRACKER_FILE()    -> Path: return _u('tracker_status.json')
def SCHEDULER_FILE()  -> Path: return _u('scheduler_config.json')

# ============================================================
# SEARCH STATE — per-user (keyed by user_id)
# ============================================================
_search_lock = threading.Lock()
_user_search_states: dict = {}   # uid -> state dict
_user_search_queues: dict = {}   # uid -> Queue
_user_stop_flags:    dict = {}   # uid -> bool


def _get_uid() -> int | None:
    try:
        from flask_login import current_user as _cu
        return _cu.id if _cu.is_authenticated else None
    except Exception:
        return None


def _search_state(uid: int | None) -> dict:
    if uid is None:
        return {'running': False, 'output': [], 'error': None,
                'progress': 0, 'started_at': None, 'finished_at': None}
    if uid not in _user_search_states:
        _user_search_states[uid] = {
            'running': False, 'output': [], 'error': None,
            'progress': 0, 'started_at': None, 'finished_at': None,
        }
    return _user_search_states[uid]


def _search_queue(uid: int | None) -> queue.Queue:
    if uid is None:
        return queue.Queue()
    if uid not in _user_search_queues:
        _user_search_queues[uid] = queue.Queue()
    return _user_search_queues[uid]


def _is_stop_requested(uid: int | None) -> bool:
    return bool(_user_stop_flags.get(uid, False))


def _set_stop_flag(uid: int | None, value: bool) -> None:
    if uid is not None:
        _user_stop_flags[uid] = value


# Legacy aliases — used in old code that referenced the global directly.
# Routed to uid=None (anonymous fallback) to avoid NameError during migration.
search_state = _search_state(None)
search_queue  = _search_queue(None)


# ============================================================
# KRYPTERING — per-user API-nycklar
# ============================================================

def _get_cipher():
    """Returnerar Fernet-cipher härledd från ENCRYPTION_KEY (eller FLASK_SECRET)."""
    from cryptography.fernet import Fernet
    import base64, hashlib
    raw = os.environ.get('ENCRYPTION_KEY') or os.environ.get('FLASK_SECRET', 'dev')
    derived = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(derived)

def encrypt_secret(value: str) -> str:
    """Krypterar en sträng. Returnerar tom sträng om value är tom."""
    if not value:
        return ''
    return _get_cipher().encrypt(value.encode()).decode()

def decrypt_secret(value: str) -> str:
    """Dekrypterar en krypterad sträng. Returnerar tom sträng vid fel."""
    if not value:
        return ''
    try:
        return _get_cipher().decrypt(value.encode()).decode()
    except Exception:
        return ''

def get_user_llm(temperature: float = 0.4, timeout: int = 60):
    """
    Returnerar LLM med användarens nyckel OCH sätter thread-local context
    så att alla get_llm()-anrop i src/ (CV-generering, brev, jobbparser)
    också använder rätt nyckel för denna tråd.
    """
    from src.libs.resume_and_cover_builder.llm.llm_factory import (
        get_llm, set_user_llm_context
    )
    try:
        from flask_login import current_user as _cu
        if _cu and _cu.is_authenticated and _cu.llm_api_key:
            key      = decrypt_secret(_cu.llm_api_key)
            provider = _cu.llm_provider or ''
            model    = _cu.llm_model or ''
            set_user_llm_context(key, provider, model)
            return get_llm(temperature=temperature, timeout=timeout,
                           api_key=key, provider=provider, model=model)
    except Exception:
        pass
    return get_llm(temperature=temperature, timeout=timeout)


def _set_search_thread_llm_context(user_id: int):
    """
    Sätts i söktrådarna (background threads) innan job_master körs.
    Säkerställer att CV- och brevgenerering använder rätt nyckel.
    """
    from src.libs.resume_and_cover_builder.llm.llm_factory import (
        set_user_llm_context, clear_user_llm_context
    )
    try:
        with app.app_context():
            from models import User
            u = User.query.get(user_id)
            if u and u.llm_api_key:
                set_user_llm_context(
                    decrypt_secret(u.llm_api_key),
                    u.llm_provider or '',
                    u.llm_model or '',
                )
                return
    except Exception:
        pass
    clear_user_llm_context()

def _validate_api_key(provider: str, api_key: str) -> str | None:
    """Validerar API-nyckelformat. Returnerar felbeskrivning eller None om OK."""
    if not api_key:
        return None  # Tom = ingen ändring
    # Sanera: ta bort whitespace inkl. newlines
    api_key = api_key.strip()
    if '\n' in api_key or '\r' in api_key or '\t' in api_key:
        return 'API-nyckeln innehåller ogiltiga tecken. Kopiera bara själva nyckeln.'
    if len(api_key) > 500:
        return 'API-nyckeln är för lång. Kontrollera att du klistrade in rätt.'
    if provider == 'openai':
        if not api_key.startswith('sk-'):
            return 'OpenAI API-nycklar börjar alltid med "sk-". Kontrollera nyckeln.'
        if api_key.startswith('sk-ant-'):
            return 'Det ser ut som en Anthropic-nyckel. Välj "Anthropic" som leverantör.'
    if provider == 'anthropic' and not api_key.startswith('sk-ant-'):
        return 'Anthropic API-nycklar börjar med "sk-ant-". Kontrollera nyckeln.'
    if provider == 'google' and len(api_key) < 20:
        return 'Google API-nyckeln ser för kort ut. Kontrollera nyckeln.'
    return None

# ============================================================
# APP CONFIG HELPERS
# ============================================================

ENV_FILE = BASE_DIR / '.env'

def read_env() -> dict:
    """Read all key=value pairs from .env"""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def write_env(updates: dict):
    """Write / update keys in .env without deleting existing ones"""
    env = read_env()
    env.update(updates)
    lines = []
    for k, v in env.items():
        lines.append(f'{k}={v}')
    ENV_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # Reload into os.environ immediately
    for k, v in updates.items():
        os.environ[k] = v

# ============================================================
# SCHEDULER HELPERS
# ============================================================

_SCHEDULER_DEFAULTS = {
    'enabled':        False,
    'time':           '08:00',
    'days':           ['mon', 'tue', 'wed', 'thu', 'fri'],
    'last_run_date':  None,
}

def load_scheduler_config() -> dict:
    try:
        if SCHEDULER_FILE().exists():
            data = json.loads(SCHEDULER_FILE().read_text(encoding='utf-8'))
            cfg = dict(_SCHEDULER_DEFAULTS)
            cfg.update(data)
            return cfg
    except Exception:
        pass
    return dict(_SCHEDULER_DEFAULTS)

def save_scheduler_config(updates: dict):
    cfg = load_scheduler_config()
    cfg.update(updates)
    SCHEDULER_FILE().write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')

def _next_run_label(cfg: dict) -> str:
    """Compute a human-readable 'nästa sökning' string from scheduler config."""
    if not cfg.get('enabled'):
        return None
    day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
    day_names_sv = ['måndag', 'tisdag', 'onsdag', 'torsdag', 'fredag', 'lördag', 'söndag']
    allowed_days = [day_map[d] for d in cfg.get('days', []) if d in day_map]
    if not allowed_days:
        return None
    sched_time = cfg.get('time', '08:00')
    try:
        h, m = map(int, sched_time.split(':'))
    except Exception:
        return None

    now = datetime.now()
    for offset in range(8):
        candidate = now + timedelta(days=offset)
        if candidate.weekday() not in allowed_days:
            continue
        candidate_dt = candidate.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate_dt <= now:
            continue
        if offset == 0:
            return f'idag {sched_time}'
        elif offset == 1:
            return f'imorgon {sched_time}'
        else:
            return f'{day_names_sv[candidate.weekday()]} {sched_time}'
    return sched_time

def _scheduler_loop():
    """Background thread: fires search at the scheduled time each day."""
    while True:
        try:
            time.sleep(60)
            cfg = load_scheduler_config()
            if not cfg.get('enabled'):
                continue

            day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
            allowed_days = [day_map[d] for d in cfg.get('days', []) if d in day_map]
            now = datetime.now()

            if now.weekday() not in allowed_days:
                continue

            sched_time = cfg.get('time', '08:00')
            try:
                h, m = map(int, sched_time.split(':'))
            except Exception:
                continue

            scheduled_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            today_str = now.strftime('%Y-%m-%d')

            if now >= scheduled_dt and cfg.get('last_run_date') != today_str:
                with _search_lock:
                    if search_state.get('running'):
                        continue

                save_scheduler_config({'last_run_date': today_str})

                # Hämta scheduler-ägaren (sparas av api_scheduler_save)
                uid = cfg.get('user_id')

                # Load saved preferences and fire search
                prefs = load_yaml(PREFS_YAML()) or {}
                platforms  = prefs.get('platforms', ['indeed', 'jobtech'])
                max_jobs   = prefs.get('max_jobs', 10)
                locations  = prefs.get('locations', ['Uppsala'])
                positions  = prefs.get('positions', [])

                # Reuse the same closure pattern as search_run
                with _search_lock:
                    search_state.update({
                        'running': True, 'output': [], 'error': None,
                        'progress': 0, 'started_at': now.isoformat(), 'finished_at': None,
                    })

                # Hämta scheduler-ägaren från config (user_id sparas när schema ställs in)
                sched_user_id = cfg.get('user_id')

                def _sched_search(plats=platforms, mj=max_jobs, locs=locations,
                                   pos=positions, uid=sched_user_id):
                    sq = _search_queue(uid)
                    st = _search_state(uid)
                    old_out = sys.stdout
                    class _SC:
                        encoding = 'utf-8'
                        def write(self, t):
                            if t and t.strip():
                                sq.put(('output', t))
                            old_out.write(t)
                        def flush(self): old_out.flush()
                        def reconfigure(self, **kw): pass
                    from job_master import JobMaster
                    try:
                        sys.stdout = _SC()
                        with app.app_context():
                            if uid:
                                _set_search_thread_llm_context(uid)
                            jm = JobMaster(
                                output_dir = _user_output_dir(uid),
                                data_dir   = _user_data_dir(uid),
                            )
                            jm.initialize()
                            jobs = jm.search_jobs(plats, mj, locations=locs, positions=pos)
                            for i, job in enumerate(jobs or [], 1):
                                jm.generate_documents_for_job(job, i)
                            jm.cleanup()
                    except Exception as e:
                        sq.put(('error', str(e)))
                    finally:
                        sys.stdout = old_out
                        with _search_lock:
                            st['running']     = False
                            st['progress']    = 100
                            st['finished_at'] = datetime.now().isoformat()
                        sq.put(('done', None))

                threading.Thread(target=_sched_search, daemon=True).start()
        except Exception:
            pass


def is_setup_complete() -> bool:
    """Returnerar True om inloggad användare har en API-nyckel,
    eller om global env har en nyckel (fallback för admin/server-nyckel)."""
    # 1. Kolla per-user nyckel i databasen
    try:
        from flask_login import current_user as _cu
        if _cu and _cu.is_authenticated:
            if _cu.llm_provider == 'ollama':
                return True
            if _cu.llm_api_key:
                decrypted = decrypt_secret(_cu.llm_api_key)
                if decrypted and len(decrypted) > 10:
                    return True
    except Exception:
        pass
    # 2. Fallback: global env (server-nyckel, bakåtkompatibilitet)
    env = read_env()
    providers = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY']
    for k in providers:
        if not env.get(k):
            env[k] = os.environ.get(k, '')
    llm_provider = env.get('LLM_PROVIDER') or os.environ.get('LLM_PROVIDER', 'openai')
    if llm_provider == 'ollama':
        return True
    return any(env.get(k, '').startswith('sk-') or
               (env.get(k, '') and len(env.get(k, '')) > 10)
               for k in providers)

def get_current_model_config() -> dict:
    env = read_env()
    return {
        'provider': env.get('LLM_PROVIDER', 'openai'),
        'model':    env.get('LLM_MODEL', 'gpt-4o-mini'),
    }

# ============================================================
# HELPERS
# ============================================================

def load_yaml(path):
    """Load YAML file safely"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def save_yaml(path, data):
    """Save YAML file with unicode support"""
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, indent=2)


def load_json(path):
    """Load JSON file safely"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def load_tracker() -> dict:
    """Load tracker status dict {folder: {status, notes, updated}}"""
    try:
        with open(TRACKER_FILE(), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_tracker(data: dict):
    """Save tracker status dict"""
    TRACKER_FILE().parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_FILE(), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_job_folders():
    """Get all job output folders with at least one PDF — per-user isolated.
    Folders without PDFs are failed/incomplete jobs and should not be shown."""
    d = _user_output_dir()
    if not d.exists():
        return []
    folders = []
    for f in d.iterdir():
        if f.is_dir() and any(f.glob('*.pdf')):
            folders.append(f)
    return sorted(folders, key=lambda x: x.name, reverse=True)


def parse_job_folder(folder: Path) -> dict:
    """Parse a job folder into a usable dict"""
    files = [f for f in folder.iterdir() if f.is_file()]
    cv_file = next((f for f in files if f.name.startswith('CV_') and f.suffix == '.pdf'), None)
    if cv_file is None:
        cv_file = next((f for f in files if f.name == 'CV.pdf'), None)

    letter_candidates = sorted(
        [f for f in files if f.name.startswith('Personligt_Brev') and f.suffix == '.pdf'],
        key=lambda f: f.stat().st_size, reverse=True
    )
    letter_file = letter_candidates[0] if letter_candidates else None

    info = {}
    info_file = folder / 'job_info.txt'
    if info_file.exists():
        for line in info_file.read_text(encoding='utf-8').split('\n'):
            if 'Titel:' in line:
                info['title'] = line.split('Titel:', 1)[1].strip()
            elif 'Företag:' in line:
                info['company'] = line.split('Företag:', 1)[1].strip()
            elif 'Plats:' in line:
                info['location'] = line.split('Plats:', 1)[1].strip()
            elif ' URL:' in line and not info.get('url'):
                # Matchar alla plattformar: Indeed URL:, LinkedIn URL:, Jobtech/AF URL: osv.
                candidate = line.split(' URL:', 1)[1].strip()
                if candidate.startswith('http'):
                    info['url'] = candidate
            elif 'Källa:' in line:
                info['source'] = line.split('Källa:', 1)[1].strip()
            elif 'Hittad:' in line:
                info['date'] = line.split('Hittad:', 1)[1].strip()
            elif 'Sista ansökningsdag:' in line:
                info['deadline'] = line.split('Sista ansökningsdag:', 1)[1].strip()

    if not info.get('title'):
        parts = folder.name.split('_', 3)
        info['company'] = parts[2] if len(parts) > 2 else ''
        info['title']   = parts[3] if len(parts) > 3 else folder.name

    def _pdf_urls(fname):
        if not fname:
            return None, None
        q = f'folder={_url_quote(folder.name)}&filename={_url_quote(fname)}'
        return f'/view-pdf?{q}', f'/download-pdf?{q}'

    cv_view_url,     cv_dl_url     = _pdf_urls(cv_file.name     if cv_file     else None)
    letter_view_url, letter_dl_url = _pdf_urls(letter_file.name if letter_file else None)

    return {
        'folder':          folder.name,
        'title':           info.get('title', folder.name),
        'company':         info.get('company', ''),
        'location':        info.get('location', ''),
        'source':          info.get('source', ''),
        'url':             info.get('url', ''),
        'date':            info.get('date', '')[:10] if info.get('date') else '',
        'deadline':        info.get('deadline', '')[:10] if info.get('deadline') else '',
        'cv_file':         cv_file.name     if cv_file     else None,
        'letter_file':     letter_file.name if letter_file else None,
        'has_letter':      letter_file is not None,
        'has_cv':          cv_file is not None,
        'cv_view_url':     cv_view_url,
        'cv_dl_url':       cv_dl_url,
        'letter_view_url': letter_view_url,
        'letter_dl_url':   letter_dl_url,
    }


def parse_openai_calls(path) -> tuple:
    """Parse open_ai_calls.json som innehåller flera JSON-objekt (ett per rad/anrop).
    Returnerar (total_calls, total_cost)."""
    total_calls = 0
    total_cost  = 0.0
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            return 0, 0.0
        # Filen innehåller flera JSON-objekt i rad — dela upp dem
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(content):
            content_slice = content[idx:].lstrip()
            if not content_slice:
                break
            offset = len(content[idx:]) - len(content_slice)
            try:
                obj, end = decoder.raw_decode(content_slice)
                total_calls += 1
                total_cost  += obj.get('total_cost', 0)
                idx += offset + end
            except json.JSONDecodeError:
                break
    except Exception:
        pass
    return total_calls, total_cost


def get_stats():
    """Get application statistics"""
    processed   = load_json(PROCESSED_JOBS())
    folders     = get_job_folders()

    jobs_with_letter = sum(
        1 for f in folders
        if any(p.name.startswith('Personligt_Brev') for p in f.iterdir() if p.is_file())
    )

    total_calls, total_cost = parse_openai_calls(OPENAI_CALLS()) if OPENAI_CALLS().exists() else (0, 0.0)

    return {
        'total_folders':     len(folders),
        'total_processed':   len(processed),
        'jobs_with_letter':  jobs_with_letter,
        'total_cost':        round(total_cost, 4),
        'total_calls':       total_calls,
    }


# ============================================================
# ROUTES — DASHBOARD
# ============================================================

# ============================================================
# AUTH CHECK — require login for all app routes
# ============================================================
_PUBLIC_ENDPOINTS = {'auth.login', 'auth.logout', 'landing', 'static'}
_PUBLIC_PREFIXES  = ['/auth/', '/static/']

@app.before_request
def require_login():
    """Redirect to login unless the route is public."""
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if any(request.path.startswith(p) for p in _PUBLIC_PREFIXES):
        return None
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.path))
    return None


# ============================================================
# SETUP CHECK — ny användare utan API-nyckel → setup, men kan skippa
# ============================================================
@app.before_request
def check_setup():
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    setup_done = is_setup_complete() or session.get('setup_skipped')
    g.setup_needed = not setup_done
    # CV- och brevsidor kräver ingen API-nyckel — alltid tillgängliga
    allowed = ['/setup', '/static', '/auth/', '/cv', '/cover-letter', '/admin']
    if not setup_done and not any(request.path.startswith(p) for p in allowed):
        return redirect(url_for('setup'))


@app.route('/setup/skip', methods=['POST'])
@login_required
def setup_skip():
    session['setup_skipped'] = True
    session.permanent = True
    return redirect(url_for('index'))
    return redirect(request.referrer or url_for('index'))


# ============================================================
# ROUTES — LANDING PAGE (public)
# ============================================================
@app.route('/landing')
def landing():
    """Public landing page. Authenticated users go straight to dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('landing.html')


# ============================================================
# ROUTES — DASHBOARD
# ============================================================
@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route('/login')
def login_redirect():
    from flask import redirect, url_for
    return redirect(url_for('auth.login'))


@app.route('/')
def index():
    stats         = get_stats()
    folders       = get_job_folders()
    recent_jobs   = [parse_job_folder(f) for f in folders[:8]]
    model_cfg     = get_current_model_config()
    scheduler_cfg = load_scheduler_config()
    scheduler_cfg['next_run_label'] = _next_run_label(scheduler_cfg)
    return render_template('index.html', stats=stats, recent_jobs=recent_jobs,
                           search_running=search_state['running'],
                           model_cfg=model_cfg,
                           scheduler_cfg=scheduler_cfg)


# ============================================================
# ROUTES — CV EDITOR
# ============================================================

ALLOWED_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png'}
MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB


@app.route('/cv')
@login_required
def cv_editor():
    resume = load_yaml(RESUME_YAML())
    has_photo = _u('profile.png').exists()
    return render_template('cv.html', resume=resume,
                           has_profile_photo=has_photo,
                           now=int(time.time()))


@app.route('/cv/photo')
@login_required
def cv_photo():
    """Serve the profile photo"""
    photo_path = _u('profile.png')
    if not photo_path.exists():
        return 'Ingen bild', 404
    return send_file(str(photo_path), mimetype='image/png')


@app.route('/cv/upload-photo', methods=['POST'])
@login_required
def cv_upload_photo():
    """Upload and save profile photo per user"""
    if 'photo' not in request.files:
        flash('Ingen fil vald.', 'danger')
        return redirect(url_for('cv_editor'))

    f = request.files['photo']
    if not f or not f.filename:
        flash('Ingen fil vald.', 'danger')
        return redirect(url_for('cv_editor'))

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        flash('Ogiltigt format. Använd JPG eller PNG.', 'danger')
        return redirect(url_for('cv_editor'))

    data = f.read()
    if len(data) > MAX_PHOTO_BYTES:
        flash('Bilden är för stor (max 5 MB).', 'danger')
        return redirect(url_for('cv_editor'))

    photo_path = _u('profile.png')
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data)).convert('RGB')
        img.save(str(photo_path), 'PNG', optimize=True)
    except ImportError:
        photo_path.write_bytes(data)
    except Exception as e:
        flash(f'Kunde inte spara bilden: {e}', 'danger')
        return redirect(url_for('cv_editor'))

    flash('Profilbild sparad!', 'success')
    return redirect(url_for('cv_editor'))


@app.route('/cv/delete-photo')
@login_required
def cv_delete_photo():
    """Delete profile photo"""
    photo_path = _u('profile.png')
    if photo_path.exists():
        photo_path.unlink()
        flash('Profilbild borttagen.', 'success')
    return redirect(url_for('cv_editor'))


@app.route('/cv/save', methods=['POST'])
@login_required
def cv_save():
    resume = load_yaml(RESUME_YAML())

    # Personal information
    resume['personal_information'] = {
        'name':         request.form.get('name', ''),
        'surname':      request.form.get('surname', ''),
        'email':        request.form.get('email', ''),
        'phone_prefix': request.form.get('phone_prefix', '+46'),
        'phone':        request.form.get('phone', ''),
        'city':         request.form.get('city', ''),
        'country':      request.form.get('country', 'Sverige'),
        'zip_code':     resume.get('personal_information', {}).get('zip_code', ''),
        'address':      request.form.get('address', ''),
        'date_of_birth':resume.get('personal_information', {}).get('date_of_birth', ''),
        'github':       request.form.get('github', ''),
        'linkedin':     request.form.get('linkedin', ''),
        'website':      request.form.get('website', ''),
    }

    resume['professional_summary']  = request.form.get('professional_summary', '')
    resume['cover_letter_profile']  = request.form.get('cover_letter_profile', '')

    # Experience
    positions      = request.form.getlist('exp_position[]')
    companies      = request.form.getlist('exp_company[]')
    periods        = request.form.getlist('exp_period[]')
    exp_locations  = request.form.getlist('exp_location[]')
    resp_blocks    = request.form.getlist('exp_responsibilities[]')
    skill_blocks   = request.form.getlist('exp_skills[]')

    experience = []
    for i, pos in enumerate(positions):
        if pos.strip():
            resp_list  = [{'responsibility': r.strip()} for r in resp_blocks[i].split('\n')  if r.strip()] if i < len(resp_blocks)  else []
            skill_list = [s.strip()                     for s in skill_blocks[i].split('\n') if s.strip()] if i < len(skill_blocks) else []
            experience.append({
                'position':          pos.strip(),
                'company':           companies[i].strip()    if i < len(companies)    else '',
                'employment_period': periods[i].strip()      if i < len(periods)      else '',
                'location':          exp_locations[i].strip() if i < len(exp_locations) else '',
                'industry':          '',
                'key_responsibilities': resp_list,
                'skills_acquired':     skill_list,
            })
    if experience:
        resume['experience_details'] = experience

    # Education
    edu_levels    = request.form.getlist('edu_level[]')
    edu_insts     = request.form.getlist('edu_institution[]')
    edu_fields    = request.form.getlist('edu_field[]')
    edu_years     = request.form.getlist('edu_year[]')

    education = []
    for i, level in enumerate(edu_levels):
        if level.strip():
            education.append({
                'education_level':      level.strip(),
                'institution':          edu_insts[i].strip()  if i < len(edu_insts)  else '',
                'field_of_study':       edu_fields[i].strip() if i < len(edu_fields) else '',
                'final_evaluation_grade': 'Godkänd',
                'year_of_completion':   edu_years[i].strip()  if i < len(edu_years)  else '',
                'start_date':           '',
                'additional_info':      {'focus': '', 'specialization': ''},
            })
    if education:
        resume['education_details'] = education

    # Technical skills
    os_raw       = request.form.get('os_skills', '')
    soft_raw     = request.form.get('software_skills', '')
    add_raw      = request.form.get('additional_skills', '')
    resume['technical_skills'] = {
        'operating_systems': [s.strip() for s in os_raw.split('\n')   if s.strip()],
        'hardware':          resume.get('technical_skills', {}).get('hardware', []),
        'software':          [s.strip() for s in soft_raw.split('\n') if s.strip()],
        'additional':        [s.strip() for s in add_raw.split('\n')  if s.strip()],
    }

    # Languages
    lang_names  = request.form.getlist('lang_name[]')
    lang_levels = request.form.getlist('lang_level[]')
    languages = []
    for i, lang in enumerate(lang_names):
        if lang.strip():
            languages.append({
                'language':    lang.strip(),
                'proficiency': lang_levels[i].strip() if i < len(lang_levels) else '',
            })
    if languages:
        resume['languages'] = languages

    try:
        save_yaml(RESUME_YAML(), resume)
        flash('CV sparat!', 'success')
    except Exception as e:
        flash(f'Kunde inte spara CV: {e}', 'danger')
    return redirect(url_for('cv_editor'))


# ============================================================
# ROUTES — COVER LETTER
# ============================================================

@app.route('/cover-letter')
@login_required
def cover_letter():
    content = COVER_LETTER().read_text(encoding='utf-8') if COVER_LETTER().exists() else ''
    resume  = load_yaml(RESUME_YAML())
    profile = resume.get('cover_letter_profile', '')
    return render_template('cover_letter.html', content=content, profile=profile)


@app.route('/cover-letter/templates')
def letter_templates():
    # Brev-design integrerat på /search under CV-design.
    # Behåller routen för bakåtkompat men redirectar.
    return redirect(url_for('search') + '#letter-picker')

@app.route('/cover-letter/template/preview/<template_key>')
@login_required
def letter_template_preview(template_key):
    """Renderar brev-mallen med användarens RIKTIGA data från plain_text_resume.yaml.

    Förut: serverade en statisk dummy-HTML från static/letter_templates/ med
    "Anna Karlsson"-data, helt orelaterad till hur det faktiska brevet ser ut.

    Nu: laddar samma mall som cover_letter_generator använder vid riktig
    generering, substituerar med Victor's data, returnerar färdig HTML.
    """
    LETTER_TEMPLATE_FILES = {
        'nordic_minimal':   'cover_letter_template_clean.html',
        'problem_solution': 'cover_letter_template_problem_solution.html',
        'modern_tech':      'cover_letter_template_modern_tech.html',
        'executive':        'cover_letter_template_executive.html',
        'elegant':          'cover_letter_template_elegant.html',
    }
    template_file = LETTER_TEMPLATE_FILES.get(template_key)
    if not template_file:
        return "Mall hittades inte", 404

    template_path = BASE_DIR / 'src' / 'libs' / 'resume_and_cover_builder' / 'moderndesign1' / template_file
    if not template_path.exists():
        return "Mall-fil saknas", 404

    template_text = template_path.read_text(encoding='utf-8')
    content = _build_letter_preview_content()
    from string import Template
    return Template(template_text).safe_substitute(content)


def _build_letter_preview_content() -> dict:
    """Bygger dict med alla brev-placeholders ifyllda med inloggad användares data."""
    from datetime import datetime
    resume = load_yaml(RESUME_YAML()) or {}
    pi = resume.get('personal_information', {}) or {}

    full_name = f"{pi.get('name', '')} {pi.get('surname', '')}".strip() or 'Namn Saknas'

    # Härled job_title från senaste erfarenhet
    exp = (resume.get('experience_details') or [])
    job_title = exp[0].get('position', '') if exp else ''

    email = pi.get('email', '')
    phone = pi.get('phone', '')
    address = pi.get('address', '')
    zip_code = pi.get('zip_code', '')
    city = pi.get('city', '')
    website = pi.get('website', '')

    contact_parts = []
    if email:   contact_parts.append(f'<div>{email}</div>')
    if phone:   contact_parts.append(f'<div>{phone}</div>')
    if address or city: contact_parts.append(f'<div>{", ".join(p for p in [address, f"{zip_code} {city}".strip()] if p)}</div>')
    if website: contact_parts.append(f'<div>{website}</div>')
    contact_info = '\n'.join(contact_parts)

    months_sv = ['januari', 'februari', 'mars', 'april', 'maj', 'juni',
                 'juli', 'augusti', 'september', 'oktober', 'november', 'december']
    now = datetime.now()
    date_str = f"{now.day} {months_sv[now.month-1]} {now.year}"

    body_text = resume.get('cover_letter_profile', '') or ''
    paragraphs = [p.strip() for p in body_text.split('\n\n') if p.strip()]
    section1 = '\n'.join(f'<p>{p}</p>' for p in paragraphs) or '<p>Fyll i ditt personliga brev under Mitt CV → Personligt brev.</p>'

    return {
        'full_name': full_name,
        'job_title': job_title,
        'contact_info': contact_info,
        'date': date_str,
        'salutation': 'Bästa rekryteringsteam,',
        'section1_content': section1,
        'closing_text': 'Med vänlig hälsning,',
        'attachment_text': 'Bilaga: Curriculum Vitae',
    }

@app.route('/cover-letter/save', methods=['POST'])
@login_required
def cover_letter_save():
    try:
        content = request.form.get('content', '')
        COVER_LETTER().write_text(content, encoding='utf-8')
        profile = request.form.get('profile', '')
        if profile:
            resume = load_yaml(RESUME_YAML())
            resume['cover_letter_profile'] = profile
            save_yaml(RESUME_YAML(), resume)
        flash('Personligt brev sparat!', 'success')
    except Exception as e:
        flash(f'Kunde inte spara brevet: {e}', 'danger')
    return redirect(url_for('cover_letter'))


# ============================================================
# ROUTES — JOB SEARCH
# ============================================================

@app.route('/search')
@login_required
def search():
    prefs = load_yaml(PREFS_YAML())
    env = read_env()
    current_cv_design = env.get('CV_DESIGN', 'design_02_classic')
    current_letter_template = env.get('LETTER_TEMPLATE', 'nordic_minimal')
    return render_template(
        'search.html',
        prefs=prefs,
        search_state=search_state,
        current_cv_design=current_cv_design,
        current_letter_template=current_letter_template,
    )


# Whitelist av designer som faktiskt har en motsvarande Jinja2/string.Template-fil.
# Synka med CV_TEMPLATE_MAP i improved_generator.py och LETTER_TEMPLATE_MAP i
# moderndesign1/cover_letter_generator.py.
ACTIVE_CV_DESIGNS     = {'design_01_minimal', 'design_02_classic', 'design_03_modern_green',
                         'design_05_nordic_blue', 'design_07_tech_modern'}
ACTIVE_LETTER_DESIGNS = {'nordic_minimal', 'problem_solution', 'modern_tech',
                         'executive', 'elegant'}


@app.route('/api/design/save', methods=['POST'])
@login_required
def api_design_save():
    """AJAX-spar för CV-/brev-design-val på sökrutan."""
    kind = request.form.get('kind', '')
    value = request.form.get('value', '')
    if kind == 'cv' and value in ACTIVE_CV_DESIGNS:
        write_env({'CV_DESIGN': value})
        return jsonify({'ok': True, 'kind': kind, 'value': value})
    if kind == 'letter' and value in ACTIVE_LETTER_DESIGNS:
        write_env({'LETTER_TEMPLATE': value})
        return jsonify({'ok': True, 'kind': kind, 'value': value})
    return jsonify({'ok': False, 'error': 'invalid kind or value'}), 400


@app.route('/search/run', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def search_run():
    uid = _get_uid()
    _st = _search_state(uid)
    _q  = _search_queue(uid)

    with _search_lock:
        if _st['running']:
            return jsonify({'error': 'En sökning pågår redan. Vänta tills den är klar.'}), 400

        # Parse form
        locations_raw = request.form.get('locations', 'Uppsala')
        locations     = [l.strip() for l in locations_raw.replace('\n', ',').split(',') if l.strip()]
        if not locations:
            locations = ['Uppsala']

        positions_raw = request.form.get('positions', '')
        positions     = [p.strip() for p in positions_raw.split('\n') if p.strip()]

        platforms_raw = request.form.getlist('platforms')
        platform_map  = {'linkedin': 'linkedin', 'indeed': 'indeed', 'af': 'arbetsformedlingen', 'jobtech': 'jobtech'}
        platforms     = [platform_map[p] for p in platforms_raw if p in platform_map]
        if not platforms:
            platforms = ['indeed']

        max_jobs = int(request.form.get('max_jobs', 10))
        remote   = 'remote' in request.form
        hybrid   = 'hybrid' in request.form
        onsite   = 'onsite' in request.form

        # ATS-filter alternativ
        ats_filter_enabled = 'ats_filter' in request.form
        ats_threshold      = max(0, min(100, int(request.form.get('ats_threshold', 65))))

        # Auto-apply alternativ
        auto_apply_enabled = 'auto_apply' in request.form

        # Save selected CV design + letter template to .env
        cv_design = request.form.get('cv_design', 'design_02_classic')
        if cv_design in ACTIVE_CV_DESIGNS:
            write_env({'CV_DESIGN': cv_design})
        letter_template = request.form.get('letter_template', 'nordic_minimal')
        if letter_template in ACTIVE_LETTER_DESIGNS:
            write_env({'LETTER_TEMPLATE': letter_template})

        # Update preferences YAML
        prefs = load_yaml(PREFS_YAML())
        prefs['remote']    = remote
        prefs['hybrid']    = hybrid
        prefs['onsite']    = onsite
        prefs['locations'] = locations
        if positions:
            prefs['positions'] = positions
        save_yaml(PREFS_YAML(), prefs)

        # Reset per-user state
        _st.update({
            'running':     True,
            'output':      [],
            'error':       None,
            'progress':    0,
            'started_at':  datetime.now().isoformat(),
            'finished_at': None,
        })

    # Drain this user's queue
    while not _q.empty():
        try:
            _q.get_nowait()
        except queue.Empty:
            break

    # uid already captured above; current_user unavailable inside thread
    _search_user_id = uid

    def run_search():
        # Use per-user queue/state captured from outer scope
        q  = _search_queue(_search_user_id)
        st = _search_state(_search_user_id)

        if _search_user_id:
            _set_search_thread_llm_context(_search_user_id)
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        class OutputCapture:
            """Capture stdout/stderr and push to user's SSE queue"""
            encoding = 'utf-8'

            def write(self, text):
                if text and text.strip():
                    q.put(('output', text))
                if old_stdout is not None:
                    try:
                        old_stdout.write(text)
                    except (UnicodeEncodeError, TypeError):
                        pass

            def flush(self):
                if old_stdout is not None:
                    old_stdout.flush()

            def reconfigure(self, **kwargs):
                pass

        try:
            from job_master import JobMaster

            sys.stdout = OutputCapture()
            sys.stderr = OutputCapture()

            _set_stop_flag(_search_user_id, False)
            jm = JobMaster(output_dir=_user_output_dir(_search_user_id), data_dir=_user_data_dir(_search_user_id))
            jm.stop_requested = False
            jm.initialize(platforms=platforms)

            q.put(('output', f'\n🔍 Plattformar: {", ".join(platforms)}\n'))
            q.put(('output', f'📍 Platser: {", ".join(locations)}\n'))
            q.put(('output', f'🎯 Max jobb: {max_jobs}\n\n'))

            def _sync_stop_flag():
                import time as _time
                while st.get('running') and not _is_stop_requested(_search_user_id):
                    _time.sleep(0.3)
                jm.stop_requested = True

            threading.Thread(target=_sync_stop_flag, daemon=True).start()

            jobs = jm.search_jobs(platforms, max_jobs, locations=locations, positions=positions)

            if _is_stop_requested(_search_user_id):
                q.put(('output', '\n⛔ Sökning avbruten av användaren.\n'))
            elif jobs:
                q.put(('output', f'\n✅ Hittade {len(jobs)} jobb!\n'))
                q.put(('output', '\n📝 Genererar CV och personliga brev...\n'))
                successful = 0
                for i, job in enumerate(jobs, 1):
                    if _is_stop_requested(_search_user_id):
                        q.put(('output', '\n⛔ Dokumentgenerering avbruten.\n'))
                        break
                    q.put(('progress', f'{i}/{len(jobs)}'))
                    q.put(('output', f'\n[{i}/{len(jobs)}] 📄 {job["title"]} @ {job["company"]}\n'))
                    _enforce_job_quota()
                    ok = jm.generate_documents_for_job(
                        job, i,
                        ats_filter=ats_filter_enabled,
                        ats_threshold=ats_threshold,
                        auto_apply=auto_apply_enabled,
                    )
                    if ok:
                        successful += 1
                        q.put(('output', '   ✅ Klar!\n'))
                    else:
                        q.put(('output', '   ⏭️  Hoppades över\n'))

                try:
                    pj_path  = _user_output_dir(_search_user_id) / 'processed_jobs.json'
                    existing = json.loads(pj_path.read_text(encoding='utf-8')) if pj_path.exists() else []
                    known    = {j.get('url') for j in existing if j.get('url')}
                    added    = 0
                    for _job in jobs:
                        _url = (_job.get('url') or '').strip()
                        if _url and _url not in known:
                            existing.append({
                                'url':            _url,
                                'title':          _job.get('title', ''),
                                'company':        _job.get('company', ''),
                                'source':         _job.get('source', ''),
                                'status':         'processed',
                                'processed_date': datetime.now().isoformat(),
                            })
                            known.add(_url)
                            added += 1
                    pj_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
                    if added:
                        q.put(('output', f'🔒 {added} jobb registrerade i historiken (hittas ej igen).\n'))
                except Exception as _e:
                    q.put(('output', f'⚠️  Kunde inte uppdatera dubblett-historiken: {_e}\n'))

                q.put(('output', f'\n✅ KLART! {successful}/{len(jobs)} jobb processade.\n'))
                q.put(('output', f'📂 Filer sparade i: {jm.base_output_dir}\n'))
            else:
                q.put(('output', '\n❌ Inga nya jobb hittades. Prova att ändra sökkriterierna.\n'))

            jm.cleanup()

        except Exception as e:
            import traceback
            err_msg = f'\n❌ Fel: {str(e)}\n{traceback.format_exc()}\n'
            q.put(('error', err_msg))
            with _search_lock:
                st['error'] = str(e)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            with _search_lock:
                st['running']     = False
                st['progress']    = 100
                st['finished_at'] = datetime.now().isoformat()
            q.put(('done', None))

    threading.Thread(target=run_search, daemon=True).start()
    return jsonify({'status': 'started'})


@app.route('/search/stream')
@login_required
def search_stream():
    """Server-Sent Events stream for live search output — per user"""
    uid = _get_uid()
    st  = _search_state(uid)
    q   = _search_queue(uid)

    def generate():
        yield 'data: {"type":"connected"}\n\n'
        if not st.get('running'):
            yield 'data: {"type":"done"}\n\n'
            return
        while True:
            try:
                msg_type, msg = q.get(timeout=20)
                if msg_type == 'output':
                    data = json.dumps({'type': 'output', 'text': msg})
                    yield f'data: {data}\n\n'
                elif msg_type == 'progress':
                    _prog_data = json.dumps({'type': 'progress', 'value': msg})
                    yield f'data: {_prog_data}\n\n'
                elif msg_type == 'error':
                    data = json.dumps({'type': 'error', 'text': msg})
                    yield f'data: {data}\n\n'
                    yield 'data: {"type":"done"}\n\n'
                    break
                elif msg_type == 'done':
                    yield 'data: {"type":"done"}\n\n'
                    break
            except queue.Empty:
                if not st.get('running'):
                    yield 'data: {"type":"done"}\n\n'
                    break
                yield 'data: {"type":"ping"}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':     'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/search/stop', methods=['POST'])
@login_required
def search_stop():
    """Stop an ongoing search gracefully"""
    uid = _get_uid()
    st  = _search_state(uid)
    q   = _search_queue(uid)
    if not st.get('running'):
        return jsonify({'status': 'not_running'})
    _set_stop_flag(uid, True)
    q.put(('output', '\n⛔ Stoppsignal mottagen — avslutar pågående plattform...\n'))
    return jsonify({'status': 'stopping'})


@app.route('/search/status')
@login_required
def search_status():
    return jsonify(_search_state(_get_uid()))


@app.route('/search/force-reset', methods=['POST'])
@login_required
def search_force_reset():
    """Force-reset search state if a previous search got stuck."""
    uid = _get_uid()
    st  = _search_state(uid)
    q   = _search_queue(uid)
    with _search_lock:
        _set_stop_flag(uid, True)
        st.update({
            'running':     False,
            'output':      [],
            'error':       None,
            'progress':    0,
            'finished_at': datetime.now().isoformat(),
        })
    while not q.empty():
        try:
            q.get_nowait()
        except queue.Empty:
            break
    return jsonify({'status': 'reset'})


@app.route('/search/clear-history', methods=['POST'])
@login_required
def search_clear_history():
    """Rensa processed_jobs.json så att redan sedda jobb kan hittas igen."""
    p = PROCESSED_JOBS()
    if p.exists():
        p.write_text('[]', encoding='utf-8')
    return jsonify({'status': 'cleared'})


# ============================================================
# ROUTES — BATCH RE-EVALUATE
# ============================================================

@app.route('/generate/batch-evaluate', methods=['POST'])
@limiter.limit("30 per hour")
def batch_evaluate():
    """Utvärdera ALLA jobbmappar med EXAKT samma detaljerade ATS-pipeline som
    /jobs-sidans badge (_evaluate_job_ats) och radera mappar under tröskeln.
    Tröskel + force styrs från UI (samma standard som söksidan: 65)."""
    uid = _get_uid()
    _st = _search_state(uid)
    _q  = _search_queue(uid)

    _body = request.get_json(silent=True) or {}
    try:
        _eval_threshold = max(0, min(100, int(_body.get('threshold', 65))))
    except (TypeError, ValueError):
        _eval_threshold = 65
    _eval_force = bool(_body.get('force', True))

    with _search_lock:
        if _st.get('running'):
            return jsonify({'status': 'already_running'})
        _set_stop_flag(uid, False)
        _st.update({
            'running':      True,
            'output':       [],
            'error':        None,
            'progress':     0,
            'started_at':   datetime.now().isoformat(),
            'finished_at':  None,
        })

    _eval_user_id = uid

    while not _q.empty():
        try:
            _q.get_nowait()
        except queue.Empty:
            break

    def run_evaluation():
        q  = _search_queue(_eval_user_id)
        st = _search_state(_eval_user_id)
        if _eval_user_id:
            _set_search_thread_llm_context(_eval_user_id)
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        class OutputCapture:
            def write(self, text):
                if text and text.strip():
                    q.put(('output', text))
                try:
                    old_stdout.write(text)
                except Exception:
                    pass
            def flush(self):
                try:
                    old_stdout.flush()
                except Exception:
                    pass
            def reconfigure(self, **kwargs):
                pass

        sys.stdout = OutputCapture()
        sys.stderr = OutputCapture()

        try:
            _out_dir = _user_output_dir(_eval_user_id)
            _found_jobs_path = _out_dir / 'found_jobs.json'

            # Scan actual job folders on disk — not found_jobs.json (which may be out of sync)
            job_folders = sorted(
                [f for f in _out_dir.iterdir() if f.is_dir() and f.name.startswith('Job_')],
                key=lambda x: x.name,
            )

            if not job_folders:
                q.put(('output', '❌ Inga jobbmappar hittades. Gör en sökning först.\n'))
                q.put(('done', None))
                return

            sep = '=' * 60
            q.put(('output',
                f'\n🔍 Utvärderar {len(job_folders)} jobbmappar med detaljerad ATS '
                f'(tröskel: {_eval_threshold}%)...\n'
                f'{sep}\n'
            ))

            passed = 0
            failed = 0
            skipped = 0

            for i, folder in enumerate(job_folders, 1):
                if _is_stop_requested(_eval_user_id):
                    q.put(('output', '\n⛔ Avbruten av användaren.\n'))
                    break

                q.put(('progress', f'{i}/{len(job_folders)}'))

                display_name = folder.name
                info_file = folder / 'job_info.txt'
                if info_file.exists():
                    for line in info_file.read_text(encoding='utf-8').split('\n'):
                        if 'Titel:' in line:
                            display_name = line.split('Titel:', 1)[1].strip()
                            break

                q.put(('output', f'\n[{i}/{len(job_folders)}] {display_name}\n'))

                if not any(folder.glob('*.pdf')):
                    q.put(('output', '   ⚠️  Inga dokument — hoppar över\n'))
                    skipped += 1
                    continue

                res = _evaluate_job_ats(folder, force=_eval_force)
                if not res.get('ok'):
                    err = (res.get('error') or 'okänt fel')[:60]
                    q.put(('output', f'   ⚠️  Kunde inte utvärdera — behålls ({err})\n'))
                    skipped += 1
                    continue

                score = res.get('score', 0)
                q.put(('output', f'   🎯 ATS-poäng: {score}/100\n'))

                if score >= _eval_threshold:
                    passed += 1
                    q.put(('output', f'   ✅ Godkänd (≥ {_eval_threshold}%) — behålls\n'))
                else:
                    failed += 1
                    summary = (res.get('summary') or '')[:80]
                    q.put(('output', f'   ❌ Under tröskeln — {summary}\n'))
                    _meta = parse_job_folder(folder)
                    _block_job_url(_meta.get('url', ''), _meta)
                    shutil.rmtree(folder, ignore_errors=True)
                    search_queue.put(('output', f'   🗑️  Mapp borttagen: {folder.name}\n'))

            # Update found_jobs.json: remove entries whose folder no longer exists
            if _found_jobs_path.exists():
                try:
                    found_jobs = json.loads(_found_jobs_path.read_text(encoding='utf-8'))
                    remaining = {f.name.lower() for f in _out_dir.iterdir() if f.is_dir()}

                    def _folder_still_exists(job):
                        safe_c = ''.join(
                            c for c in job.get('company', '') if c.isalnum() or c in (' ', '-', '_')
                        ).strip()
                        safe_t = ''.join(
                            c for c in job.get('title', '')[:30] if c.isalnum() or c in (' ', '-', '_')
                        ).strip()
                        sig = f'{safe_c}_{safe_t[:15]}'.lower()
                        return any(sig in fname for fname in remaining)

                    kept = [j for j in found_jobs if _folder_still_exists(j)]
                    _found_jobs_path.write_text(
                        json.dumps(kept, ensure_ascii=False, indent=2), encoding='utf-8'
                    )
                except Exception:
                    pass  # Non-critical

            q.put(('output',
                f'\n{sep}\n'
                f'📊 RESULTAT: {passed} behållna (≥{_eval_threshold}%), {failed} borttagna'
                + (f', {skipped} ej utvärderade' if skipped else '')
                + f' av {len(job_folders)} mappar\n'
            ))

        except Exception as e:
            import traceback
            err = f'\n❌ Fel: {str(e)}\n{traceback.format_exc()}\n'
            q.put(('error', err))
            with _search_lock:
                st['error'] = str(e)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            with _search_lock:
                st['running']     = False
                st['progress']    = 100
                st['finished_at'] = datetime.now().isoformat()
            q.put(('done', None))

    threading.Thread(target=run_evaluation, daemon=True).start()
    return jsonify({'status': 'started'})


# ============================================================
# ROUTES — JOBS LIST
# ============================================================

@app.route('/jobs')
@login_required
def jobs():
    from datetime import timedelta
    folders       = get_job_folders()
    job_list      = [parse_job_folder(f) for f in folders]
    today         = datetime.now().strftime('%Y-%m-%d')
    warning_date  = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
    expired_count = sum(1 for j in job_list if j.get('deadline') and j['deadline'] < today)
    return render_template('jobs.html', jobs=job_list, today=today,
                           warning_date=warning_date, expired_count=expired_count)


@app.route('/download-pdf')
@login_required
def download_file():
    """Download a PDF document (query-param based to handle Swedish chars)"""
    folder   = request.args.get('folder',   '').strip()
    filename = request.args.get('filename', '').strip()
    if not folder or not filename:
        return 'Parametrar saknas', 400
    if '..' in folder or '..' in filename or '/' in filename or '\\' in filename:
        return 'Ogiltig förfrågan', 400
    file_path = _user_output_dir() / folder / filename
    if file_path.exists() and file_path.suffix.lower() == '.pdf':
        return send_file(str(file_path.resolve()), as_attachment=True,
                         download_name=filename)
    return 'Filen hittades inte', 404


@app.route('/view-pdf')
@login_required
def view_pdf():
    """View a PDF in browser (query-param based to handle Swedish chars)"""
    folder   = request.args.get('folder',   '').strip()
    filename = request.args.get('filename', '').strip()
    if not folder or not filename:
        return 'Parametrar saknas', 400
    if '..' in folder or '..' in filename or '/' in filename or '\\' in filename:
        return 'Ogiltig förfrågan', 400
    file_path = _user_output_dir() / folder / filename
    if file_path.exists() and file_path.suffix.lower() == '.pdf':
        return send_file(str(file_path.resolve()), mimetype='application/pdf')
    return 'Filen hittades inte', 404


# Legacy path-based routes (redirect to query-param versions)
@app.route('/download/<path:subpath>')
@login_required
def download_file_legacy(subpath):
    parts = subpath.split('/', 1)
    if len(parts) == 2:
        return redirect(f'/download-pdf?folder={parts[0]}&filename={parts[1]}')
    return 'Ogiltig URL', 400


@app.route('/view/<path:subpath>')
@login_required
def view_pdf_legacy(subpath):
    parts = subpath.split('/', 1)
    if len(parts) == 2:
        return redirect(f'/view-pdf?folder={parts[0]}&filename={parts[1]}')
    return 'Ogiltig URL', 400


# ── Jobbkvot ────────────────────────────────────────────────────────────────
JOB_QUOTA = 50  # Max antal jobbmappar per användare

def _enforce_job_quota():
    """Ta bort de äldsta jobbmapparna om kvoten (50) överskrids.
    Kallas innan varje nytt jobb sparas."""
    out_dir = _user_output_dir()
    if not out_dir.exists():
        return
    folders = sorted(
        [f for f in out_dir.iterdir() if f.is_dir()],
        key=lambda f: f.name   # Job_001_ prefix → äldst har lägst nummer
    )
    while len(folders) >= JOB_QUOTA:
        oldest = folders.pop(0)
        shutil.rmtree(oldest, ignore_errors=True)


def _job_quota_status() -> dict:
    """Returnerar {'count': int, 'quota': int, 'pct': int}."""
    out_dir = _user_output_dir()
    count = sum(1 for f in out_dir.iterdir() if f.is_dir()) if out_dir.exists() else 0
    return {'count': count, 'quota': JOB_QUOTA, 'pct': round(count / JOB_QUOTA * 100)}


def _build_zip(folders_and_files: list, single_folder: bool = False) -> 'io.BytesIO':
    """Bygg ZIP i minne från lista av (folder_path, arcname_prefix)."""
    import zipfile, io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for folder_path, prefix in folders_and_files:
            for f in folder_path.iterdir():
                if f.is_file() and f.suffix.lower() in ('.pdf', '.txt', '.json'):
                    arcname = f.name if single_folder else f'{prefix}/{f.name}'
                    zf.write(f, arcname)
    buf.seek(0)
    return buf


@app.route('/api/jobs/download-zip')
@login_required
def download_job_zip():
    """Ladda ner ett jobb som ZIP. ?delete=1 raderar mappen efter nedladdning."""
    folder = request.args.get('folder', '').strip()
    delete = request.args.get('delete', '0') == '1'
    if not folder or '..' in folder or '/' in folder or '\\' in folder:
        return 'Ogiltig mapp', 400
    job_folder = _user_output_dir() / folder
    if not job_folder.exists():
        return 'Mappen finns inte', 404

    buf = _build_zip([(job_folder, folder)], single_folder=True)
    safe_name = "".join(c for c in folder if c.isalnum() or c in (' ', '-', '_')).strip()

    if delete:
        shutil.rmtree(job_folder, ignore_errors=True)

    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'{safe_name}.zip')


@app.route('/api/jobs/download-all-zip')
@login_required
def download_all_jobs_zip():
    """Ladda ner alla jobb som ZIP. ?delete=1 raderar alla mappar efter nedladdning."""
    delete = request.args.get('delete', '0') == '1'
    out_dir = _user_output_dir()
    if not out_dir.exists():
        return 'Inga jobb att ladda ner', 404

    job_folders = [(f, f.name) for f in sorted(out_dir.iterdir()) if f.is_dir()]
    if not job_folders:
        return 'Inga jobb att ladda ner', 404

    buf = _build_zip(job_folders)

    if delete:
        for folder_path, _ in job_folders:
            shutil.rmtree(folder_path, ignore_errors=True)

    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name='applymind-alla-jobb.zip')


@app.route('/api/jobs/quota')
@login_required
def api_job_quota():
    """Returnerar kvot-status för inloggad användare."""
    return jsonify(_job_quota_status())


@app.route('/api/jobs')
@login_required
def api_jobs():
    """JSON API for jobs list"""
    folders  = get_job_folders()
    job_list = [parse_job_folder(f) for f in folders]
    return jsonify(job_list)


def _block_job_url(job_url: str, job_meta: dict, status: str = 'rejected') -> None:
    """Lägg/markera en jobb-URL i processed_jobs.json så den inte hittas igen.
    Delad av per-jobb-radering, batch-utvärdering och radering av utgångna jobb."""
    job_url = (job_url or '').strip()
    if not job_url:
        return
    try:
        existing = json.loads(PROCESSED_JOBS().read_text(encoding='utf-8')) if PROCESSED_JOBS().exists() else []
    except Exception:
        existing = []

    known_urls = {j.get('url') for j in existing}
    if job_url not in known_urls:
        existing.append({
            'url':            job_url,
            'title':          (job_meta or {}).get('title', ''),
            'company':        (job_meta or {}).get('company', ''),
            'source':         (job_meta or {}).get('source', ''),
            'status':         status,
            'processed_date': datetime.now().isoformat(),
        })
        PROCESSED_JOBS().write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    else:
        changed = False
        for j in existing:
            if j.get('url') == job_url and j.get('status') != status:
                j['status'] = status
                changed = True
        if changed:
            PROCESSED_JOBS().write_text(
                json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8'
            )


@app.route('/api/jobs/delete', methods=['POST'])
@login_required
def api_delete_job():
    """Radera ett jobb: ta bort mappen och blockera URL:en från framtida sökningar."""
    data   = request.get_json(silent=True) or {}
    folder = data.get('folder', '').strip()

    if not folder or '..' in folder or '/' in folder or '\\' in folder:
        return jsonify({'ok': False, 'error': 'Ogiltig mapp'}), 400

    job_folder = _user_output_dir() / folder
    if not job_folder.exists():
        return jsonify({'ok': False, 'error': 'Mappen finns inte'}), 404

    # Blockera URL:en innan vi raderar mappen
    job = parse_job_folder(job_folder)
    _block_job_url(job.get('url', ''), job)

    # Radera mappen med alla filer
    shutil.rmtree(str(job_folder), ignore_errors=True)

    return jsonify({'ok': True})


@app.route('/api/jobs/delete-expired', methods=['POST'])
@login_required
def api_delete_expired():
    """Radera alla jobb vars sista ansökningsdag har passerat (deadline < idag).
    Blockerar deras URL:er. Jobb utan sparad deadline (t.ex. Indeed/LinkedIn)
    rörs inte — de saknar datum att jämföra mot."""
    today    = datetime.now().strftime('%Y-%m-%d')
    deleted  = []
    for folder in get_job_folders():
        job      = parse_job_folder(folder)
        deadline = (job.get('deadline') or '').strip()
        if deadline and deadline < today:
            _block_job_url(job.get('url', ''), job)
            shutil.rmtree(str(folder), ignore_errors=True)
            deleted.append({
                'folder':   folder.name,
                'title':    job.get('title', ''),
                'company':  job.get('company', ''),
                'deadline': deadline,
            })
    return jsonify({'ok': True, 'deleted': len(deleted), 'jobs': deleted})


@app.route('/api/jobs/import-history', methods=['POST'])
@login_required
def api_import_history():
    """Importera redan-sökta jobb till dedup-historiken (processed_jobs.json).
    Tar emot en uppladdad JSON-fil — en lista av jobb med minst 'url'. Slår ihop
    med befintliga poster (dedup på url) så att framtida sökningar hoppar över dem.
    Per användare. Rörer aldrig några dokumentmappar."""
    f = request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'error': 'Ingen fil bifogad'}), 400
    try:
        data = json.loads(f.read().decode('utf-8'))
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Ogiltig JSON: {e}'}), 400
    if not isinstance(data, list):
        return jsonify({'ok': False, 'error': 'Filen måste vara en JSON-lista av jobb'}), 400

    pj = PROCESSED_JOBS()
    try:
        existing = json.loads(pj.read_text(encoding='utf-8')) if pj.exists() else []
    except Exception:
        existing = []

    known = {(j.get('url') or '').strip() for j in existing if j.get('url')}
    added = 0
    for j in data:
        if not isinstance(j, dict):
            continue
        url = (j.get('url') or '').strip()
        if not url or url in known:
            continue
        existing.append({
            'url':            url,
            'title':          j.get('title', ''),
            'company':        j.get('company', ''),
            'source':         j.get('source', ''),
            'status':         j.get('status', 'processed'),
            'processed_date': j.get('processed_date') or datetime.now().isoformat(),
        })
        known.add(url)
        added += 1

    pj.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
    return jsonify({'ok': True, 'added': added, 'skipped': len(data) - added, 'total': len(existing)})


@app.route('/api/jobs/regenerate-docs', methods=['POST'])
@login_required
def api_regenerate_docs():
    """Bygg om CV och personligt brev för ett jobb med den aktuella grundfilen."""
    data   = request.get_json(silent=True) or {}
    folder = data.get('folder', '').strip()

    if not folder or '..' in folder or '/' in folder or '\\' in folder:
        return jsonify({'ok': False, 'error': 'Ogiltig mapp'}), 400

    job_folder = _user_output_dir() / folder
    if not job_folder.exists():
        return jsonify({'ok': False, 'error': 'Mappen finns inte'}), 404

    desc_file = job_folder / 'job_description.txt'
    if not desc_file.exists():
        return jsonify({'ok': False, 'error': 'Ingen jobbeskrivning sparad för detta jobb'}), 400

    job_description = desc_file.read_text(encoding='utf-8')

    job_info = parse_job_folder(job_folder)
    safe_company = ''.join(c for c in job_info.get('company', 'Foretag') if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_title   = ''.join(c for c in job_info.get('title', 'Jobb')[:30] if c.isalnum() or c in (' ', '-', '_')).strip()

    try:
        from job_master import JobMaster
        jm = JobMaster(output_dir=_user_output_dir(), data_dir=_user_data_dir())
        jm.initialize(platforms=[])

        # Bygg ett jobb-objekt med sparad data — facaden kräver company, role och location
        _jc = job_info.get('company', 'Företag') or 'Företag'
        _jt = job_info.get('title', 'Tjänst') or 'Tjänst'
        _jl = job_info.get('location', 'Sverige') or 'Sverige'

        class _FakeJob:
            description = job_description
            link        = folder
            company     = _jc
            role        = _jt
            location    = _jl

        jm.modern_facade.job = _FakeJob()

        # Generera CV
        _design = os.getenv('CV_DESIGN', 'design_01_minimal')
        cv_base64, _ = jm.modern_facade.create_resume_pdf_job_tailored()

        # Ta bort gamla CV-filer och spara ny
        for old in job_folder.glob('CV_*.pdf'):
            old.unlink()

        cv_path = job_folder / f'CV_{safe_company}_{safe_title}_{_design}.pdf'
        cv_path.write_bytes(base64.b64decode(cv_base64))

        # Generera personligt brev
        cover_base64, _ = jm.modern_facade.create_cover_letter()

        for old in job_folder.glob('Personligt_Brev_*.pdf'):
            old.unlink()

        cover_path = job_folder / f'Personligt_Brev_{safe_company}_{safe_title}_{_design}.pdf'
        cover_path.write_bytes(base64.b64decode(cover_base64))

        return jsonify({'ok': True})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/stats')
@login_required
def api_stats():
    return jsonify(get_stats())


@app.route('/api/stats/detailed')
@login_required
def api_stats_detailed():
    """Aggregated stats for dashboard charts."""
    try:
        processed = load_json(PROCESSED_JOBS())
        folders   = get_job_folders()
        tracker   = load_tracker()
        now       = datetime.now()

        # ── Chart 1: Applications per week (last 4 weeks) ──
        weeks = {}
        for i in range(3, -1, -1):
            ws = now - timedelta(days=now.weekday() + 7 * i)
            weeks[f"v.{ws.isocalendar()[1]}"] = 0

        for f in folders:
            job = parse_job_folder(f)
            d = job.get('date', '')
            if not d:
                continue
            try:
                jd = datetime.strptime(d[:10], '%Y-%m-%d')
                for i in range(3, -1, -1):
                    ws = (now - timedelta(days=now.weekday() + 7 * i)).replace(
                        hour=0, minute=0, second=0, microsecond=0)
                    if ws <= jd < ws + timedelta(days=7):
                        weeks[f"v.{ws.isocalendar()[1]}"] = weeks.get(
                            f"v.{ws.isocalendar()[1]}", 0) + 1
            except ValueError:
                pass

        # ── Chart 2: Platform breakdown (from processed_jobs.json) ──
        platforms = {}
        for job in processed:
            src = (job.get('source') or 'Okänd').strip()
            platforms[src] = platforms.get(src, 0) + 1

        # ── Chart 3: ATS score distribution ──
        buckets = {'0–20': 0, '20–40': 0, '40–60': 0, '60–80': 0, '80–100': 0}
        for f in folders:
            sf = f / 'ats_score.json'
            if not sf.exists():
                # Check inside the job subfolder pattern
                sf = _user_output_dir() / f.name / 'ats_score.json'
            if sf.exists():
                try:
                    sc = json.loads(sf.read_text(encoding='utf-8')).get('score', 0)
                    if   sc < 20: buckets['0–20']   += 1
                    elif sc < 40: buckets['20–40']  += 1
                    elif sc < 60: buckets['40–60']  += 1
                    elif sc < 80: buckets['60–80']  += 1
                    else:         buckets['80–100'] += 1
                except Exception:
                    pass

        # ── Chart 4: Tracker status ──
        status_counts = {'ready': 0, 'applied': 0, 'interview': 0, 'offer': 0, 'rejected': 0, 'archived': 0}
        tracked = set()
        for fname, data in tracker.items():
            s = data.get('status', 'ready')
            if s in status_counts:
                status_counts[s] += 1
            tracked.add(fname)
        # Folders not in tracker → default "ready"
        for f in folders:
            if f.name not in tracked:
                status_counts['ready'] += 1

        return jsonify({
            'ok': True,
            'weekly': {
                'labels': list(weeks.keys()),
                'values': list(weeks.values()),
            },
            'platforms': {
                'labels': list(platforms.keys()) or ['Ingen data'],
                'values': list(platforms.values()) or [0],
            },
            'ats_distribution': {
                'labels': list(buckets.keys()),
                'values': list(buckets.values()),
            },
            'tracker_status': {
                'labels': ['Redo att söka', 'Sökt', 'Intervju', 'Erbjudande', 'Avslag', 'Arkiverad'],
                'values': [
                    status_counts['ready'],
                    status_counts['applied'],
                    status_counts['interview'],
                    status_counts['offer'],
                    status_counts['rejected'],
                    status_counts['archived'],
                ],
            },
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/scheduler')
def api_scheduler():
    cfg = load_scheduler_config()
    cfg['next_run_label'] = _next_run_label(cfg)
    return jsonify(cfg)


@app.route('/api/scheduler/save', methods=['POST'])
def api_scheduler_save():
    data = request.get_json(force=True) or {}
    enabled = bool(data.get('enabled', False))
    t       = data.get('time', '08:00')
    days    = [d for d in data.get('days', []) if d in
               ('mon','tue','wed','thu','fri','sat','sun')]
    # Validate time format
    import re as _re
    if not _re.match(r'^\d{2}:\d{2}$', t):
        t = '08:00'
    # Spara user_id så schedulern vet vilken användares prefs/nyckel att använda
    uid = current_user.id if current_user.is_authenticated else None
    save_scheduler_config({'enabled': enabled, 'time': t, 'days': days, 'user_id': uid})
    cfg = load_scheduler_config()
    cfg['next_run_label'] = _next_run_label(cfg)
    return jsonify({'ok': True, 'next_run_label': cfg['next_run_label']})


@app.route('/api/found-jobs')
@login_required
def api_found_jobs():
    """Return found_jobs.json + which have been processed"""
    found     = load_json(FOUND_JOBS())
    processed = load_json(PROCESSED_JOBS())
    proc_urls = {j.get('url', '') for j in processed}
    folders   = get_job_folders()
    # Build a set of processed titles+companies
    proc_keys = {(j.get('title','').lower(), j.get('company','').lower()) for j in processed}

    for job in found:
        key = (job.get('title','').lower(), job.get('company','').lower())
        job['processed'] = key in proc_keys or job.get('url','') in proc_urls
    return jsonify(found)


# ============================================================
# ROUTES — LANGUAGE
# ============================================================

@app.route('/set-lang/<lang>')
def set_lang(lang):
    if lang in ('sv', 'en', 'es'):
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))


# ============================================================
# ROUTES — DESIGN / LAYOUT
# ============================================================

# Endast designer med riktiga genererings-mallar i moderndesign1/ listas här.
# Synka med ACTIVE_CV_DESIGNS + CV_TEMPLATE_MAP i improved_generator.py.
DESIGNS = {
    'design_01_minimal': {
        'key':         'design_01_minimal',
        'name_sv':     'Minimal',
        'name_en':     'Minimal',
        'name_es':     'Minimalista',
        'desc_sv':     'Ren vit layout med tydlig typografi. Perfekt för ATS-system.',
        'desc_en':     'Clean white layout with clear typography. Perfect for ATS systems.',
        'desc_es':     'Diseño blanco limpio con tipografía clara. Perfecto para ATS.',
        'tags':        [('ATS-vänlig', 'green'), ('Enkel', 'green')],
    },
    'design_02_classic': {
        'key':         'design_02_classic',
        'name_sv':     'Klassisk',
        'name_en':     'Classic',
        'name_es':     'Clásico',
        'desc_sv':     'Tvåkolumnslayout med mörkt sidhuvud. Tidlös professionell stil.',
        'desc_en':     'Two-column layout with dark header. Timeless professional style.',
        'desc_es':     'Diseño de dos columnas con cabecera oscura. Estilo profesional atemporal.',
        'tags':        [('Professionell', 'blue'), ('Tidlös', 'blue')],
    },
    'design_03_modern_green': {
        'key':         'design_03_modern_green',
        'name_sv':     'Modern Grön',
        'name_en':     'Modern Green',
        'name_es':     'Verde Moderno',
        'desc_sv':     'Mörk sidopanel med gröna accenter. Tech- och IT-vänlig.',
        'desc_en':     'Dark sidebar with green accents. Tech and IT-friendly.',
        'desc_es':     'Barra lateral oscura con acentos verdes. Ideal para tech e IT.',
        'tags':        [('Tech', 'green'), ('Sidopanel', 'green')],
    },
    'design_05_nordic_blue': {
        'key':         'design_05_nordic_blue',
        'name_sv':     'Nordic Blue',
        'name_en':     'Nordic Blue',
        'name_es':     'Azul Nórdico',
        'desc_sv':     'Skandinavisk design med blått sidhuvud och ren layout.',
        'desc_en':     'Scandinavian design with blue header and clean layout.',
        'desc_es':     'Diseño escandinavo con cabecera azul y diseño limpio.',
        'tags':        [('Skandinavisk', 'blue'), ('Ren', 'blue')],
    },
    'design_07_tech_modern': {
        'key':         'design_07_tech_modern',
        'name_sv':     'Tech Modern',
        'name_en':     'Tech Modern',
        'name_es':     'Tech Moderno',
        'desc_sv':     'Mörkt tema med grön monospace-text. För developers och ingenjörer.',
        'desc_en':     'Dark theme with green monospace text. For developers and engineers.',
        'desc_es':     'Tema oscuro con texto monospace verde. Para desarrolladores e ingenieros.',
        'tags':        [('Developer', 'green'), ('Dark Mode', 'green')],
    },
}


def generate_pdf_preview(pdf_path: Path, out_path: Path, width: int = 400):
    """Render first page of PDF to PNG using PyMuPDF"""
    try:
        import fitz
        doc  = fitz.open(str(pdf_path))
        page = doc[0]
        mat  = fitz.Matrix(width / page.rect.width, width / page.rect.width)
        pix  = page.get_pixmap(matrix=mat, alpha=False)
        pix.save(str(out_path))
        doc.close()
        return True
    except Exception:
        return False


@app.route('/design')
def design_page():
    current = read_env().get('CV_DESIGN', 'design_01_minimal')
    previews = {}

    preview_dir = BASE_DIR / 'static' / 'previews'
    preview_dir.mkdir(parents=True, exist_ok=True)

    for key in DESIGNS:
        img_path = preview_dir / f'{key}.png'
        previews[key] = f'/static/previews/{key}.png' if img_path.exists() else None

    return render_template('design.html',
                           designs=DESIGNS,
                           current=current,
                           previews=previews)


@app.route('/design/save', methods=['POST'])
def design_save():
    design = request.form.get('design', 'design_01_minimal')
    if design in ACTIVE_CV_DESIGNS:
        write_env({'CV_DESIGN': design})
        flash(g.t.get('design_saved', 'Design saved!'), 'success')
    return redirect(url_for('design_page'))


@app.route('/preview/pdf/<design_key>')
@login_required
def preview_design_pdf(design_key):
    """Renderar CV-mallen med inloggad användares riktiga data från plain_text_resume.yaml.
    Laddar samma mall som improved_generator använder vid riktig generering."""
    CV_TEMPLATE_FILES = {
        'design_01_minimal':      'template_minimal.html',
        'design_02_classic':      'improved_template.html',
        'design_03_modern_green': 'template_modern_green.html',
        'design_05_nordic_blue':  'template_nordic_blue.html',
        'design_07_tech_modern':  'template_tech_modern.html',
    }
    template_file = CV_TEMPLATE_FILES.get(design_key)
    if not template_file:
        return 'Ingen förhandsgranskning tillgänglig', 404

    template_path = BASE_DIR / 'src' / 'libs' / 'resume_and_cover_builder' / 'moderndesign1' / template_file
    if not template_path.exists():
        return 'Mall-fil saknas', 404

    template_text = template_path.read_text(encoding='utf-8')
    content = _build_cv_preview_content()
    from string import Template
    return Template(template_text).safe_substitute(content)


def _build_cv_preview_content() -> dict:
    """Bygger dict med alla CV-placeholders ifyllda med inloggad användares data."""
    resume = load_yaml(RESUME_YAML()) or {}
    pi = resume.get('personal_information', {}) or {}

    full_name = f"{pi.get('name', '')} {pi.get('surname', '')}".strip() or 'Namn Saknas'
    summary = resume.get('professional_summary', '') or ''

    # Härled job_title från senaste erfarenhet
    exp = (resume.get('experience_details') or [])
    job_title = exp[0].get('position', '') if exp else ''

    # Profilfoto — inkludera om det finns
    profile_image = '/cv/photo' if _u('profile.png').exists() else ''

    # Education
    edu_html = []
    for edu in (resume.get('education_details') or []):
        level = edu.get('education_level', 'Utbildning')
        inst = edu.get('institution', '')
        edu_html.append(
            f'<div class="education-item" style="margin-bottom:0.7rem">• {level}'
            f'<br><div class="institution" style="font-size:0.78rem;opacity:0.75">{inst}</div></div>'
        )
    education_content = '\n'.join(edu_html) or '<div class="education-item">• Utbildning saknas i YAML</div>'

    # Skills (certifications + interests-tags)
    skills_items = []
    for cert in (resume.get('certifications') or []):
        skills_items.append(f'<div style="margin-bottom:0.4rem">• {cert.get("name", "")}</div>')
    skills_content = '\n'.join(skills_items) or ''

    # Languages
    lang_html = []
    for lang in (resume.get('languages') or []):
        lang_html.append(f'<div style="margin-bottom:0.4rem">• {lang.get("language", "")} <em style="opacity:0.7">({lang.get("proficiency", "")})</em></div>')
    languages_content = '\n'.join(lang_html) or '<div>• Svenska (Modersmål)</div>'

    # Contact
    contact_lines = []
    if pi.get('email'):   contact_lines.append(f'<div style="margin-bottom:0.3rem">📧 {pi["email"]}</div>')
    if pi.get('phone'):   contact_lines.append(f'<div style="margin-bottom:0.3rem">📱 {pi["phone"]}</div>')
    if pi.get('address') or pi.get('city'):
        addr = ', '.join(p for p in [pi.get('address', ''), f"{pi.get('zip_code', '')} {pi.get('city', '')}".strip()] if p)
        contact_lines.append(f'<div style="margin-bottom:0.3rem">📍 {addr}</div>')
    if pi.get('website'): contact_lines.append(f'<div style="margin-bottom:0.3rem">🌐 {pi["website"]}</div>')
    contact_content = '\n'.join(contact_lines) or '<div>Kontakt saknas i YAML</div>'

    # Experience (komprimerad — ta upp till 3 senaste)
    exp_html = []
    for exp in (resume.get('experience_details') or [])[:4]:
        position = exp.get('position', '')
        company = exp.get('company', '')
        period = exp.get('employment_period', '')
        resp_items = []
        for r in (exp.get('key_responsibilities') or [])[:3]:
            text = r.get('responsibility', r) if isinstance(r, dict) else r
            resp_items.append(f'<li>{text}</li>')
        bullets = ''.join(resp_items)
        exp_html.append(
            f'<div class="experience-item">'
            f'<h4>{position}</h4>'
            f'<div class="company">{company} ({period})</div>'
            f'<ul style="padding-left:1.1rem;margin-top:0.3rem">{bullets}</ul>'
            f'</div>'
        )
    experience_content = '\n'.join(exp_html) or '<div>Erfarenheter saknas i YAML</div>'

    # Technical skills (programming languages + tools)
    tech_items = set()
    tech = resume.get('technical_skills', {}) or {}
    for category_key in ('software', 'operating_systems', 'additional'):
        for item in (tech.get(category_key) or []):
            # Splitta på komma så taggar blir individuella chips
            for part in str(item).split(','):
                p = part.strip()
                if p and len(p) < 35:
                    tech_items.add(p)
    tech_html = '<ul style="list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:0.4rem">'
    for t in sorted(tech_items)[:30]:
        tech_html += f'<li>{t}</li>'
    tech_html += '</ul>'

    return {
        'profile_image': profile_image,
        'full_name': full_name,
        'job_title': job_title,
        'summary': summary,
        'education_title': 'UTBILDNING',
        'education_content': education_content,
        'skills_title': 'ÖVRIGA KUNSKAPER',
        'skills_content': skills_content,
        'languages_title': 'SPRÅK',
        'languages_content': languages_content,
        'contact_title': 'KONTAKT',
        'contact_content': contact_content,
        'experience_title': 'YRKESERFARENHET',
        'experience_content': experience_content,
        'technical_skills_title': 'Tekniska Färdigheter',
        'technical_skills': tech_html,
        'download_text': 'Ladda ner som PDF',
    }


# ============================================================
# ROUTES — SETUP WIZARD
# ============================================================

@app.route('/setup')
def setup():
    from src.libs.resume_and_cover_builder.llm.llm_factory import AVAILABLE_MODELS, PROVIDER_INFO
    env = read_env()
    step = request.args.get('step', '1')
    return render_template('setup.html',
                           step=step,
                           env=env,
                           available_models=AVAILABLE_MODELS,
                           provider_info=PROVIDER_INFO,
                           setup_complete=is_setup_complete())


@app.route('/setup/save-model', methods=['POST'])
def setup_save_model():
    provider   = request.form.get('provider', 'openai')
    model      = request.form.get('model', 'gpt-4o-mini')
    api_key    = request.form.get('api_key', '').strip()

    updates = {
        'LLM_PROVIDER': provider,
        'LLM_MODEL':    model,
    }

    key_map = {
        'openai':    'OPENAI_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY',
        'google':    'GOOGLE_API_KEY',
    }
    if provider in key_map and api_key:
        updates[key_map[provider]] = api_key

    linkedin_email    = request.form.get('linkedin_email', '').strip()
    linkedin_password = request.form.get('linkedin_password', '').strip()
    if linkedin_email:
        updates['LINKEDIN_EMAIL'] = linkedin_email
    if linkedin_password:
        updates['LINKEDIN_PASSWORD'] = linkedin_password

    write_env(updates)
    flash('AI-modell och API-nyckel sparade!', 'success')
    return redirect(url_for('setup', step='2'))


@app.route('/setup/upload-cv', methods=['POST'])
def setup_upload_cv():
    """Accept PDF or text CV, optionally convert via AI to YAML"""
    mode = request.form.get('mode', 'text')

    if mode == 'pdf':
        f = request.files.get('cv_pdf')
        if not f or not f.filename.endswith('.pdf'):
            flash('Välj en PDF-fil.', 'danger')
            return redirect(url_for('setup', step='2'))

        # Save uploaded PDF temporarily
        tmp = BASE_DIR / 'data_folder' / '_upload_cv.pdf'
        f.save(str(tmp))

        # Extract text with pypdf
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(tmp))
            cv_text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        except ImportError:
            try:
                import pdfplumber
                with pdfplumber.open(str(tmp)) as pdf:
                    cv_text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
            except Exception as e:
                flash(f'Kunde inte läsa PDF: {e}', 'danger')
                return redirect(url_for('setup', step='2'))
        finally:
            tmp.unlink(missing_ok=True)

        # Use AI to convert text → YAML structure
        _cv_text_to_yaml(cv_text)
        flash('CV importerat från PDF!', 'success')

    elif mode == 'text':
        cv_text = request.form.get('cv_text', '').strip()
        if not cv_text:
            flash('Klistra in CV-text.', 'danger')
            return redirect(url_for('setup', step='2'))
        _cv_text_to_yaml(cv_text)
        flash('CV sparat!', 'success')

    return redirect(url_for('setup', step='3'))


def _cv_text_to_yaml(cv_text: str):
    """Use AI to parse free-text CV into our YAML structure, or store as summary"""
    resume = load_yaml(RESUME_YAML())
    env    = read_env()
    api_key = env.get('OPENAI_API_KEY') or env.get('ANTHROPIC_API_KEY') or env.get('GOOGLE_API_KEY', '')

    if not api_key and env.get('LLM_PROVIDER') != 'ollama':
        # No AI — just store as professional summary
        resume['professional_summary'] = cv_text[:2000]
        save_yaml(RESUME_YAML(), resume)
        return

    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm    = get_user_llm(temperature=0.2)
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a CV parser. Extract information from the CV text and return ONLY a YAML block "
             "with these fields: name, surname, email, phone, city, country, professional_summary, "
             "github (if found), linkedin (if found), website (if found). "
             "Return ONLY valid YAML, no markdown, no explanation."),
            ("human", "CV text:\n{cv_text}")
        ])
        chain  = prompt | llm | StrOutputParser()
        result = chain.invoke({'cv_text': cv_text[:3000]})

        # Parse result and merge into existing resume
        result = re.sub(r'^```(?:yaml)?', '', result.strip(), flags=re.MULTILINE)
        result = re.sub(r'```$', '', result.strip(), flags=re.MULTILINE)
        parsed = yaml.safe_load(result.strip()) or {}

        pi = resume.get('personal_information', {})
        for field in ['name','surname','email','phone','city','country','github','linkedin','website']:
            if parsed.get(field):
                pi[field] = parsed[field]
        resume['personal_information'] = pi
        if parsed.get('professional_summary'):
            resume['professional_summary'] = parsed['professional_summary']

    except Exception:
        resume['professional_summary'] = cv_text[:2000]

    save_yaml(RESUME_YAML(), resume)


@app.route('/setup/save-cover-letter', methods=['POST'])
def setup_save_cover_letter_route():
    content = request.form.get('content', '').strip()
    if content:
        COVER_LETTER().write_text(content, encoding='utf-8')
        resume = load_yaml(RESUME_YAML())
        resume['cover_letter_profile'] = request.form.get('profile', '')
        save_yaml(RESUME_YAML(), resume)
    flash('Personligt brev sparat! Setup klar.', 'success')
    return redirect(url_for('index'))


# ============================================================
# ROUTES — MODEL SETTINGS (standalone page)
# ============================================================

@app.route('/settings')
@login_required
def settings():
    from src.libs.resume_and_cover_builder.llm.llm_factory import AVAILABLE_MODELS, PROVIDER_INFO
    env           = read_env()
    scheduler_cfg = load_scheduler_config()
    scheduler_cfg['next_run_label'] = _next_run_label(scheduler_cfg)

    # Visa per-user konfiguration om den finns, annars global env
    if current_user.llm_provider:
        model_cfg = {
            'provider': current_user.llm_provider,
            'model':    current_user.llm_model or 'gpt-4o-mini',
            'has_key':  bool(current_user.llm_api_key),
        }
    else:
        model_cfg = get_current_model_config()
        model_cfg['has_key'] = bool(
            env.get('OPENAI_API_KEY') or env.get('ANTHROPIC_API_KEY') or
            env.get('GOOGLE_API_KEY') or os.environ.get('OPENAI_API_KEY')
        )

    return render_template('settings.html',
                           env=env,
                           model_cfg=model_cfg,
                           available_models=AVAILABLE_MODELS,
                           provider_info=PROVIDER_INFO,
                           scheduler_cfg=scheduler_cfg)


@app.route('/settings/save', methods=['POST'])
@login_required
def settings_save():
    provider = request.form.get('provider', 'openai')
    model    = request.form.get('model', 'gpt-4o-mini')
    api_key  = request.form.get('api_key', '').strip()

    # Validera API-nyckelformat innan vi sparar
    key_error = _validate_api_key(provider, api_key)
    if key_error:
        flash(key_error, 'danger')
        return redirect(url_for('settings'))

    # Spara provider/modell + krypterad nyckel per användare i databasen
    from models import db
    current_user.llm_provider = provider
    current_user.llm_model    = model
    if api_key:
        current_user.llm_api_key = encrypt_secret(api_key)
    elif provider == 'ollama':
        current_user.llm_api_key = None  # Ollama behöver ingen nyckel

    # LinkedIn (fortfarande global i .env — ingen annan användare har dessa)
    env_updates = {}
    linkedin_email    = request.form.get('linkedin_email', '').strip()
    linkedin_password = request.form.get('linkedin_password', '').strip()
    if linkedin_email:
        env_updates['LINKEDIN_EMAIL'] = linkedin_email
        current_user.linkedin_email = linkedin_email
    if linkedin_password:
        env_updates['LINKEDIN_PASSWORD'] = linkedin_password
        current_user.linkedin_password = encrypt_secret(linkedin_password)

    db.session.commit()
    if env_updates:
        write_env(env_updates)

    flash('Inställningar sparade!', 'success')
    return redirect(url_for('settings'))


# ============================================================
# ROUTES — ATS SCORE
# ============================================================
#
# Designprincip: härma riktiga ATS:er (Workday/Teamtailor/Greenhouse) som gör
# literal keyword-matching, men lägg ovanpå en kalibrerad rekryterar-bedömning
# för transferable skills och soft skills. Slutpoängen är deterministiskt
# viktad — LLM:en sätter inte ett "magiskt" 0-100-värde.

def _build_keyword_extraction_prompt(job_description: str, job_title: str, company: str) -> str:
    """Pass 1: extrahera nyckelord och hårda krav från annonsen (LLM, temp=0)."""
    return f"""Du analyserar en jobbannons för att extrahera nyckelorden som en ATS skulle söka efter.

JOBBTITEL: {job_title}
FÖRETAG: {company}

ANNONS:
{job_description[:8000]}

EXTRAHERA ENDAST KONKRETA, MATCHBARA TERMER. Det MÅSTE vara en av:
✓ Specifik teknologi/verktyg/ramverk: "Node.js", "React", "Kubernetes", "PostgreSQL", "Solvens II"
✓ Specifik metodik: "Scrum", "TDD", "Domain-Driven Design"
✓ Specifik domän: "försäkring", "industriell riskbedömning", "fintech"
✓ Specifik certifiering: "AWS Certified Solutions Architect", "B-körkort", "SC-säkerhetsklass"
✓ Specifikt språk: "svenska", "engelska", "tyska"
✓ Specifikt antal år: "5 års erfarenhet av Java", "minst 3 år backend"
✓ Specifik utbildningsnivå: "civilingenjörsexamen", "kandidatexamen i datavetenskap"

EXTRAHERA ALDRIG generiska/icke-matchbara fyllnadsord:
✗ "teknisk kompetens", "erfarenhet av utveckling", "webbutveckling" (för vagt — vilken sorts?)
✗ "engagerad", "motiverad", "ansvarstagande", "team", "samarbete" — dessa hör hemma i soft_skills
✗ "kommunikationsförmåga", "problemlösare", "drivkraft"
✗ Hela meningar eller långa fraser ("erfarenhet av att arbeta i agila team")

Om annonsen INTE innehåller några konkreta termer ovan → returnera tomma listor (`[]`).
Det är bättre att returnera färre konkreta termer än att hitta på fyllnadsord.

Klassificera varje konkret term:
- must_have: explicit krav ("krav:", "du har", "minst X år", "ska kunna"). Utan dessa filtreras kandidaten bort.
- should_have: starkt meriterande ("vi söker dig som", "vi vill att du har erfarenhet av").
- nice_to_have: bonus ("meriterande", "plus om", "gärna").

För varje term, lista SYNONYMER och vanliga skrivvarianter — var GENERÖS, inte snål.
Bättre att inkludera 6-10 varianter än att missa matchningar p.g.a. för smala synonymer.

OBLIGATORISKA REGLER:
- Om termen är ENGELSK → ge svenska översättningen som synonym
  (Fullstack Developer → MÅSTE inkludera "fullstackutvecklare", "fullstack-utvecklare";
   Backend Developer → "backendutvecklare"; Project Manager → "projektledare")
- Om termen är SVENSK → ge engelska översättningen
  (utvecklare → "developer"; ingenjör → "engineer")
- Inkludera skrivvarianter med/utan punkt/bindestreck (Node.js → ["nodejs", "node js", "node"];
  CI/CD → ["ci cd", "cicd"]; multi-tenant → ["multitenant", "multi tenant"])
- Förkortningar OCH fullformer i båda riktningar (PostgreSQL → ["postgres", "psql"];
  K8s → ["kubernetes"]; TS → ["typescript"]; JS → ["javascript"])
- Tidsuttryck i siffror och bokstäver (5 års → ["5 år", "fem år", "5+ år", "minst 5 år"])
- KATEGORI-SYNONYMER för breda termer:
  * "AI-verktyg" → ["openai", "claude", "anthropic", "llm", "gpt", "chatgpt", "copilot", "ai"]
  * "cloud" → ["aws", "azure", "gcp", "google cloud", "moln"]
  * "agila utvecklingsmetoder" → ["agile", "agila", "scrum", "kanban", "sprint", "iteration"]
  * "frontend" → ["react", "vue", "angular", "svelte", "ui", "användargränssnitt"]
  * "backend" → ["api", "rest", "server", "node", "python", "java", "c#", ".net"]
  * "DevOps" → ["docker", "kubernetes", "ci/cd", "github actions", "gitlab ci", "jenkins"]
  Lista de KONKRETA tekniker som tillhör kategorin — så CV som har "Docker" matchar "DevOps".
- "Minst X år" → ALDRIG hård-blockera på exakt formulering. Inkludera "X år", "X+ år",
  "flera år", "flerårig erfarenhet", "X år av", och utan siffra om CV listar år-spann
  (2020-2024 = 4 års erfarenhet).

HÅRDA BLOCKERARE: krav som diskvalificerar (svenskt medborgarskap, körkort, säkerhetsklass,
specifik certifiering, minimiantal år av en specifik teknologi).

SOFT SKILLS samlas separat (samarbete, kommunikation, ledarskap, problemlösning).

Svara ENDAST med JSON (ingen markdown, inga kommentarer):
{{
  "must_have":   [{{"term": "...", "synonyms": ["...", "..."]}}],
  "should_have": [{{"term": "...", "synonyms": ["..."]}}],
  "nice_to_have":[{{"term": "...", "synonyms": ["..."]}}],
  "hard_requirements": [{{"requirement": "...", "match_terms": ["...", "..."]}}],
  "soft_skills": ["samarbete", "kommunikation"]
}}"""


def _build_recruiter_assessment_prompt(
    cv_text: str, job_description: str, job_title: str, company: str,
    keyword_summary: str
) -> str:
    """Pass 3: kalibrerad rekryterar-bedömning av transferable + soft skills (LLM, temp=0.1)."""
    return f"""Du är en senior rekryterare. Det deterministiska keyword-matchning är redan gjort
(se sammanfattning nedan). Din uppgift är att bedöma TVÅ saker som inte syns i keyword-matchningen:

1. TRANSFERABLE SKILLS (0-100): Kandidatens indirekta matchningar. T.ex. "multi-tenant SaaS-arkitektur"
   är direkt överförbart till "industriella risksystem" eftersom båda kräver distribuerad systemdesign,
   skalbarhet och hög tillförlitlighet. Premiera djupa konceptuella matchningar, inte ytliga.

2. SOFT SKILLS (0-100): Hur väl CV:t signalerar samarbete, kommunikation, problemlösning,
   ledarskap utifrån vad jobbet faktiskt kräver.

Du ska OCKSÅ ge 2-4 KONKRETA REKOMMENDATIONER. Varje rekommendation MÅSTE:
- Peka på en specifik del av CV:t att redigera (t.ex. "experience_details[0].key_responsibilities")
- Ge ett föreslaget exakt formuleringstext-snippet på svenska
- Vara handlingsbar inom 5 minuter (inte "skaffa certifiering")

KALIBRERINGSEXEMPEL (transferable):
- 90+: Tidigare arbete löste konceptuellt samma problem som jobbet beskriver
- 75-89: Solida överförbara mönster men inom annan domän
- 50-74: Vissa relevanta paralleller men kräver konceptuellt språng
- <50: Få överförbara element

JOBBTITEL: {job_title}
FÖRETAG: {company}

ANNONS (full text):
{job_description[:8000]}

KEYWORD-MATCHNING (redan beräknad):
{keyword_summary}

CV (full text):
{cv_text[:10000]}

Svara ENDAST med JSON (ingen markdown):
{{
  "transferable_score": <0-100>,
  "transferable_reasoning": "<en mening på svenska>",
  "soft_skills_score": <0-100>,
  "soft_skills_reasoning": "<en mening på svenska>",
  "recommendations": [
    {{
      "action": "<vad göra på svenska>",
      "where":  "<sektion i CV att redigera, t.ex. 'experience_details[0]'>",
      "suggested_text": "<exakt text att lägga till/byta ut på svenska>"
    }}
  ],
  "summary": "<1-2 meningars helhetsbedömning på svenska>"
}}"""


def _normalize_for_match(text: str) -> str:
    """Lowercase utan att rasera svenska tecken — ATS:er är case-insensitive men ÅÄÖ-känsliga."""
    return text.lower()


def _find_keyword(term: str, synonyms: list, cv_lower: str) -> tuple:
    """Sök efter term + synonymer i CV-text. Returnerar (found: bool, found_as: str|None).

    Smart boundary för korta termer: använder en boundary som funkar med
    specialtecken (#, +, .). Standard \\b räknar # som non-word så regex
    \\bC#\\b matchar aldrig 'C#,' eller 'C# ' — eftersom \\b kräver ord-tecken
    på fel sida. Vi använder istället lookaround: termen omges av antingen
    sträng-början/-slut, whitespace, eller specifik punktuation (komma,
    semikolon, parentes osv).
    """
    # Boundary-set: vi vill INTE matcha mitten av andra ord (t.ex. "go" i "good"),
    # men ACCEPTERA att termen omges av punktuation/whitespace eller är vid
    # textens kant.
    boundary_left  = r'(?:^|[\s,;:()/\[\]{}"\'\-])'
    boundary_right = r'(?=$|[\s,;:.()/\[\]{}"\'\-+#])'

    candidates = [term] + (synonyms or [])
    for c in candidates:
        if not c:
            continue
        c_norm = _normalize_for_match(c.strip())
        if not c_norm:
            continue
        if len(c_norm) <= 4:
            pattern = boundary_left + re.escape(c_norm) + boundary_right
            if re.search(pattern, cv_lower):
                return (True, c)
        else:
            if c_norm in cv_lower:
                return (True, c)
    return (False, None)


def _match_keyword_list(keyword_specs: list, cv_lower: str) -> list:
    """Returnera lista av {term, synonyms, found, found_as} för varje keyword-spec."""
    results = []
    for spec in (keyword_specs or []):
        if not isinstance(spec, dict):
            continue
        term = (spec.get('term') or '').strip()
        if not term:
            continue
        synonyms = spec.get('synonyms') or []
        found, found_as = _find_keyword(term, synonyms, cv_lower)
        results.append({
            'term': term,
            'synonyms': synonyms,
            'found': found,
            'found_as': found_as,
        })
    return results


def _match_hard_requirements(hard_reqs: list, cv_lower: str) -> list:
    """Hårda krav matchas via 'match_terms' — minst ett måste hittas för att räknas som uppfyllt."""
    results = []
    for req in (hard_reqs or []):
        if not isinstance(req, dict):
            continue
        requirement = (req.get('requirement') or '').strip()
        if not requirement:
            continue
        terms = req.get('match_terms') or []
        found, found_as = _find_keyword(requirement, terms, cv_lower)
        results.append({
            'requirement': requirement,
            'match_terms': terms,
            'satisfied': found,
            'found_as': found_as,
        })
    return results


def _pct(matched: int, total: int) -> int:
    """Procent matchade, eller 100 om kategorin är tom (saknar negativ påverkan)."""
    if total <= 0:
        return 100
    return round(matched / total * 100)


def _soften_pct(pct: int, matched: int) -> int:
    """Mjuk poängkurva för keyword-matchning.

    Rak procent är för brant: 2/6 = 33% straffar hårt även om kandidaten
    har de viktigaste 2. Vi använder sqrt-kurvan så delvis matchning får
    skäligt erkännande:
        0/N   →   0%
        1/N   →  ~floor 20% (om något matchades så får man en bas)
        N/2   →  ~71%
        N/N   → 100%
    Detta lättar på strikheten — användarens explicita feedback efter att
    44/100 ansågs för lågt för en kandidat med starka transferable skills.
    """
    if matched <= 0:
        return 0
    # sqrt-kurva
    ratio = pct / 100.0
    softened = round((ratio ** 0.5) * 100)
    # Bas-floor: minst 20 om något matchades alls (signalvärde att kandidaten
    # inte är helt off-topic)
    return max(20, softened)


def _compute_composite_score(must_pct: int, should_pct: int,
                             transferable: int, soft_skills: int,
                             must_total: int, hard_blockers_unsatisfied: int,
                             must_matched: int = 0, should_matched: int = 0) -> int:
    """Viktad slutpoäng — uppdaterad för MJUKARE strikhet (v2.5):

    - Must-have-vikt sänkt 50% → 40% (mindre brant straff för specifika tech-keywords)
    - Should-have oförändrat (25%)
    - Transferable upp 15% → 20% (verklig passform belönas)
    - Soft skills upp 10% → 15%
    - sqrt-kurva via _soften_pct: 2/6 = 33%→57% istället för rakt 33%
    - Bas-floor på 20% om minst 1 matchning (ingen "0" från kraschpoäng)
    - Hard-blocker-straff sänkt 15 → 10 per blockerare
    - Om inga must-have keywords finns flyttas vikten över till should_have
    """
    if must_total == 0:
        weights = {'must': 0.0, 'should': 0.55, 'transferable': 0.28, 'soft': 0.17}
    else:
        weights = {'must': 0.40, 'should': 0.25, 'transferable': 0.20, 'soft': 0.15}

    soft_must_pct   = _soften_pct(must_pct,   must_matched)
    soft_should_pct = _soften_pct(should_pct, should_matched)

    raw = (
        soft_must_pct  * weights['must']        +
        soft_should_pct* weights['should']      +
        transferable   * weights['transferable']+
        soft_skills    * weights['soft']
    )
    penalty = hard_blockers_unsatisfied * 10
    return max(0, min(100, round(raw - penalty)))


def _build_keyword_summary_for_llm(must_matches: list, should_matches: list,
                                   nice_matches: list, hard_matches: list,
                                   must_pct: int, should_pct: int) -> str:
    """Kompakt textsammanfattning av keyword-matchning att skicka till rekryterar-LLM:en."""
    def _fmt(items, label):
        if not items:
            return f"{label}: (inga)"
        found = [i['term'] for i in items if i['found']]
        missing = [i['term'] for i in items if not i['found']]
        return (f"{label} ({len(found)}/{len(items)} matchade):\n"
                f"  ✓ {', '.join(found) if found else '—'}\n"
                f"  ✗ {', '.join(missing) if missing else '—'}")

    blockers_unsat = [h['requirement'] for h in hard_matches if not h['satisfied']]
    blocker_line = (f"\nHÅRDA BLOCKERARE EJ UPPFYLLDA: {', '.join(blockers_unsat)}"
                    if blockers_unsat else "\nHÅRDA BLOCKERARE: alla uppfyllda")
    return (
        f"{_fmt(must_matches, 'MUST-HAVE')} ({must_pct}%)\n\n"
        f"{_fmt(should_matches, 'SHOULD-HAVE')} ({should_pct}%)\n\n"
        f"{_fmt(nice_matches, 'NICE-TO-HAVE')}"
        f"{blocker_line}"
    )


def _get_cv_text() -> str:
    """Extract plain text summary from resume YAML for ATS analysis (legacy fallback)."""
    resume = load_yaml(RESUME_YAML())
    parts = []
    pi = resume.get('personal_information', {})
    if pi.get('name'):
        parts.append(f"Namn: {pi.get('name','')} {pi.get('surname','')}")
    if resume.get('professional_summary'):
        parts.append(f"Sammanfattning: {resume['professional_summary']}")

    tech = resume.get('technical_skills', {})
    all_skills = []
    if isinstance(tech, dict):
        for v in tech.values():
            if isinstance(v, list):
                all_skills.extend(v)
    if all_skills:
        parts.append(f"Tekniska kompetenser: {', '.join(str(s) for s in all_skills)}")

    for exp in resume.get('experience_details', [])[:5]:
        if isinstance(exp, dict):
            pos = exp.get('position', '')
            comp = exp.get('company', '')
            period = exp.get('employment_period', '')
            parts.append(f"Erfarenhet: {pos} på {comp} ({period})")
            for resp in exp.get('key_responsibilities', [])[:3]:
                if isinstance(resp, dict):
                    parts.append(f"  - {resp.get('responsibility', '')}")
                elif isinstance(resp, str):
                    parts.append(f"  - {resp}")
            skills_acq = exp.get('skills_acquired', [])
            if skills_acq:
                parts.append(f"  Tekniker: {', '.join(str(s) for s in skills_acq[:8])}")

    for edu in resume.get('education_details', [])[:3]:
        if isinstance(edu, dict):
            level = edu.get('education_level', '')
            inst = edu.get('institution', '')
            field = edu.get('field_of_study', '')
            spec = (edu.get('additional_info') or {}).get('specialization', '')
            parts.append(f"Utbildning: {level} i {field} vid {inst}")
            if spec:
                parts.append(f"  Kurser/specialisering: {spec}")

    return '\n'.join(parts)


def _get_cv_full_text(job_folder: Path) -> str:
    """Hämta så fullständig CV-text som möjligt för keyword-matchning.

    Prio 1: Den genererade jobb-skräddarsydda CV-PDF:n i job_folder (det är den
            text en riktig ATS skulle skanna). Matchar både CV.pdf och CV_*.pdf.
    Prio 2: Utökad YAML-dump utan trunkering (alla erfarenheter, alla ansvar,
            kurser från utbildning, cover_letter_profile).
    """
    cv_pdfs = sorted(
        [f for f in job_folder.glob('CV*.pdf') if f.is_file()],
        key=lambda f: f.stat().st_mtime, reverse=True
    )
    if cv_pdfs:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(cv_pdfs[0]))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages).strip()
            if text:
                return text
        except Exception:
            pass

    # Fallback: full YAML-dump (utan att kapa till 3-5 entries som _get_cv_text).
    # Inkluderar professional_summary, cover_letter_profile, alla erfarenheter,
    # alla kurser/spec från utbildning, projekt — för att maximera literal-träffar.
    resume = load_yaml(RESUME_YAML())
    parts = []
    pi = resume.get('personal_information', {})
    if pi.get('name'):
        parts.append(f"{pi.get('name','')} {pi.get('surname','')}")
    # Vissa CV-mallar visar en titel/rubrik som "FULLSTACKUTVECKLARE" — försök
    # läsa både vanliga nyckelnamn och fall tillbaka på senaste rolltiteln.
    for key in ('headline', 'subtitle', 'title', 'role_title', 'profession'):
        v = pi.get(key) if isinstance(pi, dict) else None
        if v:
            parts.append(str(v))
    exp_list = resume.get('experience_details', []) or []
    if exp_list and isinstance(exp_list[0], dict):
        first_pos = exp_list[0].get('position', '')
        if first_pos:
            parts.append(first_pos)

    if resume.get('professional_summary'):
        parts.append(resume['professional_summary'])
    if resume.get('cover_letter_profile'):
        parts.append(str(resume['cover_letter_profile']))

    tech = resume.get('technical_skills', {})
    if isinstance(tech, dict):
        for cat, vals in tech.items():
            if isinstance(vals, list) and vals:
                parts.append(f"{cat}: {', '.join(str(s) for s in vals)}")

    for exp in exp_list:
        if not isinstance(exp, dict):
            continue
        parts.append(
            f"\n{exp.get('position', '')} — {exp.get('company', '')} "
            f"({exp.get('employment_period', '')})"
        )
        for resp in exp.get('key_responsibilities', []) or []:
            if isinstance(resp, dict):
                parts.append(f"- {resp.get('responsibility', '')}")
            elif isinstance(resp, str):
                parts.append(f"- {resp}")
        skills_acq = exp.get('skills_acquired', []) or []
        if skills_acq:
            parts.append(f"Tekniker: {', '.join(str(s) for s in skills_acq)}")

    for edu in resume.get('education_details', []) or []:
        if not isinstance(edu, dict):
            continue
        parts.append(
            f"\n{edu.get('education_level','')} {edu.get('field_of_study','')} "
            f"— {edu.get('institution','')}"
        )
        ai = edu.get('additional_info') or {}
        if isinstance(ai, dict):
            for v in ai.values():
                if v:
                    parts.append(str(v))

    for proj in resume.get('projects', []) or []:
        if isinstance(proj, dict):
            parts.append(f"\nProjekt: {proj.get('name','')} — {proj.get('description','')}")

    return '\n'.join(parts)


# Kända signaturer för bot-fallback-beskrivningar genererade av modern_facade.py
# när scrapern blockerats av captcha eller fått tom text.
_PLACEHOLDER_PATTERNS = [
    'vi söker en engagerad medarbetare',
    'tjänsten kräver teknisk kompetens och erfarenhet av webbutveckling',
]


def _is_placeholder_description(text: str) -> bool:
    """Returnera True om beskrivningen är en känd bot-fallback eller för kort/innehållslös
    för att meningsfullt analyseras."""
    if not text:
        return True
    t = text.strip().lower()
    # Kortare än 400 tecken indikerar att riktig annonstext inte hämtades
    # (riktiga annonser är typiskt 1500-5000 tecken).
    if len(t) < 400:
        return True
    if any(p in t for p in _PLACEHOLDER_PATTERNS):
        return True
    return False


def _extract_url_from_job_info(job_folder: Path) -> str:
    """Hämta sparad jobb-URL från job_info.txt (rad-format 'Indeed URL:', 'LinkedIn URL:' osv)."""
    info = job_folder / 'job_info.txt'
    if not info.exists():
        return ''
    for line in info.read_text(encoding='utf-8').split('\n'):
        if ' URL:' in line:
            url = line.split(' URL:', 1)[1].strip()
            if url.startswith('http'):
                return url
    return ''


def _fetch_job_description_from_url(url: str) -> str:
    """Hämtar jobbannons från URL. Försöker requests först, sen Playwright (headless Chrome)
    som fallback för JS-renderade sidor som Indeed, LinkedIn m.fl."""
    if not url:
        return ''

    # Selektorer för jobbeskrivning-container på vanliga jobbsajter
    _DESC_SELECTORS = [
        '#jobDescriptionText',
        '.jobsearch-jobDescriptionText',
        '[data-testid="jobsearch-JobComponent-description"]',
        '.show-more-less-html__markup',
        '[data-test-id="job-description"]',
        '.job-description',
        'article',
        'main',
    ]

    def _extract_from_html(html: str) -> str:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()
        for sel in _DESC_SELECTORS:
            el = soup.select_one(sel)
            if el:
                text = ' '.join(el.get_text(' ', strip=True).split())
                if len(text) > 400:
                    return text[:12000]
        text = ' '.join(soup.get_text(' ', strip=True).split())
        return text[:12000] if len(text) > 400 else ''

    # ── Försök 1: requests (snabb, funkar för statiska sidor) ──────────────
    try:
        import requests
        headers = {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/124.0.0.0 Safari/537.36'),
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Accept-Language': 'sv-SE,sv;q=0.9,en;q=0.8',
        }
        r = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            text = _extract_from_html(r.text)
            if text and not _is_placeholder_description(text):
                return text
    except Exception:
        pass

    # ── Försök 2: Playwright (headless Chrome — kör JS, hanterar cookies) ──
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = browser.new_page(
                user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                             'AppleWebKit/537.36 (KHTML, like Gecko) '
                             'Chrome/124.0.0.0 Safari/537.36')
            )
            # Blockera bilder/fonts för snabbhet
            page.route('**/*.{png,jpg,gif,svg,woff,woff2,ttf}', lambda r: r.abort())
            page.goto(url, wait_until='domcontentloaded', timeout=20000)
            # Stäng cookie-popups om de dyker upp
            for btn_text in ['Avvisa alla', 'Reject all', 'Accept', 'Acceptera']:
                try:
                    page.get_by_text(btn_text, exact=True).first.click(timeout=2000)
                except Exception:
                    pass
            page.wait_for_timeout(2000)
            # Extrahera text från kända selektorer
            for sel in _DESC_SELECTORS:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0:
                        text = el.inner_text()
                        if len(text) > 400:
                            browser.close()
                            return text[:12000]
                except Exception:
                    continue
            # Fallback: hela body-texten
            text = page.locator('body').inner_text()
            browser.close()
            if len(text) > 400:
                return text[:12000]
    except Exception:
        pass

    return ''


def _llm_json_call(prompt_text: str, temperature: float) -> dict:
    """Anropa LLM och parsa JSON-svar. Strippar markdown-fences."""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    llm    = get_user_llm(temperature=temperature)
    prompt = ChatPromptTemplate.from_messages([("human", "{prompt}")])
    chain  = prompt | llm | StrOutputParser()
    raw    = chain.invoke({'prompt': prompt_text})
    raw    = re.sub(r'^```(?:json)?', '', raw.strip(), flags=re.MULTILINE)
    raw    = re.sub(r'```$', '', raw.strip(), flags=re.MULTILINE)
    return json.loads(raw.strip())


def _evaluate_job_ats(job_folder: Path, force: bool = False) -> dict:
    """Detaljerad 3-pass ATS-pipeline för EN jobbmapp:
       1) LLM extraherar keywords + hårda krav från annons
       2) Deterministisk keyword-matchning i full CV-text
       3) LLM bedömer transferable + soft skills, ger konkreta rekommendationer
       Slutpoäng är viktad formel — inte LLM-satt.

    Returnerar alltid en dict med 'ok'. Vid fel finns 'error' + '_status'
    (HTTP-hint). Skriver ats_score.json vid lyckad körning, återanvänder cachen
    om force=False. Anropas av BÅDE /api/ats-score/generate (per jobb) OCH
    batch-utvärderingen — så att poängen är identisk överallt."""
    score_file = job_folder / 'ats_score.json'
    if score_file.exists() and not force:
        try:
            return {'ok': True, **json.loads(score_file.read_text(encoding='utf-8'))}
        except Exception:
            pass

    desc_file = job_folder / 'job_description.txt'
    job_description = desc_file.read_text(encoding='utf-8').strip() if desc_file.exists() else ''

    job = parse_job_folder(job_folder)
    job_title = job.get('title', '')
    company   = job.get('company', '')
    folder    = job_folder.name

    if not job_description:
        return {
            'ok': False,
            'error': 'Ingen jobbeskrivning sparad för detta jobb. Kommande jobb sparas automatiskt.',
            'no_description': True,
            '_status': 422,
        }

    partial_description = False
    if _is_placeholder_description(job_description):
        # Försök hämta fullständig annonstext från sparad URL
        url = _extract_url_from_job_info(job_folder)
        fetched = _fetch_job_description_from_url(url) if url else ''
        if fetched and not _is_placeholder_description(fetched):
            job_description = fetched
            desc_file.write_text(fetched, encoding='utf-8')
        else:
            # Kör ATS ändå med ofullständig text — visa varning i resultatet
            # istället för att vägra helt. Användaren kan fortfarande se en indikation.
            partial_description = True

    cv_text = _get_cv_full_text(job_folder)
    if not cv_text:
        return {'ok': False, 'error': 'CV saknas — fyll i ditt CV först', '_status': 422}

    try:
        # ── Pass 1: Keyword-extraktion (temp=0 för deterministisk extraktion)
        kw = _llm_json_call(
            _build_keyword_extraction_prompt(job_description, job_title, company),
            temperature=0.0
        )

        # ── Pass 2: Deterministisk matchning
        cv_lower = _normalize_for_match(cv_text)
        must_matches   = _match_keyword_list(kw.get('must_have', []),   cv_lower)
        should_matches = _match_keyword_list(kw.get('should_have', []), cv_lower)
        nice_matches   = _match_keyword_list(kw.get('nice_to_have', []), cv_lower)
        hard_matches   = _match_hard_requirements(kw.get('hard_requirements', []), cv_lower)

        must_found    = sum(1 for m in must_matches   if m['found'])
        should_found  = sum(1 for m in should_matches if m['found'])
        nice_found    = sum(1 for m in nice_matches   if m['found'])
        must_pct      = _pct(must_found,   len(must_matches))
        should_pct    = _pct(should_found, len(should_matches))
        nice_pct      = _pct(nice_found,   len(nice_matches))
        blockers_unsat = sum(1 for h in hard_matches if not h['satisfied'])

        # ── Pass 3: Rekryterar-bedömning (transferable + soft skills + rekommendationer)
        kw_summary = _build_keyword_summary_for_llm(
            must_matches, should_matches, nice_matches, hard_matches,
            must_pct, should_pct
        )
        rec = _llm_json_call(
            _build_recruiter_assessment_prompt(
                cv_text, job_description, job_title, company, kw_summary
            ),
            temperature=0.1
        )
        transferable = max(0, min(100, int(rec.get('transferable_score', 50))))
        soft_skills  = max(0, min(100, int(rec.get('soft_skills_score', 50))))

        # ── Composite score (deterministisk viktning + sqrt-mjukning)
        composite = _compute_composite_score(
            must_pct, should_pct, transferable, soft_skills,
            len(must_matches), blockers_unsat,
            must_matched=must_found, should_matched=should_found
        )

        # ── Backwards-compat fält (matched_skills / missing_skills / recommendations som strängar)
        matched_skills_flat = [m['term'] for m in must_matches + should_matches if m['found']][:8]
        missing_skills_flat = [m['term'] for m in must_matches + should_matches if not m['found']][:6]
        recs_raw = rec.get('recommendations', []) or []
        recommendations_flat = []
        for r in recs_raw:
            if isinstance(r, dict):
                action = r.get('action', '').strip()
                where  = r.get('where', '').strip()
                txt    = r.get('suggested_text', '').strip()
                bits   = [action]
                if where:
                    bits.append(f"[{where}]")
                if txt:
                    bits.append(f"→ \"{txt}\"")
                recommendations_flat.append(' '.join(bits))
            elif isinstance(r, str):
                recommendations_flat.append(r)

        result = {
            'folder': folder,
            'score':  composite,
            'score_breakdown': {
                'must_have':    {'matched': must_found,   'total': len(must_matches),   'pct': must_pct,   'weight': 0.40 if must_matches else 0.0},
                'should_have':  {'matched': should_found, 'total': len(should_matches), 'pct': should_pct, 'weight': 0.25 if must_matches else 0.55},
                'nice_to_have': {'matched': nice_found,   'total': len(nice_matches),   'pct': nice_pct,   'weight': 0.0},
                'transferable': {'score': transferable, 'weight': 0.20 if must_matches else 0.28, 'reasoning': rec.get('transferable_reasoning', '')},
                'soft_skills':  {'score': soft_skills,  'weight': 0.15 if must_matches else 0.17, 'reasoning': rec.get('soft_skills_reasoning', '')},
                'hard_blockers_unsatisfied': blockers_unsat,
                'penalty_applied': blockers_unsat * 10,
            },
            'keywords_must':   must_matches,
            'keywords_should': should_matches,
            'keywords_nice':   nice_matches,
            'hard_blockers':   hard_matches,
            'recommendations_structured': recs_raw,
            # Backwards-compat:
            'matched_skills':  matched_skills_flat,
            'missing_skills':  missing_skills_flat,
            'recommendations': recommendations_flat,
            'summary':         rec.get('summary', ''),
            'partial_description': partial_description,
            'partial_warning': ('Annonstexten var ofullständig — analysen baseras på begränsad information och kan vara missvisande.'
                                if partial_description else ''),
        }

        score_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return {'ok': True, **result}

    except json.JSONDecodeError as e:
        return {'ok': False, 'error': f'AI svarade i fel format: {e}', '_status': 500}
    except Exception as e:
        return {'ok': False, 'error': str(e), '_status': 500}


@app.route('/api/ats-score/generate', methods=['POST'])
def api_ats_generate():
    """Tunn HTTP-wrapper kring _evaluate_job_ats (per jobb från /jobs-sidan)."""
    data   = request.get_json(silent=True) or {}
    folder = data.get('folder', '').strip()
    if not folder:
        return jsonify({'ok': False, 'error': 'folder required'}), 400
    if '..' in folder or '/' in folder or '\\' in folder:
        return jsonify({'ok': False, 'error': 'Ogiltig mapp'}), 400
    job_folder = _user_output_dir() / folder
    if not job_folder.exists():
        return jsonify({'ok': False, 'error': 'Mappen finns inte'}), 404
    result = _evaluate_job_ats(job_folder, force=bool(data.get('force')))
    status = result.pop('_status', 200 if result.get('ok') else 500)
    return jsonify(result), status


@app.route('/api/ats-score/<folder>')
def api_ats_get(folder):
    """Return cached ATS score for a folder"""
    score_file = _user_output_dir() / folder / 'ats_score.json'
    if score_file.exists():
        try:
            data = json.loads(score_file.read_text(encoding='utf-8'))
            return jsonify({'ok': True, **data})
        except Exception:
            pass
    return jsonify({'ok': False, 'cached': False})


# ============================================================
# ROUTES — KANBAN TRACKER
# ============================================================

TRACKER_COLUMNS = [
    ('ready',     'Redo att söka','bi-file-earmark-check','col-ready'),
    ('applied',   'Sökt',         'bi-send',              'col-applied'),
    ('response',  'Svar',         'bi-chat-dots',         'col-response'),
    ('interview', 'Intervju',     'bi-person-lines-fill', 'col-interview'),
    ('offer',     'Erbjudande',   'bi-trophy',            'col-offer'),
    ('rejected',  'Avslag',       'bi-x-circle',          'col-rejected'),
]


@app.route('/tracker')
def tracker():
    folders   = get_job_folders()
    all_jobs  = [parse_job_folder(f) for f in folders]
    tracker   = load_tracker()

    # Assign default status 'ready' to jobs without a tracker entry
    for job in all_jobs:
        if job['folder'] not in tracker:
            tracker[job['folder']] = {'status': 'ready', 'notes': '', 'updated': job.get('date', '')}
        job['tracker_status'] = tracker[job['folder']]['status']
        job['tracker_notes']  = tracker[job['folder']].get('notes', '')

    # Group by column
    columns = {}
    for key, label, icon, css_class in TRACKER_COLUMNS:
        columns[key] = {
            'label':     label,
            'icon':      icon,
            'css_class': css_class,
            'jobs':      [j for j in all_jobs if j['tracker_status'] == key],
        }

    return render_template('tracker.html',
                           columns=columns,
                           tracker_cols=TRACKER_COLUMNS,
                           total=len(all_jobs))


@app.route('/api/tracker/update', methods=['POST'])
def api_tracker_update():
    """Update tracker status for a job folder"""
    data   = request.get_json(silent=True) or {}
    folder = data.get('folder', '').strip()
    status = data.get('status', 'applied')
    notes  = data.get('notes', '')

    valid_statuses = {col[0] for col in TRACKER_COLUMNS}
    if not folder or status not in valid_statuses:
        return jsonify({'ok': False, 'error': 'Invalid folder or status'}), 400

    tracker = load_tracker()
    tracker[folder] = {
        'status':  status,
        'notes':   notes,
        'updated': datetime.now().strftime('%Y-%m-%d'),
    }
    save_tracker(tracker)
    return jsonify({'ok': True, 'folder': folder, 'status': status})


# ============================================================
# SCHEDULER STARTUP
# ============================================================
threading.Thread(target=_scheduler_loop, daemon=True, name='scheduler').start()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == '__main__':
    print('\n' + '='*60)
    print('  ApplyMind AI — Webbgränssnitt')
    print('='*60)
    print('  URL: http://localhost:5000')
    print('  Tryck Ctrl+C för att stoppa')
    print('='*60 + '\n')
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(debug=False, port=5000, host='0.0.0.0', threaded=True, use_reloader=True)
