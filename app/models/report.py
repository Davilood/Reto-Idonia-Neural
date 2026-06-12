from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class StoredFile(BaseModel):
    filename: str
    path: Path
    content_type: str = "application/octet-stream"
    size_bytes: int
    sha256: str


class DicomSummary(BaseModel):
    filename: str
    size_bytes: int
    has_dicom_preamble: bool
    modality_hint: str = "unknown"


class HumanizedReport(BaseModel):
    title: str = "Informe para paciente"
    body: str | None = Field(default=None)
    source: str = "generated"
    pdf_bytes: bytes | None = None
    content_type: str = "application/pdf"

    @property
    def size_bytes(self) -> int:
        if self.pdf_bytes is not None:
            return len(self.pdf_bytes)
        if self.body is not None:
            return len(self.body.encode("utf-8"))
        return 0


class MagicLink(BaseModel):
    url: str
    pin: str
    qr: str
