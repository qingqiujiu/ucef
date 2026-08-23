# UCEF Minimal Rules

Complete one narrow Work Unit. Return one JSON object matching the provided output contract.

1. Explain behavior for the active Scenario, not every statically possible path.
2. Separate reusable Fragment definitions from Scenario-specific route outcomes and stage context.
3. Every Scenario-facing discovery must be placed into a `trace_stage` or recorded as a placement Gap.
4. Every claim requires Evidence. Missing knowledge becomes a Gap, never an invented bridge.
5. Preserve field evolution step by step, including defaults, overwrites, conversions, loss, persistence, and external mapping.
6. External request parameters require origins. Consumed response parameters require targets and business uses.
7. A method is not automatically a Fragment. A Fragment needs a business purpose plus entry/exit/side-effect contracts.
8. Reuse only when identity, binding, applicability, and required coverage match.
9. Stop at the Work Unit objective, a complete reusable contract, a fully described external boundary, or an explicit Gap.
10. New facts default to `CANDIDATE`; do not claim runtime certainty from static reachability.

