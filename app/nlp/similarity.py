"""
Comparing an organisation's policy with the obligations of the Act (FR-08).

Method: TF-IDF and cosine similarity, written here in plain Python so that the website needs no
compiled libraries (tests check that the numbers equal scikit-learn's).

  1. Text is cut into words, lower-cased, stripped of very common words, and reduced to word stems,
     so that "retained", "retaining" and "retention" are compared as the same word.
  2. Optionally, words that mean the same thing in this domain are replaced by one concept word
     ("permission", "agreement", "opt in" -> "consent"; "delete", "erase", "destroy" -> "retain").
  3. Each text becomes a vector of TF-IDF weights: a word counts more when it is frequent in the
     text and rare in the whole collection of texts.
  4. The similarity of two texts is the cosine of the angle between their vectors, from 0 (nothing in
     common) to 1 (the same words in the same proportions).

For each obligation the best-matching policy statement is found. A similarity at or above
`ADDRESSED_THRESHOLD` means the policy addresses the obligation, one at or above `PARTIAL_THRESHOLD`
means it partly does, and anything below means no statement was found.
"""
import math
import re
from collections import Counter

STOP_WORDS = set("""
a an the and or of to in on at by for with from as is are was were be been being it its this that these those
which who whom whose any all each every no not nor than then there their they them we our us you your he she his
her shall must may can will would should could do does did done has have had having under over into out up down
further such other another also only so if when where while whether unless except such per via upon
""".split())

# Words that mean the same in this domain. Applied after stemming, to both sides of every comparison.
CONCEPTS = {
    "consent": {"consent", "agree", "agreement", "permission", "approval", "approve", "authorise", "authorize",
                "opt", "optin", "optedin", "withdraw", "withdrawal", "assent"},
    "retain": {"retain", "retention", "keep", "kept", "store", "storage", "hold", "held", "delete", "deletion",
               "erase", "erasure", "destroy", "destruction", "remove", "removal", "shred", "purge", "anonymise",
               "anonymize", "pseudonymise", "pseudonymize", "expire", "expiry", "overwrite", "indefinitely"},
}
_CONCEPT_OF = {}
for _concept, _words in CONCEPTS.items():
    for _w in _words:
        _CONCEPT_OF[_w] = _concept


# --- Concept gates -----------------------------------------------------------------------------
# Plain TF-IDF is fooled by the generic words that every rule and every policy share ("personal data",
# "processing", "controller"). So a statement can only address an obligation of a known topic if it
# also contains words of that topic. A "strong" word is enough on its own. A "weak" word (keep, store,
# remove, hold) appears in many unrelated sentences, so it counts only together with a time cue
# ("five years", "no longer needed", "until", "period").
STRONG = {
    "consent": {"consent", "agree", "agreement", "permission", "approval", "approve", "authorise", "authorize",
                "opt", "optin", "optedin", "withdraw", "withdrawal", "assent"},
    "retention": {"retain", "retention", "delete", "deletion", "erase", "erasure", "destroy", "destruction",
                  "shred", "purge", "anonymise", "anonymize", "pseudonymise", "pseudonymize", "expire", "expiry",
                  "overwrite", "indefinitely"},
}
WEAK = {"retention": {"keep", "kept", "store", "storage", "hold", "held", "remove", "removal"}}
TIME_CUE = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|thirty|sixty|ninety)\b[^.]*?\b(day|week|month|year)s?\b"
    r"|\bno longer\b|\blonger than\b|\buntil\b|\bperiod\b|\bas long as\b|\bwhile it is needed\b|\bonly while\b|\bthereafter\b",
    re.I)

ADDRESSED_THRESHOLD = 0.03   # chosen on the dev statements (see scripts/evaluate_policy_comparison.py)
PARTIAL_THRESHOLD = 0.01


def stem(word):
    """A small suffix stripper (enough to unify plurals and verb endings)."""
    w = word
    if len(w) <= 3:
        return w
    for suffix, replacement in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("edly", ""), ("ed", ""), ("es", ""), ("s", "")):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            w = w[: len(w) - len(suffix)] + replacement
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


for _concept, _words in CONCEPTS.items():
    for _w in _words:
        _CONCEPT_OF.setdefault(stem(_w), _concept)    # so "deleted" (stem "delet") also maps to the concept


