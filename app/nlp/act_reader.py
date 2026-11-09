"""
Reading the Data Protection Act into numbered provisions (FR-02, FR-05).

The Act is supplied as a PDF whose text was produced by scanning (OCR). Besides the law itself,
that text contains page headers ("No. 24  Data Protection  2019"), page numbers and the short
margin notes that print each section's title beside it. All of these have to be removed before
language analysis, or they would end up in the middle of legal sentences.

The result is a list of provisions. A provision is one numbered subsection, for example
"Section 39(2)", together with any lettered items (a), (b) ... that belong to it.
This module uses only the standard library and pypdf, so it needs nothing compiled.
"""
import re
from dataclasses import dataclass

from pypdf import PdfReader

# Page furniture that appears on every page of the Gazette.
HEADER_LINES = [
    re.compile(r"^\s*No\.\s*24\s*(Data Protection\s*(2019)?)?\s*$", re.I),
    re.compile(r"^\s*2019\s*Data Protection\s*(No\.\s*24)?\s*$", re.I),
    re.compile(r"^\s*Data Protection\s*$", re.I),
    re.compile(r"^\s*\d{3,4}\s*$"),   # page numbers such as 926
    re.compile(r"^\s*THE\s+DATA\s+PROTECTION\s+ACT.*$", re.I),
]
TOC_LINE = re.compile(r"^\s*(\d{1,2})\.\s*—\s*(.+?)\s*$")


@dataclass
class Provision:
    section: int
    subsection: str      # "1", "2" ... or "" when the section has no numbered subsections
    title: str           # the section's title, e.g. "Limitation to retention of personal data"
    text: str            # clean text of the provision, items included

    @property
    def reference(self):
        return f"Section {self.section}({self.subsection})" if self.subsection else f"Section {self.section}"


def read_pdf_text(path):
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def section_titles(raw):
    """Titles from the Act's table of sections ('39. —Limitation to retention of personal data.')."""
    titles, last = {}, None
    for line in raw.split("\n")[:400]:
        m = TOC_LINE.match(line)
        if m:
            number, title = int(m.group(1)), m.group(2)
            if number in titles:
                break                      # the table of sections has ended
            titles[number] = re.sub(r"\s+", " ", title).rstrip(". ").strip()
            last = number
        elif last and line.strip() and not line.strip().startswith("PART") and not re.match(r"^\s*\d+\.", line) \
                and len(line.split()) <= 6 and last in titles and not titles[last].endswith(")"):
            if line.strip()[0].islower() or titles[last].split()[-1] in ("of", "to", "the", "and"):
                titles[last] += " " + line.strip().rstrip(". ")
    return titles


def _strip_page_furniture(raw):
    return "\n".join(line for line in raw.split("\n") if not any(p.match(line) for p in HEADER_LINES))


def _remove_margin_notes(text, titles):
    """Margin notes repeat a section title (sometimes with 'of' for 'for'). Remove them wherever they sit."""
    for title in titles.values():
        words = re.findall(r"[A-Za-z']+", title)
        if len(words) < 2:
            continue
        pattern = r"\s+".join(re.escape(w) for w in words) + r"\s*\.?"
        text = re.sub(pattern, " ", text, flags=re.I)
    text = re.sub(r"Conditions\s+of\s+consent\s*\.?", " ", text, flags=re.I)
    return text


def split_sections(raw, titles=None):
    """Return {section number: text} for the body of the Act (after the table of sections)."""
    titles = titles or section_titles(raw)
    start = re.search(r"(?m)^\s*1\.\s+This\s+Act\s+may\s+be\s+cited", raw)
    body = raw[start.start():] if start else raw
    body = _strip_page_furniture(body)
    sections, pos, number = {}, 0, 1
    marks = []
    while True:
        # A section number normally starts a line, but a margin note can sit just before it on the
        # same line ("... personal liability. 17. The Data Commissioner ..."), so a full stop also counts.
        m = re.compile(r"(?:^|(?<=\.\s))\s*%d\.\s+(?=\(|[A-Z\"“])" % number, re.M).search(body, pos)
        if not m:
            break
        marks.append((number, m.start(), m.end()))
        pos = m.end()
        number += 1
    for i, (num, s, e) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(body)
        sections[num] = body[e:end]
    return sections


def _flatten(text):
    text = text.replace("\t", " ")
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def provisions(raw, only=None):
    """All provisions of the Act (or only the given section numbers)."""
    titles = section_titles(raw)
    out = []
    for number, text in split_sections(raw, titles).items():
        if only and number not in only:
            continue
        text = _remove_margin_notes(text, titles)
        parts = re.split(r"(?m)^\s*\((\d{1,2})\)\s+(?=[A-Z\"“a-z])", text)
        # parts = [lead, '1', body1, '2', body2 ...]; a numbered subsection is (1), (2) ... in sequence
        lead, rest = parts[0], parts[1:]
        title = titles.get(number, "")
        if not rest:
            body = _flatten(text)
            if body:
                out.append(Provision(number, "", title, body))
            continue
        expected = 1
        current = None
        buffer = [_flatten(lead)] if _flatten(lead) else []
        pieces = []
        for k in range(0, len(rest), 2):
            n, body = int(rest[k]), rest[k + 1]
            if n == expected:
                if current is not None:
                    pieces.append((current, " ".join(buffer)))
                current, buffer = str(n), [_flatten(body)]
                expected += 1
            else:                              # not a new subsection: part of a lettered list, e.g. "(2)" inside text
                buffer.append(f"({n}) " + _flatten(body))
        if current is not None:
            pieces.append((current, " ".join(buffer)))
        for sub, body in pieces:
            out.append(Provision(number, sub, title, body))
    return out
