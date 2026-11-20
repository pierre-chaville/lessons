import pytest
from pydantic import BaseModel

from bench import steps

CLAUDE_THINKING_ERROR = (
    "Error code: 400 - {'error': {'message': 'Provider returned error', 'code': 400, 'metadata': {'raw': "
    "'{\"type\":\"error\",\"error\":{\"type\":\"invalid_request_error\",\"message\":\"tool_choice: type "
    "\\\\\"tool\\\\\" and \\\\\"any\\\\\" are not supported for this model.\"}}'}}}"
)


class Answer(BaseModel):
    text: str


class FakeClient:
    closed = False

    async def close(self):
        self.closed = True


class FakeLLM:
    """Refuses the default method (forced tool call) like Claude with thinking; unusable once its
    HTTP client is closed (by run_async), like ChatOpenAI."""

    def __init__(self, error: str, methods: list):
        self.error, self.methods = error, methods
        self.root_async_client = FakeClient()

    def with_structured_output(self, schema, include_raw=True, method=None):
        self.methods.append(method)
        llm = self

        class Structured:
            async def ainvoke(self, prompt):
                if llm.root_async_client.closed:
                    raise RuntimeError("Connection error.")
                if method is None:
                    raise RuntimeError(llm.error)
                return {"raw": None, "parsed": schema(text="ok"), "parsing_error": None}

        return Structured()


def call(monkeypatch, error, **params):
    methods = []
    monkeypatch.setattr(steps, "_build_llm", lambda *a, **k: FakeLLM(error, methods))
    parsed, _ = steps.structured_call(Answer, "prompt", provider="openrouter", model="anthropic/claude",
                                      params=params, timeout=10)
    return parsed, methods


def test_falls_back_to_json_schema_when_forced_tools_are_refused(monkeypatch):
    parsed, methods = call(monkeypatch, CLAUDE_THINKING_ERROR)
    assert parsed.text == "ok" and methods == [None, "json_schema"]


def test_other_errors_and_explicit_method_are_not_retried(monkeypatch):
    with pytest.raises(RuntimeError):
        call(monkeypatch, "Error code: 401 - unauthorized")
    parsed, methods = call(monkeypatch, CLAUDE_THINKING_ERROR, structured_output_method="json_schema")
    assert parsed.text == "ok" and methods == ["json_schema"]
