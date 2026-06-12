import requests
import sys
import os
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import OLLAMA_URL, LLM_MODEL, ALLOWED_CATEGORIES

logger = logging.getLogger(__name__)

# Cache categorizations in-memory to prevent repeated LLM calls during statement parsing
LLM_CACHE = {}

def ask_llm(description: str, amount: float) -> str:
    """
    Asks the local Ollama LLM model to categorize the transaction based on description and amount.
    """
    desc_str = str(description).strip()
    if desc_str in LLM_CACHE:
        return LLM_CACHE[desc_str]
        
    prompt = f"""You are a precise personal finance assistant.
Categorize the following bank transaction:
Description: "{desc_str}"
Amount: {amount}

Choose exactly one category from this allowed list:
{", ".join(ALLOWED_CATEGORIES)}

Respond with ONLY the exact category name from the list, and nothing else. Do not add markdown, quotes, punctuation, or explanations."""

    try:
        url = f"{OLLAMA_URL}/api/generate"
        response = requests.post(
            url,
            json={
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 512
                }
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json().get("response", "").strip()
        
        # Strip Ollama reasoning/thinking block if present
        if "<think>" in result:
            parts = result.split("</think>")
            if len(parts) > 1:
                result = parts[-1].strip()
        
        # Validate that the LLM response is in the allowed list (case-insensitive check)
        matched_category = "Other"
        for cat in ALLOWED_CATEGORIES:
            if cat.lower() == result.lower() or result.lower().startswith(cat.lower()) or result.lower().endswith(cat.lower()):
                matched_category = cat
                break
                
        LLM_CACHE[desc_str] = matched_category
        return matched_category
        
    except Exception as e:
        logger.error(f"Error querying local Ollama model: {e}")
        return "Other"
