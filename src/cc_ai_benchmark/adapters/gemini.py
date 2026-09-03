"""Google Gemini baseline.

Written against the `google-genai` SDK surface. Because SDK shapes move, every
field is read defensively: an unexpected response shape degrades to missing
usage rather than a crash, and `cc-ai-benchmark verify` makes one live call per
system so a shape problem surfaces for pennies instead of mid-sweep.
"""

from __future__ import annotations

import os
from typing import Any

from cc_ai_benchmark.adapters.base import BaseAdapter, Query, Response, register
from cc_ai_benchmark.pricing import cost


def _resolve(value: str | None, fallback_env: str) -> str | None:
    """Expand ${VAR} from the environment, or fall back to a standard variable.

    This repo is public. A GCP project id is not a credential, but it is an
    internal identifier and it does not belong in a committed config file, so
    config/models.json carries the variable name and the environment carries
    the value. The resolved value still lands in the report, because which
    project answered is part of what a result means.
    """
    if value:
        expanded = os.path.expandvars(value)
        # expandvars leaves an unset ${VAR} untouched rather than emptying it.
        if "${" not in expanded:
            return expanded
    return os.environ.get(fallback_env)


def _usage(response: Any) -> dict[str, int]:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return {}
    prompt = getattr(meta, "prompt_token_count", 0) or 0
    cached = getattr(meta, "cached_content_token_count", 0) or 0
    # Gemini counts cached tokens inside prompt_token_count; Anthropic reports
    # them separately. Pricing bills the two fields at different rates, so the
    # overlap has to come out here or a cached run is billed twice for the same
    # tokens -- which would land hardest on the full-corpus approach, the one
    # run whose whole argument is that caching makes it affordable.
    return {
        "input_tokens": max(prompt - cached, 0),
        "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        "cache_read_input_tokens": cached,
    }


class _GeminiBase(BaseAdapter):
    concurrency = 8

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        max_output_tokens: int = 2048,
        label: str | None = None,
        vertex: bool = False,
        project: str | None = None,
        location: str | None = None,
        **_: Any,
    ):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "google-genai SDK not installed. `pip install -e '.[gemini]'`"
            ) from exc
        self._genai = genai
        self._types = types
        # Which backend answered is part of what a result means: the same model
        # id on Vertex and on AI Studio is a different endpoint, a different
        # quota and a different bill. Take it from config so the report records
        # it, rather than from whatever env vars the shell happened to carry.
        self.vertex = vertex
        self.project = _resolve(project, "GOOGLE_CLOUD_PROJECT")
        self.location = _resolve(location, "GOOGLE_CLOUD_LOCATION") or "global"
        if vertex and not self.project:
            raise RuntimeError(
                "Vertex backend needs a project: set $GOOGLE_CLOUD_PROJECT "
                "(see docs/TRIGGERING.md) or put a literal id in config/models.json"
            )
        if vertex:
            self._client = genai.Client(vertexai=True, project=self.project, location=self.location)
        else:
            self._client = genai.Client()
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.name = label or f"gemini:{model}"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": type(self).__name__,
            "provider": "google",
            "backend": "vertex" if self.vertex else "ai-studio",
            "project": self.project,
            "location": self.location,
            "model_requested": self.model,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }

    def _config(self, query: Query) -> Any:
        return self._types.GenerateContentConfig(
            system_instruction=query.system,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            response_mime_type="application/json",
        )

    def _invoke(self, query: Query) -> Response:
        response = self._client.models.generate_content(
            model=self.model,
            contents=query.prompt,
            config=self._config(query),
        )
        usage = _usage(response)
        resolved = getattr(response, "model_version", None) or self.model
        return Response(
            text=getattr(response, "text", "") or "",
            model_id=resolved,
            usage=usage,
            cost_usd=cost(resolved, usage),
        )


@register("gemini")
class GeminiAdapter(_GeminiBase):
    """Any Gemini model; the id comes from config/models.json."""

    name = "gemini"
