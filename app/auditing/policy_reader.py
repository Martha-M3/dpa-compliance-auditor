"""
Reading the text out of an uploaded policy document (FR-02, FR-05, IR-02).

The audit system cannot compare a policy with the Data Protection Act until the
policy is plain text. This module turns a .pdf, .docx or .txt file into clean
text. Like dataset_schema.py it never crashes on a bad file: every problem
becomes a plain-English PolicyReadError that can be shown to the user.

Only pure-Python tools are used (pypdf, and zipfile for .docx), so nothing
compiled has to be installed.
"""
import re
import xml.etree.ElementTree as ET
import zipfile

from pypdf import PdfReader

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# A real policy has far more than this. A scanned (picture-only) PDF has none.
MIN_CHARACTERS = 50

# A .docx is a zip file. Refuse one whose text part would unpack to something
# huge (a "zip bomb").
MAX_DOCX_XML_BYTES = 50 * 1024 * 1024

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class PolicyReadError(Exception):
    """The file could not be turned into text. The message is safe to show the user."""


def _read_txt(path):
    raw = path.read_bytes()
    try:
        # utf-8-sig also removes the invisible marker Notepad adds at the start.
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Older Windows files; anything unreadable becomes a replacement mark.
        return raw.decode("cp1252", errors="replace")


def _read_pdf(path):
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise PolicyReadError("The PDF is password-protected. Remove the password and upload it again.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except PolicyReadError:
        raise
    except Exception as error:  # pypdf can raise many kinds of error on damaged files
        raise PolicyReadError("The PDF could not be opened. It may be damaged.") from error
    return "\n\n".join(pages)


def _read_docx(path):
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise PolicyReadError("The Word document is too large to read.")
            root = ET.fromstring(archive.read("word/document.xml"))
    except PolicyReadError:
        raise
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise PolicyReadError(
            "The file is not a valid .docx document. (Old .doc files are not supported: "
            "open it in Word and use Save As > Word Document (.docx).)"
        ) from error

    # Every paragraph is a <w:p>; its words sit in <w:t> elements.
    paragraphs = []
    for paragraph in root.iter(WORD_NS + "p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == WORD_NS + "t":
                parts.append(node.text or "")
            elif node.tag in (WORD_NS + "tab", WORD_NS + "br"):
                parts.append(" ")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def clean_text(text):
    """Tidy extracted text so it is ready for analysis."""
    text = text.replace("\x00", "")  # PostgreSQL refuses text containing NUL characters
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)  # runs of spaces, tabs, odd spaces -> one space
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()  # at most one blank line in a row


def read_policy(path, extension):
    """Return the cleaned text of the policy file at `path` (extension like '.pdf')."""
    readers = {".txt": _read_txt, ".pdf": _read_pdf, ".docx": _read_docx}
    if extension not in readers:
        raise PolicyReadError("Only PDF, Word (.docx) and text (.txt) files are accepted.")

    text = clean_text(readers[extension](path))
    if len(text) < MIN_CHARACTERS:
        raise PolicyReadError(
            "No readable text was found in this file. If it is a scanned document "
            "(a picture of a page), the system cannot read it. Upload a text-based copy."
        )
    return text