import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class ToolActionHandler:
    """Handles OpenAI tool routing and action decisions"""
    
    def __init__(self, conversation_history):
        """Initialize with conversation history for context"""
        self.conversation_history = conversation_history
    
    def get_tool_action(self, user_message):
        """Interact with OpenAI to decide which tool/action to call based on user_message."""
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # Simple context check - only look at last 2 exchanges for efficiency
            recent_context = ""
            if len(self.conversation_history) >= 3:  # system + at least 1 exchange
                recent_messages = self.conversation_history[-4:]  # Last 2 exchanges
                for msg in recent_messages:
                    if msg["role"] in ["user", "assistant"]:
                        recent_context += f"{msg['role']}: {msg['content'][:100]}...\n"
            
            # Compact tool routing prompt
            tool_prompt = f"""Route user query to appropriate tool. Return JSON only.

Recent context: {recent_context}

Rules:
- If asking about products mentioned in recent context, use "none"
- For NEW products search: use "amazon" 
- For music/spotify: "spotify"
- For weather/time: "weather" 
- For news/search: "google_search"
- For amazon order tracking/status: "amazon_order_tracking"
- For amazon order history for upto nth days: use get_recent_orders action
- For reminders (set, add, check, list or cancel reminders): "reminder"
- For default location, use Pisoli, Pune, India
- Default: "none"

Examples:
{{"tool":"amazon","action":"single_product_search","query":"iPhone 16","lang":"en"}}
{{"tool":"spotify","action":"play","target":"song","name":"Shape of You"}}
{{"tool":"spotify","action":"resume"}}
{{"tool":"spotify","action":"stop"}}
{{"tool":"spotify","action":"next"}}
{{"tool":"weather","action":"get_current_weather","location":"Pune"}}
{{"tool":"weather","action":"get_forecast","location":"Pune"}}
{{"tool":"weather","action":"get_timezone","location":"Pune"}}
{{"tool":"amazon_order_tracking","action":"get_recent_orders","days":5}}
{{"tool":"reminder","action":"add","text":"Take medicine","time":"in 30 minutes"}}
{{"tool":"reminder","action":"list/set/check/cancel"}}
{{"tool":"none","lang":"en"}}

User: {user_message}"""

            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[{"role": "system", "content": tool_prompt}],
                max_tokens=50,  # Much smaller - just need JSON
                temperature=0.0
            )
            reply = response.choices[0].message.content.strip()
            try:
                tool_info = json.loads(reply)
            except Exception:
                tool_info = {"tool": "none"}
            return tool_info
        except Exception as e:
            print(f"Error getting tool action: {e}")
            return {"tool": "none"}