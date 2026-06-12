from __future__ import annotations

import logging
from dataclasses import replace

from app.clients.idonia_client import IdoniaClient
from app.clients.recog_client import RecogClient
from app.config import get_settings
from app.models.patient import Patient
from app.orchestrator import MedicalWorkflowOrchestrator
from app.services.dicom_service import DicomService
from app.services.magic_link_service import MagicLinkService
from app.services.pdf_service import PdfService
from app.services.report_service import ReportService


def test_workflow_mock_completes_end_to_end(tmp_path):
    settings = replace(
        get_settings(),
        use_mocks=True,
        idonia_use_mocks=True,
        recog_use_mocks=True,
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
    )
    logger = logging.getLogger("test.workflow")
    idonia_client = IdoniaClient(settings, logger)
    orchestrator = MedicalWorkflowOrchestrator(
        settings=settings,
        idonia_client=idonia_client,
        recog_client=RecogClient(settings, logger),
        dicom_service=DicomService(),
        pdf_service=PdfService(settings.output_dir),
        report_service=ReportService(),
        magic_link_service=MagicLinkService(idonia_client),
        logger=logger,
    )

    dicom_path = tmp_path / "estudio.dcm"
    dicom_path.write_bytes((b"\0" * 128) + b"DICM" + b"mock-body")
    pdf_path = tmp_path / "informe.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% mock\n")

    result = orchestrator.run(
        patient=Patient(dni="12345678A", name="Paciente Demo"),
        dicom_path=dicom_path,
        medical_report_path=pdf_path,
        workflow_id="workflow123",
    )

    assert result.status == "completed"
    assert result.idonia["patient_folder_id"].startswith("mock-folder-")
    assert result.magic_link is not None
    assert result.magic_link.pin == "12345"
    assert result.output_pdf is not None
    assert result.output_pdf.exists()
    assert len(result.steps) == 10
