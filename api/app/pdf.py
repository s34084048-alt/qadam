"""Clinician summary PDF.

The exported document is the artefact most likely to leave the platform, so it
carries the full safety boundary: device notice, disclaimer, intended use, the
module's limitations, and a clinician confirmation line.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .analysis import lesion_role
from .analysis.modules_config import GRADE_STYLE, MODULES
from .safety import (
    DEVICE_NOTICE,
    DISCLAIMER,
    HUMAN_IN_THE_LOOP,
    INTENDED_USE,
    MODULE_LIMITATIONS,
    NO_FLAG_CAVEAT,
    NO_TREATMENT_STATEMENT,
)

# The overlay is printed at most 150 mm wide. Embedding a 3000 px phone capture
# raw puts ~14 MB of pixels behind that, which makes the summary unusable over
# email for no visible gain. 1800 px across 150 mm is ~300 DPI -- past what the
# page can show. The full-resolution overlay stays in object storage and is the
# authoritative artefact.
PDF_MAX_IMAGE_WIDTH = 1800


def _fit_for_print(png_bytes: bytes) -> bytes:
    try:
        import cv2
        import numpy as np

        img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None or img.shape[1] <= PDF_MAX_IMAGE_WIDTH:
            return png_bytes
        scale = PDF_MAX_IMAGE_WIDTH / img.shape[1]
        resized = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".png", resized)
        return buf.tobytes() if ok else png_bytes
    except Exception:
        return png_bytes


_styles = getSampleStyleSheet()
S_TITLE = ParagraphStyle("qtitle", parent=_styles["Title"], fontSize=17, spaceAfter=2)
S_SUB = ParagraphStyle("qsub", parent=_styles["Normal"], fontSize=9,
                       textColor=colors.HexColor("#555555"))
S_H = ParagraphStyle("qh", parent=_styles["Heading2"], fontSize=11.5,
                     spaceBefore=10, spaceAfter=4,
                     textColor=colors.HexColor("#1B2A3A"))
S_BODY = ParagraphStyle("qbody", parent=_styles["Normal"], fontSize=9.5,
                        leading=13, alignment=TA_LEFT)
S_SMALL = ParagraphStyle("qsmall", parent=_styles["Normal"], fontSize=8,
                         leading=10.5, textColor=colors.HexColor("#444444"))
S_WARN = ParagraphStyle("qwarn", parent=_styles["Normal"], fontSize=9,
                        leading=12, textColor=colors.HexColor("#8A1A1A"))


def _banner(text: str, bg: str, fg: str = "#FFFFFF", size: float = 11) -> Table:
    style = ParagraphStyle("bn", parent=_styles["Normal"], fontSize=size,
                           leading=size + 3, textColor=colors.HexColor(fg))
    t = Table([[Paragraph(f"<b>{text}</b>", style)]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", S_BODY), Paragraph(v, S_BODY)] for k, v in rows]
    t = Table(data, colWidths=[45 * mm, 125 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#8A1A1A"))
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(20 * mm, 12 * mm, DEVICE_NOTICE)
    canvas.setFillColor(colors.HexColor("#444444"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(20 * mm, 8.5 * mm, DISCLAIMER)
    canvas.drawRightString(190 * mm, 8.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_case_pdf(
    *,
    module: str,
    patient_ref: str,
    case_id: str,
    body_site: str | None,
    created_at: str,
    triage: dict[str, Any] | None = None,
    lesions: list[dict[str, Any]] | None = None,
    quality: dict[str, Any] | None = None,
    features: dict[str, Any] | None = None,
    model_version: str | None = None,
    backend: str | None = None,
    overlay_png: bytes | None = None,
    history: list[dict[str, Any]] | None = None,
    foot_risk: dict[str, Any] | None = None,
    lab_panels: list[dict[str, Any]] | None = None,
    investigations: list[dict[str, Any]] | None = None,
    follow_ups: list[dict[str, Any]] | None = None,
) -> bytes:
    """The exported screening record.

    Every section is optional except the safety pages. A diabetic foot visit
    where the monofilament test was done but the photograph failed the quality
    gate is a real and common visit, and that record must still export -- the
    clinical examination is the part that sets the screening interval.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=16 * mm, bottomMargin=20 * mm,
        title=f"QADAM summary {case_id}", author="QADAM",
    )
    mod = MODULES[module]
    lesions = lesions or []
    quality = quality or {}
    grade = (triage or {}).get("grade") or (foot_risk or {}).get("grade") or "no_flag"
    style = GRADE_STYLE[grade]
    flow: list[Any] = []

    flow.append(Paragraph("QADAM — clinician summary", S_TITLE))
    flow.append(Paragraph(
        f"{mod['label_en']} · surface screening and triage routing", S_SUB))
    flow.append(Spacer(1, 5))
    flow.append(_banner(DEVICE_NOTICE, "#8A1A1A"))
    flow.append(Spacer(1, 3))
    flow.append(_banner(DISCLAIMER, "#2B2B2B", size=9))
    flow.append(Spacer(1, 9))

    flow.append(_kv_table([
        ("Patient reference", patient_ref),
        ("Case", case_id),
        ("Module", f"{mod['label_en']} ({module})"),
        ("Body site", body_site or "not recorded"),
        ("Captured", created_at),
        ("Model", f"{model_version} · backend {backend}"
                  if model_version else "no image analysis in this record"),
    ]))
    flow.append(Spacer(1, 10))

    if triage:
        flow.append(_banner(
            f"TRIAGE: {grade.replace('_', ' ').upper()} — {triage['label']}   "
            f"(confidence {triage['confidence']:.2f})",
            style["color"],
        ))
        flow.append(Spacer(1, 8))

        flow.append(Paragraph("Recommended next investigation", S_H))
        # Empty when the instruction was withheld: a blank "Timeframe" row
        # reads as a value that failed to load, not as one deliberately not
        # issued. The paragraph below carries the reason.
        rows = [(label, triage[key]) for label, key in
                (("Timeframe", "urgency"), ("Route to", "routing_target"))
                if triage.get(key)]
        if rows:
            flow.append(_kv_table(rows))
        flow.append(Spacer(1, 4))
        flow.append(Paragraph(triage["next_investigation"], S_BODY))

    if overlay_png:
        try:
            source_width = ImageReader(io.BytesIO(overlay_png)).getSize()[0]
            overlay_png = _fit_for_print(overlay_png)
            reader = ImageReader(io.BytesIO(overlay_png))
            iw, ih = reader.getSize()
            # Fit the page box, but never enlarge past 150 DPI: blowing a small
            # capture up to fill the width makes it look zoomed and pixelated,
            # and invites reading detail that is not in the image.
            ratio = min(150 * mm / iw, 105 * mm / ih, 72.0 / 150.0)
            flow.append(KeepTogether([
                Paragraph("Annotated image", S_H),
                Image(io.BytesIO(overlay_png), iw * ratio, ih * ratio),
                Paragraph(
                    f"Printed {iw * ratio / mm:.0f} mm wide at "
                    f"{72.0 / ratio:.0f} DPI, from a {source_width} px capture. "
                    f"Findings are outlined on the image; measurements are in "
                    f"the table below. The full-resolution annotated image is "
                    f"held in the case record.", S_SMALL),
            ]))
        except Exception:
            flow.append(Paragraph("Annotated image", S_H))
            flow.append(Paragraph("Overlay unavailable.", S_SMALL))

    if triage:
        flow.append(Paragraph("Visible surface findings", S_H))
    if lesions:
        data = [[Paragraph("<b>Finding</b>", S_SMALL),
                 Paragraph("<b>Area %</b>", S_SMALL),
                 Paragraph("<b>Severity</b>", S_SMALL),
                 Paragraph("<b>Description</b>", S_SMALL)]]
        for les in lesions:
            # The role belongs beside the kind, not in a column that can be
            # cropped off: a PDF page is forwarded on its own.
            role = les.get("role")
            kind = les["kind"].replace("_", " ")
            data.append([
                Paragraph(
                    f"{kind} [{lesion_role.ROLE_LABEL.get(role, role)}]"
                    if role else kind, S_SMALL),
                Paragraph(f"{les['area_pct']:.1f}", S_SMALL),
                Paragraph(f"{les['severity']:.2f}", S_SMALL),
                Paragraph(les.get("description", ""), S_SMALL),
            ])
        t = Table(data, colWidths=[38 * mm, 16 * mm, 18 * mm, 98 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        flow.append(t)
    elif triage:
        flow.append(Paragraph(
            "No discrete surface finding was isolated in this image.", S_BODY))

    if triage:
        flow.append(Paragraph("Basis for this grade", S_H))
        for reason in triage.get("rationale", []):
            flow.append(Paragraph(f"• {reason}", S_BODY))

    if quality.get("checks"):
        flow.append(Paragraph("Image quality", S_H))
        qdata = [[Paragraph("<b>Check</b>", S_SMALL),
                  Paragraph("<b>Result</b>", S_SMALL),
                  Paragraph("<b>Measured</b>", S_SMALL),
                  Paragraph("<b>Threshold</b>", S_SMALL)]]
        for check in quality.get("checks", []):
            qdata.append([
                Paragraph(check["name"], S_SMALL),
                Paragraph("pass" if check["passed"] else "FAIL", S_SMALL),
                Paragraph(f"{check['value']:.1f}", S_SMALL),
                Paragraph(f"{check['threshold']:.1f}", S_SMALL),
            ])
        qt = Table(qdata, colWidths=[45 * mm, 25 * mm, 45 * mm, 55 * mm])
        qt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
        ]))
        flow.append(qt)

    if history:
        flow.append(Paragraph("Prior analyses for this case", S_H))
        hdata = [[Paragraph("<b>Date</b>", S_SMALL),
                  Paragraph("<b>Grade</b>", S_SMALL),
                  Paragraph("<b>Confidence</b>", S_SMALL),
                  Paragraph("<b>Model</b>", S_SMALL)]]
        for h in history:
            hdata.append([
                Paragraph(h["created_at"], S_SMALL),
                Paragraph(h["grade"].replace("_", " "), S_SMALL),
                Paragraph(f"{h['confidence']:.2f}", S_SMALL),
                Paragraph(h["model_version"], S_SMALL),
            ])
        ht = Table(hdata, colWidths=[50 * mm, 35 * mm, 30 * mm, 55 * mm])
        ht.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
        ]))
        flow.append(ht)

    # --- structured foot examination -------------------------------------
    if foot_risk:
        flow.append(Paragraph("Diabetic foot risk assessment (IWGDF)", S_H))
        if foot_risk.get("complete") and foot_risk.get("category") is not None:
            flow.append(_banner(
                f"IWGDF CATEGORY {foot_risk['category']} — "
                f"{foot_risk['label']}   ·   {foot_risk['screening_interval']}",
                GRADE_STYLE[foot_risk.get("grade", "no_flag")]["color"],
            ))
        else:
            flow.append(_banner(
                "NO RISK CATEGORY PRODUCED — a required test was not performed. "
                "An absent test is not a negative test.",
                "#8A1A1A",
            ))
        flow.append(Spacer(1, 6))
        findings = foot_risk.get("findings") or {}
        if findings:
            labels = {
                "lops": "Loss of protective sensation (10 g monofilament)",
                "pad": "Peripheral artery disease (pulses / pressures)",
                "deformity": "Foot deformity",
                "previous_ulcer": "Previous foot ulcer",
                "previous_amputation": "Previous lower-extremity amputation",
                "end_stage_renal_disease": "End-stage renal disease",
            }
            fdata = [[Paragraph("<b>Finding</b>", S_SMALL),
                      Paragraph("<b>Recorded</b>", S_SMALL)]]
            for key, label in labels.items():
                value = findings.get(key, "not recorded").replace("_", " ")
                fdata.append([Paragraph(label, S_SMALL),
                              Paragraph(value.upper() if value == "not tested"
                                        else value, S_SMALL)])
            ft = Table(fdata, colWidths=[110 * mm, 60 * mm])
            ft.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ]))
            flow.append(ft)
        for line in foot_risk.get("missing_tests", []):
            flow.append(Paragraph(f"• OUTSTANDING: {line}", S_WARN))
        for line in foot_risk.get("rationale", []):
            flow.append(Paragraph(f"• {line}", S_SMALL))
        flow.append(Paragraph(foot_risk.get("source", ""), S_SMALL))

    # --- laboratory ------------------------------------------------------
    if lab_panels:
        flow.append(Paragraph("Laboratory results", S_H))
        for panel in lab_panels:
            flow.append(Paragraph(
                f"<b>{panel.get('panel_name') or 'Panel'}</b> — "
                f"{panel.get('triage_grade', '').replace('_', ' ')}", S_BODY))
            ldata = [[Paragraph("<b>Analyte</b>", S_SMALL),
                      Paragraph("<b>Value</b>", S_SMALL),
                      Paragraph("<b>Reference</b>", S_SMALL),
                      Paragraph("<b>Flag</b>", S_SMALL)]]
            for r in panel.get("results", []):
                low, high = r["reference"]["low"], r["reference"]["high"]
                ref = ("—" if low is None and high is None else
                       f"< {high}" if low is None else
                       f"> {low}" if high is None else f"{low} – {high}")
                ldata.append([
                    Paragraph(r["name"], S_SMALL),
                    Paragraph(f"{r['value']:g} {r['unit']}", S_SMALL),
                    Paragraph(ref, S_SMALL),
                    Paragraph("CRITICAL" if r["critical"] else r["flag"], S_SMALL),
                ])
            lt = Table(ldata, colWidths=[55 * mm, 40 * mm, 40 * mm, 35 * mm])
            lt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ]))
            flow.append(lt)
            for d in panel.get("derived", []):
                flow.append(Paragraph(
                    f"• {d['name']}: {d['value']} {d['unit']} — "
                    f"{d['interpretation']}", S_SMALL))
        flow.append(Paragraph(
            "Reference ranges are common adult values, not universal. The "
            "reporting laboratory's range takes precedence.", S_SMALL))

    # --- filed investigation results -------------------------------------
    if investigations:
        flow.append(Paragraph("Investigation results on file", S_H))
        flow.append(Paragraph(
            "<b>Stored, not interpreted.</b> QADAM has not read these "
            "documents and has produced no finding from them.", S_WARN))
        for inv in investigations:
            header = " · ".join(filter(None, [
                inv.get("category"), inv.get("modality"), inv.get("body_site"),
                inv.get("reporting_service"),
            ]))
            flow.append(Paragraph(f"<b>{header}</b>", S_SMALL))
            if inv.get("report_text"):
                flow.append(Paragraph(inv["report_text"], S_SMALL))
            if inv.get("has_file"):
                flow.append(Paragraph(
                    "A document is attached to this case in the platform.",
                    S_SMALL))

    # --- clinician follow-up ----------------------------------------------
    # Placed last among the clinical sections and deliberately not summarised:
    # this is what the clinician examined and wrote, and an export that
    # paraphrases it is no longer the record.
    if follow_ups:
        flow.append(Paragraph("Clinician follow-up", S_H))
        flow.append(Paragraph(
            "<b>Entered by a clinician, not measured by QADAM.</b> The case "
            "is routed on these answers and the IWGDF risk category. The "
            "photograph is not an input to that decision — it is the record.",
            S_WARN))
        for entry in follow_ups:
            flow.append(Paragraph(
                f"<b>{entry.get('created_at', '')}</b> — answers "
                f"<b>{entry.get('answer_grade', '?')}</b>"
                + (f" (image observed: {entry['image_grade']}, "
                   "not used for routing)" if entry.get("image_grade") else ""),
                S_SMALL))
            answers = entry.get("answers") or {}
            if answers:
                flow.append(_kv_table([
                    (str(k).replace("_", " "), str(v))
                    for k, v in answers.items()
                ]))
            for trigger in entry.get("triggers", []):
                flow.append(Paragraph(
                    f"• <b>{trigger.get('finding', '')}</b> "
                    f"({trigger.get('grade', '')}) — "
                    f"{trigger.get('because', '')}", S_SMALL))
                if trigger.get("distinguished_by"):
                    flow.append(Paragraph(
                        f"&nbsp;&nbsp;&nbsp;Distinguished by: "
                        f"{trigger['distinguished_by']}", S_SMALL))
            if entry.get("note"):
                flow.append(Paragraph("<b>Clinical notes</b>", S_SMALL))
                for line in str(entry["note"]).splitlines():
                    flow.append(Paragraph(line or "&nbsp;", S_SMALL))
            flow.append(Spacer(1, 6))

    flow.append(PageBreak())
    flow.append(Paragraph("Scope, limitations and required confirmation", S_H))
    for limitation in MODULE_LIMITATIONS.get(module, []):
        flow.append(Paragraph(f"• {limitation}", S_WARN))
        flow.append(Spacer(1, 2))
    if grade == "no_flag" and module in NO_FLAG_CAVEAT:
        flow.append(Spacer(1, 4))
        flow.append(_banner(NO_FLAG_CAVEAT[module], "#8A1A1A", size=8.5))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph(NO_TREATMENT_STATEMENT, S_BODY))
    flow.append(Spacer(1, 4))
    flow.append(Paragraph(f"<b>{HUMAN_IN_THE_LOOP}</b>", S_BODY))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph("Intended use", S_H))
    flow.append(Paragraph(INTENDED_USE, S_SMALL))
    flow.append(Spacer(1, 14))
    flow.append(HRFlowable(width="100%", color=colors.HexColor("#999999")))
    flow.append(Spacer(1, 6))
    flow.append(KeepTogether([
        Paragraph("Reviewed and confirmed by clinician", S_H),
        Spacer(1, 10),
        _kv_table([
            ("Name", "________________________________________"),
            ("Signature", "________________________________________"),
            ("Date", "________________________________________"),
            ("Action taken", "________________________________________"),
        ]),
    ]))

    doc.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
