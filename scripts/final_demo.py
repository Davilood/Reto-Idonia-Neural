from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import get_settings
from app.models.patient import Patient
from app.orchestrator import build_orchestrator
from app.utils.errors import ExternalServiceError
from app.utils.logger import bind_request_id, configure_logging, reset_request_id


DEFAULT_DICOM = ROOT_DIR / "data" / "test.dcm"
DEFAULT_REPORT = ROOT_DIR / "data" / "Informe RM RODILLA.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the final real Reto 3 flow and print presentation evidence."
    )
    parser.add_argument("--dicom", default=str(DEFAULT_DICOM), help="DICOM file to upload.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Original medical PDF.")
    parser.add_argument("--patient-dni", help="Override PATIENT_DNI from .env.")
    parser.add_argument("--patient-name", help="Override PATIENT_NAME from .env.")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the configured Idonia study route before running.",
    )
    parser.add_argument(
        "--allow-mocks",
        action="store_true",
        help="Allow running when one service is still using local simulation.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)
    token = bind_request_id("final-demo")

    try:
        if settings.mode != "real" and not args.allow_mocks:
            raise SystemExit(
                "El modo final requiere IDONIA_USE_MOCKS=false y RECOG_USE_MOCKS=false. "
                "Usa --allow-mocks solo para desarrollo local."
            )
        if not settings.idonia_use_mocks and not settings.idonia_configured:
            raise SystemExit("Faltan variables reales de Idonia en .env.")
        if not settings.recog_use_mocks and not settings.recog_configured:
            raise SystemExit("Falta RECOG_API_KEY o RECOG_BASE_URL en .env.")

        dicom_path = Path(args.dicom).expanduser().resolve()
        report_path = Path(args.report).expanduser().resolve()
        _require_file(dicom_path, "DICOM")
        _require_file(report_path, "informe medico")

        patient = Patient(
            dni=(args.patient_dni or settings.patient_dni).strip(),
            name=(args.patient_name or settings.patient_name).strip() or "Paciente Demo",
        )
        orchestrator = build_orchestrator(settings)

        if args.clean:
            route = f"{patient.safe_folder_name}/{settings.idonia_accession_number}"
            print(f"Limpiando ruta Idonia: {route}")
            try:
                orchestrator.idonia_client.delete_route(route)
                print("Limpieza solicitada correctamente.")
            except ExternalServiceError as exc:
                print(f"Aviso: no se pudo limpiar antes de ejecutar: {exc}")

        result = orchestrator.run(
            patient=patient,
            dicom_path=dicom_path,
            medical_report_path=report_path,
        )

        print("\nFlujo final completado")
        print(f"Modo: {result.mode}")
        print(f"Workflow: {result.workflow_id}")
        print(f"Estado: {result.status}")
        print(f"Duracion: {result.duration_ms} ms")
        print(f"Magic Link: {result.magic_link.url if result.magic_link else '-'}")
        print(f"PIN: {result.magic_link.pin if result.magic_link else '-'}")
        print(f"PDF paciente: {result.output_pdf}")
        print("\nChecklist para Idonia:")
        print("- Estudio DICOM visible")
        print("- Informe medico original visible")
        print("- Informe para paciente visible")
        print("\nPasos:")
        for step in result.steps:
            print(f"- {step.key}: {step.status} ({step.duration_ms} ms)")
    finally:
        reset_request_id(token)


def _require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"No existe el archivo {label}: {path}")
    if not path.is_file():
        raise SystemExit(f"La ruta de {label} no es un archivo: {path}")


if __name__ == "__main__":
    main()
