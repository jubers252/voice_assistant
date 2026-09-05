
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
        # Ensure the directory exists
        dirpath = os.path.dirname(self.file_path) or '.'
        os.makedirs(dirpath, exist_ok=True)

        # If the file exists, attempt to read and parse it. If it's missing or corrupted,
        # fall back to the default system message.
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # corrupted or empty file; fall through to return default
                pass

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
        # Ensure the directory exists before writing
        dirpath = os.path.dirname(self.file_path) or '.'
        os.makedirs(dirpath, exist_ok=True)

        # Write using the instance's file path (not a global constant) and use UTF-8
        # Ensure URLs and all fields are properly preserved
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)

  

    

if __name__ == "__main__":
    cm = ConversationManager()
    cm.save_conversation_history()