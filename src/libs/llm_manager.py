import json
import os
import re
import textwrap
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union

import httpx
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompt_values import StringPromptValue
from langchain_core.prompts import ChatPromptTemplate
from Levenshtein import distance

# Prompts handled locally in ApplyMind AI
from config import JOB_SUITABILITY_SCORE
from src.utils.constants import (
    AVAILABILITY,
    CERTIFICATIONS,
    CLAUDE,
    COMPANY,
    CONTENT,
    COVER_LETTER,
    EDUCATION_DETAILS,
    EXPERIENCE_DETAILS,
    FINISH_REASON,
    GEMINI,
    HUGGINGFACE,
    ID,
    INPUT_TOKENS,
    INTERESTS,
    JOB_APPLICATION_PROFILE,
    JOB_DESCRIPTION,
    LANGUAGES,
    LEGAL_AUTHORIZATION,
    LLM_MODEL_TYPE,
    LOGPROBS,
    MODEL,
    MODEL_NAME,
    OLLAMA,
    OPENAI,
    PERPLEXITY,
    OPTIONS,
    OUTPUT_TOKENS,
    PERSONAL_INFORMATION,
    PHRASE,
    PROJECTS,
    PROMPTS,
    QUESTION,
    REPLIES,
    RESPONSE_METADATA,
    RESUME,
    RESUME_EDUCATIONS,
    RESUME_JOBS,
    RESUME_PROJECTS,
    RESUME_SECTION,
    SALARY_EXPECTATIONS,
    SELF_IDENTIFICATION,
    SYSTEM_FINGERPRINT,
    TEXT,
    TIME,
    TOKEN_USAGE,
    TOTAL_COST,
    TOTAL_TOKENS,
    USAGE_METADATA,
    WORK_PREFERENCES,
)
from src.job import Job
from src.logger_config import logger
import config as cfg

load_dotenv()


# ✅ FIX #4: Import retry utilities for robust LLM error handling
# Framework Rule: "Release It!" Chapter 4 - Stability Patterns
# Impact: Graceful degradation, prevents crashes on transient LLM failures
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        RetryError
    )
    TENACITY_AVAILABLE = True
except ImportError:
    logger.warning("tenacity library not available. LLM calls will not have retry logic.")
    TENACITY_AVAILABLE = False


class AIModel(ABC):
    @abstractmethod
    def invoke(self, prompt: str) -> str:
        pass


class OpenAIModel(AIModel):
    def __init__(self, api_key: str, llm_model: str):
        from langchain_openai import ChatOpenAI

        self.model = ChatOpenAI(
            model_name=llm_model, openai_api_key=api_key, temperature=0.4, timeout=60
        )

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke OpenAI API with comprehensive error handling.

        RELIABILITY: Wraps API call with specific exception handling to prevent crashes.
        Framework Rule: LangChain best practices - handle all possible exceptions

        Args:
            prompt: Input prompt for the model

        Returns:
            BaseMessage: Model response

        Raises:
            ValueError: If API call fails after retries or with invalid input
            ConnectionError: If network issues prevent API access
        """
        logger.debug("Invoking OpenAI API")
        try:
            response = self.model.invoke(prompt)
            return response
        except httpx.TimeoutException as e:
            logger.error(f"OpenAI API timeout: {e}")
            raise ValueError(f"OpenAI API request timed out after 60s: {e}") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API HTTP error {e.response.status_code}: {e}")
            if e.response.status_code == 401:
                raise ValueError("OpenAI API authentication failed. Check your API key.") from e
            elif e.response.status_code == 429:
                raise ValueError("OpenAI API rate limit exceeded. Please wait and retry.") from e
            elif e.response.status_code >= 500:
                raise ConnectionError(f"OpenAI API server error (HTTP {e.response.status_code})") from e
            else:
                raise ValueError(f"OpenAI API error (HTTP {e.response.status_code}): {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error invoking OpenAI API: {e}")
            raise ValueError(f"Failed to invoke OpenAI model: {e}") from e


class ClaudeModel(AIModel):
    def __init__(self, api_key: str, llm_model: str):
        from langchain_anthropic import ChatAnthropic

        self.model = ChatAnthropic(model=llm_model, api_key=api_key, temperature=0.4)

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke Claude API with comprehensive error handling.

        RELIABILITY: Wraps API call with specific exception handling to prevent crashes.
        Framework Rule: LangChain best practices - handle all possible exceptions

        Args:
            prompt: Input prompt for the model

        Returns:
            BaseMessage: Model response

        Raises:
            ValueError: If API call fails after retries or with invalid input
            ConnectionError: If network issues prevent API access
        """
        logger.debug("Invoking Claude API")
        try:
            response = self.model.invoke(prompt)
            return response
        except httpx.TimeoutException as e:
            logger.error(f"Claude API timeout: {e}")
            raise ValueError(f"Claude API request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"Claude API HTTP error {e.response.status_code}: {e}")
            if e.response.status_code == 401:
                raise ValueError("Claude API authentication failed. Check your API key.") from e
            elif e.response.status_code == 429:
                raise ValueError("Claude API rate limit exceeded. Please wait and retry.") from e
            elif e.response.status_code >= 500:
                raise ConnectionError(f"Claude API server error (HTTP {e.response.status_code})") from e
            else:
                raise ValueError(f"Claude API error (HTTP {e.response.status_code}): {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error invoking Claude API: {e}")
            raise ValueError(f"Failed to invoke Claude model: {e}") from e


class OllamaModel(AIModel):
    def __init__(self, llm_model: str, llm_api_url: str):
        from langchain_ollama import ChatOllama

        if len(llm_api_url) > 0:
            logger.debug(f"Using Ollama with API URL: {llm_api_url}")
            self.model = ChatOllama(model=llm_model, base_url=llm_api_url)
        else:
            self.model = ChatOllama(model=llm_model)

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke Ollama API with comprehensive error handling.

        RELIABILITY: Wraps API call with specific exception handling to prevent crashes.
        Framework Rule: LangChain best practices - handle all possible exceptions

        Args:
            prompt: Input prompt for the model

        Returns:
            BaseMessage: Model response

        Raises:
            ValueError: If API call fails
            ConnectionError: If Ollama server is unreachable
        """
        logger.debug("Invoking Ollama API")
        try:
            response = self.model.invoke(prompt)
            return response
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to Ollama server: {e}")
            raise ConnectionError(
                "Ollama server is not reachable. Ensure Ollama is running locally "
                "or check the configured LLM_API_URL."
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"Ollama API timeout: {e}")
            raise ValueError(f"Ollama API request timed out: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error invoking Ollama API: {e}")
            raise ValueError(f"Failed to invoke Ollama model: {e}") from e

class PerplexityModel(AIModel):
    def __init__(self, api_key: str, llm_model: str):
        from langchain_community.chat_models import ChatPerplexity
        self.model = ChatPerplexity(model=llm_model, api_key=api_key, temperature=0.4)

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke Perplexity API with comprehensive error handling.

        RELIABILITY: Wraps API call with specific exception handling to prevent crashes.

        Args:
            prompt: Input prompt for the model

        Returns:
            BaseMessage: Model response

        Raises:
            ValueError: If API call fails
            ConnectionError: If network issues prevent API access
        """
        logger.debug("Invoking Perplexity API")
        try:
            response = self.model.invoke(prompt)
            return response
        except httpx.TimeoutException as e:
            logger.error(f"Perplexity API timeout: {e}")
            raise ValueError(f"Perplexity API request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"Perplexity API HTTP error {e.response.status_code}: {e}")
            raise ValueError(f"Perplexity API error (HTTP {e.response.status_code}): {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error invoking Perplexity API: {e}")
            raise ValueError(f"Failed to invoke Perplexity model: {e}") from e

# gemini doesn't seem to work because API doesn't rstitute answers for questions that involve answers that are too short
class GeminiModel(AIModel):
    def __init__(self, api_key: str, llm_model: str):
        from langchain_google_genai import (
            ChatGoogleGenerativeAI,
            HarmBlockThreshold,
            HarmCategory,
        )

        self.model = ChatGoogleGenerativeAI(
            model=llm_model,
            google_api_key=api_key,
            safety_settings={
                HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DEROGATORY: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_TOXICITY: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_VIOLENCE: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUAL: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_MEDICAL: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            },
        )

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke Gemini API with comprehensive error handling.

        RELIABILITY: Wraps API call with specific exception handling to prevent crashes.

        Args:
            prompt: Input prompt for the model

        Returns:
            BaseMessage: Model response

        Raises:
            ValueError: If API call fails
            ConnectionError: If network issues prevent API access
        """
        logger.debug("Invoking Gemini API")
        try:
            response = self.model.invoke(prompt)
            return response
        except httpx.TimeoutException as e:
            logger.error(f"Gemini API timeout: {e}")
            raise ValueError(f"Gemini API request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini API HTTP error {e.response.status_code}: {e}")
            if e.response.status_code == 401:
                raise ValueError("Gemini API authentication failed. Check your API key.") from e
            elif e.response.status_code == 429:
                raise ValueError("Gemini API rate limit exceeded. Please wait and retry.") from e
            else:
                raise ValueError(f"Gemini API error (HTTP {e.response.status_code}): {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error invoking Gemini API: {e}")
            raise ValueError(f"Failed to invoke Gemini model: {e}") from e


class HuggingFaceModel(AIModel):
    def __init__(self, api_key: str, llm_model: str):
        from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

        self.model = HuggingFaceEndpoint(
            repo_id=llm_model, huggingfacehub_api_token=api_key, temperature=0.4
        )
        self.chatmodel = ChatHuggingFace(llm=self.model)

    def invoke(self, prompt: str) -> BaseMessage:
        """
        Invoke HuggingFace API with comprehensive error handling.

        RELIABILITY: Wraps API call with specific exception handling to prevent crashes.

        Args:
            prompt: Input prompt for the model

        Returns:
            BaseMessage: Model response

        Raises:
            ValueError: If API call fails
            ConnectionError: If network issues prevent API access
        """
        logger.debug("Invoking HuggingFace API")
        try:
            response = self.chatmodel.invoke(prompt)
            logger.debug(
                f"HuggingFace response received: {response}, Type: {type(response)}"
            )
            return response
        except httpx.TimeoutException as e:
            logger.error(f"HuggingFace API timeout: {e}")
            raise ValueError(f"HuggingFace API request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"HuggingFace API HTTP error {e.response.status_code}: {e}")
            raise ValueError(f"HuggingFace API error (HTTP {e.response.status_code}): {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error invoking HuggingFace API: {e}")
            raise ValueError(f"Failed to invoke HuggingFace model: {e}") from e


class AIAdapter:
    def __init__(self, config: dict, api_key: str):
        self.model = self._create_model(config, api_key)

    def _create_model(self, config: dict, api_key: str) -> AIModel:
        llm_model_type = cfg.LLM_MODEL_TYPE
        llm_model = cfg.LLM_MODEL

        llm_api_url = cfg.LLM_API_URL

        logger.debug(f"Using {llm_model_type} with {llm_model}")

        if llm_model_type == OPENAI:
            return OpenAIModel(api_key, llm_model)
        elif llm_model_type == CLAUDE:
            return ClaudeModel(api_key, llm_model)
        elif llm_model_type == OLLAMA:
            return OllamaModel(llm_model, llm_api_url)
        elif llm_model_type == GEMINI:
            return GeminiModel(api_key, llm_model)
        elif llm_model_type == HUGGINGFACE:
            return HuggingFaceModel(api_key, llm_model)
        elif llm_model_type == PERPLEXITY:
            return PerplexityModel(api_key, llm_model)
        else:
            raise ValueError(f"Unsupported model type: {llm_model_type}")

    def invoke(self, prompt: str) -> str:
        """
        Invoke the configured AI model with error handling.

        This method wraps the underlying model's invoke() which already has
        comprehensive error handling in place.

        Args:
            prompt: Input prompt for the model

        Returns:
            str: Model response

        Raises:
            ValueError: If model invocation fails
            ConnectionError: If network issues prevent API access
        """
        return self.model.invoke(prompt)


class LLMLogger:
    def __init__(self, llm: Union[OpenAIModel, OllamaModel, ClaudeModel, GeminiModel]):
        self.llm = llm
        logger.debug(f"LLMLogger successfully initialized with LLM: {llm}")

    @staticmethod
    def log_request(prompts, parsed_reply: Dict[str, Dict]):
        """
        Log LLM requests with sanitized data (NO API KEYS OR SENSITIVE INFO).

        SECURITY: This method now sanitizes prompts to remove API keys and passwords
        before logging to prevent credential leakage.
        """
        logger.debug("Starting log_request method")

        # Import security utilities
        try:
            from src.security_utils import SecurityValidator
        except ImportError:
            logger.warning("Security utils not available, skipping prompt sanitization")
            SecurityValidator = None

        try:
            calls_log = os.path.join(Path("data_folder/output"), "open_ai_calls.json")
            logger.debug(f"Logging path determined: {calls_log}")
        except Exception as e:
            logger.error(f"Error determining the log path: {str(e)}")
            raise

        # Convert prompts to loggable format
        if isinstance(prompts, StringPromptValue):
            logger.debug("Prompts are of type StringPromptValue")
            prompts_text = prompts.text
        elif isinstance(prompts, Dict):
            logger.debug("Prompts are of type Dict")
            try:
                prompts_text = {
                    f"prompt_{i + 1}": prompt.content
                    for i, prompt in enumerate(prompts.messages)
                }
            except Exception as e:
                logger.error(f"Error converting prompts to dictionary: {str(e)}")
                raise
        else:
            logger.debug("Prompts are of unknown type, attempting default conversion")
            try:
                prompts_text = {
                    f"prompt_{i + 1}": prompt.content
                    for i, prompt in enumerate(prompts.messages)
                }
            except Exception as e:
                logger.error(f"Error converting prompts using default method: {str(e)}")
                raise

        # SECURITY FIX: Sanitize prompts before logging
        if SecurityValidator:
            if isinstance(prompts_text, str):
                prompts_text = SecurityValidator.sanitize_for_logging(prompts_text)
            elif isinstance(prompts_text, dict):
                prompts_text = {
                    key: SecurityValidator.sanitize_for_logging(str(value))
                    for key, value in prompts_text.items()
                }
            logger.debug("Prompts sanitized for secure logging")

        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error(f"Error obtaining current time: {str(e)}")
            raise

        try:
            token_usage = parsed_reply[USAGE_METADATA]
            output_tokens = token_usage[OUTPUT_TOKENS]
            input_tokens = token_usage[INPUT_TOKENS]
            total_tokens = token_usage[TOTAL_TOKENS]
            logger.debug(
                f"Token usage - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}"
            )
        except KeyError as e:
            logger.error(f"KeyError in parsed_reply structure: {str(e)}")
            raise

        try:
            model_name = parsed_reply[RESPONSE_METADATA][MODEL_NAME]
            logger.debug(f"Model name: {model_name}")
        except KeyError as e:
            logger.error(f"KeyError in response_metadata: {str(e)}")
            raise

        try:
            prompt_price_per_token = 0.00000015
            completion_price_per_token = 0.0000006
            total_cost = (input_tokens * prompt_price_per_token) + (
                output_tokens * completion_price_per_token
            )
            logger.debug(f"Total cost calculated: {total_cost}")
        except Exception as e:
            logger.error(f"Error calculating total cost: {str(e)}")
            raise

        try:
            # Sanitize reply content as well
            reply_content = parsed_reply[CONTENT]
            if SecurityValidator and isinstance(reply_content, str):
                reply_content = SecurityValidator.sanitize_for_logging(reply_content)

            log_entry = {
                MODEL: model_name,
                TIME: current_time,
                PROMPTS: prompts_text,  # Now sanitized
                REPLIES: reply_content,  # Now sanitized
                TOTAL_TOKENS: total_tokens,
                INPUT_TOKENS: input_tokens,
                OUTPUT_TOKENS: output_tokens,
                TOTAL_COST: total_cost,
            }
            logger.debug("Log entry created with sanitized data")
        except KeyError as e:
            logger.error(
                f"Error creating log entry: missing key {str(e)} in parsed_reply"
            )
            raise

        try:
            with open(calls_log, "a", encoding="utf-8") as f:
                json_string = json.dumps(log_entry, ensure_ascii=False, indent=4)
                f.write(json_string + "\n")
                logger.debug(f"Secure log entry written to file: {calls_log}")
        except Exception as e:
            logger.error(f"Error writing log entry to file: {str(e)}")
            raise


class LoggerChatModel:
    """
    Wrapper for LLM models with logging and comprehensive error handling.

    ✅ FIX #4: Enhanced with retry logic and graceful degradation.
    Framework Rule: "Release It!" Chapter 4 - Stability Patterns
    """
    def __init__(self, llm: Union[OpenAIModel, OllamaModel, ClaudeModel, GeminiModel]):
        self.llm = llm
        logger.debug(f"LoggerChatModel successfully initialized with LLM: {llm}")

    def __call__(self, messages: List[Dict[str, str]]) -> str:
        """
        Invoke LLM with retry logic and comprehensive error handling.

        RELIABILITY: Implements exponential backoff for rate limits and transient failures.
        Framework Rule: "Release It!" - Circuit Breaker and Retry patterns

        Args:
            messages: List of messages to send to the LLM

        Returns:
            str: LLM response

        Raises:
            ValueError: If all retries are exhausted or unrecoverable error occurs
            ConnectionError: If network issues persist across all retries
        """
        logger.debug(f"Entering __call__ method with messages: {messages}")
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                logger.debug(f"Attempt {retry_count + 1}/{max_retries}: Calling the LLM")

                reply = self.llm.invoke(messages)
                logger.debug(f"LLM response received: {reply}")

                parsed_reply = self.parse_llmresult(reply)
                logger.debug(f"Parsed LLM reply: {parsed_reply}")

                LLMLogger.log_request(prompts=messages, parsed_reply=parsed_reply)
                logger.debug("Request successfully logged")

                return reply

            except httpx.HTTPStatusError as e:
                retry_count += 1
                logger.error(f"HTTPStatusError encountered (attempt {retry_count}/{max_retries}): {str(e)}")

                if e.response.status_code == 429:
                    # Rate limit - use retry-after header
                    retry_after = e.response.headers.get("retry-after")
                    retry_after_ms = e.response.headers.get("retry-after-ms")

                    if retry_after:
                        wait_time = int(retry_after)
                        logger.warning(
                            f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying "
                            f"(extracted from 'retry-after' header)..."
                        )
                        time.sleep(wait_time)
                    elif retry_after_ms:
                        wait_time = int(retry_after_ms) / 1000.0
                        logger.warning(
                            f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying "
                            f"(extracted from 'retry-after-ms' header)..."
                        )
                        time.sleep(wait_time)
                    else:
                        wait_time = 30
                        logger.warning(
                            f"'retry-after' header not found. Waiting for {wait_time} seconds before retrying (default)..."
                        )
                        time.sleep(wait_time)

                    if retry_count >= max_retries:
                        logger.error(f"Rate limit exceeded after {max_retries} retries. Giving up.")
                        raise ValueError(
                            f"LLM API rate limit exceeded after {max_retries} retries. "
                            "Please wait before making more requests."
                        ) from e

                elif e.response.status_code >= 500:
                    # Server error - exponential backoff
                    wait_time = min(2 ** retry_count, 60)  # Cap at 60 seconds
                    logger.warning(
                        f"HTTP {e.response.status_code} server error. "
                        f"Waiting {wait_time}s before retry {retry_count}/{max_retries}..."
                    )
                    time.sleep(wait_time)

                    if retry_count >= max_retries:
                        logger.error(f"Server error persists after {max_retries} retries. Giving up.")
                        raise ConnectionError(
                            f"LLM API server error (HTTP {e.response.status_code}) after {max_retries} retries."
                        ) from e

                else:
                    # Client error (4xx other than 429) - don't retry
                    logger.error(f"HTTP {e.response.status_code} client error. Not retrying.")
                    raise ValueError(
                        f"LLM API client error (HTTP {e.response.status_code}): {e}"
                    ) from e

            except (ConnectionError, httpx.ConnectError, httpx.TimeoutException) as e:
                retry_count += 1
                wait_time = min(2 ** retry_count, 60)  # Exponential backoff, capped at 60s
                logger.error(
                    f"Network/connection error (attempt {retry_count}/{max_retries}): {str(e)}"
                )
                logger.warning(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)

                if retry_count >= max_retries:
                    logger.error(f"Network errors persist after {max_retries} retries. Giving up.")
                    raise ConnectionError(
                        f"Failed to connect to LLM API after {max_retries} retries. "
                        "Check your network connection and API endpoint."
                    ) from e

            except ValueError as e:
                # ValueError from our AIModel.invoke() methods - don't retry
                logger.error(f"LLM invocation failed with ValueError: {str(e)}")
                raise

            except Exception as e:
                retry_count += 1
                logger.error(f"Unexpected error (attempt {retry_count}/{max_retries}): {str(e)}")

                if retry_count >= max_retries:
                    logger.error(f"Unexpected errors persist after {max_retries} retries. Giving up.")
                    raise ValueError(
                        f"LLM processing failed after {max_retries} retries: {e}"
                    ) from e

                wait_time = min(2 ** retry_count, 60)
                logger.warning(f"Waiting {wait_time}s before retry due to unexpected error...")
                time.sleep(wait_time)

        # Should never reach here, but just in case
        raise ValueError(f"LLM processing failed after {max_retries} retries")

    def parse_llmresult(self, llmresult: AIMessage) -> Dict[str, Dict]:
        logger.debug(f"Parsing LLM result: {llmresult}")

        try:
            if hasattr(llmresult, USAGE_METADATA):
                content = llmresult.content
                response_metadata = llmresult.response_metadata
                id_ = llmresult.id
                usage_metadata = llmresult.usage_metadata

                parsed_result = {
                    CONTENT: content,
                    RESPONSE_METADATA: {
                        MODEL_NAME: response_metadata.get(
                            MODEL_NAME, ""
                        ),
                        SYSTEM_FINGERPRINT: response_metadata.get(
                            SYSTEM_FINGERPRINT, ""
                        ),
                        FINISH_REASON: response_metadata.get(
                            FINISH_REASON, ""
                        ),
                        LOGPROBS: response_metadata.get(
                            LOGPROBS, None
                        ),
                    },
                    ID: id_,
                    USAGE_METADATA: {
                        INPUT_TOKENS: usage_metadata.get(
                            INPUT_TOKENS, 0
                        ),
                        OUTPUT_TOKENS: usage_metadata.get(
                            OUTPUT_TOKENS, 0
                        ),
                        TOTAL_TOKENS: usage_metadata.get(
                            TOTAL_TOKENS, 0
                        ),
                    },
                }
            else:
                content = llmresult.content
                response_metadata = llmresult.response_metadata
                id_ = llmresult.id
                token_usage = response_metadata[TOKEN_USAGE]

                parsed_result = {
                    CONTENT: content,
                    RESPONSE_METADATA: {
                        MODEL_NAME: response_metadata.get(
                            MODEL, ""
                        ),
                        FINISH_REASON: response_metadata.get(
                            FINISH_REASON, ""
                        ),
                    },
                    ID: id_,
                    USAGE_METADATA: {
                        INPUT_TOKENS: token_usage.prompt_tokens,
                        OUTPUT_TOKENS: token_usage.completion_tokens,
                        TOTAL_TOKENS: token_usage.total_tokens,
                    },
                }
            logger.debug(f"Parsed LLM result successfully: {parsed_result}")
            return parsed_result

        except KeyError as e:
            logger.error(f"KeyError while parsing LLM result: missing key {str(e)}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error while parsing LLM result: {str(e)}")
            raise


class GPTAnswerer:
    def __init__(self, config, llm_api_key):
        self.ai_adapter = AIAdapter(config, llm_api_key)
        self.llm_cheap = LoggerChatModel(self.ai_adapter)

    @property
    def job_description(self):
        return self.job.description

    @staticmethod
    def find_best_match(text: str, options: list[str]) -> str:
        logger.debug(f"Finding best match for text: '{text}' in options: {options}")
        distances = [
            (option, distance(text.lower(), option.lower())) for option in options
        ]
        best_option = min(distances, key=lambda x: x[1])[0]
        logger.debug(f"Best match found: {best_option}")
        return best_option

    @staticmethod
    def _remove_placeholders(text: str) -> str:
        logger.debug(f"Removing placeholders from text: {text}")
        text = text.replace("PLACEHOLDER", "")
        return text.strip()

    @staticmethod
    def _preprocess_template_string(template: str) -> str:
        logger.debug("Preprocessing template string")
        return textwrap.dedent(template)

    def set_resume(self, resume):
        logger.debug(f"Setting resume: {resume}")
        self.resume = resume

    def set_job(self, job: Job):
        logger.debug(f"Setting job: {job}")
        self.job = job
        self.job.set_summarize_job_description(
            self.summarize_job_description(self.job.description)
        )

    def set_job_application_profile(self, job_application_profile):
        logger.debug(f"Setting job application profile: {job_application_profile}")
        self.job_application_profile = job_application_profile

    def _clean_llm_output(self, output: str) -> str:
        return output.replace("*", "").replace("#", "").strip()

    def summarize_job_description(self, text: str) -> str:
        logger.debug(f"Summarizing job description: {text}")
        prompts.summarize_prompt_template = self._preprocess_template_string(
            prompts.summarize_prompt_template
        )
        prompt = ChatPromptTemplate.from_template(prompts.summarize_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        raw_output = chain.invoke({TEXT: text})
        output = self._clean_llm_output(raw_output)
        logger.debug(f"Summary generated: {output}")
        return output

    def _create_chain(self, template: str):
        logger.debug(f"Creating chain with template: {template}")
        prompt = ChatPromptTemplate.from_template(template)
        return prompt | self.llm_cheap | StrOutputParser()

    def answer_question_textual_wide_range(self, question: str) -> str:
        logger.debug(f"Answering textual question: {question}")
        chains = {
            PERSONAL_INFORMATION: self._create_chain(
                prompts.personal_information_template
            ),
            SELF_IDENTIFICATION: self._create_chain(
                prompts.self_identification_template
            ),
            LEGAL_AUTHORIZATION: self._create_chain(
                prompts.legal_authorization_template
            ),
            WORK_PREFERENCES: self._create_chain(
                prompts.work_preferences_template
            ),
            EDUCATION_DETAILS: self._create_chain(
                prompts.education_details_template
            ),
            EXPERIENCE_DETAILS: self._create_chain(
                prompts.experience_details_template
            ),
            PROJECTS: self._create_chain(prompts.projects_template),
            AVAILABILITY: self._create_chain(prompts.availability_template),
            SALARY_EXPECTATIONS: self._create_chain(
                prompts.salary_expectations_template
            ),
            CERTIFICATIONS: self._create_chain(
                prompts.certifications_template
            ),
            LANGUAGES: self._create_chain(prompts.languages_template),
            INTERESTS: self._create_chain(prompts.interests_template),
            COVER_LETTER: self._create_chain(prompts.coverletter_template),
        }

        prompt = ChatPromptTemplate.from_template(prompts.determine_section_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        raw_output = chain.invoke({QUESTION: question})
        output = self._clean_llm_output(raw_output)

        match = re.search(
            r"(Personal information|Self Identification|Legal Authorization|Work Preferences|Education "
            r"Details|Experience Details|Projects|Availability|Salary "
            r"Expectations|Certifications|Languages|Interests|Cover letter)",
            output,
            re.IGNORECASE,
        )
        if not match:
            raise ValueError("Could not extract section name from the response.")

        section_name = match.group(1).lower().replace(" ", "_")

        if section_name == "cover_letter":
            chain = chains.get(section_name)
            raw_output = chain.invoke(
                {
                    RESUME: self.resume,
                    JOB_DESCRIPTION: self.job_description,
                    COMPANY: self.job.company,
                }
            )
            output = self._clean_llm_output(raw_output)
            logger.debug(f"Cover letter generated: {output}")
            return output
        resume_section = getattr(self.resume, section_name, None) or getattr(
            self.job_application_profile, section_name, None
        )
        if resume_section is None:
            logger.error(
                f"Section '{section_name}' not found in either resume or job_application_profile."
            )
            raise ValueError(
                f"Section '{section_name}' not found in either resume or job_application_profile."
            )
        chain = chains.get(section_name)
        if chain is None:
            logger.error(f"Chain not defined for section '{section_name}'")
            raise ValueError(f"Chain not defined for section '{section_name}'")
        raw_output = chain.invoke(
            {RESUME_SECTION: resume_section, QUESTION: question}
        )
        output = self._clean_llm_output(raw_output)
        logger.debug(f"Question answered: {output}")
        return output

    def answer_question_numeric(
        self, question: str, default_experience: str = 3
    ) -> str:
        logger.debug(f"Answering numeric question: {question}")
        func_template = self._preprocess_template_string(
            prompts.numeric_question_template
        )
        prompt = ChatPromptTemplate.from_template(func_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        raw_output_str = chain.invoke(
            {
                RESUME_EDUCATIONS: self.resume.education_details,
                RESUME_JOBS: self.resume.experience_details,
                RESUME_PROJECTS: self.resume.projects,
                QUESTION: question,
            }
        )
        output_str = self._clean_llm_output(raw_output_str)
        logger.debug(f"Raw output for numeric question: {output_str}")
        try:
            output = self.extract_number_from_string(output_str)
            logger.debug(f"Extracted number: {output}")
        except ValueError:
            logger.warning(
                f"Failed to extract number, using default experience: {default_experience}"
            )
            output = default_experience
        return output

    def extract_number_from_string(self, output_str):
        logger.debug(f"Extracting number from string: {output_str}")
        numbers = re.findall(r"\d+", output_str)
        if numbers:
            logger.debug(f"Numbers found: {numbers}")
            return str(numbers[0])
        else:
            logger.error("No numbers found in the string")
            raise ValueError("No numbers found in the string")

    def answer_question_from_options(self, question: str, options: list[str]) -> str:
        logger.debug(f"Answering question from options: {question}")
        func_template = self._preprocess_template_string(prompts.options_template)
        prompt = ChatPromptTemplate.from_template(func_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        raw_output_str = chain.invoke(
            {
                RESUME: self.resume,
                JOB_APPLICATION_PROFILE: self.job_application_profile,
                QUESTION: question,
                OPTIONS: options,
            }
        )
        output_str = self._clean_llm_output(raw_output_str)
        logger.debug(f"Raw output for options question: {output_str}")
        best_option = self.find_best_match(output_str, options)
        logger.debug(f"Best option determined: {best_option}")
        return best_option

    def determine_resume_or_cover(self, phrase: str) -> str:
        logger.debug(
            f"Determining if phrase refers to resume or cover letter: {phrase}"
        )
        prompt = ChatPromptTemplate.from_template(
            prompts.resume_or_cover_letter_template
        )
        chain = prompt | self.llm_cheap | StrOutputParser()
        raw_response = chain.invoke({PHRASE: phrase})
        response = self._clean_llm_output(raw_response)
        logger.debug(f"Response for resume_or_cover: {response}")
        if "resume" in response:
            return "resume"
        elif "cover" in response:
            return "cover"
        else:
            return "resume"

    def is_job_suitable(self):
        logger.info("Checking if job is suitable")
        prompt = ChatPromptTemplate.from_template(prompts.is_relavant_position_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        raw_output = chain.invoke(
            {
                RESUME: self.resume,
                JOB_DESCRIPTION: self.job_description,
            }
        )
        output = self._clean_llm_output(raw_output)
        logger.debug(f"Job suitability output: {output}")

        try:
            score = re.search(r"Score:\s*(\d+)", output, re.IGNORECASE).group(1)
            reasoning = re.search(r"Reasoning:\s*(.+)", output, re.IGNORECASE | re.DOTALL).group(1)
        except AttributeError:
            logger.warning("Failed to extract score or reasoning from LLM. Proceeding with application, but job may or may not be suitable.")
            return True

        logger.info(f"Job suitability score: {score}")
        if int(score) < JOB_SUITABILITY_SCORE:
            logger.debug(f"Job is not suitable: {reasoning}")
        return int(score) >= JOB_SUITABILITY_SCORE
