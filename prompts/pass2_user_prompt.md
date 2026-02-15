---
name: pass2_user_prompt
---
PASS 2 SCREENING (Full Metadata with Abstract)

Paper Information:
{paper_metadata}

This paper was included in Pass 1 based on title and keywords alone. You now have the abstract — use it as your primary signal for decision-making.

DECISION RULES:
- Include: The paper describes, builds, or evaluates a custom embedded sensing/actuation system for health or ecological applications.
- Exclude: The abstract clearly matches one or more exclusion criteria.
- When in doubt, include — the human reviewer will make the final call.
- Do NOT use "uncertain" — make a binary include/exclude decision.

DOMAIN GUIDANCE:
- Health includes: medical, clinical, rehabilitation, fitness, wellness, assistive technology, physiological monitoring, mental health, sports performance, aging/accessibility
- Ecology includes: environmental monitoring, wildlife tracking, agriculture, water quality, soil sensing, conservation, pollution detection, habitat monitoring
- Adjacent applications (e.g., smart buildings for occupant health, agricultural IoT, food safety sensing) should be INCLUDED
- Reviews/surveys of embedded sensing systems in health or ecology ARE relevant — include them

CALIBRATION EXAMPLES FROM PRIOR SCREENING:

Example 1 — INCLUDE (health-adjacent, wearable platform):
  Title: "Training Smarter with OpenEarable: A Boxing Gesture Recognition Dashboard Integration"
  Why: Sports/fitness gesture recognition using wearable embedded sensing. Health-adjacent, custom artifact evaluation. Include.

Example 2 — INCLUDE (review paper, relevant domain):
  Title: "Body-Area Capacitive or Electric Field Sensing for Human Activity Recognition and Human-Computer Interaction: A Comprehensive Survey"
  Why: Survey of body-area sensing systems for health/HCI. Reviews are relevant if they cover embedded sensing in target domains.

Example 3 — EXCLUDE (high-power radar, not embedded low-power):
  Title: "mmDrive: Fine-grained Fatigue Driving Detection Using mmWave Radar"
  Why: mmWave radar for driving is high-power (EX.1) and vehicle-focused (EX.3). Not a low-power embedded sensing system.

Example 4 — EXCLUDE (no embedded artifact, just data analysis):
  Title: "LLM-Powered Data Annotation for Bridging the Semantic Gap in Air Quality Monitoring"
  Why: Software/ML pipeline for data annotation. No custom embedded hardware designed or evaluated (EX.6).

Respond ONLY with valid JSON in this exact format:
{
  "decision": "include|exclude",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation (1-2 sentences)",
  "exclusion_codes": ["EX.1"],
  "domain": "health|ecological|null"
}

The exclusion_codes array should only be populated if decision is "exclude".
