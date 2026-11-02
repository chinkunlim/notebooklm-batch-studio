"""Build the standalone demo page docs/demo/index.html (for GitHub Pages) from the real web UI.

Takes src/notebooklm_batch_studio/entrypoints/static/index.html, inlines every stylesheet and script,
adds the mock API and fictional BIO101 / CHEM110 content from scripts/demo/, and embeds generated
lecture PDFs and a short sample audio track, so the page works on its own with no server.
Icons, fonts and pdf.js load from public CDNs (the page is meant to be viewed online).

Usage:
    uv run python scripts/build_demo.py
"""

from __future__ import annotations

import base64
import io
import logging
import math
import re
import struct
import wave
from pathlib import Path

from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/notebooklm_batch_studio/entrypoints/static"
DEMO = ROOT / "scripts/demo"
OUT = ROOT / "docs/demo/index.html"
PDFJS = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38"
CDN_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700'
    '&family=Noto+Serif+TC:wght@500;700&display=swap" rel="stylesheet">\n'
    '  <link rel="stylesheet" href="https://unpkg.com/lucide-static@0.460.0/font/lucide.css">'
)
FILLER = [
    "Read the key terms first, then connect each one to an example you already know.",
    "Draw the process as a diagram and label every step in your own words.",
    "Ask yourself why each step is needed and what would fail without it.",
    "Compare this idea with the previous lecture and note one difference.",
    "Write two exam-style questions about this page before moving on.",
]


def lecture_pages(lecture: dict[str, object]) -> dict[int, list[str]]:
    """Sentences for pages 2 and 3 of a lecture PDF: its key-point quotes on their pages, plus study tips.

    Args:
        lecture: Lecture with "points" / "laterPoints" lists of {quote, page}.

    Returns:
        Page number to list of sentences.
    """
    pages: dict[int, list[str]] = {2: [], 3: []}
    for point in [*lecture.get("points", []), *lecture.get("laterPoints", [])]:  # type: ignore[misc]
        pages[min(3, max(2, int(point["page"])))].append(point["quote"] + ".")
    for i, line in enumerate(FILLER):
        pages[2 + i % 2].append(line)
    return pages


def make_pdf(course_code: str, number: int, lecture: dict[str, object]) -> bytes:
    """A three-page lecture PDF: a title page and two pages of text containing the key-point quotes.

    Args:
        course_code: Course code shown on the title page.
        number: Lecture number.
        lecture: Lecture with "title" and key points.

    Returns:
        PDF bytes.
    """
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=landscape(letter))
    width, height = landscape(letter)
    pdf.setFont("Helvetica", 14)
    pdf.drawString(60, height - 80, f"{course_code}  ·  Lecture {number}")
    pdf.setFont("Helvetica-Bold", 34)
    pdf.drawString(60, height / 2, str(lecture["title"]))
    pdf.setFont("Helvetica", 14)
    pdf.drawString(60, height / 2 - 40, "Fictional lecture notes for the Gemini Notebook study studio demo")
    pdf.showPage()
    for page, lines in lecture_pages(lecture).items():
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawString(60, height - 80, f"{lecture['title']} ({page - 1}/2)")
        pdf.setFont("Helvetica", 15)
        y = height - 140
        for line in lines:
            pdf.drawString(70, y, "•  " + line)
            y -= 36
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def make_audio(seconds: int = 45, rate: int = 8000) -> bytes:
    """A soft, slowly breathing chord as an 8-bit mono WAV (stands in for an audio overview).

    Args:
        seconds: Length in seconds.
        rate: Sample rate in Hz.

    Returns:
        WAV bytes.
    """
    frames = bytearray()
    for i in range(seconds * rate):
        t = i / rate
        swell = 0.55 + 0.45 * math.sin(2 * math.pi * t / 6)
        fade = min(1.0, t / 2, (seconds - t) / 2)
        value = sum(math.sin(2 * math.pi * f * t) for f in (220.0, 277.18, 329.63)) / 3
        frames += struct.pack("B", int(128 + 40 * swell * fade * value))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(1)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames))
    return buf.getvalue()


def parse_courses() -> list[dict[str, object]]:
    """Read course codes, lecture titles and key points from scripts/demo/demo-data.js.

    Returns:
        Courses with "code" and "lectures" (each with "title", "points", "laterPoints").
    """
    text = (DEMO / "demo-data.js").read_text(encoding="utf-8")
    courses: list[dict[str, object]] = []
    for block in re.split(r"\n  \{\n    code: ", text)[1:]:
        code = re.match(r"'([^']+)'", block).group(1)  # type: ignore[union-attr]
        lectures = []
        for lec in re.split(r"\n      \{ ?\n? *topic: ", block)[1:]:
            title = re.search(r"title: '([^']+)'", lec).group(1)  # type: ignore[union-attr]
            points = [
                {"quote": q, "page": int(p)} for q, p in re.findall(r"quote: '([^']+)', page: (\d)", lec)
            ]
            lectures.append({"title": title, "points": points})
        courses.append({"code": code, "lectures": lectures})
    return courses


