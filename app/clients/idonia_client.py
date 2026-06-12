from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin
import urllib.error
import urllib.request
import uuid

from app.config import Settings
from app.models.patient import Patient
from app.models.report import DicomSummary, MagicLink
from app.utils.errors import ExternalServiceError, ServiceNotConfiguredError
from app.utils.logger import log_event, mask_identifier


class IdoniaClient:
    def __init__(self, settings: Settings, logger: logging.Logger) -> None:
        self.settings = settings
        self.logger = logger

    def ensure_patient_folder(self, patient: Patient) -> str:
        if self.settings.idonia_use_mocks:
            folder_id = _mock_id("folder", patient.dni)
            log_event(
                self.logger,
                logging.INFO,
                "idonia.folder.mocked",
                {"patient": mask_identifier(patient.dni), "folder_id": folder_id},
            )
            return folder_id
        self._require_real_config()
        patient_route = patient.safe_folder_name
        log_event(
            self.logger,
            logging.INFO,
            "idonia.folder.route_ready",
            {
                "patient": mask_identifier(patient.dni),
                "route": patient_route,
                "accession": self.settings.idonia_accession_number,
            },
        )
        return patient_route

    def upload_dicom(
        self,
        patient_folder_id: str,
        dicom_path: Path,
        summary: DicomSummary,
    ) -> str:
        if self.settings.idonia_use_mocks:
            upload_id = _mock_id("dicom", patient_folder_id, dicom_path.name)
            log_event(
                self.logger,
                logging.INFO,
                "idonia.dicom_upload.mocked",
                {
                    "folder_id": patient_folder_id,
                    "upload_id": upload_id,
                    "bytes": summary.size_bytes,
                    "dicom_preamble": summary.has_dicom_preamble,
                },
            )
            return upload_id
        response = self._upload_file(
            destination=self.settings.idonia_dicom_endpoint,
            patient_route=patient_folder_id,
            file_path=dicom_path,
            content_type="application/dicom",
        )
        upload_id = _first_file_uuid(response)
        log_event(
            self.logger,
            logging.INFO,
            "idonia.dicom_upload.completed",
            {
                "route": patient_folder_id,
                "upload_id": upload_id,
                "bytes": summary.size_bytes,
            },
        )
        return upload_id

    def upload_medical_report(self, patient_folder_id: str, pdf_path: Path) -> str:
        if self.settings.idonia_use_mocks:
            report_id = _mock_id("report", patient_folder_id, pdf_path.name)
            log_event(
                self.logger,
                logging.INFO,
                "idonia.medical_report.mocked",
                {"folder_id": patient_folder_id, "report_id": report_id},
            )
            return report_id
        response = self._upload_file(
            destination=self.settings.idonia_report_endpoint,
            patient_route=patient_folder_id,
            file_path=pdf_path,
            content_type="application/pdf",
        )
        report_id = _first_file_uuid(response)
        log_event(
            self.logger,
            logging.INFO,
            "idonia.medical_report.completed",
            {"route": patient_folder_id, "report_id": report_id},
        )
        return report_id

    def upload_patient_report(self, patient_folder_id: str, pdf_path: Path) -> str:
        if self.settings.idonia_use_mocks:
            report_id = _mock_id("patient-report", patient_folder_id, pdf_path.name)
            log_event(
                self.logger,
                logging.INFO,
                "idonia.patient_report.mocked",
                {"folder_id": patient_folder_id, "report_id": report_id},
            )
            return report_id
        response = self._upload_file(
            destination=self.settings.idonia_report_endpoint,
            patient_route=patient_folder_id,
            file_path=pdf_path,
            content_type="application/pdf",
        )
        report_id = _first_file_uuid(response)
        log_event(
            self.logger,
            logging.INFO,
            "idonia.patient_report.completed",
            {"route": patient_folder_id, "report_id": report_id},
        )
        return report_id

    def create_magic_link(self, patient_folder_id: str) -> MagicLink:
        if self.settings.idonia_use_mocks:
            suffix = hashlib.sha1(patient_folder_id.encode("utf-8")).hexdigest()[:8]
            link = MagicLink(
                url=f"https://demo.idonia.com/v/mock-link-{suffix}",
                pin="12345",
                qr=f"mock-qr-{suffix}",
            )
            log_event(
                self.logger,
                logging.INFO,
                "idonia.magic_link.mocked",
                {"folder_id": patient_folder_id, "url": link.url, "pin": link.pin},
            )
            return link
        route = f"{patient_folder_id}/{self.settings.idonia_accession_number}"
        params = {
            "route": route,
            "expired_creation_mode": "update",
            "return_expired": "true",
        }
        if self.settings.idonia_magic_link_password:
            params["password"] = _magic_link_password_hash(
                self.settings.idonia_magic_link_password
            )
        response = self._request_json("PUT", "/ml", query=params, ok_statuses={200, 201})
        item = response[0] if isinstance(response, list) and response else response
        if not isinstance(item, dict):
            raise ExternalServiceError(f"Unexpected Idonia Magic Link response: {item!r}")

        raw_url = str(item.get("URL") or item.get("url") or "").strip()
        url = raw_url if raw_url.startswith("http") else _join_url(
            self.settings.idonia_magic_link_base_url,
            raw_url or self.settings.idonia_participant_number,
        )
        link = MagicLink(
            url=url,
            pin=str(item.get("PIN") or item.get("pin") or ""),
            qr=str(item.get("QR") or item.get("qr") or ""),
        )
        log_event(
            self.logger,
            logging.INFO,
            "idonia.magic_link.completed",
            {"route": route, "url": link.url, "pin": link.pin},
        )
        return link

    def whoami(self) -> dict[str, object]:
        self._require_real_config()
        response = self._request_json("GET", "/whoami")
        if not isinstance(response, dict):
            raise ExternalServiceError(f"Unexpected Idonia whoami response: {response!r}")
        log_event(
            self.logger,
            logging.INFO,
            "idonia.whoami.completed",
            {"actor": _safe_actor(response.get("actorId"))},
        )
        return response

    def list_children(self, route: str) -> object:
        self._require_real_config()
        response = self._request_json(
            "GET",
            "/file/children",
            query={"route": route},
            ok_statuses={200, 204},
        )
        log_event(
            self.logger,
            logging.INFO,
            "idonia.children.completed",
            {"route": route},
        )
        return response

    def delete_route(self, route: str) -> None:
        self._require_real_config()
        self._request_json(
            "DELETE",
            "/file",
            query={"route": route},
            ok_statuses={200, 204},
        )
        log_event(
            self.logger,
            logging.INFO,
            "idonia.delete.completed",
            {"route": route},
        )

    def _upload_file(
        self,
        destination: str,
        patient_route: str,
        file_path: Path,
        content_type: str,
    ) -> object:
        self._require_real_config()
        url_path = f"/files/{quote(destination, safe='')}"
        fields = {
            "DICOMPatientID": patient_route,
            "DICOMAccessionNumber": self.settings.idonia_accession_number,
            "DICOMStudyDescription": self.settings.idonia_study_description,
        }
        body, multipart_content_type = _build_multipart(
            fields=fields,
            file_field="file",
            file_path=file_path,
            content_type=content_type,
        )
        log_event(
            self.logger,
            logging.INFO,
            "idonia.upload.request",
            {
                "destination": destination,
                "route": patient_route,
                "filename": file_path.name,
                "bytes": file_path.stat().st_size,
            },
        )
        return self._request_json(
            "POST",
            url_path,
            body=body,
            headers={"Content-Type": multipart_content_type},
            ok_statuses={200, 201},
        )

    def _request_json(
        self,
        method: str,
        path: str,
        query: dict[str, str] | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        ok_statuses: set[int] | None = None,
    ) -> object:
        ok_statuses = ok_statuses or {200}
        url = urljoin(self.settings.idonia_base_url.rstrip("/") + "/", path.lstrip("/"))
        if query:
            url = f"{url}?{urlencode(query)}"
        request_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._build_jwt()}",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers=request_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = response.status
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            detail = _read_error_body(exc)
            raise ExternalServiceError(
                f"Idonia API returned HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ExternalServiceError(f"Idonia API connection error: {exc.reason}") from exc

        if status not in ok_statuses:
            raise ExternalServiceError(f"Unexpected Idonia status {status} for {method} {path}")
        if not response_body:
            return {}
        try:
            return json.loads(response_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            preview = response_body[:240].decode("utf-8", errors="replace")
            raise ExternalServiceError(
                f"Idonia API did not return JSON for {method} {path}: {preview!r}"
            ) from exc

    def _build_jwt(self) -> str:
        issued_at = int(time.time()) - 300
        expires_at = int(time.time()) + 300
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"sub": self.settings.idonia_api_key, "iat": issued_at, "exp": expires_at}
        signing_input = b".".join(
            [
                _b64url_json(header),
                _b64url_json(payload),
            ]
        )
        signature = hmac.new(
            _decode_api_secret(self.settings.idonia_api_secret),
            signing_input,
            hashlib.sha256,
        ).digest()
        return ".".join(
            [
                signing_input.decode("ascii"),
                _b64url(signature).decode("ascii"),
            ]
        )

    def _require_real_config(self) -> None:
        if not self.settings.idonia_configured:
            raise ServiceNotConfiguredError(
                "Idonia real mode requires IDONIA_API_KEY, IDONIA_API_SECRET, "
                "IDONIA_DICOM_ENDPOINT, IDONIA_REPORT_ENDPOINT, "
                "IDONIA_ACCESSION_NUMBER and IDONIA_STUDY_DESCRIPTION."
            )


def _mock_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:9]
    return f"mock-{prefix}-{digest}"


