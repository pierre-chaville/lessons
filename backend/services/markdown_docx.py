"""Utilities to convert simple markdown documents into DOCX."""

from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_BREAK
from docx.shared import Pt

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+)$")
_HORIZONTAL_RULE_RE = re.compile(r"^\s{0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})\s*$")
_UNORDERED_LIST_RE = re.compile(r"^(?P<indent>\s*)[-*+]\s+(?P<content>.+)$")
_ORDERED_LIST_RE = re.compile(r"^(?P<indent>\s*)(?P<number>\d+)[.)]\s+(?P<content>.+)$")
_INLINE_TOKEN_RE = re.compile(r"(\*\*.+?\*\*|__.+?__|\*.+?\*|_.+?_)")


def _append_inline_runs(paragraph, text: str) -> None:
    """Append text to a paragraph while handling bold/italic markdown markers."""
    cursor = 0
    for match in _INLINE_TOKEN_RE.finditer(text):
        start, end = match.span()
        if start > cursor:
            paragraph.add_run(text[cursor:start])

        token = match.group(0)
        if token.startswith("**") and token.endswith("**") and len(token) >= 4:
            run = paragraph.add_run(token[2:-2])
            run.bold = True
        elif token.startswith("__") and token.endswith("__") and len(token) >= 4:
            run = paragraph.add_run(token[2:-2])
            run.bold = True
        elif token.startswith("*") and token.endswith("*") and len(token) >= 2:
            run = paragraph.add_run(token[1:-1])
            run.italic = True
        elif token.startswith("_") and token.endswith("_") and len(token) >= 2:
            run = paragraph.add_run(token[1:-1])
            run.italic = True
        else:
            paragraph.add_run(token)
        cursor = end

    if cursor < len(text):
        paragraph.add_run(text[cursor:])


def _list_indent_level(indent: str) -> int:
    # Tabs are treated as 4 spaces; every 2 spaces increases nesting level.
    expanded = indent.replace("\t", "    ")
    return max(0, len(expanded) // 2)


def _add_list_paragraph(
    doc: Document,
    *,
    indent_level: int,
    marker: str,
    content: str,
) -> None:
    """
    Add a list paragraph with explicit indentation.

    We intentionally render list markers ourselves rather than relying on
    Word list styles, because style availability/behavior can vary by template.
    """
    paragraph = doc.add_paragraph()
    paragraph_format = paragraph.paragraph_format
    base_indent = 18
    hanging_indent = 12
    paragraph_format.left_indent = Pt(base_indent * (indent_level + 1))
    paragraph_format.first_line_indent = Pt(-hanging_indent)
    paragraph.add_run(f"{marker} ")
    _append_inline_runs(paragraph, content.strip())


def _parse_list_item(line: str) -> tuple[int, str, str] | None:
    unordered = _UNORDERED_LIST_RE.match(line)
    if unordered:
        indent_level = _list_indent_level(unordered.group("indent"))
        return indent_level, "•", unordered.group("content")

    ordered = _ORDERED_LIST_RE.match(line)
    if ordered:
        indent_level = _list_indent_level(ordered.group("indent"))
        marker = f"{ordered.group('number')}."
        return indent_level, marker, ordered.group("content")

    return None


def markdown_to_docx_bytes(markdown_text: str) -> bytes:
    """
    Convert a simple markdown string to DOCX bytes.

    Supported markdown features:
    - Headings (# to ######)
    - Horizontal rules (---, ***, ___) as page breaks
    - Bulleted lists (-, *, +)
    - Numbered lists (1. / 1))
    - Paragraphs
    - Inline bold/italic (**text**, __text__, *text*, _text_)
    """
    doc = Document()
    lines = str(markdown_text or "").splitlines()
    idx = 0

    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()

        if not stripped:
            idx += 1
            continue

        if _HORIZONTAL_RULE_RE.match(raw):
            page_break_paragraph = doc.add_paragraph()
            page_break_paragraph.add_run().add_break(WD_BREAK.PAGE)
            idx += 1
            continue

        heading_match = _HEADING_RE.match(raw)
        if heading_match:
            level = min(len(heading_match.group(1)), 6)
            heading_text = heading_match.group(2).strip()
            paragraph = doc.add_heading(level=level)
            _append_inline_runs(paragraph, heading_text)
            idx += 1
            continue

        if _parse_list_item(raw):
            while idx < len(lines):
                line = lines[idx]
                line_stripped = line.strip()
                if not line_stripped:
                    idx += 1
                    break

                parsed = _parse_list_item(line)
                if not parsed:
                    break
                indent_level, marker, content = parsed
                _add_list_paragraph(
                    doc,
                    indent_level=indent_level,
                    marker=marker,
                    content=content,
                )
                idx += 1
            continue

        paragraph_lines: list[str] = []
        while idx < len(lines):
            line = lines[idx]
            line_stripped = line.strip()
            if not line_stripped:
                idx += 1
                break
            if (
                _HEADING_RE.match(line)
                or _UNORDERED_LIST_RE.match(line)
                or _ORDERED_LIST_RE.match(line)
                or _HORIZONTAL_RULE_RE.match(line)
            ):
                break
            paragraph_lines.append(line_stripped)
            idx += 1

        paragraph_text = " ".join(paragraph_lines).strip()
        if paragraph_text:
            paragraph = doc.add_paragraph()
            _append_inline_runs(paragraph, paragraph_text)

    output = BytesIO()
    doc.save(output)
    return output.getvalue()
