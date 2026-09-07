from dotenv import load_dotenv
load_dotenv()
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.api.websockets import manager
from src.core.security import authenticate_websocket, require_auth
from src.core.security import auth_router
from src.core.database import init_db, save_access_event
from src.api.routes import router as sim_router
from src.services.orchestrator import shutdown_ingestion, start_ingestion_loop

# Background task reference to prevent garbage collection
_ingestion_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ingestion_task
    print("[System] Initialising SQLite Database...")
    init_db()
    
    print("[System] Booting Simulation Orchestrator...")
    # asyncio.create_task allows the loop to run alongside the main web server
    _ingestion_task = asyncio.create_task(start_ingestion_loop())
    
    yield
    
    print("[System] Shutting down Aviva Triage API...")
    if _ingestion_task:
        _ingestion_task.cancel()
        try:
            await _ingestion_task
        except asyncio.CancelledError:
            pass
    await shutdown_ingestion()

app = FastAPI(title="Aviva Triage Engine API", lifespan=lifespan)


@app.middleware("http")
async def access_logging_middleware(request, call_next):
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/auth/"):
        try:
            require_auth(request, request.headers.get("authorization"))
        except HTTPException as error:
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
    response = await call_next(request)
    user = getattr(request.state, "user", None)
    save_access_event({
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user.user_id if user else None,
        "role": user.role if user else None,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "handler_type": request.headers.get("X-Handler-Type"),
        "client_host": request.client.host if request.client else None,
    })
    return response

# Register REST endpoints
app.include_router(sim_router)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    if not await authenticate_websocket(websocket):
        await websocket.close(code=1008, reason="Authentication required")
        return
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)