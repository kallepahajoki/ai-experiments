"""Thin OpenRouter API client for chat completions."""

import asyncio
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
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers=self._headers,
            timeout=120.0,
        )
        self._async_client: httpx.AsyncClient | None = None

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=self._headers,
                timeout=120.0,
            )
        return self._async_client

    def _build_payload(self, model: str, messages: list[dict],
                       temperature: float | None, max_tokens: int) -> dict:
        return {
            "model": model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_tokens": max_tokens,
        }

    def complete(
        self,
        model: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int = 4096,
        retries: int = 3,
        backoff_base: float = 2.0,
    ) -> CompletionResult:
        payload = self._build_payload(model, messages, temperature, max_tokens)

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
                return _parse_response(resp.json(), model, latency_ms)
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

    async def acomplete(
        self,
        model: str,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int = 4096,
        retries: int = 3,
        backoff_base: float = 2.0,
    ) -> CompletionResult:
        payload = self._build_payload(model, messages, temperature, max_tokens)
        client = self._get_async_client()

        last_error = None
        for attempt in range(retries):
            try:
                t0 = time.monotonic()
                resp = await client.post("/chat/completions", json=payload)
                latency_ms = (time.monotonic() - t0) * 1000

                if resp.status_code == 429:
                    await asyncio.sleep(backoff_base ** attempt)
                    continue

                resp.raise_for_status()
                return _parse_response(resp.json(), model, latency_ms)
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500:
                    await asyncio.sleep(backoff_base ** attempt)
                    continue
                raise
            except httpx.TimeoutException as e:
                last_error = e
                await asyncio.sleep(backoff_base ** attempt)
                continue

        raise RuntimeError(f"Failed after {retries} retries: {last_error}")

    async def batch_complete(
        self,
        requests: list[dict],
        concurrency: int = 10,
    ) -> list[CompletionResult]:
        """Run multiple completions concurrently.

        Each request dict has keys: model, messages, and optionally
        temperature, max_tokens.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _run(req: dict) -> CompletionResult:
            async with semaphore:
                return await self.acomplete(
                    model=req["model"],
                    messages=req["messages"],
                    temperature=req.get("temperature"),
                    max_tokens=req.get("max_tokens", 4096),
                )

        return await asyncio.gather(*[_run(r) for r in requests])

    def close(self):
        self._client.close()
        if self._async_client and not self._async_client.is_closed:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_client.aclose())
            except RuntimeError:
                asyncio.run(self._async_client.aclose())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _parse_response(data: dict, model: str, latency_ms: float) -> CompletionResult:
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


def _extract_cost(data: dict) -> float | None:
    usage = data.get("usage", {})
    cost = usage.get("cost")
    if cost is not None:
        return float(cost)
    return None
