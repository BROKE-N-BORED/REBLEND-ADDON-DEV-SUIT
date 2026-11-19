#!/usr/bin/env python3
"""Render DOSSIER.md to a readable PDF with fpdf2.

Subset parser for the constructs used in the dossier:
H1/H2/H3, paragraphs (joined lines), bullet + numbered lists,
pipe tables, fenced code blocks, horizontal rules, inline
**bold**, *italic*, `code`.
"""
import re
import sys
from fpdf import FPDF

SRC = "/home/hatch/workspace/reblend-dev-suite/DOSSIER.md"
OUT = "/home/hatch/workspace/reblend-dev-suite/Reblend-Addon-Dev-Suite-Dossier.pdf"

ACCENT = (46, 90, 60)        # bench green, dark enough for print
DARK = (28, 28, 28)
GREY = (90, 90, 90)
RULE = (200, 200, 200)
CODE_BG = (245, 244, 240)
TABLE_HEAD_BG = (235, 233, 228)


def inline_to_fpdf(text):
    """Convert dossier inline markup to fpdf2's markdown subset.

    fpdf2 multi_cell(markdown=True) supports **bold**, __italics__,
    --underline--. We map *italic* -> __italic__ and strip `code`
    backticks (kept as plain text).
    """
    text = text.replace("`", "")
    # single-asterisk italics -> double-underscore (not touching **bold**)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"__\1__", text)
    return text


def strip_inline(text):
    """Remove all inline markup (for table cells)."""
    text = text.replace("`", "")
    text = text.replace("**", "")
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    return text


FONT_DIR = "/usr/share/fonts/truetype/liberation"


class DossierPDF(FPDF):
    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_font("LibSans", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 10, f"Reblend Add-on Dev Suite  |  Dossier v0.8  |  Page {self.page_no()}",
                 align="C")


def parse_blocks(lines):
    """Yield blocks: ('h1'|'h2'|'h3'|'para'|'ul'|'ol'|'table'|'code'|'hr', payload)."""
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            buf = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i].rstrip("\n"))
                i += 1
            i += 1  # closing fence
            blocks.append(("code", buf))
            continue
        if stripped == "---":
            blocks.append(("hr", None))
            i += 1
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            blocks.append((f"h{level}", m.group(2).strip()))
            i += 1
            continue
        if stripped.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            # drop the separator row (|---|---|)
            rows = [r for r in rows if not all(re.match(r"^:?-{2,}:?$", c) for c in r)]
            if rows:
                blocks.append(("table", rows))
            continue
        if re.match(r"^-\s+", stripped):
            items = []
            while i < n and re.match(r"^-\s+", lines[i].strip()):
                items.append(re.sub(r"^-\s+", "", lines[i].strip()))
                i += 1
            blocks.append(("ul", items))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            blocks.append(("ol", items))
            continue
        # paragraph: join consecutive plain lines
        buf = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith("#") or nxt.startswith("|")
                    or nxt.startswith("```") or nxt == "---"
                    or re.match(r"^-\s+", nxt) or re.match(r"^\d+\.\s+", nxt)):
                break
            buf.append(nxt)
            i += 1
        blocks.append(("para", " ".join(buf)))
    return blocks


