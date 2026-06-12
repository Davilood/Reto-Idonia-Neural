from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.clients.idonia_client import IdoniaClient
from app.config import get_settings
from app.models.patient import Patient
from app.utils.errors import ExternalServiceError
from app.utils.logger import bind_request_id, configure_logging, reset_request_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List or delete demo files from Idonia staging."
    )
    parser.add_argument(
        "--route",
        help="Exact Idonia route to inspect/delete. Defaults to DNI/ACCESSION.",
    )
    parser.add_argument(
        "--patient-root",
        action="store_true",
        help="Use the whole patient folder route instead of DNI/ACCESSION.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete the route. Without this flag it only performs a dry run.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)
    token = bind_request_id("cleanup-idonia")
    try:
        if settings.idonia_use_mocks:
            print("Idonia esta en simulacion local. Pon IDONIA_USE_MOCKS=false para limpiar Idonia real.")
            return
        if not settings.idonia_configured:
            print("Faltan variables de Idonia real en .env.")
            return

        patient_route = Patient(
            dni=settings.patient_dni,
            name=settings.patient_name,
        ).safe_folder_name
        route = args.route or patient_route
        if not args.route and not args.patient_root:
            route = f"{patient_route}/{settings.idonia_accession_number}"

        client = IdoniaClient(settings, logging.getLogger("reto3.idonia"))
        print(f"Ruta Idonia: {route}")

        try:
            children = client.list_children(route)
            if children:
                print("Contenido detectado:")
                print(json.dumps(children, indent=2, ensure_ascii=False)[:4000])
            else:
                print("La ruta existe pero no ha devuelto contenido listado.")
        except ExternalServiceError as exc:
            print(f"No se pudo listar la ruta antes de borrar: {exc}")

        if not args.yes:
            print("\nDry run: no se ha borrado nada.")
            print("Para borrar esta ruta ejecuta el mismo comando con --yes.")
            return

        client.delete_route(route)
        print("Borrado solicitado correctamente.")
    finally:
        reset_request_id(token)


if __name__ == "__main__":
    main()
