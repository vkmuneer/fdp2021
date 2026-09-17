"""HTML-to-PDF rendering for downloadable reports.

Uses xhtml2pdf (pure Python, no system libraries like Cairo/Pango needed)
so it deploys the same way everywhere - Render, a shared VPS, etc. Report
pages are rendered with a small print-oriented template and converted here;
the same base64-embedded chart images used on screen also work inside the
generated PDF.
"""
from io import BytesIO

from flask import render_template
from xhtml2pdf import pisa


def render_pdf(template_name, **context):
    """Renders a template to a PDF file-like object (BytesIO, seeked to 0).
    Raises RuntimeError with xhtml2pdf's error log if generation fails."""
    html = render_template(template_name, **context)
    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer)
    if result.err:
        raise RuntimeError(f"PDF generation failed ({result.err} error(s))")
    buffer.seek(0)
    return buffer
