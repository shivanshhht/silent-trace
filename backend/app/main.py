from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ingestion import router as ingestion_router
from app.api.graph import router as graph_router
from app.api.nlp import router as nlp_router

app = FastAPI(title="Silent Trace API", version="0.1.0")

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


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Return a lightweight liveness response for the frontend and local checks."""
    return {"status": "ok", "service": "silent-trace-backend"}
