# Incremental HTML Explorer v0.8

## Three projections

1. **Chain View** — Scenario → System → Module → Node → Decision/Field/Interaction/Evidence.
2. **System View** — System → Module → participating Scenarios → Nodes → Data Entities.
3. **Data Model** — Table → Column/Index/Relation → related code/business facts.

The projections share the same Fact Store and metadata catalog; they are not separate copies of knowledge.

## Incremental build

```bash
ucef site build
ucef site update
ucef site stats
```

Entity chunks are content-hashed. Unchanged entities are not rewritten.

## Editable workbench

```bash
ucef site serve --open
```

Editable fields are restricted to presentation/knowledge organization:
- display name / business name
- description
- system assignment
- module assignment
- order
- hidden
- tags

They are saved in `.ucef/overrides.json` and never mutate Code/DB Facts.

A technical correction creates a `MANUAL_FACT_REVIEW` Work Unit under `.ucef/work_units/pending/`.

Opening `.ucef/site/index.html` directly remains read-only and works offline.
