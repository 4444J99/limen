# Limen — Evidence Appendix

## 1. Verifiable Execution
- **Exact-Head Constraints:** Every run receipt binds to an exact 40-character Git SHA (e.g. `9c8a87215962da131059ab63bd95a376f79891c2`), ensuring that success corresponds to a precise, verifiable tree state.
- **Durable Receipts:** `docs/receipts/positioning` records exact-head reproduction outputs with bounded timeout constraints and strict exit code validation.

## 2. Multi-Agent Capabilities
- Agents identify natively via `LIMEN_AGENT` and register capabilities dynamically using the conduct broker (`limen conduct capabilities`).
- Work routing enforces single-agent isolation.

## 3. Scope of Claims
- Proof artifacts demonstrate operation within controlled orchestration environments, focusing on deterministic validation of probabilistic tasks.
