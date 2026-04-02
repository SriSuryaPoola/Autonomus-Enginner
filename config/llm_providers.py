"""
LLM Provider Abstraction Layer — Multi-Provider Support.

Allows the platform to switch between Anthropic, OpenAI, Ollama, Gemini,
and Grok via a single env variable: LLM_PROVIDER

Usage:
    from config.llm_providers import get_llm_client, LLMMessage

    client = get_llm_client()
    response = client.complete([LLMMessage(role="user", content="Hello")])
    print(response.text)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class LLMMessage:
    role: str       # "user" | "assistant" | "system"
    content: str


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ─── Base Provider ────────────────────────────────────────────────────────────

class BaseLLMProvider:
    """Abstract base class for all LLM providers."""

    name: str = "base"

    def complete(
        self,
        messages: list[LLMMessage],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> LLMResponse:
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if this provider is properly configured."""
        raise NotImplementedError


# ─── Anthropic (Claude) ───────────────────────────────────────────────────────

class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self):
        self._client = None
        self._model = os.getenv("ANTHROPIC_MODEL", self.DEFAULT_MODEL)

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        return self._client

    def is_available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))

    def complete(self, messages, max_tokens=2048, temperature=0.1) -> LLMResponse:
        client = self._get_client()
        # Separate system messages
        system = next((m.content for m in messages if m.role == "system"), None)
        user_msgs = [{"role": m.role, "content": m.content}
                     for m in messages if m.role != "system"]
        kwargs = dict(model=self._model, max_tokens=max_tokens,
                      temperature=temperature, messages=user_msgs)
        if system:
            kwargs["system"] = system
        resp = client.messages.create(**kwargs)
        return LLMResponse(
            text=resp.content[0].text,
            model=self._model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )


# ─── OpenAI ───────────────────────────────────────────────────────────────────

class OpenAIProvider(BaseLLMProvider):
    name = "openai"
    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self):
        self._client = None
        self._model = os.getenv("OPENAI_MODEL", self.DEFAULT_MODEL)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._client

    def is_available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def complete(self, messages, max_tokens=2048, temperature=0.1) -> LLMResponse:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = resp.choices[0]
        return LLMResponse(
            text=choice.message.content,
            model=self._model,
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
        )


# ─── Ollama (Local / Free) ────────────────────────────────────────────────────

class OllamaProvider(BaseLLMProvider):
    name = "ollama"
    DEFAULT_MODEL = "llama3.2"

    def __init__(self):
        self._model = os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self._base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def is_available(self) -> bool:
        try:
            import requests
            r = requests.get(f"{self._base_url}/api/tags", timeout=2)
            return r.ok
        except Exception:
            return False

    def complete(self, messages, max_tokens=2048, temperature=0.1) -> LLMResponse:
        import requests
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        r = requests.post(f"{self._base_url}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        text = data.get("message", {}).get("content", "")
        return LLMResponse(text=text, model=self._model)


# ─── Gemini ───────────────────────────────────────────────────────────────────

class GeminiProvider(BaseLLMProvider):
    name = "gemini"
    DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self):
        self._model = os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL)

    def is_available(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY"))

    def complete(self, messages, max_tokens=2048, temperature=0.1) -> LLMResponse:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(self._model)
        prompt = "\n".join(f"{m.role}: {m.content}" for m in messages)
        resp = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens, "temperature": temperature}
        )
        return LLMResponse(text=resp.text, model=self._model)


# ─── Heuristic Fallback (no API needed) ──────────────────────────────────────

class HeuristicProvider(BaseLLMProvider):
    """Used when no LLM is configured. Returns structured placeholder responses."""
    name = "heuristic"

    def is_available(self) -> bool:
        return True  # Always available

    def complete(self, messages, max_tokens=2048, temperature=0.1) -> LLMResponse:
        # Return a minimal valid response — heuristic patches handle the rest
        return LLMResponse(
            text="# No LLM configured — heuristic mode active\nassert True",
            model="heuristic",
        )


# ─── Provider Factory ─────────────────────────────────────────────────────────

_PROVIDER_MAP: dict[str, type[BaseLLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
    "heuristic": HeuristicProvider,
}

_FALLBACK_ORDER = ["anthropic", "openai", "ollama", "gemini", "heuristic"]


def get_llm_client(provider: Optional[str] = None) -> BaseLLMProvider:
    """
    Return a configured LLM provider.

    Provider resolution order:
      1. `provider` argument (if given)
      2. LLM_PROVIDER env var
      3. Auto-detect: first available in fallback chain
      4. Heuristic (always works, no API needed)
    """
    requested = provider or os.getenv("LLM_PROVIDER", "auto")

    if requested != "auto":
        cls = _PROVIDER_MAP.get(requested.lower())
        if cls:
            instance = cls()
            logger.info(f"[LLM] Using provider: {instance.name}")
            return instance
        logger.warning(f"[LLM] Unknown provider '{requested}', falling back to auto-detect")

    # Auto-detect: try each in fallback order
    for name in _FALLBACK_ORDER:
        cls = _PROVIDER_MAP[name]
        instance = cls()
        if instance.is_available():
            logger.info(f"[LLM] Auto-detected provider: {instance.name}")
            return instance

    return HeuristicProvider()
