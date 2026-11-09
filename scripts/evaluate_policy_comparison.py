"""
Measure the policy-comparison method (TF-IDF and cosine similarity) against labelled policy statements (FR-08).

Usage (from the project root):
    python scripts/evaluate_policy_comparison.py
    python scripts/evaluate_policy_comparison.py path/to/your_labelled_statements.csv

The CSV needs the columns  split,label,statement  where split is dev or test and label is
consent, retention or none (what obligation the statement addresses). The supplied file
data/reference/policy_statements.csv was written by the researcher; to test on independent material,
add statements from real policies, labelled by someone else, with split = test.

Two methods are compared:
  baseline   plain TF-IDF cosine similarity, one threshold, no word lists
  proposed   word stems + domain concept words + topic gate (see app/nlp/similarity.py)
The baseline threshold is chosen on the dev statements only; both are then scored on the test statements.
Two views are reported:
  statement level   does THIS statement address the obligation?
  policy level      given a policy of several statements, does it address the obligation? (balanced:
                    half of the policies contain a statement of the topic, half only near-miss statements)
"""
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.nlp import similarity as sim  # noqa: E402

KB = ROOT / "data" / "knowledge_base"
DEFAULT_CSV = ROOT / "data" / "reference" / "policy_statements.csv"
CATEGORIES = ("consent", "retention")
ACT_RULES = {"consent": ["ACT-S32-1"], "retention": ["ACT-S39-1", "ACT-S39-2"]}   # approved candidates used as rules


def rule_texts():
    texts = {c: [] for c in CATEGORIES}
    for rule in json.loads((KB / "dpa_rules.json").read_text(encoding="utf-8"))["rules"]:
        texts[rule["category"]].append(rule["obligation_text"])
    candidates = {c["candidate_code"]: c for c in json.loads((KB / "act_candidates.json").read_text(encoding="utf-8"))["candidates"]}
    for category, codes in ACT_RULES.items():
        for code in codes:
            if code in candidates:
                texts[category].append(candidates[code]["obligation_text"])
    return texts


def predict_baseline(category, rules, statements, theta):
    model = sim.TfidfModel(sum(rules.values(), []) + statements, use_concepts=False)
    rv = [model.vector(r) for r in rules[category]]
    return [max(model.cosine(model.vector(s), v) for v in rv) >= theta for s in statements]


def predict_proposed(category, rules, statements):
    allrules = sum(rules.values(), [])
    model = sim.TfidfModel(allrules + statements)
    rv = [model.vector(r) for r in rules[category]]
    return [sim.has_concept(s, category) and max(model.cosine(model.vector(s), v) for v in rv) >= sim.ADDRESSED_THRESHOLD for s in statements]


def counts(pred, truth):
    tp = sum(p and t for p, t in zip(pred, truth)); fp = sum(p and not t for p, t in zip(pred, truth))
    fn = sum(t and not p for p, t in zip(pred, truth)); tn = sum((not p) and (not t) for p, t in zip(pred, truth))
    return tp, fp, fn, tn


def metrics(tp, fp, fn, tn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (tp + tn) / max(tp + fp + fn + tn, 1)


def policies(rows, split, seed=3, n=300):
    sub = [r for r in rows if r["split"] == split]
    by = {l: [r["statement"] for r in sub if r["label"] == l] for l in ("consent", "retention", "none")}
    rnd = random.Random(seed)
    out = []
    for c in CATEGORIES:
        other = "retention" if c == "consent" else "consent"
        pool = by["none"] + by[other]
        for i in range(n):
            pick = rnd.sample(pool, min(6, len(pool)))
            if i % 2 == 0 and by[c]:
                pick += rnd.sample(by[c], min(rnd.choice([1, 2]), len(by[c])))
            rnd.shuffle(pick)
            out.append((c, i % 2 == 0 and bool(by[c]), pick))
    return out


def policy_level(rows, split, rules, method, theta=None):
    tally = {c: [0, 0, 0, 0] for c in CATEGORIES}
    for category, truth, statements in policies(rows, split):
        flags = predict_baseline(category, rules, statements, theta) if method == "baseline" else predict_proposed(category, rules, statements)
        pred = any(flags)
        i = 0 if pred and truth else 1 if pred else 2 if truth else 3
        tally[category][i] += 1
    return {c: metrics(*t) for c, t in tally.items()}


def statement_level(rows, split, rules, method, theta=None):
    sub = [r for r in rows if r["split"] == split]
    statements = [r["statement"] for r in sub]
    out = {}
    for c in CATEGORIES:
        flags = predict_baseline(c, rules, statements, theta) if method == "baseline" else predict_proposed(c, rules, statements)
        out[c] = metrics(*counts(flags, [r["label"] == c for r in sub]))
    return out


def show(title, result):
    cells = "   ".join(f"{c}: P={v[0]:.0%} R={v[1]:.0%} acc={v[2]:.0%}" for c, v in result.items())
    print(f"  {title:<10} {cells}")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    rules = rule_texts()
    print(f"{len(rows)} labelled statements ({sum(r['split'] == 'dev' for r in rows)} dev, {sum(r['split'] == 'test' for r in rows)} test)")
    print("Obligation texts used:", {c: len(t) for c, t in rules.items()})

    grid = [round(0.05 * i, 2) for i in range(1, 11)]
    best = max(grid, key=lambda th: sum(v[2] for v in policy_level(rows, "dev", rules, "baseline", th).values()))
    print(f"\nBaseline threshold chosen on dev statements: {best}")
    for split in ("dev", "test"):
        print(f"\n{split.upper()} statements")
        print(" statement level:")
        show("baseline", statement_level(rows, split, rules, "baseline", best))
        show("proposed", statement_level(rows, split, rules, "proposed"))
        print(" policy level (balanced):")
        show("baseline", policy_level(rows, split, rules, "baseline", best))
        show("proposed", policy_level(rows, split, rules, "proposed"))


if __name__ == "__main__":
    main()
