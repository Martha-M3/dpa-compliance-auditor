"""
Run the rule extractor over the whole Data Protection Act and save the candidate rules.

Usage (from the project root, with spaCy and its English model installed):
    python scripts/extract_rules_from_act.py

The result, data/knowledge_base/act_candidates.json, is a list of PROPOSED rules: each is a duty in the
Act that concerns consent or retention. An administrator reviews them on the Compliance Rules page
and approves or rejects each one. Nothing here changes the audit by itself.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.nlp import act_reader, extractor  # noqa: E402

ACT_PDF = ROOT / "data" / "raw" / "legal" / "TheDataProtectionAct__No24of2019.pdf"
OUT = ROOT / "data" / "knowledge_base" / "act_candidates.json"


def short_text(text, limit=600):
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."


def main():
    raw = act_reader.read_pdf_text(ACT_PDF)
    provisions = act_reader.provisions(raw)
    analysed = extractor.extract(provisions)
    candidates = []
    for c in analysed:
        if not c.is_candidate:
            continue
        number = c.reference.replace("Section ", "").replace("(", "-").replace(")", "")
        candidates.append({
            "candidate_code": f"ACT-S{number}",
            "reference": c.reference,
            "source_section": f"{c.reference}, Data Protection Act 2019 ({c.title})",
            "category": c.category,
            "modality": c.modality,
            "actor": c.actor,
            "action": c.action,
            "object": c.object,
            "condition": c.condition,
            "confidence": c.confidence,
            "obligation_text": short_text(c.text),
        })
    candidates.sort(key=lambda d: -d["confidence"])
    OUT.write_text(json.dumps({"source": "Kenya Data Protection Act, 2019", "candidates": candidates}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Read {len(provisions)} provisions; {sum(1 for c in analysed if c.is_duty)} are duties; "
          f"{len(candidates)} concern consent or retention.")
    print(f"Saved {OUT}")
    for c in candidates:
        print(f"  {c['confidence']:.1f}  {c['candidate_code']:<12} {c['category']:<10} {c['modality']:<11} {c['actor'][:40]!r} -> {c['action']}")


if __name__ == "__main__":
    main()
