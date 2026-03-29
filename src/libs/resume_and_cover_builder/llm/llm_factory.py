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
from dotenv import load_dotenv
from src.libs.resume_and_cover_builder.utils import LoggerChatModel

load_dotenv()

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


def get_llm(temperature: float = 0.4, timeout: int = 60):
    """
    Skapar och returnerar rätt LLM baserat på LLM_PROVIDER och LLM_MODEL i .env.
    Faller tillbaka på OpenAI om leverantören inte stöds.
    """
    provider   = get_provider()
    model_name = get_model_name()

    try:
        if provider == 'openai':
            from langchain_openai import ChatOpenAI
            api_key = os.environ.get('OPENAI_API_KEY', '')
            return LoggerChatModel(ChatOpenAI(
                model_name    = model_name,
                openai_api_key= api_key,
                temperature   = temperature,
                timeout       = timeout,
            ))

        elif provider == 'anthropic':
            from langchain_anthropic import ChatAnthropic
            api_key = os.environ.get('ANTHROPIC_API_KEY', '')
            return LoggerChatModel(ChatAnthropic(
                model       = model_name,
                anthropic_api_key = api_key,
                temperature = temperature,
                timeout     = timeout,
                max_tokens  = 4096,
            ))

        elif provider == 'google':
            from langchain_google_genai import ChatGoogleGenerativeAI
            api_key = os.environ.get('GOOGLE_API_KEY', '')
            return LoggerChatModel(ChatGoogleGenerativeAI(
                model       = model_name,
                google_api_key = api_key,
                temperature = temperature,
            ))

        elif provider == 'ollama':
            from langchain_ollama import ChatOllama
            return LoggerChatModel(ChatOllama(
                model       = model_name,
                temperature = temperature,
            ))

        else:
            raise ValueError(f"Okänd leverantör: {provider}")

    except Exception as e:
        # Fallback to OpenAI
        from langchain_openai import ChatOpenAI
        api_key = os.environ.get('OPENAI_API_KEY', '')
        return LoggerChatModel(ChatOpenAI(
            model_name     = 'gpt-4o-mini',
            openai_api_key = api_key,
            temperature    = temperature,
            timeout        = timeout,
        ))
