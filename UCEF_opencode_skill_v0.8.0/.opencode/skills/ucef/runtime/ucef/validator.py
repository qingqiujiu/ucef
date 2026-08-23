import json
import uuid
from pathlib import Path
from jsonschema import Draft202012Validator

COLLECTIONS = {
    "evidences": ("Evidence", "evidence_id", "EV"),
    "execution_nodes": ("ExecutionNode", "node_id", "NODE"),
    "execution_edges": ("ExecutionEdge", "edge_id", "EDGE"),
    "decisions": ("Decision", "decision_id", "DEC"),
    "data_mutations": ("DataMutation", "mutation_id", "DM"),
    "interactions": ("Interaction", "interaction_id", "INT"),
    "unknowns": ("Unknown", "unknown_id", "UNK"),
    "conflicts": ("Conflict", "conflict_id", "CONFLICT"),
}
FACTS = ["execution_nodes","execution_edges","decisions","data_mutations","interactions"]

def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"

class IngestionValidator:
    def __init__(self, framework_root, store):
        self.root=Path(framework_root); self.store=store
        defs=json.loads((self.root/"schema.json").read_text(encoding="utf-8"))["$defs"]
        self.validators={k:Draft202012Validator(defs[d]) for k,(d,_,_) in COLLECTIONS.items()}
    def _ensure_id(self, collection, record):
        _,field,prefix=COLLECTIONS[collection]
        if not record.get(field) or str(record.get(field)).upper()=="AUTO":
            record[field]=new_id(prefix)
    def validate_record(self, collection, record):
        self._ensure_id(collection, record)
        return [e.message for e in self.validators[collection].iter_errors(record)]
    def ingest(self, output, scenario_id, work_unit_id):
        report={"inserted":{},"errors":[],"next_work_units":output.get("next_work_units") or []}
        for r in output.get("evidences") or []:
            errors=self.validate_record("evidences",r)
            if errors: report["errors"].append({"collection":"evidences","record":r,"errors":errors}); continue
            self.store.upsert_evidence(r,scenario_id,work_unit_id); report["inserted"]["evidences"]=report["inserted"].get("evidences",0)+1
        self.store.commit()
        batch_nodes={r.get("node_id") for r in (output.get("execution_nodes") or []) if r.get("node_id")}
        for c in FACTS:
            for r in output.get(c) or []:
                errors=self.validate_record(c,r)
                missing=[e for e in r.get("evidence_ids") or [] if not self.store.has_evidence(e)]
                if missing: errors.append(f"Missing evidence references: {missing}")
                refs=[]
                if c=="execution_edges": refs=[r.get("from"),r.get("to")]
                elif c in ("decisions","data_mutations","interactions"): refs=[r.get("owner_node_id")]
                bad=[x for x in refs if x and x not in batch_nodes and not self.store.has_fact_id(x)]
                if bad: errors.append(f"Missing execution node references: {bad}")
                if errors: report["errors"].append({"collection":c,"record":r,"errors":errors}); continue
                self.store.upsert_fact(c,r,scenario_id,work_unit_id); report["inserted"][c]=report["inserted"].get(c,0)+1
        for c,method in [("unknowns",self.store.upsert_unknown),("conflicts",self.store.upsert_conflict)]:
            for r in output.get(c) or []:
                errors=self.validate_record(c,r)
                if errors: report["errors"].append({"collection":c,"record":r,"errors":errors}); continue
                method(r,scenario_id,work_unit_id); report["inserted"][c]=report["inserted"].get(c,0)+1
        self.store.commit(); return report
