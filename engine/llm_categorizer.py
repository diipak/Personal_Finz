import requests
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import OLLAMA_URL, LLM_MODEL

def categorize_with_llm(description, allowed):
    prompt = f"""
Categorize the following transaction:

Transaction: {description}

Choose one category from:
{allowed}

Only return the category name.
"""

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
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

    return result