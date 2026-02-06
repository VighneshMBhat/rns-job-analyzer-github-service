from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
import requests
from app.core.config import settings
from supabase import create_client
import traceback
from datetime import datetime, timezone

router = APIRouter()
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _get_github_credentials():
    """Get GitHub OAuth credentials from environment variables."""
    client_id = settings.GITHUB_CLIENT_ID
    client_secret = settings.GITHUB_CLIENT_SECRET
    if not client_id or not client_secret:
        raise ValueError("GitHub OAuth not configured. Add GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET to Lambda environment variables.")
    return client_id, client_secret


@router.get("/connect")
def connect_github(user_id: str):
    """
    Initiates GitHub OAuth flow to link account.
    Pass user_id in query state to bind it on callback.
    """
    client_id, _ = _get_github_credentials()
    
    # Valid GitHub scopes: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps
    scope = "read:user repo"  # read:user for profile, repo for reading repos
    redirect_uri = settings.GITHUB_REDIRECT_URI
    
    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
        f"&state={user_id}"
    )
    
    return RedirectResponse(github_url)

@router.get("/auth/callback")
def github_callback(code: str, state: str):
    """
    Exchange code for access token and store in github_connections.
    State contains the user_id.
    """
    user_id = state
    current_time = datetime.now(timezone.utc).isoformat()
    
    try:
        # Get dynamic credentials
        client_id, client_secret = _get_github_credentials()
        
        # 1. Exchange code for token
        token_resp = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI
            },
            timeout=30
        )
        
        if token_resp.status_code != 200:
            print(f"GitHub token exchange failed: {token_resp.status_code} - {token_resp.text}")
            raise HTTPException(status_code=400, detail="Failed to get GitHub token")
        
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            error = token_data.get("error_description", token_data.get("error", "No access token"))
            print(f"GitHub OAuth error: {error}")
            raise HTTPException(status_code=400, detail=f"GitHub OAuth failed: {error}")

        # 2. Get GitHub User Info
        user_resp = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30
        )
        
        if user_resp.status_code != 200:
            print(f"GitHub user fetch failed: {user_resp.status_code}")
            raise HTTPException(status_code=400, detail="Failed to fetch GitHub user info")
        
        gh_user = user_resp.json()
        print(f"GitHub user fetched: {gh_user.get('login')}")
        
        # 3. Check if connection already exists
        existing = supabase.table("github_connections").select("id").eq("user_id", user_id).execute()
        
        if existing.data:
            # Update existing connection
            update_data = {
                "github_user_id": str(gh_user["id"]),
                "github_username": gh_user["login"],
                "github_email": gh_user.get("email"),
                "github_avatar_url": gh_user.get("avatar_url"),
                "access_token": access_token,
                "updated_at": current_time
            }
            supabase.table("github_connections").update(update_data).eq("user_id", user_id).execute()
            print(f"Updated GitHub connection for user: {user_id}")
        else:
            # Insert new connection
            insert_data = {
                "user_id": user_id,
                "github_user_id": str(gh_user["id"]),
                "github_username": gh_user["login"],
                "github_email": gh_user.get("email"),
                "github_avatar_url": gh_user.get("avatar_url"),
                "access_token": access_token,
                "created_at": current_time,
                "updated_at": current_time
            }
            result = supabase.table("github_connections").insert(insert_data).execute()
            print(f"Created GitHub connection for user: {user_id}, result: {result.data}")
        
        # 4. Also update the profiles table
        profile_update = {
            "github_username": gh_user["login"],
            "github_connected_at": current_time
        }
        supabase.table("profiles").update(profile_update).eq("id", user_id).execute()
        print(f"Updated profile for user: {user_id}")
        
        # 5. Trigger Async Repo Sync
        try:
            import boto3
            import os
            import json
            
            # Check if running in Lambda
            function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
            if function_name:
                client = boto3.client('lambda')
                payload = {"task": "sync_user_repos", "user_id": user_id}
                
                # Async invocation (Event)
                client.invoke(
                    FunctionName=function_name,
                    InvocationType='Event',  # Fire and forget
                    Payload=json.dumps(payload)
                )
                print(f"Triggered async sync for user: {user_id}")
            else:
                print("Skipping async sync - not running in Lambda environment")
        except Exception as sync_e:
            print(f"Failed to trigger async sync: {str(sync_e)}")
            # Don't fail the auth flow just because sync trigger failed
        
        return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard?feature=github_connected")
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).replace("'", "").replace('"', '')[:100]  # Clean error message
        print(f"GitHub callback error: {str(e)}")
        print(traceback.format_exc())
        # Redirect with error instead of crashing
        return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard?error=github_connection_failed&detail={error_msg}")


@router.get("/status/{user_id}")
def get_github_status(user_id: str):
    """
    Check GitHub connection status for a user.
    Returns connection info if exists, or null if not connected.
    """
    try:
        result = supabase.table("github_connections").select(
            "github_username, github_avatar_url, github_email, last_sync_at, repos_analyzed, created_at"
        ).eq("user_id", user_id).single().execute()
        
        if result.data:
            return {
                "connected": True,
                "github_username": result.data.get("github_username"),
                "github_avatar_url": result.data.get("github_avatar_url"),
                "github_email": result.data.get("github_email"),
                "last_sync_at": result.data.get("last_sync_at"),
                "repos_analyzed": result.data.get("repos_analyzed"),
                "connected_at": result.data.get("created_at")
            }
        return {"connected": False}
    except Exception as e:
        print(f"Error checking GitHub status: {e}")
        return {"connected": False, "error": str(e)}


@router.delete("/disconnect/{user_id}")
def disconnect_github(user_id: str):
    """
    Disconnect GitHub account for a user.
    Removes the connection from the database.
    """
    try:
        # Delete GitHub connection
        supabase.table("github_connections").delete().eq("user_id", user_id).execute()
        
        # Also clear github_username from profile
        supabase.table("profiles").update({
            "github_username": None,
            "github_connected_at": None
        }).eq("id", user_id).execute()
        
        return {"success": True, "message": "GitHub disconnected successfully"}
    except Exception as e:
        print(f"Error disconnecting GitHub: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disconnect: {str(e)}")
