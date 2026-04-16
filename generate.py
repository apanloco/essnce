#!/usr/bin/env python3
"""
Generate index.html and essnce.pdf from essnce.md.

The .md file is the single source of truth. Edit it to add/change perfumes,
then run this script to regenerate the printable HTML and PDF.

Usage:  python3 generate.py
Requires: chromium (or google-chrome) in PATH.
"""

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
MD = HERE / "essnce.md"
HTML = HERE / "index.html"
PDF = HERE / "essnce.pdf"


def parse_markdown(text: str):
    """Return (intro_html, sections, notes_html).

    sections = [ {"title": str, "count": int, "upcoming": bool,
                  "columns": [str,...], "rows": [[str,...], ...]} ]
    """
    lines = text.splitlines()

    # Title = first H1
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "")

    # Intro: paragraphs between the H1 and the first H2
    intro_lines = []
    i = 0
    while i < len(lines) and not lines[i].startswith("# "):
        i += 1
    i += 1
    while i < len(lines) and not lines[i].startswith("## "):
        if lines[i].strip():
            intro_lines.append(lines[i])
        i += 1
    intro = " ".join(intro_lines).strip()

    # Split on H2 sections
    sections = []
    notes_html = ""
    current = None
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            heading = line[3:].strip()
            if heading.lower().startswith("anmärk"):
                # Notes section — capture as HTML list
                i += 1
                items = []
                while i < len(lines) and not lines[i].startswith("## "):
                    m = re.match(r"\s*-\s+(.*)", lines[i])
                    if m:
                        items.append(md_inline(m.group(1)))
                    i += 1
                notes_html = (
                    "<strong>Anmärkningar:</strong>\n<ul>\n"
                    + "\n".join(f"  <li>{it}</li>" for it in items)
                    + "\n</ul>"
                )
                continue
            current = {
                "raw_title": heading,
                "upcoming": "kommande" in heading.lower(),
                "columns": [],
                "rows": [],
            }
            sections.append(current)
            i += 1
            continue

        # Table parsing inside a section
        if current is not None and line.strip().startswith("|"):
            header_cells = split_row(line)
            i += 1
            # separator row
            if i < len(lines) and re.match(r"^\s*\|[\s\-|]+\|\s*$", lines[i]):
                i += 1
            current["columns"] = header_cells
            while i < len(lines) and lines[i].strip().startswith("|"):
                current["rows"].append(split_row(lines[i]))
                i += 1
            continue
        i += 1

    for s in sections:
        s["count"] = len(s["rows"])
        # Strip the "n st" counter from the title if present (we'll add it back)
        s["title"] = re.sub(r"\s*\(\d+\s*st\)\s*$", "", s["raw_title"])

    intro_html = md_inline(intro)
    return title, intro_html, sections, notes_html


def split_row(line: str):
    # Strip leading/trailing pipes and split
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def md_inline(s: str) -> str:
    """Minimal markdown inline: **bold**, *italic*, escape HTML."""
    # Escape HTML first
    s = html.escape(s)
    # Bold
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    # Italic
    s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", s)
    return s


def render_cell(text: str, col_class: str, is_name_col: bool) -> str:
    """Render one <td>. Apply .dash styling to ESSNCE Originals."""
    inner = md_inline(text)
    classes = [col_class] if col_class else []
    if not is_name_col and text.startswith("—"):
        classes.append("dash")
    class_attr = f' class="{" ".join(classes)}"' if classes else ""
    return f"<td{class_attr}>{inner}</td>"


