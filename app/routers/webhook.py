from fastapi import APIRouter

router = APIRouter()

@router.post("/")
def handle_webhook():
    return {"status": "received"}
