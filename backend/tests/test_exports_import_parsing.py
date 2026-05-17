from fastapi import HTTPException
import pytest

from services.exports import (
    _build_transcript_markdown,
    extract_markdown_main_section,
    transcript_markdown_to_segments,
)


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


def test_build_transcript_markdown_writes_timed_segments_as_bullets():
    markdown = _build_transcript_markdown(
        [
            {"start": 18.0, "end": 20.0, "text": "Line one"},
            {"start": 62.0, "end": 64.0, "text": "Line two"},
        ],
        labels={"no_transcript": "_No transcript available._"},
    )

    assert markdown == "- [18s - 20s] Line one\n- [1m 02s - 1m 04s] Line two"


def test_transcript_markdown_to_segments_parses_exported_duration_units():
    markdown = (
        "- [18s - 20s] Line one\n"
        "- [1m 02s - 1m 04s] Line two\n"
        "- [1h 00m 00s - 1h 00m 01.5s] Line three\n"
    )

    segments = transcript_markdown_to_segments(markdown)

    assert segments == [
        {"start": 18.0, "end": 20.0, "text": "Line one"},
        {"start": 62.0, "end": 64.0, "text": "Line two"},
        {"start": 3600.0, "end": 3601.5, "text": "Line three"},
    ]


def test_transcript_markdown_to_segments_parses_legacy_bulleted_timed_lines():
    markdown = "- [18s - 20s] Legacy line"

    segments = transcript_markdown_to_segments(markdown)

    assert segments == [
        {"start": 18.0, "end": 20.0, "text": "Legacy line"},
    ]


def test_transcript_markdown_to_segments_parses_bracketed_lines_without_bullets():
    markdown = "[18s - 20s] La paracha est consacree"

    segments = transcript_markdown_to_segments(markdown)

    assert segments == [
        {"start": 18.0, "end": 20.0, "text": "La paracha est consacree"},
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
