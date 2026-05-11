from io import BytesIO

from docx import Document
from docx.oxml.ns import qn

from services.markdown_docx import markdown_to_docx_bytes


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
