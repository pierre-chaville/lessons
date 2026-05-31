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
MIN_SUMMARY_PROMPT_MAX_TOKENS = 1
DEFAULT_SUMMARY_PROMPT_MAX_TOKENS = 1200
DEFAULT_BRIEF_MAX_TOKENS = 1000
DEFAULT_EDITION_PROMPT_MAX_TOKENS = 16000
MIN_EDITION_PROMPT_MAX_TOKENS = 256
DEFAULT_CORRECTION_PROMPT_MAX_TOKENS = 16000
MIN_CORRECTION_PROMPT_MAX_TOKENS = 256
DEFAULT_EXTRACTION_PROMPT_MAX_TOKENS = 4000
MIN_EXTRACTION_PROMPT_MAX_TOKENS = 256
DEFAULT_SOURCES_PROMPT_MAX_TOKENS = 4000
MIN_SOURCES_PROMPT_MAX_TOKENS = 256
DEFAULT_EDITED_MIN_ALIGNMENT_SCORE = 0.2
DEFAULT_SUMMARY_MIN_ALIGNMENT_SCORE = 0.2

# Default configuration
DEFAULT_CONFIG = {
    "correction": {
        "prompts": [
            {
                "name": "Default",
                "text": "Please correct the following transcript, fixing any errors while maintaining the original meaning and style.",
                "model_preset_id": None,
                "max_tokens": DEFAULT_CORRECTION_PROMPT_MAX_TOKENS,
            }
        ],
    },
    "edition": {
        "prompts": [
            {
                "name": "Default",
                "text": "Please rewrite the following transcript in a clear, written style, maintaining the original meaning and flow. Include timing information (start/end) and cite any sources mentioned.",
                "model_preset_id": None,
                "max_tokens": DEFAULT_EDITION_PROMPT_MAX_TOKENS,
            }
        ],
    },
    "summary": {
        "prompts": [
            {
                "name": "Default",
                "text": "Please provide a concise summary of the following lesson transcript.",
                "model_preset_id": None,
                "max_tokens": DEFAULT_SUMMARY_PROMPT_MAX_TOKENS,
            }
        ],
    },
    "brief": {
        "model_preset_id": None,
        "prompt": "Please provide a brief 1-3 line summary of the following lesson transcript.",
        "max_tokens": DEFAULT_BRIEF_MAX_TOKENS,
    },
    "extraction": {
        "prompts": [
            {
                "name": "Default",
                "text": "Please extract any sources mentioned in the edited transcript.",
                "model_preset_id": None,
                "max_tokens": DEFAULT_EXTRACTION_PROMPT_MAX_TOKENS,
            }
        ],
    },
    "sources": {
        "prompts": [
            {
                "name": "Default",
                "text": "Please verify sources and provide standardized references.",
                "model_preset_id": None,
                "max_tokens": DEFAULT_SOURCES_PROMPT_MAX_TOKENS,
            }
        ],
    },
    "transcribe": {
        "model": "nova-3",
        "language": "fr",
        "audience_segment_prefix": "[audience]",
    },
    "alignment": {
        "edited_min_score": DEFAULT_EDITED_MIN_ALIGNMENT_SCORE,
        "summary_min_score": DEFAULT_SUMMARY_MIN_ALIGNMENT_SCORE,
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
    legacy_max_tokens = summary_copy.get("max_tokens")
    if legacy_max_tokens is None:
        legacy_max_length = summary_copy.get("max_length")
        try:
            legacy_max_tokens = int(legacy_max_length) * 4
        except (TypeError, ValueError):
            legacy_max_tokens = DEFAULT_SUMMARY_PROMPT_MAX_TOKENS
    prompts = summary_copy.get("prompts", [])
    if not prompts and summary_copy.get("prompt"):
        prompts = [{"name": "Default", "text": summary_copy.get("prompt")}]

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)
        prompt_copy.setdefault("model_preset_id", None)
        prompt_copy.setdefault("max_tokens", legacy_max_tokens)
        normalized_prompts.append(prompt_copy)
    if normalized_prompts:
        summary_copy["prompts"] = normalized_prompts

    # Remove legacy summary-level model tuning fields.
    for key in ("provider", "model", "temperature", "max_tokens", "prompt", "max_length"):
        summary_copy.pop(key, None)

    migrated["summary"] = summary_copy
    return migrated


def _migrate_correction_prompt_model_presets(config: Dict[str, Any]) -> Dict[str, Any]:
    """Move legacy correction model settings to prompt-level settings."""
    if not config:
        return {}

    migrated = dict(config)
    correction = migrated.get("correction")
    if not isinstance(correction, dict):
        return migrated

    correction_copy = dict(correction)
    legacy_max_tokens = correction_copy.get(
        "max_tokens", DEFAULT_CORRECTION_PROMPT_MAX_TOKENS
    )
    prompts = correction_copy.get("prompts", [])
    if not prompts and correction_copy.get("prompt"):
        prompts = [{"name": "Default", "text": correction_copy.get("prompt")}]

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)
        prompt_copy.setdefault("model_preset_id", None)
        prompt_copy.setdefault("max_tokens", legacy_max_tokens)
        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        correction_copy["prompts"] = normalized_prompts

    for key in ("provider", "model", "temperature", "max_tokens", "prompt"):
        correction_copy.pop(key, None)

    migrated["correction"] = correction_copy
    return migrated


