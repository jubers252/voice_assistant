import requests
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "tinydolphin:latest"

# Create a session for connection reuse
session = requests.Session()


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


def is_personal_query(query):
    """Detect if a query contains personal information or references"""
    personal_keywords = [
        'my wife', 'my husband', 'my name', 'my family', 'my friend', 'my birthday',
        'my address', 'my phone', 'my email', 'my password', 'my job', 'my work',
        'my home', 'my car', 'my bank', 'my account', 'my credit card', 'my mother',
        'my father', 'my brother', 'my sister', 'my child', 'my daughter', 'my son',
        'personal', 'private', 'confidential', 'secret', 'remember me', 'know me',
        'about me', 'tell me about myself', 'my history', 'my past', 'my preference'
    ]
    
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in personal_keywords)

def smart_chat_router(messages, user_query, use_streaming=True):
    """Route queries to appropriate LLM based on content"""
    if is_personal_query(user_query):
        print("[Routing to Local LLM - Personal Query]")
        if use_streaming:
            return chat_with_gemma_streaming(messages), "local"
        else:
            return chat_with_gemma(messages), "local"
    else:
        print("[Routing to OpenAI - General Query]")
        try:
            response = chat_with_openai(messages)
            return response, "openai"
        except Exception as e:
            print(f"OpenAI failed, falling back to local: {e}")
            if use_streaming:
                return chat_with_gemma_streaming(messages), "local_fallback"
            else:
                return chat_with_gemma(messages), "local_fallback"

def preload_model():
    """Pre-load the model into memory for faster responses"""
    print(f"Loading {MODEL} into memory...")
    try:
        # Use the generate endpoint with empty prompt to load model
        response = session.post("http://localhost:11434/api/generate", 
                              json={"model": MODEL, "prompt": "", "stream": False})
        if response.status_code == 200:
            print(f"Model {MODEL} loaded successfully!")
        else:
            print(f"Warning: Could not preload model. Status: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Warning: Could not preload model: {e}")

def chat_with_gemma_streaming(messages):
    """Streaming version for faster response"""
    start_time = time.time()
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True
    }
    
    try:
        response = session.post(OLLAMA_URL, json=payload, stream=True)
        response.raise_for_status()
        
        full_response = ""
        for line in response.iter_lines():
            if line:
                try:
                    chunk = json.loads(line)
                    if 'message' in chunk and 'content' in chunk['message']:
                        content = chunk['message']['content']
                        print(content, end='', flush=True)  # Print as it arrives
                        full_response += content
                    if chunk.get('done', False):
                        break
                except json.JSONDecodeError:
                    continue
        
        end_time = time.time()
        response_time = end_time - start_time
        print(f"\n[Response time: {response_time:.2f} seconds]")
        return full_response
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def chat_with_gemma(messages):
    """Non-streaming version (original)"""
    start_time = time.time()
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False
    }
    
    try:
        response = session.post(OLLAMA_URL, json=payload, timeout=30)
        response.raise_for_status()
        end_time = time.time()
        response_time = end_time - start_time
        print(f"[Response time: {response_time:.2f} seconds]")
        return response.json()["message"]["content"]
    except requests.HTTPError:
        print("Error:", response.text)
        return None
    except Exception as e:
        print("Unexpected error:", e)
        return None

if __name__ == "__main__":
    # Pre-load model into memory for faster responses
    preload_model()
    
    messages = [
        {
            "role": "system",
            "content": "You are a helpful, friendly, and concise voice assistant. your name is sofi and created by juber sarwad. Always reply with short, direct answers suitable for voice output."
        }
    ]
    print("Chat with Sofi! Type 'exit' to quit.")
    print("📍 Smart Routing: Personal queries → Local LLM, General queries → OpenAI")
    print("Choose mode: 's' for streaming (faster), 'n' for non-streaming")
    mode = input("Mode (s/n): ").lower()
    
    use_streaming = mode == 's'
    data = {}
    with open("amazon_vivo_x_fold_5_product_info.json", 'r') as log_file:
       data = json.load(log_file)

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() == "exit":
            break
            
        messages.append({"role": "user", "content": user_input})
        
        print("Sofi: ", end='', flush=True)
        reply, routing_info = smart_chat_router(messages, user_input, use_streaming)
        
        if not use_streaming and reply:
            print(reply)
            
        if reply:
            messages.append({"role": "assistant", "content": reply})