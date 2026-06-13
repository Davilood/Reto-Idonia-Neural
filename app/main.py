from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.clients.idonia_client import IdoniaClient
from app.models.patient import Patient
from app.orchestrator import build_orchestrator
from app.services.file_service import FileService
from app.utils.errors import WorkflowError
from app.utils.logger import bind_request_id, configure_logging, get_logger, log_event, mask_identifier, reset_request_id


settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("reto3.api")
file_service = FileService(settings.input_dir)
orchestrator = build_orchestrator(settings)
LAST_WORKFLOWS: deque[dict[str, object]] = deque(maxlen=20)
WORKFLOW_STATES: dict[str, dict[str, object]] = {}
ARCHIVED_WORKFLOW_IDS: set[str] = set()
ACTIVE_WORKFLOW_KEYS: dict[str, str] = {}
WORKFLOW_INPUT_KEYS: dict[str, str] = {}
WORKFLOW_LOCK = RLock()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Demo real de interoperabilidad Idonia + Recog para el Reto 3.",
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
    token = bind_request_id(request_id)
    started = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "http.request",
        {"method": request.method, "path": request.url.path},
    )
    try:
        response = await call_next(request)
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000)
        log_event(
            logger,
            logging.INFO,
            "http.response",
            {
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            },
        )
        reset_request_id(token)

    response.headers["x-request-id"] = request_id
    return response


@app.get("/", include_in_schema=False)
def read_index() -> FileResponse:
    return FileResponse(settings.frontend_dir / "index.html", media_type="text/html")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "app": settings.app_name,
        "env": settings.app_env,
        "mode": settings.mode,
        "display_mode": settings.display_mode,
        "debug": settings.debug,
        "accession_number": settings.idonia_accession_number,
        "study_description": settings.idonia_study_description,
        "services": {
            "idonia": {
                "mode": "mock" if settings.idonia_use_mocks else "real",
                "configured": settings.idonia_configured,
            },
            "recog": {
                "mode": "mock" if settings.recog_use_mocks else "real",
                "configured": settings.recog_configured,
            },
        },
    }


@app.get("/api/debug/config")
def debug_config() -> dict[str, object]:
    return settings.redacted()


@app.get("/api/debug/workflows")
def debug_workflows() -> dict[str, object]:
    with WORKFLOW_LOCK:
        running = [
            workflow
            for workflow in WORKFLOW_STATES.values()
            if workflow.get("status") in {"queued", "running"}
        ]
        return {"items": list(LAST_WORKFLOWS), "running": running}


@app.delete("/api/idonia/demo-data")
def delete_idonia_demo_data(
    patientDni: str = Query(..., min_length=3),
    scope: str = Query("study", pattern="^(study|patient)$"),
) -> JSONResponse:
    if settings.idonia_use_mocks:
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "error": "Idonia esta en simulacion local. Pon IDONIA_USE_MOCKS=false para borrar datos reales.",
            },
        )

    try:
        patient = Patient(dni=patientDni.strip(), name=settings.patient_name)
        patient_route = patient.safe_folder_name
        route = patient_route
        if scope == "study":
            route = f"{patient_route}/{settings.idonia_accession_number}"

        idonia_client: IdoniaClient = orchestrator.idonia_client
        idonia_client.delete_route(route)
        with WORKFLOW_LOCK:
            LAST_WORKFLOWS.clear()
            WORKFLOW_STATES.clear()
            ARCHIVED_WORKFLOW_IDS.clear()
            ACTIVE_WORKFLOW_KEYS.clear()
            WORKFLOW_INPUT_KEYS.clear()
        log_event(
            logger,
            logging.INFO,
            "idonia.demo_data.deleted",
            {"route": route, "scope": scope},
        )
        return JSONResponse(
            {
                "ok": True,
                "route": route,
                "scope": scope,
                "message": "Borrado solicitado correctamente en Idonia.",
            }
        )
    except WorkflowError as exc:
        log_event(
            logger,
            logging.ERROR,
            "idonia.demo_data.delete_error",
            {"error": str(exc), "scope": scope},
        )
        return JSONResponse(
            status_code=422,
            content={"ok": False, "error": str(exc), "scope": scope},
        )