def _normalize_summary_prompt_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize per-prompt summary max_tokens to a safe integer minimum."""
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
        raw_max_tokens = prompt_copy.get("max_tokens")
        if raw_max_tokens is None and "max_length" in prompt_copy:
            try:
                raw_max_tokens = int(prompt_copy.get("max_length")) * 4
            except (TypeError, ValueError):
                raw_max_tokens = DEFAULT_SUMMARY_PROMPT_MAX_TOKENS
        if raw_max_tokens is None:
            raw_max_tokens = DEFAULT_SUMMARY_PROMPT_MAX_TOKENS
        try:
            prompt_max_tokens = int(raw_max_tokens)
        except (TypeError, ValueError):
            prompt_max_tokens = DEFAULT_SUMMARY_PROMPT_MAX_TOKENS
        prompt_copy["max_tokens"] = max(MIN_SUMMARY_PROMPT_MAX_TOKENS, prompt_max_tokens)
        prompt_copy.pop("max_length", None)
        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        summary_copy["prompts"] = normalized_prompts
    normalized["summary"] = summary_copy
    return normalized


def _normalize_correction_prompt_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize correction prompt-level max_tokens and model_preset_id."""
    if not config:
        return {}

    normalized = dict(config)
    correction = normalized.get("correction")
    if not isinstance(correction, dict):
        return normalized

    correction_copy = dict(correction)
    prompts = correction_copy.get("prompts")
    if not isinstance(prompts, list):
        normalized["correction"] = correction_copy
        return normalized

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)

        raw_max_tokens = prompt_copy.get(
            "max_tokens", DEFAULT_CORRECTION_PROMPT_MAX_TOKENS
        )
        try:
            prompt_max_tokens = int(raw_max_tokens)
        except (TypeError, ValueError):
            prompt_max_tokens = DEFAULT_CORRECTION_PROMPT_MAX_TOKENS
        prompt_copy["max_tokens"] = max(
            MIN_CORRECTION_PROMPT_MAX_TOKENS, prompt_max_tokens
        )

        raw_model_preset_id = prompt_copy.get("model_preset_id")
        if raw_model_preset_id in (None, ""):
            prompt_copy["model_preset_id"] = None
        else:
            try:
                prompt_copy["model_preset_id"] = int(raw_model_preset_id)
            except (TypeError, ValueError):
                prompt_copy["model_preset_id"] = None

        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        correction_copy["prompts"] = normalized_prompts
    normalized["correction"] = correction_copy
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


def _migrate_edition_prompt_model_presets(config: Dict[str, Any]) -> Dict[str, Any]:
    """Move legacy edition model settings to prompt-level settings."""
    if not config:
        return {}

    migrated = dict(config)
    edition = migrated.get("edition")
    if not isinstance(edition, dict):
        return migrated

    edition_copy = dict(edition)
    legacy_max_tokens = edition_copy.get(
        "max_tokens", DEFAULT_EDITION_PROMPT_MAX_TOKENS
    )
    prompts = edition_copy.get("prompts", [])
    if not prompts and edition_copy.get("prompt"):
        prompts = [{"name": "Default", "text": edition_copy.get("prompt")}]

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)
        prompt_copy.setdefault("model_preset_id", None)
        prompt_copy.setdefault("max_tokens", legacy_max_tokens)
        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        edition_copy["prompts"] = normalized_prompts

    for key in ("provider", "model", "temperature", "max_tokens", "prompt"):
        edition_copy.pop(key, None)

    migrated["edition"] = edition_copy
    return migrated


