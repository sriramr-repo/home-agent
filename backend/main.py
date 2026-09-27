from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import tasks

app = FastAPI(title="Muse Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}