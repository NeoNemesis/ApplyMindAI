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
app.secret_key = os.environ.get('FLASK_SECRET', 'applymind-ai-secret-2026')

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
        t         = getattr(g, 't', get_translations('sv')),
        lang      = getattr(g, 'lang', 'sv'),
        languages = LANGUAGE_NAMES,
        app_name  = 'ApplyMind AI',
    )

# ============================================================
# PATHS
# ============================================================
DATA_DIR        = BASE_DIR / 'data_folder'
OUTPUT_DIR      = DATA_DIR / 'output' / 'job_master'
RESUME_YAML     = DATA_DIR / 'plain_text_resume.yaml'
PREFS_YAML      = DATA_DIR / 'work_preferences.yaml'
COVER_LETTER    = DATA_DIR / 'reference_cover_letter.txt'
PROCESSED_JOBS  = OUTPUT_DIR / 'processed_jobs.json'
FOUND_JOBS      = OUTPUT_DIR / 'found_jobs.json'
OPENAI_CALLS    = OUTPUT_DIR / 'open_ai_calls.json'
TRACKER_FILE    = DATA_DIR / 'tracker_status.json'
SCHEDULER_FILE  = DATA_DIR / 'scheduler_config.json'

# ============================================================
# SEARCH STATE (thread-safe via lock)
# ============================================================
_search_lock = threading.Lock()
search_state = {
    'running': False,
    'output': [],
    'error': None,
    'progress': 0,
    'started_at': None,
    'finished_at': None,
}
search_queue = queue.Queue()
_stop_requested = False  # Global stop flag — set by /search/stop


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
        if SCHEDULER_FILE.exists():
            data = json.loads(SCHEDULER_FILE.read_text(encoding='utf-8'))
            cfg = dict(_SCHEDULER_DEFAULTS)
            cfg.update(data)
            return cfg
    except Exception:
        pass
    return dict(_SCHEDULER_DEFAULTS)

def save_scheduler_config(updates: dict):
    cfg = load_scheduler_config()
    cfg.update(updates)
    SCHEDULER_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')

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

                # Load saved preferences and fire search
                prefs = load_yaml(PREFS_YAML) or {}
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

                def _sched_search(plats=platforms, mj=max_jobs, locs=locations, pos=positions):
                    global search_state
                    old_out = sys.stdout
                    class _SC:
                        encoding = 'utf-8'
                        def write(self, t):
                            if t and t.strip():
                                search_queue.put(('output', t))
                            old_out.write(t)
                        def flush(self): old_out.flush()
                        def reconfigure(self, **kw): pass
                    from job_master import JobMaster
                    try:
                        sys.stdout = _SC()
                        jm = JobMaster()
                        jm.initialize()
                        jobs = jm.search_jobs(plats, mj, locations=locs, positions=pos)
                        for i, job in enumerate(jobs or [], 1):
                            jm.generate_documents_for_job(job, i)
                        jm.cleanup()
                    except Exception as e:
                        search_queue.put(('error', str(e)))
                    finally:
                        sys.stdout = old_out
                        with _search_lock:
                            search_state['running']     = False
                            search_state['progress']    = 100
                            search_state['finished_at'] = datetime.now().isoformat()
                        search_queue.put(('done', None))

                threading.Thread(target=_sched_search, daemon=True).start()
        except Exception:
            pass


def is_setup_complete() -> bool:
    """Return True if at least one API key is configured"""
    env = read_env()
    providers = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY']
    llm_provider = env.get('LLM_PROVIDER', 'openai')
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
        with open(TRACKER_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_tracker(data: dict):
    """Save tracker status dict"""
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_job_folders():
    """Get all job output folders sorted newest first"""
    if not OUTPUT_DIR.exists():
        return []
    folders = [f for f in OUTPUT_DIR.iterdir() if f.is_dir()]
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
    processed   = load_json(PROCESSED_JOBS)
    folders     = get_job_folders()

    jobs_with_letter = sum(
        1 for f in folders
        if any(p.name.startswith('Personligt_Brev') for p in f.iterdir() if p.is_file())
    )

    total_calls, total_cost = parse_openai_calls(OPENAI_CALLS) if OPENAI_CALLS.exists() else (0, 0.0)

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
# SETUP CHECK — redirect new users to wizard
# ============================================================
@app.before_request
def check_setup():
    allowed = ['/setup', '/static', '/api/found-jobs']
    if not is_setup_complete() and not any(request.path.startswith(p) for p in allowed):
        return redirect(url_for('setup'))


# ============================================================
# ROUTES — DASHBOARD
# ============================================================
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

PROFILE_PHOTO_PATH = DATA_DIR / 'profile.png'
ALLOWED_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png'}
MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB


@app.route('/cv')
def cv_editor():
    resume = load_yaml(RESUME_YAML)
    has_photo = PROFILE_PHOTO_PATH.exists()
    return render_template('cv.html', resume=resume,
                           has_profile_photo=has_photo,
                           now=int(time.time()))


@app.route('/cv/photo')
def cv_photo():
    """Serve the profile photo"""
    if not PROFILE_PHOTO_PATH.exists():
        return 'Ingen bild', 404
    return send_file(str(PROFILE_PHOTO_PATH), mimetype='image/png')


@app.route('/cv/upload-photo', methods=['POST'])
def cv_upload_photo():
    """Upload and save profile photo as data_folder/profile.png"""
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

    # Convert JPG to PNG for consistency (overwrite profile.png)
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data)).convert('RGB')
        img.save(str(PROFILE_PHOTO_PATH), 'PNG', optimize=True)
    except ImportError:
        # PIL not installed — save raw file (works for PNG, near-works for JPG)
        PROFILE_PHOTO_PATH.write_bytes(data)
    except Exception as e:
        flash(f'Kunde inte spara bilden: {e}', 'danger')
        return redirect(url_for('cv_editor'))

    flash('Profilbild sparad!', 'success')
    return redirect(url_for('cv_editor'))


