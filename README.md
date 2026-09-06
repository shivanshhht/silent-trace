# Silent Trace

Silent Trace is an AI-assisted investigation intelligence platform prototype. It is designed to transform **synthetic, demo-only** investigative records into an explainable, time-aware knowledge graph. Phase 4 adds deterministic NLP extraction from fictional unstructured reports on top of the Phase 1–3 foundation; Stage B replaces in-process state with a relational database, so an investigation survives an application restart. No real criminal records or personally identifiable information should be used.

## Architecture overview

The project is a deliberately small local application:

- **Frontend:** React with Vite, served on `http://localhost:5173`.
- **Backend:** Python FastAPI, served on `http://localhost:8000`.
- **API:** `GET /api/health` provides liveness; `POST /api/ingestion` validates, ingests and persists a case-scoped dataset.
- **Graph API:** `POST /api/graph/resolve`, `POST /api/graph`, `GET /api/graph/{graph_id}`, and the evidence endpoint expose resolution, graph construction, retrieval, and provenance lookup.
- **NLP API:** `POST /api/nlp/extract`, `POST /api/nlp/process`, and `POST /api/nlp/extract/batch` process fictional unstructured reports.
- **Investigations API:** `GET`/`POST /api/investigations`, `GET /api/investigations/{case_id}`, and the `entities`, `relationships`, `evidence` and `graph` sub-resources read persisted state.
- **Database:** SQLAlchemy over SQLite for local development, designed to run unchanged on PostgreSQL.
- **Data:** `data/synthetic/demo_dataset.json` and `data/synthetic/reports.json` contain fictional structured and unstructured source records; `data/raw` and `data/processed` remain reserved for later workflows.

Every record, entity, edge, graph and provenance reference is scoped to a `case_id` matching `case_[a-z0-9-]+`. The backend uses FastAPI, Uvicorn, Pydantic, SQLAlchemy, pytest, and HTTPX. The Phase 4 extractor uses Python standard-library patterns rather than a heavyweight NLP dependency. Graph analytics, anomaly detection, and authentication remain deferred, as do Neo4j and any other infrastructure.

## Data model, case scoping and identity

The canonical models in `backend/app/schemas/investigation.py` cover persons, phone numbers, vehicles, locations, organizations, incidents, communications, financial transactions, evidence/source records, and relationships. Entity IDs use stable typed prefixes such as `per_`, `phn_`, `veh_`, `loc_`, `org_`, and `inc_`. Record IDs use `src_`, `com_`, `txn_`, or `rel_` prefixes. The fictional currency code `SYN` is used in demo transactions so the fixture cannot be mistaken for real financial data.

Every record carries a `case_id`. `backend/app/services/identity.py` mints canonical identifiers deterministically from `(case_id, entity_type, normalized_value)`, so an entity is stable within an investigation regardless of record order, and the same description in two investigations produces two distinct identifiers. Nothing can merge across a case boundary: entity resolution, graph construction and provenance all reject records belonging to another case.

Optional attributes the source does not state are stored as `None`. The pipeline never invents a placeholder value to satisfy a required field.

## One validation boundary

`validate_and_normalize` in `backend/app/services/ingestion.py` is the only validation boundary. Structured ingestion and NLP-derived records both pass through it before reaching entity resolution or graph construction, so there is no second, more permissive path into the graph. Relationships use a single canonical vocabulary (`located_at`, `owns`, `uses`, `member_of`, `associated_with`, `contacted`, `met`, `involved_in`, `transacted_with`); communications and transactions map onto it rather than introducing edge types of their own.

## Provenance and assertion semantics

`ProvenanceRecord` is the single provenance atom, carrying `case_id`, `source_record_id`, `document_id`, `content_hash`, `source_type`, `extraction_run_id`, `character_start`/`character_end`, `snippet`, and `observed_at`. Spans extracted from a report survive through resolution and graph construction to the evidence endpoint. A span that is incomplete or unquotable is rejected rather than stored as misleading evidence.

