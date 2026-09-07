import sys
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app

# Serve the built Vite assets.
app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_DIST / "assets"),
    name="frontend-assets",
)

# Serve the SPA at the root.
@app.get("/", include_in_schema=False)
async def frontend_root():
    return FileResponse(FRONTEND_DIST / "index.html")

# Let React Router handle frontend routes.
@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_fallback(full_path: str):
    requested = FRONTEND_DIST / full_path

    if requested.is_file():
        return FileResponse(requested)

    return FileResponse(FRONTEND_DIST / "index.html")