@app.route('/cv/delete-photo')
def cv_delete_photo():
    """Delete profile photo"""
    if PROFILE_PHOTO_PATH.exists():
        PROFILE_PHOTO_PATH.unlink()
        flash('Profilbild borttagen.', 'success')
    return redirect(url_for('cv_editor'))


@app.route('/cv/save', methods=['POST'])
def cv_save():
    resume = load_yaml(RESUME_YAML)

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

    save_yaml(RESUME_YAML, resume)
    flash('CV sparat!', 'success')
    return redirect(url_for('cv_editor'))


# ============================================================
# ROUTES — COVER LETTER
# ============================================================

@app.route('/cover-letter')
def cover_letter():
    content = COVER_LETTER.read_text(encoding='utf-8') if COVER_LETTER.exists() else ''
    resume  = load_yaml(RESUME_YAML)
    profile = resume.get('cover_letter_profile', '')
    return render_template('cover_letter.html', content=content, profile=profile)


LETTER_TEMPLATE_NAMES = {
    'problem_solution': 'Problem-Lösning',
    'executive':        'Executive / Klassisk',
    'modern_tech':      'Modern Tech',
    'nordic_minimal':   'Nordisk Minimal',
}

@app.route('/cover-letter/templates')
def letter_templates():
    active = read_env().get('LETTER_TEMPLATE', 'problem_solution')
    return render_template('letter_templates.html', active_template=active)

@app.route('/cover-letter/template/select', methods=['POST'])
def letter_template_select():
    tmpl = request.form.get('template', 'problem_solution')
    if tmpl in LETTER_TEMPLATE_NAMES:
        write_env({'LETTER_TEMPLATE': tmpl})
        flash(f'Brevmall vald: {LETTER_TEMPLATE_NAMES[tmpl]}', 'success')
    return redirect(url_for('letter_templates'))

@app.route('/cover-letter/template/preview/<template_key>')
def letter_template_preview(template_key):
    tmpl_file = BASE_DIR / 'static' / 'letter_templates' / f'template_{template_key}.html'
    if not tmpl_file.exists():
        return "Mall hittades inte", 404
    return tmpl_file.read_text(encoding='utf-8')

@app.route('/cover-letter/save', methods=['POST'])
def cover_letter_save():
    content = request.form.get('content', '')
    COVER_LETTER.write_text(content, encoding='utf-8')

    profile = request.form.get('profile', '')
    if profile:
        resume = load_yaml(RESUME_YAML)
        resume['cover_letter_profile'] = profile
        save_yaml(RESUME_YAML, resume)

    flash('Personligt brev sparat!', 'success')
    return redirect(url_for('cover_letter'))


# ============================================================
# ROUTES — JOB SEARCH
# ============================================================

@app.route('/search')
def search():
    prefs = load_yaml(PREFS_YAML)
    current_cv_design = read_env().get('CV_DESIGN', 'design_01_minimal')
    return render_template('search.html', prefs=prefs, search_state=search_state, current_cv_design=current_cv_design)


