
import json

CONVERSATION_FILE = "data/conversation_history.json"

class ConversationManager:
    def __init__(self, file_path=CONVERSATION_FILE):
        self.file_path = file_path
        self.conversation_history = self.load_conversation_history()

    def load_conversation_history(self):
        """Load conversation history from file or create a new one"""
        try:
            with open(self.file_path, 'r') as f:
                return json.load(f)
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
        
        with open(CONVERSATION_FILE, 'w') as f:
            json.dump(self.conversation_history, f)

  

    

if __name__ == "__main__":
    cm = ConversationManager()
    cm.save_conversation_history()