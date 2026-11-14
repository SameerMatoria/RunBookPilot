"""The model chain: agent preference, fallback models, and skipping exhausted models."""
import pytest

from app import config, llm


class FakeCompletions:
    def __init__(self, behaviour):
        self.behaviour = behaviour  # model -> list of outcomes ("ok" or an exception), consumed in order
        self.calls, self.kwargs = [], []
        self.content = None  # reply text; default: {"model": "<model>"}

    def create(self, model, **kwargs):
        self.calls.append(model)
        self.kwargs.append(kwargs)
        outcome = self.behaviour[model].pop(0) if self.behaviour.get(model) else "ok"
        if isinstance(outcome, Exception):
            raise outcome
        message = type("M", (), {"content": self.content or '{"model": "%s"}' % model})
        return type("R", (), {"choices": [type("C", (), {"message": message})]})


class StatusError(Exception):
    """Stands in for the OpenAI client's API errors, which carry a status_code."""

    def __init__(self, code, text):
        super().__init__(text)
        self.status_code = code


def status_error(code, text):
    return StatusError(code, text)


@pytest.fixture
def fake(monkeypatch):
    completions = FakeCompletions({})
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})})
    monkeypatch.setattr(llm, "_client", lambda base_url, api_key: client)
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    monkeypatch.setattr(config, "LLM_MODEL", "big")
    monkeypatch.setattr(config, "LLM_FALLBACK_MODELS", ["medium", "small"])
    monkeypatch.setattr(config, "LLM_AGENT_MODELS", {"parser": "small", "author": "", "tester": "", "reviewer": ""})
    monkeypatch.setattr(config, "LLM_FALLBACK_API_KEY", "")
    return completions


def test_agent_preference_comes_first(fake):
    assert llm.chat_json("s", "u", agent="parser") == {"model": "small"}
    assert llm.chat_json("s", "u", agent="author") == {"model": "big"}


def test_daily_quota_skips_to_next_model_without_retrying(fake):
    fake.behaviour = {"big": [status_error(429, "Rate limit reached on tokens per day (TPD)")]}
    assert llm.chat_json("s", "u") == {"model": "medium"}
    assert fake.calls == ["big", "medium"]


def test_request_too_large_skips_to_next_model(fake):
    fake.behaviour = {"big": [status_error(413, "Request too large")]}
    assert llm.chat_json("s", "u") == {"model": "medium"}


def test_bad_json_is_retried_on_same_model(fake):
    fake.behaviour = {"big": [ValueError("bad json")]}
    assert llm.chat_json("s", "u") == {"model": "big"}
    assert fake.calls == ["big", "big"]


def test_json_mode_can_be_switched_off(fake, monkeypatch):
    monkeypatch.setattr(config, "LLM_JSON_MODE", False)
    fake.content = 'Here it is:\n```json\n{"steps": [1, 2]}\n```'
    assert llm.chat_json("s", "u") == {"steps": [1, 2]}
    assert fake.kwargs[-1]["response_format"] is None


def test_json_mode_is_on_by_default(fake):
    llm.chat_json("s", "u")
    assert fake.kwargs[-1]["response_format"] == {"type": "json_object"}


def test_reasoning_effort_for_gpt_oss_under_any_provider_name():
    assert "reasoning_effort" in llm._extra_params("openai/gpt-oss-120b")  # Groq
    assert "reasoning_effort" in llm._extra_params("gpt-oss-120b")  # Azure deployment name
    assert llm._extra_params("gpt-4.1-mini") == {}


def test_all_models_failing_raises(fake):
    quota = lambda: status_error(429, "tokens per day")  # noqa: E731
    fake.behaviour = {"big": [quota()], "medium": [quota()], "small": [quota()]}
    with pytest.raises(llm.LLMError):
        llm.chat_json("s", "u")
