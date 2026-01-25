"""PDF generation using ReportLab (pure Python, no native dependencies)."""

from io import BytesIO
from datetime import datetime
from typing import Optional, List
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether, Frame, PageTemplate, BaseDocTemplate
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
import os
import httpx
import re
from html import unescape
import re
from html import unescape


def _register_unicode_fonts():
    """Register Unicode-compatible fonts for Hebrew and other RTL languages."""
    global _fonts_registered
    _fonts_registered = False
    
    try:
        # Try to register Arial font (common on Windows)
        arial_paths = [
            ("Arial", "C:/Windows/Fonts/arial.ttf"),
            ("Arial", "C:/Windows/Fonts/ARIAL.TTF"),
            ("Arial", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            ("Arial", "/System/Library/Fonts/Helvetica.ttc"),
        ]
        
        # Try to register Arial Bold
        arial_bold_paths = [
            ("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"),
            ("Arial-Bold", "C:/Windows/Fonts/ARIALBD.TTF"),
            ("Arial-Bold", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ]
        
        # Register regular Arial
        for font_name, font_path in arial_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont("Arial", font_path))
                    _fonts_registered = True
                    break
                except Exception as e:
                    continue
        
        # Register Arial Bold if regular was registered
        if _fonts_registered:
            for font_name, font_path in arial_bold_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont("Arial-Bold", font_path))
                        break
                    except Exception as e:
                        continue
            # If bold font not found, use regular Arial for bold (fallback)
            if "Arial-Bold" not in pdfmetrics.getRegisteredFontNames():
                try:
                    # Use regular Arial as fallback for bold
                    pdfmetrics.registerFont(TTFont("Arial-Bold", arial_paths[0][1]))
                except Exception:
                    pass
    except Exception:
        pass


# Register fonts on import
_register_unicode_fonts()


def _apply_inline_formatting(text: str) -> str:
    """
    Apply basic inline formatting to text for ReportLab Paragraph.
    Converts markdown-style formatting to HTML tags.
    """
    if not text:
        return ""
    
    # Escape HTML special characters first
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    
    # Apply formatting (simple markdown-like)
    # Bold: **text** or __text__
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # Italic: *text* or _text_
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
    
    # Code: `text`
    text = re.sub(r'`(.+?)`', r'<font name="Courier">\1</font>', text)
    
    return text


