# Context Budget Contract

UCEF separates durable knowledge from the model's temporary working set. SQLite keeps the complete Observation ledger and assembled Scenario dossier. A resume/context pack is only a routed view for the current Work Unit; omission from that pack never means deletion.

## Work Unit phase

Set `phase` explicitly:

- `EXCAVATE`: retrieve and checkpoint one bounded fact. Load checkpoint rules, the local execution neighborhood, active fields, and only the output slice relevant to persistence or external interaction.
- `PROMOTE`: turn verified Observations into canonical records. Load the full output contract.
- `ASSEMBLE`: connect reusable facts to the Scenario tree and field graph. Load the full output and reader contracts.
- `PUBLISH`: audit the reader-facing dossier and HTML. Load the full output and reader contracts.

Do not keep a Work Unit in `PROMOTE`, `ASSEMBLE`, or `PUBLISH` while continuing broad excavation.

## Required focus hints

Keep these fields current before every `resume`:

- `context_scope.anchor_execution_node_id`: the method invocation or step currently being expanded;
- `context_scope.anchor_stage_id`: the enclosing business stage;
- `context_scope.active_fields`: the small field group currently being traced;
- `target_fields`: the Work Unit's acceptance-critical fields.

The builder loads the anchor's ancestors and nearby descendants, method definitions referenced by those nodes, active-field inventory records and lineage, and gaps matching the current focus. It does not load the first arbitrary slice of the whole Scenario.

## Default 120K policy

The default UCEF context budget is 32K tokens, with 8K reserved inside that amount for reasoning and output; the compiled input target is about 24K. Pending Observations are selected from a larger candidate pool and ranked by active fields, current focus, next probe, stage, execution node, and named Coverage Gate. Skeleton and Integration roles omit the local method tree; Slice and Repair roles load only the active neighborhood. Method reuse returns a compact contract by default.

Use the remaining model window for the current code/config/database probe and synthesis. Lower `max_total_tokens` when tools return large payloads; increase it only after measuring an actual omission that cannot be handled by a narrower query.

## On-demand recovery

Every bounded section carries totals, omitted counts, or a recovery hint. Recover facts narrowly:

- `memory-query --subject <symbol-or-field>` for omitted Observations;
- `query --collection execution_nodes --scenario <id>` for another tree region, then move the anchor;
- `query --collection field_inventory` or `field_lineage_steps` for another active field group;
- `method-reuse --full` only when the complete stored method record is necessary;
- `query --collection gaps --scenario <id>` for the full gap ledger.

Never solve an omission by copying the entire database, all method bodies, or the complete Scenario dossier into the conversation.
