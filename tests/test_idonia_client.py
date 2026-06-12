from __future__ import annotations

import base64
import json
import logging
from dataclasses import replace

from app.clients.idonia_client import IdoniaClient
from app.config import get_settings
from app.models.report import DicomSummary


class FakeHeaders:
    def get_content_type(self):
        return "application/json"


class FakeResponse:
    headers = FakeHeaders()

    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


def _settings(**overrides):
    secret = "S2" + base64.urlsafe_b64encode(b"test-secret").decode("ascii").rstrip("=")
    return replace(
        get_settings(),
        idonia_use_mocks=False,
        idonia_api_key="K2-test-key",
        idonia_api_secret=secret,
        idonia_participant_number="123",
        idonia_dicom_endpoint="dicom_hak_123",
        idonia_report_endpoint="report_hak_123",
        idonia_accession_number="ACC-1",
        idonia_study_description="RM rodilla",
        **overrides,
    )


def test_idonia_whoami_sends_bearer_jwt(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return FakeResponse(b'{"actorId":"account/test"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = IdoniaClient(_settings(), logging.getLogger("test.idonia"))

    result = client.whoami()

    assert captured["url"] == "https://connect-staging.idonia.com/whoami"
    assert captured["headers"]["Authorization"].startswith("Bearer ")
    assert len(captured["headers"]["Authorization"].split()[1].split(".")) == 3
    assert result["actorId"] == "account/test"


def test_idonia_upload_dicom_posts_expected_multipart(monkeypatch, tmp_path):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = request.data
        return FakeResponse(json.dumps([{"file_uuid": "file-123"}]).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    dicom = tmp_path / "study.dcm"
    dicom.write_bytes((b"\0" * 128) + b"DICM")
    client = IdoniaClient(_settings(), logging.getLogger("test.idonia"))

    upload_id = client.upload_dicom(
        "12345678A",
        dicom,
        DicomSummary(filename="study.dcm", size_bytes=dicom.stat().st_size, has_dicom_preamble=True),
    )

    assert captured["url"] == "https://connect-staging.idonia.com/files/dicom_hak_123"
    assert captured["headers"]["Content-type"].startswith("multipart/form-data; boundary=")
    assert b'name="DICOMPatientID"' in captured["body"]
    assert b"12345678A" in captured["body"]
    assert b'name="DICOMAccessionNumber"' in captured["body"]
    assert b"ACC-1" in captured["body"]
    assert upload_id == "file-123"


def test_idonia_delete_route_calls_file_delete(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        return FakeResponse(b"", status=204)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = IdoniaClient(_settings(), logging.getLogger("test.idonia"))

    client.delete_route("12345678A/ACC-1")

    assert captured["method"] == "DELETE"
    assert captured["url"] == "https://connect-staging.idonia.com/file?route=12345678A%2FACC-1"
    assert captured["headers"]["Authorization"].startswith("Bearer ")
