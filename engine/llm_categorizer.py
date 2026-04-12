import requests

OLLAMA_URL = "http://100.103.104.90:11434/api/generate"
MODEL = "qwen2.5:7b"

def categorize_with_llm(description, allowed):

    prompt = f"""
Categorize the following transaction:

Transaction: {description}

Choose one category from:
{allowed}

Only return the category name.
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }
    )

    return response.json()["response"].strip()