from __future__ import annotations

import json

from app import main
from app.models.patient import Patient


def _clear_workflows() -> None:
    with main.WORKFLOW_LOCK:
        main.LAST_WORKFLOWS.clear()
        main.WORKFLOW_STATES.clear()
        main.ARCHIVED_WORKFLOW_IDS.clear()
        main.ACTIVE_WORKFLOW_KEYS.clear()
        main.WORKFLOW_INPUT_KEYS.clear()


def test_running_duplicate_workflow_reuses_active_workflow():
    _clear_workflows()
    try:
        main._register_active_workflow("input-key", "workflow123")
        with main.WORKFLOW_LOCK:
            main.WORKFLOW_STATES["workflow123"] = {
                "workflow_id": "workflow123",
                "status": "running",
            }

        duplicate = main._running_duplicate_workflow("input-key")

        assert duplicate is not None
        assert duplicate["workflow_id"] == "workflow123"
    finally:
        _clear_workflows()


def test_finished_workflow_releases_duplicate_guard():
    _clear_workflows()
    try:
        main._register_active_workflow("input-key", "workflow123")
        main._remember_workflow({"workflow_id": "workflow123", "status": "completed"})

        assert main._running_duplicate_workflow("input-key") is None
        assert "input-key" not in main.ACTIVE_WORKFLOW_KEYS
        assert "workflow123" not in main.WORKFLOW_INPUT_KEYS
    finally:
        _clear_workflows()


def test_workflow_status_response_includes_poll_backoff():
    _clear_workflows()
    try:
        with main.WORKFLOW_LOCK:
            main.WORKFLOW_STATES["workflow123"] = {
                "workflow_id": "workflow123",
                "status": "running",
                "steps": [],
            }

        response = main.get_workflow("workflow123")
        body = json.loads(response.body)

        assert response.headers["Retry-After"] == "3"
        assert body["retry_after_ms"] == 3000
    finally:
        _clear_workflows()


def test_workflow_input_key_changes_with_file_contents():
    patient = Patient(dni="12345678A")

    first = main._workflow_input_key(patient, b"dicom-a", b"pdf")
    second = main._workflow_input_key(patient, b"dicom-b", b"pdf")

    assert first != second
