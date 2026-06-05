"""Utility functions for LLM operations using LangChain"""
from typing import Union, Optional, Dict, Any
from threading import Lock
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import BaseCallbackHandler
import sys
from pathlib import Path
import os
import logging
from dotenv import dotenv_values, find_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import load_config

logger = logging.getLogger(__name__)
_token_usage_lock = Lock()
_token_usage: Dict[str, Any] = {
    "input_tokens": 0,
    "output_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "model_usage": {},
}


def _default_model_for_provider(provider: str) -> str:
    provider_lc = (provider or "").lower()
    if provider_lc == "anthropic":
        return "claude-3-5-sonnet-20241022"
    if provider_lc == "openrouter":
        return "openai/gpt-4.1-mini"
    return "gpt-4.1"


def reset_token_usage_tracker() -> None:
    """Reset token usage tracker for the current context."""
    with _token_usage_lock:
        _token_usage["input_tokens"] = 0
        _token_usage["output_tokens"] = 0
        _token_usage["completion_tokens"] = 0
        _token_usage["total_tokens"] = 0
        _token_usage["model_usage"] = {}


def get_token_usage_tracker() -> Dict[str, Any]:
    """Get aggregated token usage for the current context."""
    with _token_usage_lock:
        return {
            "input_tokens": int(_token_usage.get("input_tokens", 0)),
            "output_tokens": int(_token_usage.get("output_tokens", 0)),
            "completion_tokens": int(_token_usage.get("completion_tokens", 0)),
            "total_tokens": int(_token_usage.get("total_tokens", 0)),
            "model_usage": {
                k: {
                    "provider": v.get("provider"),
                    "model": v.get("model"),
                    "service_tier": v.get("service_tier"),
                    "service_tier_source": v.get("service_tier_source"),
                    "flex_used": bool(v.get("flex_used", False)),
                    "input_tokens": int(v.get("input_tokens", 0)),
                    "output_tokens": int(v.get("output_tokens", 0)),
                    "completion_tokens": int(v.get("completion_tokens", 0)),
                    "total_tokens": int(v.get("total_tokens", 0)),
                }
                for k, v in (_token_usage.get("model_usage", {}) or {}).items()
            },
        }


def _accumulate_token_usage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    service_tier: Optional[str] = None,
    service_tier_source: Optional[str] = None,
) -> None:
    with _token_usage_lock:
        input_int = max(0, int(input_tokens or 0))
        output_int = max(0, int(output_tokens or 0))
        total_int = max(0, int(total_tokens or 0))

        _token_usage["input_tokens"] += input_int
        _token_usage["output_tokens"] += output_int
        # Keep completion_tokens as alias of output_tokens for compatibility.
        _token_usage["completion_tokens"] += output_int
        _token_usage["total_tokens"] += total_int

        if provider and model:
            tier = service_tier.strip().lower() if service_tier else None
            key = f"{provider.strip().lower()}::{model.strip()}::{tier or 'default'}"
            model_usage = _token_usage.setdefault("model_usage", {})
            if key not in model_usage:
                model_usage[key] = {
                    "provider": provider.strip(),
                    "model": model.strip(),
                    "service_tier": tier,
                    "service_tier_source": service_tier_source,
                    "flex_used": tier == "flex",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }
            elif tier == "flex":
                model_usage[key]["flex_used"] = True
                if service_tier_source:
                    model_usage[key]["service_tier_source"] = service_tier_source
            model_usage[key]["input_tokens"] += input_int
            model_usage[key]["output_tokens"] += output_int
            model_usage[key]["completion_tokens"] += output_int
            model_usage[key]["total_tokens"] += total_int