@app.route('/search/run', methods=['POST'])
def search_run():
    global search_state

    with _search_lock:
        if search_state['running']:
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

        # Save selected CV design to .env
        cv_design = request.form.get('cv_design', 'design_01_minimal')
        if cv_design in DESIGNS:
            write_env({'CV_DESIGN': cv_design})

        # Update preferences YAML
        prefs = load_yaml(PREFS_YAML)
        prefs['remote']    = remote
        prefs['hybrid']    = hybrid
        prefs['onsite']    = onsite
        prefs['locations'] = locations
        if positions:
            prefs['positions'] = positions
        save_yaml(PREFS_YAML, prefs)

        # Reset state
        search_state = {
            'running':     True,
            'output':      [],
            'error':       None,
            'progress':    0,
            'started_at':  datetime.now().isoformat(),
            'finished_at': None,
        }

    # Drain queue
    while not search_queue.empty():
        try:
            search_queue.get_nowait()
        except queue.Empty:
            break

    def run_search():
        global search_state, _stop_requested
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        class OutputCapture:
            """Capture stdout/stderr and push to SSE queue"""
            encoding = 'utf-8'

            def write(self, text):
                if text and text.strip():
                    search_queue.put(('output', text))
                if old_stdout is not None:
                    try:
                        old_stdout.write(text)
                    except (UnicodeEncodeError, TypeError):
                        # Windows cp1252 console can't handle Swedish/emoji chars — ignore
                        pass

            def flush(self):
                if old_stdout is not None:
                    old_stdout.flush()

            def reconfigure(self, **kwargs):
                pass  # called by job_master on Windows — safe to ignore

        try:
            # Import inside try-finally so search_state is always reset even if import fails
            from job_master import JobMaster

            sys.stdout = OutputCapture()
            sys.stderr = OutputCapture()

            _stop_requested = False
            jm = JobMaster()
            jm.stop_requested = False
            jm.initialize(platforms=platforms)  # Skip browser if only API platforms selected

            search_queue.put(('output', f'\n🔍 Plattformar: {", ".join(platforms)}\n'))
            search_queue.put(('output', f'📍 Platser: {", ".join(locations)}\n'))
            search_queue.put(('output', f'🎯 Max jobb: {max_jobs}\n\n'))

            # Propagate stop flag from web_app global to jm instance during search
            def _sync_stop_flag():
                import time as _time
                while search_state.get('running') and not _stop_requested:
                    _time.sleep(0.3)
                jm.stop_requested = True  # always signal jm when loop ends (either stop or finish)

            threading.Thread(target=_sync_stop_flag, daemon=True).start()

            jobs = jm.search_jobs(platforms, max_jobs, locations=locations, positions=positions)

            if _stop_requested:
                search_queue.put(('output', '\n⛔ Sökning avbruten av användaren.\n'))
            elif jobs:
                search_queue.put(('output', f'\n✅ Hittade {len(jobs)} jobb!\n'))
                search_queue.put(('output', '\n📝 Genererar CV och personliga brev...\n'))
                successful = 0
                for i, job in enumerate(jobs, 1):
                    if _stop_requested:
                        search_queue.put(('output', '\n⛔ Dokumentgenerering avbruten.\n'))
                        break
                    search_queue.put(('progress', f'{i}/{len(jobs)}'))
                    search_queue.put(('output', f'\n[{i}/{len(jobs)}] 📄 {job["title"]} @ {job["company"]}\n'))
                    ok = jm.generate_documents_for_job(
                        job, i,
                        ats_filter=ats_filter_enabled,
                        ats_threshold=ats_threshold,
                        auto_apply=auto_apply_enabled,
                    )
                    if ok:
                        successful += 1
                        search_queue.put(('output', '   ✅ Klar!\n'))
                    else:
                        search_queue.put(('output', '   ⏭️  Hoppades över\n'))
                search_queue.put(('output', f'\n✅ KLART! {successful}/{len(jobs)} jobb processade.\n'))
                search_queue.put(('output', f'📂 Filer sparade i: {jm.base_output_dir}\n'))
            else:
                search_queue.put(('output', '\n❌ Inga nya jobb hittades. Prova att ändra sökkriterierna.\n'))

            jm.cleanup()

        except Exception as e:
            import traceback
            err_msg = f'\n❌ Fel: {str(e)}\n{traceback.format_exc()}\n'
            search_queue.put(('error', err_msg))
            with _search_lock:
                search_state['error'] = str(e)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            with _search_lock:
                search_state['running']     = False
                search_state['progress']    = 100
                search_state['finished_at'] = datetime.now().isoformat()
            search_queue.put(('done', None))

    threading.Thread(target=run_search, daemon=True).start()
    return jsonify({'status': 'started'})


@app.route('/search/stream')
def search_stream():
    """Server-Sent Events stream for live search output"""
    def generate():
        yield 'data: {"type":"connected"}\n\n'
        while True:
            try:
                msg_type, msg = search_queue.get(timeout=25)
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
                yield 'data: {"type":"ping"}\n\n'
                if not search_state.get('running'):
                    yield 'data: {"type":"done"}\n\n'
                    break

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':    'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection':       'keep-alive',
        }
    )


@app.route('/search/stop', methods=['POST'])
def search_stop():
    """Stop an ongoing search gracefully"""
    global _stop_requested
    if not search_state.get('running'):
        return jsonify({'status': 'not_running'})
    _stop_requested = True
    search_queue.put(('output', '\n⛔ Stoppsignal mottagen — avslutar pågående plattform...\n'))
    return jsonify({'status': 'stopping'})


@app.route('/search/status')
def search_status():
    return jsonify(search_state)


# ============================================================
# ROUTES — BATCH RE-EVALUATE
# ============================================================

