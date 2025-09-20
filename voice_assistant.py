"""
Complete Voice Assistant using OpenAI's API
Features:
- Speech-to-Text
- Natural Language Processing with OpenAI
- Text-to-Speech response
- Conversation memory
"""

import os
import json
import time
from dotenv import load_dotenv
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
from keras.models import load_model
import speech_recognition as sr
import pyttsx3
from openai import OpenAI
from connectors.spotify_connector import SpotifyConnector
from connectors.search_engine import GeminiSearch
from connectors.weather_connector import handle_tool_requests
from connectors.amzon_connector import get_amazon_result
from connectors.amazon_order_tracker import get_order
from connectors.reminder_manager import ReminderManager
import threading
from collections import deque
from audio.audio_processor import AudioProcessors
from audio.wake_word_detector import WakeWordDetector
# Load environment variables
load_dotenv()


CONVERSATION_FILE = "conversation_history.json"

# Wake word detection parameters (matching training)



class VoiceAssistant:
  
    def __init__(self):
        """Initialize the voice assistant components"""
        print("Initializing Voice Assistant...")

        # Initialize speech recognizer
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone(device_index=1)  # Adjust device index if needed

        # Initialize conversation history
        # Initialize AudioProcessors (no buffer - we'll manage our own)
        self.audio_processors = AudioProcessors()
        # Initialize wake word detector with an existing model if available
        ww_model_path = r"C:\Users\JUBER\OneDrive\Documents\chat_gpt_api\model\WWD_improved.h5"
        if not os.path.exists(ww_model_path):
            ww_model_path = 'models/wake_word_model.h5'

        try:
            self.wake_word_detector = WakeWordDetector(model_path=ww_model_path)
        except Exception as e:
            print(f"Warning: wake word model not loaded during init: {e}")
            self.wake_word_detector = None
        self.conversation_history = self.load_conversation_history()
        self.handle_weather_action = handle_tool_requests
        self.get_order_tracking = get_order
        # Audio configuration  
        self.audio_channels = 1  # Channel configuration for microphone recording
        self.tts_speed = 1.3     # Speech speed multiplier (1.0 = normal, 1.3 = 30% faster)
        self.mic_device_id = 1   # USB microphone device ID
        self.mic_gain_factor = 0.8  # Reduce gain for sensitive USB mic

        # Audio processing
        self.sample_rate = 22050
        self.duration = 1.5
        self.debug_mode = True            # Show detailed output

        # Speech interruption control
        self.is_speaking = False
        self.speech_interrupted = False
        self.speech_thread = None

        # Initialize reminder manager
        self.reminder_manager = ReminderManager()

        # Check available voices
        self.check_available_tts_options()
    
    def load_conversation_history(self):
        """Load conversation history from file or create a new one"""
        try:
            with open(CONVERSATION_FILE, 'r') as f:
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
    
    def check_available_tts_options(self):
        """Check and list available TTS options without initializing engines"""
        print("Checking available TTS options...")
        
        # Check pyttsx3
        try:
            temp_engine = pyttsx3.init('sapi5')
            voices = temp_engine.getProperty('voices')
            
            print("Available TTS voices:")
            for i, voice in enumerate(voices):
                print(f"  {i}: {voice.name}")
            
            # Clean up
            temp_engine.stop()
            print("Primary TTS (pyttsx3) is available.")
            
        except Exception as e:
            print(f"pyttsx3 not available: {str(e)}")
            
        # Always available
        print("PowerShell TTS is available as last resort.")
    
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
- For reminders (set, add, remind, list reminders): "reminder"
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
{{"tool":"reminder","action":"list"}}
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
    
    def listen_for_command(self, timeout=20, is_follow_up=False, max_retries=2):
        """
        Listen for user command with follow-up functionality and retry logic.
        
        Args:
            timeout: Max time to wait for speech to start
            is_follow_up: Whether this is a follow-up question
            max_retries: Number of retry attempts if no speech detected
        """
        if is_follow_up:
            print("[ASSISTANT] Listening for follow-up response...")
            # Shorter timeout for follow-ups since user should respond quickly
            timeout = min(timeout, 20)
        else:
            print("[ASSISTANT] Listening for command...")
            
        recognizer = sr.Recognizer()
        # Adjust settings based on whether it's a follow-up
       
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                recognizer = sr.Recognizer()
                # Adjusted recognizer settings for better reliability
                recognizer.energy_threshold = 400   # Lower threshold for better sensitivity
                recognizer.dynamic_energy_threshold = True
                recognizer.pause_threshold = 1.5    # Reasonable pause detection
                recognizer.phrase_threshold = 0.3   # Quick phrase detection start
                recognizer.non_speaking_duration = 1.0  # Moderate pause tolerance
                
                with sr.Microphone(device_index=1) as source:
                    if retry_count == 0:
                        if is_follow_up:
                            print("Please respond...")
                        else:
                            print("Say your command...")
                    else:
                        print(f"I didn't catch that. Please try again... (attempt {retry_count + 1})")
                    
                    # # Brief ambient noise adjustment to calibrate
                    # print("Calibrating microphone...")
                    # recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    # print(f"Adjusted energy threshold: {recognizer.energy_threshold}")
                        
                    print("i m listening...")
                    
                    # Use reasonable timeout settings
                    listen_timeout = timeout if retry_count == 0 else timeout + 3
                    audio = recognizer.listen(source, timeout=listen_timeout, phrase_time_limit=12)
                    
                print(f"[ASSISTANT] Audio length: {len(audio.frame_data) / audio.sample_rate:.2f} seconds")
                print("Recognizing...")
                
                # Check if we actually captured audio
                if len(audio.frame_data) < 1000:  # Very short audio
                    print("[ASSISTANT] Audio too short, trying again...")
                    retry_count += 1
                    continue
                
                # Try recognition with better error handling
                try:
                    command = recognizer.recognize_google(audio, language='en-US')
                    print(f"[ASSISTANT] You said: {command}")
                    
                    # Validate the command (not just empty or very short)
                    cleaned_command = command.lower().strip()
                    if len(cleaned_command) < 2:
                        print("[ASSISTANT] Command too short, trying again...")
                        retry_count += 1
                        continue
                        
                    return cleaned_command
                    
                except sr.RequestError as e:
                    print(f"[ASSISTANT] Google Speech Recognition service error: {e}")
                    retry_count += 1
                    continue
                except sr.UnknownValueError:
                    print("[ASSISTANT] Could not understand the audio")
                    retry_count += 1
                    continue
                
            except sr.WaitTimeoutError:
                retry_count += 1
                if retry_count <= max_retries:
                    if is_follow_up:
                        print(f"[ASSISTANT] No response heard. Trying again... ({retry_count}/{max_retries + 1})")
                    else:
                        print(f"[ASSISTANT] No command heard. Trying again... ({retry_count}/{max_retries + 1})")
                else:
                    print("[ASSISTANT] No speech detected after multiple attempts.")
                    
            except sr.UnknownValueError:
                retry_count += 1
                if retry_count <= max_retries:
                    print(f"[ASSISTANT] Could not understand audio. Trying again... ({retry_count}/{max_retries + 1})")
                else:
                    print("[ASSISTANT] Could not understand speech after multiple attempts.")
                    
            except Exception as e:
                retry_count += 1
                if retry_count <= max_retries:
                    print(f"[ASSISTANT] Recognition error: {e}. Trying again... ({retry_count}/{max_retries + 1})")
                else:
                    print(f"[ASSISTANT] Recognition failed after multiple attempts: {e}")
                    
        return None
    
    def get_ai_response(self, user_message, is_tool_response=False):
        """Get a formatted response from OpenAI for general conversation."""
        # Ensure user_message is always a string
        if not isinstance(user_message, str):
            user_message = str(user_message)
        
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # For tool responses, create a temporary conversation with the tool data
            if is_tool_response:
                temp_messages = self.conversation_history.copy()
                temp_messages.append({"role": "user", "content": f"Please summarize this information for the user in a natural, conversational way. Always respond in same language as user query. For Hindi queries, transliterate your response to Roman script (English letters). Do not add any special characters in response, make it plain text with new line if required since response will be used for TTS: {user_message}"})
                messages_to_send = temp_messages
            else:
                # For regular conversation, add user message to history
                self.conversation_history.append({"role": "user", "content": user_message})
                # Add comprehensive TTS and language formatting instruction with context awareness
                temp_messages = self.conversation_history.copy()
                temp_messages.append({"role": "system", "content": "IMPORTANT RESPONSE GUIDELINES: 1) Use the conversation history to understand context and provide relevant answers to follow-up questions. 2) If the user refers to 'this', 'that', 'it', or asks follow-up questions, reference the previous conversation. 3) Respond in the same language as the user's query. 4) For Hindi queries, transliterate your response to Roman script (English letters). 5) Use plain text only - no special characters, markdown, asterisks, or formatting. 6) Use simple punctuation only. 7) Keep responses concise and conversational for voice output. 8) This response will be converted to speech, so ensure it sounds natural when spoken aloud."})
                messages_to_send = temp_messages
            
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=messages_to_send,
                max_tokens=150,
                temperature=0.7
            )
            reply = response.choices[0].message.content.strip()
            
            # Add assistant response to conversation history
            self.conversation_history.append({"role": "assistant", "content": reply})
            self.save_conversation_history()
            
            return reply
        except Exception as e:
            print(f"Error getting AI response: {e}")
            return "Sorry, I'm having trouble thinking right now."
    
   
    def handle_spotify_action(self, tool_response):
        """Handle Spotify actions with enhanced feedback and error handling"""
        try:
            print(f"tool_response: {tool_response}")
            
            # Execute the Spotify action
            temp_connector = SpotifyConnector(None)
            result = temp_connector.main(tool_response)
            
            if result:
                self.audio_processors.speak(result)
                
                # Additional context for certain actions
                action = tool_response.get("action", "")
                if action == "play":
                    print("Music started. Ready for next command.")
                elif action == "stop":
                    print("Music stopped. Ready for next command.")
                elif action == "resume":
                    print("Music resumed. Ready for next command.")
                elif action == "next":
                    print("Skipped to next track. Ready for next command.")
            else:
              self.audio_processors.speak("Spotify action completed, but I didn't receive details about what happened.")
            return True
        except Exception as e:
            error_message = str(e)
            print(f"Spotify error: {error_message}")
            
            # Provide more specific error messages
            if "No active Spotify device" in error_message:
                self.audio_processors.speak("I couldn't find an active Spotify device. Please open Spotify on your device and try again.")
            elif "No track" in error_message or "No album" in error_message or "No artist" in error_message:
                self.audio_processors.speak("I couldn't find that song on Spotify. Try using different keywords or check the spelling.")
            elif "internet" in error_message.lower() or "connection" in error_message.lower():
                self.audio_processors.speak("I'm having trouble connecting to Spotify. Please check your internet connection.")
            else:
                self.audio_processors.speak("Sorry, I couldn't control Spotify right now. There was an unexpected error.")

    def handle_search_action(self, tool_response):
        """Handle search actions using Gemini Search - returns raw result for processing"""
        try:
            print(f"Search tool_response: {tool_response}")
            
            # Extract the query string from the tool response
            query = tool_response.get("query", "")
            if not query:
                return "I need a search query to help you."
            
            # Initialize the search connector
            gs = GeminiSearch()  # Now uses Flash-Lite by default
            lang = tool_response.get("lang", "en")
            answer = gs.quick_search(query, lang)  # Pass just the query string, not the whole dict
      
            if answer:
                return answer  # Return raw result for AI processing
            else:
                return "I couldn't complete your search request."
            
        except Exception as e:
            error_message = str(e)
            print(f"Search error: {error_message}")
            return "Sorry, I couldn't search for that information right now."

    def is_question_or_needs_clarification(self, text):
        """Check if the AI response is asking a question or seeking clarification using NLP patterns"""
        # Check if text contains any question marks
        if "?" in text:
            return True
            
        # Look for question words at the beginning of sentences
        text_lower = text.lower()
        sentences = [s.strip() for s in text.split(".")]
        question_starters = ["what", "who", "when", "where", "why", "how", "could", "can", "would", "will", "should", "do", "does", "did", "is", "are", "was", "were", "please"]
        
        for sentence in sentences:
            sentence = sentence.strip()
            # Skip empty sentences
            if not sentence:
                continue
                
            # Check if sentence starts with question words
            words = sentence.lower().split()
            if words and words[0] in question_starters:
                return True
        
        # Check for phrases indicating the AI needs more information
        clarification_indicators = [
            "tell me more",
            "i need more",
            "please provide",
            "could you",
            "can you",
            "would you",
            "i'm not sure",
            "i don't understand",
            "elaborate",
            "specify",
            "clarify"
        ]
        
        for indicator in clarification_indicators:
            if indicator in text_lower:
                return True
                
        # Analyze sentence structure for inverted subject-verb order (common in questions)
        # Example: "Are you" instead of "You are"
        inverters = ["are you", "is it", "do you", "can you", "will you", "have you", "would you"]
        for inverter in inverters:
            if inverter in text_lower:
                return True
                
        return False


    def give_processing_feedback(self, tool_type, query_hint=""):
        """Provide immediate feedback while processing different types of requests"""
        import random
        
        feedback_messages = {
            "spotify": [
                "Let me control your music for you",
                "Connecting to Spotify",
                "Working on your music request",
                "I'm handling your music command"
            ],
            "weather": [
                "Let me check the weather for you",
                "Getting the latest weather information", 
                "Fetching weather details",
                "I'm checking the current conditions"
            ],
            "amazon": [
                "Let me search for that product",
                "I'm fetching product details for you",
                "Searching Amazon for your request",
                "Let me find that on Amazon",
                "I'm looking up that product"
            ],
            "search": [
                "Let me search for that information",
                "I'm looking that up for you",
                "Searching for the latest details",
                "Let me find that information",
                "I'm searching the web for you"
            ],
            "google_search": [
                "Let me search for that information",
                "I'm looking that up for you", 
                "Searching for the latest details",
                "Let me find that information",
                "I'm searching the web for you"
            ],
            "web_search": [
                "Let me search for that information",
                "I'm looking that up for you",
                "Searching for the latest details",
                "Let me find that information",
                "I'm searching the web for you"
            ],
            "amazon_order_tracking": [
                "Let me check your order status",
                "I'm fetching your order details",
                "Checking your recent orders",
                "Let me track that order for you",
                "Looking up your order history"
            ]
           
        }
        
        # Get appropriate message for the tool type
        messages = feedback_messages.get(tool_type, ["I'm working on your request"])
        
        # Select message based on query content for more context
        if tool_type == "amazon" and query_hint:
            if "price" in query_hint.lower():
                message = "Let me check the price for you"
            elif "review" in query_hint.lower():
                message = "I'm fetching reviews for you"
            elif "compare" in query_hint.lower():
                message = "Let me compare those products"
            else:
                message = random.choice(messages)
        elif tool_type == "amazon_order_tracking" and query_hint:
            if "status" in query_hint.lower() or "track" in query_hint.lower():
                message = "Let me track that order for you"
            elif "recent" in query_hint.lower() or "latest" in query_hint.lower():
                message = "Checking your recent orders"
            elif "delivery" in query_hint.lower():
                message = "Let me check the delivery status"
            else:
                message = random.choice(messages)
        elif tool_type == "weather" and query_hint:
            if "time" in query_hint.lower():
                message = "Let me check the current time"
            elif "tomorrow" in query_hint.lower():
                message = "I'm checking tomorrow's weather"
            else:
                message = random.choice(messages)
        elif tool_type == "spotify" and query_hint:
            if "play" in query_hint.lower():
                message = "Let me play that for you"
            elif "stop" in query_hint.lower():
                message = "I'm stopping the music"
            elif "next" in query_hint.lower():
                message = "Skipping to the next song"
            else:
                message = random.choice(messages)
        else:
            # Use random message for variety
            message = random.choice(messages)
        
        # Speak the feedback immediately
        self.audio_processors.speak(message)
        
        # Small pause to let the feedback finish
        import time
        time.sleep(0.5)

    def handle_with_timed_feedback(self, tool_type, query_hint, action_func, *args, **kwargs):
        """
        Execute an action with time-based processing feedback.
        Only gives feedback if the action takes longer than 5 seconds.
        
        Args:
            tool_type: Type of tool for feedback message selection
            query_hint: User query for context-aware feedback
            action_func: Function to execute
            *args, **kwargs: Arguments to pass to action_func
            
        Returns:
            Result from action_func
        """
        import time
        import threading
        
        start_time = time.time()
        feedback_given = False
        result_ready = False
        
        def delayed_feedback():
            """Give feedback after 5 seconds if action is still running"""
            nonlocal feedback_given
            time.sleep(5.0)  # Wait 5 seconds
            if not result_ready and not feedback_given:  # Check if action is still running
                feedback_given = True
                self.give_processing_feedback(tool_type, query_hint)
        
        # Start the delayed feedback thread
        feedback_thread = threading.Thread(target=delayed_feedback, daemon=True)
        feedback_thread.start()
        
        try:
            # Execute the actual action
            result = action_func(*args, **kwargs)
            
            # Mark that action completed
            result_ready = True
            execution_time = time.time() - start_time
            
            print(f"Action completed in {execution_time:.2f} seconds. Feedback given: {feedback_given}")
            return result
            
        except Exception as e:
            # Mark completion even on error to prevent delayed feedback
            result_ready = True
            raise e

    def process_user_command(self, user_command):
        """Process user command and execute appropriate actions with interrupt support"""
        # Check for exit commands
        if any(word in user_command for word in ["exit", "quit", "goodbye", "bye"]):
            self.audio_processors.speak("Goodbye!")
            self.detection_running = False
            return True  # Signal to break from main loop
        
        # Get tool action from OpenAI
        tool_response = self.get_tool_action(user_command)
        print(tool_response)
        
        # Handle different tool responses
        if tool_response["tool"] == "spotify":
            # Spotify actions are usually fast, use timed feedback
            def spotify_action():
                return self.handle_spotify_action(tool_response)
            
            self.handle_with_timed_feedback("spotify", user_command, spotify_action)
            print("Spotify action completed. Ready for next command.")

        elif tool_response["tool"] == "weather":
            self.conversation_history.append({"role": "user", "content": user_command})
            
            def weather_action():
                response = self.handle_weather_action(tool_response)
                print(f"Weather API response: {response}")
                ai_response = self.get_ai_response(response, is_tool_response=True)
                self.audio_processors.speak(ai_response)
                return response
            
            self.handle_with_timed_feedback("weather", user_command, weather_action)
            print("Weather action completed. Ready for next command.")

        elif tool_response["tool"] == "amazon":
            self.conversation_history.append({"role": "user", "content": user_command})
            
            def amazon_action():
                response = get_amazon_result(tool_response)
                print(f"Amazon API response: {response}")
                ai_response = self.get_ai_response(response, is_tool_response=True)
                self.audio_processors.speak(ai_response)
                return response
            
            self.handle_with_timed_feedback("amazon", user_command, amazon_action)
            print("Amazon action completed. Ready for next command.")

        elif tool_response["tool"] == "amazon_order_tracking":
            self.conversation_history.append({"role": "user", "content": user_command})
            
            def order_tracking_action():
                response = self.get_order_tracking(tool_response)
                print(f"Order tracking response: {response}")
                ai_response = self.get_ai_response(response, is_tool_response=True)
                self.audio_processors.speak(ai_response)
                return response
            
            self.handle_with_timed_feedback("amazon_order_tracking", user_command, order_tracking_action)
            print("Order tracking completed. Ready for next command.")

        elif tool_response["tool"] in ["search", "google_search", "web_search", "brave_search"]:
            self.conversation_history.append({"role": "user", "content": user_command})
            
            def search_action():
                result = self.handle_search_action(tool_response)
                self.conversation_history.append({"role": "assistant", "content": result})
                self.save_conversation_history()
                
                # Get language for TTS
                lang = tool_response.get("lang", "en")
                self.audio_processors.speak(result, lang=lang)
                return result
            
            result = self.handle_with_timed_feedback(tool_response["tool"], user_command, search_action)
            
            # Check if search result needs clarification or follow-up
            if self.is_question_or_needs_clarification(result):
                time.sleep(0.3)
                return self.handle_follow_up_conversation()
            else:
                print("Search completed. Ready for next command.")

        elif tool_response["tool"] == "reminder":
            self.conversation_history.append({"role": "user", "content": user_command})
            
            def reminder_action():
                try:
                    action = tool_response.get("action", "add")
                    
                    if action == "add":
                        # Extract reminder text and time
                        reminder_text = tool_response.get("text", "")
                        reminder_time = tool_response.get("time", "")
                        
                        response = self.reminder_manager.add_reminder(reminder_text, reminder_time)
                        
                    elif action == "list":
                        response = self.reminder_manager.list_reminders()
                        
                    else:
                        response = "I can help you add reminders or list your current reminders."
                    
                    print(f"Reminder response: {response}")
                    ai_response = self.get_ai_response(response, is_tool_response=True)
                    self.audio_processors.speak(ai_response)
                    return response
                    
                except Exception as e:
                    error_msg = f"Sorry, I had trouble with that reminder. {str(e)}"
                    print(f"Reminder error: {error_msg}")
                    self.audio_processors.speak(error_msg)
                    return error_msg
            
            # Execute reminder action directly - no need for timed feedback
            reminder_action()
            print("Reminder action completed. Ready for next command.")

        elif tool_response["tool"] == "none":
            return self.handle_direct_response(tool_response, user_command)
            
        else:
            # Fallback for any other case
            return self.handle_fallback_conversation(user_command)
        
        return False  # Continue main loop
    
    def handle_direct_response(self, tool_response, user_command):
        """Handle direct response from OpenAI without tools"""
        # Give feedback for complex conversational queries
        if any(keyword in user_command.lower() for keyword in ["explain", "tell me about", "what is", "how does", "why", "describe"]):
            self.audio_processors.speak("Let me think about that")
            time.sleep(0.3)
        
        # Add the user command to history since it's a conversational message
        self.conversation_history.append({"role": "user", "content": user_command})
        
        if "response" in tool_response:
            response_text = tool_response["response"]
            # Add assistant response to history
            self.conversation_history.append({"role": "assistant", "content": response_text})
            self.save_conversation_history()
            self.audio_processors.speak(response_text)
            
            # Check if the direct response needs follow-up
            if self.is_question_or_needs_clarification(response_text):
                time.sleep(0.3)
                return self.handle_follow_up_conversation()
        else:
            # Fallback to general AI response (already handles conversation history)
            ai_response = self.get_ai_response(user_command)
            self.audio_processors.speak(ai_response)
            
            # Check if this AI response needs follow-up too
            if self.is_question_or_needs_clarification(ai_response):
                time.sleep(0.3)
                return self.handle_follow_up_conversation()
        
        print("Direct response completed. Ready for next command.")
        return False
    
    def handle_fallback_conversation(self, user_command):
        """Handle fallback conversation with follow-up support"""
        # Give feedback for processing
        if len(user_command) > 20:  # Longer queries might need processing time
            self.audio_processors.speak("Let me process that for you")
            time.sleep(0.3)
        
        # This is a conversational message, so add to history and get AI response
        ai_response = self.get_ai_response(user_command)
        self.audio_processors.speak(ai_response)
        
        time.sleep(0.3)
        
        if self.is_question_or_needs_clarification(ai_response):
            return self.handle_follow_up_conversation()
        else:
            print("AI response is complete. Ready for next command.")
            return False
    
    def handle_follow_up_conversation(self):
        """Handle follow-up conversation when AI asks questions"""
        print("AI is asking a question or needs clarification. Continuing conversation...")
        # Pause using audio_processors helper for consistent behavior
        self.audio_processors.pause_listening(0.5)  # Longer pause for better audio separation
        print("Now listening for follow-up response...")
        
        # Try to get follow-up response
        follow_up_command = self.listen_for_command(is_follow_up=True)
        if follow_up_command:
            print(f"Received valid follow-up response: '{follow_up_command}'")
            ai_response = self.get_ai_response(follow_up_command)
            self.audio_processors.speak(ai_response)
            
            # Check if this response also needs follow-up
            if self.is_question_or_needs_clarification(ai_response):
                return self.handle_final_follow_up()
        else:
            print("No valid follow-up response detected after multiple attempts")
            self.audio_processors.speak("I didn't hear your response. Feel free to wake me up again if you need anything!")
        
        return False
    
    def handle_final_follow_up(self):
        """Handle final follow-up attempt"""
        print("AI has another question. One more follow-up attempt...")
        self.audio_processors.pause_listening(1.5)
        final_follow_up = self.listen_for_command(is_follow_up=True)
        if final_follow_up:
            final_response = self.get_ai_response(final_follow_up)
            self.audio_processors.speak(final_response)
        else:
          self.audio_processors.speak("I'll end our conversation here. Feel free to wake me up again anytime!")
        
        return False

    def check_and_announce_reminders(self):
        """Check for due reminders and announce them"""
        try:
            reminder_message = self.reminder_manager.get_due_reminders_for_speech()
            if reminder_message and not getattr(self.audio_processors, 'is_speaking', False):
                print(f"Announcing reminder: {reminder_message}")
                # Play attention sound before reminder
                self.audio_processors.play_beep_sound()
                time.sleep(0.3)
                self.audio_processors.speak(reminder_message)
        except Exception as e:
            print(f"Error checking reminders: {e}")

    def handle_wake_word_detection(self):
        """Handle actions when wake word is detected"""
        print("Wake word detected! Listening for command...")
        # play beep sound to indicate readiness
        self.audio_processors.play_beep_sound()
        self.audio_processors.pause_listening(0.2)  # Minimal pause
        
        user_command = self.listen_for_command()
        
        if user_command:
            should_exit = self.process_user_command(user_command)
            if should_exit:
                return True  # Signal to break from main loop
        else:
            print("No command detected, waiting for next input...")
        
        return False  # Continue main loop
    def main_conversation_thread(self):
        """Thread function for continuous wake word detection with speech interruption"""
        print("Main conversation thread started")
        
        while self.detection_running:
            # Ensure wake word detector and its model are available
            if not getattr(self, 'wake_word_detector', None) or not getattr(self.wake_word_detector, 'model', None):
                time.sleep(self.step_duration)
                continue
            # Check if we have enough audio data in our buffer
            if len(self.audio_buffer) < self.window_samples:
                time.sleep(self.step_duration)
                continue

            # Wake word detection (now always active, even during speech)
            audio_window = np.array(self.audio_buffer)
            detected, energy, confidence = self.wake_word_detector.detect_wakeword(audio_window, self.sample_rate)
            
            # Show detection attempts with energy > 0.005 for debugging
            if energy and energy > 0.005:
                print(f"Wakeword check: Detected={detected}, Energy={energy:.4f}, Confidence={confidence}")
            
            # Handle wake word detection
            if detected:
                # If we're speaking, interrupt it via audio_processors
                if getattr(self.audio_processors, 'is_speaking', False):
                    print("Wake word detected while speaking - interrupting!")
                    try:
                        self.audio_processors.stop_speech()
                    except Exception:
                        pass
                    time.sleep(0.3)  # Brief pause after interruption

                should_exit = self.handle_wake_word_detection()
                if should_exit:
                    break
                
                print("Returning to wake word listening...")
                
            time.sleep(self.step_duration)
        
    def run(self):
        """Main loop to run the voice assistant with conversation continuity"""
        print("Listening for wake word...")
        
        # Initialize wake word detection variables
        print("Wake word model already loaded in WakeWordDetector")

        self.window_duration = 1.5  # seconds (back to training size for accuracy)
        self.step_duration = 0.3    # seconds (faster than 0.5 but not too fast)
        self.window_samples = int(self.window_duration * self.sample_rate)
        
        # Create audio buffer for wake word detection in VoiceAssistant
        self.audio_buffer = deque(maxlen=self.window_samples)
        self.buffer_lock = threading.Lock()
        print(f"Audio buffer created with {self.window_samples} samples ({self.window_duration})")
        
        # Configure AudioProcessors to use our buffer
        self.audio_processors.set_audio_buffer(self.audio_buffer, self.buffer_lock)
        
        # Start reminder checker in background
        print("Starting reminder system...")
        # self.reminder_manager.start_reminder_checker()
            
        self.detection_running = True
        self.stream = None
        try:
            self.audio_processors.play_beep_sound(beep_file = "beep/startup_sound.wav")
            
            self.stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='float32', callback=self.audio_processors.audio_callback)
            with self.stream:
                t = threading.Thread(target=self.main_conversation_thread, daemon=True)
                t.start()
                while self.detection_running:
                    # Check for due reminders while waiting
                    self.check_and_announce_reminders()
                    time.sleep(0.1)  # Keep main thread alive
        except KeyboardInterrupt:
            print("\nProgram stopped by user")
            self.detection_running = False
        except Exception as e:
            print(f"Error in main loop: {e}")
            self.detection_running = False
        finally:
            print("Voice assistant shutting down...")
            # Stop reminder checker
            if hasattr(self, 'reminder_manager'):
                self.reminder_manager.stop_reminder_checker()

if __name__ == "__main__":
    try:
        assistant = VoiceAssistant()
        assistant.run()
    except Exception as e:
        import traceback
        print("\n Voice assistant stopped due to an error:")
        traceback.print_exc()
        print(f"Error details: {type(e).__name__}: {e}")
