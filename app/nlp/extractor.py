"""
Rule extraction from the Data Protection Act with spaCy (FR-06, NFR-06).

For every provision of the Act (see act_reader.py) the extractor answers four questions:

  1. Does the provision impose a duty? It looks for a modal verb ("shall", "must") whose main verb
     is not "have the right", and records whether the duty is negative ("shall not" = prohibition).
     Provisions that grant rights ("has a right to ..."), permissions ("may ..."), exceptions
     ("shall not apply") and definitions are recognised and set aside.
  2. Who must do what? The grammatical subject of the modal verb is the actor, the verb is the
     action, its direct object is the object, and an "unless" / "where" / "if" clause is the condition.
  3. Which topic does it concern? Consent and retention are recognised from the lemmas
     (base forms) of the words, so "consented", "consents" and "consent" all count.
  4. How sure is it? A simple score from how many signals agree.

A provision that is a duty AND concerns consent or retention becomes a candidate rule. Candidates
are proposals: an administrator reviews them before they are used (FR-04).

The English model is loaded only when it is first needed, and the rest of the system never imports
this module, so spaCy is not needed to run the website.
"""
import re
from dataclasses import asdict, dataclass, field

MODAL_DUTY = {"shall", "must"}
MODAL_PERMISSION = {"may", "can"}
# Verbs that turn "shall" into an exception or a deeming rule rather than a duty on someone:
# "Sub-section (1) shall not apply where ...", "the processor shall be deemed to be a controller".
STATEMENT_VERBS = {"apply", "deem"}

CONSENT_LEMMAS = {"consent"}
RETENTION_LEMMAS = {"retain", "retention", "delete", "erase", "erasure", "destroy", "expiry",
                    "anonymise", "anonymize", "pseudonymise", "pseudonymize"}

CONTROLLER_WORDS = {"controller", "processor"}
LEADING_WORDS = {"a", "an", "the", "every", "any", "each"}

_nlp = None


def get_nlp():
    """Load spaCy and its small English model once."""
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load("en_core_web_sm", disable=["ner"])
        except OSError as error:
            raise RuntimeError(
                "The spaCy English model is missing. Install it with: python -m spacy download en_core_web_sm"
            ) from error
    return _nlp


@dataclass
class Candidate:
    reference: str
    title: str
    text: str
    modality: str            # obligation | prohibition | right | permission | statement | none
    actor: str = ""
    action: str = ""
    object: str = ""
    condition: str = ""
    consent: bool = False
    retention: bool = False
    confidence: float = 0.0
    lead: str = field(default="", repr=False)

    @property
    def is_duty(self):
        return self.modality in ("obligation", "prohibition")

    @property
    def category(self):
        if self.consent and self.retention:
            return "consent" if "consent" in self.lead.lower() else "retention"
        return "consent" if self.consent else ("retention" if self.retention else "other")

    @property
    def is_candidate(self):
        return self.is_duty and (self.consent or self.retention)

    def as_dict(self):
        d = asdict(self)
        d.pop("lead", None)
        d["category"] = self.category
        d["is_candidate"] = self.is_candidate
        return d


def lead_sentence(text):
    """The main clause: the text before the first list of items ('— (a) ...')."""
    text = re.split(r"\s—\s|—\s*\(a\)|\s\(a\)\s", text, maxsplit=1)[0]
    text = re.sub(r"\s+", " ", text).strip(" —:;")
    return text


def _clean_phrase(tokens):
    words = [t.text for t in tokens]
    while words and words[0].lower() in LEADING_WORDS:
        words.pop(0)
    return " ".join(words)


def _subtree_text(token, exclude=()):
    return _clean_phrase([t for t in token.subtree if t.i not in exclude])


def _find_modal(doc):
    """The first modal verb that governs a main verb: (modal token, verb token) or None."""
    for token in doc:
        if token.tag_ == "MD" or token.lower_ in MODAL_DUTY | MODAL_PERMISSION:
            if token.lower_ in MODAL_DUTY | MODAL_PERMISSION:
                return token, token.head
    return None


