"""
LLM Factory — väljer rätt AI-modell baserat på miljövariabler.

Stödda leverantörer:
  openai    → OpenAI (gpt-4o-mini, gpt-4o, gpt-4-turbo, ...)
  anthropic → Anthropic Claude (claude-3-5-sonnet-*, claude-3-haiku-*, ...)
  google    → Google Gemini (gemini-1.5-pro, gemini-1.5-flash, ...)
  ollama    → Ollama lokalt (llama3, mistral, ...)

Konfigurera via .env:
  LLM_PROVIDER=openai
  LLM_MODEL=gpt-4o-mini
"""

import os
import threading
from dotenv import load_dotenv
from src.libs.resume_and_cover_builder.utils import LoggerChatModel

load_dotenv()

# Thread-local: per-user LLM-kontext sätts av web_app innan LLM-anrop
# Alla get_llm()-anrop (inklusive från src/-moduler) läser härifrån
_user_llm_context = threading.local()


def set_user_llm_context(api_key: str, provider: str = '', model: str = ''):
    """Sätts av web_app i request-kontexten eller söktrådarna."""
    _user_llm_context.api_key  = api_key
    _user_llm_context.provider = provider
    _user_llm_context.model    = model


def clear_user_llm_context():
    """Nollställ efter anropet."""
    _user_llm_context.api_key  = ''
    _user_llm_context.provider = ''
    _user_llm_context.model    = ''


def has_user_llm_context() -> bool:
    """True om en per-user LLM-kontext är satt i denna tråd.
    Ollama har ingen nyckel — då räcker provider."""
    return bool(getattr(_user_llm_context, 'api_key', '') or
                getattr(_user_llm_context, 'provider', ''))


def get_context_openai_key(fallback: str = '') -> str:
    """Nyckel som får användas för OpenAI-EMBEDDINGS (FAISS-vektorsökning).

    Embeddings finns bara hos OpenAI. Med användarkontext satt: returnera
    användarens egen nyckel om hens provider är openai, annars '' (embeddings
    hoppas över — parsern fungerar utan). ALDRIG serverns env-nyckel för
    inloggade användare — annars debiteras admins konto för t.ex.
    Gemini-användares jobbparsning. Fallback är för desktop-läget utan kontext."""
    if has_user_llm_context():
        provider = (getattr(_user_llm_context, 'provider', '') or '').lower()
        key = getattr(_user_llm_context, 'api_key', '')
        return key if (provider == 'openai' and key) else ''
    return fallback

# ── Tillgängliga modeller per leverantör ─────────────────────────────────────
AVAILABLE_MODELS = {
    'openai': [
        {'id': 'gpt-4o-mini',      'label': 'GPT-4o Mini (snabb & billig)',    'recommended': True},
        {'id': 'gpt-4o',           'label': 'GPT-4o (kraftfull)',               'recommended': False},
        {'id': 'gpt-4-turbo',      'label': 'GPT-4 Turbo',                      'recommended': False},
        {'id': 'gpt-3.5-turbo',    'label': 'GPT-3.5 Turbo (billigast)',        'recommended': False},
    ],
    'anthropic': [
        {'id': 'claude-3-5-sonnet-20241022', 'label': 'Claude 3.5 Sonnet (bäst)',      'recommended': True},
        {'id': 'claude-3-5-haiku-20241022',  'label': 'Claude 3.5 Haiku (snabb)',      'recommended': False},
        {'id': 'claude-3-opus-20240229',     'label': 'Claude 3 Opus (kraftfullast)',  'recommended': False},
    ],
    'google': [
        {'id': 'gemini-1.5-flash', 'label': 'Gemini 1.5 Flash (snabb & gratis)',  'recommended': True},
        {'id': 'gemini-1.5-pro',   'label': 'Gemini 1.5 Pro (kraftfull)',          'recommended': False},
        {'id': 'gemini-2.0-flash', 'label': 'Gemini 2.0 Flash',                    'recommended': False},
    ],
    'ollama': [
        {'id': 'llama3.2',    'label': 'Llama 3.2 (lokalt, gratis)',    'recommended': True},
        {'id': 'mistral',     'label': 'Mistral (lokalt, gratis)',       'recommended': False},
        {'id': 'llama3.1',    'label': 'Llama 3.1 (lokalt, gratis)',     'recommended': False},
        {'id': 'phi4',        'label': 'Phi-4 (lokalt, litet)',          'recommended': False},
    ],
}

