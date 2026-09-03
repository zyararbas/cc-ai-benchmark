"""Anthropic baseline.

Current Claude models removed sampling parameters -- `temperature` is rejected --
so the quality/cost dial is `output_config.effort`. That means "Claude scored X"
is under-specified without the effort level, and the level is recorded in
`describe()` and belongs in any published number.
"""

from __future__ import annotations

from typing import Any

from cc_ai_benchmark.adapters.base import BaseAdapter, Query, Response, register
from cc_ai_benchmark.pricing import cost


@register("anthropic")
class AnthropicAdapter(BaseAdapter):
    name = "anthropic"
    concurrency = 8

    def __init__(
        self,
        model: str = "claude-opus-5",
        effort: str = "medium",
        max_tokens: int = 2048,
        thinking: bool = True,
        label: str | None = None,
        **_: Any,
    ):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "anthropic SDK not installed. `pip install -e '.[anthropic]'`"
            ) from exc
        self._client = anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.thinking = thinking
        self.name = label or f"anthropic:{model}"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": "AnthropicAdapter",
            "provider": "anthropic",
            "model_requested": self.model,
            "effort": self.effort,
            "thinking": "adaptive" if self.thinking else "disabled",
            "max_tokens": self.max_tokens,
            "sampling": "n/a - removed on current Claude models",
        }

    def _invoke(self, query: Query) -> Response:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "output_config": {"effort": self.effort},
            "messages": [{"role": "user", "content": query.prompt}],
        }
        if self.thinking:
            request["thinking"] = {"type": "adaptive"}
        if query.system:
            # Cache the system prefix: it is byte-identical across every item, so
            # this is close to the ideal caching shape and does not change output.
            request["system"] = [
                {
                    "type": "text",
                    "text": query.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        message = self._client.messages.create(**request)
        text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text")
        usage = {
            "input_tokens": getattr(message.usage, "input_tokens", 0),
            "output_tokens": getattr(message.usage, "output_tokens", 0),
            "cache_read_input_tokens": getattr(message.usage, "cache_read_input_tokens", 0) or 0,
            "cache_creation_input_tokens": getattr(message.usage, "cache_creation_input_tokens", 0)
            or 0,
        }
        resolved = getattr(message, "model", self.model)
        return Response(
            text=text,
            model_id=resolved,
            usage=usage,
            cost_usd=cost(resolved, usage),
            raw={"stop_reason": getattr(message, "stop_reason", None)},
        )
