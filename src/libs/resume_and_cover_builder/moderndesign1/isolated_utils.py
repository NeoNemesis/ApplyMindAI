"""
Modern Design 1 - Helt isolerade utilities
INGA global_config beroenden
"""

import time
import json
import base64
from datetime import datetime
from typing import Any
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages.ai import AIMessage
from loguru import logger

# Gemensam loggfil (samma format som LLMParser)
_CALLS_LOG = Path("data_folder/output/job_master/open_ai_calls.json")


def _log_ai_call(prompt: str, reply: str, model: str = "gpt-4o-mini") -> None:
    """Loggar AI-anrop till open_ai_calls.json."""
    try:
        _CALLS_LOG.parent.mkdir(parents=True, exist_ok=True)
        input_tokens  = len(prompt) // 4
        output_tokens = len(reply) // 4
        # gpt-4o-mini: $0.15/1M input, $0.60/1M output
        cost = (input_tokens * 0.00000015) + (output_tokens * 0.0000006)
        record = {
            "model":         model,
            "time":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type":          "cv_cover_letter",
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "total_tokens":  input_tokens + output_tokens,
            "total_cost":    round(cost, 8),
        }
        with open(_CALLS_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"⚠️ Kunde inte logga AI-anrop: {e}")


class IsolatedLoggerChatModel:
    """Isolerad ChatModel för Modern Design 1"""

    def __init__(self, chat_model: ChatOpenAI):
        self.llm = chat_model
        self.max_retries = 15
        self.retry_delay = 10

    def __call__(self, messages: Any) -> str:
        """Anropar AI med retry-logik och loggar anropet."""
        prompt_text = messages if isinstance(messages, str) else str(messages)
        for attempt in range(self.max_retries):
            try:
                logger.info(f"🤖 Modern Design 1: AI-anrop (försök {attempt + 1}/{self.max_retries})")

                if isinstance(messages, str):
                    response = self.llm.invoke([{"role": "user", "content": messages}])
                else:
                    response = self.llm.invoke(messages)

                result = response.content if isinstance(response, AIMessage) else str(response)
                logger.info(f"✅ Modern Design 1: AI-svar mottaget ({len(result)} tecken)")
                _log_ai_call(prompt_text, result)
                return result

            except Exception as e:
                logger.warning(f"⚠️ Modern Design 1: AI-anrop misslyckades (försök {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    logger.info(f"🔄 Väntar {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"❌ Alla AI-försök misslyckades efter {self.max_retries} försök")
                    raise

        raise Exception("Modern Design 1: AI-anrop misslyckades efter alla försök")

    def invoke(self, messages: Any) -> str:
        return self.__call__(messages)


def create_isolated_llm(api_key: str) -> IsolatedLoggerChatModel:
    """Skapar en isolerad LLM för Modern Design 1"""
    chat_model = ChatOpenAI(
        model_name="gpt-4o-mini",
        openai_api_key=api_key,
        temperature=0.4,
        timeout=60
    )
    return IsolatedLoggerChatModel(chat_model)


def image_to_base64(image_path: str) -> str:
    """Konverterar bild till base64."""
    try:
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        with open(image_path, "rb") as image_file:
            base64_string = base64.b64encode(image_file.read()).decode('utf-8')
            logger.debug(f"Modern Design 1: Konverterade {image_path} till base64")
            return base64_string
    except FileNotFoundError as e:
        logger.error(f"Modern Design 1: Error converting image to base64: {e}")
        raise
    except Exception as e:
        logger.error(f"Modern Design 1: Unexpected error converting image to base64: {e}")
        raise
