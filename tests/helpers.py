"""Small builders used by several tests: CSV text, a .docx file and a .pdf file."""
import io
import zipfile
from datetime import date

HEADER = "data_subject_id,consent_status,collection_date,retention_period,record_status"


def csv_bytes(rows, header=HEADER):
    """rows: list of 5-item lists/tuples. Returns the file content as UTF-8 bytes."""
    lines = [header] + [",".join(str(cell) for cell in row) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def good_rows(n=3):
    return [[f"Customer{i:05d}", "Yes", "2025-01-15", "5 years", "Active"] for i in range(1, n + 1)]


def upload_csv(client, content, name="data.csv"):
    return client.post(
        "/upload",
        data={"dataset": (io.BytesIO(content), name)},
        content_type="multipart/form-data",
    )


def make_docx(text):
    """A minimal but valid Word document holding `text` (one paragraph per line)."""
    paragraphs = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{line}</w:t></w:r></w:p>" for line in text.split("\n")
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def make_pdf(text):
    """A minimal one-page PDF that contains `text` as real (selectable) text. text="" gives a blank page."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 11 Tf 40 740 Td ({safe}) Tj ET" if text else ""
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


POLICY_TEXT = (
    "Data Retention Policy. Customer personal data is kept for five years and is then deleted. "
    "Consent is recorded before any personal data is processed."
)


from contextlib import contextmanager

from flask import template_rendered


@contextmanager
def captured_context(app):
    """Collect the values a view passed to its template (so tests can check the numbers)."""
    contexts = []

    def collect(sender, template, context, **extra):
        contexts.append(context)

    template_rendered.connect(collect, app)
    try:
        yield contexts
    finally:
        template_rendered.disconnect(collect, app)


def finish_upload(client, content, name="data.csv"):
    """Upload a CSV and return the dataset id that the redirect points at."""
    response = upload_csv(client, content, name)
    assert response.status_code == 302, response.status_code
    return int(response.headers["Location"].rstrip("/").split("/")[-1])


def run_audit_via_web(client, content, name="data.csv"):
    """Upload, then press 'Proceed to audit'. Returns (dataset_id, audit_id)."""
    dataset_id = finish_upload(client, content, name)
    response = client.post(f"/upload/{dataset_id}/proceed")
    assert response.status_code == 302, response.status_code
    audit_id = int(response.headers["Location"].rstrip("/").split("/")[-1].split("?")[0])
    return dataset_id, audit_id
