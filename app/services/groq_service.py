from groq import Groq
from app.core.config import settings
from app.services.key_service import get_groq_key
import json


def _get_groq_client():
    """Get Groq client with dynamic API key (database first, then env fallback)."""
    # Try database first, then fall back to environment variable
    api_key = get_groq_key(fallback=settings.GROQ_API_KEY)
    if not api_key:
        raise ValueError("GROQ_API_KEY not configured. Add it via Admin Portal or environment variable.")
    return Groq(api_key=api_key)


def extract_skills_from_text(text: str, source_context: str = "readme") -> list[dict]:
    """
    Uses Groq (Llama 3.3) to extract technical skills from text.
    Returns a list of dicts: {"skill": "Python", "confidence": 0.9}
    
    Args:
        text: The text content to analyze (README or Resume)
        source_context: Either "readme" or "resume" to adjust the prompt
    """
    if not text or len(text) < 50:
        return []

    # Get client with dynamic key
    client = _get_groq_client()

    if source_context == "resume":
        prompt = f"""
        Analyze the following RESUME content and extract ALL technical skills, 
        programming languages, frameworks, tools, databases, cloud platforms, 
        and methodologies mentioned.
        
        Return ONLY a valid JSON object with a "skills" array.
        Each skill should have:
        - "skill": the skill name (e.g., "Python", "AWS", "React")
        - "confidence": a score from 0.0 to 1.0 based on how clearly it's mentioned
        
        Do NOT include:
        - Soft skills (communication, teamwork, etc.)
        - Generic terms (computer, internet, etc.)
        - Job titles or company names
        
        Resume Content:
        {text[:8000]}
        """
    else:
        prompt = f"""
        Analyze the following README/project description and extract key technical 
        skills, frameworks, languages, and tools mentioned.
        
        Return ONLY a valid JSON object with a "skills" array.
        Each skill should have:
        - "skill": the skill name
        - "confidence": a score from 0.0 to 1.0 based on prominence
        
        Do not include generic terms.
        
        Content:
        {text[:4000]}
        """
    
    try:
        completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system", 
                    "content": "You are a technical skill extraction AI. Extract skills and return ONLY valid JSON."
                },
                {"role": "user", "content": prompt}
            ],
            model=settings.GROQ_MODEL,
            response_format={"type": "json_object"}
        )
        
        content = completion.choices[0].message.content
        result = json.loads(content)
        return result.get("skills", [])
        
    except Exception as e:
        print(f"Groq Extraction Error: {e}")
        return []


def extract_skills_from_resume(text: str) -> list[dict]:
    """
    Wrapper function specifically for resume skill extraction.
    Uses a more comprehensive prompt for resumes.
    """
    return extract_skills_from_text(text, source_context="resume")


def extract_skills_from_readme(text: str) -> list[dict]:
    """
    Wrapper function specifically for README skill extraction.
    """
    return extract_skills_from_text(text, source_context="readme")
