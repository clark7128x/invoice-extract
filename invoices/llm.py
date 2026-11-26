from __future__ import annotations

import time
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

from .calllog import CallLog
from .config import LLMConfig, ModelConfig


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatResult:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_s: float


class LLMClient:
    def __init__(self, llm: LLMConfig, model: ModelConfig, call_log: CallLog | None = None):
        self.llm = llm
        self.model = model
        self.call_log = call_log

    def _log(self, **kwargs) -> None:
        if self.call_log:
            self.call_log.record(model=self.model.model or "", **kwargs)

    def _delay(self, attempt: int) -> float:
        return min(self.llm.retry_base_delay_s * (2**attempt), self.llm.retry_max_delay_s)

    def chat(self, messages: list[dict[str, str]], extra: dict[str, Any] | None = None) -> ChatResult:
        if not self.llm.base_url or not self.model.configured:
            raise LLMError("Не задано LLM_API_BASE або назву моделі")

        url = self.llm.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.llm.api_key:
            headers["Authorization"] = f"Bearer {self.llm.api_key}"
        payload: dict[str, Any] = {
            "model": self.model.model,
            "messages": messages,
            "temperature": self.model.temperature,
            "max_tokens": self.model.max_output_tokens,
        }
        if self.model.json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error = "невідома помилка"
        with httpx.Client(timeout=self.llm.timeout_s) as client:
            for attempt in range(self.llm.max_retries + 1):
                started = perf_counter()
                try:
                    response = client.post(url, json=payload, headers=headers)
                except httpx.HTTPError as exc:
                    latency = perf_counter() - started
                    last_error = f"{type(exc).__name__}: {exc}"
                    self._log(input_tokens=None, output_tokens=None, latency_s=latency,
                              ok=False, error=last_error, extra=extra)
                    if attempt < self.llm.max_retries:
                        time.sleep(self._delay(attempt))
                        continue
                    raise LLMError(last_error) from exc

                latency = perf_counter() - started
                if response.status_code != 200:
                    last_error = f"http {response.status_code}: {response.text[:200]}"
                    self._log(input_tokens=None, output_tokens=None, latency_s=latency,
                              ok=False, error=last_error, extra=extra)
                    retryable = response.status_code == 429 or response.status_code >= 500
                    if retryable and attempt < self.llm.max_retries:
                        time.sleep(self._delay(attempt))
                        continue
                    raise LLMError(last_error)

                data = response.json()
                try:
                    text = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as exc:
                    last_error = "відповідь без choices[0].message.content"
                    self._log(input_tokens=None, output_tokens=None, latency_s=latency,
                              ok=False, error=last_error, extra=extra)
                    raise LLMError(last_error) from exc

                usage = data.get("usage") or {}
                input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
                output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
                self._log(input_tokens=input_tokens, output_tokens=output_tokens,
                          latency_s=latency, extra=extra)
                return ChatResult(text, self.model.model, input_tokens, output_tokens, latency)

        raise LLMError(last_error)
