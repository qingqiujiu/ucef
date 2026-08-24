# Layered Agent Protocol

All Workers are read-only analysts. They return new Observations and bounded canonical proposals; the UCEF runtime is the single writer. A Worker may suggest candidates but may not create or continue another Work Unit. Checkpoint once after a semantic probe changes state, not after every low-level tool call.

Common invariants:

- one Work Unit closes named Coverage Gates;
- no direct editing of complete JSON, SQLite, HTML, or source projects;
- no claim without Evidence and no unknown bridge without a Gap;
- output only deltas, never repeat the input dossier;
- framework internals are transparent bridges only when they change no decision, field value, side effect, error, transaction, timing, or output;
- stop on acceptance, budget exhaustion, no state delta, repeated probe fingerprint, or explicit Gap.

## SKELETON

Build the Scenario business spine: entry, business decisions, selected route candidates, persistence/external boundaries, terminal outcomes, and the Coverage Gates that must be closed. Do not decompose every method or trace all fields. Classify discovered references as `FOLLOW`, `REFERENCE`, `DEFER`, `IGNORE`, or `GAP`. Only propose `FOLLOW`; the scheduler decides whether it becomes work.

Required output: candidate TraceStages, CoverageGates, concise Evidence/Observations, and bounded candidate references. Do not output ImplementationSlices or final narrative.

Allowed operations: `add_observation`, `propose_trace_stage`, `propose_coverage_gate`, `propose_candidate_reference`, `open_gap`.

## SLICE

Close the named gate for exactly one business step or cohesive semantic slice. Follow application code across method boundaries until input, decisions/config, P0 and necessary P1 fields, side effects/boundaries, output, error/timing, and unknowns are semantically closed. Record transparent framework plumbing without entering its internals.

Required output: one bounded ImplementationSlice plus only the MethodDefinitions, Scenario execution nodes, field edges, boundary facts, Evidence, and Gaps newly required by that slice. `closure_status=COMPLETE` is valid only when every semantic closure flag is true.

Allowed operations: `add_observation`, `propose_implementation_slice`, `propose_method_definition`, `propose_execution_node`, `propose_field_inventory`, `propose_field_lineage`, `propose_route_decision`, `propose_persistence_effect`, `propose_external_interaction`, `propose_gate_status`, `open_gap`.

## INTEGRATION

Do not query source code, production configuration, or raw Observation payloads. Read the business spine, compact ImplementationSlices, P0 field view, route outcomes, persistence/external contracts, Coverage Gates, and Gaps. Produce or revise the business narrative, detect cross-step contradictions and broken handoffs, and propose focused follow-up gates. Do not repair implementation facts or broaden excavation.

Required output: business-ordered narrative deltas, contradiction Gaps, and gate status proposals. The runtime assembles HTML.

Allowed operations: `propose_narrative_delta`, `propose_gate_status`, `open_contradiction_gap`.

## REPAIR

Read only the rejected Patch records, machine error codes, and one-hop dependencies. Correct only allowed record IDs and operation types. One repair attempt is the default. If the same error fingerprint remains, return a Gap and stop; do not reread the Scenario or source repository broadly.

Allowed operations: `propose_patch`, `open_gap`.