def _extract_usage_from_llm_result(response: Any) -> Dict[str, Any]:
    """Best-effort extraction of token usage from a LangChain LLM result."""
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    service_tier: Optional[str] = None
    usage_found = False

    def _assign_service_tier(metadata: Dict[str, Any]) -> None:
        nonlocal service_tier
        if service_tier or not metadata:
            return
        raw_tier = metadata.get("service_tier")
        if raw_tier is not None:
            service_tier = str(raw_tier).strip().lower() or None

    def _assign_from_usage(usage: Dict[str, Any]) -> bool:
        nonlocal input_tokens, output_tokens, total_tokens
        if not usage:
            return False
        input_tokens = int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or 0
        )
        output_tokens = int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        )
        total_tokens = int(usage.get("total_tokens") or 0)
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens
        return (input_tokens + output_tokens + total_tokens) > 0

    try:
        llm_output = getattr(response, "llm_output", None) or {}
        token_usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        _assign_service_tier(llm_output)
        _assign_service_tier(token_usage)
        if _assign_from_usage(token_usage):
            usage_found = True
    except Exception:
        pass

    try:
        generations = getattr(response, "generations", None) or []
        for batch in generations:
            for generation in batch:
                message = getattr(generation, "message", None)
                response_metadata = getattr(message, "response_metadata", None) or {}
                _assign_service_tier(response_metadata)
                token_usage = response_metadata.get("token_usage", {}) or {}
                _assign_service_tier(token_usage)
                if not usage_found and _assign_from_usage(token_usage):
                    usage_found = True
                usage_metadata = getattr(message, "usage_metadata", None) or {}
                _assign_service_tier(usage_metadata)
                if not usage_found and _assign_from_usage(usage_metadata):
                    usage_found = True
    except Exception:
        pass

    return {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "service_tier": service_tier,
    }


def register_token_usage_from_response(response: Any) -> None:
    """Best-effort usage extraction from direct LLM message responses."""
    if response is None:
        return

    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    service_tier: Optional[str] = None

    try:
        usage_metadata = getattr(response, "usage_metadata", None) or {}
        input_tokens += usage_metadata.get("input_tokens", 0) or 0
        output_tokens += usage_metadata.get("output_tokens", 0) or 0
        total_tokens += usage_metadata.get("total_tokens", 0) or 0
        raw_tier = usage_metadata.get("service_tier")
        if raw_tier is not None:
            service_tier = str(raw_tier).strip().lower() or None
    except Exception:
        pass

    try:
        response_metadata = getattr(response, "response_metadata", None) or {}
        raw_tier = response_metadata.get("service_tier")
        if raw_tier is not None:
            service_tier = str(raw_tier).strip().lower() or None
        token_usage = response_metadata.get("token_usage", {}) or {}
        input_tokens += token_usage.get("prompt_tokens", 0) or token_usage.get(
            "input_tokens", 0
        ) or 0
        output_tokens += token_usage.get("completion_tokens", 0) or token_usage.get(
            "output_tokens", 0
        ) or 0
        total_tokens += token_usage.get("total_tokens", 0) or 0
        raw_tier = token_usage.get("service_tier")
        if raw_tier is not None:
            service_tier = str(raw_tier).strip().lower() or None
    except Exception:
        pass

    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens

    _accumulate_token_usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        service_tier=service_tier,
    )


