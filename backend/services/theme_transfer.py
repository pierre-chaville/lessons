"""JSON export / import of the theme hierarchy.

Themes are transferred by name, not by id, so a file can move between
environments (dev → prod) or come from another source. Import is a merge:
it never deletes or moves existing themes, because lessons reference themes
by id.
"""

from sqlalchemy import func
from sqlmodel import Session, select

from models import Theme
from schemas.theme import ThemeImportResult, ThemeTransferNode


def _name_key(name: str) -> str:
    return name.strip().casefold()


def export_theme_tree(session: Session) -> list[ThemeTransferNode]:
    """Return all themes as a nested, name-based tree ordered like the UI."""
    themes = list(session.exec(select(Theme).order_by(Theme.sort_order, Theme.name)).all())
    ids = {theme.id for theme in themes}
    children_of: dict[int | None, list[Theme]] = {}
    for theme in themes:
        # Orphans (parent missing) are exported as roots, as the tree view shows them.
        parent_id = theme.parent_id if theme.parent_id in ids else None
        children_of.setdefault(parent_id, []).append(theme)

    def _build(parent_id: int | None) -> list[ThemeTransferNode]:
        return [
            ThemeTransferNode(
                name=theme.name,
                description=theme.description,
                children=_build(theme.id),
            )
            for theme in children_of.get(parent_id, [])
        ]

    return _build(None)


def import_theme_tree(session: Session, nodes: list[ThemeTransferNode]) -> ThemeImportResult:
    """Merge a name-based theme tree into the database, in a single commit.

    A node matches an existing theme with the same name (case-insensitive)
    under the same parent; otherwise it is created at the end of its
    siblings, in file order. A matched theme's description is updated only
    when the node sets `description` explicitly and it differs.
    """
    existing = list(session.exec(select(Theme).order_by(Theme.sort_order, Theme.id)).all())
    by_parent: dict[int | None, dict[str, Theme]] = {}
    for theme in existing:
        by_parent.setdefault(theme.parent_id, {}).setdefault(_name_key(theme.name), theme)

    next_order: dict[int | None, int] = {}
    counts = {"created": 0, "updated": 0, "unchanged": 0}

    def _next_sort_order(parent_id: int | None) -> int:
        if parent_id not in next_order:
            max_order = session.exec(
                select(func.coalesce(func.max(Theme.sort_order), -1)).where(
                    Theme.parent_id == parent_id
                    if parent_id is not None
                    else Theme.parent_id.is_(None)
                )
            ).one()
            next_order[parent_id] = max_order + 1
        value = next_order[parent_id]
        next_order[parent_id] = value + 1
        return value

    def _merge(node: ThemeTransferNode, parent_id: int | None) -> None:
        siblings = by_parent.setdefault(parent_id, {})
        key = _name_key(node.name)
        theme = siblings.get(key)
        if theme is None:
            theme = Theme(
                name=node.name,
                description=node.description,
                parent_id=parent_id,
                sort_order=_next_sort_order(parent_id),
            )
            session.add(theme)
            session.flush()  # assign theme.id for the children
            siblings[key] = theme
            counts["created"] += 1
        elif "description" in node.model_fields_set and theme.description != node.description:
            theme.description = node.description
            session.add(theme)
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

        for child in node.children:
            _merge(child, theme.id)

    try:
        for node in nodes:
            _merge(node, None)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return ThemeImportResult(**counts, total=sum(counts.values()))
