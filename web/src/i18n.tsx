import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export type Lang = 'en' | 'ar'

type Dict = Record<string, string>

const en: Dict = {
  'app.name': 'QADAM',
  'app.tagline': 'Surface screening and triage routing',
  'banner.device': 'NOT A MEDICAL DEVICE — not for clinical use.',
  'banner.disclaimer':
    'Research/decision-support tool — not a diagnosis. Not a substitute for clinical assessment.',
  'banner.human': 'A qualified clinician must confirm every clinically significant output.',

  'nav.new': 'New case',
  'nav.cases': 'Cases',
  'nav.emergency': 'Emergency',
  'nav.fairness': 'Fairness',
  'nav.signout': 'Sign out',
  'nav.language': 'العربية',

  'demo.title': 'Try QADAM',
  'demo.intro':
    'No account and no password. One click starts a private session, and everything you capture stays in it.',
  'demo.start': 'Start a demo session',
  'demo.starting': 'Starting…',
  'demo.privacy':
    'Your session is isolated: nobody else using this link can see your patients, cases or images — and you cannot see theirs.',
  'demo.noPatients':
    'Use test images only. Do not photograph a real patient. This is an unvalidated prototype on a public server, and anything captured here is lost when the server restarts.',
  'demo.haveAccount': 'Or sign in with an account',

  'login.title': 'Sign in',
  'login.email': 'Email',
  'login.password': 'Password',
  'login.submit': 'Sign in',
  'login.working': 'Signing in…',
  'login.role': 'Trained health worker access only.',
  'login.demoAccounts':
    'Local demo build — seeded accounts, click to sign in. These do not exist in a deployed instance.',

  'new.step.module': '1. Choose a module',
  'new.step.patient': '2. Patient record and consent',
  'new.step.capture': '3. Capture or upload',
  'new.step.result': '4. Result',
  'new.patient.ref': 'Patient reference (pseudonymous code)',
  'new.patient.refHint':
    'A site-local code only. Do not enter a name, an MRN, or any contact detail.',
  'new.patient.site': 'Body site',
  'new.patient.tone': 'Monk Skin Tone (optional, patient-declared)',
  'new.patient.toneHint':
    'Recorded only so performance can be reported per skin-tone group. It is never used as an analysis input.',
  'new.patient.consent': 'The patient has consented to their image being stored and analysed.',
  'new.patient.consentRequired': 'Consent is required before any image is stored.',
  'new.patient.create': 'Create / open record',
  'new.patient.ready': 'Record ready',
  'crop.title': 'Crop to the area being assessed',
  'crop.help': 'Drag a box around the area you are assessing.',
  'crop.tooSmall': 'That selection is too small to analyse. Drag a larger box, or use the whole image.',
  'crop.failed': 'The crop could not be produced. Use the whole image instead.',
  'crop.apply': 'Use this area',
  'crop.skip': 'Use the whole image',
  'crop.reopen': 'Crop',
  'crop.why':
    'Every measurement is a percentage of the segmented subject, so what else is in frame changes the numbers. Background that leaks in shifts the skin reference that every threshold is relative to, and a lesion filling 4% of a wide shot fills 30% of a tight one. Cropping is the single most effective thing you can do to make the result mean something.',
  'capture.blocked':
    'Capture is switched off until step 2 is complete. Enter the patient reference above, tick the consent box, and press "Create / open record" — no image may be taken or stored before consent is recorded.',
  'capture.preparing': 'Preparing the image…',
  'capture.prepared': 'Resized for upload',
  'diag.open': 'Camera not working? Run a check',
  'diag.origin': 'Address',
  'diag.secure': 'Secure context',
  'diag.permission': 'Camera permission',
  'diag.api': 'Camera API available',
  'diag.devices': 'Cameras found',
  'diag.lastTest': 'Last test result',
  'diag.test': 'Test the camera now',
  'diag.testing': 'Testing…',
  'diag.copy': 'Copy this report',
  'diag.fixInsecure':
    'The address is not a secure context, so the browser has removed the camera API entirely. Open the app over HTTPS or on localhost. This is the usual cause when a phone is opened on an http://192.168.x.x address.',
  'diag.fixNoApi':
    'This browser does not expose a camera API here. Use the "Take photo (device camera app)" button instead — it needs no permission.',
  'diag.fixDenied':
    'Camera access is BLOCKED for this address. Click the camera or lock icon in the address bar, set Camera to Allow, then reload. On a phone also check the browser app itself has camera permission in system settings.',
  'diag.fixNoDevice':
    'No camera was found on this device. Use "Take photo (device camera app)" or upload an image taken elsewhere.',
  'diag.fixBusy':
    'The camera is in use by another application. Close any video call or camera app and test again.',
  'diag.fixPrompt':
    'Permission has not been asked for yet. Press "Test the camera now" and accept the prompt.',
  'diag.fixUnknown':
    'The camera failed for a reason this check could not classify. Copy the report and send it on — the "Last test result" line names the exact browser error.',
  'diag.fixNone':
    'Everything needed is present. If capture still fails, press "Test the camera now" and read the result line.',
  'camera.starting': 'Starting camera…',
  'camera.denied':
    'Camera access is blocked for this site. Click the camera or lock icon in the browser address bar, set Camera to Allow, then press "Use camera" again. On a phone, also check the browser app has camera permission in system settings.',
  'camera.notFound':
    'No camera was found on this device.',
  'camera.busy':
    'The camera is already in use by another application. Close the other app — video call, camera app — and try again.',
  'camera.insecure':
    'The camera only works over HTTPS or on localhost. You appear to be on a plain http:// address, so the browser has disabled it. Open the app via localhost or an HTTPS address, or upload an image instead.',
  'camera.failed': 'The camera could not be started.',
  'camera.notReady':
    'The camera has not produced a picture yet. Wait a moment for the preview to appear, then press Capture again — or use the device camera app below, which always works.',
  'camera.fellBack':
    'The device camera app was opened instead — it needs no permission and captures at full resolution. Nothing is lost.',
  'camera.uploadInstead':
    'You can still upload a photo taken with the device camera app — the analysis is identical.',
  'new.capture.camera': 'Live preview instead',
  'new.capture.stop': 'Stop camera',
  'new.capture.shoot': 'Capture',
  'new.capture.deviceCamera': 'Take photo',
  'new.capture.upload': 'Upload an image',
  'new.capture.retake': 'Retake',
  'new.capture.analyze': 'Analyse',
  'new.capture.analysing': 'Analysing…',
  'new.guidance.title': 'Capture guidance',
  'new.guidance.distance': 'Hold the camera 20–30 cm from the area and tap to focus.',
  'new.guidance.framing': 'Fill about half the frame with the area of interest.',
  'new.guidance.light': 'Use even, indirect light. Avoid flash, glare and shadows.',
  'new.guidance.background': 'Use a plain background and keep the camera steady.',
  'new.guidance.scale': 'Include a size marker where possible for comparison over time.',

  'offline.offline': 'No connection — working offline',
  'offline.online': 'Connected',
  'offline.queued': 'item(s) waiting to send',
  'offline.showQueue': 'Show what is waiting',
  'offline.syncNow': 'Send now',
  'offline.syncing': 'Sending…',
  'offline.notAnalysed':
    'Queued captures have NOT been analysed — the analysis runs on the server. A waiting item has no triage grade, and no grade is not the same as no flag. Act on your own clinical judgement; do not wait for this to send.',
  'offline.failed':
    'An item was rejected by the server and everything after it is held back, because later items depend on it. Open the queue to see why.',
  'offline.stopped': 'Sending stopped',
  'offline.failedItem': 'rejected',
  'offline.discard': 'Discard everything waiting',
  'offline.discardConfirm': 'This permanently deletes the captures and findings waiting on this device. ',
  'offline.discardYes': 'Yes, delete them',
  'offline.discardNo': 'Cancel',
  'offline.queuedCapture': 'Saved on this device — not yet sent or analysed',
  'offline.willQueue':
    'No connection. This will be saved on this device and sent when you are back online.',
  'foot.title': 'Diabetic foot risk assessment (IWGDF)',
  'foot.intro':
    'Structured examination, not image analysis. Loss of protective sensation, arterial disease, deformity and history are what set the risk category and the screening interval — and none of them is visible in a photograph.',
  'foot.none': 'No foot risk assessment recorded for this case yet.',
  'foot.record': 'Record foot examination',
  'foot.side': 'Foot',
  'foot.lops': 'Loss of protective sensation (10 g monofilament)',
  'foot.pad': 'Peripheral artery disease (pulses / ankle or toe pressures)',
  'foot.deformity': 'Foot deformity',
  'foot.previousUlcer': 'Previous foot ulcer',
  'foot.previousAmputation': 'Previous lower-extremity amputation',
  'foot.esrd': 'End-stage renal disease / dialysis',
  'foot.requiredTest': 'required for stratification',
  'foot.finding.present': 'Present',
  'foot.finding.absent': 'Absent (tested)',
  'foot.finding.not_tested': 'Not tested',
  'foot.willNotStratify':
    'No risk category will be produced, because these required tests are marked as not performed:',
  'foot.save': 'Save assessment',
  'foot.saving': 'Saving…',
  'foot.category': 'IWGDF category',
  'foot.notStratified': 'Not stratified',
  'foot.incompleteTitle': 'No category was produced. An absent test is not a negative test.',
  'foot.nextScreening': 'Next screening',
  'foot.interval': 'Interval',
  'inv.title': 'Investigation results',
  'inv.notInterpreted':
    'STORED, NOT INTERPRETED. QADAM has not read these documents and has produced no finding, grade or opinion from them. They are filed here so the clinician who ordered the investigation sees the result next to the referral that prompted it.',
  'inv.closesLoop':
    'Reading a radiology study needs the whole study, the clinical context, prior imaging and a trained reporter. This platform has none of those, so it files the result rather than pretending to read it.',
  'inv.none': 'No results filed against this case yet.',
  'inv.add': 'File a result',
  'inv.category': 'Category',
  'inv.modality': 'Modality',
  'inv.bodySite': 'Body site',
  'inv.service': 'Reporting service',
  'inv.serviceHint': 'The department or service — not a named individual.',
  'inv.reportText': 'Report text',
  'inv.file': 'Document (PDF, JPEG, PNG, WebP or text)',
  'inv.fileHint':
    'DICOM is not accepted: its headers carry the patient name, date of birth and accession number, which would break the pseudonymity of this record. Export a de-identified PDF or image from the PACS instead.',
  'inv.ack':
    'I confirm identifiers have been removed or covered. Reports and screenshots routinely show the patient name, date of birth and accession number, and this platform stores pseudonymous records only.',
  'inv.save': 'File result',
  'inv.saving': 'Filing…',
  'inv.openFile': 'Open document',
  'lab.panelName': 'Panel name (optional)',
  'lab.age': 'Age',
  'lab.sex': 'Sex',
  'lab.ageHint':
    'Age and sex are used for sex-specific reference ranges and for eGFR and FIB-4. Left blank, they are taken from the patient record; those indices are simply not produced if age is unknown.',
  'lab.addAnalyte': 'Add an analyte',
  'lab.choose': 'Choose…',
  'lab.noRows': 'No analytes added yet. Pick one above.',
  'lab.reference': 'Reference',
  'lab.save': 'Save and interpret',
  'lab.saving': 'Saving…',
  'lab.results': 'Results',
  'lab.analyte': 'Analyte',
  'lab.value': 'Value',
  'lab.flag': 'Flag',
  'lab.asEntered': 'As entered',
  'lab.critical': 'critical',
  'lab.notFlagged': 'not flagged',
  'lab.analytes': 'analytes',
  'lab.flagged': 'flagged',
  'lab.derived': 'Derived indices',
  'lab.unrecognised': 'Stored but not interpreted',
  'lab.addPanel': 'Add laboratory results',
  'lab.needCase': 'Create the patient record above first.',
  'lab.panels': 'Laboratory panels',
  'lab.noPanels': 'No laboratory results attached to this case yet.',
  'lab.attachHint':
    'Results can be attached to any case, so an imaging case that routed to bloods can hold what came back.',
  'emergency.whyStatic': 'Why this page shows nothing about your patient',
  'emergency.moveOnlyIf': 'Move them ONLY if',
  'clinical.title': 'Clinical considerations for the reviewing clinician',
  'clinical.considerations': 'What this pattern is compatible with',
  'clinical.overlapsWith': 'This pattern overlaps with all of these:',
  'clinical.distinguishedBy': 'Distinguished by',
  'clinical.immediateActions': 'Immediate protective steps, pending review',
  'clinical.immediateActionsNote':
    'Protective measures only, to be taken while the referral is arranged. No medication or procedure is recommended, and these do not replace the clinician’s plan.',
  'clinical.askAndCheck': 'Ask and examine — these are not in the result',
  'clinical.askAndCheckNote':
    'These often matter more than the image. Record the answers with the case.',
  'clinical.notAssessable': 'Not assessable from what was supplied',

  'followUp.title': 'Answers the camera cannot give',
  'followUp.intro':
    'These are the findings that decide the case and that no photograph contains. Answer what you actually examined; leave the rest blank.',
  'followUp.rule':
    'Answers can raise the urgency of this case. They never lower it — a measured image flag is not withdrawn because a test was reported as normal.',
  'followUp.notes': 'Clinical notes',
  'followUp.notesHint':
    'Free text. Stored and shown exactly as written, and included in the PDF. It is never parsed, scored, or used as an input to any model.',
  'followUp.notesPlaceholder':
    'History, examination findings, what you have already done, what you are asking the reviewing clinician…',
  'followUp.submit': 'Save and re-assess',
  'followUp.saving': 'Re-assessing…',
  'followUp.reset': 'Clear answers',
  'followUp.open': 'Answer follow-up questions',
  'followUp.why': 'Why this is asked',
  'followUp.answered': 'answered',
  'followUp.unanswered': 'not answered',
  'followUp.imageGrade': 'From the image',
  'followUp.answerGrade': 'From your answers',
  'followUp.combined': 'Combined grade',
  'followUp.escalated': 'Escalated by your answers',
  'followUp.notEscalated': 'Your answers did not raise the grade.',
  'followUp.triggers': 'What your answers raised',
  'followUp.because': 'Why it matters',
  'followUp.consider': 'Consider',
  'followUp.distinguishedBy': 'Distinguished by',
  'followUp.history': 'Previous follow-up entries',
  'followUp.recordedBy': 'Recorded',
  'followUp.noEntries': 'No follow-up answers have been recorded for this case.',
  'followUp.emptyAnswers':
    'Answer at least one question, or write a note, before saving.',
  'followUp.queued':
    'No connection — your answers are saved on this device and will be sent when you reconnect. The re-assessment runs on the server, so no combined grade is shown yet.',
  'followUp.blank': '—',
  'followUp.opt.yes': 'Yes',
  'followUp.opt.no': 'No',
  'followUp.opt.unknown': 'Not known',
  'followUp.opt.not_tested': 'Not tested',
  'followUp.opt.not_applicable': 'Not applicable',
  'followUp.opt.both_palpable': 'Both palpable',
  'followUp.opt.one_absent': 'One absent',
  'followUp.opt.both_absent': 'Both absent',
  'followUp.opt.intact': 'Intact',
  'followUp.opt.reduced': 'Reduced',
  'followUp.opt.absent': 'Absent',

  'calib.title': 'Colour reference',
  'calib.applied': 'Calibrated against a reference card',
  'calib.notDetected': 'No reference card in this image',
  'calib.unusable': 'Reference card found but not usable',
  'calib.shift': 'Illuminant shift corrected',
  'calib.howTo': 'How to use a reference card',
  'calib.why':
    'Colour in a phone photograph is set more by the light in the room than by the patient. A neutral grey or white card in the frame makes today’s image comparable with last week’s.',

  'delete.title': 'Delete this case',
  'delete.warn':
    'This permanently destroys the images and every assessment derived from them. There is no recycle bin and this cannot be undone.',
  'delete.keeps':
    'The pseudonymous patient record is kept, and so is the audit entry recording that this case was deleted. Neither holds a patient identifier or any clinical content.',
  'delete.button': 'Delete case',
  'delete.confirmPrompt': 'Type DELETE to confirm',
  'delete.confirmWord': 'DELETE',
  'delete.confirm': 'Permanently delete',
  'delete.cancel': 'Cancel',
  'delete.working': 'Deleting…',
  'delete.done': 'Case deleted.',
  'delete.removed': 'Removed',

  'routing.notAssessed': 'Not assessed',
  'routing.missing': 'What is missing',
  'routing.basis': 'What this decision rests on',
  'routing.source.iwgdf_risk_category': 'Foot examination (IWGDF risk category)',
  'routing.source.follow_up_answers': 'Clinician follow-up answers',
  'case.photoRecord': 'The photograph — record, not decision',
  'case.photoRecordHint':
    'What the camera measured, kept so the wound can be compared over time. It is not the routing decision above and takes no part in it.',
  'result.observationOnly': 'OBSERVED IN THE PHOTOGRAPH — NOT THE ROUTING DECISION',
  'result.imageOnly': 'What the image alone would suggest',
  'result.imageOnlyHint':
    'Shown for completeness only. The case is routed on the examination and the answers, not on this.',
  'followUp.imageObserved': 'Photograph observed',
  'followUp.triggered': 'These answers raised a red flag',
  'followUp.noTrigger': 'These answers raised no red flag.',

  'progress.title': 'Is the wound closing?',
  'progress.intro':
    'Area measured in cm² against a card of known size, across visits. Only photographs that carried a size reference are compared — a percentage of the frame changes when the camera moves and the wound does not.',
  'progress.notEnough': 'Not enough calibrated measurements to compare yet.',
  'progress.change': 'Area reduction',
  'progress.absolute': 'Absolute change',
  'progress.over': 'Over',
  'progress.days': 'days',
  'progress.excluded': 'Photographs that could not be compared',

  'labUpload.title': 'Upload the laboratory report',
  'labUpload.storedNotRead':
    'Stored, never read. No value is extracted from this document and no grade comes out of it — the interpretation above works on the numbers you type, with the unit stated. It is filed here so the referral carries its source and a reviewer can check the typed values against the original.',
  'labUpload.choose': 'Choose a PDF or photo',
  'labUpload.service': 'Reporting laboratory (optional)',
  'labUpload.servicePlaceholder': 'e.g. Central Laboratory',
  'labUpload.serviceHint': 'The service, never a named person.',
  'labUpload.ack':
    'I have removed the patient’s name, date of birth and any other identifier from this document. A laboratory printout normally carries them across the top, and this record is pseudonymous.',
  'labUpload.file': 'File the report',
  'labUpload.filing': 'Filing…',
  'labUpload.filed': 'Report filed against this case.',

  'clarify.title': 'Worth asking before anything else',
  'clarify.intro':
    'One or two questions chosen from what this image actually showed. Each names what its answer would settle — the point is an experiment with a result, not advice.',
  'clarify.settles': 'What the answer settles',

  'evidence.title': 'What the photograph shows, and what it cannot',
  'evidence.observed': 'Observed in the image',
  'evidence.observedHint':
    'A description of pixels. None of these is a diagnosis, and none names a disease.',
  'evidence.cannot': 'Not determinable from a photograph',
  'evidence.cannotHint':
    'These require hands, instruments or imaging. Nothing below was assessed, and no result on this page implies otherwise.',
  'evidence.means': 'What this result means',
  'evidence.ceiling': 'Most urgent grade the visual evidence supports',
  'evidence.capped':
    'The measured areas crossed a higher threshold, but the visual evidence did not support it. The grade shown was lowered to what the evidence carries — the reasons are listed in the rationale below.',
  'evidence.limits': 'Why the evidence does not carry more',
  'evidence.appearance.no_significant_visual_abnormality': 'No significant visual abnormality detected',
  'evidence.appearance.potentially_abnormal_appearance': 'Potentially abnormal appearance',
  'evidence.appearance.insufficient_image_quality': 'Insufficient image quality for reliable visual assessment',
  'evidence.params':
    'Configurable research parameters — not clinically validated thresholds',

  // Collapsible summaries — used to hide long detail behind a toggle rather
  // than remove it. The detail is one tap away; nothing is deleted.
  'result.aboutScore': 'About this score',
  'clinical.moreDetail': 'Clinical detail — differentials, what to ask and examine',
  'result.moreLimits': 'More on what a photograph cannot assess',

  'feedback.title': 'Was this right?',
  'feedback.intro':
    'Every real defect this platform has had was found by someone looking at a real photograph — never by its tests. If it got this wrong, saying so here is the most useful thing you can do with it.',
  'feedback.groundTruth': 'What was actually there?',
  'feedback.groundTruthHint':
    'Optional, but it is what turns a complaint into a measurement.',
  'feedback.notePlaceholder': 'Anything that would help — what you saw, what it missed…',
  'feedback.send': 'Send',
  'feedback.sending': 'Sending…',
  'feedback.thanks': 'Recorded. Thank you — this is how the thresholds get fixed.',
  'feedback.previous': 'Previously recorded',

  'result.triage': 'Triage',
  // NOT "Confidence". The number is an uncalibrated distance-from-boundary
  // heuristic, not a probability — there is no clinical calibration behind it,
  // and "confidence 55%" reads as "55% sure", which is a claim this platform
  // cannot make. See app/analysis/evidence.py and _conf() in classical.py.
  'result.confidence': 'Evidence strength (uncalibrated)',
  'result.distance': 'Evidence strength (uncalibrated)',
  'result.evidenceStrengthHint':
    'A heuristic score, not a probability. It reflects how far the measurement sits from a decision threshold, discounted by image quality — it is NOT calibrated against clinical outcomes and must not be read as a percentage chance of anything.',
  'result.noFlagMeaning':
    'No surface feature was detected — that is all this means. It is not a measure of how healthy the foot is, and it does not exclude ischaemia, neuropathy, infection or anything beneath the skin.',
  'result.nextStep': 'Recommended next step',
  'result.routeTo': 'Route to',
  'result.timeframe': 'Timeframe',
  'result.findings': 'Detected surface features',
  'result.noFindings': 'No discrete surface finding was isolated in this image.',
  'result.rationale': 'Basis for this grade',
  'result.quality': 'Image quality',
  'result.limitations': 'Not assessed / limitations',
  'result.overlay': 'Annotated image',
  'result.pdf': 'Download clinician summary (PDF)',
  'result.summary': 'Clinician summary',
  'result.model': 'Model',
  'result.newCase': 'Start another case',
  'result.openCase': 'Open case',
  'result.area': 'Area',
  'result.severity': 'Severity',

  'quality.rejected': 'Image rejected — please re-capture',
  'quality.passed': 'Passed',
  'quality.degraded': 'Degraded',
  'quality.check.resolution': 'Resolution',
  'quality.check.focus': 'Focus',
  'quality.check.exposure': 'Exposure',
  'quality.check.subject_present': 'Subject in frame',
  'quality.measured': 'Measured',
  'quality.threshold': 'Threshold',

  'cases.title': 'Cases',
  'cases.module': 'Module',
  'cases.grade': 'Grade',
  'cases.patient': 'Patient reference',
  'cases.created': 'Created',
  'cases.status': 'Status',
  'cases.analyses': 'Analyses',
  'cases.none': 'No cases match these filters.',
  'cases.all': 'All',
  'cases.filter': 'Filter',

  'case.title': 'Case',
  'case.latest': 'Latest analysis',
  'case.history': 'Earlier analyses',
  'case.compare': 'Compare over time',
  'case.compareHint':
    'Side-by-side comparison of the same case. Differences may reflect the condition, the lighting, or the framing — a clinician decides which.',
  'case.noHistory': 'No earlier analysis to compare against yet.',
  'case.back': 'Back to cases',

  'fairness.title': 'Fairness (placeholder)',
  'fairness.group': 'Monk Skin Tone group',
  'fairness.analyses': 'Analyses',
  'fairness.meanConfidence': 'Mean evidence strength (uncalibrated)',
  'fairness.qualityPass': 'Quality pass rate',
  'fairness.coverage': 'Skin tone recorded for',
  'fairness.ofAnalyses': 'of analyses',

  'common.loading': 'Loading…',
  'common.error': 'Something went wrong',
  'common.hint': 'What to do',
  'common.close': 'Close',
  'common.required': 'required',
  'common.notRecorded': 'not recorded',
  'common.intendedUse': 'Intended use',
}

