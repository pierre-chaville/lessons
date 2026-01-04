"""PDF generation using ReportLab (pure Python, no native dependencies)."""

from io import BytesIO
from datetime import datetime
from typing import Optional, List
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os


def _register_unicode_fonts():
    """Register Unicode-compatible fonts for Hebrew and other RTL languages."""
    try:
        # Try to register common system fonts that support Hebrew/Unicode
        # On Windows, use Arial or Segoe UI which support Hebrew

        # Check for Windows fonts
        windows_fonts = [
            (r"C:\Windows\Fonts\arial.ttf", "Arial"),
            (r"C:\Windows\Fonts\arialbd.ttf", "Arial-Bold"),
            (r"C:\Windows\Fonts\ariali.ttf", "Arial-Italic"),
            (r"C:\Windows\Fonts\segoeui.ttf", "SegoeUI"),
            (r"C:\Windows\Fonts\segoeuib.ttf", "SegoeUI-Bold"),
        ]

        registered = False
        for font_path, font_name in windows_fonts:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    registered = True
                except Exception:
                    pass

        return registered
    except Exception:
        return False


# Try to register fonts on module load
_fonts_registered = _register_unicode_fonts()


def _parse_markdown_to_paragraphs(markdown_text: str, styles) -> List:
    """Convert simple markdown to ReportLab paragraphs.

    Supports: headings (#, ##, ###), bold (**text**), italic (*text*),
    code (`code`), lists (- item), and paragraphs.
    """
    flowables = []
    lines = markdown_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            flowables.append(Spacer(1, 0.3 * cm))
            i += 1
            continue

        # Headings
        if line.startswith("### "):
            text = line[4:].strip()
            flowables.append(Paragraph(text, styles["Heading3"]))
            flowables.append(Spacer(1, 0.3 * cm))
        elif line.startswith("## "):
            text = line[3:].strip()
            flowables.append(Paragraph(text, styles["Heading2"]))
            flowables.append(Spacer(1, 0.4 * cm))
        elif line.startswith("# "):
            text = line[2:].strip()
            flowables.append(Paragraph(text, styles["Heading1"]))
            flowables.append(Spacer(1, 0.5 * cm))
        # Check for standalone bold text as a heading (e.g., **L'Ancrage**)
        elif line.startswith("**") and line.endswith("**") and line.count("**") == 2:
            text = line[2:-2].strip()
            flowables.append(Paragraph(text, styles["Heading3"]))
            flowables.append(Spacer(1, 0.3 * cm))
        # List items
        elif line.startswith("- ") or line.startswith("* "):
            text = line[2:].strip()
            text = _apply_inline_formatting(text)
            flowables.append(Paragraph(f"• {text}", styles["BodyText"]))
        # Regular paragraph
        else:
            text = _apply_inline_formatting(line)
            flowables.append(Paragraph(text, styles["BodyText"]))

        i += 1

    return flowables


def _apply_inline_formatting(text: str) -> str:
    """Apply inline markdown formatting (bold, italic, code)."""
    # Code (backticks)
    import re

    text = re.sub(
        r"`([^`]+)`",
        r'<font name="Courier" size="10" backColor="#f3f4f6">\1</font>',
        text,
    )

    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)

    # Italic
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)

    return text


