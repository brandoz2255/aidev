import requests

OLLAMA_URL = "http://ollama:11434"
DEFAULT_MODEL = "mistral"

def query_mistral(prompt: str, system_prompt: str = "") -> str:
    try:
        res = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": DEFAULT_MODEL,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False
            },
            timeout=60
        )
        res.raise_for_status()
        return res.json().get("response", "").strip()
    except Exception as e:
        return f"[LLM error] {e}"

## Perhaps we need to add another pipline
