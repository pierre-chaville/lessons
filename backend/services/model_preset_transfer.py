"""JSON export / import of model presets, keeping their ids.

Configuration YAML references presets by `model_preset_id`, so a preset must
keep the same id across environments (dev → prod). Import upserts by id:
an existing preset is overwritten with the file's values, a missing one is
created with that exact id. Presets absent from the file are left untouched.
"""

from datetime import datetime

from sqlalchemy import text
from sqlmodel import Session, select

from models.model_preset import ModelPreset
from schemas.model_preset import ModelPresetImportResult, ModelPresetTransfer

_TRANSFER_FIELDS = (
    "name",
    "provider",
    "model_id",
    "temperature",
    "cost_input_per_m_tokens",
    "cost_output_per_m_tokens",
    "flex_cost_ratio",
    "thinking_mode",
)


def export_model_presets(session: Session) -> list[ModelPresetTransfer]:
    """Return all presets, ordered by id."""
    presets = session.exec(select(ModelPreset).order_by(ModelPreset.id)).all()
    return [
        ModelPresetTransfer(id=preset.id, **{field: getattr(preset, field) for field in _TRANSFER_FIELDS})
        for preset in presets
    ]


def _sync_id_sequence(session: Session) -> None:
    """Move the PostgreSQL id sequence past the highest id, since import inserts explicit ids."""
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('model_preset', 'id'), "
            "COALESCE((SELECT MAX(id) FROM model_preset), 1), "
            "(SELECT COUNT(*) FROM model_preset) > 0)"
        )
    )


def import_model_presets(
    session: Session, presets: list[ModelPresetTransfer]
) -> ModelPresetImportResult:
    """Upsert presets by id, in a single commit."""
    existing = {preset.id: preset for preset in session.exec(select(ModelPreset)).all()}
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    now = datetime.utcnow()

    try:
        for item in presets:
            values = {field: getattr(item, field) for field in _TRANSFER_FIELDS}
            preset = existing.get(item.id)
            if preset is None:
                session.add(ModelPreset(id=item.id, created_at=now, updated_at=now, **values))
                counts["created"] += 1
            elif any(getattr(preset, field) != value for field, value in values.items()):
                for field, value in values.items():
                    setattr(preset, field, value)
                preset.updated_at = now
                session.add(preset)
                counts["updated"] += 1
            else:
                counts["unchanged"] += 1
        session.flush()
        _sync_id_sequence(session)
        session.commit()
    except Exception:
        session.rollback()
        raise

    file_ids = {item.id for item in presets}
    return ModelPresetImportResult(
        **counts,
        total=sum(counts.values()),
        ids_not_in_file=sorted(preset_id for preset_id in existing if preset_id not in file_ids),
    )