@app.route('/generate/batch-evaluate', methods=['POST'])
def batch_evaluate():
    """Re-evaluate all jobs in found_jobs.json with ATS filter (threshold 60%).
    Generates CV+cover letter for jobs scoring ≥60%, deletes folders for the rest."""
    global _stop_requested

    with _search_lock:
        if search_state.get('running'):
            return jsonify({'status': 'already_running'})
        _stop_requested = False
        search_state.update({
            'running':      True,
            'output':       [],
            'error':        None,
            'progress':     0,
            'started_at':   datetime.now().isoformat(),
            'finished_at':  None,
        })

    # Flush queue
    while not search_queue.empty():
        try:
            search_queue.get_nowait()
        except queue.Empty:
            break

    def run_evaluation():
        global _stop_requested
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        class OutputCapture:
            def write(self, text):
                if text and text.strip():
                    search_queue.put(('output', text))
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
            if not FOUND_JOBS.exists():
                search_queue.put(('error', '❌ Inga sparade jobb hittades. Gör en sökning först.\n'))
                return

            jobs = json.loads(FOUND_JOBS.read_text(encoding='utf-8'))
            if not jobs:
                search_queue.put(('output', '❌ Jobbfilen är tom. Gör en ny sökning.\n'))
                search_queue.put(('done', None))
                return

            sep = '=' * 60
            search_queue.put(('output',
                f'\n🔍 Utvärderar {len(jobs)} sparade jobb med ATS-filter (tröskel: 60%)...\n'
                f'{sep}\n'
            ))

            from job_master import JobMaster
            jm = JobMaster()
            # Lazy browser init — only starts if a job needs it
            jm.initialize(platforms=['jobtech'])

            def _sync_stop():
                import time as _t
                while search_state.get('running') and not _stop_requested:
                    _t.sleep(0.3)
                jm.stop_requested = True

            threading.Thread(target=_sync_stop, daemon=True).start()

            passed = 0
            failed = 0

            for i, job in enumerate(jobs, 1):
                if _stop_requested:
                    search_queue.put(('output', '\n⛔ Avbruten av användaren.\n'))
                    break

                search_queue.put(('progress', f'{i}/{len(jobs)}'))
                search_queue.put(('output',
                    f'\n[{i}/{len(jobs)}] {job["title"]} @ {job["company"]}\n'
                ))

                ok = jm.generate_documents_for_job(
                    job, i,
                    ats_filter=True,
                    ats_threshold=60,
                )

                if ok:
                    passed += 1
                    search_queue.put(('output', '   ✅ Dokument genererade! (ATS ≥ 60%)\n'))
                else:
                    failed += 1
                    search_queue.put(('output', '   ❌ Under tröskeln (ATS < 60%) — tar bort mapp...\n'))
                    # Delete the job folder so it doesn't clutter the jobs list
                    safe_company = "".join(
                        c for c in job['company'] if c.isalnum() or c in (' ', '-', '_')
                    ).strip()
                    safe_title = "".join(
                        c for c in job['title'][:30] if c.isalnum() or c in (' ', '-', '_')
                    ).strip()
                    folder_path = OUTPUT_DIR / f"Job_{i:03d}_{safe_company}_{safe_title}"
                    if folder_path.exists():
                        shutil.rmtree(folder_path)
                        search_queue.put(('output', f'   🗑️  Borttagen: {folder_path.name}\n'))

            jm.cleanup()

            search_queue.put(('output',
                f'\n{sep}\n'
                f'📊 RESULTAT: {passed} godkända, {failed} borttagna av {len(jobs)} jobb\n'
                f'📂 Filer: {OUTPUT_DIR}\n'
            ))

        except Exception as e:
            import traceback
            err = f'\n❌ Fel: {str(e)}\n{traceback.format_exc()}\n'
            search_queue.put(('error', err))
            with _search_lock:
                search_state['error'] = str(e)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            with _search_lock:
                search_state['running']     = False
                search_state['progress']    = 100
                search_state['finished_at'] = datetime.now().isoformat()
            search_queue.put(('done', None))

    threading.Thread(target=run_evaluation, daemon=True).start()
    return jsonify({'status': 'started'})


# ============================================================
# ROUTES — JOBS LIST
# ============================================================

@app.route('/jobs')
def jobs():
    folders  = get_job_folders()
    job_list = [parse_job_folder(f) for f in folders]
    return render_template('jobs.html', jobs=job_list)


@app.route('/download-pdf')
def download_file():
    """Download a PDF document (query-param based to handle Swedish chars)"""
    folder   = request.args.get('folder',   '').strip()
    filename = request.args.get('filename', '').strip()
    if not folder or not filename:
        return 'Parametrar saknas', 400
    if '..' in folder or '..' in filename or '/' in filename or '\\' in filename:
        return 'Ogiltig förfrågan', 400
    file_path = OUTPUT_DIR / folder / filename
    if file_path.exists() and file_path.suffix.lower() == '.pdf':
        return send_file(str(file_path.resolve()), as_attachment=True,
                         download_name=filename)
    return 'Filen hittades inte', 404