Two orthogonal semantics are modelled. `assertion_type` records the status of a claim (`observed`, `inferred`, `unknown`); `provenance_type` records how the supporting evidence was located. Structured records are `observed`. NLP output is `inferred` even though its backing span is `observed`, because the interpretation is the machine's. Combining records keeps the weakest assertion, so nothing gains certainty by being merged.

## Entity resolution

`EntityResolutionService` applies deterministic structured keys after normalization: names and aliases for people, digits for phone numbers, registrations for vehicles, label/locality pairs for locations, normalized names for organizations, and type/summary for incidents. An exact key match consolidates source representations under one minted canonical ID while retaining every source ID and every piece of provenance. A strong-but-not-exact fuzzy similarity is never silently merged; it produces a `candidate_review` result with confidence and candidate IDs, and the record is listed in `unresolved_record_ids`. No criminality, guilt, or risk score is produced.

## Knowledge graph

`KnowledgeGraphService` converts resolved entities into provenance-carrying nodes that retain their `match_status`, `match_confidence` and `review_candidates`, so an uncertain identity stays distinguishable from a confident one. Edge identity is `(case_id, from, to, relationship_type)`: several records asserting the same relationship pool their evidence onto one edge instead of producing duplicate IDs, and evidence lookup returns every supporting record.

Construction is total and explainable. An edge is only created when both endpoints resolve to nodes present in the graph; a relationship whose endpoint cannot be resolved appears in `rejected_edges` with a reason rather than becoming a dangling edge. Graphs are persisted as versioned snapshots (see **Persistence** below); graph analytics remain out of scope.

## Persistence

Stage B removes the in-process `GraphStore` and replaces it with a relational persistence layer under `backend/app/db/`: `database.py` (engine and session lifecycle), `models.py` (schema) and `repositories.py` (case-scoped data access).

**Records are authoritative; everything else is a projection.** The graph is already a deterministic function of the validated record set, so storing the projection as if it were independent truth would let the two drift. `backend/app/services/pipeline.py` persists records and provenance, then rebuilds entities, relationships and the graph snapshot from the full case record set. This is why a person named in a second report merges with the same person from the first, and why an edge whose endpoint only becomes resolvable later does become an edge.

**There is one write path.** Structured ingestion, NLP processing and direct graph construction differ only in how they produce canonical records; once records exist they all take the identical route through `InvestigationPipeline._persist_and_project`. There is no second way into a case.

**Case isolation is structural.** Every table carrying case data has `case_id` in its primary key and a foreign key back to `investigation_cases`, so a row cannot exist without a case and the identifier `src_demo-001` in two investigations is two genuinely distinct rows. Every repository method is keyed by case. The single deliberate exception is `GraphRepository.case_of_graph`, which exists so the pipeline can *detect* an attempt to reuse one graph id across two cases and refuse it.

Provenance is stored once and referenced from both entities and relationships, so evidence cannot disagree with itself depending on which way it is queried. Assertion semantics are unchanged by storage: structured entities reload as `observed`, NLP entities as `inferred`, and an inferred claim still carries `observed` provenance for the span that backs it.

Graph snapshots are versioned. Each pipeline run appends a version and marks it current, so how the graph of an investigation evolved stays inspectable rather than being overwritten.

## Database

Local development uses SQLite through SQLAlchemy; the schema is written to run unchanged on PostgreSQL, which is the intended production database. `JSON` columns are declared with a `JSONB` variant so PostgreSQL gets the indexable type, timestamps are normalized to UTC at the repository boundary because SQLite discards offsets and PostgreSQL does not, and SQLite foreign keys are explicitly enabled so a constraint is not weaker in development than in production.

The database is selected by `SILENT_TRACE_DATABASE_URL` and defaults to `backend/silent_trace.db`. Pointing at PostgreSQL is a configuration change rather than a code change:

```bash
export SILENT_TRACE_DATABASE_URL="postgresql+psycopg://user:password@localhost/silent_trace"
```

Neo4j, Redis, Elasticsearch and Kafka are deliberately not introduced.

