from __future__ import annotations

import logging
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.clients.idonia_client import IdoniaClient
from app.config import get_settings
from app.utils.logger import bind_request_id, configure_logging, mask_identifier, reset_request_id


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    token = bind_request_id("check-idonia")
    try:
        if settings.idonia_use_mocks:
            print("Idonia esta en simulacion local. Pon IDONIA_USE_MOCKS=false para probar Idonia real.")
        if not settings.idonia_configured:
            print("Faltan variables de Idonia real en .env.")
            print("Necesitas IDONIA_API_KEY, IDONIA_API_SECRET, IDONIA_DICOM_ENDPOINT,")
            print("IDONIA_REPORT_ENDPOINT, IDONIA_ACCESSION_NUMBER e IDONIA_STUDY_DESCRIPTION.")
            return

        whoami = IdoniaClient(settings, logging.getLogger("reto3.idonia")).whoami()
        actor = whoami.get("actorId") or whoami.get("realActorId") or "desconocido"
        print("Idonia /whoami OK")
        print(f"Actor: {_mask_actor(actor)}")
    finally:
        reset_request_id(token)


def _mask_actor(actor: object) -> str:
    text = str(actor)
    if "/" in text:
        prefix, suffix = text.rsplit("/", 1)
        return f"{prefix}/{mask_identifier(suffix)}"
    return mask_identifier(text)


if __name__ == "__main__":
    main()
