"""
Measure the rule extractor against a hand-labelled reference set (NFR-06).

Usage (from the project root, with spaCy and its English model installed):
    python scripts/evaluate_nlp_extraction.py data/reference/act_reference_dev.csv
    python scripts/evaluate_nlp_extraction.py data/reference/act_reference_heldout.csv

For every labelled provision it compares what the extractor decided with what a person decided,
for three questions: is it a duty, does it concern consent, does it concern retention. It also
scores the thing the system actually produces, the candidate rule (a duty that concerns consent or
retention), and prints every mistake so that they can be studied.

NFR-06 asks for a precision of at least 75% and a recall of at least 70% on candidate rules.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.nlp import act_reader, extractor  # noqa: E402

ACT_PDF = ROOT / "data" / "raw" / "legal" / "TheDataProtectionAct__No24of2019.pdf"


def prf(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def score(name, pairs):
    """pairs: list of (predicted: bool, expected: bool, label)."""
    tp = sum(1 for p, e, _ in pairs if p and e)
    fp = [l for p, e, l in pairs if p and not e]
    fn = [l for p, e, l in pairs if e and not p]
    precision, recall, f1 = prf(tp, len(fp), len(fn))
    print(f"{name:<34} TP={tp:<3} FP={len(fp):<3} FN={len(fn):<3} precision={precision:6.1%} recall={recall:6.1%} F1={f1:.2f}")
    return precision, recall, f1, fp, fn


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    reference = {}
    with open(sys.argv[1], newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            reference[row["reference"]] = row
    raw = act_reader.read_pdf_text(ACT_PDF)
    wanted = {int(r.split()[1].split("(")[0]) for r in reference}
    provisions = [p for p in act_reader.provisions(raw, only=wanted) if p.reference in reference]
    missing = set(reference) - {p.reference for p in provisions}
    if missing:
        print("Provisions in the reference that the reader did not find:", sorted(missing))
    candidates = extractor.extract(provisions)

    duty, consent, retention, candidate_pairs = [], [], [], []
    for c in candidates:
        ref = reference[c.reference]
        is_duty = ref["type"] == "OBLIGATION"
        has_consent, has_retention = ref["concerns_consent"] == "Y", ref["concerns_retention"] == "Y"
        duty.append((c.is_duty, is_duty, c.reference))
        consent.append((c.consent, has_consent, c.reference))
        retention.append((c.retention, has_retention, c.reference))
        candidate_pairs.append((c.is_candidate, is_duty and (has_consent or has_retention), c.reference))

    print(f"Reference file: {sys.argv[1]}  ({len(candidates)} provisions, "
          f"{sum(1 for d in duty if d[1])} duties, {sum(1 for d in candidate_pairs if d[1])} consent/retention duties)\n")
    score("Duty detection", duty)
    score("Topic: consent", consent)
    score("Topic: retention", retention)
    print()
    p, r, f1, fp, fn = score("CANDIDATE RULES (NFR-06)", candidate_pairs)
    print(f"\nNFR-06 target: precision >= 75% and recall >= 70%  ->  {'MET' if p >= 0.75 and r >= 0.70 else 'NOT MET'}")
    for name, pairs in (("Candidate rules", candidate_pairs), ("Duty detection", duty), ("Consent topic", consent), ("Retention topic", retention)):
        fps = [label for predicted, expected, label in pairs if predicted and not expected]
        fns = [label for predicted, expected, label in pairs if expected and not predicted]
        if fps or fns:
            print(f"\n{name}:\n  false positives (extractor said yes, reference says no): {fps}\n  false negatives (reference says yes, extractor said no): {fns}")


if __name__ == "__main__":
    main()
