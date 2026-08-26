# Business-First Layered Analysis Contract

## Layer 1 — Business spine

`TraceStage` is the primary reader navigation. It explains what happens, why this Scenario executes it, its input/output contract, business state change, next handoff, and terminal result. It is not a directory of methods.

## Layer 2 — Implementation slice

`ImplementationSlice` belongs to one TraceStage and may cross several small methods. It closes a coherent business question rather than stopping at a method boundary. It includes actual method path, meaningful internal steps, route/config facts, field effects, persistence/external boundaries, error/timing behavior, and transparent bridges.

A method may be collapsed only when it has no business condition, field value change, side effect, error/fallback, transaction/timing effect, or output change. Collapsing means recording a TechnicalBridge, not silently omitting the handoff.

## Layer 3 — Evidence

Evidence identifies the registered source, relative file/config/database object, symbol or key, and exact location needed to verify the claim. Large source/tool payloads are stored once outside the narrative and referenced by ID.

## Cross-cutting field graph

P0 fields require complete origin-to-required-sink lineage. P1 fields are expanded when they affect the selected route, result, persistence, external interaction, or requested error path. P2 fields are inventoried and normally excluded from deep lineage with a reason.

## Coverage gates

Priority is lexicographic, not a free-form weighted score:

- `G0`: missing entry/main spine/terminal or unresolved selected production route;
- `G1`: broken P0 lineage or incomplete required persistence/external boundary;
- `G2`: P1/error/timing information that can change the requested outcome;
- `G3`: useful optional detail;
- `G4`: framework or unrelated detail that must not auto-expand.

An automatic Work Unit must name the gate it closes. A discovered symbol without a gate impact is `DEFER` or `IGNORE`, not a new task.
