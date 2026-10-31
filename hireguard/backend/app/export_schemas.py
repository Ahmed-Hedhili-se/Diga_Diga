"""Export frozen contracts to JSON Schema: python -m app.export_schemas"""
import json

from . import contracts as c
from .config import ROOT

MODELS = {
    "cv_extraction": c.CVExtraction,
    "email_extraction": c.EmailExtraction,
    "sanitize_result": c.SanitizeResult,
    "validated_cv": c.ValidatedCV,
    "rubric": c.Rubric,
    "score_output": c.ScoreOutput,
    "approval_item": c.ApprovalItem,
    "audit_entry": c.AuditEntry,
}

if __name__ == "__main__":
    out = ROOT / "contracts" / "schemas"
    out.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        (out / f"{name}.json").write_text(json.dumps(model.model_json_schema(), indent=2), encoding="utf-8")
        print("wrote", name)
