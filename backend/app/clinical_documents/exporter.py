"""
Clinical Documents — Exporter.

Generates professional Word (DOCX) files from finalized clinical documents.
"""
from __future__ import annotations

import io
from datetime import datetime
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn


def set_run_font(
    run,
    font_name: str = "SimSun",
    font_size: float = 10.5,
    bold: bool = False,
    italic: bool = False,
    color_rgb: RGBColor | None = None,
):
    """Set font styling including East Asia font support in python-docx."""
    run.font.name = 'Times New Roman'
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn('w:eastAsia'), font_name)
    run.font.size = Pt(font_size)
    run.bold = bold
    run.italic = italic
    if color_rgb:
        run.font.color.rgb = color_rgb


def export_progress_note_docx(draft: dict) -> bytes:
    """Generate a highly professional clinical progress note in DOCX format."""
    doc = Document()

    # Set margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Document Header
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_p.add_run("ICU 24小时病程记录")
    set_run_font(
        title_run,
        font_name="Microsoft YaHei",
        font_size=16,
        bold=True,
        color_rgb=RGBColor(22, 119, 255),
    )

    # Context basics
    snapshot = draft.get("context_snapshot") or {}
    basics = snapshot.get("basics") or {}
    patient_id = draft.get("patient_id") or ""
    patient_name = basics.get("name") or snapshot.get("patient_name") or "未提供"

    # Patient details grid
    table = doc.add_table(rows=2, cols=4)
    table.style = 'Table Grid'

    headers = ["床号", "患者姓名 / ID", "性别 / 年龄", "入院天数"]
    values = [
        str(basics.get("bed") or "未提供"),
        f"{patient_name} ({patient_id})",
        f"{basics.get('sex') or '未提供'} / {basics.get('age') or '未提供'}岁",
        f"第 {basics.get('day') or '未提供'} 天"
    ]

    # Write headers
    hdr_cells = table.rows[0].cells
    for i, h_text in enumerate(headers):
        hdr_cells[i].text = h_text
        hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        # style run
        for r in hdr_cells[i].paragraphs[0].runs:
            set_run_font(r, font_name="Microsoft YaHei", font_size=10, bold=True)

    # Write values
    val_cells = table.rows[1].cells
    for i, v_text in enumerate(values):
        val_cells[i].text = v_text
        val_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        # style run
        for r in val_cells[i].paragraphs[0].runs:
            set_run_font(r, font_name="SimSun", font_size=10)

    doc.add_paragraph()  # spacing

    # Main Diagnosis
    diag_p = doc.add_paragraph()
    r_label = diag_p.add_run("主要诊断：")
    set_run_font(r_label, font_name="Microsoft YaHei", font_size=11, bold=True)
    r_val = diag_p.add_run(str(basics.get("diagnosis") or "未提供"))
    set_run_font(r_val, font_name="SimSun", font_size=11)

    doc.add_paragraph()  # spacing

    content = draft.get("current_content") or {}

    # Helper for rendering sections
    def add_soap_section(tag: str, title_text: str, data: any):
        h = doc.add_paragraph()
        run_tag = h.add_run(f"【{tag}】 ")
        set_run_font(
            run_tag,
            font_name="Microsoft YaHei",
            font_size=12,
            bold=True,
            color_rgb=RGBColor(22, 119, 255),
        )
        run_title = h.add_run(title_text)
        set_run_font(run_title, font_name="Microsoft YaHei", font_size=12, bold=True)

        if isinstance(data, str):
            p = doc.add_paragraph()
            # Indent text slightly
            p.paragraph_format.left_indent = Inches(0.2)
            run_text = p.add_run(data)
            set_run_font(run_text, font_name="SimSun", font_size=10.5)
        elif isinstance(data, dict):
            for sub_key, sub_val in data.items():
                if not sub_val:
                    continue
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.2)
                
                label_map = {
                    "vitals": "生命体征",
                    "labs": "检验",
                    "drugs": "用药",
                    "ventilator": "呼吸机",
                    "alerts": "告警",
                }
                lbl = label_map.get(sub_key, sub_key)
                r_sub_lbl = p.add_run(f"• {lbl}: ")
                set_run_font(r_sub_lbl, font_name="Microsoft YaHei", font_size=10, bold=True)
                
                r_sub_val = p.add_run(str(sub_val))
                set_run_font(r_sub_val, font_name="SimSun", font_size=10.5)
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                if not item:
                    continue
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.2)
                r_item = p.add_run(f"{idx + 1}. {item}")
                set_run_font(r_item, font_name="SimSun", font_size=10.5)

    # S (Subjective)
    add_soap_section("S", "主观症状 (Subjective)", content.get("subjective") or "未提供")
    doc.add_paragraph()

    # O (Objective)
    add_soap_section("O", "客观检查 (Objective)", content.get("objective") or {})
    doc.add_paragraph()

    # A (Assessment)
    add_soap_section("A", "病情评估 (Assessment)", content.get("assessment") or {})
    doc.add_paragraph()

    # P (Plan)
    add_soap_section("P", "诊疗计划 (Plan)", content.get("plan") or [])
    doc.add_paragraph()

    # Overall Trend & Key Concerns
    tc_p = doc.add_paragraph()
    tc_p.paragraph_format.left_indent = Inches(0.2)
    
    r_trend_lbl = tc_p.add_run("总体趋势：")
    set_run_font(r_trend_lbl, font_name="Microsoft YaHei", font_size=10, bold=True)
    r_trend_val = tc_p.add_run(f"{content.get('overall_trend') or '平稳'}    ")
    set_run_font(r_trend_val, font_name="SimSun", font_size=10.5)

    r_conc_lbl = tc_p.add_run("重点关注：")
    set_run_font(r_conc_lbl, font_name="Microsoft YaHei", font_size=10, bold=True)
    r_conc_val = tc_p.add_run(", ".join(content.get("key_concerns") or ["无"]))
    set_run_font(r_conc_val, font_name="SimSun", font_size=10.5)

    doc.add_paragraph()

    # Signature line if finalized
    if draft.get("status") == "finalized":
        sig_p = doc.add_paragraph()
        sig_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        
        signer = draft.get("finalized_by") or "系统"
        sig_date = draft.get("finalized_at")
        if isinstance(sig_date, str):
            try:
                sig_date = datetime.fromisoformat(sig_date)
            except ValueError:
                pass
                
        sig_str = sig_date.strftime("%Y-%m-%d %H:%M") if isinstance(sig_date, datetime) else str(sig_date or "")
        
        sig_run = sig_p.add_run(f"医师签署： {signer}      签署日期： {sig_str}")
        set_run_font(sig_run, font_name="SimSun", font_size=11, bold=True, italic=True)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
