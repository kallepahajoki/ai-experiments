"""Thin OpenRouter API client for chat completions."""

import os
import time
import httpx
from dataclasses import dataclass, field


@dataclass
class CompletionResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float | None
    latency_ms: float
    raw_response: dict = field(repr=False)


class OpenRouterClient:
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str | None = None, default_temperature: float = 0.0):
        self.api_key = api_key or os.environ["OPENROUTER_API_KEY"]
        self.default_temperature = default_temperature
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    def complete(
        self,
        model: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int = 4096,
        retries: int = 3,
        backoff_base: float = 2.0,
    ) -> CompletionResult:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_tokens": max_tokens,
        }

        last_error = None
        for attempt in range(retries):
            try:
                t0 = time.monotonic()
                resp = self._client.post("/chat/completions", json=payload)
                latency_ms = (time.monotonic() - t0) * 1000

                if resp.status_code == 429:
                    wait = backoff_base ** attempt
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                usage = data.get("usage", {})
                return CompletionResult(
                    content=data["choices"][0]["message"]["content"],
                    model=data.get("model", model),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    cost_usd=_extract_cost(data),
                    latency_ms=latency_ms,
                    raw_response=data,
                )
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500:
                    time.sleep(backoff_base ** attempt)
                    continue
                raise
            except httpx.TimeoutException as e:
                last_error = e
                time.sleep(backoff_base ** attempt)
                continue

        raise RuntimeError(f"Failed after {retries} retries: {last_error}")

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _extract_cost(data: dict) -> float | None:
    usage = data.get("usage", {})
    cost = usage.get("cost")
    if cost is not None:
        return float(cost)
    return None
