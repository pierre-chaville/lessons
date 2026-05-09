"""Utility functions for LLM operations using LangChain"""
from typing import Union, Optional, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
import sys
from pathlib import Path
import os
import logging
from dotenv import dotenv_values, find_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import load_config

logger = logging.getLogger(__name__)


def _default_model_for_provider(provider: str) -> str:
    provider_lc = (provider or "").lower()
    if provider_lc == "anthropic":
        return "claude-3-5-sonnet-20241022"
    if provider_lc == "openrouter":
        return "openai/gpt-4.1-mini"
    return "gpt-4.1"

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
        }
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if thinking_mode:
            # Pass provider-specific body for OpenRouter without leaking unknown
            # top-level kwargs into ChatCompletions.create().
            params["extra_body"] = {"reasoning": thinking_mode}
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

