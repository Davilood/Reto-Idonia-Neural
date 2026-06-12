from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from app.clients.idonia_client import IdoniaClient
from app.clients.recog_client import RecogClient
from app.config import Settings, get_settings
from app.models.patient import Patient
from app.models.workflow_result import WorkflowResult, WorkflowStep
from app.services.dicom_service import DicomService
from app.services.magic_link_service import MagicLinkService
from app.services.pdf_service import PdfService
from app.services.report_service import ReportService
from app.utils.logger import get_logger, log_event, mask_identifier


T = TypeVar("T")


class MedicalWorkflowOrchestrator:
    def __init__(
        self,
        settings: Settings,
        idonia_client: IdoniaClient,
        recog_client: RecogClient,
        dicom_service: DicomService,
        pdf_service: PdfService,
        report_service: ReportService,
        magic_link_service: MagicLinkService,
        logger: logging.Logger,
    ) -> None:
        self.settings = settings
        self.idonia_client = idonia_client
        self.recog_client = recog_client
        self.dicom_service = dicom_service
        self.pdf_service = pdf_service
        self.report_service = report_service
        self.magic_link_service = magic_link_service
        self.logger = logger

    def run(
        self,
        patient: Patient,
        dicom_path: Path,
        medical_report_path: Path,
        workflow_id: str | None = None,
        on_update: Callable[[WorkflowResult], None] | None = None,
    ) -> WorkflowResult:
        workflow_id = workflow_id or uuid.uuid4().hex
        result = WorkflowResult.started(
            workflow_id=workflow_id,
            patient_dni=mask_identifier(patient.dni),
            patient_name=patient.name,
            mode=self.settings.mode,
        )
        started = time.perf_counter()

        log_event(
            self.logger,
            logging.INFO,
            "workflow.started",
            {
                "workflow_id": workflow_id,
                "patient": mask_identifier(patient.dni),
                "mode": result.mode,
            },
        )
        if on_update:
            on_update(result)

        try:
            dicom_summary = self._step(
                result,
                "validate_dicom",
                "Validar imagen DICOM",
                lambda: self.dicom_service.inspect(dicom_path),
                lambda summary: {
                    "filename": summary.filename,
                    "bytes": summary.size_bytes,
                    "dicom_preamble": summary.has_dicom_preamble,
                },
                on_update,
            )

            folder_id = self._step(
                result,
                "idonia_folder",
                "Crear carpeta segura en Idonia",
                lambda: self.idonia_client.ensure_patient_folder(patient),
                lambda value: {"patient_folder_id": value},
                on_update,
            )
            result.idonia["patient_folder_id"] = folder_id

            dicom_upload_id = self._step(
                result,
                "upload_dicom",
                "Subir estudio de imagen",
                lambda: self.idonia_client.upload_dicom(folder_id, dicom_path, dicom_summary),
                lambda value: {"dicom_upload_id": value},
                on_update,
            )
            result.idonia["dicom_upload_id"] = dicom_upload_id

            extracted_text = self._step(
                result,
                "extract_pdf",
                "Extraer texto del informe medico",
                lambda: self.pdf_service.extract_text(medical_report_path),
                lambda text: {"characters": len(text)},
                on_update,
            )

            medical_report_id = self._step(
                result,
                "upload_medical_report",
                "Subir informe medico original",
                lambda: self.idonia_client.upload_medical_report(
                    folder_id, medical_report_path
                ),
                lambda value: {"medical_report_id": value},
                on_update,
            )
            result.idonia["medical_report_id"] = medical_report_id

            recog_payload = self._step(
                result,
                "prepare_recog",
                "Preparar payload para Recog",
                lambda: self.report_service.summarize_for_recog(extracted_text),
                lambda text: {"payload_chars": len(text)},
                on_update,
            )

            humanized_report = self._step(
                result,
                "recog_humanize",
                "Humanizar informe con Recog",
                lambda: self.recog_client.humanize_report(recog_payload, patient),
                lambda report: {
                    "source": report.source,
                    "output_bytes": report.size_bytes,
                    "content_type": report.content_type,
                },
                on_update,
            )
            result.recog["source"] = humanized_report.source
            result.recog["content_type"] = humanized_report.content_type
            result.recog["output_bytes"] = humanized_report.size_bytes
            if humanized_report.body:
                result.recog["humanized_report"] = humanized_report.body

            output_pdf = self._step(
                result,
                "generate_patient_pdf",
                "Persistir informe para paciente",
                lambda: self.pdf_service.write_patient_report_pdf(
                    patient, humanized_report, workflow_id
                ),
                lambda path: {"output_pdf": str(path), "bytes": path.stat().st_size},
                on_update,
            )
            result.output_pdf = output_pdf

            patient_report_id = self._step(
                result,
                "upload_patient_report",
                "Subir Informe para paciente a Idonia",
                lambda: self.idonia_client.upload_patient_report(folder_id, output_pdf),
                lambda value: {"patient_report_id": value},
                on_update,
            )
            result.idonia["patient_report_id"] = patient_report_id

            magic_link = self._step(
                result,
                "magic_link",
                "Generar Magic Link QR+PIN",
                lambda: self.magic_link_service.create_for_patient_folder(folder_id),
                lambda link: {"url": link.url, "pin": link.pin, "qr": link.qr},
                on_update,
            )
            result.magic_link = magic_link

            result.status = "completed"
            return result
        except Exception as exc:
            result.status = "failed"
            result.debug["error"] = str(exc)
            log_event(
                self.logger,
                logging.ERROR,
                "workflow.failed",
                {"workflow_id": workflow_id, "error": str(exc)},
            )
            raise
        finally:
            result.finished_at = datetime.now(timezone.utc)
            result.duration_ms = round((time.perf_counter() - started) * 1000)
            log_event(
                self.logger,
                logging.INFO,
                "workflow.finished",
                {
                    "workflow_id": workflow_id,
                    "status": result.status,
                    "duration_ms": result.duration_ms,
                },
            )
            if on_update:
                on_update(result)

    def _step(
        self,
        result: WorkflowResult,
        key: str,
        label: str,
        action: Callable[[], T],
        metadata_builder: Callable[[T], dict[str, object]],
        on_update: Callable[[WorkflowResult], None] | None = None,
    ) -> T:
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        step = WorkflowStep(
            key=key,
            label=label,
            status="running",
            detail="En curso",
            duration_ms=0,
            started_at=started_at,
            metadata={},
        )
        result.steps.append(step)
        if on_update:
            on_update(result)
        log_event(
            self.logger,
            logging.DEBUG,
            "step.started",
            {"workflow_id": result.workflow_id, "step": key},
        )

        try:
            value = action()
            duration_ms = round((time.perf_counter() - started) * 1000)
            metadata = metadata_builder(value)
            step.status = "completed"
            step.detail = "Paso completado correctamente"
            step.duration_ms = duration_ms
            step.metadata = metadata
            log_event(
                self.logger,
                logging.INFO,
                "step.completed",
                {
                    "workflow_id": result.workflow_id,
                    "step": key,
                    "duration_ms": duration_ms,
                }
                | metadata,
            )
            if on_update:
                on_update(result)
            return value
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000)
            step.status = "failed"
            step.detail = str(exc)
            step.duration_ms = duration_ms
            step.metadata = {}
            log_event(
                self.logger,
                logging.ERROR,
                "step.failed",
                {
                    "workflow_id": result.workflow_id,
                    "step": key,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                },
            )
            if on_update:
                on_update(result)
            raise


def build_orchestrator(settings: Settings | None = None) -> MedicalWorkflowOrchestrator:
    settings = settings or get_settings()
    logger = get_logger("reto3.workflow")
    idonia_logger = get_logger("reto3.idonia")
    recog_logger = get_logger("reto3.recog")
    idonia_client = IdoniaClient(settings=settings, logger=idonia_logger)
    return MedicalWorkflowOrchestrator(
        settings=settings,
        idonia_client=idonia_client,
        recog_client=RecogClient(settings=settings, logger=recog_logger),
        dicom_service=DicomService(),
        pdf_service=PdfService(settings.output_dir),
        report_service=ReportService(),
        magic_link_service=MagicLinkService(idonia_client),
        logger=logger,
    )
