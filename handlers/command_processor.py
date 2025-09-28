import time
from connectors.weather_connector import handle_tool_requests
from connectors.amzon_connector import get_amazon_result
from connectors.amazon_order_tracker import get_order
from connectors.spotify_connector import SpotifyConnector
from connectors.search_engine import GeminiSearch


class CommandProcessor:
    """Processes user commands and routes them to appropriate handlers"""
    
    def __init__(self, tool_action_handler, ai_response_handler, 
                 feedback_handler, conversation_manager, conversation_history, 
                 audio_processors, reminder_manager):
        """Initialize command processor with all required handlers"""
        self.tool_action_handler = tool_action_handler
        self.ai_response_handler = ai_response_handler
        self.feedback_handler = feedback_handler
        self.conversation_manager = conversation_manager
        self.conversation_history = conversation_history
        self.audio_processors = audio_processors
        self.reminder_manager = reminder_manager
        
        # Tool action methods
        self.handle_weather_action = handle_tool_requests
        self.get_order_tracking = get_order
        
        # Initialize connectors
        self.spotify_connector = SpotifyConnector(None)  # Will be initialized properly when needed
        self.search_connector = GeminiSearch()
    
    def process_user_command(self, user_command):
        """Process user command and execute appropriate actions with interrupt support"""
        # Check for exit commands
        if any(word in user_command for word in ["exit", "quit", "goodbye", "bye"]):
            self.audio_processors.speak("Goodbye!")
            return True  # Signal to break from main loop
        
        # Get tool action from OpenAI
        tool_response = self.tool_action_handler.get_tool_action(user_command)
        print(tool_response)
        
        # Handle different tool responses
        if tool_response["tool"] == "spotify":
            return self._handle_spotify_command(user_command, tool_response)
            
        elif tool_response["tool"] == "weather":
            return self._handle_weather_command(user_command, tool_response)
            
        elif tool_response["tool"] == "amazon":
            return self._handle_amazon_command(user_command, tool_response)
            
        elif tool_response["tool"] == "amazon_order_tracking":
            return self._handle_order_tracking_command(user_command, tool_response)
            
        elif tool_response["tool"] in ["search", "google_search", "web_search", "brave_search"]:
            return self._handle_search_command(user_command, tool_response)
            
        elif tool_response["tool"] == "reminder":
            return self._handle_reminder_command(user_command, tool_response)
            
        elif tool_response["tool"] == "none":
            return self.ai_response_handler.handle_direct_response(tool_response, user_command)
            
        else:
            # Fallback for any other case
            return self.ai_response_handler.handle_fallback_conversation(user_command)
    
    def _handle_spotify_command(self, user_command, tool_response):
        """Handle Spotify commands"""
        self.conversation_history.append({"role": "user", "content": user_command})
        
        def spotify_action():
            return self.spotify_connector.handle_spotify_action_with_feedback(
                tool_response, self.audio_processors, self.conversation_history
            )

        self.feedback_handler.handle_with_timed_feedback("spotify", user_command, spotify_action)
        print("Spotify action completed. Ready for next command.")
        return False
    
    def _handle_weather_command(self, user_command, tool_response):
        """Handle weather commands"""
        self.conversation_history.append({"role": "user", "content": user_command})
        
        def weather_action():
            response = self.handle_weather_action(tool_response)
            print(f"Weather API response: {response}")
            ai_response = self.ai_response_handler.get_ai_response(response, is_tool_response=True)
            self.audio_processors.speak(ai_response)
            return response

        self.feedback_handler.handle_with_timed_feedback("weather", user_command, weather_action)
        print("Weather action completed. Ready for next command.")
        return False
    
    def _handle_amazon_command(self, user_command, tool_response):
        """Handle Amazon search commands"""
        self.conversation_history.append({"role": "user", "content": user_command})
        
        def amazon_action():
            response = get_amazon_result(tool_response)
            print(f"Amazon API response: {response}")
            ai_response = self.ai_response_handler.get_ai_response(response, is_tool_response=True)
            self.audio_processors.speak(ai_response)
            return response
        
        self.feedback_handler.handle_with_timed_feedback("amazon", user_command, amazon_action)
        print("Amazon action completed. Ready for next command.")
        return False
    
    def _handle_order_tracking_command(self, user_command, tool_response):
        """Handle Amazon order tracking commands"""
        self.conversation_history.append({"role": "user", "content": user_command})
        
        def order_tracking_action():
            response = self.get_order_tracking(tool_response)
            print(f"Order tracking response: {response}")
            ai_response = self.ai_response_handler.get_ai_response(response, is_tool_response=True)
            self.audio_processors.speak(ai_response)
            return response
        
        self.feedback_handler.handle_with_timed_feedback("amazon_order_tracking", user_command, order_tracking_action)
        print("Order tracking completed. Ready for next command.")
        return False
    
    def _handle_search_command(self, user_command, tool_response):
        """Handle search commands"""
        self.conversation_history.append({"role": "user", "content": user_command})
        
        def search_action():
            result = self.search_connector.handle_search_action_with_feedback(tool_response)
            self.conversation_history.append({"role": "assistant", "content": result})
            self.conversation_manager.save_conversation_history()
            
            # Get language for TTS
            lang = tool_response.get("lang", "en")
            self.audio_processors.speak(result, lang=lang)
            return result
        
        result = self.feedback_handler.handle_with_timed_feedback(tool_response["tool"], user_command, search_action)
        
        # Check if search result needs clarification or follow-up
        if self.ai_response_handler.is_question_or_needs_clarification(result):
            time.sleep(0.3)
            return self.ai_response_handler.handle_follow_up_conversation()
        else:
            print("Search completed. Ready for next command.")
            return False
    
    def _handle_reminder_command(self, user_command, tool_response):
        """Handle reminder commands"""
        self.conversation_history.append({"role": "user", "content": user_command})
        
        def reminder_action():
            response = self.reminder_manager.handle_reminder_action(tool_response)
            print(f"Reminder response: {response}")
            ai_response = self.ai_response_handler.get_ai_response(response, is_tool_response=True)
            self.audio_processors.speak(ai_response)
            return response
            
        reminder_action()
        print("Reminder action completed. Ready for next command.")
        return False