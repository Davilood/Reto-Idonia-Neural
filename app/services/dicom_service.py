from __future__ import annotations

from pathlib import Path

from app.models.report import DicomSummary
from app.utils.errors import InputValidationError


class DicomService:
    def inspect(self, path: Path) -> DicomSummary:
        if not path.exists():
            raise InputValidationError(f"DICOM file does not exist: {path}")
        if path.stat().st_size == 0:
            raise InputValidationError("DICOM file is empty")

        with path.open("rb") as file:
            header = file.read(132)

        has_preamble = len(header) >= 132 and header[128:132] == b"DICM"
        return DicomSummary(
            filename=path.name,
            size_bytes=path.stat().st_size,
            has_dicom_preamble=has_preamble,
            modality_hint="MR" if path.suffix.lower() in {".dcm", ".dicom"} else "unknown",
        )

