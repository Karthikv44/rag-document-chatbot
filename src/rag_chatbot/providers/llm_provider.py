"""Gemini LLM Provider.

Wraps langchain-google-genai's ChatGoogleGenerativeAI so the rest of
the application depends on this thin adapter rather than the LangChain class
directly.
"""

from functools import cached_property

from langchain_google_genai import ChatGoogleGenerativeAI

from rag_chatbot.config.config import settings
from rag_chatbot.utils.logger import logger


class LLMProvider:
    """Adapter around ChatGoogleGenerativeAI.

    Provides a single `llm` property returning a configured LangChain
    chat model instance.
    """

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model or settings.gemini_llm_model
        self._temperature = temperature if temperature is not None else settings.llm_temperature
        self._max_tokens = max_tokens or settings.llm_max_tokens
        self._api_key = api_key or settings.google_api_key.get_secret_value()

    @cached_property
    def llm(self) -> ChatGoogleGenerativeAI:
        """Lazily construct and cache the LangChain LLM object."""
        logger.info("Initialising Gemini LLM model: %s", self._model)
        return ChatGoogleGenerativeAI(
            model=self._model,
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
            google_api_key=self._api_key,  # type: ignore[arg-type]
            timeout=60,
            max_retries=2,
        )


# Module-level singleton
llm_provider = LLMProvider()
