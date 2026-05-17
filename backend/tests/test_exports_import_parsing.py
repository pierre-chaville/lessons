from fastapi import HTTPException
import pytest

from services.exports import extract_markdown_main_section, transcript_markdown_to_segments


def test_extract_markdown_main_section_prefers_marker_section():
    markdown = (
        "# Lesson details\n"
        "- **Title:** Demo\n\n"
        "<!-- MARKER:section-start -->\n\n"
        "# Summary\n\n"
        "Main imported text.\n"
        "<!-- MARKER:section-end -->\n"
    )

    extracted = extract_markdown_main_section(markdown)

    assert extracted == "# Summary\n\nMain imported text."


def test_extract_markdown_main_section_without_markers_returns_full_text():
    markdown = "# Summary\n\nNo marker wrapper."

    extracted = extract_markdown_main_section(markdown)

    assert extracted == markdown


def test_extract_markdown_main_section_strips_export_preface_without_markers():
    markdown = (
        "# Test lesson\n"
        "**2026-01-01 - 2m 00s**\n"
        "\n"
        "Imported summary body.\n"
    )

    extracted = extract_markdown_main_section(markdown)

    assert extracted == "Imported summary body."


def test_transcript_markdown_to_segments_parses_timed_lines():
    markdown = (
        "- [00:01 - 00:03] First line\n"
        "- [1:02:03 - 1:02:04.5] Second line\n"
    )

    segments = transcript_markdown_to_segments(markdown)

    assert segments == [
        {"start": 1.0, "end": 3.0, "text": "First line"},
        {"start": 3723.0, "end": 3724.5, "text": "Second line"},
    ]


def test_transcript_markdown_to_segments_fallback_without_timestamps():
    markdown = (
        "# Transcript\n\n"
        "- Plain bullet line\n"
        "Second plain line\n"
        "<!-- comment line should be ignored -->\n"
    )

    segments = transcript_markdown_to_segments(markdown)

    assert segments == [
        {"start": 0.0, "end": 1.0, "text": "Plain bullet line"},
        {"start": 1.0, "end": 2.0, "text": "Second plain line"},
    ]


def test_transcript_markdown_to_segments_rejects_invalid_timestamp():
    markdown = "- [1:2:3:4 - 00:10] Broken format"

    with pytest.raises(HTTPException) as exc_info:
        transcript_markdown_to_segments(markdown)
    assert exc_info.value.status_code == 400
    assert "Unsupported timestamp format" in str(exc_info.value.detail)
