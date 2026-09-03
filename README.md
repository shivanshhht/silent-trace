# Silent Trace

Silent Trace is an AI-assisted investigation intelligence platform prototype. It is designed to transform **synthetic, demo-only** investigative records into an explainable, time-aware knowledge graph. Phase 2 adds the typed synthetic data model and ingestion foundation; no real criminal records or personally identifiable information should be used.

## Architecture overview

The project is a deliberately small local application:

- **Frontend:** React with Vite, served on `http://localhost:5173`.
- **Backend:** Python FastAPI, served on `http://localhost:8000`.
- **API:** `GET /api/health` provides liveness; `POST /api/ingestion` validates and ingests a dataset.
- **Data:** `data/synthetic/demo_dataset.json` contains fictional source records; `data/raw` and `data/processed` remain reserved for later workflows.

The backend currently uses only FastAPI, Uvicorn, Pydantic, pytest, and HTTPX. SQLite, NetworkX, NLP, graph analytics, anomaly detection, and authentication are intentionally deferred until a later phase.

## Phase 2 data model and ingestion flow

The canonical models in `backend/app/schemas/investigation.py` cover persons, phone numbers, vehicles, locations, organizations, incidents, communications, financial transactions, evidence/source records, and relationships. Entity IDs use stable typed prefixes such as `per_`, `phn_`, `veh_`, `loc_`, `org_`, and `inc_`. Record IDs use `src_`, `com_`, `txn_`, or `rel_` prefixes. The fictional currency code `SYN` is used in demo transactions so the fixture cannot be mistaken for real financial data.

Each dataset contains source records with a `record_id`, `record_type`, `source_record_id`, `observed_at`, and payload. The `IngestionService` validates each payload against its typed model, normalizes basic fields such as phone numbers and vehicle registrations, rejects duplicate or mismatched IDs, and returns a consistent `IngestedRecord`. Every accepted record includes a non-empty `provenance` list containing its source record ID. Errors are returned per record with field-level detail so one invalid record does not obscure other valid records.

The ingestion service is intentionally independent of persistence. A future authorized source adapter can convert its input into `SourceRecord` objects without changing the validation, normalization, or provenance contract.

## Prerequisites

- Python 3.12+ (the current environment is Python 3.12.3; Python 3.14 should be used if that is the target environment)
- Node.js 22+ and npm 10+
- Git

## Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Start the API from the `backend` directory:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The health endpoint is available at <http://localhost:8000/api/health>.

## Frontend setup

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The interface calls the backend health endpoint and displays either **Backend connected** or **Backend unavailable**.

To create a production build:

```bash
npm run build
```

## How to run the application

1. Start the backend with Uvicorn using the command above.
2. Start the frontend with Vite in a second terminal.
3. Visit <http://localhost:5173> and confirm the connected status.

## Current MVP status

**Phase 2 complete:** typed synthetic investigation data model, fictional demo fixture, modular ingestion service, ingestion API route, validation/normalization, stable IDs, provenance preservation, automated ingestion tests, and documentation.

The following remain explicitly out of scope: NLP/entity extraction, entity resolution, graph visualization and analytics, anomaly detection, authentication, and the full investigation dashboard.

## Testing

Run the backend test suite from `backend` with the virtual environment active:

```bash
pytest
```

## Ethics and safety

This is a college hackathon prototype. Use synthetic data only. Analytical outputs in future phases must distinguish observed evidence from AI-inferred relationships and provide supporting evidence and confidence; the system must not label a person as criminal based on an algorithmic score.