@app.route('/view-pdf')
def view_pdf():
    """View a PDF in browser (query-param based to handle Swedish chars)"""
    folder   = request.args.get('folder',   '').strip()
    filename = request.args.get('filename', '').strip()
    if not folder or not filename:
        return 'Parametrar saknas', 400
    if '..' in folder or '..' in filename or '/' in filename or '\\' in filename:
        return 'Ogiltig förfrågan', 400
    file_path = OUTPUT_DIR / folder / filename
    if file_path.exists() and file_path.suffix.lower() == '.pdf':
        return send_file(str(file_path.resolve()), mimetype='application/pdf')
    return 'Filen hittades inte', 404


# Legacy path-based routes (redirect to query-param versions)
@app.route('/download/<path:subpath>')
def download_file_legacy(subpath):
    parts = subpath.split('/', 1)
    if len(parts) == 2:
        return redirect(f'/download-pdf?folder={parts[0]}&filename={parts[1]}')
    return 'Ogiltig URL', 400


@app.route('/view/<path:subpath>')
def view_pdf_legacy(subpath):
    parts = subpath.split('/', 1)
    if len(parts) == 2:
        return redirect(f'/view-pdf?folder={parts[0]}&filename={parts[1]}')
    return 'Ogiltig URL', 400


@app.route('/api/jobs')
def api_jobs():
    """JSON API for jobs list"""
    folders  = get_job_folders()
    job_list = [parse_job_folder(f) for f in folders]
    return jsonify(job_list)


@app.route('/api/jobs/delete', methods=['POST'])
def api_delete_job():
    """Radera ett jobb: ta bort mappen och blockera URL:en från framtida sökningar."""
    data   = request.get_json(silent=True) or {}
    folder = data.get('folder', '').strip()

    if not folder or '..' in folder or '/' in folder or '\\' in folder:
        return jsonify({'ok': False, 'error': 'Ogiltig mapp'}), 400

    job_folder = OUTPUT_DIR / folder
    if not job_folder.exists():
        return jsonify({'ok': False, 'error': 'Mappen finns inte'}), 404

    # Hämta URL från job_info.txt så vi kan blockera den
    job      = parse_job_folder(job_folder)
    job_url  = job.get('url', '').strip()

    # Säkerställ att URL:en finns i processed_jobs.json (blockerar framtida sökningar)
    if job_url:
        try:
            existing = json.loads(PROCESSED_JOBS.read_text(encoding='utf-8')) if PROCESSED_JOBS.exists() else []
        except Exception:
            existing = []

        known_urls = {j.get('url') for j in existing}
        if job_url not in known_urls:
            existing.append({
                'url':            job_url,
                'title':          job.get('title', ''),
                'company':        job.get('company', ''),
                'source':         job.get('source', ''),
                'status':         'rejected',
                'processed_date': datetime.now().isoformat(),
            })
            PROCESSED_JOBS.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8'
            )
        else:
            # Markera som rejected om den redan finns
            changed = False
            for j in existing:
                if j.get('url') == job_url and j.get('status') != 'rejected':
                    j['status'] = 'rejected'
                    changed = True
            if changed:
                PROCESSED_JOBS.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8'
                )

    # Radera mappen med alla filer
    shutil.rmtree(str(job_folder), ignore_errors=True)

    return jsonify({'ok': True})