@app.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> JSONResponse:
    with WORKFLOW_LOCK:
        workflow = WORKFLOW_STATES.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow no encontrado")
    content: dict[str, object] = {"ok": True, "workflow": workflow}
    headers: dict[str, str] = {"Cache-Control": "no-store"}
    if workflow.get("status") in {"queued", "running"}:
        content["retry_after_ms"] = 3000
        headers["Retry-After"] = "3"
    return JSONResponse(content, headers=headers)


@app.get("/api/workflows/{workflow_id}/patient-report")
def download_patient_report(workflow_id: str) -> FileResponse:
    with WORKFLOW_LOCK:
        workflows = list(LAST_WORKFLOWS)
        if workflow_id in WORKFLOW_STATES:
            workflows.insert(0, WORKFLOW_STATES[workflow_id])
    for workflow in workflows:
        if workflow.get("workflow_id") == workflow_id and workflow.get("output_pdf"):
            path = Path(str(workflow["output_pdf"]))
            if path.exists():
                return FileResponse(
                    path,
                    media_type="application/pdf",
                    filename=path.name,
                )
    raise HTTPException(status_code=404, detail="Informe no encontrado")


@app.post("/procesar")
async def procesar(
    background_tasks: BackgroundTasks,
    patientDni: str = Form(...),
    patientName: str = Form("Paciente Demo"),
    dicomFile: UploadFile = File(...),
    medicalReport: UploadFile = File(...),
    asyncMode: bool = Form(False),
) -> JSONResponse:
    workflow_id = uuid.uuid4().hex
    patient = Patient(dni=patientDni.strip(), name=patientName.strip() or "Paciente Demo")

    dicom_bytes = await dicomFile.read()
    pdf_bytes = await medicalReport.read()
    input_key = _workflow_input_key(patient, dicom_bytes, pdf_bytes)

    duplicate = _running_duplicate_workflow(input_key)
    if duplicate:
        duplicate_id = str(duplicate["workflow_id"])
        log_event(
            logger,
            logging.WARNING,
            "workflow.duplicate_ignored",
            {
                "workflow_id": duplicate_id,
                "patient": mask_identifier(patient.dni),
                "status": duplicate.get("status"),
            },
        )
        return JSONResponse(
            status_code=202,
            content={
                "ok": True,
                "workflow_id": duplicate_id,
                "workflow": duplicate,
                "poll_url": f"/api/workflows/{duplicate_id}",
                "deduplicated": True,
            },
        )

    try:
        dicom = file_service.store_bytes(
            workflow_id=workflow_id,
            filename=dicomFile.filename or "estudio.dcm",
            content=dicom_bytes,
            content_type=dicomFile.content_type or "application/dicom",
        )
        report = file_service.store_bytes(
            workflow_id=workflow_id,
            filename=medicalReport.filename or "informe_medico.pdf",
            content=pdf_bytes,
            content_type=medicalReport.content_type or "application/pdf",
        )
        input_files = {
            "dicom": dicom.model_dump(mode="json"),
            "medical_report": report.model_dump(mode="json"),
        }

        if asyncMode:
            queued_payload: dict[str, object] = {
                "workflow_id": workflow_id,
                "status": "queued",
                "patient_dni": mask_identifier(patient.dni),
                "patient_name": patient.name,
                "mode": settings.mode,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "duration_ms": 0,
                "steps": [],
                "idonia": {},
                "recog": {},
                "magic_link": None,
                "output_pdf": None,
                "debug": {},
                "input_files": input_files,
            }
            _register_active_workflow(input_key, workflow_id)
            _remember_workflow(queued_payload)
            background_tasks.add_task(
                _run_workflow_background,
                patient,
                dicom.path,
                report.path,
                workflow_id,
                input_files,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "ok": True,
                    "workflow_id": workflow_id,
                    "workflow": queued_payload,
                    "poll_url": f"/api/workflows/{workflow_id}",
                },
            )

        _register_active_workflow(input_key, workflow_id)
        result = orchestrator.run(
            patient=patient,
            dicom_path=dicom.path,
            medical_report_path=report.path,
            workflow_id=workflow_id,
        )
        payload = _workflow_payload(result, input_files)
        _remember_workflow(payload)
        return JSONResponse({"ok": True, "workflow": jsonable_encoder(payload)})
    except WorkflowError as exc:
        _forget_active_workflow(workflow_id)
        log_event(
            logger,
            logging.ERROR,
            "workflow.controlled_error",
            {"workflow_id": workflow_id, "error": str(exc)},
        )
        return JSONResponse(
            status_code=422,
            content={"ok": False, "workflow_id": workflow_id, "error": str(exc)},
        )
    except Exception as exc:
        _forget_active_workflow(workflow_id)
        log_event(
            logger,
            logging.ERROR,
            "workflow.unexpected_error",
            {"workflow_id": workflow_id, "error": str(exc)},
        )
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "workflow_id": workflow_id,
                "error": "Error inesperado durante el procesamiento",
                "debug": str(exc) if settings.debug else None,
            },
        )


