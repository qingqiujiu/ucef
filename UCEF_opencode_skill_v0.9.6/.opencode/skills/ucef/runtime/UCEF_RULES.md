# UCEF Minimal Rules

Complete one narrow Work Unit that closes named Coverage Gates. Treat chat history as disposable: after one semantic probe changes state, persist its new facts and one incremental Checkpoint before switching business questions. Several low-level reads of the same target are one probe; `NO_DELTA` does not create another Checkpoint. Return only bounded deltas matching the output contract when ready to promote.

1. Explain behavior for the active Scenario, not every statically possible path.
2. Separate reusable Fragment definitions from Scenario-specific route outcomes and stage context.
3. Every Scenario-facing discovery must be placed into a business `trace_stage` and a concrete execution node, or recorded as a placement Gap.
4. Every claim requires Evidence. Missing knowledge becomes a Gap, never an invented bridge.
5. Inventory fields before descent. Every method STEP declares field reads/writes, and every non-origin lineage step links its predecessors; no field may disappear silently.
6. External request parameters require origins. Consumed response parameters require targets and business uses.
7. Separate reusable MethodDefinition from Scenario METHOD_INVOCATION. A method invocation without meaningful internal STEP nodes is incomplete. A method is not automatically a Fragment; a Fragment needs a business purpose plus entry/exit/side-effect contracts.
8. Reuse only when identity, binding, applicability, and required coverage match.
9. Stop at the Work Unit objective, a complete reusable contract, a fully described external boundary, or an explicit Gap.
10. New facts default to `CANDIDATE`; do not claim runtime certainty from static reachability.
11. Never carry an uncheckpointed caller edge, route rule, field transformation, persistence mapping, external mapping, error behavior, configuration result, or explicit unknown into another probe.
12. After compaction or a new session, resume only from the durable latest Checkpoint and pending Observation ledger.
13. TraceStage is the business spine; ImplementationSlice explains cross-method implementation. Method trees and field graphs are evidence, not the default narrative.
14. Expand only behavior that changes a decision, P0/necessary P1 field, side effect, error/fallback, transaction/timing, or output. Otherwise record a TechnicalBridge and stop.
15. A Worker may suggest but not execute follow-up work. Only the scheduler may open another Work Unit, and automatic work must close an OPEN G0/G1/G2 gate.