def main():
    with open(SRC, encoding="utf-8") as f:
        lines = f.read().splitlines()
    blocks = parse_blocks(lines)

    pdf = DossierPDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("LibSans", "", f"{FONT_DIR}/LiberationSans-Regular.ttf")
    pdf.add_font("LibSans", "B", f"{FONT_DIR}/LiberationSans-Bold.ttf")
    pdf.add_font("LibSans", "I", f"{FONT_DIR}/LiberationSans-Italic.ttf")
    pdf.add_font("LibSans", "BI", f"{FONT_DIR}/LiberationSans-BoldItalic.ttf")
    pdf.add_font("LibMono", "", f"{FONT_DIR}/LiberationMono-Regular.ttf")
    pdf.add_font("LibMono", "B", f"{FONT_DIR}/LiberationMono-Bold.ttf")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 18, 20)
    pdf.set_title("Reblend Add-on Dev Suite — Project Dossier v0.8")
    pdf.set_author("Arlo, for Joshua Lofland")
    pdf.set_subject("Full-stack project dossier, on paper first")
    pdf.add_page()

    first_h1 = True
    for kind, payload in blocks:
        if kind == "h1":
            if not first_h1:
                pdf.add_page()
            first_h1 = False
            pdf.set_font("LibSans", "B", 24)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(0, 11, strip_inline(payload), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_draw_color(*ACCENT)
            pdf.set_line_width(0.8)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(5)
        elif kind == "h2":
            # keep heading with following content where possible
            if pdf.get_y() > 245:
                pdf.add_page()
            pdf.ln(4)
            pdf.set_font("LibSans", "B", 15)
            pdf.set_text_color(*ACCENT)
            pdf.multi_cell(0, 8, strip_inline(payload), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif kind == "h3":
            if pdf.get_y() > 255:
                pdf.add_page()
            pdf.ln(2)
            pdf.set_font("LibSans", "B", 12)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(0, 7, strip_inline(payload), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif kind == "para":
            pdf.set_font("LibSans", "", 10.5)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(0, 6, inline_to_fpdf(payload), markdown=True,
                           new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        elif kind == "ul":
            pdf.set_font("LibSans", "", 10.5)
            pdf.set_text_color(*DARK)
            for item in items_joined(payload):
                x = pdf.get_x()
                pdf.multi_cell(0, 6, "\u2022  " + inline_to_fpdf(item),
                               markdown=True, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)
            pdf.ln(1)
        elif kind == "ol":
            pdf.set_font("LibSans", "", 10.5)
            pdf.set_text_color(*DARK)
            for idx, item in enumerate(items_joined(payload), 1):
                pdf.multi_cell(0, 6, f"{idx}.  " + inline_to_fpdf(item),
                               markdown=True, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)
            pdf.ln(1)
        elif kind == "hr":
            pdf.ln(2)
            pdf.set_draw_color(*RULE)
            pdf.set_line_width(0.4)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(4)
        elif kind == "code":
            pdf.set_font("LibMono", "", 7.8)
            pdf.set_text_color(*DARK)
            pdf.set_fill_color(*CODE_BG)
            max_chars = 96
            for raw in payload:
                line = raw if raw else " "
                # hard-split overlong lines so nothing runs off the page
                while len(line) > max_chars:
                    pdf.multi_cell(0, 4.2, line[:max_chars], fill=True,
                                   new_x="LMARGIN", new_y="NEXT")
                    line = line[max_chars:]
                pdf.multi_cell(0, 4.2, line, fill=True,
                               new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
        elif kind == "table":
            render_table(pdf, payload)
            pdf.ln(3)

    pdf.output(OUT)
    print(f"Wrote {OUT} ({pdf.pages_count} pages)")


def items_joined(items):
    return items


def render_table(pdf, rows):
    header = rows[0]
    body = rows[1:]
    ncols = len(header)
    avail = pdf.w - pdf.l_margin - pdf.r_margin
    # width by longest cell, clamped so no column is starved or hogging
    lens = [1] * ncols
    for r in rows:
        for j, c in enumerate(r[:ncols]):
            lens[j] = max(lens[j], len(strip_inline(c)))
    weights = [min(max(l, 28), 90) for l in lens]
    total = sum(weights)
    col_widths = tuple(100 * w / total for w in weights)
    with pdf.table(col_widths=col_widths, line_height=5.2, text_align="LEFT",
                   borders_layout="ALL", cell_fill_color=TABLE_HEAD_BG,
                   cell_fill_mode="ROWS", first_row_as_headings=False) as table:
        hdr = table.row()
        pdf.set_font("LibSans", "B", 9)
        for cell in header:
            hdr.cell(strip_inline(cell))
        pdf.set_font("LibSans", "", 9)
        for r in body:
            row = table.row()
            for j in range(ncols):
                text = strip_inline(r[j]) if j < len(r) else ""
                row.cell(text)


if __name__ == "__main__":
    main()
