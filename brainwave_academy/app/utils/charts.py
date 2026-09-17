"""Server-side chart rendering for exam analysis reports.

Charts are rendered to a base64 PNG so the same <img> tag works both for the
on-screen analysis page and the downloadable PDF (xhtml2pdf renders base64
data-URI images fine, unlike live JS charting libraries).
"""
import base64
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BRAND_TEAL = "#36b6a8"
BRAND_BLUE = "#1c3f63"
PALETTE = [BRAND_TEAL, BRAND_BLUE, "#d97706", "#dc2626", "#6b7280", "#9333ea"]


def _fig_to_data_uri(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=140)
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def bar_chart(labels, values, title, ylabel="Average Marks (%)"):
    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    ax.bar(labels, values, color=BRAND_TEAL)
    ax.set_title(title, color=BRAND_BLUE, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(0, max(values + [10]) * 1.15)
    for i, v in enumerate(values):
        ax.text(i, v + 0.5, f"{v:.0f}", ha="center", fontsize=8)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def pie_chart(labels, values, title):
    fig, ax = plt.subplots(figsize=(4.2, 4.2))
    non_zero = [(lbl, v) for lbl, v in zip(labels, values) if v > 0]
    if not non_zero:
        non_zero = [("No data", 1)]
    lbls, vals = zip(*non_zero)
    ax.pie(vals, labels=lbls, autopct="%1.0f%%", colors=PALETTE[: len(lbls)], startangle=90)
    ax.set_title(title, color=BRAND_BLUE, fontweight="bold")
    fig.tight_layout()
    return _fig_to_data_uri(fig)
