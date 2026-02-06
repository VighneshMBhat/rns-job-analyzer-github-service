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

mangum_handler = Mangum(app)

def handler(event, context):
    """
    Lambda Handler wrapper to support:
    1. Standard API Gateway events (via Mangum)
    2. Direct 'Event' invocations for background tasks (e.g. repo sync)
    """
    # Check for custom background task events
    if isinstance(event, dict) and event.get("task") == "sync_user_repos":
        try:
            from app.routers.sync import trigger_sync
            user_id = event.get("user_id")
            print(f"Starting background repo sync for user: {user_id}")
            result = trigger_sync(user_id)
            print(f"Background sync completed: {result}")
            return result
        except Exception as e:
            print(f"Background sync failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    return mangum_handler(event, context)
