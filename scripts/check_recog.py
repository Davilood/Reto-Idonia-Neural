from __future__ import annotations

import logging
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.clients.recog_client import RecogClient
from app.config import get_settings
from app.models.patient import Patient
from app.services.pdf_service import PdfService
from app.utils.logger import bind_request_id, configure_logging, reset_request_id


SAMPLE_REPORT = (
    "Paciente con dolor e inflamacion de rodilla tras caida en montana. "
    "Se realiza resonancia magnetica. Se recomienda seguimiento clinico, "
    "control del dolor y revision por traumatologia."
)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    token = bind_request_id("check-recog")
    try:
        if settings.recog_use_mocks:
            print("Recog esta en simulacion local. Pon RECOG_USE_MOCKS=false para probar Recog real.")
        if not settings.recog_api_key:
            print("Falta RECOG_API_KEY en .env.")
            return

        patient = Patient(dni=settings.patient_dni, name=settings.patient_name)
        report = RecogClient(settings, logging.getLogger("reto3.recog")).humanize_report(
            SAMPLE_REPORT,
            patient,
        )
        output = PdfService(settings.output_dir).write_patient_report_pdf(
            patient,
            report,
            "recogcheck",
        )
        print(f"PDF Recog guardado en: {Path(output)}")
    finally:
        reset_request_id(token)


if __name__ == "__main__":
    main()