class TokenUsageCallbackHandler(BaseCallbackHandler):
    """Callback handler that aggregates token usage per task context."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        requested_service_tier: Optional[str] = None,
    ):
        self.provider = provider
        self.model = model
        self.requested_service_tier = (
            requested_service_tier.strip().lower() if requested_service_tier else None
        )

    def on_llm_end(self, response, **kwargs) -> None:
        usage = _extract_usage_from_llm_result(response)
        response_service_tier = usage.get("service_tier")
        service_tier = response_service_tier or self.requested_service_tier
        _accumulate_token_usage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            provider=self.provider,
            model=self.model,
            service_tier=service_tier,
            service_tier_source="response" if response_service_tier else (
                "request" if service_tier else None
            ),
        )

def _load_api_key_from_env_file(key_name: str) -> str:
    candidates = [
        find_dotenv(usecwd=True),
        str(Path(__file__).parent.parent / ".env"),
        str(Path(__file__).parent / ".env"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.exists():
            continue
        values = dotenv_values(path)
        value = values.get(key_name, "")
        if value:
            return value.strip()
    return ""


def _get_api_key_for_provider(provider: str) -> str:
    if provider.lower() == "openai":
        return os.getenv("OPENAI_API_KEY", "") or _load_api_key_from_env_file(
            "OPENAI_API_KEY"
        )
    if provider.lower() == "openrouter":
        return os.getenv("OPENROUTER_API_KEY", "") or _load_api_key_from_env_file(
            "OPENROUTER_API_KEY"
        )
    if provider.lower() == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY", "") or _load_api_key_from_env_file(
            "ANTHROPIC_API_KEY"
        )
    return ""


def get_llm_model(
    task_name: str = None,
    temperature: float = None,
    model: str = None,
    max_tokens: int = None,
    provider: Optional[str] = None,
    thinking_mode: Optional[Dict[str, Any]] = None,
    use_flex: bool = False,
) -> Union[ChatOpenAI, ChatAnthropic]:
    """
    Get an LLM model instance based on the configured provider.
    
    Args:
        task_name: Optional task name to load specific config (e.g., 'correction', 'summary')
        temperature: Optional temperature override
        model: Optional model name override
        
    Returns:
        ChatOpenAI or ChatAnthropic instance configured with API key and settings
        
    Raises:
        ValueError: If provider is not supported or API key is missing
    """
    config = load_config()
    
    # Get provider and API key from config/.env
    selected_provider = provider or config.get('provider', 'OpenAI')
    
    # Load task-specific config if task_name is provided
    if task_name and task_name in config:
        task_config = config[task_name]
        task_provider = task_config.get('provider')
        if task_provider and provider is None:
            selected_provider = task_provider
        if temperature is None:
            temperature = task_config.get('temperature', 0.7)
        if model is None:
            task_model = task_config.get('model')
            if task_model:
                model = task_model
            else:
                model = _default_model_for_provider(selected_provider)
        if max_tokens is None:
            max_tokens = task_config.get('max_tokens')
    else:
        # Use defaults if no task specified
        if temperature is None:
            temperature = 0.7
        if model is None:
            model = _default_model_for_provider(selected_provider)
    
    # Normalize model for provider if it looks incompatible
    if selected_provider.lower() == "anthropic":
        if model and ("gpt" in model.lower() or model.lower().startswith("o")):
            logger.warning(
                "Model '%s' looks OpenAI-specific; defaulting to Claude for Anthropic.",
                model,
            )
            model = "claude-3-5-sonnet-20241022"
    elif selected_provider.lower() == "openai":
        if model and "claude" in model.lower():
            logger.warning(
                "Model '%s' looks Anthropic-specific; defaulting to gpt-4o for OpenAI.",
                model,
            )
            model = "gpt-4o"

    # Return appropriate model based on provider
    if selected_provider.lower() == 'openai':
        api_key = _get_api_key_for_provider(selected_provider)
        if not api_key:
            raise ValueError(
                f"API key not found for provider {selected_provider}. Set {selected_provider.upper()}_API_KEY in .env"
            )
        params = {
            "api_key": api_key,
            "model": model,
            "temperature": temperature,
            "callbacks": [TokenUsageCallbackHandler(provider=selected_provider, model=model)],
        }
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if thinking_mode:
            logger.warning(
                "Ignoring thinking_mode for OpenAI ChatCompletions provider because "
                "it is not supported in this integration."
            )
        return ChatOpenAI(**params)
    elif selected_provider.lower() == "openrouter":
        api_key = _get_api_key_for_provider(selected_provider)
        if not api_key:
            raise ValueError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY in .env"
            )
        params = {
            "api_key": api_key,
            "base_url": "https://openrouter.ai/api/v1",
            "model": model or "openai/gpt-4o-mini",
            "temperature": temperature,
            "callbacks": [
                TokenUsageCallbackHandler(
                    provider=selected_provider,
                    model=(model or "openai/gpt-4o-mini"),
                    requested_service_tier="flex" if use_flex else None,
                )
            ],
        }
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        extra_body: Dict[str, Any] = {}
        if thinking_mode:
            # Pass provider-specific body for OpenRouter without leaking unknown
            # top-level kwargs into ChatCompletions.create().
            extra_body["reasoning"] = thinking_mode
        if use_flex:
            extra_body["service_tier"] = "flex"
        if extra_body:
            params["extra_body"] = extra_body
        return ChatOpenAI(**params)
    elif selected_provider.lower() == 'anthropic':
        api_key = _get_api_key_for_provider(selected_provider)
        if not api_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY in .env"
            )
        params = {
            "api_key": api_key,
            "model": model,
            "temperature": temperature,
            "callbacks": [TokenUsageCallbackHandler(provider=selected_provider, model=model)],
        }
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if thinking_mode:
            params["thinking"] = thinking_mode
        return ChatAnthropic(**params)
    else:
        raise ValueError(
            f"Unsupported provider: {selected_provider}. "
            "Supported providers are: 'OpenAI', 'OpenRouter', and 'Anthropic'"
        )

