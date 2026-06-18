"""
Multi-provider LLM client for PulseGuardAssistant.

Auto-detects the first available provider from the environment so the
chatbot becomes a real open-domain LLM as soon as the user sets ONE of
these env vars in `backend/.env`:

  * `GROQ_API_KEY`       — Llama-3.3-70B via Groq (free tier, fastest).
  * `OPENAI_API_KEY`     — GPT-4o-mini via OpenAI (paid).
  * `ANTHROPIC_API_KEY`  — Claude Haiku via Anthropic (paid).
  * `OLLAMA_BASE_URL`    — local Ollama server (free, slower).

If none is configured, `LLMClient.is_available` is False and the assistant
falls back to its symbolic + trained-NN-classifier path. Zero new
dependencies — uses urllib only.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("pulseguard.llm")


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: int


class LLMClient:
    """Calls whichever provider is configured. Thread-safe (stateless)."""

    def __init__(self) -> None:
        self.provider: Optional[str] = None
        self.model: Optional[str] = None
        self.api_key: Optional[str] = None
        self.base_url: Optional[str] = None
        self.timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "20"))
        self._detect()

    # ------------------------------------------------------------------
    def _detect(self) -> None:
        if os.environ.get("GROQ_API_KEY"):
            self.provider = "groq"
            self.api_key = os.environ["GROQ_API_KEY"]
            self.model = os.environ.get(
                "GROQ_MODEL", "llama-3.3-70b-versatile"
            )
            self.base_url = "https://api.groq.com/openai/v1"
        elif os.environ.get("OPENAI_API_KEY"):
            self.provider = "openai"
            self.api_key = os.environ["OPENAI_API_KEY"]
            self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            self.base_url = os.environ.get(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            )
        elif os.environ.get("ANTHROPIC_API_KEY"):
            self.provider = "anthropic"
            self.api_key = os.environ["ANTHROPIC_API_KEY"]
            self.model = os.environ.get(
                "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
            )
            self.base_url = "https://api.anthropic.com/v1"
        elif os.environ.get("OLLAMA_BASE_URL"):
            self.provider = "ollama"
            self.base_url = os.environ["OLLAMA_BASE_URL"].rstrip("/")
            self.model = os.environ.get("OLLAMA_MODEL", "llama3.2")
        else:
            logger.info(
                "LLMClient: no provider API key configured. "
                "Falling back to symbolic + trained-classifier assistant."
            )

        if self.provider:
            logger.info(
                "LLMClient: using %s with model %s",
                self.provider, self.model,
            )

    @property
    def is_available(self) -> bool:
        return self.provider is not None

    # ------------------------------------------------------------------
    def chat(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
    ) -> Optional[LLMResponse]:
        """Send a chat completion. Returns None on any error (callers
        should fall back to the symbolic path)."""
        if not self.is_available:
            return None
        start = time.time()
        try:
            if self.provider == "anthropic":
                text = self._call_anthropic(system_prompt, messages)
            elif self.provider == "ollama":
                text = self._call_ollama(system_prompt, messages)
            else:  # groq / openai (OpenAI-compatible API)
                text = self._call_openai_compat(system_prompt, messages)
        except Exception as exc:
            logger.warning(
                "LLMClient (%s): call failed (%s) — falling back.",
                self.provider, exc,
            )
            return None
        latency_ms = int((time.time() - start) * 1000)
        return LLMResponse(
            text=text.strip(),
            provider=self.provider,
            model=self.model or "?",
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # Provider-specific HTTP calls
    # ------------------------------------------------------------------
    def _post_json(self, url: str, headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", **headers},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw)

    def _call_openai_compat(
        self, system_prompt: str, messages: List[Dict[str, str]]
    ) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload_msgs = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = m.get("role", "user")
            if role not in ("user", "assistant", "system"):
                role = "user"
            payload_msgs.append({"role": role, "content": m.get("content", "")})
        body = {
            "model": self.model,
            "messages": payload_msgs,
            "temperature": 0.4,
            "max_tokens": 400,
            "stream": False,
        }
        resp = self._post_json(
            url, {"Authorization": f"Bearer {self.api_key}"}, body
        )
        return resp["choices"][0]["message"]["content"]

    def _call_anthropic(
        self, system_prompt: str, messages: List[Dict[str, str]]
    ) -> str:
        url = f"{self.base_url}/messages"
        anthropic_msgs = []
        for m in messages:
            role = m.get("role", "user")
            role = "assistant" if role == "assistant" else "user"
            anthropic_msgs.append({"role": role, "content": m.get("content", "")})
        body = {
            "model": self.model,
            "max_tokens": 500,
            "temperature": 0.4,
            "system": system_prompt,
            "messages": anthropic_msgs,
        }
        resp = self._post_json(
            url,
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            body,
        )
        return resp["content"][0]["text"]

    def _call_ollama(
        self, system_prompt: str, messages: List[Dict[str, str]]
    ) -> str:
        url = f"{self.base_url}/api/chat"
        payload_msgs = [{"role": "system", "content": system_prompt}]
        for m in messages:
            payload_msgs.append({
                "role": m.get("role", "user"),
                "content": m.get("content", ""),
            })
        body = {
            "model": self.model,
            "messages": payload_msgs,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 400},
        }
        resp = self._post_json(url, {}, body)
        return resp["message"]["content"]

    # ------------------------------------------------------------------
    def info(self) -> Dict[str, Any]:
        return {
            "available": self.is_available,
            "provider": self.provider,
            "model": self.model,
            "timeout_seconds": self.timeout,
        }
