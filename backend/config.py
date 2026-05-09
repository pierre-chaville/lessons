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
MIN_SUMMARY_PROMPT_MAX_LENGTH = 50
DEFAULT_SUMMARY_PROMPT_MAX_LENGTH = 300
DEFAULT_BRIEF_MAX_TOKENS = 1000

# Default configuration
DEFAULT_CONFIG = {
    "correction": {
        "provider": "OpenAI",
        "model": "gpt-4o",
        "prompts": [
            {
                "name": "Default",
                "text": "Please correct the following transcript, fixing any errors while maintaining the original meaning and style.",
            }
        ],
        "temperature": 0.3,
        "max_tokens": 16000,
    },
    "edition": {
        "provider": "OpenAI",
        "model": "gpt-4o",
        "prompts": [
            {
                "name": "Default",
                "text": "Please rewrite the following transcript in a clear, written style, maintaining the original meaning and flow. Include timing information (start/end) and cite any sources mentioned.",
            }
        ],
        "temperature": 0.5,
        "max_tokens": 16000,
    },
    "summary": {
        "prompts": [
            {
                "name": "Default",
                "text": "Please provide a concise summary of the following lesson transcript.",
                "model_preset_id": None,
                "max_length": 300,
            }
        ],
    },
    "brief": {
        "model_preset_id": None,
        "prompt": "Please provide a brief 1-3 line summary of the following lesson transcript.",
        "max_tokens": DEFAULT_BRIEF_MAX_TOKENS,
    },
    "extraction": {
        "provider": "OpenAI",
        "model": "gpt-4o",
        "prompts": [
            {
                "name": "Default",
                "text": "Please extract any sources mentioned in the edited transcript.",
            }
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
    },
    "sources": {
        "provider": "OpenAI",
        "model": "gpt-4o",
        "prompts": [
            {
                "name": "Default",
                "text": "Please verify sources and provide standardized references.",
            }
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
    },
    "transcribe": {
        "model": "nova-3",
        "language": "fr",
    },
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


def _migrate_legacy_brief_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Promote legacy summary.brief config to top-level brief config."""
    if not config:
        return {}

    migrated = dict(config)
    summary = migrated.get("summary")
    if isinstance(summary, dict):
        legacy_brief = summary.get("brief")
        if legacy_brief is not None:
            if "brief" not in migrated:
                migrated["brief"] = legacy_brief
            summary_copy = dict(summary)
            summary_copy.pop("brief", None)
            migrated["summary"] = summary_copy
    return migrated


def _migrate_summary_prompt_model_presets(config: Dict[str, Any]) -> Dict[str, Any]:
    """Move legacy summary model settings to prompt-level prompt settings."""
    if not config:
        return {}

    migrated = dict(config)
    summary = migrated.get("summary")
    if not isinstance(summary, dict):
        return migrated

    summary_copy = dict(summary)
    legacy_max_length = summary_copy.get(
        "max_length", DEFAULT_SUMMARY_PROMPT_MAX_LENGTH
    )
    prompts = summary_copy.get("prompts", [])
    if not prompts and summary_copy.get("prompt"):
        prompts = [{"name": "Default", "text": summary_copy.get("prompt")}]

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)
        prompt_copy.setdefault("model_preset_id", None)
        prompt_copy.setdefault(
            "max_length", legacy_max_length or DEFAULT_SUMMARY_PROMPT_MAX_LENGTH
        )
        normalized_prompts.append(prompt_copy)
    if normalized_prompts:
        summary_copy["prompts"] = normalized_prompts

    # Remove legacy summary-level model tuning fields.
    for key in ("provider", "model", "temperature", "max_tokens", "prompt", "max_length"):
        summary_copy.pop(key, None)

    migrated["summary"] = summary_copy
    return migrated


def _normalize_summary_prompt_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize per-prompt summary max_length to a safe integer minimum."""
    if not config:
        return {}

    normalized = dict(config)
    summary = normalized.get("summary")
    if not isinstance(summary, dict):
        return normalized

    summary_copy = dict(summary)
    prompts = summary_copy.get("prompts")
    if not isinstance(prompts, list):
        normalized["summary"] = summary_copy
        return normalized

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)
        raw_max_length = prompt_copy.get(
            "max_length", DEFAULT_SUMMARY_PROMPT_MAX_LENGTH
        )
        try:
            prompt_max_length = int(raw_max_length)
        except (TypeError, ValueError):
            prompt_max_length = DEFAULT_SUMMARY_PROMPT_MAX_LENGTH
        prompt_copy["max_length"] = max(MIN_SUMMARY_PROMPT_MAX_LENGTH, prompt_max_length)
        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        summary_copy["prompts"] = normalized_prompts
    normalized["summary"] = summary_copy
    return normalized


def _normalize_brief_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize brief config to model_preset_id/max_tokens/prompt shape."""
    if not config:
        return {}

    normalized = dict(config)
    brief = normalized.get("brief")
    if not isinstance(brief, dict):
        normalized["brief"] = dict(DEFAULT_CONFIG["brief"])
        return normalized

    brief_copy = dict(brief)
    prompt = brief_copy.get("prompt")
    if not isinstance(prompt, str):
        prompt = DEFAULT_CONFIG["brief"]["prompt"]
    brief_copy["prompt"] = prompt

    raw_model_preset_id = brief_copy.get("model_preset_id")
    if raw_model_preset_id in (None, ""):
        brief_copy["model_preset_id"] = None
    else:
        try:
            brief_copy["model_preset_id"] = int(raw_model_preset_id)
        except (TypeError, ValueError):
            brief_copy["model_preset_id"] = None

    raw_max_tokens = brief_copy.get("max_tokens", DEFAULT_BRIEF_MAX_TOKENS)
    try:
        max_tokens = int(raw_max_tokens)
    except (TypeError, ValueError):
        max_tokens = DEFAULT_BRIEF_MAX_TOKENS
    brief_copy["max_tokens"] = max(1, max_tokens)

    # Remove legacy LLMConfig fields from brief.
    for key in ("provider", "model", "temperature"):
        brief_copy.pop(key, None)

    normalized["brief"] = brief_copy
    return normalized


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
                file_config = _migrate_legacy_brief_config(file_config)
                file_config = _migrate_summary_prompt_model_presets(file_config)
                merged = merge_dicts(DEFAULT_CONFIG.copy(), file_config)
                merged = _normalize_summary_prompt_limits(merged)
                merged = _normalize_brief_config(merged)
                merged = _sanitize_config(merged)
                _save_db_config(session, merged)
                return merged

            db_config = _migrate_legacy_brief_config(db_config)
            db_config = _migrate_summary_prompt_model_presets(db_config)
            merged = merge_dicts(DEFAULT_CONFIG.copy(), db_config)
            merged = _normalize_summary_prompt_limits(merged)
            merged = _normalize_brief_config(merged)
            cleaned = _sanitize_config(merged)
            if cleaned != db_config or "api_key" in db_config:
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
            normalized = _normalize_summary_prompt_limits(config)
            normalized = _normalize_brief_config(normalized)
            cleaned = _sanitize_config(normalized)
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
    config = _normalize_summary_prompt_limits(config)
    config = _normalize_brief_config(config)
    save_config(config)
    return config


def get_config_value(key_path: str, default=None) -> Any:
    """Get a specific configuration value using dot notation (e.g., 'transcribe.model')."""
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
