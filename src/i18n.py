"""
ApplyMind AI — Translations (SV / EN / ES)
"""

TRANSLATIONS = {

    # ── Navigation ──────────────────────────────────────────────
    'nav_dashboard':      {'sv': 'Dashboard',         'en': 'Dashboard',        'es': 'Panel'},
    'nav_my_cv':          {'sv': 'Mitt CV',            'en': 'My CV',            'es': 'Mi CV'},
    'nav_cover_letter':   {'sv': 'Personligt Brev',   'en': 'Cover Letter',     'es': 'Carta de Presentación'},
    'nav_search':         {'sv': 'Sök Jobb',           'en': 'Search Jobs',      'es': 'Buscar Empleo'},
    'nav_applications':   {'sv': 'Mina Ansökningar',  'en': 'My Applications',  'es': 'Mis Solicitudes'},
    'nav_settings':       {'sv': 'AI-inställningar',  'en': 'AI Settings',      'es': 'Configuración IA'},
    'nav_setup':          {'sv': 'Setup-guide',        'en': 'Setup Guide',      'es': 'Guía de Inicio'},
    'nav_design':         {'sv': 'CV-design',          'en': 'CV Design',        'es': 'Diseño de CV'},

    # ── Dashboard ────────────────────────────────────────────────
    'dash_total':         {'sv': 'Ansökningar totalt',     'en': 'Total Applications',  'es': 'Solicitudes Totales'},
    'dash_with_letter':   {'sv': 'Med personligt brev',    'en': 'With Cover Letter',   'es': 'Con Carta'},
    'dash_ai_calls':      {'sv': 'AI-anrop',               'en': 'AI Calls',            'es': 'Llamadas IA'},
    'dash_ai_cost':       {'sv': 'AI-kostnad totalt',      'en': 'Total AI Cost',       'es': 'Costo Total IA'},
    'dash_quickstart':    {'sv': 'Snabbstart',              'en': 'Quick Start',         'es': 'Inicio Rápido'},
    'dash_search_new':    {'sv': 'Sök nya jobb',           'en': 'Search New Jobs',     'es': 'Buscar Nuevos Empleos'},
    'dash_edit_cv':       {'sv': 'Redigera CV',            'en': 'Edit CV',             'es': 'Editar CV'},
    'dash_edit_letter':   {'sv': 'Redigera personligt brev','en': 'Edit Cover Letter',  'es': 'Editar Carta'},
    'dash_all_apps':      {'sv': 'Visa alla ansökningar',  'en': 'View All Applications','es': 'Ver Todas'},
    'dash_recent':        {'sv': 'Senaste ansökningar',    'en': 'Recent Applications', 'es': 'Solicitudes Recientes'},
    'dash_view_all':      {'sv': 'Visa alla',              'en': 'View All',            'es': 'Ver Todo'},
    'dash_no_apps':       {'sv': 'Inga ansökningar ännu.', 'en': 'No applications yet.','es': 'Sin solicitudes aún.'},
    'dash_start_search':  {'sv': 'Sök ditt första jobb!', 'en': 'Search your first job!','es': '¡Busca tu primer empleo!'},

    # ── CV Editor ────────────────────────────────────────────────
    'cv_editor':          {'sv': 'CV-editor',             'en': 'CV Editor',           'es': 'Editor de CV'},
    'cv_save':            {'sv': 'Spara CV',              'en': 'Save CV',             'es': 'Guardar CV'},
    'cv_personal':        {'sv': 'Personlig information', 'en': 'Personal Information','es': 'Información Personal'},
    'cv_summary':         {'sv': 'Professionell sammanfattning','en': 'Professional Summary','es': 'Resumen Profesional'},
    'cv_ai_profile':      {'sv': 'AI-profil för personliga brev','en': 'AI Profile for Cover Letters','es': 'Perfil IA para Cartas'},
    'cv_experience':      {'sv': 'Arbetslivserfarenhet',  'en': 'Work Experience',     'es': 'Experiencia Laboral'},
    'cv_education':       {'sv': 'Utbildning',            'en': 'Education',           'es': 'Educación'},
    'cv_skills':          {'sv': 'Tekniska kompetenser',  'en': 'Technical Skills',    'es': 'Habilidades Técnicas'},
    'cv_languages':       {'sv': 'Språk',                 'en': 'Languages',           'es': 'Idiomas'},
    'cv_add':             {'sv': 'Lägg till',             'en': 'Add',                 'es': 'Agregar'},
    'cv_remove':          {'sv': '✕ Ta bort',             'en': '✕ Remove',            'es': '✕ Eliminar'},
    'cv_saved':           {'sv': 'CV sparat!',            'en': 'CV saved!',           'es': '¡CV guardado!'},

    # ── Cover Letter ─────────────────────────────────────────────
    'cl_editor':          {'sv': 'Personligt brev-editor','en': 'Cover Letter Editor', 'es': 'Editor de Carta'},
    'cl_save':            {'sv': 'Spara',                 'en': 'Save',               'es': 'Guardar'},
    'cl_template':        {'sv': 'Brevmall',              'en': 'Letter Template',     'es': 'Plantilla de Carta'},
    'cl_ai_profile':      {'sv': 'AI-profil',             'en': 'AI Profile',          'es': 'Perfil IA'},
    'cl_saved':           {'sv': 'Personligt brev sparat!','en': 'Cover letter saved!','es': '¡Carta guardada!'},

    # ── Search ───────────────────────────────────────────────────
    'search_platforms':   {'sv': 'Jobbplattformar',       'en': 'Job Platforms',       'es': 'Plataformas de Empleo'},
    'search_locations':   {'sv': 'Sökplatser',            'en': 'Search Locations',    'es': 'Ubicaciones'},
    'search_positions':   {'sv': 'Jobbtitlar / sökord',  'en': 'Job Titles / Keywords','es': 'Títulos / Palabras Clave'},
    'search_worktype':    {'sv': 'Arbetsform',            'en': 'Work Type',           'es': 'Tipo de Trabajo'},
    'search_remote':      {'sv': 'Distans',               'en': 'Remote',              'es': 'Remoto'},
    'search_hybrid':      {'sv': 'Hybrid',                'en': 'Hybrid',              'es': 'Híbrido'},
    'search_onsite':      {'sv': 'På plats',              'en': 'On-site',             'es': 'Presencial'},
    'search_count':       {'sv': 'Antal jobb',            'en': 'Number of Jobs',      'es': 'Número de Empleos'},
    'search_start':       {'sv': 'Starta Sökning',        'en': 'Start Search',        'es': 'Iniciar Búsqueda'},
    'search_running':     {'sv': 'Söker...',              'en': 'Searching...',        'es': 'Buscando...'},
    'search_found_jobs':  {'sv': 'Hittade jobb',          'en': 'Found Jobs',          'es': 'Empleos Encontrados'},
    'search_live_output': {'sv': 'Live output',           'en': 'Live Output',         'es': 'Salida en Vivo'},
    'search_clear':       {'sv': 'Rensa',                 'en': 'Clear',               'es': 'Limpiar'},

    # ── Jobs list ────────────────────────────────────────────────
    'jobs_title':         {'sv': 'Titel',                 'en': 'Title',               'es': 'Título'},
    'jobs_company':       {'sv': 'Företag',               'en': 'Company',             'es': 'Empresa'},
    'jobs_location':      {'sv': 'Plats',                 'en': 'Location',            'es': 'Ubicación'},
    'jobs_date':          {'sv': 'Datum',                 'en': 'Date',                'es': 'Fecha'},
    'jobs_documents':     {'sv': 'Dokument',              'en': 'Documents',           'es': 'Documentos'},
    'jobs_actions':       {'sv': 'Åtgärder',              'en': 'Actions',             'es': 'Acciones'},
    'jobs_search_more':   {'sv': 'Sök fler',              'en': 'Search More',         'es': 'Buscar Más'},
    'jobs_filter':        {'sv': 'Filtrera jobb...',      'en': 'Filter jobs...',      'es': 'Filtrar empleos...'},
    'jobs_cv_letter':     {'sv': 'CV + Brev',             'en': 'CV + Letter',         'es': 'CV + Carta'},
    'jobs_cv_only':       {'sv': 'Bara CV',               'en': 'CV Only',             'es': 'Solo CV'},
    'jobs_none':          {'sv': 'Inga ansökningar ännu', 'en': 'No applications yet', 'es': 'Sin solicitudes aún'},

    # ── Settings / Setup ─────────────────────────────────────────
    'settings_title':     {'sv': 'Inställningar',         'en': 'Settings',            'es': 'Configuración'},
    'settings_provider':  {'sv': 'AI-leverantör',         'en': 'AI Provider',         'es': 'Proveedor IA'},
    'settings_save':      {'sv': 'Spara inställningar',   'en': 'Save Settings',       'es': 'Guardar Configuración'},
    'settings_saved':     {'sv': 'Inställningar sparade!','en': 'Settings saved!',     'es': '¡Configuración guardada!'},
    'settings_active':    {'sv': 'Aktiv modell',          'en': 'Active Model',        'es': 'Modelo Activo'},
    'settings_api_key':   {'sv': 'API-nyckel',            'en': 'API Key',             'es': 'Clave API'},
    'settings_get_key':   {'sv': 'Hämta API-nyckel',      'en': 'Get API Key',         'es': 'Obtener Clave API'},

    # ── Design page ──────────────────────────────────────────────
    'design_title':       {'sv': 'CV-design',             'en': 'CV Design',           'es': 'Diseño de CV'},
    'design_select':      {'sv': 'Välj design',           'en': 'Select Design',       'es': 'Seleccionar Diseño'},
    'design_active':      {'sv': 'Aktiv',                 'en': 'Active',              'es': 'Activo'},
    'design_use':         {'sv': 'Använd denna design',   'en': 'Use This Design',     'es': 'Usar este Diseño'},
    'design_preview':     {'sv': 'Förhandsgranskning',    'en': 'Preview',             'es': 'Vista Previa'},
    'design_saved':       {'sv': 'Design sparad!',        'en': 'Design saved!',       'es': '¡Diseño guardado!'},

    # ── General ──────────────────────────────────────────────────
    'btn_save':           {'sv': 'Spara',                 'en': 'Save',               'es': 'Guardar'},
    'btn_cancel':         {'sv': 'Avbryt',                'en': 'Cancel',             'es': 'Cancelar'},
    'btn_next':           {'sv': 'Nästa',                 'en': 'Next',               'es': 'Siguiente'},
    'btn_back':           {'sv': 'Tillbaka',              'en': 'Back',               'es': 'Atrás'},
    'btn_download':       {'sv': 'Ladda ner',             'en': 'Download',           'es': 'Descargar'},
    'btn_preview':        {'sv': 'Förhandsgranskning',    'en': 'Preview',            'es': 'Vista Previa'},
    'btn_open_job':       {'sv': 'Öppna jobbannnons',     'en': 'Open Job Post',      'es': 'Ver Oferta'},
    'search_ongoing':     {'sv': 'Sökning pågår...',      'en': 'Search in progress...','es': 'Búsqueda en progreso...'},
    'lang_label':         {'sv': 'Språk',                 'en': 'Language',           'es': 'Idioma'},
}


def get_translations(lang: str = 'sv') -> dict:
    """Return flat dict of key→translated string for given lang."""
    lang = lang if lang in ('sv', 'en', 'es') else 'sv'
    return {k: v.get(lang, v.get('sv', k)) for k, v in TRANSLATIONS.items()}


LANGUAGE_NAMES = {
    'sv': '🇸🇪 Svenska',
    'en': '🇬🇧 English',
    'es': '🇪🇸 Español',
}