@app.route('/api/jobs/regenerate-docs', methods=['POST'])
def api_regenerate_docs():
    """Bygg om CV och personligt brev för ett jobb med den aktuella grundfilen."""
    data   = request.get_json(silent=True) or {}
    folder = data.get('folder', '').strip()

    if not folder or '..' in folder or '/' in folder or '\\' in folder:
        return jsonify({'ok': False, 'error': 'Ogiltig mapp'}), 400

    job_folder = OUTPUT_DIR / folder
    if not job_folder.exists():
        return jsonify({'ok': False, 'error': 'Mappen finns inte'}), 404

    desc_file = job_folder / 'job_description.txt'
    if not desc_file.exists():
        return jsonify({'ok': False, 'error': 'Ingen jobbeskrivning sparad för detta jobb'}), 400

    job_description = desc_file.read_text(encoding='utf-8')

    try:
        from job_master import JobMaster
        jm = JobMaster()
        jm.initialize(platforms=[])

        # Bygg ett minimalt jobb-objekt med sparad beskrivning
        class _FakeJob:
            description = job_description
            link = folder

        jm.modern_facade.job = _FakeJob()

        # Generera CV
        _design = os.getenv('CV_DESIGN', 'design_01_minimal')
        cv_base64, _ = jm.modern_facade.create_resume_pdf_job_tailored()

        # Ta bort gamla CV-filer och spara ny
        for old in job_folder.glob('CV_*.pdf'):
            old.unlink()

        job = parse_job_folder(job_folder)
        safe_company = ''.join(c for c in job.get('company', 'Foretag') if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title   = ''.join(c for c in job.get('title', 'Jobb')[:30] if c.isalnum() or c in (' ', '-', '_')).strip()

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
def api_stats():
    return jsonify(get_stats())


@app.route('/api/stats/detailed')
def api_stats_detailed():
    """Aggregated stats for dashboard charts."""
    try:
        processed = load_json(PROCESSED_JOBS)
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
                sf = OUTPUT_DIR / f.name / 'ats_score.json'
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
    save_scheduler_config({'enabled': enabled, 'time': t, 'days': days})
    cfg = load_scheduler_config()
    cfg['next_run_label'] = _next_run_label(cfg)
    return jsonify({'ok': True, 'next_run_label': cfg['next_run_label']})


@app.route('/api/found-jobs')
def api_found_jobs():
    """Return found_jobs.json + which have been processed"""
    found     = load_json(FOUND_JOBS)
    processed = load_json(PROCESSED_JOBS)
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

DESIGNS = {
    'design_01_minimal': {
        'key':         'design_01_minimal',
        'template':    'design_01_minimal.html',
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
        'template':    'design_02_classic.html',
        'name_sv':     'Klassisk',
        'name_en':     'Classic',
        'name_es':     'Clásico',
        'desc_sv':     'Klassisk serif-typografi med svart sidhuvud. Tidlös professionell stil.',
        'desc_en':     'Classic serif typography with black header. Timeless professional style.',
        'desc_es':     'Tipografía serif clásica con cabecera negra. Estilo profesional atemporal.',
        'tags':        [('Professionell', 'blue'), ('Tidlös', 'blue')],
    },
    'design_03_modern_green': {
        'key':         'design_03_modern_green',
        'template':    'design_03_modern_green.html',
        'name_sv':     'Modern Grön',
        'name_en':     'Modern Green',
        'name_es':     'Verde Moderno',
        'desc_sv':     'Mörk sidopanel med gröna accenter. Tech- och IT-vänlig.',
        'desc_en':     'Dark sidebar with green accents. Tech and IT-friendly.',
        'desc_es':     'Barra lateral oscura con acentos verdes. Ideal para tech e IT.',
        'tags':        [('Tech', 'green'), ('Sidopanel', 'green')],
    },
    'design_04_dark_executive': {
        'key':         'design_04_dark_executive',
        'template':    'design_04_dark_executive.html',
        'name_sv':     'Dark Executive',
        'name_en':     'Dark Executive',
        'name_es':     'Ejecutivo Oscuro',
        'desc_sv':     'Mörk premiumdesign med gulddetaljer. För ledarskapsroller.',
        'desc_en':     'Dark premium design with gold details. For leadership roles.',
        'desc_es':     'Diseño premium oscuro con detalles dorados. Para roles de liderazgo.',
        'tags':        [('Premium', 'gold'), ('Ledare', 'gold')],
    },
    'design_05_nordic_blue': {
        'key':         'design_05_nordic_blue',
        'template':    'design_05_nordic_blue.html',
        'name_sv':     'Nordic Blue',
        'name_en':     'Nordic Blue',
        'name_es':     'Azul Nórdico',
        'desc_sv':     'Skandinavisk design med blått sidhuvud och ren layout.',
        'desc_en':     'Scandinavian design with blue header and clean layout.',
        'desc_es':     'Diseño escandinavo con cabecera azul y diseño limpio.',
        'tags':        [('Skandinavisk', 'blue'), ('Ren', 'blue')],
    },
    'design_06_creative_sidebar': {
        'key':         'design_06_creative_sidebar',
        'template':    'design_06_creative_sidebar.html',
        'name_sv':     'Creative Sidebar',
        'name_en':     'Creative Sidebar',
        'name_es':     'Barra Creativa',
        'desc_sv':     'Marinblå sidopanel med teal-accenter. Kreativ och modern.',
        'desc_en':     'Navy sidebar with teal accents. Creative and modern.',
        'desc_es':     'Barra lateral azul marino con acentos turquesa. Creativo y moderno.',
        'tags':        [('Kreativ', 'teal'), ('Sidopanel', 'teal')],
    },
    'design_07_tech_modern': {
        'key':         'design_07_tech_modern',
        'template':    'design_07_tech_modern.html',
        'name_sv':     'Tech Modern',
        'name_en':     'Tech Modern',
        'name_es':     'Tech Moderno',
        'desc_sv':     'Mörkt tema med grön monospace-text. För developers och ingenjörer.',
        'desc_en':     'Dark theme with green monospace text. For developers and engineers.',
        'desc_es':     'Tema oscuro con texto monospace verde. Para desarrolladores e ingenieros.',
        'tags':        [('Developer', 'green'), ('Dark Mode', 'green')],
    },
    'design_08_timeline': {
        'key':         'design_08_timeline',
        'template':    'design_08_timeline.html',
        'name_sv':     'Timeline',
        'name_en':     'Timeline',
        'name_es':     'Línea de Tiempo',
        'desc_sv':     'Lila tidslinje-design med kortlayout. Visuell och strukturerad.',
        'desc_en':     'Purple timeline design with card layout. Visual and structured.',
        'desc_es':     'Diseño de línea de tiempo morada con tarjetas. Visual y estructurado.',
        'tags':        [('Visuell', 'purple'), ('Tidslinje', 'purple')],
    },
    'design_09_infographic': {
        'key':         'design_09_infographic',
        'template':    'design_09_infographic.html',
        'name_sv':     'Infografik',
        'name_en':     'Infographic',
        'name_es':     'Infografía',
        'desc_sv':     'Gradientsidhuvud med kompetensgrafer. Kreativ och datadriven.',
        'desc_en':     'Gradient header with skill bars. Creative and data-driven.',
        'desc_es':     'Cabecera con degradado y barras de habilidades. Creativo y orientado a datos.',
        'tags':        [('Infografik', 'orange'), ('Kompetenser', 'orange')],
    },
    'design_10_premium_gold': {
        'key':         'design_10_premium_gold',
        'template':    'design_10_premium_gold.html',
        'name_sv':     'Premium Gold',
        'name_en':     'Premium Gold',
        'name_es':     'Oro Premium',
        'desc_sv':     'Elfenbensvit med gulddetaljer och elegant serif-typografi.',
        'desc_en':     'Ivory white with gold details and elegant serif typography.',
        'desc_es':     'Blanco marfil con detalles dorados y elegante tipografía serif.',
        'tags':        [('Lyx', 'gold'), ('Elegant', 'gold')],
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
    if design in DESIGNS:
        write_env({'CV_DESIGN': design})
        flash(g.t.get('design_saved', 'Design saved!'), 'success')
    return redirect(url_for('design_page'))


@app.route('/preview/pdf/<design_key>')
def preview_design_pdf(design_key):
    """Return the HTML template file for full preview"""
    info = DESIGNS.get(design_key)
    if info and info.get('template'):
        tmpl = BASE_DIR / 'static' / 'design_templates' / info['template']
        if tmpl.exists():
            return send_file(str(tmpl.resolve()), mimetype='text/html')
    return 'Ingen förhandsgranskning tillgänglig', 404


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
    resume = load_yaml(RESUME_YAML)
    env    = read_env()
    api_key = env.get('OPENAI_API_KEY') or env.get('ANTHROPIC_API_KEY') or env.get('GOOGLE_API_KEY', '')

    if not api_key and env.get('LLM_PROVIDER') != 'ollama':
        # No AI — just store as professional summary
        resume['professional_summary'] = cv_text[:2000]
        save_yaml(RESUME_YAML, resume)
        return

    try:
        from src.libs.resume_and_cover_builder.llm.llm_factory import get_llm
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm    = get_llm(temperature=0.2)
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

    save_yaml(RESUME_YAML, resume)


@app.route('/setup/save-cover-letter', methods=['POST'])
def setup_save_cover_letter_route():
    content = request.form.get('content', '').strip()
    if content:
        COVER_LETTER.write_text(content, encoding='utf-8')
        resume = load_yaml(RESUME_YAML)
        resume['cover_letter_profile'] = request.form.get('profile', '')
        save_yaml(RESUME_YAML, resume)
    flash('Personligt brev sparat! Setup klar.', 'success')
    return redirect(url_for('index'))


# ============================================================
# ROUTES — MODEL SETTINGS (standalone page)
# ============================================================

@app.route('/settings')
def settings():
    from src.libs.resume_and_cover_builder.llm.llm_factory import AVAILABLE_MODELS, PROVIDER_INFO
    env           = read_env()
    model_cfg     = get_current_model_config()
    scheduler_cfg = load_scheduler_config()
    scheduler_cfg['next_run_label'] = _next_run_label(scheduler_cfg)
    return render_template('settings.html',
                           env=env,
                           model_cfg=model_cfg,
                           available_models=AVAILABLE_MODELS,
                           provider_info=PROVIDER_INFO,
                           scheduler_cfg=scheduler_cfg)


@app.route('/settings/save', methods=['POST'])
def settings_save():
    provider = request.form.get('provider', 'openai')
    model    = request.form.get('model', 'gpt-4o-mini')
    api_key  = request.form.get('api_key', '').strip()

    updates  = {'LLM_PROVIDER': provider, 'LLM_MODEL': model}
    key_map  = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY', 'google': 'GOOGLE_API_KEY'}
    if provider in key_map and api_key:
        updates[key_map[provider]] = api_key

    linkedin_email    = request.form.get('linkedin_email', '').strip()
    linkedin_password = request.form.get('linkedin_password', '').strip()
    if linkedin_email:
        updates['LINKEDIN_EMAIL'] = linkedin_email
    if linkedin_password:
        updates['LINKEDIN_PASSWORD'] = linkedin_password

    write_env(updates)
    flash('Inställningar sparade!', 'success')
    return redirect(url_for('settings'))


# ============================================================
# ROUTES — ATS SCORE
# ============================================================

def _build_ats_prompt(cv_text: str, job_description: str, job_title: str, company: str) -> str:
    return f"""Du är en expert på rekrytering och ATS-system (Applicant Tracking Systems).
Analysera hur väl följande CV matchar jobbeskrivningen.

JOBBTITEL: {job_title}
FÖRETAG: {company}

JOBBESKRIVNING:
{job_description[:3000]}

CV-SAMMANFATTNING:
{cv_text[:3000]}

Svara ENDAST med ett JSON-objekt i detta exakta format (inga kommentarer, ingen markdown):
{{
  "score": <heltal 0-100>,
  "matched_skills": [<lista med kompetenser som matchar, max 8>],
  "missing_skills": [<lista med kompetenser som saknas, max 6>],
  "recommendations": [<2-4 konkreta förbättringsförslag på svenska>],
  "summary": "<1-2 meningar sammanfattning på svenska>"
}}"""


def _get_cv_text() -> str:
    """Extract plain text summary from resume YAML for ATS analysis"""
    resume = load_yaml(RESUME_YAML)
    parts = []
    pi = resume.get('personal_information', {})
    if pi.get('name'):
        parts.append(f"Namn: {pi.get('name','')} {pi.get('surname','')}")
    if resume.get('professional_summary'):
        parts.append(f"Sammanfattning: {resume['professional_summary']}")

    # technical_skills är en dict med undernycklar (software, operating_systems, etc.)
    tech = resume.get('technical_skills', {})
    all_skills = []
    if isinstance(tech, dict):
        for v in tech.values():
            if isinstance(v, list):
                all_skills.extend(v)
    if all_skills:
        parts.append(f"Tekniska kompetenser: {', '.join(str(s) for s in all_skills)}")

    # experience_details (inte work_experience)
    for exp in resume.get('experience_details', [])[:5]:
        if isinstance(exp, dict):
            pos = exp.get('position', '')
            comp = exp.get('company', '')
            period = exp.get('employment_period', '')
            parts.append(f"Erfarenhet: {pos} på {comp} ({period})")
            # Inkludera nyckelansvar och tekniker
            for resp in exp.get('key_responsibilities', [])[:3]:
                if isinstance(resp, dict):
                    parts.append(f"  - {resp.get('responsibility', '')}")
                elif isinstance(resp, str):
                    parts.append(f"  - {resp}")
            skills_acq = exp.get('skills_acquired', [])
            if skills_acq:
                parts.append(f"  Tekniker: {', '.join(str(s) for s in skills_acq[:8])}")

    # education_details (inte education)
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


@app.route('/api/ats-score/generate', methods=['POST'])
def api_ats_generate():
    """Generate ATS score for a job folder using LLM"""
    data   = request.get_json(silent=True) or {}
    folder = data.get('folder', '').strip()

    if not folder:
        return jsonify({'ok': False, 'error': 'folder required'}), 400

    job_folder = OUTPUT_DIR / folder
    if not job_folder.exists():
        return jsonify({'ok': False, 'error': 'Mappen finns inte'}), 404

    # Check cache first (unless force regenerate)
    score_file = job_folder / 'ats_score.json'
    if score_file.exists() and not data.get('force'):
        try:
            return jsonify({'ok': True, **json.loads(score_file.read_text(encoding='utf-8'))})
        except Exception:
            pass

    # Load job description
    desc_file = job_folder / 'job_description.txt'
    if desc_file.exists():
        job_description = desc_file.read_text(encoding='utf-8').strip()
    else:
        job_description = ''

    # Parse job metadata
    job = parse_job_folder(job_folder)
    job_title = job.get('title', '')
    company   = job.get('company', '')

    if not job_description:
        # No description saved — return a placeholder encouraging future use
        return jsonify({
            'ok': False,
            'error': 'Ingen jobbeskrivning sparad för detta jobb. Kommande jobb sparas automatiskt.',
            'no_description': True
        }), 422

    # Build CV text
    cv_text = _get_cv_text()
    if not cv_text:
        return jsonify({'ok': False, 'error': 'CV saknas — fyll i ditt CV först'}), 422

    # Call LLM
    try:
        from src.libs.resume_and_cover_builder.llm.llm_factory import get_llm
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm    = get_llm(temperature=0.1)
        prompt = ChatPromptTemplate.from_messages([
            ("human", "{prompt}")
        ])
        chain  = prompt | llm | StrOutputParser()
        raw    = chain.invoke({'prompt': _build_ats_prompt(cv_text, job_description, job_title, company)})

        # Strip markdown fences if present
        raw = re.sub(r'^```(?:json)?', '', raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r'```$', '', raw.strip(), flags=re.MULTILINE)
        result = json.loads(raw.strip())

        # Validate and clamp score
        result['score'] = max(0, min(100, int(result.get('score', 0))))
        result['folder'] = folder

        # Cache result
        score_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

        return jsonify({'ok': True, **result})

    except json.JSONDecodeError as e:
        return jsonify({'ok': False, 'error': f'AI svarade i fel format: {e}'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/ats-score/<folder>')
def api_ats_get(folder):
    """Return cached ATS score for a folder"""
    score_file = OUTPUT_DIR / folder / 'ats_score.json'
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