### Initializing and seeding the local database

From `backend`, with the virtual environment active:

```bash
python -m app.cli init-db      # create any missing tables
python -m app.cli seed-demo    # load the synthetic demo investigation
python -m app.cli status       # show what is persisted
python -m app.cli reset --yes  # drop and recreate the schema
```

`seed-demo` loads `data/synthetic/demo_dataset.json` and `data/synthetic/reports.json` through the same pipeline a live request uses. Nothing is generated randomly, and every identifier is derived from content, so seeding twice produces the same case rather than duplicating it. The API also creates missing tables on startup, so `uvicorn` works without an explicit `init-db`.

## NLP extraction

`NLPExtractionService` is a deterministic rule-based extractor for the controlled synthetic report format, not a language model. It is built to find less rather than to assert something the text does not support.

Relationship attribution is sentence-scoped: the subject is the nearest person mention preceding the trigger phrase within the same sentence. If no person precedes the trigger in that sentence, the relationship is omitted rather than attributed to a person from elsewhere in the document. A standalone first or last name is treated as another mention of an already-extracted person, but only when it matches exactly one of them; an ambiguous short name is ignored. A negated statement does not become the relationship it denies, and the omission is reported in `warnings`.

Extraction emits the canonical relationship vocabulary directly. Character spans, snippets, content hash and extraction run ID are preserved into provenance. Output that has no domain representation, such as a `DATE_TIME` used to time another assertion, is reported in `rejected_records` rather than silently dropped.

Known limitations: hedged or hypothetical wording ("it is possible that ...") is still extracted, though only ever as an `inferred` assertion with sub-1.0 confidence; sentence splitting is punctuation-based; and unsupported wording simply produces no extraction.

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

**Stage A complete:** case scoping enforced end to end, canonical identity minting, a single validation boundary shared by structured and NLP records, structured provenance with preserved spans, explicit observed/inferred/unknown semantics, sentence-scoped relationship attribution, graph referential integrity, and a shared graph store so `POST /api/nlp/process` produces a graph retrievable through the graph API. Phases 1–4 functionality remains in place.

**Stage B complete:** a relational persistence layer replaces the in-process graph store. An investigation now runs case → source documents → ingestion run → evidence → entity resolution → relationships → knowledge graph → persisted investigation, and reloads intact after the application stops. Case isolation, provenance, spans and observed/inferred semantics all survive storage, and the synthetic demo case can be seeded deterministically. Every Stage A test still passes unchanged.

The following remain explicitly out of scope: graph visualization and analytics, anomaly detection, authentication, the full investigation dashboard, and Neo4j.

Known Stage B limitations are recorded in **Limitations** below.

## Limitations

- **No migrations.** The schema is created with `create_all`, which is appropriate for a prototype and for SQLite but is not a substitute for versioned migrations. A PostgreSQL deployment should adopt Alembic before the schema changes again.
- **PostgreSQL is designed for, not yet exercised.** The schema, types and queries are written to be portable and use no SQLite-specific behaviour, but the test suite runs against SQLite only; no PostgreSQL server was available in this environment.
- **Reprojection is whole-case.** Every pipeline run rebuilds the projection for the entire case. That is what keeps the projection honest, and it is inexpensive at demo scale, but it is O(records in case) per run and would need incremental reprojection at a larger size.
- **Graph snapshots retain every version.** Nothing prunes old snapshots yet.
- **No concurrency control.** Two simultaneous writes to one case would both reproject; the prototype assumes a single writer.
- **Evidence carries no assertion column.** `assertion_type` belongs to the claim, not to the span, so the evidence API joins it from the owning record rather than duplicating a field Stage A deliberately does not have.

## Testing

Run the backend test suite from `backend` with the virtual environment active:

```bash
pytest
```

## Ethics and safety

This is a college hackathon prototype. Use synthetic data only. Analytical outputs in future phases must distinguish observed evidence from AI-inferred relationships and provide supporting evidence and confidence; the system must not label a person as criminal based on an algorithmic score.
