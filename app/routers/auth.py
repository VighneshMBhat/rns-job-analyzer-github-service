from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
import requests
from app.core.config import settings
from supabase import create_client

router = APIRouter()
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

@router.get("/connect")
def connect_github(user_id: str):
    """
    Initiates GitHub OAuth flow to link account.
    Pass user_id in query state to bind it on callback.
    """
    scope = "repo:read" # Need read access to repos for webhooks and content
    return RedirectResponse(
        f"https://github.com/login/oauth/authorize?client_id={settings.GITHUB_CLIENT_ID}&redirect_uri={settings.GITHUB_REDIRECT_URI}&scope={scope}&state={user_id}"
    )

@router.get("/auth/callback")
def github_callback(code: str, state: str):
    """
    Exchange code for access token and store in github_connections.
    State contains the user_id.
    """
    user_id = state
    
    # 1. Exchange code for token
    token_resp = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.GITHUB_REDIRECT_URI
        }
    )
    
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to get GitHub connection")
    
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token returned")

    # 2. Get GitHub User Info
    user_resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    gh_user = user_resp.json()
    
    # 3. Store/Update in Supabase 'github_connections'
    data = {
        "user_id": user_id,
        "github_user_id": str(gh_user["id"]),
        "github_username": gh_user["login"],
        "github_email": gh_user.get("email"),
        "github_avatar_url": gh_user["avatar_url"],
        "access_token": access_token,
        # "webhook_active": False (Will be enabled when we register webhook)
    }
    
    # Upsert based on user_id (Constraint: one github connection per user)
    # Note: Ensure RLS allow this or use Service Role Key
    supabase.table("github_connections").upsert(data, on_conflict="user_id").execute()
    
    return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard?feature=github_connected")

