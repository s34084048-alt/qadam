"""Clinical depth layer.

Turns a set of measured surface features into the kind of structured note a
specialist would write from the same photograph: what the visible pattern
overlaps with, what test separates those possibilities, what to do right now to
protect the patient, and what to ask or examine because the camera cannot.

THE BOUNDARY IS UNCHANGED. Nothing here asserts a diagnosis. Every entry is a
DIFFERENTIAL -- a list of possibilities a clinician should evaluate -- and each
one names the investigation that actually distinguishes them. A single-item
differential is never emitted: if the surface cannot narrow it, it says so.

`immediate_actions` are protective, non-pharmacological steps taken WHILE the
referral is being arranged. No medication, no dose, no procedure, no wound
manipulation. See test_safety_boundary.py, which enforces all of this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import Grade, Lesion


@dataclass(slots=True)
class Consideration:
    """One differential prompt. `overlaps_with` always holds 2+ entries."""

    pattern: str
    overlaps_with: list[str]
    distinguished_by: str

    def to_json(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "overlaps_with": list(self.overlaps_with),
            "distinguished_by": self.distinguished_by,
        }


@dataclass(slots=True)
class ClinicalContext:
    severity_index: dict[str, Any] | None = None
    considerations: list[Consideration] = field(default_factory=list)
    immediate_actions: list[str] = field(default_factory=list)
    ask_and_check: list[str] = field(default_factory=list)
    not_assessable: list[str] = field(default_factory=list)
    scales: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "severity_index": self.severity_index,
            "considerations": [c.to_json() for c in self.considerations],
            "immediate_actions": list(self.immediate_actions),
            "ask_and_check": list(self.ask_and_check),
            "not_assessable": list(self.not_assessable),
            "scales": dict(self.scales),
            "status": (
                "Differential prompts for a clinician, not findings. The list is "
                "what the visible surface is compatible with; the named test is "
                "what settles it."
            ),
        }


# --- foot --------------------------------------------------------------------

def _foot(grade: Grade, f: dict[str, Any]) -> ClinicalContext:
    ery = float(f.get("erythema_pct", 0.0))
    brk = float(f.get("breakdown_pct", 0.0))
    nec = float(f.get("dark_area_pct", 0.0))

    # Weighted surface burden. Necrotic-appearing tissue and an open bed carry
    # far more weight than redness alone. Bounded 0-100; it summarises the
    # IMAGE, not the limb.
    burden = min(100.0, nec * 12.0 + brk * 6.0 + ery * 1.2)
    band = ("minimal" if burden < 5 else
            "mild" if burden < 20 else
            "moderate" if burden < 50 else "extensive")

    ctx = ClinicalContext(
        severity_index={
            "name": "Surface burden index",
            "value": round(burden, 1),
            "unit": "% (weighted surface score, 0-100)",
            "band": band,
            "components": {
                "dark_area_pct": round(nec, 2),
                "tissue_breakdown_pct": round(brk, 2),
                "erythema_pct": round(ery, 2),
            },
            "caveat": "A composite of visible area only. It is not a wound "
                      "grade and does not correlate with depth or infection.",
        },
        scales={
            "SINBAD": {
                "assessable_from_this_image": ["Area (surface extent only)"],
                "requires_clinical_examination": [
                    "Site (confirm anatomically)",
                    "Ischaemia (pulses, ABPI or toe pressures)",
                    "Neuropathy (10 g monofilament, vibration)",
                    "Bacterial infection (clinical signs, swab)",
                    "Depth (probe-to-bone)",
                ],
                "note": "5 of 6 SINBAD components cannot be obtained from a "
                        "photograph. No SINBAD score is produced.",
            },
            "Wagner": {
                "assessable_from_this_image": [],
                "note": "Wagner grading is depth-based and starts at the "
                        "question of whether the ulcer penetrates to tendon, "
                        "capsule or bone. A photograph cannot answer that, so "
                        "no Wagner grade is produced.",
            },
        },
        ask_and_check=[
            "Pulses (dorsalis pedis, posterior tibial) and capillary refill.",
            "Protective sensation with a 10 g monofilament at standard sites.",
            "Probe-to-bone if there is an open wound.",
            "Fever, rigors, malaise, or rapidly spreading redness.",
            "Glycaemic control, and how long the lesion has been present.",
            "Previous ulcer or amputation, smoking, renal disease.",
            "Always inspect the OTHER foot and between all toes.",
        ],
        not_assessable=[
            "Whether tissue is viable. A photograph cannot separate eschar "
            "from shadow, bruising or pigmentation — only inspection can.",
            "Wound depth and whether bone is involved.",
            "Infection, osteomyelitis, or abscess.",
            "Arterial perfusion and tissue viability.",
            "Neuropathy.",
        ],
    )

    if nec >= 1.5:
        ctx.considerations.append(Consideration(
            pattern="Area markedly darker than the surrounding skin",
            overlaps_with=[
                "SHADOW — the commonest explanation by far, especially between "
                "toes, under an arch, or in raking light",
                "normal pigmentation, a callus, or a healing bruise",
                "dressing residue, iodine, henna or another topical dye",
                "haematoma under a callus",
                "eschar or dry gangrene",
                "deep tissue pressure injury",
            ],
            distinguished_by="RE-IMAGE IN EVEN, INDIRECT LIGHT FIRST — a dark "
                             "area that moves or disappears was shadow. If it "
                             "persists, direct inspection with debridement of "
                             "overlying callus by a trained clinician, "
                             "perfusion assessment (pulses, ABPI, toe "
                             "pressures), and imaging where osteomyelitis is "
                             "suspected.",
        ))
    if brk >= 0.4:
        ctx.considerations.append(Consideration(
            pattern="Open wound bed with slough on the surface",
            overlaps_with=[
                "neuropathic (plantar, punched-out) ulcer",
                "ischaemic ulcer",
                "neuroischaemic ulcer",
                "pressure or footwear-related ulceration",
                "traumatic wound or burn",
            ],
            distinguished_by="Site and margin pattern on examination, "
                             "monofilament testing, pulses and ABPI. These "
                             "differ in management, and only examination "
                             "separates them.",
        ))
    if ery >= 4.0:
        ctx.considerations.append(Consideration(
            pattern="Area of surface erythema",
            overlaps_with=[
                "cellulitis",
                "acute Charcot neuroarthropathy",
                "dependent rubor of critical ischaemia",
                "gout or inflammatory arthropathy",
                "pressure erythema or a reaction to footwear",
            ],
            distinguished_by="Skin temperature difference between feet, "
                             "whether the redness settles on elevation, "
                             "systemic signs, inflammatory markers, and "
                             "imaging. Charcot and cellulitis look alike in a "
                             "photograph and are managed very differently.",
        ))
    if not ctx.considerations:
        ctx.considerations.append(Consideration(
            pattern="No discrete surface abnormality isolated",
            overlaps_with=[
                "intact skin",
                "an early lesion below the resolution or contrast of this image",
                "a lesion outside the photographed field",
            ],
            distinguished_by="Structured foot examination, which also covers "
                             "perfusion and sensation that no photograph shows.",
        ))

    if grade in (Grade.REVIEW, Grade.URGENT):
        ctx.immediate_actions = [
            "Stop weight-bearing on the affected foot and offload it while the "
            "referral is arranged.",
            "Remove tight or rubbing footwear and any constricting sock.",
            "Keep the area clean and dry. Cover with a simple dry dressing.",
            "Do NOT debride, cut, or use corn removers, and do NOT apply heat "
            "or a hot-water bottle.",
            "Do not soak the foot.",
            "Escalate the same day if there is fever, spreading redness, foul "
            "odour, or the foot becomes cold, pale or acutely painful.",
        ]
    elif grade is Grade.MONITOR:
        ctx.immediate_actions = [
            "Offload and change footwear; recheck the area daily.",
            "Do not apply heat or attempt to trim callus.",
            "Seek review sooner if the area opens, spreads, or discharges.",
        ]
    else:
        ctx.immediate_actions = [
            "Continue daily foot inspection, including between the toes and "
            "the other foot.",
            "Well-fitting footwear; never walk barefoot.",
        ]
    return ctx


# --- skin --------------------------------------------------------------------

def _skin(grade: Grade, f: dict[str, Any]) -> ClinicalContext:
    area = float(f.get("lesion_area_pct", 0.0))
    border = float(f.get("border_irregularity", 0.0))
    asym = float(f.get("asymmetry", 0.0))
    colours = int(f.get("colour_clusters", 1) or 1)
    inflam = float(f.get("inflammation_pct", 0.0))
    criteria = list(f.get("criteria_met", []))

    # ABCDE, scored explicitly. E (Evolution) can never come from one still
    # image -- it is a history question, and it is the single most useful of
    # the five.
    abcde = {
        "A_asymmetry": {
            "measured": round(asym, 3),
            "flagged": asym >= 0.25,
            "basis": "Mismatch on reflection about the lesion's principal axis.",
        },
        "B_border": {
            "measured": round(border, 3),
            "flagged": border >= 1.35,
            "basis": "Perimeter² / 4πArea. 1.0 is a perfect circle.",
        },
        "C_colour": {
            "measured": colours,
            "flagged": colours >= 3,
            "basis": "Distinct colour clusters occupying ≥12% of the lesion.",
        },
        "D_diameter": {
            "measured": None,
            "flagged": None,
            "basis": "NOT MEASURED. Absolute diameter needs a size reference "
                     "(ruler or sticker) in the frame. Re-image with one.",
        },
        "E_evolution": {
            "measured": None,
            "flagged": None,
            "basis": "NOT ASSESSABLE from a single image. Ask the patient "
                     "directly, or re-image this case later and compare.",
        },
    }
    flagged = sum(1 for k, v in abcde.items() if v["flagged"] is True)

    ctx = ClinicalContext(
        severity_index={
            "name": "ABCDE surface criteria met",
            "value": flagged,
            "unit": "of 3 assessable (D and E need a size marker / history)",
            "band": ("none" if flagged == 0 else
                     "one" if flagged == 1 else
                     "two" if flagged == 2 else "all three"),
            "components": criteria,
            "caveat": "ABCDE is a referral prompt, not a diagnostic test. It "
                      "misses nodular and amelanotic lesions, which can look "
                      "bland.",
        },
        scales={"ABCDE": abcde},
        ask_and_check=[
            "How long has it been there, and has it CHANGED in size, shape, "
            "colour or elevation? (the 'E' this image cannot supply)",
            "Has it bled, crusted, ulcerated, or failed to heal?",
            "Is it itchy, painful, or new in an adult over 50?",
            "Is it the 'ugly duckling' — different from the patient's other moles?",
            "Sun exposure, sunburns, sunbed use, outdoor work.",
            "Personal or family history of melanoma or skin cancer; "
            "immunosuppression or transplant.",
            "Examine the whole skin surface and regional lymph nodes.",
        ],
        not_assessable=[
            "Dermoscopic structures (pigment network, streaks, blue-white veil, "
            "vascular patterns) — a dermatoscope is required.",
            "Whether the lesion is benign or malignant — only histopathology "
            "answers that.",
            "Breslow thickness or any depth measure.",
            "Palpable features: elevation, induration, tenderness.",
        ],
    )

    if flagged >= 2:
        ctx.considerations.append(Consideration(
            pattern="Pigmented lesion that is asymmetric and/or irregularly "
                    "bordered with multiple colours",
            overlaps_with=[
                "melanoma",
                "atypical / dysplastic naevus",
                "seborrhoeic keratosis with irregular pigmentation",
                "pigmented basal cell carcinoma",
                "traumatised or irritated benign naevus",
                "solar lentigo with uneven pigment",
            ],
            distinguished_by="Dermoscopy by a trained clinician, and excision "
                             "biopsy with histopathology where dermoscopy is "
                             "not reassuring. Several of these are common and "
                             "benign; photography cannot separate them.",
        ))
    elif flagged == 1:
        ctx.considerations.append(Consideration(
            pattern="Pigmented lesion with one atypical surface feature",
            overlaps_with=[
                "benign melanocytic naevus",
                "seborrhoeic keratosis",
                "solar lentigo",
                "atypical naevus",
                "early melanoma (can present with a single feature)",
            ],
            distinguished_by="Dermoscopy, and comparison against a repeat "
                             "image over 4–8 weeks with a size marker in frame.",
        ))
    elif area >= 0.3:
        ctx.considerations.append(Consideration(
            pattern="Discrete pigmented lesion with no atypical surface feature "
                    "on this image",
            overlaps_with=[
                "benign melanocytic naevus",
                "seborrhoeic keratosis",
                "solar lentigo",
                "dermatofibroma",
            ],
            distinguished_by="Clinical examination including palpation. Note "
                             "that a bland appearance does NOT exclude nodular "
                             "or amelanotic melanoma.",
        ))

    if inflam >= 1.0:
        ctx.considerations.append(Consideration(
            pattern="Surrounding erythema / inflammation",
            overlaps_with=[
                "eczema or contact dermatitis",
                "psoriasis",
                "tinea (dermatophyte infection)",
                "actinic keratosis or Bowen's disease",
                "irritation from scratching or a dressing",
            ],
            distinguished_by="Distribution and scale pattern on examination, "
                             "skin scraping with mycology, and biopsy where a "
                             "fixed scaly plaque persists.",
        ))

    if not ctx.considerations:
        ctx.considerations.append(Consideration(
            pattern="No discrete lesion isolated on this image",
            overlaps_with=[
                "unremarkable skin",
                "a lesion with too little contrast against this skin tone or "
                "lighting to segment",
                "a lesion outside the photographed field",
            ],
            distinguished_by="Full skin examination. A negative image is not a "
                             "negative examination.",
        ))

    if grade in (Grade.REVIEW, Grade.URGENT):
        ctx.immediate_actions = [
            "Photograph again with a ruler or size sticker beside the lesion "
            "and store it with this case, so change over time is measurable.",
            "Do not pick, scratch, shave or apply any removal preparation to "
            "the lesion — it must be seen intact.",
            "Sun protection for the area.",
            "Bring the referral forward if it bleeds, ulcerates or grows.",
        ]
    else:
        ctx.immediate_actions = [
            "Advise monthly self-examination and re-imaging with a size marker.",
            "Sun protection; avoid sunbeds.",
            "Re-present promptly if it changes in any way.",
        ]
    return ctx


# --- face --------------------------------------------------------------------

def _face(grade: Grade, f: dict[str, Any]) -> ClinicalContext:
    lip_margin = float(f.get("lip_to_cheek_redness_margin", 0.0))
    blue_shift = float(f.get("lip_to_cheek_blue_shift", 0.0))
    sclera_b = f.get("sclera_yellowness")
    flush = float(f.get("cheek_to_forehead_redness", 0.0))

    ctx = ClinicalContext(
        severity_index=None,  # colour from a photograph does not earn a score
        scales={
            "measurement_basis": {
                "method": "Relative colour differences between facial regions "
                          "in CIE-Lab, plus the visible sclera as an in-frame "
                          "white reference.",
                "why": "Camera auto white-balance and the colour of the light "
                       "source shift absolute colour far more than illness "
                       "does. A difference between two regions of the same "
                       "photograph survives that; an absolute value does not.",
                "white_reference_available": f.get("white_reference_available"),
                "face_located_by": f.get("face_detector"),
            }
        },
        ask_and_check=[
            "SpO₂ by pulse oximeter, respiratory rate, heart rate, blood "
            "pressure, temperature and level of consciousness.",
            "Look at the TONGUE and inside the mouth: central cyanosis "
            "involves them, peripheral cyanosis does not. This distinction "
            "cannot be made from a photograph of closed lips.",
            "Is the patient breathless, confused, drowsy, or in pain?",
            "Conjunctivae, palmar creases and nail beds for pallor.",
            "For yellowing: urine and stool colour, itch, abdominal pain, "
            "alcohol history, medicines, recent travel.",
            "Are the hands and feet cold? Peripheral cyanosis from cold is "
            "common and benign.",
            "Any make-up, lipstick, food colouring or dye on the lips.",
        ],
        not_assessable=[
            "Oxygen saturation. This is not a pulse oximeter and no image can "
            "substitute for one.",
            "Haemoglobin concentration or the degree of anaemia.",
            "Serum bilirubin, or the cause of any jaundice.",
            "Whether cyanosis is central or peripheral — that needs the tongue.",
            "Stroke. Facial asymmetry is not assessed and a normal photograph "
            "does not exclude it; perform FAST in person.",
        ],
    )

    if blue_shift >= 10.0 and lip_margin <= 4.0:
        ctx.considerations.append(Consideration(
            pattern="Lips read blue relative to the cheek",
            overlaps_with=[
                "central cyanosis from hypoxaemia (respiratory or cardiac)",
                "peripheral cyanosis from cold or poor perfusion",
                "methaemoglobinaemia or another abnormal haemoglobin",
                "lipstick, dye, food colouring or make-up",
                "camera white balance, screen light or shade artefact",
            ],
            distinguished_by="Pulse oximetry now, examination of the tongue "
                             "(central cyanosis involves it, peripheral does "
                             "not), warming the patient, and arterial blood "
                             "gases where saturation is low or does not fit "
                             "the picture.",
        ))
    if isinstance(sclera_b, (int, float)) and sclera_b >= 14.0:
        ctx.considerations.append(Consideration(
            pattern="Visible sclera reads yellow against the in-frame white "
                    "reference",
            overlaps_with=[
                "jaundice — pre-hepatic (haemolysis)",
                "jaundice — hepatic (hepatitis, cirrhosis, drugs)",
                "jaundice — post-hepatic (biliary obstruction)",
                "scleral pigmentation, pinguecula or subconjunctival fat, "
                "which are normal variants",
                "warm or yellow artificial lighting",
            ],
            distinguished_by="Serum bilirubin split into conjugated and "
                             "unconjugated, liver function tests, full blood "
                             "count and reticulocytes, and liver ultrasound as "
                             "directed. Note that carotenaemia yellows the "
                             "skin but SPARES the sclera — that difference is "
                             "made on examination, not on a photograph.",
        ))
    if lip_margin <= 3.0 and blue_shift < 10.0:
        ctx.considerations.append(Consideration(
            pattern="Lips barely redder than the surrounding skin",
            overlaps_with=[
                "anaemia",
                "shock or hypovolaemia",
                "peripheral vasoconstriction from cold or pain",
                "hypoglycaemia",
                "normal variation, or lighting that washes out colour",
            ],
            distinguished_by="Full blood count, vital signs including blood "
                             "pressure and heart rate, capillary glucose, and "
                             "direct inspection of the conjunctivae, palmar "
                             "creases and nail beds — where pallor is actually "
                             "assessed.",
        ))
    if flush >= 10.0:
        ctx.considerations.append(Consideration(
            pattern="Cheeks read flushed relative to the forehead",
            overlaps_with=[
                "fever or recent exertion",
                "rosacea or another chronic facial dermatosis",
                "alcohol, or a drug or food reaction",
                "polycythaemia",
                "menopausal or carcinoid flushing",
            ],
            distinguished_by="Temperature, full blood count and haematocrit, "
                             "and the history — timing, triggers and duration "
                             "separate these.",
        ))
    if not ctx.considerations:
        ctx.considerations.append(Consideration(
            pattern="No colour flag on this image",
            overlaps_with=[
                "unremarkable facial colour",
                "illness present but not visible as a colour change",
                "a real colour change masked by lighting or white balance",
            ],
            distinguished_by="Vital signs including SpO₂. Facial colour is one "
                             "of the least reliable signs available, and a "
                             "normal photograph carries very little weight "
                             "against an unwell patient.",
        ))

    if grade is Grade.URGENT:
        ctx.immediate_actions = [
            "Measure SpO₂ with a pulse oximeter NOW, and record respiratory "
            "rate, heart rate and level of consciousness.",
            "Sit the patient upright and keep them warm and calm.",
            "Do not wait for or act on this image — escalate on the clinical "
            "picture.",
            "Call emergency services immediately if the patient is breathless "
            "at rest, confused, drowsy, has chest pain, or is deteriorating. "
            "Decisions about oxygen are for a clinician.",
        ]
    elif grade is Grade.REVIEW:
        ctx.immediate_actions = [
            "Record a full set of observations including SpO₂ and temperature.",
            "Assess conjunctivae, palms and nail beds directly.",
            "Re-image in even, indirect daylight before comparing over time.",
        ]
    else:
        ctx.immediate_actions = [
            "Record observations if the patient feels unwell, regardless of "
            "this result.",
            "Re-image in even, indirect daylight if colour is being followed.",
        ]
    return ctx


# --- eye ---------------------------------------------------------------------

def _eye(grade: Grade, f: dict[str, Any]) -> ClinicalContext:
    aniso = f.get("anisocoria_mm")
    pupils = f.get("pupils") or []
    red = float(f.get("red_fraction", 0.0))
    sclera_b = float(f.get("sclera_b_mean", 0.0))

    ctx = ClinicalContext(
        severity_index=(
            {
                "name": "Anisocoria",
                "value": round(float(aniso), 2),
                "unit": "mm difference between pupils",
                "band": ("within physiological range" if aniso < 0.5 else
                         "borderline" if aniso < 1.0 else "significant"),
                "components": {
                    "pupil_diameters_mm": [p["pupil_diameter_mm"] for p in pupils],
                    "iris_reference_mm": f.get("iris_reference_mm"),
                },
                "caveat": "Estimated by assuming an 11.7 mm iris, which varies "
                          "by about ±0.5 mm between people. Measured in ONE "
                          "lighting condition, which is the wrong test: what "
                          "matters is whether the difference grows in bright "
                          "or in dim light.",
            } if isinstance(aniso, (int, float)) else None
        ),
        scales={
            "pupil_measurement": {
                "method": "Pupil/iris ratio scaled by an assumed 11.7 mm "
                          "horizontal iris diameter.",
                "why_ratio": "The ratio is scale-free, so it survives unknown "
                             "camera distance and zoom. Only the conversion to "
                             "millimetres depends on the iris assumption.",
                "pupils_found": f.get("pupils_measured", 0),
                "reaction_to_light": "NOT ASSESSED — impossible from a still "
                                     "image.",
                "rapd_swinging_flashlight": "NOT ASSESSED — requires a torch "
                                            "and a clinician.",
            }
        },
        ask_and_check=[
            "Is there head injury, reduced consciousness, severe headache or "
            "vomiting? Unequal pupils with any of these is an EMERGENCY — call "
            "for help now.",
            "Is there a drooping eyelid (ptosis), double vision, or an eye that "
            "will not move fully? That combination needs immediate assessment.",
            "Does the difference between the pupils get BIGGER in bright light "
            "or in dim light? Bright — the larger pupil is the abnormal one. "
            "Dim — the smaller one is. This single test does most of the work "
            "and needs only a torch.",
            "Do the pupils react to light, and is there a relative afferent "
            "pupillary defect on the swinging-flashlight test?",
            "Any eye drops, nebulised medicines, patches, or plant sap on the "
            "hands? Pharmacological causes are common and easily missed.",
            "Old photographs of the patient — long-standing inequality that is "
            "unchanged is reassuring in a way a single image cannot be.",
            "Visual acuity in each eye, pain, photophobia, discharge, and "
            "contact lens use.",
        ],
        not_assessable=[
            "Whether the pupils react to light, and how briskly.",
            "Relative afferent pupillary defect.",
            "Whether the inequality is greater in bright or in dim light — the "
            "test that localises the problem.",
            "Visual acuity and intraocular pressure.",
            "The retina and optic nerve. A fundus camera or slit lamp is "
            "required.",
        ],
    )

    if isinstance(aniso, (int, float)) and aniso >= 0.5:
        ctx.considerations.append(Consideration(
            pattern=f"Pupils differ by {aniso:.1f} mm in this image",
            overlaps_with=[
                "physiological anisocoria — present in about one person in "
                "five, usually under 0.5 mm and equal in bright and dim light",
                "Horner syndrome — smaller pupil, with ptosis; worse in dim "
                "light",
                "third cranial nerve palsy — larger pupil, with ptosis and "
                "restricted eye movement; worse in bright light",
                "pharmacological — eye drops, nebulisers, scopolamine patches, "
                "plant alkaloids on the fingers",
                "previous eye surgery, trauma or iritis distorting the iris",
                "an artefact of unequal lighting on the two sides of the face, "
                "or of camera angle",
            ],
            distinguished_by="Comparing the pupils in bright and in dim light "
                             "with a torch, looking for ptosis and eye "
                             "movement restriction, and reviewing old "
                             "photographs. If there is head injury or reduced "
                             "consciousness, this is a neurosurgical emergency "
                             "and imaging is arranged immediately — do not "
                             "wait to work through this list.",
        ))
    if red >= 0.12:
        ctx.considerations.append(Consideration(
            pattern="Redness of the anterior ocular surface",
            overlaps_with=[
                "conjunctivitis — viral, bacterial or allergic",
                "subconjunctival haemorrhage",
                "episcleritis or scleritis",
                "acute anterior uveitis (iritis)",
                "keratitis or corneal ulcer, including contact-lens related",
                "acute angle-closure glaucoma",
                "dry eye or irritant exposure",
            ],
            distinguished_by="Slit-lamp examination with fluorescein, visual "
                             "acuity, and intraocular pressure. Pain, "
                             "photophobia and reduced acuity separate the "
                             "sight-threatening causes from the trivial ones, "
                             "and none of those three is visible in a "
                             "photograph.",
        ))
    if sclera_b >= 12.0:
        ctx.considerations.append(Consideration(
            pattern="Yellow tint to the visible sclera",
            overlaps_with=[
                "jaundice — pre-hepatic, hepatic or post-hepatic",
                "pinguecula or subconjunctival fat, which are normal variants",
                "scleral pigmentation, more visible in some individuals",
                "warm or yellow artificial lighting",
            ],
            distinguished_by="Serum bilirubin split into conjugated and "
                             "unconjugated, liver function tests and a full "
                             "blood count. Examining the sclera in daylight is "
                             "the first step; carotenaemia spares the sclera.",
        ))
    if not ctx.considerations:
        ctx.considerations.append(Consideration(
            pattern="No anterior-surface flag on this image",
            overlaps_with=[
                "an unremarkable anterior segment",
                "disease of the retina or optic nerve, which this image cannot "
                "reach at all",
                "a change too subtle for this resolution or lighting",
            ],
            distinguished_by="Slit-lamp examination and dilated fundoscopy, or "
                             "a fundus camera for retinal screening.",
        ))

    if grade is Grade.URGENT:
        ctx.immediate_actions = [
            "If there has been head injury, or the patient is drowsy, "
            "confused, vomiting or has severe headache, treat this as an "
            "emergency and call for help now.",
            "Check the pupils again with a torch in both bright and dim light "
            "and record what you see.",
            "Look for a drooping eyelid and test eye movements.",
            "Do not instil any eye drops before the eye is examined — they "
            "change the pupil and remove the sign.",
            "Protect the eye from bright light if the patient is photophobic.",
        ]
    elif grade is Grade.REVIEW:
        ctx.immediate_actions = [
            "Record pupil sizes in bright and in dim light with a torch.",
            "Ask about eye drops, patches and nebulised medicines.",
            "Do not instil any eye drops before assessment.",
            "Seek same-day advice if drooping eyelid, double vision, headache "
            "or reduced vision develops.",
        ]
    else:
        ctx.immediate_actions = [
            "No action from this image. Re-present if vision changes, the eye "
            "becomes painful, or the pupils become unequal.",
            "Retinal screening remains due on its own schedule.",
        ]
    return ctx


def build(module: str, grade: Grade, features: dict[str, Any],
          lesions: list[Lesion] | None = None) -> ClinicalContext | None:
    """Entry point. Returns None for modules without a clinical layer yet."""
    builders = {"foot": _foot, "skin": _skin, "face": _face, "eye": _eye}
    builder = builders.get(module)
    return builder(grade, features) if builder else None
