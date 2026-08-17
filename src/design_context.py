"""
Per-user design-kontext för CV-/brevgenerering.

Designvalet lagras per användare i databasen (User.cv_design /
User.letter_template) men själva generatorerna (improved_generator,
cover_letter_generator, job_master) körs djupt nere i trådar utan
Flask-kontext. Samma mönster som llm_factory: web_app sätter kontexten
i request-/söktråden, generatorerna läser härifrån.

Fallback-kedja: thread-local → env (CV_DESIGN/LETTER_TEMPLATE) → default.
Env-fallbacken behåller gammalt beteende för desktop-läget och för
användare som aldrig valt något.
"""

import os
import threading

_ctx = threading.local()


def set_design_context(cv_design: str | None, letter_template: str | None) -> None:
    """Sätts av web_app i request-kontexten eller i sök-/schemaläggartrådar."""
    _ctx.cv_design = cv_design or None
    _ctx.letter_template = letter_template or None


def clear_design_context() -> None:
    _ctx.cv_design = None
    _ctx.letter_template = None


def get_cv_design(default: str = 'design_02_classic') -> str:
    chosen = getattr(_ctx, 'cv_design', None)
    if chosen:
        return chosen
    return os.getenv('CV_DESIGN', default)


def get_letter_template(default: str = 'nordic_minimal') -> str:
    chosen = getattr(_ctx, 'letter_template', None)
    if chosen:
        return chosen
    return os.getenv('LETTER_TEMPLATE', default)
