"""Structured clinician summary.

Written to be pasted into a note. Every summary states what was assessed, what
was NOT assessed, the routing decision, and the confirmation requirement.
"""

from __future__ import annotations

from .analysis.modules_config import MODULES
from .analysis.types import Grade, ModuleResult, QualityReport
from .safety import (
    DEVICE_NOTICE,
    DISCLAIMER,
    HUMAN_IN_THE_LOOP,
    MODULE_LIMITATIONS,
    NO_FLAG_CAVEAT,
)


def build_summary(
    *,
    module: str,
    patient_ref: str,
    body_site: str | None,
    result: ModuleResult,
    quality: QualityReport,
    captured_at: str,
) -> str:
    mod = MODULES[module]
    triage = result.triage
    lines: list[str] = []

    lines.append(f"QADAM {mod['label_en']} screening — clinician summary")
    lines.append(f"Patient reference: {patient_ref}")
    lines.append(f"Image captured: {captured_at}")
    if body_site:
        lines.append(f"Body site: {body_site}")
    lines.append(f"Model: {result.model_version} ({result.backend})")
    lines.append("")

    lines.append(f"TRIAGE: {str(triage.grade).upper()} — {triage.label}")
    lines.append(f"Confidence: {triage.confidence:.2f} (image quality "
                 f"{'passed' if quality.passed else 'degraded'}, factor "
                 f"{quality.confidence_factor:.2f})")
    lines.append("")

    lines.append("RECOMMENDED NEXT INVESTIGATION")
    lines.append(f"  Timeframe: {triage.urgency}")
    lines.append(f"  Route to: {triage.routing_target}")
    lines.append(f"  {triage.next_investigation}")
    lines.append("")

    lines.append("VISIBLE SURFACE FINDINGS")
    if result.lesions:
        for lesion in result.lesions:
            lines.append(
                f"  - {lesion.kind.replace('_', ' ')}: {lesion.area_pct:.1f}% of "
                f"the imaged region, severity {lesion.severity:.2f}"
                + (f" — {lesion.description}" if lesion.description else "")
            )
    else:
        lines.append("  - No discrete surface finding isolated in this image.")
    lines.append("")

    lines.append("BASIS FOR THIS GRADE")
    for reason in triage.rationale:
        lines.append(f"  - {reason}")
    lines.append("")

    lines.append("IMAGE QUALITY")
    for check in quality.checks:
        state = "pass" if check.passed else "FAIL"
        lines.append(f"  - {check.name}: {state} ({check.value:.1f} vs "
                     f"{check.threshold:.1f})")
    lines.append("")

    lines.append("NOT ASSESSED / LIMITATIONS")
    for limitation in MODULE_LIMITATIONS.get(module, []):
        lines.append(f"  - {limitation}")
    if triage.grade is Grade.NO_FLAG and module in NO_FLAG_CAVEAT:
        lines.append(f"  - {NO_FLAG_CAVEAT[module]}")
    lines.append("")

    lines.append(DEVICE_NOTICE)
    lines.append(DISCLAIMER)
    lines.append(HUMAN_IN_THE_LOOP)
    lines.append("")
    lines.append("Clinician confirmation: ______________________  "
                 "Date: ____________")
    return "\n".join(lines)