const ar: Dict = {
  'app.name': 'قَدَم',
  'app.tagline': 'فحص سطحي وتوجيه الفرز',
  'banner.device': 'ليس جهازاً طبياً — غير مخصص للاستخدام السريري.',
  'banner.disclaimer':
    'أداة بحثية لدعم القرار — ليست تشخيصاً. ولا تُغني عن التقييم السريري.',
  'banner.human': 'يجب أن يؤكد طبيب مؤهل كل نتيجة ذات دلالة سريرية.',

  'nav.new': 'حالة جديدة',
  'nav.cases': 'الحالات',
  'nav.emergency': 'الطوارئ',
  'nav.fairness': 'الإنصاف',
  'nav.signout': 'تسجيل الخروج',
  'nav.language': 'English',

  'demo.title': 'QADAM را امتحان کنید',
  'demo.intro':
    'بدون حساب و بدون رمز. یک کلیک یک نشست خصوصی می‌سازد و هرچه ثبت کنید در همان می‌ماند.',
  'demo.start': 'شروع نشست دمو',
  'demo.starting': 'در حال شروع…',
  'demo.privacy':
    'نشست شما جداست: هیچ‌کس دیگری که این لینک را دارد بیماران، کیس‌ها یا تصاویر شما را نمی‌بیند — و شما هم مال آن‌ها را نمی‌بینید.',
  'demo.noPatients':
    'فقط از تصاویر آزمایشی استفاده کنید. از بیمار واقعی عکس نگیرید. این یک نمونهٔ اولیهٔ اعتبارسنجی‌نشده روی سرور عمومی است و هرچه اینجا ثبت شود با راه‌اندازی مجدد سرور از بین می‌رود.',
  'demo.haveAccount': 'یا با یک حساب وارد شوید',

  'login.title': 'تسجيل الدخول',
  'login.email': 'البريد الإلكتروني',
  'login.password': 'كلمة المرور',
  'login.submit': 'دخول',
  'login.working': 'جارٍ الدخول…',
  'login.role': 'مخصص للكوادر الصحية المدرَّبة فقط.',
  'login.demoAccounts':
    'نسخة تجريبية محلية — حسابات تجريبية، اضغط للدخول. لا وجود لها في أي نسخة منشورة.',

  'new.step.module': '١. اختر الوحدة',
  'new.step.patient': '٢. سجل المريض والموافقة',
  'new.step.capture': '٣. التقاط أو رفع صورة',
  'new.step.result': '٤. النتيجة',
  'new.patient.ref': 'رمز المريض (رمز مستعار)',
  'new.patient.refHint': 'رمز محلي فقط. لا تُدخل اسماً أو رقم ملف أو بيانات تواصل.',
  'new.patient.site': 'موضع الجسم',
  'new.patient.tone': 'مقياس مونك للون البشرة (اختياري، بإفادة المريض)',
  'new.patient.toneHint':
    'يُسجَّل فقط لعرض الأداء لكل فئة لون بشرة. لا يُستخدم أبداً كمدخل للتحليل.',
  'new.patient.consent': 'وافق المريض على تخزين صورته وتحليلها.',
  'new.patient.consentRequired': 'الموافقة مطلوبة قبل تخزين أي صورة.',
  'new.patient.create': 'إنشاء / فتح السجل',
  'new.patient.ready': 'السجل جاهز',
  'crop.title': 'اقتصاص المنطقة المراد تقييمها',
  'crop.help': 'اسحب مربعاً حول المنطقة التي تقيّمها.',
  'crop.tooSmall': 'هذا التحديد صغير جداً للتحليل. اسحب مربعاً أكبر، أو استخدم الصورة كاملة.',
  'crop.failed': 'تعذّر إنشاء الاقتصاص. استخدم الصورة كاملة.',
  'crop.apply': 'استخدم هذه المنطقة',
  'crop.skip': 'استخدم الصورة كاملة',
  'crop.reopen': 'اقتصاص',
  'crop.why':
    'كل قياس هو نسبة من الهدف المقتطع، لذا فإن ما يوجد في الإطار يغيّر الأرقام. الخلفية المتسربة تزيح مرجع الجلد الذي تُقاس عليه كل العتبات، وآفة تملأ ٤٪ من لقطة واسعة تملأ ٣٠٪ من لقطة قريبة. الاقتصاص أكثر ما يمكنك فعله لجعل النتيجة ذات معنى.',
  'capture.blocked':
    'الالتقاط معطَّل حتى تكتمل الخطوة ٢. أدخل رمز المريض أعلاه، وحدّد مربع الموافقة، ثم اضغط «إنشاء / فتح السجل» — لا يجوز التقاط أو تخزين أي صورة قبل تسجيل الموافقة.',
  'capture.preparing': 'جارٍ تجهيز الصورة…',
  'capture.prepared': 'تم تصغيرها للرفع',
  'diag.open': 'الكاميرا لا تعمل؟ شغّل فحصاً',
  'diag.origin': 'العنوان',
  'diag.secure': 'سياق آمن',
  'diag.permission': 'إذن الكاميرا',
  'diag.api': 'واجهة الكاميرا متاحة',
  'diag.devices': 'الكاميرات المكتشفة',
  'diag.lastTest': 'نتيجة آخر اختبار',
  'diag.test': 'اختبر الكاميرا الآن',
  'diag.testing': 'جارٍ الاختبار…',
  'diag.copy': 'انسخ هذا التقرير',
  'diag.fixInsecure':
    'العنوان ليس سياقاً آمناً، لذا أزال المتصفح واجهة الكاميرا بالكامل. افتح التطبيق عبر HTTPS أو على localhost. هذا هو السبب المعتاد عند فتح الهاتف على عنوان http://192.168.x.x.',
  'diag.fixNoApi':
    'هذا المتصفح لا يوفّر واجهة كاميرا هنا. استخدم زر «التقاط صورة (تطبيق كاميرا الجهاز)» — لا يحتاج إذناً.',
  'diag.fixDenied':
    'الوصول إلى الكاميرا محظور لهذا العنوان. اضغط أيقونة الكاميرا أو القفل في شريط العنوان، واضبطها على «السماح»، ثم أعد التحميل. على الهاتف تحقق أيضاً من صلاحية الكاميرا للمتصفح في إعدادات النظام.',
  'diag.fixNoDevice':
    'لم يتم العثور على كاميرا في هذا الجهاز. استخدم «التقاط صورة (تطبيق كاميرا الجهاز)» أو ارفع صورة.',
  'diag.fixBusy':
    'الكاميرا مستخدمة من تطبيق آخر. أغلق أي مكالمة فيديو أو تطبيق كاميرا ثم أعد الاختبار.',
  'diag.fixPrompt':
    'لم يُطلب الإذن بعد. اضغط «اختبر الكاميرا الآن» واقبل الطلب.',
  'diag.fixUnknown':
    'فشلت الكاميرا لسبب لم يستطع هذا الفحص تصنيفه. انسخ التقرير وأرسله — سطر «نتيجة آخر اختبار» يذكر خطأ المتصفح بدقة.',
  'diag.fixNone':
    'كل ما يلزم متوفر. إذا استمر الفشل، اضغط «اختبر الكاميرا الآن» واقرأ سطر النتيجة.',
  'camera.starting': 'جارٍ تشغيل الكاميرا…',
  'camera.denied':
    'الوصول إلى الكاميرا محظور لهذا الموقع. اضغط على أيقونة الكاميرا أو القفل في شريط العنوان، واضبط الكاميرا على «السماح»، ثم اضغط «استخدام الكاميرا» مرة أخرى. على الهاتف، تحقق أيضاً من صلاحية الكاميرا للمتصفح في إعدادات النظام.',
  'camera.notFound': 'لم يتم العثور على كاميرا في هذا الجهاز.',
  'camera.busy':
    'الكاميرا مستخدمة من تطبيق آخر. أغلق التطبيق الآخر — مكالمة فيديو أو تطبيق الكاميرا — ثم أعد المحاولة.',
  'camera.insecure':
    'تعمل الكاميرا فقط عبر HTTPS أو على localhost. يبدو أنك على عنوان http:// عادي، لذا عطّلها المتصفح. افتح التطبيق عبر localhost أو عنوان HTTPS، أو ارفع صورة بدلاً من ذلك.',
  'camera.failed': 'تعذّر تشغيل الكاميرا.',
  'camera.notReady':
    'لم تُنتج الكاميرا صورة بعد. انتظر قليلاً حتى تظهر المعاينة ثم اضغط «التقاط» مرة أخرى — أو استخدم كاميرا الجهاز أدناه، فهي تعمل دائماً.',
  'camera.fellBack':
    'فُتحت كاميرا الجهاز بدلاً من ذلك — لا تحتاج إذناً وتلتقط بأعلى دقة. لم يُفقد شيء.',
  'camera.uploadInstead':
    'ما زال بإمكانك رفع صورة التقطتها بتطبيق الكاميرا — التحليل مطابق تماماً.',
  'new.capture.camera': 'معاينة مباشرة بدلاً من ذلك',
  'new.capture.stop': 'إيقاف الكاميرا',
  'new.capture.shoot': 'التقاط',
  'new.capture.deviceCamera': 'التقاط صورة',
  'new.capture.upload': 'رفع صورة',
  'new.capture.retake': 'إعادة الالتقاط',
  'new.capture.analyze': 'تحليل',
  'new.capture.analysing': 'جارٍ التحليل…',
  'new.guidance.title': 'إرشادات الالتقاط',
  'new.guidance.distance': 'أمسك الكاميرا على بعد ٢٠–٣٠ سم وانقر لضبط التركيز.',
  'new.guidance.framing': 'اجعل المنطقة المطلوبة تملأ نصف الإطار تقريباً.',
  'new.guidance.light': 'استخدم إضاءة متساوية غير مباشرة. تجنّب الفلاش والوهج والظلال.',
  'new.guidance.background': 'استخدم خلفية سادة وثبّت الكاميرا.',
  'new.guidance.scale': 'أضف مقياس حجم عند الإمكان للمقارنة عبر الزمن.',

  'offline.offline': 'لا يوجد اتصال — العمل دون إنترنت',
  'offline.online': 'متصل',
  'offline.queued': 'عنصر بانتظار الإرسال',
  'offline.showQueue': 'عرض ما ينتظر',
  'offline.syncNow': 'أرسل الآن',
  'offline.syncing': 'جارٍ الإرسال…',
  'offline.notAnalysed':
    'الصور المنتظِرة لم تُحلَّل — التحليل يجري على الخادم. العنصر المنتظِر لا يحمل درجة فرز، وغياب الدرجة ليس كغياب العلامة. اعمل بحكمك السريري ولا تنتظر الإرسال.',
  'offline.failed':
    'رُفض عنصر من الخادم، وأُوقف كل ما بعده لأن العناصر اللاحقة تعتمد عليه. افتح القائمة لمعرفة السبب.',
  'offline.stopped': 'توقف الإرسال',
  'offline.failedItem': 'مرفوض',
  'offline.discard': 'حذف كل ما ينتظر',
  'offline.discardConfirm': 'سيحذف هذا نهائياً الصور والنتائج المنتظِرة على هذا الجهاز. ',
  'offline.discardYes': 'نعم، احذفها',
  'offline.discardNo': 'إلغاء',
  'offline.queuedCapture': 'محفوظ على هذا الجهاز — لم يُرسل ولم يُحلَّل بعد',
  'offline.willQueue':
    'لا يوجد اتصال. سيُحفظ هذا على الجهاز ويُرسل عند عودة الاتصال.',
  'foot.title': 'تقييم خطورة القدم السكرية (IWGDF)',
  'foot.intro':
    'فحص منظَّم، لا تحليل صورة. فقدان الإحساس الواقي ومرض الشرايين والتشوه والتاريخ المرضي هي ما يحدد فئة الخطورة وفترة الفحص — ولا يظهر أي منها في صورة.',
  'foot.none': 'لم يُسجَّل تقييم خطورة للقدم في هذه الحالة بعد.',
  'foot.record': 'تسجيل فحص القدم',
  'foot.side': 'القدم',
  'foot.lops': 'فقدان الإحساس الواقي (مونوفيلامنت ١٠ غ)',
  'foot.pad': 'مرض الشرايين المحيطية (النبض / ضغط الكاحل أو الإصبع)',
  'foot.deformity': 'تشوه القدم',
  'foot.previousUlcer': 'قرحة قدم سابقة',
  'foot.previousAmputation': 'بتر سابق في الطرف السفلي',
  'foot.esrd': 'مرض كلوي بمرحلة نهائية / غسيل كلوي',
  'foot.requiredTest': 'مطلوب للتصنيف',
  'foot.finding.present': 'موجود',
  'foot.finding.absent': 'غير موجود (تم الفحص)',
  'foot.finding.not_tested': 'لم يُفحص',
  'foot.willNotStratify':
    'لن تُنتَج فئة خطورة، لأن هذه الفحوص المطلوبة مُعلَّمة كغير مُنفَّذة:',
  'foot.save': 'حفظ التقييم',
  'foot.saving': 'جارٍ الحفظ…',
  'foot.category': 'فئة IWGDF',
  'foot.notStratified': 'غير مُصنَّف',
  'foot.incompleteTitle': 'لم تُنتَج أي فئة. الفحص غير المُنفَّذ ليس فحصاً سلبياً.',
  'foot.nextScreening': 'الفحص القادم',
  'foot.interval': 'الفترة',
  'inv.title': 'نتائج الفحوصات',
  'inv.notInterpreted':
    'مخزَّن، غير مُفسَّر. لم يقرأ قَدَم هذه المستندات ولم يُنتج منها أي نتيجة أو درجة أو رأي. تُحفظ هنا ليرى الطبيب الذي طلب الفحص النتيجة بجوار الإحالة التي أدت إليها.',
  'inv.closesLoop':
    'قراءة دراسة أشعة تتطلب الدراسة كاملة والسياق السريري والصور السابقة ومختصاً مدرَّباً. لا تملك هذه المنصة أياً منها، لذا تحفظ النتيجة بدل ادعاء قراءتها.',
  'inv.none': 'لا توجد نتائج محفوظة لهذه الحالة بعد.',
  'inv.add': 'حفظ نتيجة',
  'inv.category': 'الفئة',
  'inv.modality': 'نوع التصوير',
  'inv.bodySite': 'موضع الجسم',
  'inv.service': 'الجهة المُصدِرة للتقرير',
  'inv.serviceHint': 'القسم أو الخدمة — لا اسم شخص.',
  'inv.reportText': 'نص التقرير',
  'inv.file': 'مستند (PDF أو JPEG أو PNG أو WebP أو نص)',
  'inv.fileHint':
    'ملفات DICOM غير مقبولة: ترويساتها تحمل اسم المريض وتاريخ ميلاده ورقم الفحص، ما يكسر السرية المستعارة لهذا السجل. صدِّر PDF أو صورة مجهولة الهوية من نظام PACS.',
  'inv.ack':
    'أؤكد إزالة أو تغطية المعرِّفات. التقارير ولقطات الشاشة تُظهر عادةً اسم المريض وتاريخ ميلاده ورقم الفحص، وهذه المنصة تخزّن سجلات مستعارة فقط.',
  'inv.save': 'حفظ النتيجة',
  'inv.saving': 'جارٍ الحفظ…',
  'inv.openFile': 'فتح المستند',
  'lab.panelName': 'اسم اللوحة (اختياري)',
  'lab.age': 'العمر',
  'lab.sex': 'الجنس',
  'lab.ageHint':
    'يُستخدم العمر والجنس للنطاقات المرجعية الخاصة بالجنس ولحساب eGFR وFIB-4. إذا تُركا فارغين يُؤخذان من سجل المريض، ولا تُحتسب هذه المؤشرات إن كان العمر مجهولاً.',
  'lab.addAnalyte': 'أضف تحليلاً',
  'lab.choose': 'اختر…',
  'lab.noRows': 'لم تُضف أي تحاليل بعد.',
  'lab.reference': 'المرجع',
  'lab.save': 'حفظ وتفسير',
  'lab.saving': 'جارٍ الحفظ…',
  'lab.results': 'النتائج',
  'lab.analyte': 'التحليل',
  'lab.value': 'القيمة',
  'lab.flag': 'العلامة',
  'lab.asEntered': 'كما أُدخلت',
  'lab.critical': 'حرج',
  'lab.notFlagged': 'بلا علامة',
  'lab.analytes': 'تحاليل',
  'lab.flagged': 'معلَّمة',
  'lab.derived': 'المؤشرات المشتقة',
  'lab.unrecognised': 'مخزَّن دون تفسير',
  'lab.addPanel': 'إضافة نتائج مختبر',
  'lab.needCase': 'أنشئ سجل المريض أعلاه أولاً.',
  'lab.panels': 'لوحات المختبر',
  'lab.noPanels': 'لا توجد نتائج مختبر مرفقة بهذه الحالة بعد.',
  'lab.attachHint':
    'يمكن إرفاق النتائج بأي حالة، فحالة التصوير التي وجّهت لتحاليل دم يمكنها الاحتفاظ بما عاد منها.',
  'emergency.whyStatic': 'لماذا لا تعرض هذه الصفحة شيئاً عن مريضك',
  'emergency.moveOnlyIf': 'حرّكه فقط إذا',
  'clinical.title': 'اعتبارات سريرية للطبيب المراجِع',
  'clinical.considerations': 'ما يتوافق معه هذا النمط',
  'clinical.overlapsWith': 'هذا النمط يتقاطع مع كل ما يلي:',
  'clinical.distinguishedBy': 'يُميَّز بواسطة',
  'clinical.immediateActions': 'خطوات وقائية فورية، بانتظار المراجعة',
  'clinical.immediateActionsNote':
    'إجراءات وقائية فقط، تُتخذ أثناء ترتيب الإحالة. لا يُوصى بأي دواء أو إجراء، وهي لا تحل محل خطة الطبيب.',
  'clinical.askAndCheck': 'اسأل وافحص — هذه ليست في النتيجة',
  'clinical.askAndCheckNote':
    'غالباً ما تكون أهم من الصورة. سجّل الإجابات مع الحالة.',
  'clinical.notAssessable': 'غير قابل للتقييم مما قُدِّم',

  'followUp.title': 'إجابات لا تستطيع الكاميرا تقديمها',
  'followUp.intro':
    'هذه هي المعطيات التي تحسم الحالة ولا تحتويها أي صورة. أجب عمّا فحصته فعلاً، واترك الباقي فارغاً.',
  'followUp.rule':
    'الإجابات قد ترفع درجة الاستعجال، ولا تخفضها أبداً — لا تُسحب علامة مقيسة من الصورة لأن فحصاً ذُكر أنه طبيعي.',
  'followUp.notes': 'ملاحظات سريرية',
  'followUp.notesHint':
    'نص حر. يُحفظ ويُعرض كما كُتب تماماً، ويُدرج في ملف PDF. لا يُحلَّل ولا يُقيَّم ولا يُستخدم كمدخل لأي نموذج.',
  'followUp.notesPlaceholder':
    'القصة المرضية، نتائج الفحص، ما قمت به بالفعل، وما تسأل عنه الطبيب المراجِع…',
  'followUp.submit': 'حفظ وإعادة التقييم',
  'followUp.saving': 'جارٍ إعادة التقييم…',
  'followUp.reset': 'مسح الإجابات',
  'followUp.open': 'أجب عن أسئلة المتابعة',
  'followUp.why': 'سبب طرح هذا السؤال',
  'followUp.answered': 'مُجاب',
  'followUp.unanswered': 'بدون إجابة',
  'followUp.imageGrade': 'من الصورة',
  'followUp.answerGrade': 'من إجاباتك',
  'followUp.combined': 'الدرجة المجمَّعة',
  'followUp.escalated': 'ارتفعت الدرجة بسبب إجاباتك',
  'followUp.notEscalated': 'لم ترفع إجاباتك الدرجة.',
  'followUp.triggers': 'ما رفعته إجاباتك',
  'followUp.because': 'لماذا يهم',
  'followUp.consider': 'ضع في الاعتبار',
  'followUp.distinguishedBy': 'يُميَّز بواسطة',
  'followUp.history': 'إدخالات المتابعة السابقة',
  'followUp.recordedBy': 'سُجِّل',
  'followUp.noEntries': 'لم تُسجَّل أي إجابات متابعة لهذه الحالة.',
  'followUp.emptyAnswers': 'أجب عن سؤال واحد على الأقل، أو اكتب ملاحظة، قبل الحفظ.',
  'followUp.queued':
    'لا يوجد اتصال — حُفظت إجاباتك على هذا الجهاز وستُرسل عند عودة الاتصال. تُجرى إعادة التقييم على الخادم، لذا لا تظهر درجة مجمَّعة بعد.',
  'followUp.blank': '—',
  'followUp.opt.yes': 'نعم',
  'followUp.opt.no': 'لا',
  'followUp.opt.unknown': 'غير معروف',
  'followUp.opt.not_tested': 'لم يُفحص',
  'followUp.opt.not_applicable': 'لا ينطبق',
  'followUp.opt.both_palpable': 'كلاهما محسوس',
  'followUp.opt.one_absent': 'أحدهما غائب',
  'followUp.opt.both_absent': 'كلاهما غائب',
  'followUp.opt.intact': 'سليم',
  'followUp.opt.reduced': 'منخفض',
  'followUp.opt.absent': 'غائب',

  'calib.title': 'مرجع اللون',
  'calib.applied': 'مُعايَر مقابل بطاقة مرجعية',
  'calib.notDetected': 'لا توجد بطاقة مرجعية في هذه الصورة',
  'calib.unusable': 'عُثر على بطاقة مرجعية لكنها غير صالحة للاستخدام',
  'calib.shift': 'انحراف الإضاءة المُصحَّح',
  'calib.howTo': 'كيفية استخدام البطاقة المرجعية',
  'calib.why':
    'لون الصورة في الهاتف تحدده إضاءة الغرفة أكثر مما يحدده المريض. وجود بطاقة رمادية أو بيضاء محايدة في الإطار يجعل صورة اليوم قابلة للمقارنة مع صورة الأسبوع الماضي.',

  'delete.title': 'حذف هذه الحالة',
  'delete.warn':
    'هذا يُتلف الصور نهائياً وكل تقييم مُشتق منها. لا توجد سلة محذوفات ولا يمكن التراجع.',
  'delete.keeps':
    'يُحتفظ بسجل المريض المُرمَّز، وكذلك بقيد التدقيق الذي يسجّل حذف هذه الحالة. ولا يحمل أيٌّ منهما معرِّف مريض أو أي محتوى سريري.',
  'delete.button': 'حذف الحالة',
  'delete.confirmPrompt': 'اكتب DELETE للتأكيد',
  'delete.confirmWord': 'DELETE',
  'delete.confirm': 'حذف نهائي',
  'delete.cancel': 'إلغاء',
  'delete.working': 'جارٍ الحذف…',
  'delete.done': 'تم حذف الحالة.',
  'delete.removed': 'أُزيل',

  'routing.notAssessed': 'لم يُقيَّم',
  'routing.missing': 'ما هو ناقص',
  'routing.basis': 'على ماذا يستند هذا القرار',
  'routing.source.iwgdf_risk_category': 'فحص القدم (فئة خطورة IWGDF)',
  'routing.source.follow_up_answers': 'إجابات متابعة الطبيب',
  'case.photoRecord': 'الصورة — سجل، وليست قراراً',
  'case.photoRecordHint':
    'ما قاسته الكاميرا، محفوظ لتتبّع الجرح عبر الزمن. ليست قرار التوجيه أعلاه ولا تشارك فيه.',
  'result.observationOnly': 'مُلاحَظ في الصورة — ليس قرار التوجيه',
  'result.imageOnly': 'ما قد توحي به الصورة وحدها',
  'result.imageOnlyHint':
    'يُعرض للاكتمال فقط. تُوجَّه الحالة بناءً على الفحص والإجابات، لا على هذا.',
  'followUp.imageObserved': 'ما لوحظ في الصورة',
  'followUp.triggered': 'هذه الإجابات رفعت علامة تحذير',
  'followUp.noTrigger': 'لم ترفع هذه الإجابات أي علامة تحذير.',

  'progress.title': 'هل يلتئم الجرح؟',
  'progress.intro':
    'المساحة مقيسة بالسنتيمتر المربع مقابل بطاقة معلومة الأبعاد، عبر الزيارات. تُقارن فقط الصور التي تحتوي مرجع قياس — فالنسبة المئوية من الإطار تتغير عند تحريك الكاميرا دون أن يتغير الجرح.',
  'progress.notEnough': 'لا توجد قياسات معايَرة كافية للمقارنة بعد.',
  'progress.change': 'انخفاض المساحة',
  'progress.absolute': 'التغير المطلق',
  'progress.over': 'خلال',
  'progress.days': 'يوماً',
  'progress.excluded': 'صور تعذّرت مقارنتها',

  'labUpload.title': 'رفع تقرير المختبر',
  'labUpload.storedNotRead':
    'يُحفظ ولا يُقرأ. لا تُستخرج أي قيمة من هذا المستند ولا تنتج عنه أي درجة — التفسير أعلاه يعمل على الأرقام التي تكتبها مع وحدتها. يُحفظ هنا ليحمل الإحالة مصدرها وليتمكن المراجع من مطابقة القيم المكتوبة بالأصل.',
  'labUpload.choose': 'اختر ملف PDF أو صورة',
  'labUpload.service': 'المختبر المُصدِر (اختياري)',
  'labUpload.servicePlaceholder': 'مثال: المختبر المركزي',
  'labUpload.serviceHint': 'اسم الخدمة، لا اسم شخص.',
  'labUpload.ack':
    'أزلت اسم المريض وتاريخ ميلاده وأي معرِّف آخر من هذا المستند. تقرير المختبر يحملها عادةً في أعلاه، وهذا السجل مُرمَّز.',
  'labUpload.file': 'حفظ التقرير',
  'labUpload.filing': 'جارٍ الحفظ…',
  'labUpload.filed': 'حُفظ التقرير في هذه الحالة.',

  'clarify.title': 'يستحق السؤال قبل أي شيء آخر',
  'clarify.intro':
    'سؤال أو سؤالان مُختاران مما أظهرته هذه الصورة فعلاً. كل منهما يذكر ما ستحسمه إجابته — المقصود تجربة لها نتيجة، لا نصيحة.',
  'clarify.settles': 'ما تحسمه الإجابة',

  'evidence.title': 'ما تُظهره الصورة، وما لا تستطيع إظهاره',
  'evidence.observed': 'ما لوحظ في الصورة',
  'evidence.observedHint':
    'وصف لوحدات الصورة. لا شيء من هذا تشخيص، ولا يسمّي أيٌّ منه مرضاً.',
  'evidence.cannot': 'لا يمكن تحديده من صورة',
  'evidence.cannotHint':
    'هذه تتطلب اليدين أو أدوات أو تصويراً طبياً. لم يُقيَّم أيٌّ مما يلي، ولا تعني أي نتيجة في هذه الصفحة خلاف ذلك.',
  'evidence.means': 'ماذا تعني هذه النتيجة',
  'evidence.ceiling': 'أعلى درجة استعجال تدعمها الأدلة البصرية',
  'evidence.capped':
    'تجاوزت المساحات المقيسة عتبة أعلى، لكن الأدلة البصرية لم تدعمها. خُفّضت الدرجة المعروضة إلى ما تحمله الأدلة — والأسباب مذكورة في المسوّغات أدناه.',
  'evidence.limits': 'لماذا لا تحمل الأدلة أكثر من ذلك',
  'evidence.appearance.no_significant_visual_abnormality': 'لم يُكتشف شذوذ بصري ذو دلالة',
  'evidence.appearance.potentially_abnormal_appearance': 'مظهر قد يكون غير طبيعي',
  'evidence.appearance.insufficient_image_quality': 'جودة الصورة غير كافية لتقييم بصري موثوق',
  'evidence.params':
    'معاملات بحثية قابلة للضبط — وليست عتبات سريرية مُتحقَّقاً منها',

  'result.aboutScore': 'حول هذه الدرجة',
  'clinical.moreDetail': 'تفاصيل سريرية — التشخيصات التفريقية، وما يُسأل ويُفحص',
  'result.moreLimits': 'المزيد عمّا لا تستطيع الصورة تقييمه',

  'feedback.title': 'هل كان هذا صحيحاً؟',
  'feedback.intro':
    'كل خلل حقيقي في هذه المنصة اكتشفه شخص ينظر إلى صورة حقيقية — لا اختباراتها. إن أخطأت هنا، فإن قولك ذلك هو أنفع ما يمكن فعله بها.',
  'feedback.groundTruth': 'ما الذي كان موجوداً فعلاً؟',
  'feedback.groundTruthHint': 'اختياري، لكنه ما يحوّل الشكوى إلى قياس.',
  'feedback.notePlaceholder': 'أي شيء يساعد — ما رأيته، وما فاتها…',
  'feedback.send': 'إرسال',
  'feedback.sending': 'جارٍ الإرسال…',
  'feedback.thanks': 'سُجّل. شكراً — هكذا تُصحَّح العتبات.',
  'feedback.previous': 'مسجَّل سابقاً',

  'result.triage': 'الفرز',
  // ليست «ثقة». الرقم مؤشّر استدلالي غير معاير للمسافة عن العتبة، وليس احتمالاً.
  'result.confidence': 'قوة الدليل (غير معايَرة)',
  'result.distance': 'قوة الدليل (غير معايَرة)',
  'result.evidenceStrengthHint':
    'مؤشّر استدلالي، لا احتمال. يعكس بُعد القياس عن عتبة القرار مخصوماً بجودة الصورة — وهو غير معاير مقابل النتائج السريرية، ولا يجوز قراءته كنسبة احتمال لأي شيء.',
  'result.noFlagMeaning':
    'لم تُكتشف أي سمة سطحية — هذا كل ما يعنيه الأمر. ليس قياساً لسلامة القدم، ولا يستبعد نقص التروية أو الاعتلال العصبي أو العدوى أو أي شيء تحت الجلد.',
  'result.nextStep': 'الخطوة التالية الموصى بها',
  'result.routeTo': 'التوجيه إلى',
  'result.timeframe': 'الإطار الزمني',
  'result.findings': 'السمات السطحية المكتشفة',
  'result.noFindings': 'لم تُعزل أي سمة سطحية واضحة في هذه الصورة.',
  'result.rationale': 'أساس هذه الدرجة',
  'result.quality': 'جودة الصورة',
  'result.limitations': 'ما لم يُقيَّم / القيود',
  'result.overlay': 'الصورة الموسومة',
  'result.pdf': 'تنزيل ملخص الطبيب (PDF)',
  'result.summary': 'ملخص الطبيب',
  'result.model': 'النموذج',
  'result.newCase': 'بدء حالة أخرى',
  'result.openCase': 'فتح الحالة',
  'result.area': 'المساحة',
  'result.severity': 'الشدة',

  'quality.rejected': 'رُفضت الصورة — يرجى إعادة الالتقاط',
  'quality.passed': 'مقبولة',
  'quality.degraded': 'منخفضة',
  'quality.check.resolution': 'الدقة',
  'quality.check.focus': 'التركيز',
  'quality.check.exposure': 'التعريض',
  'quality.check.subject_present': 'وجود الهدف في الإطار',
  'quality.measured': 'المقاس',
  'quality.threshold': 'الحد',

  'cases.title': 'الحالات',
  'cases.module': 'الوحدة',
  'cases.grade': 'الدرجة',
  'cases.patient': 'رمز المريض',
  'cases.created': 'تاريخ الإنشاء',
  'cases.status': 'الحالة',
  'cases.analyses': 'التحاليل',
  'cases.none': 'لا توجد حالات مطابقة.',
  'cases.all': 'الكل',
  'cases.filter': 'تصفية',

  'case.title': 'الحالة',
  'case.latest': 'أحدث تحليل',
  'case.history': 'تحاليل سابقة',
  'case.compare': 'المقارنة عبر الزمن',
  'case.compareHint':
    'مقارنة جنباً إلى جنب لنفس الحالة. قد تعكس الفروق الحالة نفسها أو الإضاءة أو التأطير — والطبيب هو من يقرر.',
  'case.noHistory': 'لا يوجد تحليل سابق للمقارنة بعد.',
  'case.back': 'العودة إلى الحالات',

  'fairness.title': 'الإنصاف (نموذج أولي)',
  'fairness.group': 'فئة مقياس مونك للون البشرة',
  'fairness.analyses': 'التحاليل',
  'fairness.meanConfidence': 'متوسط قوة الدليل (غير معايَرة)',
  'fairness.qualityPass': 'نسبة اجتياز الجودة',
  'fairness.coverage': 'سُجِّل لون البشرة لـ',
  'fairness.ofAnalyses': 'من التحاليل',

  'common.loading': 'جارٍ التحميل…',
  'common.error': 'حدث خطأ',
  'common.hint': 'ما ينبغي فعله',
  'common.close': 'إغلاق',
  'common.required': 'مطلوب',
  'common.notRecorded': 'غير مسجَّل',
  'common.intendedUse': 'الاستخدام المقصود',
}

const DICTS: Record<Lang, Dict> = { en, ar }
const LANG_KEY = 'qadam.lang'

interface I18nValue {
  lang: Lang
  dir: 'ltr' | 'rtl'
  t: (key: string) => string
  setLang: (lang: Lang) => void
  toggle: () => void
}

const I18nContext = createContext<I18nValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(
    () => (localStorage.getItem(LANG_KEY) as Lang) ?? 'en',
  )
  const dir: 'ltr' | 'rtl' = lang === 'ar' ? 'rtl' : 'ltr'

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dir
    localStorage.setItem(LANG_KEY, lang)
  }, [lang, dir])

  const setLang = useCallback((next: Lang) => setLangState(next), [])
  const toggle = useCallback(
    () => setLangState((cur) => (cur === 'en' ? 'ar' : 'en')),
    [],
  )
  const t = useCallback(
    (key: string) => DICTS[lang][key] ?? DICTS.en[key] ?? key,
    [lang],
  )

  const value = useMemo(
    () => ({ lang, dir, t, setLang, toggle }),
    [lang, dir, t, setLang, toggle],
  )
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside I18nProvider')
  return ctx
}
