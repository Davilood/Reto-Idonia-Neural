# Reto 3 Neural

Solucion para el reto de interoperabilidad de pruebas medicas: una webapp que conecta Idonia Connect Cloud y Recog para entregar una resonancia magnetica, el informe medico original y una version comprensible para el paciente mediante un Magic Link seguro con PIN.

El objetivo no es solo mover archivos. El flujo preserva el informe clinico original para el profesional sanitario, genera un documento adaptado para el paciente y agrupa todo en una entrega segura y trazable.

## Equipo Neural

- David Martin Fortea - d.martinf.2024@alumnos.urjc.es
- Alex Montecino Puerto - a.montecino.2024@alumnos.urjc.es
- Miguel Esteban Salazar - m.esteban.2024@alumnos.urjc.es
- Angel Garcia Sanchez - a.garciasan.2024@alumnos.urjc.es
- Rafael Garcia Marquez - re.marquez.2024@alumnos.urjc.es

## Que resuelve

El caso del reto plantea una barrera habitual en continuidad asistencial: una prueba se realiza en un entorno sanitario, pero el seguimiento y la explicacion al paciente ocurren en otro.

Reto 3 Neural automatiza este circuito:

1. Recibe un estudio DICOM y un informe medico en PDF.
2. Valida tecnicamente la imagen DICOM.
3. Sube DICOM e informe original a Idonia.
4. Extrae el texto del informe medico.
5. Envia ese texto a Recog para generar un PDF adaptado a lenguaje de paciente.
6. Sube el informe humanizado a Idonia.
7. Genera un Magic Link con PIN para consultar la entrega completa.

Resultado esperado en Idonia:

- Estudio DICOM.
- Informe medico original.
- Informe para paciente generado por Recog.

## Estado del proyecto

- Flujo real con Idonia staging.
- Flujo real con Recog mediante API key.
- Frontend clinico minimalista para ejecutar la demo sin consola.
- Progreso incremental por pasos reales del backend.
- Logs con `workflow_id`, duracion y metadatos redactados.
- Scripts de verificacion para Idonia, Recog y demo final.
- Tests automatizados para servicios y flujo local.

## Arquitectura

```text
Frontend
  |
  | POST /procesar
  | GET /api/workflows/{workflow_id}
  v
FastAPI
  |
  v
MedicalWorkflowOrchestrator
  |-- DicomService        valida el DICOM
  |-- PdfService          extrae texto y guarda PDFs generados
  |-- ReportService       prepara el texto para Recog
  |-- IdoniaClient        sube DICOM, informe original e informe paciente
  |-- RecogClient         genera el PDF humanizado
  |-- MagicLinkService    solicita Magic Link + PIN
```

## Estructura del repositorio

```text
app/
  clients/        Clientes de Idonia y Recog
  models/         Modelos de dominio
  services/       Servicios DICOM, PDF, informes, ficheros y Magic Link
  utils/          Logs, errores y redaccion de identificadores
  main.py         API FastAPI
  orchestrator.py Flujo clinico completo
frontend/
  index.html      Interfaz de ejecucion y seguimiento del flujo
scripts/
  check_idonia.py
  check_recog.py
  cleanup_idonia.py
  final_demo.py
tests/
docs/
data/
  test.dcm
  Informe RM RODILLA.pdf
.env.example
.gitignore
requirements.txt
README.md
run_demo.py
```

## Requisitos

- Python 3.10 o superior.
- Acceso a las claves de staging de Idonia.
- API key de Recog para `report-results`.
- Opcional: `pdftotext`/`poppler-utils` para extraer texto del PDF con mayor fidelidad.

En Ubuntu/Debian:

```bash
sudo apt-get install poppler-utils
```

Si `pdftotext` no esta disponible, el sistema mantiene un fallback tecnico, pero para la demo final se recomienda tenerlo instalado.

## Instalacion

```bash
python3 -m venv reto-3
source reto-3/bin/activate
pip install -r requirements.txt
```

## Configuracion

Crear un archivo `.env` local a partir de `.env.example`:

```bash
cp .env.example .env
```

Rellenar las claves reales solo en `.env`:

```env
APP_NAME=Reto 3 Neural
APP_ENV=local
APP_DEBUG=true
APP_USE_MOCKS=false
IDONIA_USE_MOCKS=false
RECOG_USE_MOCKS=false
LOG_LEVEL=DEBUG

IDONIA_BASE_URL=https://connect-staging.idonia.com
IDONIA_API_KEY=
IDONIA_API_SECRET=
IDONIA_PARTICIPANT_NUMBER=
IDONIA_DICOM_ENDPOINT=
IDONIA_REPORT_ENDPOINT=
IDONIA_ACCESSION_NUMBER=RM_RODILLA_HACKATON
IDONIA_STUDY_DESCRIPTION=Informe y estudio RM rodilla
IDONIA_MAGIC_LINK_BASE_URL=https://demo.idonia.com/v
IDONIA_MAGIC_LINK_PASSWORD=

RECOG_BASE_URL=https://api.recog.es
RECOG_API_KEY=
RECOG_API_SECRET=
RECOG_REPORT_RESULTS_PATH=/relisten/dictation/process/report-results
RECOG_TIMEOUT_SECONDS=60

PATIENT_DNI=12345678A
PATIENT_NAME=Paciente Demo
```

## Ejecucion por navegador

Levantar la API y el frontend:

```bash
source reto-3/bin/activate
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abrir:

```text
http://127.0.0.1:8000
```

Flujo de uso:

1. Comprobar que Idonia y Recog aparecen como activos en entorno real.
2. Introducir DNI y nombre visible del paciente de prueba.
3. Cargar `data/test.dcm`.
4. Cargar `data/Informe RM RODILLA.pdf`.
5. Ejecutar el flujo final.
6. Esperar a que todos los pasos aparezcan completados.
7. Abrir el Magic Link e introducir el PIN generado.
8. Verificar en Idonia el DICOM, el informe original y el informe para paciente.

El progreso visible en la interfaz se alimenta de `GET /api/workflows/{workflow_id}`. No es una animacion simulada: cada check refleja un paso completado en backend.

## Ejecucion por script

Para generar una evidencia final sin depender del navegador:

```bash
source reto-3/bin/activate
python3 scripts/final_demo.py
```

Para preparar una ejecucion limpia en staging:

```bash
python3 scripts/final_demo.py --clean
```

`--clean` solicita borrar la ruta configurada `PATIENT_DNI/IDONIA_ACCESSION_NUMBER` en Idonia antes de ejecutar. Usarlo solo en el entorno de staging del reto.

Para guardar logs sin publicar PIN:

```bash
python3 scripts/final_demo.py --clean 2>&1 | sed -E 's/(^PIN:).*/\1 [redactado]/; s/pin=[A-Z0-9]+/pin=[redactado]/g'
```

## Verificacion

```bash
source reto-3/bin/activate
python3 -m pytest -q
python3 scripts/check_idonia.py
python3 scripts/check_recog.py
python3 scripts/final_demo.py --clean
```

Checks esperados:

- `pytest`: tests pasando.
- `check_idonia.py`: Idonia responde correctamente.
- `check_recog.py`: Recog devuelve un PDF valido.
- `final_demo.py --clean`: workflow completado, Magic Link generado y PDF paciente subido.

## Endpoints principales

```text
GET    /api/health
POST   /procesar
GET    /api/workflows/{workflow_id}
GET    /api/workflows/{workflow_id}/patient-report
DELETE /api/idonia/demo-data?patientDni=12345678A&scope=study
```

Endpoints de diagnostico:

```text
GET /api/debug/config
GET /api/debug/workflows
```

Los endpoints de diagnostico devuelven informacion redactada. No exponen claves.


## Uso de IA

La IA se usa en dos niveles:

- Recog: transforma el texto del informe medico en un PDF comprensible para el paciente.
- Herramientas de desarrollo asistido por IA: apoyo para estructuracion del proyecto, mejora del frontend, documentacion, revision de logs y preparacion de la entrega.

Uso critico aplicado:

- La IA no diagnostica.
- La IA no sustituye el informe medico original.
- El informe original se conserva junto al documento para paciente.
- El flujo registra pasos, duraciones y evidencias para auditoria tecnica.
