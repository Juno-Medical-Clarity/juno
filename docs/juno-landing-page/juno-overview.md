# Juno — Company & Product Overview
*Compiled from the user's Google Drive folder "Health App / Shared" (read-only research). All claims below are sourced from internal documents; nothing is invented. Where the docs are silent, it's flagged in the Gaps section.*

---

## Overview

Juno is an early-stage (pre-seed, pre-revenue) health-tech startup building a **"patient-understanding" and care-adherence platform for clinics**. The core idea: after a doctor's visit, patients forget or misunderstand most of what they were told. Juno takes the clinician-authored notes, discharge instructions, and care plans that already exist (from the EHR, an after-visit summary, or an AI scribe) and turns them into a clear, source-grounded, plain-language, multilingual summary the patient (and their caregiver) can read, act on, and ask follow-up questions about — with the results tracked and reported back to the clinic.

From the pitch deck's own framing:
> "Juno — Patient engagement and care adherence platform for Clinics. Turns visits and discharge instructions into clear guidance patients can act on."

Juno explicitly positions itself as **not** an AI scribe (it doesn't listen to/record the visit), **not** a patient portal (it doesn't just expose records), and **not** a care-management platform (it doesn't run the outreach program) — it's the "translation and follow-through layer" that sits on top of all of those and feeds them cleaner, more actionable patient-facing content.

The company is building this as a Microsoft-engineer-founded startup with a clinical/neuropsychology co-founder and academic clinical advisors, currently doing early clinic outreach (mostly Boston-area, AthenaHealth-based practices) to secure a first pilot, with neurology / multiple sclerosis (MS) as the initial specialty wedge.

---

## Problem / Market Need

Documented (with citations) across the Business Model and pitch-deck materials:

- **Patients forget 40–80% of what's discussed in a visit**, and roughly half of what they do remember is incorrect (cited: AHRQ; Murugesu 2022).
- **~80 million U.S. adults** have limited health literacy (low education, older age, anxiety, language barriers).
- **76% of providers** report communication challenges, especially with low-literacy patient groups.
- **$238B/year** is attributed to the cost of low health literacy (unnecessary visits, missed care steps, poor adherence, confusion).
- Clinics absorb the resulting burden as repetitive calls, portal messages, missed follow-ups/tests, no-shows, and preventable deterioration.
- Standard after-visit summaries (AVSs) are frequently confusing; more content doesn't equal better recall.
- Specific literature cited elsewhere in the Drive: enhanced-readability discharge summaries cut provider phone calls by ~22%→9% and monthly readmissions by up to ~50% in one study; health-literacy interventions raise treatment adherence ~14–16% on average; ~56% of seniors have a medication discrepancy between discharge instructions and actual home use.
- Policy tailwind: ONC's Cures Act Final Rule requires patients get full electronic access to their health information; CMS's APCM (Advanced Primary Care Management) framework increasingly rewards communication, care planning, and transitions management — i.e., **access to records is now expected, but usable understanding of them is the remaining gap**, which is exactly where Juno positions itself.

## Product & Key Features

Juno's own "Features" doc and the GTM synthesis PDF converge on a fairly complete feature map. Grouped by audience:

**Patient-facing (source-grounded, "translate not interpret")**
- Plain-language visit/discharge summary tied explicitly back to source documentation (core artifact)
- "What changed today" — delta from the prior care plan
- Medication changes: added/changed/stopped, purpose, clinician-authored warnings only (no added medical advice)
- Action-item checklist with due dates/status; separate follow-up checklist (schedule / complete / bring-prepare)
- Lab/test explanations (what was ordered, what to do next — no diagnostic interpretation)
- "What to watch for" / "when to call the clinic" (source-grounded escalation guidance)
- Chat interface to ask questions about the summary, with auto-escalation to staff when the AI doesn't know
- No-app delivery: link via WhatsApp/SMS/email/portal, plus optional web/phone app
- Multilingual support and health-literacy-level adaptation (simple/medium/detailed views of the same facts)
- Older-adult accessibility (large type, low cognitive load, audio-ready/mobile-friendly)
- Research-backed medical-literacy testing to personalize summary complexity
- Care-plan timeline across visits/tests/referrals; reminder system (SMS/email/portal) tied to tasks

**Caregiver-facing**
- Shareable, permissioned, auditable summary link
- Mirrored caregiver checklist and follow-up tracker
- Medication-change visibility at a glance
- Cognitive-impairment-friendly dual patient/care-partner workflows

**Clinic-facing (analytics/ROI)**
- Engagement dashboard: opens, time spent, caregiver shares, action-item progress
- "Patient understanding score" (behavior-based, explainable — not inferred clinical judgment)
- Missed-action-item exception queue; confusion-flag detection ("I don't understand," repeat reopens, repeated unresolved prompts)
- Unresolved-question routing to staff (only escalate what's actually unresolved)
- Callback-deflection metrics (contacts per 100 visits, before/after)
- Follow-up completion tracking, adherence tracking (starting with medication-question resolution / refill-gap proxies)
- Exportable pilot ROI report

**Safety & compliance**
- Every patient-facing statement source-grounded; explicit "provider said / record says / pending" distinction
- No unsupported medical advice; ambiguous questions escalate to humans; optional/default human-review mode for higher-risk pilots (oncology, post-discharge)
- Audit trail, version history, HIPAA-aligned handling, role-based access, consent/caregiver-sharing controls with revocation

**Integrations / workflow**
- EHR note upload and PDF/doc upload (AVSs, discharge instructions) from day one
- Visit-transcript ingestion (works well alongside ambient scribes)
- MyChart/portal-compatible link; SMS/email delivery (doesn't rely on portal adoption)
- CRM/care-management export (for APCM/CCM/TCM workflows)
- Optional deeper EHR integration later — explicitly **not** a blocker for first pilots
- Concretely: **AthenaHealth integration is partially built** — the team has identified AthenaHealth's data-fetch endpoint and can already pull/process sample patient data from it (per 06/24/2026 internal meeting notes). HIPAA compliance work is "partially done."

**Longer-term / adjacent ideas mentioned**
- Summarization/scoring/medical-literacy-test APIs exposed to third parties
- Partner product marketplace (e.g., adherence devices) with data shared back to clinics
- Research data collection / clinical trial routing
- B2C paths: direct-to-consumer monthly subscription, insurance-backed, or employer-backed versions of the app
- CVS/Walgreens API integration to track pharmacy-side patient actions and generate pre-visit PDF reports for clinicians (discussed in a 06/24/2026 advisor meeting, not yet built)

## Target Customer Segments & Value Propositions

The Business Model brainstorm doc lays out three prioritized "paths"; the pitch deck reflects the same thesis condensed into a single B2B strategy. Combined view:

### 1. Clinics (primary, near-term focus)
- **Who specifically**: neurology, MS, memory/dementia, geriatrics, oncology, cardiology, rheumatology, complex primary-care, independent specialty practices, hospital-affiliated outpatient specialty clinics, concierge/DPC clinics.
- **First wedge chosen deliberately**: neurology / MS-heavy follow-up workflows — high cognitive load, frequent medication changes, heavy caregiver involvement, recurring labs/imaging/follow-ups, and direct founder-market fit (the CSO is a neuropsychologist, the clinical advisor is a Columbia MS researcher).
- **Value prop**: "Juno is the patient-understanding layer for clinics. We take the notes, visit summaries, medication changes, and care instructions your team already creates, translate them into clear patient guidance without changing provider intent, and track whether patients and caregivers actually understand and complete the next steps. That helps clinics improve follow-through, reduce confusion-driven rework, support caregivers, and prove ROI with real operational metrics."
- **Concrete benefits pitched**: fewer avoidable calls/portal messages, more completed downstream care (labs, referrals, imaging, meds, follow-ups) → less revenue leakage, improved patient-experience/HCAHPS scores, reimbursable care-management support (CCM/PCM/TCM/APCM codes referenced: CPT 99487, 99489, 99490, 99439).
- Second-priority buyer type: **care-management infrastructure organizations** (CCM/PCM/TCM vendors, FQHCs, home-health transition programs, nurse/patient navigation companies) — attach to an existing reimbursable workflow rather than requiring a new budget line.

### 2. Payers / Value-Based-Care & Risk-Bearing Entities (strategic, longer-horizon)
- **Who specifically**: ACOs, Medicare Advantage plans, Medicaid managed-care organizations, risk-bearing primary-care groups, PACE programs, clinically integrated networks.
- **Why attractive**: these buyers capture direct financial upside from better adherence/follow-through (fewer ER visits, fewer admissions/readmissions, better medication adherence, closed care gaps, better CMS Star Ratings — which the docs note directly affect Medicare Advantage quality bonus payments).
- **Value prop**: "Juno helps high-risk patients execute care plans after complex visits, closing the gap between clinical recommendations and real-world follow-through."
- Docs are explicit that this is the **largest long-term revenue opportunity but requires stronger evidence** than the clinic-first path, so it's treated as a Path-3 (later) motion, not the current GTM focus.
- Medicaid managed care is called out as a plausible but harder buyer (budgets tighter, reimbursement varies by state); commercial insurers/employers are flagged as a "slower first buyer unless you have a very specific ROI story."

### 3. Patients (indirect / B2C, secondary)
- Docs are candid that **patients are not the primary go-to-market buyer**: "patients don't really care about research. They want to get a product recommended by their clinicians that is easy to use." The National MS Society specifically advised the founders to shift from a B2C to a B2B model because "customers are reluctant to pay for health apps, and doctors' recommendations carry more weight than direct sales" (per 06/24/2026 advisor meeting notes).
- Patient-side value: improved understanding/adherence, caregiver visibility, easier follow-through, chat access to their own summary.
- A B2C/insurance-backed/employer-backed subscription is listed as a possible parallel/future revenue stream, not the current focus. There was an earlier, smaller consumer pilot (see Traction) that has since been de-prioritized in favor of the clinic-first motion.

## Business Model

- **Model**: B2B SaaS sold to clinics and health systems (per pitch deck), not a consumer subscription at this stage.
- **Pricing tiers stated in the pitch deck** (Annual Contract Value / ACV):
  - Small clinics: **$15K–$30K ACV**, priced by provider count and eligible patient volume.
  - Specialty / complex-care clinics: **$30K–$75K ACV** (complex workflows, adherence tracking, analytics).
  - Hospital departments: **$75K–$250K+ ACV**, priced by volume, integrations, analytics, enterprise support.
  - Pricing drivers named: patient volume, provider count, workflow depth, integrations/analytics, outcome tracking.
- Earlier brainstorm doc also floated alternative pricing structures depending on path: per-provider/month, per-active-patient/month, pilot flat fee (Path 1); per-care-manager SaaS, white-label, per-episode for TCM (Path 2); PMPM per attributed high-risk patient or shared-savings-linked/performance-based contracts (Path 3, payer-side).
- **Current commercial motion**: no-cost pilots. The clinic outreach email template explicitly offers a **free pilot with no software fee** in exchange for being a "design partner," in Boston-area clinics and/or clinics on the AthenaHealth EHR (to ease integration).
- **Market sizing** (pitch deck, sourced to Grand View Research "U.S. Patient Engagement Solutions Market Size Report," 2024, plus a bottoms-up estimate):
  - TAM: **$12B+** (US patient engagement software market, ~21% annual growth, driven by shift to value-based care)
  - SAM: **$2B** (complex-care clinics specifically)
  - SOM: **$120–200M** (initial neurology/neuro-complex-care wedge: 3,000–5,000 U.S. sites × $20K–$40K ACV; expansion path into oncology and other high-complexity specialties)
- **Funding**: no institutional funding closed yet per the docs. The company is actively researching non-dilutive and dilutive paths — SBIR/STTR (via NIH/HHS, NSF), HRSA telehealth grants (nonprofit-partnership required), the ACL "Caregiver AI Challenge" ($100K prize), Massachusetts Life Sciences Center milestone grants (up to $250K), and accelerators (YC, a16z Speedrun, Techstars Anywhere/Boston, Mayo Clinic Platform_Accelerate, AgeTech Collaborative/AARP, Northwestern Medicine & Techstars Healthcare, MassChallenge). VCs noted as targets for later: 7wire Ventures, Rock Health Capital, Oak HC/FT, General Catalyst, Flare Capital. The pitch deck's explicit "Ask" section (below) confirms funding has not yet closed.
- **"Ask" (from pitch deck, i.e., what they're currently raising/seeking)**: pilot partners (neurology/MS/complex-care clinics), funding/grants to support pilot deployment/safety testing/outcome validation, and clinical advisors (neurologists, clinic operators, patient-experience leaders, care-management experts).

## Competitive Landscape / Differentiation

Extensively researched — a competitor tracking sheet lists **50+ named companies** across adjacent categories (patient-facing AI notes, post-discharge/transitions platforms, oncology navigation, medication adherence, RPM/CCM/chronic-care-management platforms, patient engagement/outreach, and reference points like OpenNotes). Selected notables with deep-dive notes: Kouper Health, Commure (Memora Health), Awell, CipherHealth, GetWell, Biofourmis/CopilotIQ, Navigating Cancer, Thyme Care, Reimagine Care, AdhereTech, Medisafe.

**Positioning vs. adjacent categories** (from the GTM synthesis doc's comparison table):

| Category | What they solve | What Juno adds |
|---|---|---|
| Patient portals (MyChart) | Access to records/messaging/scheduling | Turns access into *understanding* — translation, task extraction, literacy adaptation, caregiver sharing |
| OpenNotes | Transparency into clinician documentation | "OpenNotes made records visible; Juno makes them understandable and executable." |
| After-visit summaries (AVS) | Standard recap | Better structure and measurable task follow-through, not "more document" |
| Ambient scribes (e.g., Abridge) | Clinical documentation from the visit | Complementary — Juno takes the finalized documentation and produces patient-safe guidance + follow-through analytics ("Documentation AI writes the chart. Juno closes the understanding gap after the visit.") |
| Discharge-instruction tools | Standardized episodic instructions | Longitudinal, shareable, monitored comprehension flow |
| Patient engagement platforms | Outreach, reminders, scheduling | Actual care-plan comprehension, not generic engagement |
| Care-management platforms | Manage work after enrollment | Feeds them cleaner patient-facing plans and understanding signals |
| Call-center automation | Handle inbound demand | Prevents avoidable demand upstream rather than routing it |

A feature-comparison table in the pitch deck (Juno vs. AI Scribes vs. EHRs vs. Patient Portals) claims Juno is the only one of the four offering: personalized patient explanations, actionable care-plan next steps, plan-completion/follow-through tracking, confusion/missed-step visibility, integrated caregiver support, and material reduction of unnecessary calls/messages.

Direct/closest competitors flagged as most important to watch: **CipherHealth** ("probably the best direct competitor," used by 500 hospitals, claims 4x patient engagement, 17x recommend-likelihood, 42% staff-burnout reduction, 11-point patient-score increase), **Commure/Memora Health**, and **GetWell** (32% readmission reduction claimed, founded 2000 by Michael O'Neil).

Juno's stated commercial discipline: only claim what's evidence-backed today (patient understanding, medication clarity, caregiver sharing, follow-through visibility); explicitly avoid unproven claims (readmission reduction, staffing-cost cuts, nurse-burden reduction, no-show reduction, guaranteed ROI) until pilot data exists locally.

## Traction, Metrics, Financials, Roadmap

**Research/validation traction (per pitch deck "Traction" slide, current as of ~July 2026):**
- 300+ patient surveys
- 50+ patient interviews (completed independently, ~1 month)
- 50+ clinician interviews
- Key findings: 80% of patients not fully prepared for visits; 97% have follow-up questions; 61% struggle to act on follow-up; clinicians estimate losing 10–15 minutes per appointment to needless re-explanation
- 10 active MVP users, 70+ person waitlist
- Columbia-affiliated physician interest; conversations with National MS Society senior leaders, who encouraged the team toward the Society's "Fast Forward" program
- Prior B2C pilot (per 06/24/2026 advisor meeting): ~10 active users tested the earlier consumer version but showed "limited traction, with most using it only once or twice, primarily due to HIPAA concerns about data privacy" — this predates and motivated the pivot to B2B.
- The dedicated interview-tracking sheets (Clinicians and Patients, Google Forms) contain dozens of detailed qualitative responses on medical-instruction recall, comfort with AI scribes/recording, and willingness to use a HIPAA-compliant post-visit AI tool.

**Outreach/GTM traction:**
- A structured clinic-outreach campaign started 07/06/2026, targeting ~50 clinic contacts/week, starting in Boston and the Bay Area then expanding nationally; criteria: small, value-based-care-oriented clinics on Medicare/Medicaid, neurology-first then primary care.
- A "Reachout Tracking" sheet lists ~15 real Boston-area clinics/practices contacted starting 7/8–7/10/2026 (e.g., Holtzman Medical Group, North Shore Neurology, Manet Community Health Center, Heywood Medical Group, Bookmark Medical/an ACO contact, Arlington Family Practice) — as of the sheet's last update, no pilot has been confirmed signed; this is active/open pipeline, not closed deals.
- A separate "Track" master sheet (Organization/Contact/Email/Date/Note) exists but was empty (headers only) at the time of review — suggesting either very early-stage tracking or a sheet not yet populated.

**Roadmap / execution status (from internal meeting notes, most recent entries 06/01–07/06/2026):**
- AthenaHealth EHR integration: **partially built** — the team has identified AthenaHealth's data-fetch endpoint and can pull/process sample patient data.
- HIPAA compliance: **partially built** — critical components identified, to be completed alongside any public release.
- Applied to (unsuccessfully so far) MS Society and Mayo Clinic research/grant programs; Mayo Clinic's accelerator was assessed as premature ("tighter expectations... applying now might be a waste of time").
- Planned near-term: complete Athena integration to enable a hospital-head meeting via a Boston incubator contact; explore CVS/Walgreens pharmacy API integration for tracking patient actions; design a pilot comparison methodology (before/after Juno, or Juno vs. non-Juno patients) with the co-founder; explore an MS-Society research-grant partnership via a Columbia-affiliated advisor (may require a nonprofit/university partner).
- The pitch deck's own pilot-design guidance (from the GTM synthesis PDF) recommends an **8–12 week, single-service-line, matched-comparison pilot** in neurology/MS, with a defined ROI formula (staff capacity value + retained follow-up margin + leakage recapture + no-show recovery) and named success thresholds (e.g., "Strong" = 65%+ summary open rate, 10+ point comprehension gain, 8+ point follow-up completion gain, annualized payback visible within 6–12 months).

**Financials**: No revenue, funding round, or valuation figures are documented anywhere in the Drive. The only dollar figures present are market-sizing estimates, illustrative/hypothetical pilot ROI math (an example scenario in the GTM synthesis PDF, explicitly labeled "illustrative assumptions, not forecasts," which nets to a *−23% pilot-period ROI* before annualization — used to argue Juno shouldn't lead its sales pitch with near-term cost savings), and target ACV pricing bands.

## Team

- **Tejit Pabari — CEO/Founder** (the user). Software Engineer at Microsoft (geospatial APIs at scale); BS Computer Science, Columbia. Built several side projects (SMARTest — HIV/syphilis self-testing app; Med-Doc Tracker; Clip-Verse; a Crunchyroll filler-episode Chrome extension with 500+ Reddit upvotes); co-founded Columbia Virtual Campus (10,000+ views) during COVID. Published research on flood-event extraction for index insurance in Bangladesh.
- **Gitika Bose — CTO/Co-founder**. Software Engineer at Microsoft (PowerPoint backend/microservices); BS Computer Science (AI specialization), Columbia, 2017–2021, Cum Laude. Holds 55% equity per her (likely YC-style) founder-application profile. AI/NLP research background (Columbia's Natural and Spoken Language Lab; co-authored a misinformation/semantic-forensics paper on arXiv); past medical project MedDocTracker; past project on pill identification from images.
- **Frédérique ("Fred") Escudier, Ph.D., Psy.D. — Chief Scientific Officer/Co-founder**. Clinical neuropsychologist, 15+ years' experience in cognitive impairment, clinical communication, and patient/family support in complex care. Co-founded and later became president of the Quebec Association of Neuropsychologists. Published author (a book on evidence-based learning strategies used in Quebec schools) with registered IP (a Judgment Assessment Tool) and prior research funding (~$110K) from the Quebec Network for Research on Aging and the Alzheimer Society of Canada. Explicitly named as the founder-market fit for the neurology/neuro-complex-care wedge.
- **Dr. Victoria Leavitt, Ph.D. — Clinical Advisor**. Associate Professor of Neuropsychology, Columbia University Medical Center. Cognitive neuroscience researcher, MS specialist; funded in the past by NIH, DoD, and the National MS Society. Previously co-founded eSupport Health, an NMSS-funded HIPAA-compliant telehealth peer-support platform for MS patients, with strong reported feasibility/adherence signals.
- **Anindita — informal advisor** mentioned in a 06/24/2026 meeting, helping structure Juno's value proposition, ROI metrics, and stakeholder narrative (measurement background across sectors); relationship/title not otherwise documented.
- An unnamed "advisor at Columbia" is referenced regarding a possible MS Society research-grant partnership requiring a nonprofit/university tie-in — may or may not be Dr. Leavitt; not disambiguated in the docs.

## Gaps
(Things a future landing page or outward-facing narrative would need to fill in, because the internal docs are silent, inconsistent, or clearly marked "to be validated")

- **No closed pilot yet.** All clinic conversations in the Reachout Tracking sheet are open/in-progress as of the most recent update (~7/10/2026); no signed pilot, LOI, or paying customer is documented.
- **No revenue, funding, or valuation data anywhere.** The pitch deck's "Ask" slide confirms the company is still raising/seeking pilot funding and grants — not something to present as "funded" or "revenue-generating."
- **ROI/ outcome claims are explicitly unproven.** The company's own GTM synthesis document is unusually disciplined about this: readmission reduction, staffing-cost cuts, nurse-burden reduction, no-show reduction, and net positive ROI are all flagged as claims Juno should **not** make publicly until it has pilot-specific data. Any landing page copy needs to respect this "designed to / can help / to be measured in pilot" phrasing discipline the team has already set for itself.
- **Product maturity is ambiguous.** Docs describe both a built MVP with "10 active users" (older B2C version, low retention) and a newer B2B prototype with partial AthenaHealth integration and partial HIPAA compliance — it's unclear from the docs alone exactly what is live/demoable today versus still being engineered.
- **B2C/insurance/employer-backed model is only conceptual.** It appears in the "Juno features" brainstorm as a future/indirect-use idea, not in the pitch deck's actual (B2B-only) revenue model — so messaging should not conflate the two paths as current offerings.
- **Payer/value-based-care segment is strategic but not active.** The docs are explicit this is a "Path 3," longer-horizon motion requiring more evidence than currently exists; it shouldn't be presented as an active GTM motion today.
- **No company name/brand assets, logo, tagline, or domain were found** in the reviewed folders (the "Public" folder contained only Docs/PDFs of founder profiles and the pitch deck — no design assets, one-pagers beyond the deck, or website copy).
- **Legal/entity information absent** — no incorporation details, cap table (beyond one founder-application data point showing Gitika Bose at 55% equity), IP/patent status, or HIPAA/BAA documentation itself (only references to HIPAA work being "partially done").
- Folders not deeply reviewed due to scope/time (noted for completeness, but likely lower-value for a landing page): **Data** (raw "Appointment Summaries" and "Test results samples" sample folders, plus an LLM datasets/benchmarks doc — not opened, likely working data rather than narrative content), **Tech**, **Scientific literature**, **Applications**, **Op3 - Via Integration**, **Patient Research/Archive**, and the individual **Competitor Analysis/Individual** subfolder and two "Integrations, compliance and competitors" / "Competitor analysis - GPT" PDFs.

---

*Note: several documents ("Juno Clinics ROI - Part 1/1-2/2/Final," "Juno Summary formation..." PDF) are AI-generated ("GPT Analysis") research/strategy syntheses commissioned by the team rather than primary company statements — treated here as internal strategic input, not as independently verified fact.*
