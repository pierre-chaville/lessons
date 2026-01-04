"""Configuration management for the application"""

from pathlib import Path
from typing import Dict, Any
import os
import json
import yaml

CONFIG_FILE = Path(__file__).parent / "data/config.yaml"

# Default configuration
DEFAULT_CONFIG = {
    "api_key": "",
    "provider": "OpenAI",
    "correction": {
        "model": "gpt-4o",
        "prompt": "Please correct the following transcript, fixing any errors while maintaining the original meaning and style.",
        "temperature": 0.3,
    },
    "summary": {
        "max_length": 300,
        "model": "gpt-4o",
        "prompts": [
            {
                "name": "Default",
                "text": "Please provide a concise summary of the following lesson transcript.",
            }
        ],
        "temperature": 0.7,
    },
    "transcribe": {
        "beam_size": 5,
        "initial_prompt": "",
        "language": "fr",
        "vad_filter": True,
    },
    "whisper": {"compute_type": "int8", "device": "cuda", "model_size": "large-v3"},
}


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML or JSON file"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                # Merge with defaults to ensure all keys exist
                return merge_dicts(DEFAULT_CONFIG.copy(), config or {})
        else:
            # Create default config file if it doesn't exist
            save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to YAML or JSON file"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(
                config, f, default_flow_style=False, allow_unicode=True, sort_keys=False
            )
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def merge_dicts(default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dictionaries, with override taking precedence"""
    result = default.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update configuration with new values"""
    config = load_config()
    config = merge_dicts(config, updates)
    save_config(config)
    return config


def get_config_value(key_path: str, default=None) -> Any:
    """Get a specific configuration value using dot notation (e.g., 'whisper.model_size')"""
    config = load_config()
    keys = key_path.split(".")
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


def set_config_value(key_path: str, value: Any) -> bool:
    """Set a specific configuration value using dot notation"""
    config = load_config()
    keys = key_path.split(".")
    current = config

    # Navigate to the parent of the target key
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    # Set the value
    current[keys[-1]] = value
    return save_config(config)
