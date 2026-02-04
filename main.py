from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from app.routers import auth, webhook, sync
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/github", tags=["auth"])
app.include_router(webhook.router, prefix="/api/github/webhook", tags=["webhook"])
app.include_router(sync.router, prefix="/api/github/sync", tags=["sync"])

@app.get("/")
def health_check():
    return {"status": "ok", "service": "GitHub Skill Extractor"}

handler = Mangum(app)
