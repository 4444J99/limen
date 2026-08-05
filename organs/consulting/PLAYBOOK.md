# Sovereign Systems — PLAYBOOK (Intake to Delivery)

> This is the first vertical slice of the consulting organ: the **repeatable playbook** for taking a client from initial contact to final delivery, turning manual, high-touch processes into an autonomic engine driven by the 5-primitive kernel.

## 1. Intake: Establishing the Member and Mandate

The goal of intake is not just to talk to the client, but to structure their needs into an executable format.

*   **Trigger:** New client inquiry or kickoff meeting.
*   **System Action (Solutions Architect role):**
    *   Ingest meeting notes, emails, and context docs.
    *   Map the **Member** (client identity, risk tolerance, core constraints).
    *   Draft the **Mandate** (the proposed Scope of Work, specific deliverables, success metrics).
*   **Human Check (Principal):** Review, adjust pricing/timeline, and present to the client. *The system never sends the proposal.*
*   **Output:** `engagements/<client_name>/mandate.yaml`

## 2. Planning: Breaking down the Execution

Once the Mandate is agreed upon, it must be decomposed into actionable work units for the fleet (or the human).

*   **Trigger:** Mandate approved by client.
*   **System Action (Delivery Lead role):**
    *   Decompose the SOW into specific tasks.
    *   Assign tasks to the appropriate lane (AI agent for research/drafting, human for strategic decisions/review).
    *   Initialize the **Standing** (project dashboard, timeline).
*   **Human Check (Principal):** Verify the task breakdown and lane assignments.
*   **Output:** Tasks added to `tasks.yaml` (if applicable to Limen), and `engagements/<client_name>/standing.md` initialized.

## 3. Execution & Tracking: Managing the Standing

The system runs continuously to keep the project moving and the principal informed.

*   **Trigger:** Continuous heartbeat/conductor cycle.
*   **System Action (Engagement Manager role):**
    *   Monitor task completion across lanes.
    *   Update the **Standing** document with progress, blockers, and burndown.
    *   Draft weekly status updates for the client.
*   **Human Check (Principal):** Review status updates, resolve flagged blockers, and send updates to the client.
*   **Output:** Living `engagements/<client_name>/standing.md` and draft correspondence.

## 4. Quality Assurance: Enforcing the Standard

Before any work reaches the principal for final review, it must meet the baseline quality bar.

*   **Trigger:** Draft deliverable completed by a lane.
*   **System Action (QA / Standard Enforcer role):**
    *   Evaluate the draft against the **Standard** (client-specific style guides, technical requirements, accuracy checks).
    *   Flag deviations or missing elements.
    *   *Self-correction:* If the lane is an AI, route it back for revision before human review.
*   **Human Check (Principal):** Final review of the QA-cleared draft. The principal owns the final polish.
*   **Output:** QA report and polished draft deliverable.

## 5. Delivery & Handoff: The Governance Process

Closing the loop securely and professionally.

*   **Trigger:** Principal approves final deliverable.
*   **System Action (Operations role):**
    *   Package the deliverable according to the **Governance** rules (correct formats, secure channels).
    *   Draft the handoff communication.
    *   Trigger internal billing milestone notifications.
*   **Human Check (Principal):** Send the final package and invoice to the client.
*   **Output:** Delivery package ready for transmission.

---

## The Micro Instance: Real-World Prototyping

This playbook is currently being manually executed and validated against Anthony's active engagements:

*   **The Maddie Deployment:** Testing the Intake and Mandate formation. Turning raw requirements into a structured, trackable SOW.
*   **The Rob Deployment:** Testing Execution & Tracking. Maintaining the Standing dashboard and coordinating complex multi-step delivery.
*   **The Derek Deployment:** Testing the Standard and QA. Ensuring narrative and technical deliverables meet a high, consistent bar before human review.

*These are manual prototypes. The next stage (maturing) involves automating these steps via the conductor, scaling the capacity of Sovereign Systems.*
