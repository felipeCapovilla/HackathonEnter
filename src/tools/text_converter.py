"""Read local PDF or text pages without writing plaintext sidecars."""

from collections.abc import Iterator
from pathlib import Path

from pypdf import PdfReader


def iter_document_pages(input_path: str | Path) -> Iterator[dict]:
    path = Path(input_path)
    if path.suffix.lower() in {".txt", ".md"}:
        with path.open(encoding="utf-8", errors="replace") as stream:
            content = stream.read(12000)
            while content:
                yield {"page_number": 1, "text_content": content}
                following = stream.read(11800)
                content = content[-200:] + following if following else ""
        return
    if path.suffix.lower() != ".pdf":
        raise ValueError("Formato não suportado; use PDF, TXT ou Markdown.")
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        if reader.is_encrypted:
            raise ValueError("PDF protegido; forneça uma cópia acessível para análise.")
        for number, page in enumerate(reader.pages, start=1):
            yield {"page_number": number, "text_content": page.extract_text() or ""}
