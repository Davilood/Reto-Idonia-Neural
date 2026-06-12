from __future__ import annotations

from pydantic import BaseModel, Field


class Patient(BaseModel):
    dni: str = Field(min_length=3, max_length=32)
    name: str = Field(default="Paciente Demo", min_length=1, max_length=120)

    @property
    def safe_folder_name(self) -> str:
        return "".join(ch for ch in self.dni.upper() if ch.isalnum() or ch in {"-", "_"})

