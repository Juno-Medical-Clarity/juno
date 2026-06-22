# EHR & Clinic Integration Compliance Requirements for Juno

> **Disclaimer:** This document is a planning and research resource, not legal advice. Specific regulatory questions — especially regarding FDA jurisdiction, state law applicability, and contract terms — require review by qualified healthcare regulatory counsel before business decisions are made.

> **Research Date:** June 2026. This is a rapidly evolving landscape. Key areas (FDA CDS guidance, state AI laws, HITRUST requirements) should be re-verified annually and before each new state market entry.

---

## Executive Summary

**Five Critical Findings:**

1. **FDA jurisdiction is Juno's most consequential risk — and the analysis is nuanced.** Juno's core function (translating clinical notes into plain-language patient guidance) likely falls *outside* FDA's Software as a Medical Device (SaMD) jurisdiction if the product is carefully scoped and marketed as patient education only — not clinical decision support, not diagnostic, not treatment-directing. However, this is not a clean exemption: the CDS Non-Device exemption under the 21st Century Cures Act *explicitly applies only to recommendations made to healthcare professionals*, not to patient-facing tools. Juno must rely on the "general wellness" and "administrative software" carve-outs, and maintain strict guardrails against clinical claims in marketing and product design. A qualified healthcare regulatory attorney must assess and document this analysis before Juno's first commercial deployment. This is the single highest-stakes compliance decision the company will make.

2. **SOC 2 Type II first, HITRUST later.** SOC 2 Type II is the universal entry credential for any clinic customer — small or large. It is achievable in 6–12 months at $30K–$80K and is required to win virtually every deal above a solo practice. HITRUST i1 certification becomes required at approximately the $100K–$250K ACV tier (mid-size health systems). Juno should begin SOC 2 immediately and plan HITRUST within 18–24 months of first revenue.

3. **Washington State's My Health MY Data Act is a significant risk.** This 2023 law applies to *all* entities processing "consumer health data" of Washington residents, regardless of whether they are a HIPAA covered entity or B2B vendor. The B2B shield is weaker than most startups assume — downstream patient data flowing through Juno can trigger the law. Consent mechanisms and data minimization practices must be designed with MHMDA compliance in mind from day one.

4. **Athena Health integration is feasible but requires formal partner agreement and BAA execution before any PHI flows.** The Marketplace program involves security vetting, OAuth 2.0 API access, a Data Use Agreement, and a revenue share of 15–30%. Approval takes 6–12 weeks. Juno must not access Athena data without completing this process.

5. **The typical time from first vendor contact to live production integration is 2–6 months at small/mid-size clinics and 6–18 months at large health systems.** This has major revenue planning implications. The primary deal blockers are absence of a signed BAA, lack of SOC 2 or security questionnaire responses, and inability to demonstrate clear HIPAA compliance. Penetration testing results and evidence of encryption are expected at mid-market and above.

---

## Federal Regulations Beyond HIPAA

### 21st Century Cures Act / Information Blocking (ONC)

**What it is:** The 21st Century Cures Act (2016) and ONC's Cures Act Final Rule (2020) prohibit "information blocking" — practices that unreasonably interfere with the access, exchange, or use of electronic health information (EHI). Enforcement of financial disincentives began July 31, 2024 for hospitals and clinicians, and January 1, 2025 for ACOs. Full enforcement with civil monetary penalties up to $1M per violation for health IT developers is now in effect (HHS crackdown announced September 2025).

**Who is subject to information blocking rules:**
- Health IT developers of certified health IT
- Health Information Networks (HINs) and Health Information Exchanges (HIEs)
- Healthcare providers

**Does Juno directly need to comply?** Juno is not itself a certified health IT developer, HIN, or healthcare provider, so it is not currently a direct information blocking "actor" subject to ONC penalties. However:

- If Juno's clinic customers use Juno in a way that blocks patient access to their own data, the *clinic* could face penalties
- If Juno were to seek ONC certification (not currently required), it would become an actor subject to the rule
- Juno must not design features or contractual terms that would enable or encourage its clinic customers to engage in information blocking

**ONC Health IT Certification — Is it required for Juno?**
ONC certification is currently *not required* for third-party patient engagement apps like Juno. It is required for EHR systems seeking to meet Meaningful Use / Promoting Interoperability requirements. However, ONC certification can be a market differentiator and some large health systems may prefer or require working with certified apps.

The ONC HTI-1 Final Rule (effective 2024) and proposed HTI-2 rule include requirements for algorithm transparency (for developers of decision support interventions used by ONC-certified health IT) — these rules apply primarily to EHR vendors, not to downstream apps like Juno.

**USCDI (United States Core Data for Interoperability):** USCDI v4 is now the baseline standard (adopted in ONC SVAP 2024, proposed as HTI-2 baseline). Juno's Athena Health integration will encounter USCDI-formatted data. Juno should design its data ingestion layer to handle USCDI data classes including clinical notes (new in v3/v4), problem list, medications, allergies, and social determinants of health.

**Practical implication for Juno:** Ensure no contractual terms prohibit patients from accessing their own guidance or sharing it. Never charge patients for access to their own health information. Build data export/portability features consistent with patient access norms.

---

### FDA — Software as a Medical Device (SaMD)

**This is the most consequential compliance question Juno faces. Analysis is detailed below.**

#### What Makes Software a Medical Device?

Under 21 U.S.C. § 321(h) and FDA guidance, software is a medical device if it is "intended to be used for the diagnosis of disease or other conditions, or in the cure, mitigation, treatment, or prevention of disease." The "intended use" is determined by labeling, marketing claims, and reasonably foreseeable use — not just what the software technically does.

The 21st Century Cures Act (2016) and subsequent FDA guidance created categories of software explicitly excluded from the device definition:

**Excluded (Non-Device) Software Categories:**
1. Administrative functions (scheduling, billing, coding)
2. Electronic Health Records (EHR/EMR systems)
3. General wellness products (low-risk, not disease-specific)
4. Medical Device Data Systems (MDDS) for display/transfer only
5. Clinical Decision Support (CDS) software — but only under specific conditions

#### The Critical CDS Non-Device Exemption

The 21st Century Cures Act exempts CDS software from device regulation if it meets **all four** of the following criteria:

