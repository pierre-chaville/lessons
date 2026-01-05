"""PDF generation using ReportLab (pure Python, no native dependencies)."""

from io import BytesIO
from datetime import datetime
from typing import Optional, List
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
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
    """Apply inline markdown formatting (bold, italic, code) and handle Hebrew RTL text."""
    import re
    from bidi.algorithm import get_display

    # First apply markdown formatting
    # Code (backticks)
    text = re.sub(
        r"`([^`]+)`",
        r'<font name="Courier" size="10" backColor="#f3f4f6">\1</font>',
        text,
    )

    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)

    # Italic
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)

    # Check if text contains Hebrew characters
    if re.search(r"[\u0590-\u05FF]", text):
        # Apply bidi algorithm to the entire text for proper RTL/LTR mixing
        # The algorithm will handle the word order correctly
        text = get_display(text)
        # Wrap in Arial font for Hebrew support
        text = f'<font name="Arial">{text}</font>'

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


def generate_lesson_edited_transcript_pdf(
    title: str,
    edited_transcript: List[dict],
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
) -> bytes:
    """Generate a PDF from an edited transcript with sources.

    Args:
        title: Lesson title
        edited_transcript: List of edited parts (each with 'start', 'end', 'text', 'sources')
        date: Lesson date
        course_name: Associated course name

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

    # Edited text style
    edited_style = ParagraphStyle(
        "EditedText",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=11,
        leading=18,
        alignment=TA_LEFT,
    )

    # Timing style
    timing_style = ParagraphStyle(
        "Timing",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        textColor=HexColor("#6366f1"),
        spaceAfter=6,
    )

    # Source style
    source_style = ParagraphStyle(
        "Source",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        textColor=HexColor("#059669"),
        leftIndent=20,
        spaceAfter=4,
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
    story.append(Paragraph("<b>Document Type:</b> Edited Transcript", metadata_style))
    story.append(Spacer(1, 0.5 * cm))

    # Edited transcript parts
    for part in edited_transcript:
        text = part.get("text", "").strip()
        sources = part.get("sources", [])

        if text:
            # Add source markers to text
            marked_text = text
            if sources:
                # Filter sources with cited_excerpt
                sources_with_excerpt = [
                    (i, src)
                    for i, src in enumerate(sources)
                    if src.get("cited_excerpt")
                ]

                # Sort by excerpt length (longest first) to avoid nested replacements
                sources_with_excerpt.sort(
                    key=lambda x: len(x[1].get("cited_excerpt", "")), reverse=True
                )

                for idx, source in sources_with_excerpt:
                    marker = idx + 1
                    excerpt = source.get("cited_excerpt", "")
                    if excerpt and excerpt in marked_text:
                        # Add superscript marker
                        marked_excerpt = f"{excerpt}<super>[{marker}]</super>"
                        marked_text = marked_text.replace(excerpt, marked_excerpt, 1)

            # Add edited text with markers
            story.append(Paragraph(_apply_inline_formatting(marked_text), edited_style))
            story.append(Spacer(1, 0.2 * cm))

            # Add sources only if they exist
            if sources:
                for idx, source in enumerate(sources):
                    marker = idx + 1
                    author = source.get("author", "Unknown")
                    work = source.get("work", "")
                    reference = source.get("reference", "")
                    source_text = source.get("text", "")

                    source_info = f"<b>[{marker}]</b> <b>{author}</b>"
                    if work:
                        source_info += f", <i>{work}</i>"
                    if reference:
                        source_info += f" ({reference})"
                    if source_text:
                        source_info += f": {source_text[:100]}{'...' if len(source_text) > 100 else ''}"

                    story.append(Paragraph(source_info, source_style))

            story.append(Spacer(1, 0.4 * cm))

    # Generate PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_lesson_sources_pdf(
    title: str,
    edited_transcript: List[dict],
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
) -> bytes:
    """Generate a PDF with all sources grouped by author.

    Args:
        title: Lesson title
        edited_transcript: List of edited parts (each with 'sources')
        date: Lesson date
        course_name: Associated course name

    Returns:
        PDF file as bytes
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    # Create styles
    styles = getSampleStyleSheet()

    # Use Arial font if registered
    default_font = "Arial" if _fonts_registered else "Helvetica"

    # Title style
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontName=f"{default_font}-Bold" if _fonts_registered else "Helvetica-Bold",
        fontSize=20,
        textColor=HexColor("#1f2937"),
        spaceAfter=12,
        alignment=TA_CENTER,
    )

    # Metadata style
    metadata_style = ParagraphStyle(
        "Metadata",
        parent=styles["Normal"],
        fontName=default_font,
        fontSize=10,
        textColor=HexColor("#6b7280"),
        spaceAfter=6,
        alignment=TA_CENTER,
    )

    # Author header style
    author_style = ParagraphStyle(
        "AuthorHeader",
        parent=styles["Heading2"],
        fontName=f"{default_font}-Bold" if _fonts_registered else "Helvetica-Bold",
        fontSize=14,
        textColor=HexColor("#1f2937"),
        spaceAfter=8,
        spaceBefore=12,
    )

    # Source style
    source_style = ParagraphStyle(
        "Source",
        parent=styles["Normal"],
        fontName=default_font,
        fontSize=10,
        textColor=HexColor("#374151"),
        leftIndent=20,
        spaceAfter=6,
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
    story.append(Paragraph("<b>Document Type:</b> Sources", metadata_style))
    story.append(Spacer(1, 0.8 * cm))

    # Collect and group sources by author
    author_sources = {}
    for part in edited_transcript:
        if part.get("sources"):
            for source in part["sources"]:
                author = source.get("author", "Unknown")
                if author not in author_sources:
                    author_sources[author] = []
                author_sources[author].append(source)

    # Sort authors alphabetically
    sorted_authors = sorted(author_sources.keys())

    # Generate content for each author
    for author in sorted_authors:
        # Author header
        story.append(Paragraph(_apply_inline_formatting(author), author_style))

        # List all sources for this author
        sources = author_sources[author]
        for source in sources:
            work = source.get("work", "")
            reference = source.get("reference", "")
            text = source.get("text", "")
            cited_excerpt = source.get("cited_excerpt", "")

            # Build source line with bullet point
            source_parts = []
            if work:
                source_parts.append(f"<i>{work}</i>")
            if reference:
                source_parts.append(reference)
            if text:
                # Truncate long source text
                truncated_text = text[:150] + "..." if len(text) > 150 else text
                source_parts.append(f'"{truncated_text}"')

            source_line = ", ".join(source_parts) if source_parts else "No details"
            # Add bullet point at the beginning
            bullet_line = f"• {source_line}"
            story.append(Paragraph(_apply_inline_formatting(bullet_line), source_style))
            
            # Add referenced text (cited excerpt) if it exists
            if cited_excerpt:
                # Truncate long excerpts
                truncated_excerpt = cited_excerpt[:200] + "..." if len(cited_excerpt) > 200 else cited_excerpt
                excerpt_text = f'<i>Referenced in: "{truncated_excerpt}"</i>'
                # Create a style for the excerpt with extra left indent
                excerpt_style = ParagraphStyle(
                    'SourceExcerpt',
                    parent=source_style,
                    leftIndent=40,
                    fontSize=9,
                    textColor=colors.HexColor('#666666')
                )
                story.append(Paragraph(_apply_inline_formatting(excerpt_text), excerpt_style))

        story.append(Spacer(1, 0.3 * cm))

    # Generate PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
