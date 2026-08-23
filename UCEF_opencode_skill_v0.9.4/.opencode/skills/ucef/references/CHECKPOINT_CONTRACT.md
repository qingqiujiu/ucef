# Anti-loss Checkpoint Contract

The conversation is a disposable working buffer. SQLite-backed Observations and Checkpoints are the durable memory of an unfinished Work Unit.

## Mandatory cadence

One probe is one bounded retrieval target: one symbol with its directly relevant callers/callees, one route definition, one mapper, one persistence statement, one external client operation, or one small set of configuration keys answering the same question.

After every probe that returns a chain-changing fact, run `checkpoint` before opening another symbol, branch, mapper, client, SQL statement, or configuration query. Also checkpoint before switching projects, before producing a long explanation, and before any likely context compaction. `max_uncheckpointed_probes` is one.

Do not wait for a complete Fragment or TraceStage. Partial but evidenced discoveries belong in the Observation ledger.

## Observation content

Capture every fact that would change the reconstructed business path:

- caller/callee handoff;
- route input, condition, candidate, or selected result;
- field origin, copy, rename, default, override, conversion, split/merge, sink, or drop;
- persistence condition, key, column mapping, or transaction behavior;
- external request origin, response consumer, timeout/retry/fallback, or exception mapping;
- effective configuration value or binding;
- terminal behavior, contradiction, or explicit unknown.

An Observation is a concise claim plus an evidence pointer. Do not store large source excerpts. Multiple contradictory claims remain separate Observations until resolved.

## Checkpoint content

Each Checkpoint records the current focus, visited references, current chain spine, unresolved questions, one next probe, a concise resume summary, and the Observations produced by the just-finished probe. It also retains an `execution_frontier` of unexpanded invocation/step nodes and a `field_frontier` showing where each tracked field currently ends or breaks. The runtime assigns sequence numbers, deduplicates identical Observations, and unions visited references across Checkpoints.

An `ACTIVE` Checkpoint has exactly one `next_probe`. Use `READY_TO_PROMOTE` when the pending Observations are sufficient to build canonical Evidence/Fragment/Trace records. Use `COMPLETE` only after canonical ingestion and audit; use `BLOCKED` only with an explicit unresolved dependency.

## Resume and overflow

Run `resume` after a new session or context compaction. Read `DURABLE RESUME STATE` before retrieving code. Continue only from `latest_checkpoint.next_probe`; do not reconstruct progress from chat history.

The resume pack loads a bounded frontier of pending Observations plus an index and omitted count. If observations were omitted, query them by subject, kind, or source with `memory-query`. Omission from a context pack never deletes the ledger record.

Do not load all overflow facts at once. Process one semantic group at a time—for example one route, one canonical field, one external operation, or one persistence effect—and promote that group before loading the next. This keeps synthesis bounded without reducing coverage.

## Promotion

Canonical ingestion records may carry `observation_ids`. Successful ingestion records an immutable promotion link from each Observation to its Evidence, Fragment, MethodDefinition, ExecutionNode, FieldInventoryItem, TraceStage, route decision, field lineage, persistence effect, external interaction, or Gap. Evidence-only promotion does not remove an Observation from the pending-assembly frontier; it remains visible until assembled into a reusable or Scenario-facing entity. Assembled Observations remain queryable with their promotion targets.