1. Does not acquire, process, or analyze medical images, IVD signals, or patterns from signal acquisition systems
2. Displays, analyzes, or prints medical information about a patient or other medical information
3. **Intended for supporting or providing recommendations to a *healthcare professional* (HCP) user**
4. Provides sufficient information about the basis for recommendations so the HCP "does not rely primarily on" the recommendation

**Critical finding: Criterion #3 is the problem for Juno.** The FDA's 2022 final CDS guidance (confirmed in the January 2026 updated guidance) explicitly removed patient-facing apps from CDS exemption analysis, directing them to other regulatory frameworks instead. The CDS Non-Device exemption applies *only when recommendations are made to a healthcare professional*, not to patients or caregivers.

This means Juno **cannot rely on the CDS Non-Device exemption** for its patient-facing output.

#### Alternative FDA Exemption Pathways for Juno

**Path 1: General Wellness Software (Most Applicable)**

FDA's General Wellness guidance (updated January 2026) provides enforcement discretion for products intended for "general wellness" that present only low risk. Under this guidance, software is treated as general wellness (not a medical device) if:
- It is intended solely to support or maintain general health
- It does not reference a specific disease or condition (or if it does, the disease/condition is not serious and the link to wellness is well-established)
- It presents only low risk to users

**Analysis for Juno:** Juno's core function — translating clinical notes into plain-language patient education — is arguably closer to "administrative support" or "patient communication" than to "wellness" in the FDA's intended sense. However, the general wellness pathway could support Juno if:
- Marketing strictly avoids disease-specific medical claims
- Juno does not claim to diagnose, treat, or improve specific conditions
- Juno explicitly positions output as "educational information" rather than "guidance for clinical action"

**Path 2: Administrative Software**

FDA explicitly excludes software "intended for administrative support of a healthcare facility" including "patient communication of general health information." Plain-language versions of discharge instructions and care notes could qualify here.

**Path 3: Intended Use Design**

The safest FDA strategy for Juno is a carefully designed intended use statement that characterizes the product as:
- A *patient communication and education tool*
- That converts complex clinical language into plain language *for patient comprehension*
- Without providing independent clinical recommendations
- Without replacing or supplementing clinical judgment
- With explicit disclaimers that output is not medical advice and does not supersede provider instructions

Juno's tagline "Juno translates, it does not interpret" directly supports this framing. The product must be consistent with this in every marketing asset, UI element, sales material, and contract.

#### What Would Trigger FDA Jurisdiction for Juno

Juno WOULD likely require FDA clearance/approval if it:
- Added features providing treatment recommendations to patients or providers
- Generated personalized clinical recommendations (e.g., "you should schedule an appointment for X")
- Made predictive assessments about patient health status
- Analyzed clinical notes to flag diagnoses or risks
- Was marketed as a tool for managing a specific condition (e.g., "MS management platform")
- Generated alerts or interventions that clinicians are expected to act on

The "neurology first" strategy (MS, dementia, Parkinson's) introduces heightened scrutiny risk if Juno's content generation is tailored to specific disease management rather than general note translation.

#### FDA 510(k) and De Novo Pathways (If Required)

If FDA jurisdiction were triggered:
- **510(k):** Premarket notification for devices substantially equivalent to a legally marketed predicate device. Most AI health software that is regulated has gone through 510(k). Over 97% of AI-enabled devices cleared via 510(k) as of 2024.
- **De Novo:** For novel low-to-moderate risk devices with no predicate. Establishes a new device type.
- **PMA (Premarket Approval):** For high-risk Class III devices. Unlikely to apply to Juno.

#### FDA Recommendation for Juno

1. Retain a qualified FDA regulatory counsel or consultant to formally assess intended use and prepare a written regulatory strategy memo before commercial launch
2. Create a "regulatory justification file" documenting why Juno is not a medical device
3. Design all marketing, labeling, and product UI consistent with "patient education/communication tool" — not "clinical tool"
4. Implement a product change review process to evaluate whether new features trigger device status
5. Monitor FDA's forthcoming consolidated digital health guidance (Commissioner Makary signaled updates in early 2026)

---

### FTC Health Breach Notification Rule

**What it is:** The FTC's Health Breach Notification Rule (HBNR), updated in a final rule effective July 29, 2024, requires companies not covered by HIPAA (or that fall outside HIPAA's scope for certain activities) to notify individuals, the FTC, and in some cases the media when there is an unauthorized disclosure of personal health information.

**Who it covers:** The updated rule explicitly covers:
- Vendors of Personal Health Records (PHRs) — apps that collect health information from multiple sources
- PHR-related entities — apps that access or send health data to/from PHRs
- Third-party service providers to the above

**Does it apply to Juno?**

This requires careful analysis. Juno operates as a HIPAA Business Associate of covered entity clinics — the clinic is the covered entity, and Juno receives PHI under a BAA. If Juno is properly operating as a business associate, HIPAA's Breach Notification Rule (not FTC HBNR) would govern breach notifications.

**Risk scenario:** If there is ever a question about whether Juno's patient-side engagement constitutes a "PHR" (because patients interact directly with Juno-generated content), Juno could potentially fall under FTC HBNR jurisdiction for that patient-facing component. The 2024 FTC update broadly extended HBNR to apps that "access or send" health information.

**Conservative approach:** Juno should maintain breach notification procedures that satisfy both HIPAA and HBNR requirements, including:
- Notifying affected individuals within 60 days of discovering a breach
- Notifying the FTC for breaches affecting 500+ individuals
- Notifying media for breaches affecting 500+ residents in a state

**FTC Act Section 5:** Separately, FTC Act Section 5 (prohibiting unfair or deceptive practices) applies to all companies including healthcare tech. Juno must not make false or misleading claims about:
- How it handles patient data (data use must match privacy policy)
- AI capabilities or accuracy ("Juno never makes errors" would be deceptive)
- Security practices claimed but not implemented

---

### 42 CFR Part 2 (Substance Use Disorder Records)

**What it is:** 42 CFR Part 2 provides heightened privacy protections for records created in connection with federally-assisted Substance Use Disorder (SUD) treatment programs. These protections are stricter than HIPAA and historically required patient-specific consent for nearly every disclosure.

**2024 Final Rule changes (compliance date: February 16, 2026):**
- Allows single consent for all future uses and disclosures for treatment, payment, and health care operations
- Allows HIPAA-covered entities that receive Part 2 records under consent to redisclose under HIPAA rules
- Removes requirement for data segregation
- Each disclosure/re-disclosure must still be accompanied by a statement that records are covered by Part 2