def _b64url_json(value: dict[str, object]) -> bytes:
    return _b64url(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _b64url(value: bytes) -> bytes:
    return base64.urlsafe_b64encode(value).rstrip(b"=")


def _decode_api_secret(secret: str) -> bytes:
    raw = secret.strip()
    if raw.startswith("S2"):
        raw = raw[2:]
    padding = "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw + padding)
    except Exception as exc:
        raise ServiceNotConfiguredError(
            "IDONIA_API_SECRET must be the S2-prefixed base64-url-safe secret from Idonia."
        ) from exc


def _build_multipart(
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = f"----reto3-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _first_file_uuid(response: object) -> str:
    if isinstance(response, list) and response:
        first = response[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(first.get("file_uuid") or first.get("id_file") or first)
    if isinstance(response, dict):
        return str(response.get("file_uuid") or response.get("id_file") or response)
    return str(response)


def _magic_link_password_hash(password: str) -> str:
    hex_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return base64.b64encode(hex_hash.encode("ascii")).decode("ascii")


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.strip('/')}"


def _safe_actor(actor: object) -> str:
    if not actor:
        return ""
    text = str(actor)
    if "/" in text:
        prefix, suffix = text.rsplit("/", 1)
        return f"{prefix}/{mask_identifier(suffix)}"
    return mask_identifier(text)


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read(800).decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    return body or exc.reason or "sin detalle"
