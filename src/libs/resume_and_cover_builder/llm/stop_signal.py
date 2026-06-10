"""
Trådlokal stoppsignal för LLM-anrop.

Problem: när användaren klickar Stopp sätts en flagga som sökloopen kollar
MELLAN jobb — men ett pågående LLM-anrop ligger i en retry-loop (flera
försök × 60s timeout + paus) som inte känner till flaggan. Resultatet är
att UI:t "snurrar" i många minuter efter stopp.

Lösning: web_app registrerar en stop-check-funktion i söktråden (samma
mönster som thread-local LLM-kontexten i llm_factory). Retry-looparna i
LoggerChatModel och IsolatedLoggerChatModel kollar den mellan försök och
avbryter direkt.

Modulen har medvetet INGA projektberoenden — den importeras av både
utils.py och isolated_utils.py som annars skulle bilda cirkulära importer.
"""

import threading

_ctx = threading.local()


class SearchStopped(Exception):
    """Användaren stoppade sökningen — avbryt pågående LLM-arbete."""


def set_stop_check(fn) -> None:
    """Registrera en callable som returnerar True när användaren stoppat.
    Anropas av web_app i början av varje sök-/utvärderingstråd."""
    _ctx.check = fn


def clear_stop_check() -> None:
    _ctx.check = None


def stop_requested() -> bool:
    fn = getattr(_ctx, 'check', None)
    if fn is None:
        return False
    try:
        return bool(fn())
    except Exception:
        return False


def raise_if_stopped() -> None:
    if stop_requested():
        raise SearchStopped("Stoppad av användaren")
