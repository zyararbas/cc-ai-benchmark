"""Listing the model ids a provider will actually accept.

config/models.json demands exact snapshot ids, on the grounds that a floating
alias silently redefines what a published number means. That is the right rule
and it creates an obvious problem: somebody has to know the ids. Guessing them
from memory is how a sweep ends up reporting a model nobody ran.

So ask the provider. Every one of these is a catalogue call - it lists what the
key can reach and spends no tokens - which makes it the cheapest possible way
to turn a FILL-IN into something real.
"""

from __future__ import annotations

import os
from typing import Any

Row = dict[str, Any]


class ProviderUnavailable(RuntimeError):
    """The SDK is missing, or the credential for it is not in the environment."""


def _require(env: str, provider: str) -> None:
    if not os.environ.get(env):
        raise ProviderUnavailable(f"{provider}: ${env} is not set in this environment")


def anthropic_models() -> list[Row]:
    _require("ANTHROPIC_API_KEY", "anthropic")
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise ProviderUnavailable(
            "anthropic SDK not installed: pip install -e '.[anthropic]'"
        ) from exc
    rows = []
    for model in Anthropic().models.list(limit=100):
        rows.append(
            {
                "id": model.id,
                "name": getattr(model, "display_name", "") or "",
                "created": str(getattr(model, "created_at", "") or "")[:10],
            }
        )
    return rows


def gemini_models() -> list[Row]:
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise ProviderUnavailable("gemini: neither $GEMINI_API_KEY nor $GOOGLE_API_KEY is set")
    try:
        from google import genai
    except ImportError as exc:
        raise ProviderUnavailable(
            "google-genai SDK not installed: pip install -e '.[gemini]'"
        ) from exc
    rows = []
    for model in genai.Client().models.list():
        actions = getattr(model, "supported_actions", None) or []
        if actions and "generateContent" not in actions:
            continue
        identifier = (getattr(model, "name", "") or "").removeprefix("models/")
        if not identifier:
            continue
        rows.append(
            {
                "id": identifier,
                "name": getattr(model, "display_name", "") or "",
                "created": "",
            }
        )
    return rows


def openai_models() -> list[Row]:
    _require("OPENAI_API_KEY", "openai")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ProviderUnavailable("openai SDK not installed: pip install -e '.[openai]'") from exc
    import datetime as _dt

    rows = []
    for model in OpenAI().models.list():
        created = getattr(model, "created", None)
        stamp = ""
        if created:
            stamp = _dt.datetime.fromtimestamp(created, _dt.UTC).date().isoformat()
        rows.append(
            {"id": model.id, "name": getattr(model, "owned_by", "") or "", "created": stamp}
        )
    return rows


PROVIDERS = {
    "anthropic": anthropic_models,
    "gemini": gemini_models,
    "openai": openai_models,
}


def discover(provider: str) -> list[Row]:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r} (have: {', '.join(PROVIDERS)})")
    rows = PROVIDERS[provider]()
    return sorted(rows, key=lambda r: (r["created"], r["id"]), reverse=True)