PROVIDER_INFO = {
    'openai': {
        'label':       'OpenAI',
        'icon':        '🟢',
        'env_key':     'OPENAI_API_KEY',
        'key_url':     'https://platform.openai.com/api-keys',
        'free':        False,
        'description': 'Bäst tillgänglighet och kvalitet. Kräver kreditkort.',
    },
    'anthropic': {
        'label':       'Anthropic (Claude)',
        'icon':        '🟠',
        'env_key':     'ANTHROPIC_API_KEY',
        'key_url':     'https://console.anthropic.com/',
        'free':        False,
        'description': 'Utmärkt för text och kreativt skrivande.',
    },
    'google': {
        'label':       'Google (Gemini)',
        'icon':        '🔵',
        'env_key':     'GOOGLE_API_KEY',
        'key_url':     'https://aistudio.google.com/app/apikey',
        'free':        True,
        'description': 'Gratis tier tillgänglig. Bra för de flesta uppgifter.',
    },
    'ollama': {
        'label':       'Ollama (lokalt)',
        'icon':        '🟣',
        'env_key':     None,
        'key_url':     'https://ollama.com/',
        'free':        True,
        'description': 'Kör AI lokalt — helt gratis, ingen API-nyckel.',
    },
}


def get_provider() -> str:
    return os.environ.get('LLM_PROVIDER', 'openai').lower()


def get_model_name() -> str:
    provider = get_provider()
    defaults = {
        'openai':    'gpt-4o-mini',
        'anthropic': 'claude-3-5-sonnet-20241022',
        'google':    'gemini-1.5-flash',
        'ollama':    'llama3.2',
    }
    return os.environ.get('LLM_MODEL', defaults.get(provider, 'gpt-4o-mini'))


def create_chat_model(temperature: float = 0.4, timeout: int = 60,
                      api_key: str = '', provider: str = '', model: str = ''):
    """
    Skapar och returnerar rätt rå LangChain-chatmodell (utan LoggerChatModel-wrapper).

    Prioritetsordning för konfiguration:
      1. Explicit api_key/provider/model (skickas direkt)
      2. Thread-local context (sätts av web_app för inloggad användare)
      3. Miljövariabler (.env.production)
    """
    ctx_key      = getattr(_user_llm_context, 'api_key',  '')
    ctx_provider = getattr(_user_llm_context, 'provider', '')
    ctx_model    = getattr(_user_llm_context, 'model',    '')

    _provider = (provider or ctx_provider or get_provider()).lower()
    _model    = model or ctx_model or get_model_name()

    def _key(env_var: str) -> str:
        return api_key or ctx_key or os.environ.get(env_var, '')

    try:
        if _provider == 'openai':
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model_name     = _model,
                openai_api_key = _key('OPENAI_API_KEY'),
                temperature    = temperature,
                timeout        = timeout,
            )

        elif _provider == 'anthropic':
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model             = _model,
                anthropic_api_key = _key('ANTHROPIC_API_KEY'),
                temperature       = temperature,
                timeout           = timeout,
                max_tokens        = 4096,
            )

        elif _provider == 'google':
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model          = _model,
                google_api_key = _key('GOOGLE_API_KEY'),
                temperature    = temperature,
            )

        elif _provider == 'ollama':
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model       = _model,
                temperature = temperature,
            )

        else:
            raise ValueError(f"Okänd leverantör: {_provider}")

    except ValueError:
        raise  # Okänd leverantör eller valideringsfel — propagera, inte swälj
    except Exception:
        # Fallback till OpenAI vid oväntade fel (fel modellnamn, nätverksfel etc.)
        from langchain_openai import ChatOpenAI
        fallback_key = api_key or ctx_key or os.environ.get('OPENAI_API_KEY', '')
        if not fallback_key:
            raise ValueError(
                "API-nyckel saknas. Gå till Inställningar och konfigurera din LLM-leverantör."
            )
        return ChatOpenAI(
            model_name     = 'gpt-4o-mini',
            openai_api_key = fallback_key,
            temperature    = temperature,
            timeout        = timeout,
        )


def get_llm(temperature: float = 0.4, timeout: int = 60,
            api_key: str = '', provider: str = '', model: str = ''):
    """Som create_chat_model() men wrappad i LoggerChatModel (retry + loggning)."""
    return LoggerChatModel(create_chat_model(
        temperature=temperature, timeout=timeout,
        api_key=api_key, provider=provider, model=model,
    ))
