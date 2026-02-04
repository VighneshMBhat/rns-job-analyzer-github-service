from groq import Groq
from app.core.config import settings
import json

client = Groq(api_key=settings.GROQ_API_KEY)

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
