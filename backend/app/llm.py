"""Single place that talks to the AI model.

Uses the OpenAI-compatible API, so switching provider (Groq, Gemini, OpenRouter, Azure AI Foundry)
is only a change to the LLM_* settings in .env.

Models are tried as a chain: the agent's preferred model, then LLM_FALLBACK_MODELS on the same
provider, then the backup provider. A model whose quota is used up or that rejects the request as
too large is skipped straight away (retrying it would fail the same way).
"""
import json
import logging

from openai import OpenAI

from . import config

log = logging.getLogger(__name__)

ATTEMPTS_PER_MODEL = 2  # models occasionally emit malformed JSON; one retry usually fixes it

# An explicit reply budget per agent. Without one, providers reserve the model's maximum, which trips
# free-tier "output tokens per minute" limits; reasoning models also need room to think before answering.
MAX_TOKENS = {"author": 8000, "parser": 4000, "tester": 3000, "reviewer": 3000}
DEFAULT_MAX_TOKENS = 4000


def _extra_params(model: str) -> dict:
    """Model-family specific options (only gpt-oss models accept reasoning_effort)."""
    if model.startswith("openai/gpt-oss") and config.LLM_REASONING_EFFORT:
        return {"reasoning_effort": config.LLM_REASONING_EFFORT}
    return {}


class LLMError(RuntimeError):
    pass


def _client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key, max_retries=2)


def _chain(agent: str | None) -> list[tuple[str, OpenAI]]:
    chain = []
    if config.LLM_API_KEY:
        primary = _client(config.LLM_BASE_URL, config.LLM_API_KEY)
        models = [config.LLM_AGENT_MODELS.get(agent or "", config.LLM_MODEL), config.LLM_MODEL, *config.LLM_FALLBACK_MODELS]
        for model in dict.fromkeys(m for m in models if m):  # de-duplicate, keep order
            chain.append((model, primary))
    if config.LLM_FALLBACK_API_KEY and config.LLM_FALLBACK_MODEL:
        chain.append((config.LLM_FALLBACK_MODEL, _client(config.LLM_FALLBACK_BASE_URL, config.LLM_FALLBACK_API_KEY)))
    if not chain:
        raise LLMError("No AI model configured. Copy backend/.env.example to backend/.env and add LLM_API_KEY.")
    return chain


def _skip_model(error: Exception) -> bool:
    """Errors that will not go away by retrying the same model: quota used up, request too large."""
    status = getattr(error, "status_code", None)  # set on the OpenAI client's API errors
    text = str(error).lower()
    return status == 413 or (status == 429 and ("per day" in text or "quota" in text))


def _complete(system: str, user: str, parse, json_mode: bool, agent: str | None):
    errors = []
    for model, client in _chain(agent):
        for _ in range(ATTEMPTS_PER_MODEL):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    response_format={"type": "json_object"} if json_mode else None,
                    temperature=0.1,
                    max_tokens=MAX_TOKENS.get(agent or "", DEFAULT_MAX_TOKENS),
                    **_extra_params(model),
                )
                if not response.choices[0].message.content:
                    raise ValueError(f"empty reply (finish_reason={response.choices[0].finish_reason})")
                return parse(response.choices[0].message.content)
            except Exception as e:
                message = str(e)[:300]
                log.warning("Model %s failed (%s): %s", model, agent or "-", message)
                errors.append(f"{model}: {message}")
                if _skip_model(e):
                    break
    raise LLMError("All AI models failed. " + " | ".join(errors[-2:]))


def chat_json(system: str, user: str, agent: str | None = None) -> dict:
    """Send a prompt and get back a parsed JSON object."""
    return _complete(system, user, json.loads, json_mode=True, agent=agent)


def chat_text(system: str, user: str, parse=lambda text: text, agent: str | None = None):
    """Send a prompt and parse the free-text reply with `parse` (which may raise to trigger a retry)."""
    return _complete(system, user, parse, json_mode=False, agent=agent)
