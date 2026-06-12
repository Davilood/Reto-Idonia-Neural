from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from urllib.parse import urljoin

from app.config import Settings
from app.models.patient import Patient
from app.models.report import HumanizedReport
from app.utils.errors import ExternalServiceError, ServiceNotConfiguredError
from app.utils.logger import log_event, mask_identifier


class RecogClient:
    def __init__(self, settings: Settings, logger: logging.Logger) -> None:
        self.settings = settings
        self.logger = logger

    def humanize_report(self, report_text: str, patient: Patient) -> HumanizedReport:
        if self.settings.recog_use_mocks:
            log_event(
                self.logger,
                logging.INFO,
                "recog.humanize.mocked",
                {
                    "patient": mask_identifier(patient.dni),
                    "input_chars": len(report_text),
                },
            )
            return HumanizedReport(
                body=_mock_humanized_text(report_text),
                source="mock-recog",
            )
        if not self.settings.recog_configured:
            raise ServiceNotConfiguredError(
                "Recog real mode requires RECOG_BASE_URL and RECOG_API_KEY."
            )

        url = urljoin(
            self.settings.recog_base_url.rstrip("/") + "/",
            self.settings.recog_report_results_path.lstrip("/"),
        )
        payload = json.dumps({"dictationReport": report_text}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/pdf",
                "X-API-Key": self.settings.recog_api_key,
            },
        )

        log_event(
            self.logger,
            logging.INFO,
            "recog.humanize.request",
            {
                "patient": mask_identifier(patient.dni),
                "url": url,
                "input_chars": len(report_text),
                "timeout_seconds": self.settings.recog_timeout_seconds,
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.settings.recog_timeout_seconds,
            ) as response:
                pdf_bytes = response.read()
                content_type = response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            error_body = _read_error_body(exc)
            raise ExternalServiceError(
                f"Recog API returned HTTP {exc.code}: {error_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ExternalServiceError(f"Recog API connection error: {exc.reason}") from exc

        if not pdf_bytes.startswith(b"%PDF"):
            preview = pdf_bytes[:240].decode("utf-8", errors="replace")
            raise ExternalServiceError(
                f"Recog API did not return a PDF. Content-Type={content_type}. "
                f"Preview={preview!r}"
            )

        log_event(
            self.logger,
            logging.INFO,
            "recog.humanize.completed",
            {
                "patient": mask_identifier(patient.dni),
                "content_type": content_type,
                "output_bytes": len(pdf_bytes),
            },
        )
        return HumanizedReport(
            source="recog-report-results-api",
            pdf_bytes=pdf_bytes,
            content_type=content_type,
        )


def _mock_humanized_text(report_text: str) -> str:
    finding_hint = " ".join(report_text.split())[:320]
    if not finding_hint:
        finding_hint = "El informe original se ha recibido y procesado correctamente."

    return (
        "Hola, queremos explicarte de forma sencilla el resultado de tu prueba. "
        "La resonancia y el informe medico han sido incorporados a una carpeta segura "
        "para que el equipo que continua tu seguimiento pueda consultarlos sin barreras. "
        "En terminos generales, el documento original describe los hallazgos observados "
        "por el especialista y sirve para orientar las siguientes decisiones clinicas. "
        f"Resumen tecnico usado como referencia: {finding_hint}. "
        "Si tienes dolor, aumento de inflamacion, fiebre o dificultad progresiva para apoyar, "
        "contacta con tu profesional sanitario. Este texto no sustituye la valoracion medica, "
        "pero te ayuda a entender el informe y preparar tus dudas para la consulta."
    )


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read(800).decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    return body or exc.reason or "sin detalle"
