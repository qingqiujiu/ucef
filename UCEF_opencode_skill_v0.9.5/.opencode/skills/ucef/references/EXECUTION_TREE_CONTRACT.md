# Method Execution Tree and Field Contract

Use this contract when decomposing Java code or publishing a Scenario. A linear business Stage is only a summary; it is not sufficient execution evidence.

## Three identities

- `MethodDefinition` is reusable code knowledge identified by `source_id + symbol + code_hash`. It records module, class, signature, source range, input/output contracts, and declared/observed errors.
- `METHOD_INVOCATION` is one call instance in the current Scenario. The same definition may appear multiple times with different callers, inputs, configuration, branches, or outcomes.
- `STEP` is one meaningful region inside an invocation: validation, read, default, assignment, transform, compute, route, call, persistence, external call, return, or error handling.

The primary hierarchy is:

```text
MODULE
└── METHOD_INVOCATION
    ├── STEP
    ├── BRANCH / LOOP
    ├── STEP (CALL)
    │   └── METHOD_INVOCATION
    └── STEP (RETURN)
```

Do not create a real parent cycle. Use `REFERENCE` for previously assembled behavior and `RECURSION` for a recursive back edge. Use `ASYNC_HANDOFF` for events, queues, schedulers, or callbacks whose consumer continues in another execution lane.

## Method step boundary

Split a method when one of these changes: control condition, field state, called boundary, side effect, error behavior, or returned value. Several adjacent statements may be one step when they perform one indivisible transformation. A method with only “calls X” and no internal steps is `METHOD_OPAQUE` and is not complete.

Every STEP explicitly contains `field_reads` and `field_writes`, including empty arrays. Object-level wording such as “convert request to command” is incomplete when any contained field affects routing, business state, persistence, external parameters, or output.

## Field inventory before descent

Inventory fields at the Scenario entry and at newly discovered boundaries before following more calls:

- `P0`: route inputs, identifiers, money, status, tenant/channel selectors, persistence keys;
- `P1`: persisted columns, external request/consumed response values, returned business values;
- `P2`: ordinary payload or passthrough fields.

Each field is `TRACKED`, `EXCLUDED`, or `GAP`. Exclusion requires a concrete reason. A field read or written by a STEP but absent from the inventory is a completeness failure; fields may not disappear silently.

## Field lineage graph

A field path is a graph, not an ordered prose list. Every non-origin `FieldLineageStep` names `previous_step_ids`; merge and split operations may have multiple predecessors or successors. Each step also points to its `execution_node_id`.

Capture when relevant:

- source and target value locations;
- expression or conversion rule;
- before/after type, format, unit, or value semantics;
- null/default/override behavior and precedence;
- branch condition;
- business use;
- final persistence, external request, decision, return, drop, or other sink.

Having both an origin and a sink is not sufficient when the predecessor graph cannot connect them. Audit this as a discontinuous field.

## Presentation

The Scenario page uses three synchronized views:

1. execution tree for navigation;
2. selected invocation/step details, including evidence and boundaries;
3. field inventory and data-flow path, with reverse highlighting of tree nodes.

Business Stages remain a concise orientation layer. They do not replace the method tree or field graph.

