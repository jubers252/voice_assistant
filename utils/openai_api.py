import os
import requests

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Set your API key in environment or pass as argument


def chat_with_openai(messages, model="gpt-3.5-turbo", api_key=None, temperature=0.7, max_tokens=512):
    """
    Send a chat completion request to OpenAI API.
    messages: list of dicts [{"role": "user"|"system"|"assistant", "content": str}]
    model: OpenAI model name (default: gpt-3.5-turbo)
    api_key: API key (default: from env OPENAI_API_KEY)
    temperature: float (default: 0.7)
    max_tokens: int (default: 512)
    Returns: response text or None
    """
    if api_key is None:
        api_key = OPENAI_API_KEY
    if not api_key:
        raise ValueError("OpenAI API key not set. Set OPENAI_API_KEY env variable or pass as argument.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return None
