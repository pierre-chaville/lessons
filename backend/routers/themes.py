"""Themes router — /themes endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from typing import Dict, Any, List

import crud
from auth import require_roles
from database import get_session
from models import Lesson, Theme
from schemas.theme import ThemeCreate, ThemeUpdate, ThemeResponse, ThemeTreeNode
from hashid_utils import encode_id, decode_id


class ReorderRequest(BaseModel):
    direction: str  # "up" or "down"

router = APIRouter(prefix="/themes", tags=["Themes"])


def _build_theme_response(theme) -> ThemeResponse:
    """Build a ThemeResponse with hashid from a Theme DB model."""
    return ThemeResponse(
        id=theme.id,
        hashid=encode_id(theme.id),
        name=theme.name,
        description=theme.description,
        parent_id=theme.parent_id,
        sort_order=theme.sort_order,
    )


def _get_lesson_counts(session: Session) -> Dict[int, int]:
    """Return {theme_id: direct_lesson_count} for themes stored on lessons."""
    rows = session.exec(
        select(Lesson.themes_json).where(
            Lesson.deleted_at.is_(None),
            Lesson.themes_json.is_not(None),
        )
    ).all()
    counts: Dict[int, int] = {}
    for row in rows:
        raw = row[0] if isinstance(row, tuple) else row
        if not raw:
            continue
        try:
            theme_ids = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(theme_ids, list):
            continue
        for theme_id in theme_ids:
            if isinstance(theme_id, int):
                counts[theme_id] = counts.get(theme_id, 0) + 1
    return counts


def _propagate_counts(node: ThemeTreeNode) -> int:
    """Recursively sum lesson counts from children into each node. Returns subtree total."""
    child_total = sum(_propagate_counts(c) for c in node.children)
    node.lesson_count += child_total
    return node.lesson_count


def _build_tree(themes, lesson_counts: Dict[int, int]) -> List[ThemeTreeNode]:
    """Build a list of root-level ThemeTreeNode from a flat list of themes."""
    nodes: Dict[int, ThemeTreeNode] = {}
    for theme in themes:
        nodes[theme.id] = ThemeTreeNode(
            id=theme.id,
            hashid=encode_id(theme.id),
            name=theme.name,
            description=theme.description,
            parent_id=theme.parent_id,
            sort_order=theme.sort_order,
            lesson_count=lesson_counts.get(theme.id, 0),
            children=[],
        )
    roots: List[ThemeTreeNode] = []
    for node in nodes.values():
        if node.parent_id and node.parent_id in nodes:
            nodes[node.parent_id].children.append(node)
        else:
            roots.append(node)

    def _sort_children(node: ThemeTreeNode):
        node.children.sort(key=lambda child: (child.sort_order, child.name))
        for child in node.children:
            _sort_children(child)

    for root in roots:
        _propagate_counts(root)
        _sort_children(root)
    roots.sort(key=lambda child: (child.sort_order, child.name))
    return roots


def _would_create_cycle(session: Session, theme_id: int, new_parent_id: int) -> bool:
    """Return True if setting theme_id.parent_id = new_parent_id creates a cycle."""
    visited = {theme_id}
    current = new_parent_id
    while current is not None:
        if current in visited:
            return True
        visited.add(current)
        parent = crud.get_theme(session, current)
        current = parent.parent_id if parent else None
    return False


@router.get("", response_model=List[ThemeResponse])
def get_themes(session: Session = Depends(get_session)):
    """Get all themes (flat list)."""
    themes = crud.get_all_themes(session)
    return [_build_theme_response(theme) for theme in themes]


@router.get("/tree", response_model=List[ThemeTreeNode])
def get_themes_tree(session: Session = Depends(get_session)):
    """Get themes as a hierarchical tree with aggregated lesson counts."""
    themes = crud.get_all_themes(session)
    lesson_counts = _get_lesson_counts(session)
    return _build_tree(themes, lesson_counts)


@router.patch("/{theme_hashid}/reorder", response_model=List[ThemeResponse])
def reorder_theme(
    theme_hashid: str,
    body: ReorderRequest,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Move a theme up or down among its siblings."""
    theme_id = decode_id(theme_hashid)
    theme = crud.get_theme(session, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    siblings = list(
        session.exec(
            select(Theme)
            .where(Theme.parent_id == theme.parent_id)
            .order_by(Theme.sort_order, Theme.name)
        ).all()
    )

    idx = next((i for i, sibling in enumerate(siblings) if sibling.id == theme_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Theme not found among siblings")

    if body.direction == "up" and idx > 0:
        swap = siblings[idx - 1]
        theme.sort_order, swap.sort_order = swap.sort_order, theme.sort_order
        if theme.sort_order == swap.sort_order:
            theme.sort_order -= 1
        session.add(theme)
        session.add(swap)
        session.commit()
    elif body.direction == "down" and idx < len(siblings) - 1:
        swap = siblings[idx + 1]
        theme.sort_order, swap.sort_order = swap.sort_order, theme.sort_order
        if theme.sort_order == swap.sort_order:
            theme.sort_order += 1
        session.add(theme)
        session.add(swap)
        session.commit()

    updated = list(
        session.exec(
            select(Theme)
            .where(Theme.parent_id == theme.parent_id)
            .order_by(Theme.sort_order, Theme.name)
        ).all()
    )
    return [_build_theme_response(item) for item in updated]


@router.get("/{theme_hashid}", response_model=ThemeResponse)
def get_theme(theme_hashid: str, session: Session = Depends(get_session)):
    """Get a specific theme by hashid."""
    theme_id = decode_id(theme_hashid)
    theme = crud.get_theme(session, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return _build_theme_response(theme)


@router.post("", response_model=ThemeResponse, status_code=201)
def create_theme(
    theme_data: ThemeCreate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Create a new theme."""
    if theme_data.parent_id is not None:
        if not crud.get_theme(session, theme_data.parent_id):
            raise HTTPException(status_code=404, detail="Parent theme not found")

    theme = crud.create_theme(
        session,
        name=theme_data.name,
        description=theme_data.description,
        parent_id=theme_data.parent_id,
        sort_order=theme_data.sort_order,
    )
    return _build_theme_response(theme)


@router.patch("/{theme_hashid}", response_model=ThemeResponse)
def update_theme(
    theme_hashid: str,
    theme_data: ThemeUpdate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Update an existing theme."""
    theme_id = decode_id(theme_hashid)
    payload = theme_data.model_dump(exclude_unset=True)

    parent_id = payload.get("parent_id", None)
    if "parent_id" in payload:
        if parent_id in (None, 0):
            parent_id = 0
        elif parent_id == theme_id:
            raise HTTPException(status_code=400, detail="A theme cannot be its own parent")
        else:
            if not crud.get_theme(session, parent_id):
                raise HTTPException(status_code=404, detail="Parent theme not found")
            if _would_create_cycle(session, theme_id, parent_id):
                raise HTTPException(status_code=400, detail="This parent would create a cycle")

    theme = crud.update_theme(
        session,
        theme_id,
        name=payload.get("name"),
        description=payload.get("description"),
        parent_id=parent_id if "parent_id" in payload else None,
        sort_order=payload.get("sort_order"),
        update_description="description" in payload,
    )
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return _build_theme_response(theme)


@router.delete("/{theme_hashid}", status_code=204)
def delete_theme(
    theme_hashid: str,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Delete a theme. Children are re-parented to the deleted theme's parent."""
    theme_id = decode_id(theme_hashid)
    if not crud.delete_theme(session, theme_id):
        raise HTTPException(status_code=404, detail="Theme not found")
    return None
