#!/usr/bin/env python3
"""Render the Markdown optimization report as a self-contained PDF."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from markdown_it import MarkdownIt
from PIL import Image
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration


REPORT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = REPORT_DIR / "README.md"
DEFAULT_OUTPUT = REPORT_DIR / "single_batch_optimization_timeline_report.pdf"

# The report only loads trusted, locally generated figures. Disable Pillow's
# generic large-image warning for the tall combined overview.
Image.MAX_IMAGE_PIXELS = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--font",
        type=Path,
        default=None,
        help="CJK-capable TTF/OTF/TTC font embedded in the PDF",
    )
    return parser.parse_args()


def resolve_font(explicit_font: Path | None) -> Path:
    candidates = [
        explicit_font,
        Path(os.environ["TRACE_REPORT_CJK_FONT"])
        if "TRACE_REPORT_CJK_FONT" in os.environ
        else None,
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise SystemExit(
        "No CJK font found. Pass --font /path/to/NotoSansCJKsc-Regular.otf "
        "or set TRACE_REPORT_CJK_FONT."
    )


def markdown_to_html(markdown_text: str) -> str:
    markdown_text = re.sub(
        r"<!-- pdf-build-instructions:start -->.*?"
        r"<!-- pdf-build-instructions:end -->",
        "",
        markdown_text,
        flags=re.DOTALL,
    )
    # A PDF has no collapsed interaction. Expose the overview image and use its
    # summary as an ordinary heading.
    markdown_text = re.sub(
        r"<details>\s*<summary>(.*?)</summary>",
        r"## \1",
        markdown_text,
        flags=re.DOTALL,
    ).replace("</details>", "")
    renderer = MarkdownIt("commonmark", {"html": True}).enable("table")
    body = renderer.render(markdown_text)
    body = re.sub(
        r"<h2>([ABCD]\. .*?)</h2>",
        r'<h2 class="panel-heading">\1</h2>',
        body,
    )
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<title>A–D 单 Batch 主要优化报告</title></head>"
        f"<body>{body}</body></html>"
    )


def stylesheet(font: Path, font_config: FontConfiguration) -> CSS:
    css = f"""
    @font-face {{
      font-family: ReportCJK;
      src: url('{font.as_uri()}');
      font-style: normal;
      font-weight: 400;
    }}
    @font-face {{
      font-family: ReportCJK;
      src: url('{font.as_uri()}');
      font-style: normal;
      font-weight: 700;
    }}
    @page {{
      size: A4;
      margin: 14mm 13mm 17mm 13mm;
      @bottom-center {{
        content: "Optimization trace report  ·  " counter(page) " / " counter(pages);
        font-family: ReportCJK, sans-serif;
        font-size: 8pt;
        color: #64748b;
      }}
    }}
    html {{ font-family: ReportCJK, sans-serif; color: #17202a; }}
    body {{ font-size: 9.4pt; line-height: 1.48; }}
    h1 {{ font-size: 22pt; line-height: 1.2; margin: 0 0 8mm; color: #111827; }}
    h2 {{ font-size: 16pt; line-height: 1.25; margin: 8mm 0 4mm; color: #0f2942; }}
    h3 {{ font-size: 12.5pt; line-height: 1.3; margin: 6mm 0 3mm; color: #173b5e; }}
    h2.panel-heading {{ break-before: page; }}
    p {{ margin: 0 0 3mm; }}
    ul, ol {{ margin: 2mm 0 4mm 6mm; padding-left: 5mm; }}
    li {{ margin: 0 0 1.2mm; }}
    blockquote {{
      margin: 4mm 0 6mm;
      padding: 3.5mm 5mm;
      border-left: 1.2mm solid #3b82f6;
      background: #f3f7fb;
      color: #334155;
    }}
    blockquote p:last-child {{ margin-bottom: 0; }}
    img {{
      display: block;
      width: 100%;
      height: auto;
      max-height: 122mm;
      object-fit: contain;
      margin: 4mm auto 5mm;
      break-inside: avoid;
    }}
    img[src$='single_batch_optimization_timeline.png'] {{
      width: auto;
      max-width: 100%;
      max-height: 235mm;
    }}
    a {{ color: #075c9c; text-decoration: none; }}
    code {{
      font-family: 'DejaVu Sans Mono', monospace;
      font-size: 0.90em;
      background: #eef2f6;
      padding: 0.2mm 0.7mm;
      border-radius: 0.7mm;
    }}
    pre {{
      font-family: 'DejaVu Sans Mono', ReportCJK, monospace;
      font-size: 7.1pt;
      line-height: 1.28;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      margin: 3mm 0 5mm;
      padding: 3.5mm;
      border: 0.3mm solid #cbd5e1;
      background: #f8fafc;
      break-inside: avoid;
    }}
    pre strong {{ color: #b42318; font-weight: 800; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 3mm 0 5mm;
      font-size: 8.5pt;
      break-inside: avoid;
    }}
    th, td {{ border: 0.25mm solid #cbd5e1; padding: 1.8mm 2.2mm; vertical-align: top; }}
    th {{ background: #eaf0f6; font-weight: 700; }}
    hr {{ border: 0; border-top: 0.3mm solid #cbd5e1; margin: 6mm 0; }}
    """
    return CSS(string=css, font_config=font_config)


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    font_path = resolve_font(args.font)
    html = markdown_to_html(input_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_config = FontConfiguration()
    HTML(string=html, base_url=str(input_path.parent)).write_pdf(
        output_path,
        stylesheets=[stylesheet(font_path, font_config)],
        presentational_hints=True,
        font_config=font_config,
    )
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
