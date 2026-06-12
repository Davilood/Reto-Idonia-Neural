from __future__ import annotations

from app.models.patient import Patient
from app.models.report import HumanizedReport
from app.services.pdf_service import PdfService


def test_write_humanized_pdf_creates_valid_pdf(tmp_path):
    service = PdfService(tmp_path)
    patient = Patient(dni="12345678A", name="Paciente Demo")
    report = HumanizedReport(body="Texto humanizado para el paciente.")

    output = service.write_humanized_pdf(patient, report, "workflow123")

    assert output.exists()
    assert output.read_bytes().startswith(b"%PDF-1.4")
    assert output.name == "informe_paciente_workflow.pdf"


def test_write_patient_report_pdf_uses_recog_pdf_bytes(tmp_path):
    service = PdfService(tmp_path)
    patient = Patient(dni="12345678A", name="Paciente Demo")
    report = HumanizedReport(source="recog", pdf_bytes=b"%PDF-1.4\nrecog")

    output = service.write_patient_report_pdf(patient, report, "workflow123")

    assert output.exists()
    assert output.read_bytes() == b"%PDF-1.4\nrecog"