**Does it apply to Juno?**

Juno does not operate a federally-assisted SUD treatment program, so it is not itself a Part 2 "program." However:

- If a neurology clinic using Juno also treats patients for SUD, and those clinical notes are transmitted to Juno, any SUD-related information in those notes carries Part 2 protections
- Juno must be able to identify and handle Part 2-protected information appropriately when it appears in clinical notes

**Practical implication:** Juno should include Part 2 handling obligations in its BAA with clinic customers, include a data processing note that Part 2 data must be flagged by the clinic before transmitting to Juno, and design its AI processing pipeline to handle Part 2 data in compliance with applicable disclosure limitations. For the initial Neurology focus, direct SUD records exposure is lower risk — but as Juno expands to other specialties, this becomes more important.

---

### Other Federal Requirements

**FERPA (Family Educational Rights and Privacy Act):** FERPA applies to educational records at schools/universities. If Juno ever deploys in a pediatric clinic affiliated with a school system or a hospital's educational program, FERPA could apply to certain records. For the primary care/neurology clinic focus, FERPA is not a current concern.

**Section 504 / ADA Accessibility:** Patient-facing content (the shareable patient guidance link) should be accessible to patients with disabilities. WCAG 2.1 AA compliance is a reasonable target for patient-facing web content. Not a hard regulatory requirement for Juno, but increasingly expected by health systems and important for serving patients with disabilities (who are disproportionately represented in neurology).

---

## State Privacy Law Landscape

### High-Risk States for Juno

**California — Two Overlapping Laws:**

*CMIA (Confidentiality of Medical Information Act):* California's medical privacy law is broader than HIPAA in several ways. CMIA applies to any "provider of health care" — which has been interpreted expansively and could capture some health tech companies. CMIA requires written authorization before using or disclosing medical information except for treatment, payment, or operations purposes. Violations can result in civil penalties of $1,000 per violation plus actual damages. AI systems in California must document consent for medical information uses that exceed HIPAA's TPO exceptions.

*CPRA (California Privacy Rights Act):* The CPRA established health information as "sensitive personal information" requiring enhanced protections. However, CPRA provides a partial exemption for medical information governed by CMIA and HIPAA-protected information. CPRA is most relevant to Juno for any health data that falls *outside* HIPAA's scope — e.g., anonymous or de-identified data, data from non-covered entity interactions. As of 2025, the California Privacy Protection Agency is drafting Automated Decision-Making Technology (ADMT) regulations that would impose pre-use notices, access rights, and opt-out options for automated systems processing sensitive data.

**Practical implication:** For clinic customers in California, Juno's BAA and consent framework must address CMIA requirements, not just HIPAA. A California-specific addendum to the clinic services agreement may be advisable.

**Washington — My Health MY Data Act (MHMDA, 2023):**

This is the strictest state health privacy law in the country for purposes relevant to Juno. Key features:

- Covers **any** entity that collects "consumer health data" of Washington residents, regardless of HIPAA status
- Defines "consumer health data" extremely broadly: any personal information that "identifies the consumer's past, present, or future physical or mental health status" — including inferential health data
- Requires **explicit, opt-in consent** before collecting or sharing consumer health data
- Requires separate consent for data sharing beyond initial collection purpose
- Grants consumers rights to access, withdraw consent, and delete health data
- Applies to B2B processors — data processing agreements with processors are required
- Enforcement: Washington Consumer Protection Act, plus **private right of action** (significant litigation risk)
- Geofencing restrictions around health facilities (not directly relevant to Juno's model)

**B2B Shield Analysis for Washington:** Operating as a B2B vendor selling to clinics does not fully shield Juno from MHMDA. The law reaches "regulated entities" that "determine the purpose and means of collecting, processing, sharing, or selling consumer health data." Juno processes patient health data and determines how its AI model uses that data. Even if the clinic is the primary regulated entity, Juno as a processor still needs to enter into data processing agreements with its clinic customers that comply with MHMDA requirements.

The more significant risk: if Juno's patient-facing engagement portal constitutes direct collection of "consumer health data" from patients (e.g., tracking engagement, collecting adherence data, receiving patient-entered information), Juno may itself be a "regulated entity" under MHMDA with respect to those patient interactions.

**Texas — HB 300 (Texas Medical Privacy Act):**

Texas HB 300 expands HIPAA protections in several ways:
- Applies HIPAA-equivalent obligations to a broader category of entities than federal HIPAA covers (including IT service providers, sports teams, and others not typically covered by HIPAA)
- Business Associates in Texas are treated as covered entities under Texas law — Juno, as a BA to Texas clinics, has direct obligations under Texas law
- BAs must provide annual evidence of security risk analyses
- BAAs must specify who notifies patients in case of breach and who bears the cost
- Additional training requirements for employees handling PHI
- Annual compliance training documentation required

**Colorado — SB 24-205 (Colorado AI Act, effective February 1, 2026):**

Colorado's first-in-nation AI regulation targets "high-risk AI systems" that make or "substantially influence" consequential decisions in healthcare. Key requirements:

- Developers of high-risk AI must provide deployers with: intended uses, known limitations, training data documentation, evaluation metrics, and risk mitigation guidance
- Deployers must implement AI risk management policies, conduct impact assessments, and provide consumers with notice of adverse AI-influenced decisions
- "Healthcare" is explicitly listed as a high-risk domain
- If Juno's AI outputs substantially influence clinical decisions (even indirectly, through patient adherence affecting outcomes), the Colorado Act may apply

**Practical implication:** Juno should document its AI model's intended uses, known limitations, and evaluation methodology now. This documentation will be needed for Colorado Act compliance by Feb 2026 and is good practice regardless.

**Illinois — BIPA (Biometric Information Privacy Act):**

BIPA covers biometric identifiers (fingerprints, retina scans, face geometry, voiceprints). Juno's current product (text-based note translation) does not collect biometric data, so BIPA is not currently relevant. If Juno ever adds voice-based patient interactions or video features, BIPA analysis would be required.

**New York — SHIELD Act:**

NY SHIELD Act requires any company possessing "private information" of New York residents to implement a reasonable data security program. Medical information is explicitly included in "private information." The Act:
- Applies to any company holding NY resident data, regardless of where the company is located
- Requires written security policies, employee training, role-based access, encryption, vendor oversight, and incident response
- Breach notification requirements broader than federal HIPAA (unauthorized "access" triggers notification, not just "acquisition")
- A HIPAA Security Rule violation is also a SHIELD Act violation (as held in 2024 precedent)

**Practical implication:** Juno's HIPAA Security Rule compliance will substantially satisfy NY SHIELD Act requirements, but the breach notification standard is different and must be addressed separately.

**Nevada, Florida, and Other States:** Nevada AB 406 (2025) prohibits AI-delivered mental/behavioral healthcare therapy — not directly relevant to Juno's neurology focus but relevant if Juno expands to behavioral health use cases. Florida's HB 1459 and other state laws are creating a patchwork of AI-specific requirements. Juno should monitor the IAPP and healthcare law blogs for state AI law developments, as at least 7 additional states passed new privacy laws in 2024 alone.

### B2B Shield Analysis (Does Selling to Clinics Protect Juno from Consumer Laws?)

**Answer: Partial shield, not complete protection.**

The B2B business model provides meaningful protection in some contexts:
- For laws that specifically target "businesses" vs. "processors" with different obligations (CPRA), clinic-side obligations are primarily the clinic's
- For laws like HIPAA that define Juno as a Business Associate, the regulatory framework clearly allocates responsibilities
- For most contract-based obligations, the clinic bears primary patient-facing compliance responsibility

However, the B2B shield fails in important situations:
- **Washington MHMDA** explicitly covers processors and requires data processing agreements — the law flows down
- **Colorado SB 24-205** imposes obligations on AI *developers*, not just deployers
- **Texas HB 300** treats BAs as covered entities with direct obligations
- When Juno's patient-facing portal *directly receives data from patients* (engagement data, adherence tracking, patient-entered information), Juno may be a first-party collector, not just a B2B processor

**Recommendation:** Juno should not rely on B2B framing as a compliance strategy. Instead, design the product to comply with patient-protective requirements as a matter of practice, and use the BAA/DPA structure with clinics to allocate compliance responsibilities contractually.

### State Law Compliance Strategy

**Priority approach for Juno:**
1. Design core data handling practices to satisfy the strictest applicable requirements (Washington MHMDA, California CMIA) — this ensures compliance in all states
2. Add California- and Texas-specific contractual addenda for clinic customers in those states
3. Include MHMDA data processing agreement language in all clinic contracts (not just Washington clinics, given the broad definition of who can be a "Washington consumer")
4. Document AI model information for Colorado Act compliance
5. Maintain a state-by-state compliance tracker updated at least annually

---

## EHR Vendor Requirements

### Athena Health Integration Requirements

Athena Health is Juno's primary planned EHR integration. Here is what is required:

**Technical Prerequisites:**
- OAuth 2.0 authentication for all API access (mandatory — no exceptions)
- Practice must explicitly authorize Juno's application before Juno can access data
- All data exchange must use HTTPS/TLS
- API rate limits and usage policies must be followed

**Business / Legal Requirements:**
- **Marketplace Partner Agreement:** Juno must apply to the Athena Marketplace program and be accepted before accessing production data at scale. This involves:
  - Submitting application, business model, and integration plan
  - Security assessment (data encryption, access controls, HIPAA compliance, pen test results)
  - UX review if the app is embedded in the clinical workflow
  - Compliance verification (HIPAA compliance + BAA execution)
- **Business Associate Agreement (BAA):** Athena executes BAAs with all marketplace partners handling PHI. This must be signed before any production PHI flows
- **Revenue Share:** Athena charges 15–30% revenue share on Marketplace-channeled transactions (exact rate negotiated)
- **Data Use Agreement:** Athena's terms restrict how partner apps can use data obtained through the API — PHI obtained through the integration cannot be used to train general AI models or for purposes beyond serving the specific practice

**Timeline:** Marketplace approval takes approximately **6–12 weeks** (faster than Epic). Development + approval combined typically 3–5 months.

**Athena's Own Certifications (context for partner expectations):** Athena maintains HITRUST CSF certification, SOC 1, PCI-DSS, EPCS, DirectTrust, and ONC certification. Partners are expected to meet comparable standards appropriate to their role.

**Recommendation for Juno:** Do not attempt to access Athena production APIs using individual practice credentials (OAuth tokens obtained from individual clinics) without going through the Marketplace partner process. This is a terms of service violation and could result in API access termination.

### General EHR Marketplace Requirements

**Epic Showroom (formerly App Orchard):**
Epic reorganized its marketplace in 2024 from "App Orchard" to "Showroom" with three tiers:
- **Connection Hub** ($500/year): Basic integration listing
- **Toolbox**: Clinical workflow tools with deeper review
- **Workshop**: Enterprise-level integrations and co-development

For a patient engagement tool like Juno, the Toolbox tier is most likely applicable.

Timeline: Application + listing takes **8–16 weeks** for Showroom review after development completion. Development of SMART on FHIR apps typically adds 12–20 weeks. Total: **5–9 months** from development start to production listing.

Requirements: SMART on FHIR / FHIR R4 compliance, security review, clinical workflow review, Epic customer sponsor (production access requires a customer to request/sponsor the integration).

**Oracle Health / Cerner:**
- Must join Oracle Partner Network (OPN) first
- Register application in Oracle Health Code Console
- Complete Demonstration Services Addendum
- Migration underway to Oracle Cloud Infrastructure (OCI) — integration architecture is in transition
- Supports FHIR R4 (Ignite APIs), HL7 v2, and CCDA exchange

### Common Security Assessment Frameworks Required by EHR Vendors and Health Systems

| Framework | Who Uses It | Scope | Required vs. Common |
|---|---|---|---|
| **SIG (Standardized Information Gathering)** | Large health systems, TPAs, payers | 18 risk domains, comprehensive | Very common; often required |
| **CAIQ (Cloud Security Alliance)** | Cloud-heavy organizations | Cloud-specific controls | Common for cloud SaaS |
| **Custom questionnaires** | Most health systems | Variable | Universal — every health system has their own |
| **SOC 2 Type II report** | All levels | Trust Service Criteria | Increasingly required, especially >$100K deals |
| **HITRUST certification** | Mid-market and above | Healthcare-specific CSF | Required for large health systems |
| **Pen test report** | Mid-market and above | Application + infrastructure | Expected, 12-month-old or newer |

The SIG questionnaire was updated in 2024 with 11 new regulatory mappings and is now used by over 10,000 organizations globally. Juno should prepare SIG Lite responses proactively and maintain them as a standing vendor security document.

---

## Industry Standards & Certification Frameworks

### HITRUST CSF — Recommendation for Juno

**What it is:** The Health Information Trust Alliance Common Security Framework (HITRUST CSF) is a prescriptive, healthcare-specific security certification framework that maps to HIPAA, NIST, ISO 27001, SOC 2, and other standards. It has become the de facto certification standard for healthcare vendors selling to mid-size and large health systems.

**Three Certification Levels:**

| Level | Controls | Scope | Best For | Cost | Timeline |
|---|---|---|---|---|---|
| **e1 (Essentials)** | 44 essential controls | Basic assessment | Very early-stage, small practices only | $30K–$50K | 3–4 months |
| **i1 (Implemented)** | 44 + additional threat/access controls | Implemented controls verified | Mid-market health systems; most common | $50K–$100K | 6–9 months |
| **r2 (Risk-based)** | 200+ controls | Full maturity scoring, 5 levels | Large health systems, enterprise | $100K–$500K+ | 12–15 months |

**Market reality:** The i1 certification is the most commonly required level in vendor contracts. For UnitedHealth Group, Kaiser Permanente, Anthem, and other major payers and health systems, HITRUST is now "non-negotiable" rather than a differentiator. Enterprise deals above $250K ACV will almost always require HITRUST.

**Recommendation for Juno:** Target HITRUST i1 as the certification to achieve before pursuing mid-size health system deals. Plan 9–12 months for preparation and certification. Budget $60K–$120K all-in (assessor fees + HITRUST fees + internal preparation costs). SOC 2 Type II should be completed first since 50–70% of SOC 2 work can be leveraged for HITRUST, significantly reducing cost and time.

**HITRUST and HIPAA:** HITRUST CSF explicitly maps controls to HIPAA Privacy, Security, and Breach Notification Rules. A HITRUST-certified organization has effectively demonstrated HIPAA security compliance in a third-party verified, structured format. Many health system vendor risk teams accept HITRUST certification as HIPAA compliance evidence without requiring a separate HIPAA assessment.

### SOC 2 Type II — Timeline and Relevance

**What it is:** SOC 2 (Service Organization Control 2) is an AICPA-defined audit framework assessing a service organization's controls across five Trust Service Criteria: Security, Availability, Processing Integrity, Confidentiality, and Privacy. Type II means the controls were in place and operating effectively over an observation period (minimum 6 months, typically 12 months).

**Why it matters for Juno:** SOC 2 Type II is the baseline security credential expected by virtually all B2B SaaS customers, including small-to-mid-size clinic customers. Without SOC 2, Juno will face recurring friction in every sales cycle as prospects attempt to assess security through custom questionnaires.

**Cost:** $30K–$80K for Type II depending on auditor and scope. SOC 2 + HIPAA combined assessments are available from specialized healthcare auditors and can save $10K–$20K compared to separate assessments.

**Timeline:**
- Readiness assessment + gap remediation: 2–4 months
- Observation period: 6–12 months
- Audit and report: 4–8 weeks
- **Total time to Type II report: 9–14 months from start**

**Recommendation:** Start SOC 2 Type II process within the first 6 months of operations. Type I (snapshot in time, no observation period) can be obtained faster (4–6 months) and used as an interim credential, with Type II following.

**Trust Service Criteria most relevant to Juno:**
- **Security (CC):** Universal and required for all SOC 2
- **Confidentiality:** Highly relevant given PHI handling
- **Privacy:** Relevant to patient data handling
- **Availability:** Relevant for clinic reliance on the platform

### ISO 27001 and NIST — Relevance Assessment

**ISO 27001:**
ISO 27001 is the international information security management system standard. In the US healthcare market, it has been increasingly demanded by large health systems, particularly those with international affiliations or academic medical centers doing global research. Key facts:

- Increasingly appearing in large health system RFPs alongside SOC 2 and HITRUST
- Certification cost: $25K–$80K for initial certification; annual surveillance audits $5K–$15K
- Timeline: 6–12 months
- 50–70% control overlap with SOC 2 — can be pursued in parallel cost-efficiently

**Relevance for Juno (current stage):** ISO 27001 is a "Tier 3" requirement — needed for large academic medical centers and international expansion. Not required for initial market entry.

**NIST Cybersecurity Framework (CSF 2.0):**

NIST CSF 2.0 (released 2024) is voluntary but:
- The HIPAA Safe Harbor Law directs regulators to consider NIST-based framework adoption when assessing breach penalties — documented NIST alignment can reduce penalty exposure
- Many health systems expect vendors to reference NIST alignment in security documentation
- NIST alignment is inherent in HITRUST (HITRUST maps to NIST)
- Adopting NIST CSF 2.0 framework documentation costs little and provides meaningful risk management benefit

**NIST AI Risk Management Framework (AI RMF 1.0):**

Released January 2023 with the Generative AI Profile released July 2024. Voluntary for all sectors. Organized around four functions: Govern, Map, Measure, Manage.

For Juno, NIST AI RMF adoption provides:
- A framework for documenting AI model governance, risk assessment, and bias monitoring
- Credibility with health system customers who ask "how do you manage AI risk?"
- Documentation that supports Colorado SB 24-205 impact assessment requirements
- Protection against FTC scrutiny if Juno's AI ever fails or produces harmful outputs

**Recommendation:** Adopt NIST AI RMF governance documentation internally now. It is low cost, high credibility, and required for Colorado Act compliance.

### Comparison Table: Required vs. Nice-to-Have

| Framework | Small Clinics | Mid-Size Health Systems | Large / Academic Health Systems | Notes |
|---|---|---|---|---|
| **BAA** | Required | Required | Required | Non-negotiable |
| **HIPAA compliance** | Required | Required | Required | Fundamental |
| **SOC 2 Type II** | Expected | Required | Required | Get this first |
| **Pen test (annual)** | Sometimes asked | Usually required | Required | Budget $15K–$40K/year |
| **HITRUST i1** | Nice-to-have | Often required | Required | Plan for Year 2 |
| **HITRUST r2** | Not required | Nice-to-have | Often required | Year 3+ |
| **ISO 27001** | Not required | Nice-to-have | Increasingly required | Year 3+ or international |
| **NIST CSF** | Not required | Nice-to-have | Nice-to-have | Adopt internally now |
| **NIST AI RMF** | Not required | Emerging | Emerging | Document now |
| **SIG questionnaire** | Rarely | Often | Always | Prepare proactively |

---

## AI-Specific Compliance

### FDA Clinical Decision Support Analysis (CRITICAL)

Addressed comprehensively in the Federal Regulations section above. Summary:

**Juno's most defensible FDA position:**
- Product is a "patient communication and education tool" that reformats clinical language
- Does not provide medical advice, clinical recommendations, or treatment guidance
- Does not analyze clinical data to generate diagnoses or treatment plans
- HCP (the ordering clinic) remains fully responsible for clinical decisions
- Juno's output is reviewed/approved by the ordering clinic before delivery to patient

**What must remain true to maintain this position:**
- No algorithmic clinical recommendations in output (not "you should take X medication," only "your doctor prescribed X medication, here is what it does")
- Output is grounded in the provided clinical note — Juno does not add clinical information not in the source note
- Clear disclaimers that output is not a substitute for clinical advice
- Clinic reviews and controls what is sent to patients (not fully automated without clinical oversight)

**Biggest risk:** A future feature or marketing claim that positions Juno as providing clinical guidance rather than educational translation. The product team and marketing must operate with FDA intended use guardrails in mind.

**Bottom line on FDA:** Juno likely does not need FDA clearance under current product design — but this is not a settled, low-risk determination. It requires attorney review, documented rationale, and ongoing monitoring as the product evolves and FDA guidance updates.

### NIST AI RMF and AMA Guidelines

**AMA Guidelines:** The American Medical Association established policies in 2024 requiring that:
- AI tools augment, not replace, physician judgment
- Physicians using AI "accept responsibility for responding appropriately to AI recommendations"
- Failure to apply human judgment to AI output "is a violation of a physician's professional duties"
- AI tools must be transparent about how they work and their limitations

**Implications for Juno's clinic customers:**
- The clinics using Juno must review Juno's output before it reaches patients — or must make an informed decision to authorize automated delivery with appropriate oversight
- Juno should design its product so clinics can review, edit, and approve content before patient delivery
- If Juno offers fully automated (no physician review) delivery, clinics should be made aware of their professional responsibility obligations
- Juno's sales process should include a discussion of physician responsibility and appropriate oversight models

**NIST AI RMF Practical Steps for Juno:**

| Function | Actions for Juno |
|---|---|
| **Govern** | Establish AI governance policy; designate AI risk owner; document acceptable use |
| **Map** | Catalog AI use cases (Gemini for note translation); identify affected populations (patients with neurological conditions); document risks (hallucination, clinical error) |
| **Measure** | Define accuracy metrics for translated content; implement QA review sampling; track patient and clinic feedback on output quality |
| **Manage** | Incident response plan for AI errors; process for clinics to flag and correct problematic output; escalation path to clinical review |

### Patient Consent for AI Processing

**Federal level (HIPAA):** HIPAA does not require explicit patient consent for AI-processing of PHI when the purpose is treatment, payment, or healthcare operations. Translating clinical notes to improve patient understanding falls within "treatment" operations. Clinics' existing Notice of Privacy Practices (NPP) typically authorize use of PHI for treatment purposes, which covers Juno's function.

**Key HIPAA limit:** If Juno or its AI provider (Google/Gemini) uses PHI to train its AI models, that requires explicit patient authorization beyond standard HIPAA TPO consent. Juno's Google Cloud / Gemini contract must explicitly prohibit use of processed PHI for model training, and this prohibition must flow down through Juno's BAA with clinics.

**State-specific consent considerations:**
- **California:** CMIA may require explicit authorization for AI processing of medical information beyond HIPAA TPO purposes — especially for any uses that aren't purely "treatment"
- **Washington MHMDA:** Requires opt-in consent before collecting or sharing "consumer health data" — if patients directly interact with Juno's portal, separate patient consent is advisable
- **All-party consent states:** 11 states require all-party consent for recording conversations. If Juno ever adds voice features, these laws apply

**Best practice for Juno:** Work with clinic customers to include a Juno-specific disclosure in their patient consent forms or NPP: "We may use a technology platform (Juno Health) to translate your clinical notes into plain-language educational materials delivered to you. This platform uses AI to prepare these materials. Your information is not used to train AI models."

### IRB Considerations

**The quality improvement vs. research distinction:**

- **Research** (requires IRB): "A systematic investigation designed to develop or contribute to generalizable knowledge" — publishing findings, testing hypotheses about patient populations
- **Quality Improvement** (no IRB): Activities aimed at improving care at a specific facility using established practices

**Does Juno require IRB approval?**

In most cases, **no** — if Juno's function is:
- Delivering care education to individual patients (operational/clinical)
- Processing notes to improve communication efficiency (quality improvement)
- Tracking engagement for the treating clinic's purposes (operational)

IRB approval *would* be required if Juno:
- Conducts or participates in research studies using patient data
- Analyzes aggregate patient data to generate generalizable scientific conclusions published or presented externally
- Partners with academic medical centers for research on AI in patient education

**Practical guidance:** If Juno collects aggregate engagement/adherence data and publishes findings (e.g., "Juno improves medication adherence by X% in MS patients"), this could constitute research requiring IRB oversight. Any publication or external presentation of aggregate patient data should be reviewed by the clinic's IRB or equivalent. Juno should explicitly disclaim research activities in its clinical agreements.

---

## Clinical Deployment Requirements

### Vendor Security Assessment Process

**What health systems typically require before allowing a vendor to connect:**

1. **Security Questionnaire:** SIG, CAIQ, or custom — typically 100–400 questions covering access controls, encryption, incident response, vulnerability management, employee training, physical security, and business continuity
2. **SOC 2 Type II Report:** Auditor's report reviewed by health system security team — typically requires report to be <12 months old
3. **HITRUST Certification Letter:** For mid-size and above — current certification status letter from HITRUST Alliance
4. **Penetration Test Report:** Most health systems require an annual third-party pen test. Reports must be <12 months old; executive summary + remediation status typically sufficient for initial review
5. **BAA Execution:** Signed before any PHI is shared
6. **Privacy Policy and Terms of Service Review:** By health system legal/compliance
7. **On-site or virtual security assessment:** For larger deals, health system CISO team may conduct a live technical review

**Penetration testing:**
- Scope: Application-level pen test + infrastructure (cloud) pen test
- Frequency: Annual minimum; after major code changes
- Provider: Must be a qualified third-party security firm (not internal testing)
- Cost: $15,000–$40,000 per engagement depending on scope
- Budget for this annually from Day 1 of production operations

**Vulnerability Disclosure Program:** Large health systems increasingly expect vendors to have a responsible disclosure policy. Consider implementing a simple VDP via Bugcrowd or HackerOne — this is low cost and signals security maturity.

### Typical Contract Requirements

**Business Associate Agreement (BAA):**
- Required before any PHI handling
- Governs permitted uses and disclosures of PHI on behalf of the clinic
- Juno's BAA template must be reviewed by healthcare legal counsel
- Must address: Google Cloud/Gemini sub-processor chain (downstream BAA from Google is required)
- Must specify AI model training restriction: PHI cannot be used to train AI models without patient authorization

**Data Processing Agreement (DPA):**
- Required by GDPR for EU-based clinic customers (if any); increasingly expected by US clinic customers for Washington MHMDA and California CPRA compliance
- Documents data processing activities, retention periods, deletion procedures, and processor obligations

**Security Addendum:**
- Many mid-size health systems append a security addendum to vendor contracts specifying minimum security controls: MFA, encryption at rest and in transit, annual pen testing, security incident notification within 24 hours

**Indemnification:**
- Clinics will typically require Juno to indemnify them for:
  - PHI breaches caused by Juno's negligence or failure
  - AI-generated content errors that cause patient harm (contested but increasingly included)
  - Third-party IP infringement in AI outputs
  - Regulatory penalties arising from Juno's non-compliance
- Juno should negotiate liability caps (typically 12 months of contract value for AI companies) and insurance requirements as the indemnification backstop
- Clinical Decision Support / patient safety indemnification is a heightened area of negotiation risk — Juno's "translation not interpretation" positioning is directly relevant here

**SLA Requirements:**
- Healthcare SaaS is expected to maintain:
  - **Uptime:** 99.9% or higher (health system contracts often require 99.99%)
  - **Incident response:** Security incidents reported within 24–72 hours
  - **Data retention and deletion:** Typically 7 years for medical records (state-specific)
  - **Disaster recovery:** Recovery Time Objective (RTO) and Recovery Point Objective (RPO) specified — typical targets: RTO 4 hours, RPO 1 hour
- Consider Firebase/Firestore SLA (Google provides 99.99% SLA) as the underlying commitment for Juno's SLA

### Cyber Insurance Requirements

**What clinics require of vendors:**

Most clinic contracts require vendors to maintain:
- **Cyber liability / Technology E&O:** $1M–$5M per occurrence for small-mid vendors; $5M–$10M for vendors handling sensitive data at scale
- **General liability:** $1M–$2M per occurrence
- **Professional liability:** $1M–$3M (errors and omissions)
- **Workers' compensation:** As legally required

**2024–2025 market context:**
- Cyber insurance premiums for healthcare technology companies have increased substantially following major breaches (Change Healthcare 2024, etc.)
- Carriers now require MFA, EDR (endpoint detection and response), encrypted backups, and incident response plans as prerequisites for coverage
- Annual cost for $2M cyber liability policy for a healthcare SaaS startup: approximately $15,000–$40,000/year depending on security posture

**Recommendation for Juno:** Obtain $2M cyber liability / tech E&O coverage before first clinic contract is signed. This is a standard contractual requirement and demonstrates maturity to prospects.

---

## Practical Procurement Timeline

How long does it typically take to get approved as a vendor and go live?

| Stage | Small Clinic (1–5 providers) | Mid-Size Health System (50–500 beds) | Large Academic Medical Center (500+ beds) |
|---|---|---|---|
| **Initial contact to proposal** | 1–2 weeks | 2–6 weeks | 4–12 weeks |
| **Security questionnaire / review** | None or informal | 4–8 weeks | 8–16 weeks |
| **IT review and BAA negotiation** | 1–2 weeks | 4–8 weeks | 8–16 weeks |
| **Legal / contract review** | 1–2 weeks | 4–8 weeks | 8–16 weeks |
| **EHR integration setup (Athena)** | 1–2 weeks | 2–4 weeks | 4–8 weeks |
| **Go-live / training** | 1–2 weeks | 2–4 weeks | 4–8 weeks |
| **TOTAL (typical range)** | **1–2 months** | **3–6 months** | **6–18 months** |

**Key factors that extend timelines:**
- Missing SOC 2 report (adds 3–6 months for health systems that require it)
- BAA negotiation disputes (legal teams at large systems can take months)
- EHR vendor marketplace approval (6–12 weeks for Athena; 3–5 months for Epic)
- CISO or compliance officer backlog (health system security teams are severely understaffed)
- Clinical champion departure or turnover (frequently resets procurement process)

**Stakeholders involved in healthcare vendor decisions:**
- **Small clinic:** Practice administrator, physician owner, IT vendor/MSP
- **Mid-size health system:** CISO/Security team, Compliance officer, CMO, IT/EHR team, Legal, Department head (clinical champion)
- **Large academic medical center:** All of above + IRB consultation, Procurement/GPO committee, Finance, Privacy officer, sometimes Board-level approval for significant AI deployments

**Common deal killers:**
1. No SOC 2 or HITRUST certification (automatic disqualifier at mid-market and above)
2. No signed BAA template ready to negotiate
3. Data retention/deletion practices inconsistent with clinic requirements
4. AI model training restrictions absent from BAA/DPA
5. Pen test results showing high/critical vulnerabilities not remediated
6. Cyber insurance insufficient or unavailable
7. No incident response plan
8. Marketing claims suggesting clinical decision support (FDA risk question raised)
9. Inability to answer "how does your AI work" questions (explainability concerns)
10. Legal / indemnification terms unacceptable (common for small startups without established vendor terms)

---

## Compliance Priority Roadmap for Juno

### Tier 1: Must-Have Before First Clinic Customer

These items should be completed before executing any agreement involving PHI:

| Item | Action | Timeline | Cost Estimate |
|---|---|---|---|
| **HIPAA compliance program** | Implement administrative, physical, and technical safeguards; complete risk analysis; document policies | Month 1–2 | $5K–$15K (consultant) |
| **BAA template** | Draft and have healthcare counsel review | Month 1 | $2K–$5K (legal) |
| **Google Cloud / Gemini BAA** | Execute BAA with Google (Google Cloud offers BAA as part of Business or Enterprise agreements) | Month 1 | Included in GCP contract |
| **Privacy Policy + Terms of Service** | Healthcare-aware privacy policy and ToS; include AI processing disclosure | Month 1 | $2K–$5K (legal) |
| **AI model training restriction** | Confirm in contract with Google that PHI processed through Gemini is not used for model training | Month 1 | Part of GCP agreement |
| **Cyber insurance** | Obtain $2M cyber liability / tech E&O policy | Month 1–2 | $15K–$40K/year |
| **Incident response plan** | Written IR plan with roles, notification timelines (24-hour), escalation procedures | Month 1–2 | $2K–$5K (template + customization) |
| **FDA regulatory analysis** | Retain healthcare regulatory counsel to document intended use and non-device regulatory rationale | Month 1–3 | $5K–$15K (regulatory attorney) |
| **Data retention and deletion policy** | Define retention periods and deletion procedures consistent with medical record requirements | Month 1–2 | Internal |
| **SOC 2 Type I (interim)** | Begin readiness; obtain Type I as interim credential | Month 4–6 | $15K–$30K |

### Tier 2: Required for Mid-Market Health Systems ($50K–$250K ACV)

| Item | Action | Timeline from Launch | Cost Estimate |
|---|---|---|---|
| **SOC 2 Type II** | Complete 12-month observation period and audit | Month 12–18 | $30K–$80K |
| **Annual penetration test** | Engage qualified third-party security firm | Month 6 (annually thereafter) | $15K–$40K/year |
| **SIG questionnaire preparation** | Prepare standardized SIG Lite response document | Month 3–6 | Internal + $2K–$5K (consultant) |
| **NIST AI RMF documentation** | Document AI governance framework, risk register, model cards | Month 3–6 | Internal |
| **Colorado SB 24-205 compliance** | AI impact assessment; developer documentation; update contracts | Before Feb 2026 | $3K–$8K (legal) |
| **Washington MHMDA DPA language** | Add MHMDA-compliant data processing agreement language to all clinic contracts | Month 2–3 | $2K–$5K (legal) |
| **Athena Marketplace certification** | Complete Athena partner program application and security assessment | Month 3–5 | $0 (time cost primarily) |
| **Vulnerability disclosure program** | Establish basic VDP policy; consider Bugcrowd/HackerOne | Month 6 | $5K–$15K/year |

### Tier 3: Required for Large Health System / Enterprise Deals ($250K+ ACV)

| Item | Action | Timeline from Launch | Cost Estimate |
|---|---|---|---|
| **HITRUST i1 certification** | Full HITRUST i1 assessment; requires SOC 2 as foundation | Month 18–30 | $60K–$120K |
| **ISO 27001** | If pursuing academic medical centers or international expansion | Month 24–36 | $30K–$80K |
| **Epic Showroom listing** | Apply for Epic integration listing; requires Epic customer sponsor | Month 12–18 | $500–$1,000/year |
| **Enhanced BAA / Security Addendum** | Negotiate enterprise-grade terms with clinical indemnification provisions | Ongoing | Legal costs |
| **AI ethics / bias documentation** | Formal bias assessment of Gemini outputs for healthcare equity | Month 12–18 | $5K–$20K |
| **HITRUST r2** | If required by specific enterprise customers (rare for patient engagement tools) | Month 36+ | $100K–$300K |

---

## Open Questions / Legal Counsel Required

The following items require qualified healthcare regulatory and/or technology counsel before Juno takes a definitive position:

1. **FDA Intended Use Analysis:** Is Juno's current product design definitively outside FDA device jurisdiction? What specific language in product, marketing, and contracts establishes this? What product changes would cross the line? **Requires FDA regulatory attorney with digital health experience.**

2. **Washington MHMDA — When is Juno a "Regulated Entity" vs. "Processor"?** Does Juno's patient-facing portal constitute direct health data collection from patients, making Juno a regulated entity under MHMDA in addition to (or instead of) the clinic? **Requires privacy attorney with Washington MHMDA expertise.**

3. **California CMIA Analysis:** Do Juno's activities constitute Juno becoming a "provider of health care" subject to CMIA, or does operating as a BA under a HIPAA-governed relationship keep Juno outside CMIA's direct scope? **Requires California healthcare privacy attorney.**

4. **Colorado SB 24-205 Applicability:** Does Juno's AI (Gemini-based note translation) constitute a "high-risk AI system" making or "substantially influencing" consequential decisions in healthcare? What documentation does Colorado require of Juno as a developer vs. its clinic customers as deployers? **Requires Colorado attorney or AI law specialist.**

5. **42 CFR Part 2 Data Handling:** What contractual and technical obligations must Juno impose on clinic customers to ensure Part 2 data is not inadvertently transmitted to Juno without appropriate protections? **Requires HIPAA / Part 2 counsel.**

6. **AI Model Training Restrictions in Google Cloud Contract:** Exactly what protections does Google Cloud's BAA and terms provide regarding PHI processed through Gemini? Does the standard Business Associate Agreement with Google prohibit Gemini from using PHI for model improvement? **Requires review of current GCP agreement and confirmation with Google's healthcare team.**

7. **IRB Threshold:** At what point does Juno's collection and analysis of aggregate engagement/adherence data become "research" requiring IRB oversight? Specifically, if Juno publishes case studies or outcome data from clinic deployments, what IRB path is needed? **Requires IRB consultant or research compliance attorney.**

8. **Indemnification Caps for AI Errors:** What is an appropriate liability cap for AI-generated content errors in Juno's clinical contracts? Are there market standards for patient engagement AI vendors? **Requires healthcare transactional attorney and insurance broker input.**

---

*Report prepared by research agent on June 21, 2026. Sources include ONC, FDA, FTC, HHS official guidance documents; HITRUST Alliance; AICPA SOC 2 guidance; state attorney general publications; leading healthcare law firm analysis (Arnold & Porter, Morgan Lewis, Covington & Burling, ArentFox Schiff); and healthcare technology industry resources. All research should be independently verified against current official sources before business decisions are made.*