def render_section(section) -> str:
    title = section["title"]
    count = section["count"]
    is_upcoming = section["upcoming"]
    columns = section["columns"]
    rows = section["rows"]
    ncols = len(columns)

    # Decide col widths based on column count (3 or 4)
    if ncols == 4:
        col_html = (
            '<col class="name"><col class="type">'
            '<col class="dupe" style="width:40%"><col class="price">'
        )
        # td column classes positionally
        col_classes = ["name", "type", "dupe", "price"]
    else:
        col_html = '<col class="name"><col class="dupe"><col class="price">'
        col_classes = ["name", "dupe", "price"]

    h2_class = ' class="upcoming"' if is_upcoming else ""
    count_suffix = f"under utveckling · {count} st" if is_upcoming else f"{count} st"

    thead = "<tr>" + "".join(f"<th>{md_inline(c)}</th>" for c in columns) + "</tr>"

    body_rows = []
    for row in rows:
        tds = []
        for idx, cell in enumerate(row):
            cls = col_classes[idx] if idx < len(col_classes) else ""
            tds.append(render_cell(cell, cls, idx == 0))
        body_rows.append("<tr>" + "".join(tds) + "</tr>")

    return (
        f'<h2{h2_class}>{html.escape(title)} '
        f'<span class="count">{count_suffix}</span></h2>\n'
        f"<table>\n<colgroup>{col_html}</colgroup>\n"
        f"<thead>{thead}</thead>\n<tbody>\n"
        + "\n".join(body_rows)
        + "\n</tbody>\n</table>"
    )


CSS = """
@page { size: A4; margin: 14mm 12mm; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 8.5pt;
  color: #111;
  line-height: 1.22;
}
h1 {
  font-size: 15pt;
  margin: 0 0 3px 0;
  letter-spacing: 1px;
}
h2 {
  font-size: 11pt;
  margin: 12px 0 4px 0;
  color: #222;
  letter-spacing: 1px;
  text-transform: uppercase;
  border-bottom: 0.6pt solid #333;
  padding-bottom: 2px;
}
h2.upcoming { color: #777; border-bottom-color: #aaa; }
.sub { font-size: 8pt; color: #555; margin: 0 0 8px 0; }
table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  margin-bottom: 4px;
}
col.name  { width: 27%; }
col.dupe  { width: 47%; }
col.price { width: 26%; }
col.type  { width: 8%; }
th, td {
  padding: 3px 5px;
  border-bottom: 0.4pt solid #ccc;
  vertical-align: top;
  word-wrap: break-word;
}
thead th {
  background: #f2f2f2;
  text-align: left;
  font-size: 8pt;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 0.8pt solid #333;
}
tbody tr:nth-child(even) { background: #fafafa; }
td.name { font-weight: 600; }
td.type { text-align: center; font-size: 7.5pt; color: #555; }
td.dash { color: #888; font-style: italic; }
td.price { text-align: left; white-space: nowrap; font-variant-numeric: tabular-nums; }
.count {
  font-size: 7.5pt;
  color: #888;
  font-weight: normal;
  letter-spacing: 0;
  text-transform: none;
  margin-left: 6px;
}
.notes {
  margin-top: 10px;
  font-size: 7.5pt;
  color: #444;
  border-top: 0.4pt solid #ccc;
  padding-top: 5px;
}
.notes ul { margin: 3px 0 0 14px; padding: 0; }
.notes li { margin-bottom: 1.5px; }
tr { page-break-inside: avoid; }
h2 { page-break-after: avoid; }
"""


def build_html(title, intro_html, sections, notes_html) -> str:
    sections_html = "\n\n".join(render_section(s) for s in sections)
    notes_block = f'<div class="notes">\n  {notes_html}\n</div>' if notes_html else ""
    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>

<h1>{html.escape(title).upper()}</h1>
<p class="sub">{intro_html}</p>

{sections_html}

{notes_block}

</body>
</html>
"""


def find_chromium() -> str | None:
    for exe in ("chromium", "google-chrome", "chrome"):
        path = shutil.which(exe)
        if path:
            return path
    return None


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    chrome = find_chromium()
    if not chrome:
        print("warning: chromium/google-chrome not found, skipping PDF", file=sys.stderr)
        return
    subprocess.run(
        [
            chrome, "--headless", "--disable-gpu", "--no-sandbox",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", str(html_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    if not MD.exists():
        sys.exit(f"error: {MD} not found")
    text = MD.read_text(encoding="utf-8")
    title, intro_html, sections, notes_html = parse_markdown(text)
    HTML.write_text(build_html(title, intro_html, sections, notes_html), encoding="utf-8")
    print(f"wrote {HTML.name}")
    render_pdf(HTML, PDF)
    if PDF.exists():
        print(f"wrote {PDF.name}")
    total = sum(s["count"] for s in sections)
    print(f"{len(sections)} sektioner, {total} parfymer totalt")


if __name__ == "__main__":
    main()