def generate_lesson_summary_pdf(
    title: str,
    summary_markdown: str,
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
    prompt_name: Optional[str] = None,
) -> bytes:
    """Generate a PDF from a lesson summary (markdown format).

    Args:
        title: Lesson title
        summary_markdown: Summary text in markdown format
        date: Lesson date
        course_name: Associated course name
        prompt_name: Name of the prompt used to generate the summary

    Returns:
        PDF file as bytes
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    # Custom styles
    styles = getSampleStyleSheet()

    # Use Arial font for Unicode/Hebrew support if registered
    font_name = "Arial" if _fonts_registered else "Helvetica"

    # Title style
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=24,
        textColor=HexColor("#4f46e5"),
        spaceAfter=12,
        alignment=TA_LEFT,
    )

    # Metadata style
    metadata_style = ParagraphStyle(
        "Metadata",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        textColor=HexColor("#666666"),
        spaceAfter=6,
        spaceBefore=6,
        leftIndent=10,
        rightIndent=10,
        backColor=HexColor("#f9fafb"),
    )

    # Heading styles
    styles["Heading1"].fontName = font_name
    styles["Heading1"].textColor = HexColor("#4f46e5")
    styles["Heading1"].fontSize = 18
    styles["Heading1"].spaceAfter = 12

    styles["Heading2"].fontName = font_name
    styles["Heading2"].textColor = HexColor("#6366f1")
    styles["Heading2"].fontSize = 16
    styles["Heading2"].spaceAfter = 10

    styles["Heading3"].fontName = font_name
    styles["Heading3"].textColor = HexColor("#818cf8")
    styles["Heading3"].fontSize = 14
    styles["Heading3"].spaceAfter = 8

    # Body text style
    styles["BodyText"].fontName = font_name
    styles["BodyText"].fontSize = 11
    styles["BodyText"].leading = 16
    styles["BodyText"].spaceAfter = 8

    # Build content
    story = []

    # Title
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.5 * cm))

    # Metadata
    if date or course_name or prompt_name:
        if date:
            date_str = date.strftime("%Y-%m-%d %H:%M")
            story.append(Paragraph(f"<b>Date:</b> {date_str}", metadata_style))
        if course_name:
            story.append(Paragraph(f"<b>Course:</b> {course_name}", metadata_style))
        if prompt_name:
            story.append(
                Paragraph(f"<b>Summary Type:</b> {prompt_name}", metadata_style)
            )
        story.append(Spacer(1, 0.5 * cm))

    # Summary content (parse markdown)
    content_flowables = _parse_markdown_to_paragraphs(summary_markdown, styles)
    story.extend(content_flowables)

    # Generate PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_lesson_transcript_pdf(
    title: str,
    transcript: List[dict],
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
    transcript_type: str = "corrected",
) -> bytes:
    """Generate a PDF from a lesson transcript.

    Args:
        title: Lesson title
        transcript: List of transcript segments (each with 'text' field)
        date: Lesson date
        course_name: Associated course name
        transcript_type: Type of transcript ("corrected" or "initial")

    Returns:
        PDF file as bytes
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    # Custom styles
    styles = getSampleStyleSheet()

    # Use Arial font for Unicode/Hebrew support if registered
    font_name = "Arial" if _fonts_registered else "Helvetica"

    # Title style
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=24,
        textColor=HexColor("#4f46e5"),
        spaceAfter=12,
        alignment=TA_LEFT,
    )

    # Metadata style
    metadata_style = ParagraphStyle(
        "Metadata",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        textColor=HexColor("#666666"),
        spaceAfter=6,
        spaceBefore=6,
        leftIndent=10,
        rightIndent=10,
        backColor=HexColor("#f9fafb"),
    )

    # Transcript text style
    transcript_style = ParagraphStyle(
        "TranscriptText",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=11,
        leading=18,
        alignment=TA_LEFT,
    )

    # Build content
    story = []

    # Title
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.5 * cm))

    # Metadata
    if date:
        date_str = date.strftime("%Y-%m-%d %H:%M")
        story.append(Paragraph(f"<b>Date:</b> {date_str}", metadata_style))
    if course_name:
        story.append(Paragraph(f"<b>Course:</b> {course_name}", metadata_style))
    story.append(
        Paragraph(
            f"<b>Transcript Type:</b> {transcript_type.capitalize()}", metadata_style
        )
    )
    story.append(Spacer(1, 0.5 * cm))

    # Transcript segments
    for segment in transcript:
        text = segment.get("text", "").strip()
        if text:
            story.append(Paragraph(f"• {text}", transcript_style))

    # Generate PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
