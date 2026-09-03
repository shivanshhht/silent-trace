# Silent Trace

Silent Trace is an AI-assisted investigation intelligence platform prototype. It is designed to transform **synthetic, demo-only** investigative records into an explainable, time-aware knowledge graph. Phase 1 establishes the local full-stack foundation only; no real criminal records or personally identifiable information should be used.

## Architecture overview

The project is a deliberately small local application:

- **Frontend:** React with Vite, served on `http://localhost:5173`.
- **Backend:** Python FastAPI, served on `http://localhost:8000`.
- **API:** `GET /api/health` provides the initial liveness check.
- **Data:** `data/raw`, `data/processed`, and `data/synthetic` reserve space for later synthetic data workflows.

The backend currently uses only FastAPI, Uvicorn, pytest, and HTTPX. SQLite, NetworkX, NLP, graph analytics, anomaly detection, and authentication are intentionally deferred until a later phase.

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

**Phase 1 complete:** repository foundation, React/Vite frontend, FastAPI backend, CORS configuration, health endpoint, basic backend test, local environment templates, and run documentation.

The following are explicitly out of scope for Phase 1: data ingestion, NLP/entity extraction, relationship extraction, identity resolution, graph visualization and analytics, anomaly detection, authentication, and the full investigation dashboard.

## Testing

Run the backend test suite from `backend` with the virtual environment active:

```bash
pytest
```

## Ethics and safety

This is a college hackathon prototype. Use synthetic data only. Analytical outputs in future phases must distinguish observed evidence from AI-inferred relationships and provide supporting evidence and confidence; the system must not label a person as criminal based on an algorithmic score.
