"""
Key Service - Fetches API keys from Supabase admin_api_keys table
"""
import requests
from datetime import datetime, timedelta
from app.core.config import settings

SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY

# Cache for API keys
_key_cache: dict = {}
_cache_timestamp: datetime = None
CACHE_DURATION = timedelta(minutes=5)


def _fetch_all_keys() -> dict:
    """Fetch all API keys from Supabase."""
    global _key_cache, _cache_timestamp
    
    # Return cached if still valid
    if _cache_timestamp and (datetime.now() - _cache_timestamp) < CACHE_DURATION:
        return _key_cache
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/admin_api_keys"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        params = {
            "select": "service_name,key_name,key_value,is_active",
            "is_active": "eq.true"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            keys = response.json()
            _key_cache = {}
            for key in keys:
                key_identifier = f"{key['service_name']}_{key['key_name']}"
                _key_cache[key_identifier] = key['key_value']
            _cache_timestamp = datetime.now()
            return _key_cache
    except Exception as e:
        print(f"Error fetching API keys from database: {e}")
    
    return _key_cache


def get_api_key(service_name: str, key_name: str, fallback: str = None) -> str:
    """Get a specific API key from the database."""
    keys = _fetch_all_keys()
    key_identifier = f"{service_name}_{key_name}"
    return keys.get(key_identifier) or fallback or ""


def get_groq_key(fallback: str = None) -> str:
    """Get Groq API key."""
    return get_api_key("groq", "GROQ_API_KEY", fallback)


def get_github_client_id(fallback: str = None) -> str:
    """Get GitHub Client ID."""
    return get_api_key("github", "GITHUB_CLIENT_ID", fallback)


def get_github_client_secret(fallback: str = None) -> str:
    """Get GitHub Client Secret."""
    return get_api_key("github", "GITHUB_CLIENT_SECRET", fallback)


def clear_cache():
    """Clear the key cache."""
    global _key_cache, _cache_timestamp
    _key_cache = {}
    _cache_timestamp = None