class NumberedCanvas(canvas.Canvas):
    """Custom canvas with page numbering and footer"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.footer_title = ""
        self.doc_type = ""

    def draw_footer(self):
        """Draw footer with page number and document info"""
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(HexColor("#666666"))
        
        # Footer text
        footer_text = f"{self.footer_title} - {self.doc_type}"
        page_text = f"Page {self._pageNumber}"
        
        # Draw footer
        self.drawRightString(self._pagesize[0] - 2 * cm, 1.5 * cm, page_text)
        self.drawString(2 * cm, 1.5 * cm, footer_text)
        
        self.restoreState()

    def showPage(self):
        """Override to add footer before new page"""
        self.draw_footer()
        super().showPage()

    def save(self):
        """Override to add footer on last page"""
        self.draw_footer()
        super().save()


def generate_lesson_summary_pdf(
    title: str,
    summary_markdown: str,
    filename: str,
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
    prompt_name: Optional[str] = None,
) -> bytes:
    """Generate a PDF from a lesson summary (markdown).

    Args:
        title: Lesson title
        summary_markdown: Summary text in markdown format
        filename: Original audio filename
        date: Lesson date
        course_name: Associated course name
        prompt_name: Optional prompt name used for summary

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
        bottomMargin=3 * cm,
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

    # Summary text style
    summary_style = ParagraphStyle(
        "SummaryText",
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
    if prompt_name:
        story.append(Paragraph(f"<b>Prompt:</b> {prompt_name}", metadata_style))
    story.append(
        Paragraph("<b>Document Type:</b> Summary", metadata_style)
    )
    story.append(Spacer(1, 0.5 * cm))

    # Convert markdown to HTML-like format for ReportLab
    # Simple markdown parsing
    summary_lines = summary_markdown.split("\n")
    for line in summary_lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.3 * cm))
            continue

        # Headers
        if line.startswith("# "):
            header_style = ParagraphStyle(
                "H1",
                parent=styles["Heading1"],
                fontName=font_name,
                fontSize=18,
                textColor=HexColor("#1f2937"),
                spaceAfter=12,
                spaceBefore=12,
            )
            story.append(Paragraph(_apply_inline_formatting(line[2:]), header_style))
        elif line.startswith("## "):
            header_style = ParagraphStyle(
                "H2",
                parent=styles["Heading2"],
                fontName=font_name,
                fontSize=14,
                textColor=HexColor("#374151"),
                spaceAfter=8,
                spaceBefore=10,
            )
            story.append(Paragraph(_apply_inline_formatting(line[3:]), header_style))
        elif line.startswith("### "):
            header_style = ParagraphStyle(
                "H3",
                parent=styles["Heading3"],
                fontName=font_name,
                fontSize=12,
                textColor=HexColor("#4b5563"),
                spaceAfter=6,
                spaceBefore=8,
            )
            story.append(Paragraph(_apply_inline_formatting(line[4:]), header_style))
        else:
            # Regular paragraph
            story.append(Paragraph(_apply_inline_formatting(line), summary_style))

    # Build PDF with custom canvas for page numbering
    def create_canvas_with_footer(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.footer_title = title
        c.doc_type = "Summary"
        return c

    doc.build(story, canvasmaker=create_canvas_with_footer)

    return buffer.getvalue()


def generate_lesson_transcript_pdf(
    title: str,
    transcript: List[dict],
    filename: str,
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
    transcript_type: str = "corrected",
) -> bytes:
    """Generate a PDF from a lesson transcript.

    Args:
        title: Lesson title
        transcript: List of transcript segments (each with 'text' field)
        filename: Original audio filename
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
        bottomMargin=3 * cm,
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

    # Prepare transcript segments for two-column layout
    transcript_segments = []
    for segment in transcript:
        text = segment.get("text", "").strip()
        if text:
            transcript_segments.append(Paragraph(f"• {text}", transcript_style))
    
    if not transcript_segments:
        story.append(Paragraph("No transcript segments available.", transcript_style))
        # Build PDF with custom canvas for page numbering
        def create_canvas_with_footer(*args, **kwargs):
            c = NumberedCanvas(*args, **kwargs)
            c.footer_title = title
            c.doc_type = "Transcript"
            return c
        doc.build(story, canvasmaker=create_canvas_with_footer)
        return buffer.getvalue()
    
    # For continuous column flow, we need to use BaseDocTemplate with frames
    # Calculate column dimensions
    page_width = A4[0]
    page_height = A4[1]
    usable_width = page_width - (doc.leftMargin + doc.rightMargin)
    column_width = (usable_width - 0.5 * cm) / 2  # Leave 0.5cm gap between columns
    gap = 0.5 * cm
    frame_height = page_height - doc.topMargin - doc.bottomMargin
    
    # Create a custom document template with two-column frames
    class TwoColumnDocTemplate(BaseDocTemplate):
        def __init__(self, buffer, title_for_footer, **kwargs):
            BaseDocTemplate.__init__(self, buffer, **kwargs)
            # Calculate frame positions
            left_x = self.leftMargin
            right_x = self.leftMargin + column_width + gap
            frame_y = self.bottomMargin
            
            # Create full-width frame for title/metadata (first page only)
            full_frame = Frame(
                left_x,
                frame_y,
                usable_width,
                frame_height,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
                id='full'
            )
            
            # Create two frames side by side for transcript columns
            left_frame = Frame(
                left_x,
                frame_y,
                column_width,
                frame_height,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
                id='left'
            )
            
            right_frame = Frame(
                right_x,
                frame_y,
                column_width,
                frame_height,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
                id='right'
            )
            
            # Store title for footer
            self.footer_title = title_for_footer
            
            # Create page template with full-width frame (for title/metadata)
            first_page_template = PageTemplate(
                id='first_page',
                frames=[full_frame],
                onPage=self.on_page
            )
            
            # Create page template with two-column frames (for transcript)
            two_column_template = PageTemplate(
                id='two_column',
                frames=[left_frame, right_frame],
                onPage=self.on_page
            )
            
            self.addPageTemplates([first_page_template, two_column_template])
            self._first_page_used = False
        
        def afterPage(self):
            """Switch to two-column template after first page"""
            if not self._first_page_used:
                self._first_page_used = True
                # Switch to two-column template
                self.pageTemplate = self.pageTemplates[1]
        
        def on_page(self, canvas, doc):
            """Called on each page - add footer"""
            canvas.saveState()
            canvas.setFont("Helvetica", 9)
            canvas.setFillColor(HexColor("#666666"))
            
            # Footer text
            footer_text = f"{self.footer_title} - Transcript"
            page_text = f"Page {doc.page}"
            
            # Draw footer
            canvas.drawRightString(page_width - 2 * cm, 1.5 * cm, page_text)
            canvas.drawString(2 * cm, 1.5 * cm, footer_text)
            canvas.restoreState()
    
    # Create new document with two-column template
    two_col_doc = TwoColumnDocTemplate(
        buffer,
        title_for_footer=title,
        pagesize=A4,
        rightMargin=doc.rightMargin,
        leftMargin=doc.leftMargin,
        topMargin=doc.topMargin,
        bottomMargin=doc.bottomMargin,
    )
    
    # Build the story - title/metadata flows in full-width frame first,
    # then transcript flows in two columns (left, then right, then next page)
    # Add page break after title/metadata to switch to two-column layout
    two_col_doc.build(story + [PageBreak()] + transcript_segments)

    return buffer.getvalue()


def generate_lesson_edited_transcript_pdf(
    title: str,
    edited_transcript: List[dict],
    filename: str,
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
) -> bytes:
    """Generate a PDF from an edited transcript with sources.

    Args:
        title: Lesson title
        edited_transcript: List of edited parts (each with 'start', 'end', 'text', 'sources')
        filename: Original audio filename
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
        bottomMargin=3 * cm,
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
    source_counter = 0  # Global counter for source numbers
    for part in edited_transcript:
        text = part.get("text", "").strip()
        sources = part.get("sources", [])

        if text:
            # Add source markers to text
            marked_text = text
            if sources:
                # Try to find cited excerpts in the text by matching source text
                # We'll look for translation_text or original_text in the edited text
                sources_with_match = []
                for i, src in enumerate(sources):
                    translation_text = src.get("translation_text", "")
                    original_text = src.get("original_text", "")
                    # Try to find a match in the text
                    excerpt = None
                    if translation_text and translation_text in text:
                        excerpt = translation_text
                    elif original_text and original_text in text:
                        excerpt = original_text
                    if excerpt:
                        sources_with_match.append((i, src, excerpt))

                # Sort by excerpt length (longest first) to avoid nested replacements
                sources_with_match.sort(
                    key=lambda x: len(x[2]), reverse=True
                )

                for idx, source, excerpt in sources_with_match:
                    marker = source_counter + idx + 1
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
                    marker = source_counter + idx + 1
                    source_type = source.get("type", "Unknown")
                    work = source.get("work", "")
                    ref = source.get("ref", "")
                    standard_slug = source.get("standard_slug", "")
                    translation_text = source.get("translation_text", "")
                    original_text = source.get("original_text", "")
                    confidence = source.get("confidence")
                    
                    # Use translation_text if available, otherwise original_text
                    source_text = translation_text if translation_text else original_text

                    # Build source citation
                    source_info = f"<b>[{marker}]</b>"
                    if source_type:
                        source_info += f" <b>{source_type}</b>"
                    if work:
                        source_info += f", <i>{work}</i>"
                    if ref:
                        source_info += f" {ref}"
                    if standard_slug:
                        source_info += f" ({standard_slug})"
                    if source_text:
                        source_info += f": {source_text[:100]}{'...' if len(source_text) > 100 else ''}"
                    if confidence is not None:
                        source_info += f" [Confidence: {int(confidence * 100)}%]"

                    story.append(Paragraph(source_info, source_style))

                # Increment counter by the number of sources in this part
                source_counter += len(sources)

            story.append(Spacer(1, 0.4 * cm))

    # Build PDF with custom canvas for page numbering
    def create_canvas_with_footer(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.footer_title = title
        c.doc_type = "Edited"
        return c

    doc.build(story, canvasmaker=create_canvas_with_footer)

    return buffer.getvalue()


def generate_lesson_sources_pdf(
    title: str,
    edited_transcript: List[dict],
    filename: str,
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
) -> bytes:
    """Generate a PDF with all sources grouped by author.

    Args:
        title: Lesson title
        edited_transcript: List of edited parts (each with 'sources')
        filename: Original audio filename
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
        bottomMargin=3 * cm,
    )

    # Create styles
    styles = getSampleStyleSheet()

    # Use Arial font if registered
    default_font = "Arial" if _fonts_registered else "Helvetica"

    # Title style - use Helvetica-Bold as it's always available
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
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

    # Author header style - use Helvetica-Bold as it's always available
    author_style = ParagraphStyle(
        "AuthorHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
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

    # Collect and group sources by type
    type_sources = {}
    for part in edited_transcript:
        if part.get("sources"):
            for source in part["sources"]:
                source_type = source.get("type") or "Unknown"  # Handle None values
                if source_type not in type_sources:
                    type_sources[source_type] = []
                type_sources[source_type].append(source)

    # Sort types alphabetically (None values are handled by using "Unknown" as default)
    sorted_types = sorted(type_sources.keys())

    # Generate content for each type
    for source_type in sorted_types:
        # Type header
        story.append(Paragraph(_apply_inline_formatting(source_type), author_style))

        # List all sources for this type
        sources = type_sources[source_type]
        for source in sources:
            work = source.get("work", "")
            ref = source.get("ref", "")
            standard_slug = source.get("standard_slug", "")
            translation_text = source.get("translation_text", "")
            original_text = source.get("original_text", "")
            confidence = source.get("confidence")
            
            # Use translation_text if available, otherwise original_text
            source_text = translation_text if translation_text else original_text

            # Build source line with bullet point
            source_parts = []
            if work:
                source_parts.append(f"<i>{work}</i>")
            if ref:
                source_parts.append(ref)
            if standard_slug:
                source_parts.append(f"({standard_slug})")
            if source_text:
                # Truncate long source text
                truncated_text = source_text[:150] + "..." if len(source_text) > 150 else source_text
                source_parts.append(f'"{truncated_text}"')
            if confidence is not None:
                source_parts.append(f"[Confidence: {int(confidence * 100)}%]")

            source_line = ", ".join(source_parts) if source_parts else "No details"
            # Add bullet point at the beginning
            bullet_line = f"• {source_line}"
            story.append(Paragraph(_apply_inline_formatting(bullet_line), source_style))

            # Add verification information if available
            verification_parts = []
            slug_retrieved = source.get("slug_retrieved")
            citation_found = source.get("citation_found")
            verification_confidence = source.get("verification_confidence")
            
            if slug_retrieved is not None:
                status = "Yes" if slug_retrieved else "No"
                verification_parts.append(f"Slug retrieved: {status}")
            if citation_found is not None:
                status = "Yes" if citation_found else "No"
                verification_parts.append(f"Citation found: {status}")
            if verification_confidence is not None:
                verification_parts.append(f"Verification confidence: {int(verification_confidence * 100)}%")
            
            if verification_parts:
                verification_text = f'<i>Verification: {", ".join(verification_parts)}</i>'
                # Create a style for the verification info with extra left indent
                verification_style = ParagraphStyle(
                    "SourceVerification",
                    parent=source_style,
                    leftIndent=40,
                    fontSize=9,
                    textColor=colors.HexColor("#666666"),
                )
                story.append(
                    Paragraph(_apply_inline_formatting(verification_text), verification_style)
                )

        story.append(Spacer(1, 0.3 * cm))

    # Build PDF with custom canvas for page numbering
    def create_canvas_with_footer(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.footer_title = title
        c.doc_type = "Sources"
        return c

    doc.build(story, canvasmaker=create_canvas_with_footer)

    return buffer.getvalue()


def generate_lesson_detailed_sources_pdf(
    title: str,
    edited_transcript: List[dict],
    filename: str,
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
) -> bytes:
    """Generate a detailed PDF with all sources showing full information (like the modal).

    Args:
        title: Lesson title
        edited_transcript: List of edited parts (each with 'sources')
        filename: Original audio filename
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
        bottomMargin=3 * cm,
    )

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

    # Section header style - use Helvetica-Bold as it's always available
    section_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=HexColor("#1f2937"),
        spaceAfter=8,
        spaceBefore=12,
    )

    # Source info style
    source_info_style = ParagraphStyle(
        "SourceInfo",
        parent=styles["Normal"],
        fontName=default_font,
        fontSize=10,
        textColor=HexColor("#374151"),
        leftIndent=20,
        spaceAfter=4,
    )

    # Source text style
    source_text_style = ParagraphStyle(
        "SourceText",
        parent=styles["Normal"],
        fontName=default_font,
        fontSize=10,
        textColor=HexColor("#374151"),
        leftIndent=30,
        spaceAfter=6,
        fontStyle='italic',
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
    story.append(Paragraph("<b>Document Type:</b> Detailed Sources Review", metadata_style))
    story.append(Spacer(1, 0.8 * cm))

    # Collect all sources with their edited part text
    all_sources_with_context = []
    for part in edited_transcript:
        if part.get("sources"):
            part_text = part.get("text", "")
            for source in part["sources"]:
                all_sources_with_context.append({
                    "source": source,
                    "edited_part_text": part_text
                })

    # Generate detailed content for each source
    for idx, item in enumerate(all_sources_with_context, 1):
        source = item["source"]
        edited_part_text = item["edited_part_text"]
        
        # Source number header
        source_type = source.get("type") or "Unknown"
        work = source.get("work", "")
        ref = source.get("ref", "")
        source_header = f"Source {idx}"
        if source_type:
            source_header += f" - {source_type}"
        if work:
            source_header += f": {work}"
        if ref:
            source_header += f" {ref}"
        
        story.append(Paragraph(_apply_inline_formatting(source_header), section_style))
        
        # Edited Part Text
        if edited_part_text:
            story.append(Paragraph("<b>Edited Part Text:</b>", source_info_style))
            story.append(Paragraph(_apply_inline_formatting(edited_part_text), source_text_style))
            story.append(Spacer(1, 0.3 * cm))
        
        # Source Information
        story.append(Paragraph("<b>Source Information:</b>", source_info_style))
        
        info_lines = []
        if source.get("type"):
            info_lines.append(f"Type: {source.get('type')}")
        if source.get("work"):
            info_lines.append(f"Work: {source.get('work')}")
        if source.get("ref"):
            info_lines.append(f"Reference: {source.get('ref')}")
        if source.get("standard_slug"):
            info_lines.append(f"Slug: {source.get('standard_slug')}")
        if source.get("original_text"):
            info_lines.append(f"Original Text: {source.get('original_text')}")
        if source.get("translation_text"):
            info_lines.append(f"Translation Text: {source.get('translation_text')}")
        if source.get("confidence") is not None:
            confidence_pct = int(source.get("confidence") * 100)
            info_lines.append(f"Initial Confidence: {confidence_pct}%")
        
        for line in info_lines:
            story.append(Paragraph(_apply_inline_formatting(line), source_info_style))
        
        story.append(Spacer(1, 0.3 * cm))
        
        # Verification Status
        if source.get("slug_retrieved") is not None or source.get("citation_found") is not None:
            story.append(Paragraph("<b>Verification Status:</b>", source_info_style))
            
            verification_lines = []
            if source.get("slug_retrieved") is not None:
                status = "Yes" if source.get("slug_retrieved") else "No"
                verification_lines.append(f"Slug Retrieved: {status}")
            if source.get("citation_found") is not None:
                status = "Yes" if source.get("citation_found") else "No"
                verification_lines.append(f"Citation Found: {status}")
            if source.get("verification_confidence") is not None:
                conf_pct = int(source.get("verification_confidence") * 100)
                verification_lines.append(f"Verification Confidence: {conf_pct}%")
            if source.get("verification_explanation"):
                verification_lines.append(f"Explanation: {source.get('verification_explanation')}")
            if source.get("matched_text"):
                verification_lines.append(f"Matched Text: {source.get('matched_text')}")
            
            for line in verification_lines:
                story.append(Paragraph(_apply_inline_formatting(line), source_info_style))
            
            story.append(Spacer(1, 0.3 * cm))
        
        # Sefaria Text (fetch if slug available)
        standard_slug = source.get("standard_slug")
        if standard_slug:
            story.append(Paragraph(f"<b>Text from Sefaria ({standard_slug}):</b>", source_info_style))
            
            try:
                # Fetch Sefaria text synchronously
                sefaria_url = f"https://www.sefaria.org/api/texts/{standard_slug}"
                with httpx.Client(timeout=30.0) as client:
                    response = client.get(sefaria_url)
                    response.raise_for_status()
                    sefaria_data = response.json()
                    
                    # Extract text from response
                    sefaria_text = ""
                    if "text" in sefaria_data:
                        text_data = sefaria_data["text"]
                        if isinstance(text_data, list):
                            sefaria_text = "\n".join(
                                item if isinstance(item, str) else " ".join(item)
                                for item in text_data
                            )
                        elif isinstance(text_data, str):
                            sefaria_text = text_data
                    elif "he" in sefaria_data:
                        sefaria_text = sefaria_data["he"]
                    else:
                        sefaria_text = str(sefaria_data)
                    
                    # Remove HTML tags
                    sefaria_text = re.sub(r'<[^>]+>', '', sefaria_text)
                    # Decode HTML entities
                    sefaria_text = unescape(sefaria_text)
                    
                    # Limit to first 10 lines
                    sefaria_lines = sefaria_text.split('\n')
                    if len(sefaria_lines) > 10:
                        sefaria_text = '\n'.join(sefaria_lines[:10])
                        sefaria_text += f"\n... ({len(sefaria_lines) - 10} more lines)"
                    
                    # Highlight matched text if available (after HTML removal)
                    matched_text = source.get("matched_text")
                    if matched_text:
                        # Remove HTML from matched_text for comparison
                        clean_matched_text = re.sub(r'<[^>]+>', '', matched_text)
                        clean_matched_text = unescape(clean_matched_text)
                        if clean_matched_text in sefaria_text:
                            # Simple highlighting - replace matched text with bold version
                            highlighted_text = sefaria_text.replace(
                                clean_matched_text,
                                f"<b>{clean_matched_text}</b>",
                                1
                            )
                            story.append(Paragraph(_apply_inline_formatting(highlighted_text), source_text_style))
                        else:
                            story.append(Paragraph(_apply_inline_formatting(sefaria_text), source_text_style))
                    else:
                        story.append(Paragraph(_apply_inline_formatting(sefaria_text), source_text_style))
            except Exception as e:
                error_msg = f"Error fetching text from Sefaria: {str(e)}"
                story.append(Paragraph(_apply_inline_formatting(error_msg), source_info_style))
        
        story.append(Spacer(1, 0.5 * cm))
        story.append(PageBreak())

    # Build PDF with custom canvas for page numbering
    def create_canvas_with_footer(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.footer_title = title
        c.doc_type = "Detailed Sources"
        return c

    doc.build(story, canvasmaker=create_canvas_with_footer)

    return buffer.getvalue()
