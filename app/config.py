from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_files() -> None:
    """Load local env files without overriding shell-provided values."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    for env_file in (BASE_DIR / ".env", BASE_DIR / "APIs.env"):
        if env_file.exists():
            load_dotenv(env_file, override=False)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    debug: bool
    use_mocks: bool
    idonia_use_mocks: bool
    recog_use_mocks: bool
    log_level: str
    base_dir: Path
    frontend_dir: Path
    data_dir: Path
    input_dir: Path
    output_dir: Path
    idonia_base_url: str
    idonia_api_key: str
    idonia_api_secret: str
    idonia_participant_number: str
    idonia_dicom_endpoint: str
    idonia_report_endpoint: str
    idonia_accession_number: str
    idonia_study_description: str
    idonia_magic_link_base_url: str
    idonia_magic_link_password: str
    recog_base_url: str
    recog_api_key: str
    recog_api_secret: str
    recog_report_results_path: str
    recog_timeout_seconds: int
    patient_dni: str
    patient_name: str

    @property
    def idonia_configured(self) -> bool:
        return all(
            [
                self.idonia_base_url,
                self.idonia_api_key,
                self.idonia_api_secret,
                self.idonia_dicom_endpoint,
                self.idonia_report_endpoint,
                self.idonia_accession_number,
                self.idonia_study_description,
            ]
        )

    @property
    def recog_configured(self) -> bool:
        return all([self.recog_base_url, self.recog_api_key])

    @property
    def mode(self) -> str:
        if self.idonia_use_mocks and self.recog_use_mocks:
            return "mock"
        if self.idonia_use_mocks or self.recog_use_mocks:
            return "hybrid"
        return "real"

    @property
    def display_mode(self) -> str:
        if self.mode == "real":
            return "flujo real"
        if self.mode == "hybrid":
            return "conexion parcial"
        return "sin conexion real"

    def redacted(self) -> dict[str, object]:
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "debug": self.debug,
            "use_mocks": self.use_mocks,
            "idonia_use_mocks": self.idonia_use_mocks,
            "recog_use_mocks": self.recog_use_mocks,
            "log_level": self.log_level,
            "idonia_base_url": self.idonia_base_url,
            "idonia_configured": self.idonia_configured,
            "idonia_dicom_endpoint": self.idonia_dicom_endpoint,
            "idonia_report_endpoint": self.idonia_report_endpoint,
            "idonia_accession_number": self.idonia_accession_number,
            "idonia_study_description": self.idonia_study_description,
            "idonia_magic_link_base_url": self.idonia_magic_link_base_url,
            "idonia_magic_link_password_configured": bool(self.idonia_magic_link_password),
            "recog_base_url": self.recog_base_url,
            "recog_configured": self.recog_configured,
            "recog_report_results_path": self.recog_report_results_path,
            "recog_timeout_seconds": self.recog_timeout_seconds,
            "idonia_participant_number": _redact(self.idonia_participant_number),
            "patient_dni": _redact(self.patient_dni),
            "patient_name": self.patient_name,
            "data_dir": str(self.data_dir),
        }


def _redact(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def get_settings() -> Settings:
    _load_env_files()

    data_dir = BASE_DIR / "data"
    use_mocks = _env_bool("APP_USE_MOCKS", True)
    participant_number = os.getenv("IDONIA_PARTICIPANT_NUMBER", "")
    return Settings(
        app_name=os.getenv("APP_NAME", "Reto 3 Neural"),
        app_env=os.getenv("APP_ENV", "local"),
        debug=_env_bool("APP_DEBUG", True),
        use_mocks=use_mocks,
        idonia_use_mocks=_env_bool("IDONIA_USE_MOCKS", use_mocks),
        recog_use_mocks=_env_bool("RECOG_USE_MOCKS", use_mocks),
        log_level=os.getenv("LOG_LEVEL", "DEBUG").upper(),
        base_dir=BASE_DIR,
        frontend_dir=BASE_DIR / "frontend",
        data_dir=data_dir,
        input_dir=data_dir / "input",
        output_dir=data_dir / "output",
        idonia_base_url=os.getenv("IDONIA_BASE_URL", "https://connect-staging.idonia.com"),
        idonia_api_key=os.getenv("IDONIA_API_KEY", ""),
        idonia_api_secret=os.getenv("IDONIA_API_SECRET", ""),
        idonia_participant_number=participant_number,
        idonia_dicom_endpoint=os.getenv(
            "IDONIA_DICOM_ENDPOINT",
            f"dicom_hak_{participant_number}" if participant_number else "",
        ),
        idonia_report_endpoint=os.getenv(
            "IDONIA_REPORT_ENDPOINT",
            f"report_hak_{participant_number}" if participant_number else "",
        ),
        idonia_accession_number=os.getenv("IDONIA_ACCESSION_NUMBER", "RM_RODILLA_HACKATON"),
        idonia_study_description=os.getenv("IDONIA_STUDY_DESCRIPTION", "Informe y estudio RM rodilla"),
        idonia_magic_link_base_url=os.getenv(
            "IDONIA_MAGIC_LINK_BASE_URL",
            "https://demo.idonia.com/v",
        ),
        idonia_magic_link_password=os.getenv("IDONIA_MAGIC_LINK_PASSWORD", ""),
        recog_base_url=os.getenv("RECOG_BASE_URL", "https://api.recog.es"),
        recog_api_key=os.getenv("RECOG_API_KEY", ""),
        recog_api_secret=os.getenv("RECOG_API_SECRET", ""),
        recog_report_results_path=os.getenv(
            "RECOG_REPORT_RESULTS_PATH",
            "/relisten/dictation/process/report-results",
        ),
        recog_timeout_seconds=int(os.getenv("RECOG_TIMEOUT_SECONDS", "60")),
        patient_dni=os.getenv("PATIENT_DNI", "12345678A"),
        patient_name=os.getenv("PATIENT_NAME", "Paciente Demo"),
    )
