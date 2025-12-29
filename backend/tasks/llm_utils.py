"""Utility functions for LLM operations using LangChain"""
from typing import Union
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import load_config


def get_llm_model(
    task_name: str = None,
    temperature: float = None,
    model: str = None
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
    
    # Get provider and API key from config
    provider = config.get('provider', 'OpenAI')
    api_key = config.get('api_key', '')
    
    if not api_key:
        raise ValueError(
            "API key not found in config. Please set the 'api_key' in config.yaml"
        )
    
    # Load task-specific config if task_name is provided
    if task_name and task_name in config:
        task_config = config[task_name]
        if temperature is None:
            temperature = task_config.get('temperature', 0.7)
        if model is None:
            model = task_config.get('model', 'gpt-4o')
    else:
        # Use defaults if no task specified
        if temperature is None:
            temperature = 0.7
        if model is None:
            model = 'gpt-4o' if provider.lower() == 'openai' else 'claude-3-5-sonnet-20241022'
    
    # Return appropriate model based on provider
    if provider.lower() == 'openai':
        return ChatOpenAI(
            api_key=api_key,
            model=model,
            temperature=temperature
        )
    elif provider.lower() == 'anthropic':
        return ChatAnthropic(
            api_key=api_key,
            model=model,
            temperature=temperature
        )
    else:
        raise ValueError(
            f"Unsupported provider: {provider}. "
            "Supported providers are: 'OpenAI' and 'Anthropic'"
        )

