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
from config import load_config
import re
from html import unescape


_fonts_registered = False
_pdf_font_names = {
    "regular": "Helvetica",
    "bold": "Helvetica-Bold",
    "italic": "Helvetica-Oblique",
    "bold_italic": "Helvetica-BoldOblique",
}


def _register_first_available_font(font_name: str, candidate_paths: list[str]) -> bool:
    for font_path in candidate_paths:
        if not os.path.exists(font_path):
            continue
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            return True
        except Exception:
            continue
    return False


def _register_unicode_fonts():
    """Register Unicode-compatible fonts for Hebrew and other RTL languages."""
    global _fonts_registered
    global _pdf_font_names
    _fonts_registered = False
    
    try:
        regular_candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/ARIAL.TTF",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

        bold_candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/ARIALBD.TTF",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]

        italic_candidates = [
            "C:/Windows/Fonts/ariali.ttf",
            "C:/Windows/Fonts/ARIALI.TTF",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        ]

        bold_italic_candidates = [
            "C:/Windows/Fonts/arialbi.ttf",
            "C:/Windows/Fonts/ARIALBI.TTF",
            "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        ]

        regular_ok = _register_first_available_font("Arial", regular_candidates)
        if not regular_ok:
            return

        _fonts_registered = True
        _pdf_font_names = {
            "regular": "Arial",
            "bold": "Arial-Bold",
            "italic": "Arial-Italic",
            "bold_italic": "Arial-BoldItalic",
        }

        if not _register_first_available_font("Arial-Bold", bold_candidates):
            _register_first_available_font("Arial-Bold", regular_candidates)
        if not _register_first_available_font("Arial-Italic", italic_candidates):
            _register_first_available_font("Arial-Italic", regular_candidates)
        if not _register_first_available_font("Arial-BoldItalic", bold_italic_candidates):
            _register_first_available_font("Arial-BoldItalic", bold_candidates)

        # Ensure inline <b>/<i> tags keep using Unicode-capable family.
        pdfmetrics.registerFontFamily(
            "Arial",
            normal="Arial",
            bold="Arial-Bold",
            italic="Arial-Italic",
            boldItalic="Arial-BoldItalic",
        )
    except Exception:
        pass


# Register fonts on import
_register_unicode_fonts()


def get_pdf_font_names() -> dict[str, str]:
    """Return the active PDF font names (Unicode-capable when available)."""
    return dict(_pdf_font_names)


def _apply_inline_formatting(text: str) -> str:
    """
    Apply basic inline formatting to text for ReportLab Paragraph.
    Converts markdown-style formatting to HTML tags.
    """
    if not text:
        return ""
    
    import re
    
    # Escape HTML special characters first (but preserve tags we'll restore)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    
    # Restore valid HTML tags that ReportLab supports (after escaping)
    # ReportLab supports <sup> for superscript, so preserve it
    text = text.replace("&lt;sup&gt;", "<sup>")
    text = text.replace("&lt;/sup&gt;", "</sup>")
    text = text.replace("&lt;b&gt;", "<b>")
    text = text.replace("&lt;/b&gt;", "</b>")
    text = text.replace("&lt;i&gt;", "<i>")
    text = text.replace("&lt;/i&gt;", "</i>")
    text = text.replace("&lt;br/&gt;", "<br/>")
    text = text.replace("&lt;br&gt;", "<br/>")
    text = text.replace("&lt;font", "<font")
    text = text.replace("&lt;/font&gt;", "</font>")
    
    # Handle headers (### Header -> <b>Header</b>)
    # Process headers from largest to smallest to avoid conflicts
    text = re.sub(r'^####\s+(.+?)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^###\s+(.+?)$', r'<b><font size="14">\1</font></b>', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.+?)$', r'<b><font size="16">\1</font></b>', text, flags=re.MULTILINE)
    text = re.sub(r'^#\s+(.+?)$', r'<b><font size="18">\1</font></b>', text, flags=re.MULTILINE)
    
    # Apply formatting (simple markdown-like)
    # Bold: **text** or __text__ (process first to avoid conflicts with italic)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # Italic: *text* or _text_ (single asterisk/underscore, not double)
    # Use negative lookahead/behind to avoid matching inside bold
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!_)_([^_]+?)_(?!_)', r'<i>\1</i>', text)
    
    # Code: `text`
    text = re.sub(r'`(.+?)`', r'<font name="Courier">\1</font>', text)
    
    # Handle line breaks (double newline = paragraph break, single = line break)
    # ReportLab handles <br/> for line breaks
    text = re.sub(r'\n\n+', r'<br/><br/>', text)
    text = re.sub(r'\n(?!<br/>)', r'<br/>', text)
    
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
        footer_font = get_pdf_font_names()["regular"]
        self.setFont(footer_font, 9)
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
    brief_text: Optional[str],
    filename: str,
    date: Optional[datetime] = None,
    course_name: Optional[str] = None,
    prompt_name: Optional[str] = None,
    summary_metadata: Optional[dict] = None,
) -> bytes:
    """Generate a PDF from a lesson summary (markdown).

    Args:
        title: Lesson title
        summary_markdown: Summary text in markdown format
        brief_text: Optional brief summary text
        filename: Original audio filename
        date: Lesson date
        course_name: Associated course name
        prompt_name: Optional prompt name used for summary
        summary_metadata: Optional summary metadata dict (provider/model/temperature/max_tokens/prompt)

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
            footer_font = get_pdf_font_names()["regular"]
            canvas.setFont(footer_font, 9)
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
                        # Add superscript marker (ReportLab uses <sup> for superscript)
                        marked_excerpt = f"{excerpt}<sup>[{marker}]</sup>"
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


def _calculate_source_statistics(edited_transcript: List[dict]) -> tuple:
    """Calculate source statistics by type.
    
    Returns:
        Tuple of (source_stats_by_type, total_stats)
        source_stats_by_type: List of dicts with type, total, slugRetrieved, citationFound, checked
        total_stats: Dict with total, slugRetrieved, citationFound, checked
    """
    type_stats_map = {}
    
    for part in edited_transcript:
        if part.get("sources"):
            for source in part["sources"]:
                source_type = source.get("type") or "Unknown"
                
                if source_type not in type_stats_map:
                    type_stats_map[source_type] = {
                        "type": source_type,
                        "total": 0,
                        "slugRetrieved": 0,
                        "citationFound": 0,
                        "checked": 0
                    }
                
                stats = type_stats_map[source_type]
                stats["total"] += 1
                
                if source.get("slug_retrieved") is True:
                    stats["slugRetrieved"] += 1
                
                # Citation found: FOUND, SIMILAR, or PARTIAL
                verification_status = source.get("verification_status")
                if verification_status and verification_status in ["exactly_found", "paraphrase_or_similar", "partially_found"]:
                    stats["citationFound"] += 1
                
                # Checked: FOUND or SIMILAR AND verification confidence > 90%
                if (verification_status and 
                    verification_status in ["exactly_found", "paraphrase_or_similar"] and
                    source.get("verification_confidence") is not None and 
                    source.get("verification_confidence") > 0.9):
                    stats["checked"] += 1
    
    # Convert to sorted list
    source_stats_by_type = sorted(type_stats_map.values(), key=lambda x: x["type"])
    
    # Calculate totals
    total_stats = {
        "total": sum(s["total"] for s in source_stats_by_type),
        "slugRetrieved": sum(s["slugRetrieved"] for s in source_stats_by_type),
        "citationFound": sum(s["citationFound"] for s in source_stats_by_type),
        "checked": sum(s["checked"] for s in source_stats_by_type)
    }
    
    return source_stats_by_type, total_stats


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

    # Calculate and add statistics table
    source_stats_by_type, total_stats = _calculate_source_statistics(edited_transcript)
    
    # Statistics header style
    stats_header_style = ParagraphStyle(
        "StatsHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=HexColor("#1f2937"),
        spaceAfter=8,
        spaceBefore=0,
    )
    
    # Statistics table style
    stats_table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor("#f3f4f6")),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor("#374151")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor("#ffffff")),
        ('TEXTCOLOR', (0, 1), (-1, -1), HexColor("#374151")),
        ('FONTNAME', (0, 1), (-1, -1), default_font),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 1, HexColor("#e5e7eb")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ])
    
    # Add statistics section
    story.append(Paragraph("Source Statistics", stats_header_style))
    
    # Total statistics row
    total_row = [
        "Total",
        str(total_stats["total"]),
        str(total_stats["slugRetrieved"]),
        str(total_stats["citationFound"]),
        str(total_stats["checked"])
    ]
    
    # Statistics table data
    table_data = [
        ["Type", "Total", "Slug Retrieved", "Citation Found", "Checked"]
    ]
    
    # Add rows for each type
    for stats in source_stats_by_type:
        # Calculate percentages
        slug_pct_val = int((stats['slugRetrieved'] / stats['total']) * 100) if stats['total'] > 0 else 0
        citation_pct_val = int((stats['citationFound'] / stats['total']) * 100) if stats['total'] > 0 else 0
        checked_pct_val = int((stats['checked'] / stats['total']) * 100) if stats['total'] > 0 else 0
        
        slug_pct = f" ({slug_pct_val}%)" if stats['total'] > 0 else ""
        citation_pct = f" ({citation_pct_val}%)" if stats['total'] > 0 else ""
        checked_pct = f" ({checked_pct_val}%)" if stats['total'] > 0 else ""
        
        table_data.append([
            stats["type"],
            str(stats["total"]),
            str(stats["slugRetrieved"]) + slug_pct,
            str(stats["citationFound"]) + citation_pct,
            str(stats["checked"]) + checked_pct
        ])
    
    # Add total row at the end with percentages
    total_slug_pct_val = int((total_stats['slugRetrieved'] / total_stats['total']) * 100) if total_stats['total'] > 0 else 0
    total_citation_pct_val = int((total_stats['citationFound'] / total_stats['total']) * 100) if total_stats['total'] > 0 else 0
    total_checked_pct_val = int((total_stats['checked'] / total_stats['total']) * 100) if total_stats['total'] > 0 else 0
    
    total_slug_pct = f" ({total_slug_pct_val}%)" if total_stats['total'] > 0 else ""
    total_citation_pct = f" ({total_citation_pct_val}%)" if total_stats['total'] > 0 else ""
    total_checked_pct = f" ({total_checked_pct_val}%)" if total_stats['total'] > 0 else ""
    
    total_row = [
        "Total",
        str(total_stats["total"]),
        str(total_stats["slugRetrieved"]) + total_slug_pct,
        str(total_stats["citationFound"]) + total_citation_pct,
        str(total_stats["checked"]) + total_checked_pct
    ]
    table_data.append(total_row)
    
    # Create table
    stats_table = Table(table_data, colWidths=[3*cm, 2*cm, 2.5*cm, 2.5*cm, 2*cm])
    stats_table.setStyle(stats_table_style)
    
    # Apply bold to total row
    total_row_style = TableStyle([
        ('FONTNAME', (0, len(table_data)-1), (-1, len(table_data)-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, len(table_data)-1), (-1, len(table_data)-1), HexColor("#e0e7ff")),
    ])
    stats_table.setStyle(total_row_style)
    
    story.append(stats_table)
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
            verification_status = source.get("verification_status")
            verification_confidence = source.get("verification_confidence")
            
            if slug_retrieved is not None:
                status = "Yes" if slug_retrieved else "No"
                verification_parts.append(f"Slug retrieved: {status}")
            if verification_status is not None:
                # Format status: replace underscores with spaces and capitalize
                formatted_status = verification_status.replace("_", " ").title()
                verification_parts.append(f"Verification status: {formatted_status}")
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

    # Calculate and add statistics table
    source_stats_by_type, total_stats = _calculate_source_statistics(edited_transcript)
    
    # Statistics header style
    stats_header_style = ParagraphStyle(
        "StatsHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=HexColor("#1f2937"),
        spaceAfter=8,
        spaceBefore=0,
    )
    
    # Statistics table style
    stats_table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor("#f3f4f6")),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor("#374151")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor("#ffffff")),
        ('TEXTCOLOR', (0, 1), (-1, -1), HexColor("#374151")),
        ('FONTNAME', (0, 1), (-1, -1), default_font),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 1, HexColor("#e5e7eb")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ])
    
    # Add statistics section
    story.append(Paragraph("Source Statistics", stats_header_style))
    
    # Total statistics row
    total_row = [
        "Total",
        str(total_stats["total"]),
        str(total_stats["slugRetrieved"]),
        str(total_stats["citationFound"]),
        str(total_stats["checked"])
    ]
    
    # Statistics table data
    table_data = [
        ["Type", "Total", "Slug Retrieved", "Citation Found", "Checked"]
    ]
    
    # Add rows for each type
    for stats in source_stats_by_type:
        # Calculate percentages
        slug_pct_val = int((stats['slugRetrieved'] / stats['total']) * 100) if stats['total'] > 0 else 0
        citation_pct_val = int((stats['citationFound'] / stats['total']) * 100) if stats['total'] > 0 else 0
        checked_pct_val = int((stats['checked'] / stats['total']) * 100) if stats['total'] > 0 else 0
        
        slug_pct = f" ({slug_pct_val}%)" if stats['total'] > 0 else ""
        citation_pct = f" ({citation_pct_val}%)" if stats['total'] > 0 else ""
        checked_pct = f" ({checked_pct_val}%)" if stats['total'] > 0 else ""
        
        table_data.append([
            stats["type"],
            str(stats["total"]),
            str(stats["slugRetrieved"]) + slug_pct,
            str(stats["citationFound"]) + citation_pct,
            str(stats["checked"]) + checked_pct
        ])
    
    # Add total row at the end with percentages
    total_slug_pct_val = int((total_stats['slugRetrieved'] / total_stats['total']) * 100) if total_stats['total'] > 0 else 0
    total_citation_pct_val = int((total_stats['citationFound'] / total_stats['total']) * 100) if total_stats['total'] > 0 else 0
    total_checked_pct_val = int((total_stats['checked'] / total_stats['total']) * 100) if total_stats['total'] > 0 else 0
    
    total_slug_pct = f" ({total_slug_pct_val}%)" if total_stats['total'] > 0 else ""
    total_citation_pct = f" ({total_citation_pct_val}%)" if total_stats['total'] > 0 else ""
    total_checked_pct = f" ({total_checked_pct_val}%)" if total_stats['total'] > 0 else ""
    
    total_row = [
        "Total",
        str(total_stats["total"]),
        str(total_stats["slugRetrieved"]) + total_slug_pct,
        str(total_stats["citationFound"]) + total_citation_pct,
        str(total_stats["checked"]) + total_checked_pct
    ]
    table_data.append(total_row)
    
    # Create table
    stats_table = Table(table_data, colWidths=[3*cm, 2*cm, 2.5*cm, 2.5*cm, 2*cm])
    stats_table.setStyle(stats_table_style)
    
    # Apply bold to total row
    total_row_style = TableStyle([
        ('FONTNAME', (0, len(table_data)-1), (-1, len(table_data)-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, len(table_data)-1), (-1, len(table_data)-1), HexColor("#e0e7ff")),
    ])
    stats_table.setStyle(total_row_style)
    
    story.append(stats_table)
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
        if source.get("slug_retrieved") is not None or source.get("verification_status") is not None:
            story.append(Paragraph("<b>Verification Status:</b>", source_info_style))
            
            verification_lines = []
            if source.get("slug_retrieved") is not None:
                status = "Yes" if source.get("slug_retrieved") else "No"
                verification_lines.append(f"Slug Retrieved: {status}")
            verification_status = source.get("verification_status")
            if verification_status is not None:
                # Format status: replace underscores with spaces and capitalize
                formatted_status = verification_status.replace("_", " ").title()
                verification_lines.append(f"Verification Status: {formatted_status}")
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