def script(code: str, module: bool = False) -> str:
    """An inline <script> element (a closing tag inside the code is escaped).

    Args:
        code: JavaScript source.
        module: True for a module script.

    Returns:
        HTML.
    """
    kind = ' type="module"' if module else ""
    safe = code.replace("</script", "<\\/script")
    return f"<script{kind}>\n{safe}\n</script>"


def assets_js() -> str:
    """JavaScript that defines the embedded lecture PDFs and the sample audio track.

    Returns:
        JavaScript source.
    """
    pdfs: dict[str, dict[int, str]] = {}
    for course in parse_courses():
        for i, lecture in enumerate(course["lectures"], start=1):  # type: ignore[arg-type]
            pdf = make_pdf(str(course["code"]), i, lecture)
            pdfs.setdefault(str(course["code"]), {})[i] = base64.b64encode(pdf).decode()
    audio = base64.b64encode(make_audio()).decode()
    entries = ",".join(
        f"{code!r}:{{" + ",".join(f"{n}:'{b}'" for n, b in lectures.items()) + "}"
        for code, lectures in pdfs.items()
    )
    return (
        "/* Embedded files for the demo: generated lecture PDFs and a sample audio track. */\n"
        f"const DEMO_PDFS = {{{entries}}};\n"
        f"const DEMO_AUDIO = 'data:audio/wav;base64,{audio}';"
    )


def build() -> Path:
    """Assemble docs/demo/index.html.

    Returns:
        Path of the written file.
    """
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'\s*<link rel="(manifest|icon|apple-touch-icon)"[^>]*>', "", html)
    html = re.sub(
        r'<!-- Icons and fonts are bundled.*?noto-serif-tc\.css">',
        CDN_LINKS,
        html,
        flags=re.S,
    )
    styles = "".join(
        (STATIC / name).read_text(encoding="utf-8")
        for name in ("studio-theme.css", "studio.css", "studio-learning.css", "vendor/pdfjs/text_layer.css")
    )
    html = re.sub(r'\s*<link rel="stylesheet" href="/static/[^"]+">', "", html)
    html = html.replace("</head>", f"<style>\n{styles}\n</style>\n</head>", 1)
    title = "<title>Gemini Notebook 學習工作室</title>"
    html = html.replace(title, title.replace("工作室<", "工作室（示範）<"))

    def inline(match: re.Match[str]) -> str:
        """Replace one <script src> with its inline code (the demo layers go around the app's scripts).

        Args:
            match: The script tag match.

        Returns:
            Inline script HTML.
        """
        name = match.group(2)
        code = (STATIC / name).read_text(encoding="utf-8")
        if match.group(1):  # the reader module: pdf.js from the CDN, PDFs from the page
            code = code.replace("/static/vendor/pdfjs/pdf.min.mjs", f"{PDFJS}/build/pdf.min.mjs")
            worker = "/static/vendor/pdfjs/pdf.worker.min.mjs"
            code = code.replace(worker, f"{PDFJS}/build/pdf.worker.min.mjs")
            code = re.sub(r"const pdfUrl = `[^`]+`;", "const pdfUrl = demoPdf(code, no);", code)
            return script(code, module=True)
        out = script(code)
        if name == "studio-core.js":
            demo = [
                (DEMO / "demo-data.js").read_text(encoding="utf-8"),
                assets_js(),
                (DEMO / "demo-mock.js").read_text(encoding="utf-8"),
            ]
            out = "\n".join(script(part) for part in demo) + "\n" + out
        if name == "studio-start.js":
            out += "\n" + script((DEMO / "demo-overrides.js").read_text(encoding="utf-8"))
        return out

    html = re.sub(r'<script( type="module")? src="/static/([^"]+)"></script>', inline, html)
    badge = (
        '<div class="demo-badge" role="note">示範版　課程與進度都是虛構的，操作只存在這個瀏覽器</div>\n'
        "<style>.demo-badge{position:fixed;bottom:12px;right:16px;z-index:5000;"
        "background:var(--ink);color:var(--canvas);font-size:12px;padding:4px 14px;border-radius:999px;"
        "opacity:.85;pointer-events:none;white-space:nowrap}</style>\n"
    )
    html = html.replace("<body>", "<body>\n" + badge, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    logger.info("Wrote %s (%d KB)", OUT, OUT.stat().st_size // 1024)
    return OUT


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = build()
    print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB")
