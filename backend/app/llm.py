"""Single place that talks to the AI model.

Uses the OpenAI-compatible API, so switching provider (Groq, Gemini, OpenRouter, Azure AI Foundry)
is only a change to the LLM_* settings in .env. If a backup model is configured, it is tried
automatically when the primary fails.
"""
import json
import logging

from openai import OpenAI

from . import config

log = logging.getLogger(__name__)

ATTEMPTS_PER_MODEL = 2  # models occasionally emit malformed JSON; one retry usually fixes it


class LLMError(RuntimeError):
    pass


def _providers() -> list[tuple[str, OpenAI]]:
    providers = []
    if config.LLM_API_KEY:
        providers.append((config.LLM_MODEL, OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, max_retries=2)))
    if config.LLM_FALLBACK_API_KEY and config.LLM_FALLBACK_MODEL:
        providers.append((
            config.LLM_FALLBACK_MODEL,
            OpenAI(base_url=config.LLM_FALLBACK_BASE_URL, api_key=config.LLM_FALLBACK_API_KEY, max_retries=2),
        ))
    if not providers:
        raise LLMError("No AI model configured. Copy backend/.env.example to backend/.env and add LLM_API_KEY.")
    return providers


def _complete(system: str, user: str, parse, json_mode: bool):
    errors = []
    for model, client in _providers():
        for _ in range(ATTEMPTS_PER_MODEL):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    response_format={"type": "json_object"} if json_mode else None,
                    temperature=0.1,
                )
                return parse(response.choices[0].message.content)
            except Exception as e:
                message = str(e)[:300]
                log.warning("Model %s failed: %s", model, message)
                errors.append(f"{model}: {message}")
    raise LLMError("All AI models failed. " + " | ".join(errors[-2:]))


def chat_json(system: str, user: str) -> dict:
    """Send a prompt and get back a parsed JSON object, trying the backup model on failure."""
    return _complete(system, user, json.loads, json_mode=True)


def chat_text(system: str, user: str, parse=lambda text: text):
    """Send a prompt and parse the free-text reply with `parse` (which may raise to trigger a retry)."""
    return _complete(system, user, parse, json_mode=False)
