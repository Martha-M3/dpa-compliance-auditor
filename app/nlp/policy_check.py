"""
Compare an organisation's policy text with the obligations in the rules (FR-08).

This sits between the database and the similarity maths in similarity.py. It needs no spaCy, so it runs
inside the website.
"""
from app.nlp import similarity

CATEGORY_ORDER = ("consent", "retention")


def assess_policy(policy_text, rules):
    """
    policy_text: the extracted text of a policy document.
    rules: ComplianceRule rows (enabled ones).
    Returns one dictionary per topic that has at least one rule:
        category, rule (the rule whose obligation matched best), verdict, similarity, best_statement
    """
    statements = similarity.split_statements(policy_text)
    findings = []
    for category in CATEGORY_ORDER:
        group = [r for r in rules if r.category == category]
        if not group:
            continue
        verdict, score, statement = similarity.assess(category, [r.obligation_text for r in group], statements)
        best_rule = group[0]
        if statement:
            model = similarity.TfidfModel([r.obligation_text for r in group] + statements)
            sv = model.vector(statement)
            best_rule = max(group, key=lambda r: model.cosine(model.vector(r.obligation_text), sv))
        findings.append({"category": category, "rule": best_rule, "verdict": verdict,
                         "similarity": score, "best_statement": statement})
    return findings
