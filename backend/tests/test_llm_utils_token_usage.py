from __future__ import annotations

import importlib
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace


def _import_llm_utils_with_stubs(monkeypatch):
    backend_root = str(Path(__file__).resolve().parent.parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    fake_openai = types.ModuleType("langchain_openai")
    fake_openai.ChatOpenAI = type("ChatOpenAI", (), {})
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai)

    fake_anthropic = types.ModuleType("langchain_anthropic")
    fake_anthropic.ChatAnthropic = type("ChatAnthropic", (), {})
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_anthropic)

    fake_langchain_core = types.ModuleType("langchain_core")
    fake_callbacks = types.ModuleType("langchain_core.callbacks")
    fake_callbacks.BaseCallbackHandler = type("BaseCallbackHandler", (), {})
    fake_langchain_core.callbacks = fake_callbacks
    monkeypatch.setitem(sys.modules, "langchain_core", fake_langchain_core)
    monkeypatch.setitem(sys.modules, "langchain_core.callbacks", fake_callbacks)

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.dotenv_values = lambda _path: {}
    fake_dotenv.find_dotenv = lambda usecwd=True: ""
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_config = types.ModuleType("config")
    fake_config.load_config = lambda: {}
    monkeypatch.setitem(sys.modules, "config", fake_config)

    sys.modules.pop("services.llm_utils", None)
    return importlib.import_module("services.llm_utils")


def _llm_response(input_tokens: int, output_tokens: int, service_tier: str | None):
    return SimpleNamespace(
        llm_output={
            "token_usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            "service_tier": service_tier,
        },
        generations=[],
    )


def test_token_usage_tracker_is_isolated_per_worker_thread(monkeypatch):
    llm_utils = _import_llm_utils_with_stubs(monkeypatch)
    results = {}

    def record_usage(name, input_tokens, output_tokens, requested_tier=None):
        llm_utils.reset_token_usage_tracker()
        handler = llm_utils.TokenUsageCallbackHandler(
            provider="openrouter",
            model=name,
            requested_service_tier=requested_tier,
        )
        handler.on_llm_end(
            _llm_response(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                service_tier=requested_tier,
            )
        )
        results[name] = llm_utils.get_token_usage_tracker()

    threads = [
        threading.Thread(target=record_usage, args=("model-a", 10, 5, None)),
        threading.Thread(target=record_usage, args=("model-b", 100, 50, "flex")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results["model-a"]["total_tokens"] == 15
    assert results["model-a"]["model_usage"]["openrouter::model-a::default"][
        "flex_used"
    ] is False
    assert results["model-b"]["total_tokens"] == 150
    assert results["model-b"]["model_usage"]["openrouter::model-b::flex"][
        "flex_used"
    ] is True
