from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "Guide_Utilisateur.md"
DOCX_PATH = ROOT / "Guide_Utilisateur.docx"


def add_field(paragraph, field_code: str) -> None:
    fld_simple = OxmlElement("w:fldSimple")
    fld_simple.set(qn("w:instr"), field_code)
    paragraph._p.append(fld_simple)


def add_page_number(paragraph) -> None:
    run = paragraph.add_run("Page ")
    run.font.size = Pt(9)
    add_field(paragraph, "PAGE")
    run2 = paragraph.add_run(" / ")
    run2.font.size = Pt(9)
    add_field(paragraph, "NUMPAGES")


def set_uniform_page_layout(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    header_run = header.add_run("NutriFAQ-Chat")
    header_run.font.size = Pt(9)
    header_run.font.color.rgb = RGBColor(90, 90, 90)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    add_page_number(footer)


def configure_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    for name, size in [("Heading 1", 18), ("Heading 2", 15), ("Heading 3", 13)]:
        style = document.styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)


def add_cover(document: Document) -> None:
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("NutriFAQ-Chat")
    run.bold = True
    run.font.size = Pt(30)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("Guide de l'utilisateur")
    run.font.size = Pt(20)
    run.bold = True

    document.add_paragraph("")
    meta_table = document.add_table(rows=4, cols=2)
    meta_table.style = "Table Grid"
    meta_table.cell(0, 0).text = "Version du document"
    meta_table.cell(0, 1).text = "1.0"
    meta_table.cell(1, 0).text = "Date de génération"
    meta_table.cell(1, 1).text = datetime.now().strftime("%Y-%m-%d")
    meta_table.cell(2, 0).text = "Application"
    meta_table.cell(2, 1).text = "NutriFAQ-Chat"
    meta_table.cell(3, 0).text = "Entreprise"
    meta_table.cell(3, 1).text = "IMX Technologie inc."

    document.add_page_break()


def add_toc(document: Document) -> None:
    h = document.add_paragraph("Table des matières", style="Heading 1")
    h.runs[0].bold = True
    p = document.add_paragraph()
    add_field(p, r'TOC \o "1-3" \h \z \u')
    document.add_page_break()


def add_callout(document: Document, text: str) -> None:
    table = document.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.cell(0, 0)
    p = cell.paragraphs[0]
    r = p.add_run(text)
    r.italic = True
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), "F2F2F2")
    tc_pr.append(shading)


def render_markdown(document: Document, content: str) -> None:
    bullet_re = re.compile(r"^\s*-\s+(.*)$")
    number_re = re.compile(r"^\s*\d+\.\s+(.*)$")
    heading_re = re.compile(r"^(#{1,3})\s+(.*)$")

    for raw in content.splitlines():
        line = raw.rstrip()
        if not line or line == "---":
            document.add_paragraph("")
            continue

        h = heading_re.match(line)
        if h:
            level = len(h.group(1))
            text = h.group(2).strip()
            document.add_paragraph(text, style=f"Heading {level}")
            continue

        if line.startswith("> [Capture d'écran à insérer"):
            add_callout(document, line.replace("> ", "", 1))
            continue

        b = bullet_re.match(line)
        if b:
            document.add_paragraph(b.group(1).strip(), style="List Bullet")
            continue

        n = number_re.match(line)
        if n:
            document.add_paragraph(n.group(1).strip(), style="List Number")
            continue

        # Inline bold markers as plain text cleanup for readability in Word.
        cleaned = line.replace("**", "")
        document.add_paragraph(cleaned)


def add_roles_table(document: Document) -> None:
    document.add_paragraph("Tableau de référence — rôles applicatifs", style="Heading 3")
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = "Rôle"
    table.cell(0, 1).text = "Accès principal"
    rows = [
        ("Collaborateur", "Utilisation opérationnelle (consultation, validation, interactions)."),
        ("Admin", "Accès complet incluant indexation, publication, journal de logs et gestion des utilisateurs."),
    ]
    for role, access in rows:
        row = table.add_row().cells
        row[0].text = role
        row[1].text = access


def main() -> None:
    if not MD_PATH.exists():
        raise FileNotFoundError(f"Markdown source not found: {MD_PATH}")

    markdown = MD_PATH.read_text(encoding="utf-8")

    doc = Document()
    set_uniform_page_layout(doc)
    configure_styles(doc)
    add_cover(doc)
    add_toc(doc)
    render_markdown(doc, markdown)
    add_roles_table(doc)
    doc.save(DOCX_PATH)
    print(f"Generated: {DOCX_PATH}")


if __name__ == "__main__":
    main()