def _negated(modal, verb):
    return any(c.dep_ == "neg" for c in list(modal.children) + list(verb.children))


def _classify(doc):
    """Modality, actor, action and object of one parsed clause. Returns a dict."""
    out = {"modality": "none", "actor": "", "action": "", "object": ""}

    # "A data subject has a right to ..." (no modal verb)
    for token in doc:
        if token.lemma_ == "right" and token.dep_ in ("dobj", "attr") and token.head.lemma_ == "have":
            out["modality"] = "right"
            return out

    found = _find_modal(doc)
    if not found:
        return out
    modal, verb = found
    has_right = verb.lemma_ == "have" and any(c.lemma_ == "right" for c in verb.children)
    negated = _negated(modal, verb)
    passive_require = verb.lemma_ == "require" and any(c.dep_ == "auxpass" for c in verb.children)
    if modal.lower_ in MODAL_PERMISSION:
        out["modality"] = "right" if has_right else "permission"
    elif has_right:
        out["modality"] = "right"
    elif verb.lemma_ in STATEMENT_VERBS or any(c.lemma_ in STATEMENT_VERBS for c in verb.children if c.dep_ in ("auxpass", "xcomp", "conj")):
        out["modality"] = "statement"
    elif negated and passive_require:          # "shall not be required to ..." is an exemption, not a duty
        out["modality"] = "statement"
    else:
        out["modality"] = "prohibition" if negated else "obligation"

    subj = [c for c in verb.children if c.dep_ in ("nsubj", "nsubjpass")]
    if subj:
        out["actor"] = _subtree_text(subj[0], exclude={c.i for c in subj[0].subtree if c.dep_ == "relcl"})
    out["action"] = verb.lemma_.lower()
    objs = [c for c in verb.children if c.dep_ in ("dobj", "attr", "oprd", "acomp")]
    if objs:
        out["object"] = _subtree_text(objs[0])
    return out


def _first_item(text):
    """The text of item (a) of a provision, or ''. Used when the main clause only sets the scene
    ('Where ... a decision is taken —') and the duty itself is stated in the items."""
    m = re.search(r"\(a\)\s+(.*?)(?=\s\([b-z]\)\s|$)", text)
    return m.group(1).strip() if m else ""


def analyse(provision):
    nlp = get_nlp()
    full = nlp(provision.text)
    consent = any(t.lemma_.lower() in CONSENT_LEMMAS for t in full)
    retention = any(t.lemma_.lower() in RETENTION_LEMMAS for t in full)

    lead = lead_sentence(provision.text)
    doc = nlp(lead)
    info = _classify(doc)
    if info["modality"] == "none":
        item = _first_item(provision.text)
        if item:
            item_info = _classify(nlp(item))
            if item_info["modality"] != "none":
                info = item_info
    candidate = Candidate(provision.reference, provision.title, provision.text, info["modality"],
                          actor=info["actor"], action=info["action"], object=info["object"],
                          consent=consent, retention=retention, lead=lead)

    # Condition: an unless / where / if clause
    m = re.search(r"\b(unless|where|if|provided that|before|within)\b(.+)$", lead, flags=re.I)
    if m and candidate.is_duty:
        candidate.condition = (m.group(1) + m.group(2)).strip()

    # Confidence: how many independent signals agree
    score = 0.0
    if candidate.is_duty:
        score += 0.5
        if candidate.action:
            score += 0.1
        if any(w in candidate.actor.lower().split() for w in CONTROLLER_WORDS):
            score += 0.2
        lead_lemmas = {t.lemma_.lower() for t in doc}
        if lead_lemmas & (CONSENT_LEMMAS | RETENTION_LEMMAS):
            score += 0.2
    candidate.confidence = round(min(score, 1.0), 2)
    return candidate


def extract(provisions):
    """Analyse every provision. Returns a list of Candidate."""
    return [analyse(p) for p in provisions]
