Provide a concise summary of this paper in 3-4 paragraphs. Cover:

1. **Problem & Motivation** — What problem does this work address, and why does it matter?
2. **Approach & System** — What did the authors build or propose? Describe the sensing system, its key components, and how it works.
3. **Evaluation & Results** — How was it tested, and what were the key findings?
4. **Limitations & Future Work** — What limitations do the authors acknowledge? What is left for future work?

Use direct quotes with page references where possible.

---

I need to extract specific technical details from this paper for my synthesis matrix. For each item below, provide the answer with a direct quote or page reference. If the information is not present, say "Not specified."

**Application Type:** Is this a Health, Ecological, or Other application?

**Application Target:** What specific group, environment, or condition is targeted? Be brief (e.g., "cardiac arrhythmia detection", "vineyard microclimate monitoring").

**Sensors:** List all sensors used in the system (e.g., IMU, PPG, temperature, camera, custom).

**Actuators:** List any actuators (e.g., LED, motor, haptics, speaker). If none, say "None."

**Microcontroller:** What microcontroller or processor is used? (e.g., ESP32, STM32, Nordic nRF, ATmega). If not specified, say so.

**Embedded Platform:** What embedded platform or OS is used? (e.g., Arduino, ZephyrRTOS, Bare Metal, Nordic SDK, Contiki OS). If not specified, say so.

**Data Collection Technology:** What wireless communication technology is used? (e.g., BLE, WiFi, LoRa, Wired, None). List all that apply.

**Data Processing Methods:** How is data processed? (e.g., onboard, cloud, Machine Learning, Deep Learning, one-off scripting/exploratory). List all that apply.

**Interface Type:** What user-facing interfaces exist? (e.g., Mobile App, Web Portal, Desktop Application, Scripting/Serial, Onboard Hardware). List all that apply. If not specified, say so.

**Interface Platform:** How was the interface built? (e.g., iOS, Android, Python, Web, Mobile Cross Platform). If not specified, say so.

**Functional Artifact:** What is the primary outcome of this work? (e.g., Usable System, Proof of Concept, Toolkit, System Design/Architecture, Dataset, Development Methodology, Usable System Component). Can be multiple.

**Artifact Tags:** Does the paper mention ACM artifact badges (Artifacts Evaluated - Functional, Artifacts Available, Artifacts Evaluated - Reusable)? These are official ACM badges, not self-claims.

**External Source Link:** Is there a link to source code, hardware designs, or datasets? Provide the URL(s) if so.

**Evaluation Duration:** How long did the evaluation last? (e.g., "4 hours", "12 days"). If time is not meaningful to the evaluation or is not specified, say "N/A."

**Evaluation Units:** How many units or participants were involved? (e.g., "8 participants", "20 sensor nodes", "3 deployment sites").

---

Now I need your help gathering evidence for columns that require more interpretation. For each item below, do NOT pick a value — instead, provide the relevant quotes and page references so I can make the judgment call.

**Application Framing — How do the authors motivate and frame the application of their work?**
Surface evidence for how the authors justify the need for this system. Specifically look for:
- Do they cite literature identifying the problem/need?
- Do they describe their own observations or prior work that motivates this?
- Did they consult stakeholders, domain experts, or target users?
- Is there any co-design or participatory process?
- Is the application framing hypothetical or speculative?
- If the application we care about (health or ecology) is secondary to the paper's primary focus, note that.
Quote the key framing passages.

**Evaluation Type — What is the context and rigor of the evaluation?**
Surface evidence for how the system was evaluated. Look for:
- Was it benchtop/simulation only?
- Was it in a controlled lab or with proxy participants?
- Was it deployed in the target context but with limited scope (short time, few units, heavy researcher involvement)?
- Was it a longitudinal deployment in the real target environment?
- Was it a demonstration or a feasibility showcase?
- Was there a participatory workshop or user study component?
Quote the passages describing the evaluation setup, environment, duration, and participants.

**Reusability — Hardware/Platform:**
What does the paper reveal about whether someone could reuse or reproduce the hardware? Look for:
- Is the hardware described in detail (components, connections, schematics)?
- Are schematics, PCB layouts, or CAD files mentioned or available?
- Is it based on a previous work or a commercial off-the-shelf platform?
- Are bill-of-materials or sourcing details provided?
Quote relevant passages about hardware description, availability, and documentation.

**Reusability — Firmware:**
What does the paper reveal about the firmware (the logic running on the device)? Look for:
- Is the firmware described in detail (what it does, how it works)?
- Is source code mentioned or available?
- What language/framework is used?
- Are there enough details to reimplement it?
Quote relevant passages.

**Reusability — Analysis/Processing:**
What does the paper reveal about post-processing, algorithms, or data analysis methods critical to results? Look for:
- Are novel algorithms or processing pipelines described in detail?
- Is the analysis code available?
- Are methods standard/well-known or custom?
- Could someone reproduce the analysis from what's written?
Quote relevant passages.

**Reusability — Software:**
What does the paper reveal about upstream software (mobile apps, web portals, desktop applications)? Look for:
- Is the software described in detail?
- Is the source code available?
- What platform/framework is used?
- Is it based on a previous work or an off-the-shelf solution?
If there is no upstream software component, say so.
Quote relevant passages.

---

Finally, I need evidence related to challenges, limitations, and development methodologies described in this paper. For each section, provide a brief summary followed by supporting quotes with page references.

**Challenges — What challenges did the authors encounter or identify?**
Look for challenges at any stage: design, development, deployment, data collection, or analysis. These could be technical (power, connectivity, form factor), methodological (recruitment, data quality), or contextual (environmental conditions, user compliance). Summarize each distinct challenge with supporting quotes.

**Limitations — What limitations do the authors acknowledge?**
Look for explicitly stated limitations of the system, evaluation, or approach. Also note any significant limitations that are implied but not explicitly acknowledged (e.g., very small sample size, lab-only testing presented as generalizable). Summarize with quotes.

**Development Methodology — How was the system developed?**
Look for evidence of the development process, specifically:
- What tools, environments, or workflows were used for development? (e.g., IDEs, simulation tools, power profilers, oscilloscopes, 3D printers, PCB design tools)
- Was there a described development pipeline or process? (e.g., iterative prototyping, agile, hardware-software co-design)
- Were any custom tools or methods created for development?
- How were hardware and software integrated and tested during development?
- What manufacturing or fabrication methods were used?
- How were components sourced?
Summarize the development approach with supporting quotes. If the paper says little about development methodology, note that explicitly.



---

Based on your review and understanding of my codebook and criteria. Do you feel this paper should be included in my literature review? 