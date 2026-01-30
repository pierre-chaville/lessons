"""Configuration management for the application"""

from pathlib import Path
from typing import Dict, Any
import json
import yaml
from sqlmodel import Session
from dotenv import load_dotenv, find_dotenv

from database import engine, create_db_and_tables
from models import AppConfig

CONFIG_FILE = Path(__file__).parent / "data/config.yaml"
CONFIG_RECORD_ID = 1

# Default configuration
DEFAULT_CONFIG = {
    "correction": {
        "provider": "OpenAI",
        "model": "gpt-4o",
        "prompt": "Please correct the following transcript, fixing any errors while maintaining the original meaning and style.",
        "temperature": 0.3,
        "max_tokens": 16000,
    },
    "edition": {
        "provider": "OpenAI",
        "model": "gpt-4o",
        "prompt": "Please rewrite the following transcript in a clear, written style, maintaining the original meaning and flow. Include timing information (start/end) and cite any sources mentioned.",
        "temperature": 0.5,
        "max_tokens": 16000,
    },
    "summary": {
        "max_length": 300,
        "provider": "OpenAI",
        "model": "gpt-4o",
        "prompts": [
            {
                "name": "Default",
                "text": "Please provide a concise summary of the following lesson transcript.",
            }
        ],
        "temperature": 0.7,
        "max_tokens": 4000,
        "brief": {
            "provider": "OpenAI",
            "model": "gpt-4o",
            "prompt": "Please provide a brief 1-3 line summary of the following lesson transcript.",
            "temperature": 0.5,
            "max_tokens": 1000,
        },
    },
    "extraction": {
        "provider": "OpenAI",
        "model": "gpt-4o",
        "prompt": "Please extract any sources mentioned in the edited transcript.",
        "temperature": 0.3,
        "max_tokens": 4000,
    },
    "sources": {
        "provider": "OpenAI",
        "model": "gpt-4o",
        "prompt": "Please verify sources and provide standardized references.",
        "temperature": 0.3,
        "max_tokens": 4000,
    },
    "transcribe": {
        "beam_size": 5,
        "initial_prompt": "",
        "language": "fr",
        "vad_filter": True,
    },
    "whisper": {"compute_type": "int8", "device": "cuda", "model_size": "large-v3"},
}


def _load_env_file() -> None:
    """Load environment variables from .env files if present."""
    load_dotenv(find_dotenv(usecwd=True), override=True, encoding="utf-8-sig")
    load_dotenv(Path(__file__).parent / ".env", override=True, encoding="utf-8-sig")
    load_dotenv(Path(__file__).parent.parent / ".env", override=True, encoding="utf-8-sig")


def _sanitize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Remove sensitive keys before persisting configuration."""
    if not config:
        return {}
    cleaned = dict(config)
    cleaned.pop("api_key", None)
    return cleaned


def _get_db_config(session: Session) -> Dict[str, Any]:
    record = session.get(AppConfig, CONFIG_RECORD_ID)
    if record and isinstance(record.data, dict):
        return record.data
    return {}


def _save_db_config(session: Session, config: Dict[str, Any]) -> None:
    record = session.get(AppConfig, CONFIG_RECORD_ID)
    if record is None:
        record = AppConfig(id=CONFIG_RECORD_ID, data=config)
        session.add(record)
    else:
        record.data = config
    session.commit()


def load_config() -> Dict[str, Any]:
    """Load configuration from DB (seeded from config.yaml if empty)."""
    _load_env_file()
    try:
        create_db_and_tables()
        with Session(engine) as session:
            db_config = _get_db_config(session)
            if not db_config:
                file_config = {}
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        file_config = yaml.safe_load(f) or {}
                merged = merge_dicts(DEFAULT_CONFIG.copy(), file_config)
                merged = _sanitize_config(merged)
                _save_db_config(session, merged)
                return merged

            merged = merge_dicts(DEFAULT_CONFIG.copy(), db_config)
            cleaned = _sanitize_config(merged)
            if "api_key" in db_config:
                _save_db_config(session, cleaned)
            return cleaned
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to DB."""
    try:
        create_db_and_tables()
        with Session(engine) as session:
            cleaned = _sanitize_config(config)
            _save_db_config(session, cleaned)
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
    updates = _sanitize_config(updates or {})
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
