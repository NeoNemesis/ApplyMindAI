#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ApplyMind AI — Webbgränssnitt
============================
Flask-baserat webbgränssnitt för ApplyMind AI jobbsökningssystem.

Starta: python web_app.py
URL:    http://localhost:5000
"""

import os
import sys
import re
import json
import yaml
import shutil
import threading
import queue
from pathlib import Path
from datetime import datetime
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
    cv_file     = next((f for f in files if f.name.startswith('CV_') and f.suffix == '.pdf'), None)
    letter_file = next((f for f in files if f.name.startswith('Personligt_Brev') and f.suffix == '.pdf'), None)

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
            elif 'Indeed URL:' in line:
                info['url'] = line.split('Indeed URL:', 1)[1].strip()
            elif 'LinkedIn URL:' in line and not info.get('url'):
                info['url'] = line.split('LinkedIn URL:', 1)[1].strip()
            elif 'Hittad:' in line:
                info['date'] = line.split('Hittad:', 1)[1].strip()

    if not info.get('title'):
        parts = folder.name.split('_', 3)
        info['company'] = parts[2] if len(parts) > 2 else ''
        info['title']   = parts[3] if len(parts) > 3 else folder.name

    return {
        'folder':      folder.name,
        'title':       info.get('title', folder.name),
        'company':     info.get('company', ''),
        'location':    info.get('location', ''),
        'url':         info.get('url', ''),
        'date':        info.get('date', '')[:10] if info.get('date') else '',
        'cv_file':     cv_file.name     if cv_file     else None,
        'letter_file': letter_file.name if letter_file else None,
        'has_letter':  letter_file is not None,
        'has_cv':      cv_file is not None,
    }


def get_stats():
    """Get application statistics"""
    processed   = load_json(PROCESSED_JOBS)
    openai_data = load_json(OPENAI_CALLS) if OPENAI_CALLS.exists() else {}
    folders     = get_job_folders()

    jobs_with_letter = sum(
        1 for f in folders
        if any(p.name.startswith('Personligt_Brev') for p in f.iterdir() if p.is_file())
    )

    if isinstance(openai_data, dict):
        total_cost  = openai_data.get('total_cost', 0)
        total_calls = openai_data.get('total_calls', 0)
    else:
        total_cost  = 0
        total_calls = 0

    return {
        'total_folders':     len(folders),
        'total_processed':   len(processed),
        'jobs_with_letter':  jobs_with_letter,
        'total_cost':        round(total_cost, 2),
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
    stats       = get_stats()
    folders     = get_job_folders()
    recent_jobs = [parse_job_folder(f) for f in folders[:8]]
    model_cfg   = get_current_model_config()
    return render_template('index.html', stats=stats, recent_jobs=recent_jobs,
                           search_running=search_state['running'],
                           model_cfg=model_cfg)


# ============================================================
# ROUTES — CV EDITOR
# ============================================================

@app.route('/cv')
def cv_editor():
    resume = load_yaml(RESUME_YAML)
    return render_template('cv.html', resume=resume)


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
        global search_state
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        class OutputCapture:
            """Capture stdout/stderr and push to SSE queue"""
            encoding = 'utf-8'

            def write(self, text):
                if text and text.strip():
                    search_queue.put(('output', text))
                old_stdout.write(text)

            def flush(self):
                old_stdout.flush()

            def reconfigure(self, **kwargs):
                pass  # called by job_master on Windows — safe to ignore

        # Import BEFORE replacing stdout so module-level code runs on real stdout
        from job_master import JobMaster

        try:
            sys.stdout = OutputCapture()
            sys.stderr = OutputCapture()
            jm = JobMaster()
            jm.initialize()

            search_queue.put(('output', f'\n🔍 Plattformar: {", ".join(platforms)}\n'))
            search_queue.put(('output', f'📍 Platser: {", ".join(locations)}\n'))
            search_queue.put(('output', f'🎯 Max jobb: {max_jobs}\n\n'))

            jobs = jm.search_jobs(platforms, max_jobs, locations=locations, positions=positions)

            if jobs:
                search_queue.put(('output', f'\n✅ Hittade {len(jobs)} jobb!\n'))
                search_queue.put(('output', '\n📝 Genererar CV och personliga brev...\n'))
                successful = 0
                for i, job in enumerate(jobs, 1):
                    search_queue.put(('progress', f'{i}/{len(jobs)}'))
                    search_queue.put(('output', f'\n[{i}/{len(jobs)}] 📄 {job["title"]} @ {job["company"]}\n'))
                    ok = jm.generate_documents_for_job(job, i)
                    if ok:
                        successful += 1
                        search_queue.put(('output', '   ✅ Klar!\n'))
                    else:
                        search_queue.put(('output', '   ❌ Misslyckades\n'))
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


@app.route('/search/status')
def search_status():
    return jsonify(search_state)


# ============================================================
# ROUTES — JOBS LIST
# ============================================================

@app.route('/jobs')
def jobs():
    folders  = get_job_folders()
    job_list = [parse_job_folder(f) for f in folders]
    return render_template('jobs.html', jobs=job_list)


@app.route('/download/<folder>/<filename>')
def download_file(folder, filename):
    """Download a PDF document"""
    file_path = OUTPUT_DIR / folder / filename
    if file_path.exists() and file_path.suffix == '.pdf':
        return send_file(str(file_path.resolve()), as_attachment=True,
                         download_name=filename)
    return 'Filen hittades inte', 404


@app.route('/view/<folder>/<filename>')
def view_pdf(folder, filename):
    """View a PDF in browser"""
    file_path = OUTPUT_DIR / folder / filename
    if file_path.exists() and file_path.suffix == '.pdf':
        return send_file(str(file_path.resolve()), mimetype='application/pdf')
    return 'Filen hittades inte', 404


@app.route('/api/jobs')
def api_jobs():
    """JSON API for jobs list"""
    folders  = get_job_folders()
    job_list = [parse_job_folder(f) for f in folders]
    return jsonify(job_list)


@app.route('/api/stats')
def api_stats():
    return jsonify(get_stats())


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
    env        = read_env()
    model_cfg  = get_current_model_config()
    return render_template('settings.html',
                           env=env,
                           model_cfg=model_cfg,
                           available_models=AVAILABLE_MODELS,
                           provider_info=PROVIDER_INFO)


@app.route('/settings/save', methods=['POST'])
def settings_save():
    provider = request.form.get('provider', 'openai')
    model    = request.form.get('model', 'gpt-4o-mini')
    api_key  = request.form.get('api_key', '').strip()

    updates  = {'LLM_PROVIDER': provider, 'LLM_MODEL': model}
    key_map  = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY', 'google': 'GOOGLE_API_KEY'}
    if provider in key_map and api_key:
        updates[key_map[provider]] = api_key

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
    skills = resume.get('skills', [])
    if skills:
        parts.append(f"Kompetenser: {', '.join(str(s) for s in skills[:30])}")
    for exp in resume.get('work_experience', [])[:4]:
        if isinstance(exp, dict):
            parts.append(f"Erfarenhet: {exp.get('position','')} på {exp.get('company','')} ({exp.get('period','')})")
    for edu in resume.get('education', [])[:3]:
        if isinstance(edu, dict):
            parts.append(f"Utbildning: {edu.get('degree','')} vid {edu.get('institution','')} ({edu.get('period','')})")
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
    ('applied',   'Sökt',        'bi-send',             'col-applied'),
    ('response',  'Svar',        'bi-chat-dots',        'col-response'),
    ('interview', 'Intervju',    'bi-person-lines-fill','col-interview'),
    ('offer',     'Erbjudande',  'bi-trophy',           'col-offer'),
    ('rejected',  'Avslag',      'bi-x-circle',         'col-rejected'),
]


@app.route('/tracker')
def tracker():
    folders   = get_job_folders()
    all_jobs  = [parse_job_folder(f) for f in folders]
    tracker   = load_tracker()

    # Assign default status 'applied' to jobs without a tracker entry
    for job in all_jobs:
        if job['folder'] not in tracker:
            tracker[job['folder']] = {'status': 'applied', 'notes': '', 'updated': job.get('date', '')}
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
