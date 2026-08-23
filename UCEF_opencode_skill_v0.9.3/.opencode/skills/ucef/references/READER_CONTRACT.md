# Reader Contract

The published Scenario is for a Java developer who has no prior knowledge of the system. The dossier must be understandable before the reader opens source code.

## Required reader answers

1. What business operation is performed?
2. What triggers it and what is the input contract?
3. Which registered Java sources, revisions, environment, and production configuration apply?
4. Why does this Scenario select its current route?
5. What are the ordered business stages and handoffs?
6. What does each stage receive, do, produce, mutate, and call next?
7. Where do routing inputs, identifiers, money, status, tenant/channel, external parameters, and persisted values originate?
8. Where are those values copied, defaulted, converted, computed, overwritten, dropped, returned, or stored?
9. Which stores/tables/columns change and under what transaction/condition?
10. Which external systems are called, with which request values and why?
11. How are external responses consumed, persisted, returned, or used in decisions?
12. What happens on errors, timeouts, retries, fallbacks, and alternate routes?
13. What differs from comparison variants?
14. What remains unknown or only statically inferred?

## Completeness dimensions

Audit separately:

- `TOPOLOGY`
- `ROUTING`
- `FIELD_LINEAGE`
- `PERSISTENCE`
- `EXTERNAL_INTERACTIONS`
- `ERROR_HANDLING`
- `EVIDENCE`
- `MEMORY_ASSEMBLY` — no durable Observation affecting this Scenario remains outside the reusable or Scenario-facing knowledge layers.

A Scenario is `READABLE_COMPLETE` only when mandatory dimensions are complete or explicitly not applicable. Partial and unknown regions remain visible in the dossier.

## Presentation

The default page begins with business goal, trigger, applicable environment/config, terminal outcome, stores changed, and external systems called. Then show the numbered execution story. Reused Fragments are expanded inline with a reuse badge. Source links and raw facts are progressive detail.
