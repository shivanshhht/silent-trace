from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.graph import router as graph_router
from app.api.ingestion import router as ingestion_router
from app.api.investigations import router as investigations_router
from app.api.nlp import router as nlp_router
from app.db.database import create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the schema exists before the API serves its first request.

    Creating missing tables at startup is right for this prototype and for the
    SQLite development database. A deployment against PostgreSQL should apply
    versioned migrations instead; see the Stage B notes in the README.
    """
    create_all()
    yield


app = FastAPI(title="Silent Trace API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion_router)
app.include_router(graph_router)
app.include_router(nlp_router)
app.include_router(investigations_router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Return a lightweight liveness response for the frontend and local checks."""
    return {"status": "ok", "service": "silent-trace-backend"}