def _normalize_edition_prompt_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize edition prompt-level max_tokens and model_preset_id."""
    if not config:
        return {}

    normalized = dict(config)
    edition = normalized.get("edition")
    if not isinstance(edition, dict):
        return normalized

    edition_copy = dict(edition)
    prompts = edition_copy.get("prompts")
    if not isinstance(prompts, list):
        normalized["edition"] = edition_copy
        return normalized

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)

        raw_max_tokens = prompt_copy.get(
            "max_tokens", DEFAULT_EDITION_PROMPT_MAX_TOKENS
        )
        try:
            prompt_max_tokens = int(raw_max_tokens)
        except (TypeError, ValueError):
            prompt_max_tokens = DEFAULT_EDITION_PROMPT_MAX_TOKENS
        prompt_copy["max_tokens"] = max(MIN_EDITION_PROMPT_MAX_TOKENS, prompt_max_tokens)

        raw_model_preset_id = prompt_copy.get("model_preset_id")
        if raw_model_preset_id in (None, ""):
            prompt_copy["model_preset_id"] = None
        else:
            try:
                prompt_copy["model_preset_id"] = int(raw_model_preset_id)
            except (TypeError, ValueError):
                prompt_copy["model_preset_id"] = None

        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        edition_copy["prompts"] = normalized_prompts
    normalized["edition"] = edition_copy
    return normalized


def _migrate_extraction_prompt_model_presets(config: Dict[str, Any]) -> Dict[str, Any]:
    """Move legacy extraction model settings to prompt-level settings."""
    if not config:
        return {}

    migrated = dict(config)
    extraction = migrated.get("extraction")
    if not isinstance(extraction, dict):
        return migrated

    extraction_copy = dict(extraction)
    legacy_max_tokens = extraction_copy.get(
        "max_tokens", DEFAULT_EXTRACTION_PROMPT_MAX_TOKENS
    )
    prompts = extraction_copy.get("prompts", [])
    if not prompts and extraction_copy.get("prompt"):
        prompts = [{"name": "Default", "text": extraction_copy.get("prompt")}]

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)
        prompt_copy.setdefault("model_preset_id", None)
        prompt_copy.setdefault("max_tokens", legacy_max_tokens)
        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        extraction_copy["prompts"] = normalized_prompts

    for key in ("provider", "model", "temperature", "max_tokens", "prompt"):
        extraction_copy.pop(key, None)

    migrated["extraction"] = extraction_copy
    return migrated


def _normalize_extraction_prompt_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize extraction prompt-level max_tokens and model_preset_id."""
    if not config:
        return {}

    normalized = dict(config)
    extraction = normalized.get("extraction")
    if not isinstance(extraction, dict):
        return normalized

    extraction_copy = dict(extraction)
    prompts = extraction_copy.get("prompts")
    if not isinstance(prompts, list):
        normalized["extraction"] = extraction_copy
        return normalized

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)
        raw_max_tokens = prompt_copy.get(
            "max_tokens", DEFAULT_EXTRACTION_PROMPT_MAX_TOKENS
        )
        try:
            prompt_max_tokens = int(raw_max_tokens)
        except (TypeError, ValueError):
            prompt_max_tokens = DEFAULT_EXTRACTION_PROMPT_MAX_TOKENS
        prompt_copy["max_tokens"] = max(MIN_EXTRACTION_PROMPT_MAX_TOKENS, prompt_max_tokens)

        raw_model_preset_id = prompt_copy.get("model_preset_id")
        if raw_model_preset_id in (None, ""):
            prompt_copy["model_preset_id"] = None
        else:
            try:
                prompt_copy["model_preset_id"] = int(raw_model_preset_id)
            except (TypeError, ValueError):
                prompt_copy["model_preset_id"] = None

        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        extraction_copy["prompts"] = normalized_prompts
    normalized["extraction"] = extraction_copy
    return normalized


def _migrate_sources_prompt_model_presets(config: Dict[str, Any]) -> Dict[str, Any]:
    """Move legacy sources model settings to prompt-level settings."""
    if not config:
        return {}

    migrated = dict(config)
    sources = migrated.get("sources")
    if not isinstance(sources, dict):
        return migrated

    sources_copy = dict(sources)
    legacy_max_tokens = sources_copy.get(
        "max_tokens", DEFAULT_SOURCES_PROMPT_MAX_TOKENS
    )
    prompts = sources_copy.get("prompts", [])
    if not prompts and sources_copy.get("prompt"):
        prompts = [{"name": "Default", "text": sources_copy.get("prompt")}]

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)
        prompt_copy.setdefault("model_preset_id", None)
        prompt_copy.setdefault("max_tokens", legacy_max_tokens)
        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        sources_copy["prompts"] = normalized_prompts

    for key in ("provider", "model", "temperature", "max_tokens", "prompt"):
        sources_copy.pop(key, None)

    migrated["sources"] = sources_copy
    return migrated


