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
    """Minimal markdown inline: [link](url), **bold**, *italic*, escape HTML."""
    # Escape HTML first
    s = html.escape(s)
    # Links: [text](url)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
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

    if is_upcoming:
        slug = "kommande"
    else:
        slug = section["raw_title"].lower().split()[0]

    return (
        f'<section data-category="{slug}">\n'
        f'<h2{h2_class}>{html.escape(title)} '
        f'<span class="count">{count_suffix}</span></h2>\n'
        f"<table>\n<colgroup>{col_html}</colgroup>\n"
        f"<thead>{thead}</thead>\n<tbody>\n"
        + "\n".join(body_rows)
        + "\n</tbody>\n</table>\n</section>"
    )


CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }

/* --- Screen defaults (mobile-first) --- */
body {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  color: #111;
  line-height: 1.4;
  font-size: 16px;
  padding: 14px;
  max-width: 960px;
  margin: 0 auto;
}
h1 {
  font-size: 22px;
  margin: 0 0 6px 0;
  letter-spacing: 1px;
}
h2 {
  font-size: 16px;
  margin: 22px 0 8px 0;
  color: #222;
  letter-spacing: 1px;
  text-transform: uppercase;
  border-bottom: 1px solid #333;
  padding-bottom: 4px;
}
h2.upcoming { color: #777; border-bottom-color: #aaa; }
.sub { font-size: 14px; color: #555; margin: 0 0 14px 0; }
table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 12px;
}
th, td {
  padding: 8px 10px;
  border-bottom: 1px solid #ddd;
  vertical-align: top;
  text-align: left;
  word-wrap: break-word;
}
thead th {
  background: #f2f2f2;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 2px solid #333;
}
tbody tr:nth-child(even) { background: #fafafa; }
td.name { font-weight: 600; }
a { color: inherit; text-decoration: none; border-bottom: 0.3pt dotted #aaa; }
td.type { text-align: center; font-size: 13px; color: #555; }
td.dash { color: #888; font-style: italic; }
td.price { white-space: nowrap; font-variant-numeric: tabular-nums; }
.count {
  font-size: 12px;
  color: #888;
  font-weight: normal;
  letter-spacing: 0;
  text-transform: none;
  margin-left: 6px;
}
.notes {
  margin-top: 20px;
  font-size: 13px;
  color: #444;
  border-top: 1px solid #ccc;
  padding-top: 8px;
}
.notes ul { margin: 6px 0 0 18px; padding: 0; }
.notes li { margin-bottom: 3px; }

.pdf-link {
  display: inline-block;
  margin: 0 0 14px 0;
  padding: 7px 12px;
  font-size: 13px;
  color: #222;
  background: #f2f2f2;
  border: 1px solid #bbb;
  border-radius: 4px;
  text-decoration: none;
  letter-spacing: 0.3px;
}
.pdf-link:hover { background: #e8e8e8; }

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin: 0 0 16px 0;
  padding: 10px 12px;
  background: #f7f7f7;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 14px;
}
.filter-bar label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
}
.filter-bar input { cursor: pointer; }

/* --- Narrow screens: kort-layout istället för tabell --- */
@media (max-width: 600px) {
  body { padding: 12px 10px; font-size: 15px; }
  h1 { font-size: 19px; }
  h2 { font-size: 14px; margin: 18px 0 6px 0; }
  .sub { font-size: 13px; }

  table, tbody, tr { display: block; width: 100%; }
  colgroup, thead { display: none; }

  tbody tr {
    padding: 10px 2px;
    border-bottom: 1px solid #ddd;
    background: transparent !important;
    display: grid;
    grid-template-columns: 1fr auto;
    column-gap: 10px;
    row-gap: 2px;
  }
  td {
    padding: 0;
    border: none;
    text-align: left;
  }
  td.name {
    grid-column: 1;
    grid-row: 1;
    font-size: 16px;
    font-weight: 600;
  }
  td.price {
    grid-column: 2;
    grid-row: 1;
    text-align: right;
    color: #555;
    font-size: 14px;
  }
  td.dupe {
    grid-column: 1 / -1;
    grid-row: 2;
    color: #555;
    font-size: 14px;
  }
  td.type {
    grid-column: 1 / -1;
    grid-row: 3;
    text-align: left;
    font-size: 12px;
    color: #888;
  }
}

/* --- Print / PDF: behåll A4-layouten --- */
@media print {
  .pdf-link { display: none; }
  .filter-bar { display: none !important; }
  section[data-category] { display: block !important; }
  @page { size: A4; margin: 14mm 12mm; }
  body {
    font-size: 8.5pt;
    line-height: 1.22;
    padding: 0;
    max-width: none;
    margin: 0;
  }
  h1 { font-size: 15pt; margin: 0 0 3px 0; }
  h2 {
    font-size: 11pt;
    margin: 12px 0 4px 0;
    border-bottom: 0.6pt solid #333;
    padding-bottom: 2px;
  }
  .sub { font-size: 8pt; margin: 0 0 8px 0; }
  table { table-layout: fixed; margin-bottom: 4px; }
  col.name  { width: 27%; }
  col.dupe  { width: 47%; }
  col.price { width: 26%; }
  col.type  { width: 8%; }
  th, td {
    padding: 3px 5px;
    border-bottom: 0.4pt solid #ccc;
  }
  thead th {
    font-size: 8pt;
    border-bottom: 0.8pt solid #333;
  }
  td.type { font-size: 7.5pt; }
  .count { font-size: 7.5pt; }
  .notes {
    margin-top: 10px;
    font-size: 7.5pt;
    border-top: 0.4pt solid #ccc;
    padding-top: 5px;
  }
  .notes ul { margin: 3px 0 0 14px; }
  .notes li { margin-bottom: 1.5px; }
  tr { page-break-inside: avoid; }
  h2 { page-break-after: avoid; }
}
"""


def build_html(title, intro_html, sections, notes_html) -> str:
    sections_html = "\n\n".join(render_section(s) for s in sections)
    notes_block = f'<div class="notes">\n  {notes_html}\n</div>' if notes_html else ""
    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>

<h1>{html.escape(title).upper()}</h1>
<p class="sub">{intro_html}</p>
<a class="pdf-link" href="{PDF.name}" download>Ladda ner som PDF</a>

<div class="filter-bar" role="group" aria-label="Visa sektioner">
  <label><input type="checkbox" data-filter="dam" checked> Dam</label>
  <label><input type="checkbox" data-filter="unisex" checked> Unisex</label>
  <label><input type="checkbox" data-filter="herr" checked> Herr</label>
  <label><input type="checkbox" data-filter="kommande" checked> Kommande</label>
</div>

{sections_html}

{notes_block}

<script>
document.querySelectorAll('.filter-bar input[data-filter]').forEach(cb => {{
  cb.addEventListener('change', () => {{
    const cat = cb.dataset.filter;
    document.querySelectorAll('section[data-category="' + cat + '"]').forEach(sec => {{
      sec.style.display = cb.checked ? '' : 'none';
    }});
  }});
}});
</script>

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
