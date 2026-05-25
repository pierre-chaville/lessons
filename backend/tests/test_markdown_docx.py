from io import BytesIO

from docx import Document
from docx.oxml.ns import qn

from services.markdown_docx import docx_bytes_to_markdown, markdown_to_docx_bytes


def _has_page_break(paragraph) -> bool:
    for run in paragraph.runs:
        for br in run._r.findall(qn("w:br")):
            if br.get(qn("w:type")) == "page":
                return True
    return False


def test_horizontal_rule_creates_page_break():
    markdown = "# Title\n\nParagraph before break.\n\n---\n\n## After break"
    docx_bytes = markdown_to_docx_bytes(markdown)
    doc = Document(BytesIO(docx_bytes))

    assert any(_has_page_break(p) for p in doc.paragraphs)
    assert any("After break" in p.text for p in doc.paragraphs)


def test_nested_bullets_have_increasing_indentation():
    markdown = (
        "- **Chapitre 1**\n"
        "- 2025-12-20 - Midrash...\n"
        "  - Nested level 1\n"
        "    - Nested level 2\n"
    )
    docx_bytes = markdown_to_docx_bytes(markdown)
    doc = Document(BytesIO(docx_bytes))

    bullet_paragraphs = [p for p in doc.paragraphs if p.text.strip().startswith("• ")]
    assert len(bullet_paragraphs) >= 4

    indents = [p.paragraph_format.left_indent.pt if p.paragraph_format.left_indent else 0 for p in bullet_paragraphs[:4]]
    assert indents[0] == indents[1]
    assert indents[2] > indents[1]
    assert indents[3] > indents[2]


def test_ordered_list_keeps_explicit_marker_and_indentation():
    markdown = "1. First\n  2. Nested second\n"
    docx_bytes = markdown_to_docx_bytes(markdown)
    doc = Document(BytesIO(docx_bytes))

    ordered = [p for p in doc.paragraphs if p.text.strip()]
    assert ordered[0].text.startswith("1. ")
    assert ordered[1].text.startswith("2. ")
    assert ordered[1].paragraph_format.left_indent.pt > ordered[0].paragraph_format.left_indent.pt


def test_mixed_nested_lists_keep_order_and_indentation():
    markdown = (
        "- Chapter root\n"
        "  1. Numbered child\n"
        "    - Bullet grandchild\n"
        "  2. Numbered sibling\n"
        "- Next root\n"
    )
    docx_bytes = markdown_to_docx_bytes(markdown)
    doc = Document(BytesIO(docx_bytes))

    lines = [p for p in doc.paragraphs if p.text.strip()]
    assert lines[0].text.startswith("• ")
    assert lines[1].text.startswith("1. ")
    assert lines[2].text.startswith("• ")
    assert lines[3].text.startswith("2. ")
    assert lines[4].text.startswith("• ")

    indents = [p.paragraph_format.left_indent.pt if p.paragraph_format.left_indent else 0 for p in lines[:5]]
    assert indents[1] > indents[0]
    assert indents[2] > indents[1]
    assert indents[3] == indents[1]
    assert indents[4] == indents[0]


def test_docx_to_markdown_round_trip_supported_structure():
    markdown = (
        "# Report title\n\n"
        "Intro with **bold** and *italic* text.\n\n"
        "- Bullet root\n"
        "  - Nested bullet\n"
        "  1. Nested ordered\n\n"
        "> A quoted thought\n\n"
        "---\n\n"
        "## After break\n"
    )
    docx_bytes = markdown_to_docx_bytes(markdown)

    converted = docx_bytes_to_markdown(docx_bytes)

    assert "# Report title" in converted
    assert "Intro with **bold** and *italic* text." in converted
    assert "- Bullet root" in converted
    assert "  - Nested bullet" in converted
    assert "  1. Nested ordered" in converted
    assert "> A quoted thought" in converted
    assert "---" in converted
    assert "## After break" in converted


def test_docx_to_markdown_keeps_list_indentation_from_exporter():
    markdown = "- Root\n  - Child\n    - Grandchild\n"
    docx_bytes = markdown_to_docx_bytes(markdown)

    converted = docx_bytes_to_markdown(docx_bytes)

    assert "- Root" in converted
    assert "  - Child" in converted
    assert "    - Grandchild" in converted


def test_docx_round_trip_preserves_section_markers():
    markdown = (
        "# Meta\n\n"
        "<!-- MARKER:section-start -->\n\n"
        "Summary body\n\n"
        "<!-- MARKER:section-end -->\n"
    )
    docx_bytes = markdown_to_docx_bytes(markdown)

    converted = docx_bytes_to_markdown(docx_bytes)

    assert "<!-- MARKER:section-start -->" in converted
    assert "<!-- MARKER:section-end -->" in converted


def test_docx_round_trip_preserves_italic_heading_segments():
    markdown = "## *Matan Torathenou* et *Qabbalat ha-Torah*"

    docx_bytes = markdown_to_docx_bytes(markdown)
    converted = docx_bytes_to_markdown(docx_bytes)

    assert "## *Matan Torathenou* et *Qabbalat ha-Torah*" in converted


def test_docx_heading_import_ignores_heading_bold_noise_in_italic_runs():
    document = Document()
    heading = document.add_heading(level=2)

    run_one = heading.add_run("Matan Torathenou")
    run_one.italic = True
    heading.add_run(" et ")
    run_two = heading.add_run("Qabbalat")
    run_two.italic = True
    run_three = heading.add_run(" ha-Torah")
    run_three.italic = True
    run_three.bold = True

    output = BytesIO()
    document.save(output)

    converted = docx_bytes_to_markdown(output.getvalue())

    assert converted == "## *Matan Torathenou* et *Qabbalat ha-Torah*"


def test_docx_import_escapes_literal_markdown_control_chars():
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run(r"Price *value* and key_name ")
    italic = paragraph.add_run(r"*wrapped* _token_")
    italic.italic = True

    output = BytesIO()
    document.save(output)

    converted = docx_bytes_to_markdown(output.getvalue())

    assert converted == r"Price \*value\* and key\_name *\*wrapped\* \_token\_*"
