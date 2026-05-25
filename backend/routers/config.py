"""Configuration router — /config endpoints."""

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException

import config as config_module
from auth import require_roles
from schemas.config import ConfigUpdate

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.get("")
def get_configuration(
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Get the current application configuration."""
    try:
        return config_module.load_config()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load configuration: {str(e)}"
        )


@router.put("")
def update_configuration(
    config_update: ConfigUpdate,
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Update the application configuration."""
    try:
        updated_config = config_module.update_config(config_update.config)
        return {"message": "Configuration updated successfully", "config": updated_config}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update configuration: {str(e)}"
        )


@router.get("/{key_path}")
def get_configuration_value(
    key_path: str,
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Get a specific configuration value using dot notation (e.g., 'transcribe.model')."""
    try:
        value = config_module.get_config_value(key_path)
        if value is None:
            raise HTTPException(
                status_code=404, detail=f"Configuration key '{key_path}' not found"
            )
        return {"key": key_path, "value": value}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get configuration value: {str(e)}"
        )


@router.post("/reset")
def reset_configuration(
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Reset configuration to default values."""
    try:
        config_module.save_config(config_module.DEFAULT_CONFIG)
        return {
            "message": "Configuration reset to defaults",
            "config": config_module.DEFAULT_CONFIG,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reset configuration: {str(e)}"
        )