def _normalize_alignment_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize alignment score thresholds to [0.0, 1.0]."""
    if not config:
        return {}

    normalized = dict(config)
    alignment = normalized.get("alignment")
    if not isinstance(alignment, dict):
        normalized["alignment"] = dict(DEFAULT_CONFIG["alignment"])
        return normalized

    alignment_copy = dict(alignment)

    def _score(raw: Any, default: float) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
        return max(0.0, min(1.0, value))

    alignment_copy["edited_min_score"] = _score(
        alignment_copy.get("edited_min_score", DEFAULT_EDITED_MIN_ALIGNMENT_SCORE),
        DEFAULT_EDITED_MIN_ALIGNMENT_SCORE,
    )
    alignment_copy["summary_min_score"] = _score(
        alignment_copy.get("summary_min_score", DEFAULT_SUMMARY_MIN_ALIGNMENT_SCORE),
        DEFAULT_SUMMARY_MIN_ALIGNMENT_SCORE,
    )

    normalized["alignment"] = alignment_copy
    return normalized


def _normalize_sources_prompt_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize sources prompt-level max_tokens and model_preset_id."""
    if not config:
        return {}

    normalized = dict(config)
    sources = normalized.get("sources")
    if not isinstance(sources, dict):
        return normalized

    sources_copy = dict(sources)
    prompts = sources_copy.get("prompts")
    if not isinstance(prompts, list):
        normalized["sources"] = sources_copy
        return normalized

    normalized_prompts = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt_copy = dict(prompt)
        raw_max_tokens = prompt_copy.get(
            "max_tokens", DEFAULT_SOURCES_PROMPT_MAX_TOKENS
        )
        try:
            prompt_max_tokens = int(raw_max_tokens)
        except (TypeError, ValueError):
            prompt_max_tokens = DEFAULT_SOURCES_PROMPT_MAX_TOKENS
        prompt_copy["max_tokens"] = max(MIN_SOURCES_PROMPT_MAX_TOKENS, prompt_max_tokens)

        raw_model_preset_id = prompt_copy.get("model_preset_id")
        if raw_model_preset_id in (None, ""):
            prompt_copy["model_preset_id"] = None
        else:
            try:
                prompt_copy["model_preset_id"] = int(raw_model_preset_id)
            except (TypeError, ValueError):
                prompt_copy["model_preset_id"] = None

        normalized_prompts.append(prompt_copy)

    if normalized_prompts:
        sources_copy["prompts"] = normalized_prompts
    normalized["sources"] = sources_copy
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
                file_config = _migrate_correction_prompt_model_presets(file_config)
                file_config = _migrate_edition_prompt_model_presets(file_config)
                file_config = _migrate_extraction_prompt_model_presets(file_config)
                file_config = _migrate_sources_prompt_model_presets(file_config)
                merged = merge_dicts(DEFAULT_CONFIG.copy(), file_config)
                merged = _normalize_summary_prompt_limits(merged)
                merged = _normalize_correction_prompt_limits(merged)
                merged = _normalize_edition_prompt_limits(merged)
                merged = _normalize_extraction_prompt_limits(merged)
                merged = _normalize_sources_prompt_limits(merged)
                merged = _normalize_brief_config(merged)
                merged = _normalize_alignment_config(merged)
                merged = _sanitize_config(merged)
                _save_db_config(session, merged)
                return merged

            db_config = _migrate_legacy_brief_config(db_config)
            db_config = _migrate_summary_prompt_model_presets(db_config)
            db_config = _migrate_correction_prompt_model_presets(db_config)
            db_config = _migrate_edition_prompt_model_presets(db_config)
            db_config = _migrate_extraction_prompt_model_presets(db_config)
            db_config = _migrate_sources_prompt_model_presets(db_config)
            merged = merge_dicts(DEFAULT_CONFIG.copy(), db_config)
            merged = _normalize_summary_prompt_limits(merged)
            merged = _normalize_correction_prompt_limits(merged)
            merged = _normalize_edition_prompt_limits(merged)
            merged = _normalize_extraction_prompt_limits(merged)
            merged = _normalize_sources_prompt_limits(merged)
            merged = _normalize_brief_config(merged)
            merged = _normalize_alignment_config(merged)
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
            normalized = _normalize_correction_prompt_limits(normalized)
            normalized = _normalize_edition_prompt_limits(normalized)
            normalized = _normalize_extraction_prompt_limits(normalized)
            normalized = _normalize_sources_prompt_limits(normalized)
            normalized = _normalize_brief_config(normalized)
            normalized = _normalize_alignment_config(normalized)
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
    config = _normalize_correction_prompt_limits(config)
    config = _normalize_edition_prompt_limits(config)
    config = _normalize_extraction_prompt_limits(config)
    config = _normalize_sources_prompt_limits(config)
    config = _normalize_brief_config(config)
    config = _normalize_alignment_config(config)
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
