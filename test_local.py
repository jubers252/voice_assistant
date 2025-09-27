import requests
import json
import time

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma3:1b-it-q8_0"

# Create a session for connection reuse
session = requests.Session()

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
        
        print("Gemma: ", end='', flush=True)
        if use_streaming:
            reply = chat_with_gemma_streaming(messages)
        else:
            reply = chat_with_gemma(messages)
            print(reply)
            
        if reply:
            messages.append({"role": "assistant", "content": reply})