"""Language processing: reading the Act, extracting rules, comparing a policy (FR-05, FR-06, FR-08, NFR-06). TC-N01 to TC-N10."""
import csv
import importlib.util
import json
from pathlib import Path

import pytest

from app.nlp import similarity as sim

ROOT = Path(__file__).resolve().parent.parent
ACT_PDF = ROOT / "data" / "raw" / "legal" / "TheDataProtectionAct__No24of2019.pdf"

RULES = {
    "consent": ["Personal data may only be processed where the data subject has given valid consent, or another lawful basis applies."],
    "retention": ["A data controller or data processor shall retain personal data only as long as may be reasonably necessary to satisfy the purpose for which it is processed.",
                  "A data controller or data processor shall delete, erase, anonymise or pseudonymise personal data not necessary to be retained at the expiry of the retention period."],
}


def test_tfidf_matches_scikit_learn(record):
    sk = pytest.importorskip("sklearn.feature_extraction.text")
    pairwise = pytest.importorskip("sklearn.metrics.pairwise")
    docs = ["personal data is deleted after five years", "consent is recorded before processing personal data",
            "access to the database is restricted", "records are kept for five years then deleted"]
    # compare on plain tokens (no concept words) so that both sides see identical vocabulary
    analyzer = lambda text: sim.tokens(text, use_concepts=False)
    vec = sk.TfidfVectorizer(analyzer=analyzer)
    matrix = vec.fit_transform(docs)
    expected = pairwise.cosine_similarity(matrix)
    model = sim.TfidfModel(docs, use_concepts=False)
    worst = 0.0
    for i, a in enumerate(docs):
        for j, b in enumerate(docs):
            mine = model.cosine(model.vector(a), model.vector(b))
            worst = max(worst, abs(mine - expected[i][j]))
    assert worst < 1e-9
    record("TC-N01", f"The 4 x 4 cosine similarity matrix of the plain-Python TF-IDF matched scikit-learn's to within {worst:.1e}.")


def test_word_forms_and_domain_concepts(record):
    forms = {"deleted": "retain", "erasure": "retain", "destroyed": "retain", "retention": "retain",
             "permission": "consent", "withdraw": "consent", "consented": "consent"}
    for word, concept in forms.items():
        assert sim.tokens(word) == [concept], word
    assert sim.tokens("The records are being deleted.") == ["record", "retain"]
    record("TC-N02", "Seven word forms (deleted, erasure, destroyed, retention, permission, withdraw, consented) were each mapped to the right concept word; stop words were dropped.")


def test_concept_gate(record):
    assert not sim.has_concept("All personal data is encrypted in transit and at rest.", "retention")
    assert not sim.has_concept("Personal data must be accurate and kept up to date.", "retention")      # weak word, no time cue
    assert sim.has_concept("Job applicants' details are kept for six months and then removed.", "retention")
    assert sim.has_concept("Customers are asked to opt in before receiving marketing messages.", "consent")
    assert not sim.has_concept("Visitors must sign the register at reception.", "consent")
    record("TC-N03", "Security and accuracy statements did not pass the retention gate; 'kept for six months' (weak word plus a time cue) and 'opt in' passed their gates.")


def test_assess_verdicts(record):
    policy = sim.split_statements(
        "Our offices open at eight. Customer records are deleted five years after the contract ends. "
        "Visitors sign the register. We ask customers for their consent before collecting personal data.")
    assert sim.assess("retention", RULES["retention"], policy)[0] == "Addressed"
    assert sim.assess("consent", RULES["consent"], policy)[0] == "Addressed"
    verdict, score, statement = sim.assess("retention", RULES["retention"], sim.split_statements("Visitors sign the register. Our offices open at eight."))
    assert (verdict, statement) == ("Not found", "")
    assert sim.assess("consent", RULES["consent"], [])[0] == "Not found"
    record("TC-N04", "A policy with a deletion sentence and a consent sentence: both topics 'Addressed'. A policy about opening hours: 'Not found' with no statement quoted. An empty policy: 'Not found'.")


def test_statement_splitting(record):
    text = "1. Data is deleted after five years.\n- We ask for consent first\nShort one.\n(a) Customers may withdraw consent at any time; they are told how."
    parts = sim.split_statements(text)
    assert parts == ["Data is deleted after five years.", "We ask for consent first",
                     "Customers may withdraw consent at any time;", "they are told how."]
    record("TC-N05", f"Numbered and bulleted lines and sentences were separated and their markers removed; a 2-word fragment was dropped. Result: {len(parts)} statements.")


def _spacy_usable():
    """True only if spaCy really loads with its English model. On some Windows computers the library is installed but
    Windows Application Control blocks its compiled files, so checking that it is installed is not enough."""
    if not ACT_PDF.exists():
        return False
    try:
        import spacy
        spacy.load("en_core_web_sm")
        return True
    except Exception:  # ImportError, a blocked DLL, a missing model ...
        return False


needs_act = pytest.mark.skipif(not ACT_PDF.exists(), reason="the Act PDF is missing")
needs_spacy = pytest.mark.skipif(not _spacy_usable(), reason="spaCy (with en_core_web_sm) cannot be loaded here, or the Act PDF is missing")


@pytest.fixture(scope="module")
def act_raw():
    from app.nlp import act_reader
    return act_reader.read_pdf_text(ACT_PDF)


