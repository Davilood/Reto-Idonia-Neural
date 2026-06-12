from __future__ import annotations

import logging
from dataclasses import replace

from app.clients.recog_client import RecogClient
from app.config import get_settings
from app.models.patient import Patient


def test_recog_mock_returns_humanized_report():
    settings = replace(get_settings(), use_mocks=True, recog_use_mocks=True)
    client = RecogClient(settings, logging.getLogger("test.recog"))

    result = client.humanize_report(
        "Rotura parcial del ligamento cruzado anterior.", Patient(dni="12345678A")
    )

    assert result.source == "mock-recog"
    assert result.body is not None
    assert "Hola" in result.body
    assert "ligamento" in result.body


def test_recog_real_posts_report_and_returns_pdf(monkeypatch):
    captured = {}

    class FakeHeaders:
        def get_content_type(self):
            return "application/pdf"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"%PDF-1.4\nfake recog pdf"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = request.data
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    settings = replace(
        get_settings(),
        use_mocks=False,
        recog_use_mocks=False,
        recog_base_url="https://api.recog.es",
        recog_api_key="fake_recog_api_key_for_tests",
        recog_report_results_path="/relisten/dictation/process/report-results",
        recog_timeout_seconds=12,
    )
    client = RecogClient(settings, logging.getLogger("test.recog"))

    result = client.humanize_report("Informe tecnico", Patient(dni="12345678A"))

    assert captured["url"] == (
        "https://api.recog.es/relisten/dictation/process/report-results"
    )
    assert captured["timeout"] == 12
    assert captured["headers"]["X-api-key"] == "fake_recog_api_key_for_tests"
    assert b"dictationReport" in captured["body"]
    assert result.source == "recog-report-results-api"
    assert result.pdf_bytes == b"%PDF-1.4\nfake recog pdf"
