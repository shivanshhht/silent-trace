# Silent Trace

Silent Trace is an AI-assisted investigation intelligence platform prototype. It is designed to transform **synthetic, demo-only** investigative records into an explainable, time-aware knowledge graph. Phase 4 adds deterministic NLP extraction from fictional unstructured reports on top of the Phase 1–3 foundation; no real criminal records or personally identifiable information should be used.

## Architecture overview

The project is a deliberately small local application:

- **Frontend:** React with Vite, served on `http://localhost:5173`.
- **Backend:** Python FastAPI, served on `http://localhost:8000`.
- **API:** `GET /api/health` provides liveness; `POST /api/ingestion` validates and ingests a dataset.
- **Graph API:** `POST /api/graph/resolve`, `POST /api/graph`, `GET /api/graph/{graph_id}`, and the evidence endpoint expose resolution, graph construction, retrieval, and provenance lookup.
- **NLP API:** `POST /api/nlp/extract`, `POST /api/nlp/process`, and `POST /api/nlp/extract/batch` process fictional unstructured reports.
- **Data:** `data/synthetic/demo_dataset.json` and `data/synthetic/reports.json` contain fictional structured and unstructured source records; `data/raw` and `data/processed` remain reserved for later workflows.

The backend currently uses only FastAPI, Uvicorn, Pydantic, pytest, and HTTPX. The Phase 4 extractor uses Python standard-library patterns rather than a heavyweight NLP dependency. SQLite, graph analytics, anomaly detection, and authentication remain deferred.

## Phase 2 data model and ingestion flow

The canonical models in `backend/app/schemas/investigation.py` cover persons, phone numbers, vehicles, locations, organizations, incidents, communications, financial transactions, evidence/source records, and relationships. Entity IDs use stable typed prefixes such as `per_`, `phn_`, `veh_`, `loc_`, `org_`, and `inc_`. Record IDs use `src_`, `com_`, `txn_`, or `rel_` prefixes. The fictional currency code `SYN` is used in demo transactions so the fixture cannot be mistaken for real financial data.

Each dataset contains source records with a `record_id`, `record_type`, `source_record_id`, `observed_at`, and payload. The `IngestionService` validates each payload against its typed model, normalizes basic fields such as phone numbers and vehicle registrations, rejects duplicate or mismatched IDs, and returns a consistent `IngestedRecord`. Every accepted record includes a non-empty `provenance` list containing its source record ID. Errors are returned per record with field-level detail so one invalid record does not obscure other valid records.

The ingestion service is intentionally independent of persistence. A future authorized source adapter can convert its input into `SourceRecord` objects without changing the validation, normalization, or provenance contract.

## Phase 3 entity resolution and knowledge graph

`EntityResolutionService` applies deterministic structured keys after normalization: names and aliases for people, digits for phone numbers, registrations for vehicles, label/locality pairs for locations, and normalized names for organizations. An exact key match consolidates source representations under the first stable entity ID while retaining every source ID and evidence reference. A strong-but-not-exact fuzzy similarity is never silently merged; it produces a `candidate_review` result with confidence and candidate IDs. Different keys remain separate. No criminality, guilt, or risk score is produced.

`KnowledgeGraphService` converts resolved entities into provenance-carrying nodes and communication, transaction, or explicit relationship records into typed observed edges. Edges retain their source record, timestamp, confidence, and evidence reference. The graph schemas are intentionally simple lists of nodes and edges so later analytics can be added without changing the evidence contract. Graphs are currently held in process memory for this prototype; persistence and graph analytics are out of scope for Phase 3.

## Phase 4 NLP extraction

`NLPExtractionService` provides a reproducible, lightweight extractor for the controlled synthetic report format. It uses regular expressions and explicit relationship phrases to identify people, phone numbers, vehicles, locations, organizations, date/time values, and incident/event text. It emits normalized values, stable deterministic IDs, confidence values, character spans, source report IDs, and evidence snippets. Relationships are created only for explicit phrases such as “contacted ... using phone,” “drove vehicle,” “met,” and “associated with”; co-occurrence alone does not create an edge.

The extractor adapter converts supported entities and explicit relationships into the existing `IngestedRecord` representation. The `/api/nlp/process` endpoint then runs extraction, entity resolution, and graph construction in sequence, preserving the original report source reference throughout. This is a deterministic NLP demonstration, not a general-purpose language understanding system; unsupported wording may produce no extraction, and all outputs are evidence-bearing observations rather than conclusions about guilt or criminality.

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

**Phase 4 complete:** deterministic synthetic-report NLP extraction, explicit relationship extraction, source spans and evidence snippets, integration with ingestion/entity resolution/graph construction, NLP APIs, synthetic report fixtures, and automated tests. Phase 1–3 functionality remains in place.

The following remain explicitly out of scope: graph visualization and analytics, anomaly detection, authentication, and the full investigation dashboard.

## Testing

Run the backend test suite from `backend` with the virtual environment active:

```bash
pytest
```

## Ethics and safety

This is a college hackathon prototype. Use synthetic data only. Analytical outputs in future phases must distinguish observed evidence from AI-inferred relationships and provide supporting evidence and confidence; the system must not label a person as criminal based on an algorithmic score.
