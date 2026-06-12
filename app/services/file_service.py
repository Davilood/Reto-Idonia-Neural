from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.models.report import StoredFile


class FileService:
    def __init__(self, input_dir: Path) -> None:
        self.input_dir = input_dir
        self.input_dir.mkdir(parents=True, exist_ok=True)

    def store_bytes(
        self,
        workflow_id: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile:
        workflow_dir = self.input_dir / workflow_id
        workflow_dir.mkdir(parents=True, exist_ok=True)

        safe_name = self.safe_filename(filename)
        path = workflow_dir / safe_name
        path.write_bytes(content)
        return StoredFile(
            filename=safe_name,
            path=path,
            content_type=content_type or "application/octet-stream",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    @staticmethod
    def safe_filename(filename: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename.strip())
        return cleaned.strip("._") or "upload.bin"

