"""Reusable HTML + plain-text rendering for parking-monitor emails.

An email is a list of typed nodes -- headings, paragraphs, a prominent status
panel, signpost "findings", dividers. ``render_html`` turns that into a polished,
email-safe HTML document (semantic tags + inline CSS, constrained width, no
images, no JavaScript). ``render_text`` produces the plain-text fallback from the
*same* nodes, so the two never drift.

The compose layer (``app/monitor/compose.py``) builds the node list. Nothing here
or there relies on Markdown for formatting.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field


@dataclass
class H1:
    text: str


@dataclass
class H2:
    text: str


@dataclass
class P:
    text: str
    strong: bool = False
    muted: bool = False
    small: bool = False


@dataclass
class Rule:
    """A horizontal divider."""


@dataclass
class Panel:
    """A prominent status box. ``rows`` are (label, value) pairs; value is bold."""

    rows: list[tuple[str, str]]
    tone: str = "neutral"  # neutral | ok | warn | bad


@dataclass
class Finding:
    """A signpost line: emoji + bold title, then explanatory text and an optional
    de-emphasised caveat below it."""

    emoji: str
    title: str
    text: str = ""
    caveat: str = ""


@dataclass
class Lines:
    """A tight block of short lines (e.g. an alternative's location / walk / distance)."""

    items: list[str]


@dataclass
class Actions:
    """Management links. Rendered as real <a> in HTML, ``label: url`` in text."""

    items: list[tuple[str, str]]  # (label, url)


Node = H1 | H2 | P | Rule | Panel | Finding | Lines | Actions


@dataclass
class EmailDoc:
    title: str
    preheader: str
    nodes: list[Node] = field(default_factory=list)


_FONT = (
    '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,'
    '"Apple Color Emoji","Segoe UI Emoji",sans-serif'
)
_TONE_BG = {"neutral": "#f4f6f8", "ok": "#edf7ed", "warn": "#fff5e6", "bad": "#fdecea"}
_TONE_BAR = {"neutral": "#8a94a6", "ok": "#2e7d32", "warn": "#b26a00", "bad": "#c62828"}


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _esc_attr(s: str) -> str:
    return html.escape(s or "", quote=True)


def render_html(doc: EmailDoc) -> str:
    body: list[str] = []
    for n in doc.nodes:
        if isinstance(n, H1):
            body.append(
                f'<h1 style="font-size:26px;line-height:1.25;margin:0 0 16px;'
                f'color:#1a1a1a;font-weight:700;">{_esc(n.text)}</h1>'
            )
        elif isinstance(n, H2):
            body.append(
                f'<h2 style="font-size:18px;line-height:1.3;margin:26px 0 10px;'
                f'color:#1a1a1a;font-weight:600;">{_esc(n.text)}</h2>'
            )
        elif isinstance(n, P):
            size = 13 if n.small else 16
            color = "#6b7280" if n.muted else "#333333"
            weight = 700 if n.strong else 400
            body.append(
                f'<p style="font-size:{size}px;line-height:1.55;margin:0 0 12px;'
                f'color:{color};font-weight:{weight};">{_esc(n.text)}</p>'
            )
        elif isinstance(n, Rule):
            body.append(
                '<hr style="border:0;border-top:1px solid #e2e5ea;margin:22px 0;">'
            )
        elif isinstance(n, Panel):
            cells = "".join(
                f'<tr><td style="padding:2px 0;font-size:12px;color:#6b7280;'
                f'text-transform:uppercase;letter-spacing:.04em;">{_esc(lbl)}</td></tr>'
                f'<tr><td style="padding:0 0 6px;font-size:20px;font-weight:700;'
                f'color:#1a1a1a;">{_esc(val)}</td></tr>'
                for lbl, val in n.rows
            )
            body.append(
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                f'style="background:{_TONE_BG.get(n.tone, _TONE_BG["neutral"])};'
                f'border-left:4px solid {_TONE_BAR.get(n.tone, _TONE_BAR["neutral"])};'
                'border-radius:4px;margin:0 0 16px;"><tr><td style="padding:14px 16px;">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
                f'{cells}</table></td></tr></table>'
            )
        elif isinstance(n, Finding):
            caveat = (
                f'<span style="display:block;font-size:13px;color:#6b7280;margin-top:4px;">'
                f"{_esc(n.caveat)}</span>"
                if n.caveat
                else ""
            )
            tail = f" {_esc(n.text)}" if n.text else ""
            body.append(
                '<p style="font-size:15px;line-height:1.55;margin:0 0 12px;color:#333333;">'
                f"<strong>{_esc(n.emoji)} {_esc(n.title)}</strong>{tail}{caveat}</p>"
            )
        elif isinstance(n, Lines):
            spans = "".join(
                '<span style="display:block;font-size:15px;line-height:1.5;color:#333333;">'
                f"{_esc(it)}</span>"
                for it in n.items
            )
            body.append(f'<p style="margin:0 0 12px;">{spans}</p>')
        elif isinstance(n, Actions):
            links = "".join(
                f'<a href="{_esc_attr(url)}" style="color:#0b63c5;text-decoration:underline;'
                f'font-size:13px;margin-right:16px;display:inline-block;">{_esc(label)}</a>'
                for label, url in n.items
            )
            body.append(f'<p style="margin:6px 0 0;">{links}</p>')

    inner = "\n".join(body)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_esc(doc.title)}</title></head>"
        '<body style="margin:0;padding:0;background:#eef0f3;">'
        '<span style="display:none!important;visibility:hidden;opacity:0;height:0;width:0;'
        f'overflow:hidden;">{_esc(doc.preheader)}</span>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#eef0f3;padding:24px 12px;"><tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background:#ffffff;border-radius:8px;'
        f'padding:28px 28px 20px;font-family:{_FONT};">'
        f"<tr><td>{inner}</td></tr></table></td></tr></table></body></html>"
    )


_TEXT_RULE = "─" * 32


def render_text(doc: EmailDoc) -> str:
    out: list[str] = []
    for n in doc.nodes:
        if isinstance(n, H1):
            out += [n.text, ""]
        elif isinstance(n, H2):
            out += ["", n.text, ""]
        elif isinstance(n, P):
            out += [n.text, ""]
        elif isinstance(n, Rule):
            out += [_TEXT_RULE, ""]
        elif isinstance(n, Panel):
            for lbl, val in n.rows:
                out.append(f"{lbl.upper()}: {val}")
            out.append("")
        elif isinstance(n, Finding):
            line = f"{n.emoji} {n.title}"
            if n.text:
                line += f" - {n.text}"
            out.append(line)
            if n.caveat:
                out.append(f"   {n.caveat}")
            out.append("")
        elif isinstance(n, Lines):
            out += [*n.items, ""]
        elif isinstance(n, Actions):
            for label, url in n.items:
                out.append(f"{label}: {url}")
            out.append("")

    text = "\n".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip() + "\n"
