"""OpenAI baseline.

Uses the Responses API. Field access is defensive for the same reason as the
Gemini adapter: verify with one live call before committing to a sweep.
"""

from __future__ import annotations

from typing import Any

from cc_ai_benchmark.adapters.base import BaseAdapter, Query, Response, register
from cc_ai_benchmark.pricing import cost


@register("openai")
class OpenAIAdapter(BaseAdapter):
    name = "openai"
    concurrency = 8

    def __init__(
        self,
        model: str,
        max_output_tokens: int = 2048,
        temperature: float | None = 0.0,
        label: str | None = None,
        **_: Any,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("openai SDK not installed. `pip install -e '.[openai]'`") from exc
        self._client = OpenAI()
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.name = label or f"openai:{model}"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": "OpenAIAdapter",
            "provider": "openai",
            "model_requested": self.model,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }

    def _invoke(self, query: Query) -> Response:
        request: dict[str, Any] = {
            "model": self.model,
            "instructions": query.system,
            "input": query.prompt,
            "max_output_tokens": self.max_output_tokens,
        }
        # Reasoning-mode models reject `temperature`; drop it rather than fail.
        if self.temperature is not None:
            request["temperature"] = self.temperature
        try:
            response = self._client.responses.create(**request)
        except Exception as exc:
            if "temperature" in str(exc).lower() and self.temperature is not None:
                request.pop("temperature")
                response = self._client.responses.create(**request)
            else:
                raise

        usage_obj = getattr(response, "usage", None)
        usage = {
            "input_tokens": getattr(usage_obj, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage_obj, "output_tokens", 0) or 0,
        }
        resolved = getattr(response, "model", None) or self.model
        return Response(
            text=getattr(response, "output_text", "") or "",
            model_id=resolved,
            usage=usage,
            cost_usd=cost(resolved, usage),
        )
