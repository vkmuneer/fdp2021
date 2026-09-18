"""HTML-to-PDF rendering for downloadable reports.

Uses xhtml2pdf (pure Python, no system libraries like Cairo/Pango needed)
so it deploys the same way everywhere - Render, a shared VPS, etc. Report
pages are rendered with a small print-oriented template and converted here;
the same base64-embedded chart images used on screen also work inside the
generated PDF.
"""
import base64
import os
from io import BytesIO

from flask import render_template, current_app
from xhtml2pdf import pisa

_logo_data_uri_cache = None


def logo_data_uri():
    """Base64 data URI of the academy logo, for embedding in PDF headers.
    xhtml2pdf can't resolve relative/static URLs reliably, and doesn't
    render SVG, so this reads the raster PNG once and caches the result."""
    global _logo_data_uri_cache
    if _logo_data_uri_cache is None:
        path = os.path.join(current_app.static_folder, "img", "logo.png")
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        _logo_data_uri_cache = f"data:image/png;base64,{encoded}"
    return _logo_data_uri_cache


def render_pdf(template_name, **context):
    """Renders a template to a PDF file-like object (BytesIO, seeked to 0).
    Raises RuntimeError with xhtml2pdf's error log if generation fails."""
    context.setdefault("logo_data_uri", logo_data_uri())
    html = render_template(template_name, **context)
    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer)
    if result.err:
        raise RuntimeError(f"PDF generation failed ({result.err} error(s))")
    buffer.seek(0)
    return buffer
