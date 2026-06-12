from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from app.models.patient import Patient
from app.models.report import HumanizedReport
from app.utils.errors import InputValidationError


class PdfService:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_text(self, path: Path) -> str:
        if not path.exists():
            raise InputValidationError(f"PDF file does not exist: {path}")
        if path.stat().st_size == 0:
            raise InputValidationError("PDF file is empty")

        try:
            completed = subprocess.run(
                ["pdftotext", str(path), "-"],
                check=True,
                capture_output=True,
                text=True,
                timeout=8,
            )
            text = completed.stdout.strip()
            if text:
                return text
        except Exception:
            pass

        return (
            "Informe medico cargado correctamente. "
            "La extraccion de texto no esta disponible en este entorno, "
            "asi que el flujo continua con un resumen tecnico minimo."
        )

    def write_humanized_pdf(
        self,
        patient: Patient,
        report: HumanizedReport,
        workflow_id: str,
    ) -> Path:
        patient_dir = self.output_dir / patient.safe_folder_name
        patient_dir.mkdir(parents=True, exist_ok=True)

        output_path = patient_dir / f"informe_paciente_{workflow_id[:8]}.pdf"
        body = report.body or "Informe humanizado recibido sin texto adjunto."
        lines = [
            "Reto 3 - Informe para paciente",
            f"Paciente: {patient.name}",
            f"DNI: {patient.dni}",
            "",
            report.title,
            "",
            *textwrap.wrap(body, width=92),
        ]
        output_path.write_bytes(_build_simple_pdf(lines))
        return output_path

    def write_patient_report_pdf(
        self,
        patient: Patient,
        report: HumanizedReport,
        workflow_id: str,
    ) -> Path:
        if report.pdf_bytes is None:
            return self.write_humanized_pdf(patient, report, workflow_id)

        patient_dir = self.output_dir / patient.safe_folder_name
        patient_dir.mkdir(parents=True, exist_ok=True)
        output_path = patient_dir / f"informe_paciente_{workflow_id[:8]}.pdf"
        output_path.write_bytes(report.pdf_bytes)
        return output_path


def _build_simple_pdf(lines: list[str]) -> bytes:
    escaped_lines = [_escape_pdf_text(line) for line in lines]
    content_lines = ["BT", "/F1 12 Tf", "50 770 Td", "16 TL"]
    for index, line in enumerate(escaped_lines):
        if index == 0:
            content_lines.append(f"({line}) Tj")
        else:
            content_lines.append("T*")
            content_lines.append(f"({line}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _escape_pdf_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )
