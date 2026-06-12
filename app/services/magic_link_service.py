from __future__ import annotations

from app.clients.idonia_client import IdoniaClient
from app.models.report import MagicLink


class MagicLinkService:
    def __init__(self, idonia_client: IdoniaClient) -> None:
        self.idonia_client = idonia_client

    def create_for_patient_folder(self, patient_folder_id: str) -> MagicLink:
        return self.idonia_client.create_magic_link(patient_folder_id)

