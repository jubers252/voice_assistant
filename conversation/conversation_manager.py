
import json
import os
import tempfile

# Use a project-root relative data directory when possible. This avoids
# attempting to create a top-level relative 'data' dir if the current
# working directory is not writable. The file_path is resolved in
# ConversationManager.__init__ so tests can override it.
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "data")
CONVERSATION_FILE = os.path.join(DEFAULT_DATA_DIR, "conversation_history.json")

class ConversationManager:
    def __init__(self, file_path=CONVERSATION_FILE):
        self.file_path = file_path
        self.conversation_history = self.load_conversation_history()

    def load_conversation_history(self):
        """Load conversation history from file or create a new one"""
        try:
            dir_path = os.path.dirname(self.file_path) or "."
            try:
                if not os.path.exists(self.file_path):
                    os.makedirs(dir_path, exist_ok=True)

                with open(self.file_path, 'r') as f:
                    return json.load(f)
            except PermissionError:
                # If we cannot create or read the file due to permissions,
                # return the default in-memory conversation history. This
                # allows the assistant to continue running without persisting
                # history.
                print(f"Warning: cannot create or read conversation file at {self.file_path} due to PermissionError. Using in-memory history.")
                return []
        except (FileNotFoundError, json.JSONDecodeError):
            # Start with system message to establish assistant personality
            return [
                {"role": "system", "content": "You are a helpful, friendly, and concise voice assistant named Sofi. Respond primarily in English unless the user specifically asks in Hindi. Provide short and direct answers suitable for voice responses. Always use conversation history to understand context and provide relevant follow-up answers. When users refer to previous topics, reference them appropriately. Do not use special characters, markdown, asterisks, or formatting in your responses. Use only plain text with simple punctuation as your responses will be converted to speech."}
            ]

    def save_conversation_history(self):
        """Save conversation history to file"""
        # Keep only the last 10 exchanges to prevent context from growing too large
        if len(self.conversation_history) > 21:  # 1 system message + 20 turns (10 exchanges)
            # Always keep the system message (first message)
            self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-20:]
        
        try:
            dir_path = os.path.dirname(CONVERSATION_FILE) or "."
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
            with open(CONVERSATION_FILE, 'w') as f:
                json.dump(self.conversation_history, f)
        except PermissionError:
            print(f"Warning: cannot save conversation history to {CONVERSATION_FILE} due to PermissionError. History will not be persisted.")
        except Exception as e:
            print(f"Warning: failed to save conversation history: {e}")

  

    

if __name__ == "__main__":
    cm = ConversationManager()
    cm.save_conversation_history()