def _stems(words):
    return {stem(w) for w in words}


def tokens(text, use_concepts=True):
    out = []
    for raw in re.findall(r"[a-zA-Z]+", text.lower()):
        if raw in STOP_WORDS or len(raw) < 2:
            continue
        # concept words are looked up before stemming (the lists hold whole words) and after it
        concept = _CONCEPT_OF.get(raw) or _CONCEPT_OF.get(stem(raw))
        out.append(concept if (use_concepts and concept) else stem(raw))
    return out


class TfidfModel:
    """TF-IDF with the same formulas as scikit-learn's default: idf = ln((1+n)/(1+df)) + 1, then l2 normalisation."""

    def __init__(self, documents, use_concepts=True):
        self.use_concepts = use_concepts
        tokenised = [tokens(d, use_concepts) for d in documents]
        n = len(tokenised)
        df = Counter(t for doc in tokenised for t in set(doc))
        self.idf = {t: math.log((1 + n) / (1 + count)) + 1 for t, count in df.items()}

    def vector(self, text):
        counts = Counter(t for t in tokens(text, self.use_concepts) if t in self.idf)
        weights = {t: c * self.idf[t] for t, c in counts.items()}
        norm = math.sqrt(sum(w * w for w in weights.values()))
        return {t: w / norm for t, w in weights.items()} if norm else {}

    @staticmethod
    def cosine(a, b):
        if len(a) > len(b):
            a, b = b, a
        return sum(w * b.get(t, 0.0) for t, w in a.items())


def has_concept(statement, category):
    """Does the statement contain words of the obligation's topic? Unknown topics are not gated."""
    if category not in STRONG:
        return True
    raw = set(re.findall(r"[a-z]+", statement.lower()))
    present = raw | _stems(raw)
    if present & (STRONG[category] | _stems(STRONG[category])):
        return True
    weak = WEAK.get(category, set())
    return bool(present & (weak | _stems(weak))) and bool(TIME_CUE.search(statement))


def split_statements(text, minimum_words=4):
    """Cut policy text into statements: sentences, and bullet or numbered lines."""
    pieces = re.split(r"(?<=[.!?;])\s+|\n+|\s•\s", text)
    statements = []
    for piece in pieces:
        piece = re.sub(r"^\s*(?:\d+[.)]|[-•*]|\([a-z0-9]+\))\s*", "", piece).strip()
        if len(piece.split()) >= minimum_words:
            statements.append(piece)
    return statements


def best_matches(rule_texts, statements, use_concepts=True):
    """For each rule text: (best similarity, best statement). Statements and rules share one IDF model."""
    model = TfidfModel(list(rule_texts) + list(statements), use_concepts)
    statement_vectors = [(s, model.vector(s)) for s in statements]
    results = []
    for rule in rule_texts:
        rv = model.vector(rule)
        best, best_statement = 0.0, ""
        for s, sv in statement_vectors:
            sim = model.cosine(rv, sv)
            if sim > best:
                best, best_statement = sim, s
        results.append((round(best, 4), best_statement))
    return results


def assess(category, rule_texts, statements, addressed=ADDRESSED_THRESHOLD, partial=PARTIAL_THRESHOLD):
    """
    Does a policy (a list of statements) address the obligations of one topic?
    Returns (verdict, similarity, best statement).
      Addressed        a statement of the right topic whose similarity to an obligation is >= `addressed`
      Partly addressed a statement of the right topic with some similarity (>= `partial`)
      Not found        nothing in the policy matches the topic
    """
    if not statements or not rule_texts:
        return "Not found", 0.0, ""
    model = TfidfModel(list(rule_texts) + list(statements))
    rule_vectors = [model.vector(r) for r in rule_texts]
    best, best_statement = 0.0, ""
    for statement in statements:
        if not has_concept(statement, category):
            continue
        sv = model.vector(statement)
        similarity = max(model.cosine(sv, rv) for rv in rule_vectors)
        if similarity > best:
            best, best_statement = similarity, statement
    best = round(best, 4)
    if best >= addressed:
        return "Addressed", best, best_statement
    if best >= partial:
        return "Partly addressed", best, best_statement
    return "Not found", best, best_statement