@needs_act
def test_act_reader(act_raw, record):
    from app.nlp import act_reader
    provisions = act_reader.provisions(act_raw)
    sections = {p.section for p in provisions}
    s39 = [p for p in provisions if p.section == 39]
    assert set(act_reader.split_sections(act_raw)) == set(range(1, 76))          # all 75 sections located
    assert len(set(range(1, 76)) - sections) <= 3                                 # a few sections (such as the schedule of amendments) hold no provisions
    assert [p.reference for p in s39] == ["Section 39(1)", "Section 39(2)"]
    assert "delete, erase, anonymise or pseudonymise personal data" in s39[1].text
    assert "Limitation to retention" not in s39[0].text and "No. 24" not in s39[0].text   # margin notes and page headers removed
    record("TC-N06", f"The reader located all 75 sections and read {len(provisions)} provisions from {len(sections)} of them (Sections 71 and 75 hold no provisions to read). Section 39 gave two provisions; page headers and margin notes were absent from their text.")


@needs_spacy
def test_extractor_on_known_sentences(record):
    from app.nlp import extractor
    from app.nlp.act_reader import Provision

    def run(text):
        return extractor.analyse(Provision(1, "1", "t", text))

    cases = {
        "A data controller shall retain personal data only as long as necessary.": "obligation",
        "A data controller or data processor shall not process personal data, unless the data subject consents.": "prohibition",
        "A data subject has the right to withdraw consent at any time.": "right",
        "A data subject may request a data controller to erase personal data.": "permission",
        "Sub-section (1) shall not apply where the processing is necessary.": "statement",
        "A data controller who contravenes this section commits an offence.": "none",
    }
    seen = []
    for text, expected in cases.items():
        got = run(text)
        assert got.modality == expected, (text, got.modality)
        seen.append(f"{expected}")
    c = run("A data controller shall delete personal data at the expiry of the retention period.")
    assert (c.actor, c.action, c.retention, c.is_candidate) == ("data controller", "delete", True, True)
    record("TC-N07", "Six sentences were classified as obligation, prohibition, right, permission, statement and none, as a reader would; the actor 'data controller' and action 'delete' were extracted and the sentence became a retention candidate.")


@needs_spacy
def test_extractor_meets_nfr06_on_unseen_sections(record):
    spec = importlib.util.spec_from_file_location("evalnlp", ROOT / "scripts" / "evaluate_nlp_extraction.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from app.nlp import act_reader, extractor

    def duty_scores(path):
        reference = {r["reference"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}
        wanted = {int(r.split()[1].split("(")[0]) for r in reference}
        provisions = [p for p in act_reader.provisions(act_raw_text, only=wanted) if p.reference in reference]
        pairs = [(c.is_duty, reference[c.reference]["type"] == "OBLIGATION") for c in extractor.extract(provisions)]
        tp = sum(p and e for p, e in pairs); fp = sum(p and not e for p, e in pairs); fn = sum(e and not p for p, e in pairs)
        return module.prf(tp, fp, fn), len(pairs), sum(e for _, e in pairs)

    act_raw_text = act_reader.read_pdf_text(ACT_PDF)
    (hp, hr, _), n_held, duties_held = duty_scores(ROOT / "data" / "reference" / "act_reference_heldout.csv")
    (dp, dr, _), n_dev, duties_dev = duty_scores(ROOT / "data" / "reference" / "act_reference_dev.csv")
    assert hp >= 0.75 and hr >= 0.70, (hp, hr)      # NFR-06 on provisions the extractor was not built on
    assert dp >= 0.75 and dr >= 0.70, (dp, dr)
    record("TC-N08", f"Duty detection against hand-labelled provisions. Held-out sections 18-24 and 44-55 ({n_held} provisions, {duties_held} duties): precision {hp:.1%}, recall {hr:.1%}. Development sections 25-43 ({n_dev} provisions, {duties_dev} duties): precision {dp:.1%}, recall {dr:.1%}. NFR-06 thresholds: precision 75%, recall 70%.")


def test_candidate_file(record):
    path = ROOT / "data" / "knowledge_base" / "act_candidates.json"
    data = json.loads(path.read_text(encoding="utf-8"))["candidates"]
    codes = {c["candidate_code"]: c for c in data}
    assert {"ACT-S30-1", "ACT-S32-1", "ACT-S39-1", "ACT-S39-2"} <= set(codes)
    assert codes["ACT-S39-2"]["category"] == "retention" and codes["ACT-S32-1"]["category"] == "consent"
    assert all(c["category"] in ("consent", "retention") and c["obligation_text"] for c in data)
    record("TC-N09", f"The candidate file holds {len(data)} proposed rules, including Sections 30(1), 32(1), 39(1) and 39(2); each has a category and the text of the Act.")


def test_policy_comparison_accuracy_beats_plain_tfidf(record):
    spec = importlib.util.spec_from_file_location("evalpol", ROOT / "scripts" / "evaluate_policy_comparison.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = list(csv.DictReader(open(module.DEFAULT_CSV, encoding="utf-8")))
    rules = module.rule_texts()
    best = max([round(0.05 * i, 2) for i in range(1, 11)], key=lambda th: sum(v[2] for v in module.policy_level(rows, "dev", rules, "baseline", th).values()))
    base = module.policy_level(rows, "test", rules, "baseline", best)
    new = module.policy_level(rows, "test", rules, "proposed")
    for category in module.CATEGORIES:
        assert new[category][2] > base[category][2], category
        assert new[category][1] >= 0.90                       # a policy that does address the topic is almost always recognised
    line = "; ".join(f"{c}: baseline accuracy {base[c][2]:.0%} (P {base[c][0]:.0%}, R {base[c][1]:.0%}) vs proposed {new[c][2]:.0%} (P {new[c][0]:.0%}, R {new[c][1]:.0%})" for c in module.CATEGORIES)
    record("TC-N10", f"On the 30 test statements, in 600 balanced test policies: {line}.")