def _run_workflow_background(
    patient: Patient,
    dicom_path: Path,
    medical_report_path: Path,
    workflow_id: str,
    input_files: dict[str, object],
) -> None:
    token = bind_request_id(f"workflow-{workflow_id[:8]}")
    try:
        orchestrator.run(
            patient=patient,
            dicom_path=dicom_path,
            medical_report_path=medical_report_path,
            workflow_id=workflow_id,
            on_update=lambda result: _remember_workflow(
                _workflow_payload(result, input_files)
            ),
        )
    except WorkflowError as exc:
        _forget_active_workflow(workflow_id)
        log_event(
            logger,
            logging.ERROR,
            "workflow.background_controlled_error",
            {"workflow_id": workflow_id, "error": str(exc)},
        )
    except Exception as exc:
        _forget_active_workflow(workflow_id)
        log_event(
            logger,
            logging.ERROR,
            "workflow.background_unexpected_error",
            {"workflow_id": workflow_id, "error": str(exc)},
        )
    finally:
        reset_request_id(token)


def _workflow_payload(
    result,
    input_files: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = result.model_dump(mode="json")
    if result.output_pdf:
        payload["download_url"] = f"/api/workflows/{result.workflow_id}/patient-report"
    if input_files is not None:
        payload["input_files"] = input_files
    return jsonable_encoder(payload)


def _remember_workflow(payload: dict[str, object]) -> None:
    workflow_id = str(payload["workflow_id"])
    with WORKFLOW_LOCK:
        WORKFLOW_STATES[workflow_id] = payload
        if payload.get("status") in {"completed", "failed"} and workflow_id not in ARCHIVED_WORKFLOW_IDS:
            LAST_WORKFLOWS.appendleft(payload)
            ARCHIVED_WORKFLOW_IDS.add(workflow_id)
        if payload.get("status") in {"completed", "failed"}:
            input_key = WORKFLOW_INPUT_KEYS.pop(workflow_id, None)
            if input_key and ACTIVE_WORKFLOW_KEYS.get(input_key) == workflow_id:
                ACTIVE_WORKFLOW_KEYS.pop(input_key, None)


def _workflow_input_key(patient: Patient, dicom_bytes: bytes, pdf_bytes: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(patient.dni.strip().casefold().encode("utf-8"))
    digest.update(b"\0")
    digest.update(dicom_bytes)
    digest.update(b"\0")
    digest.update(pdf_bytes)
    return digest.hexdigest()


def _register_active_workflow(input_key: str, workflow_id: str) -> None:
    with WORKFLOW_LOCK:
        ACTIVE_WORKFLOW_KEYS[input_key] = workflow_id
        WORKFLOW_INPUT_KEYS[workflow_id] = input_key


def _forget_active_workflow(workflow_id: str) -> None:
    with WORKFLOW_LOCK:
        input_key = WORKFLOW_INPUT_KEYS.pop(workflow_id, None)
        if input_key and ACTIVE_WORKFLOW_KEYS.get(input_key) == workflow_id:
            ACTIVE_WORKFLOW_KEYS.pop(input_key, None)


def _running_duplicate_workflow(input_key: str) -> dict[str, object] | None:
    with WORKFLOW_LOCK:
        workflow_id = ACTIVE_WORKFLOW_KEYS.get(input_key)
        if not workflow_id:
            return None
        workflow = WORKFLOW_STATES.get(workflow_id)
        if workflow and workflow.get("status") in {"queued", "running"}:
            return workflow
        ACTIVE_WORKFLOW_KEYS.pop(input_key, None)
        WORKFLOW_INPUT_KEYS.pop(workflow_id, None)
        return None
