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
import librosa
import numpy as np
from keras.models import load_model
import speech_recognition as sr
import pyttsx3
from openai import OpenAI
from connectors.spotify_connector import SpotifyConnector
from connectors.search_engine import GeminiSearch
from connectors.weather_connector import handle_tool_requests
import edge_tts
import asyncio
import tempfile
import pygame
import tempfile
import soundfile as sf
import threading
from collections import deque

# Load environment variables
load_dotenv()


CONVERSATION_FILE = "conversation_history.json"

# Wake word detection parameters (matching training)
n_mfcc = 40
n_fft = 2048
hop_length = 512
n_mels = 128

# Function to extract MFCC features (from test_cnn_model.py)
def extract_features(audio, sample_rate):
    try:
        mfcc = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length)
        mfcc_delta = librosa.feature.delta(mfcc)
        mfcc_delta2 = librosa.feature.delta(mfcc, order=2)
        features = np.concatenate((mfcc, mfcc_delta, mfcc_delta2), axis=0)
        features = features.T  # Transpose to (time_steps, features)
        return features
    except Exception as e:
        print(f"Error extracting features: {e}")
        return None

# Function to record audio (from test_cnn_model.py)
def record_audio(duration, sample_rate, save_path=None):
    try:
        print("Recording...")
        audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
        sd.wait()
        print("Recording complete.")
        audio_flat = audio.flatten()
        if save_path:
            sf.write(save_path, audio_flat, sample_rate)
            print(f"Audio saved to {save_path}")
        return audio_flat
    except Exception as e:
        print(f"Error recording audio: {e}")
        return None

def detect_wakeword(audio_window, model, sample_rate, energy_threshold=0.060, confidence_threshold=0.997):
    """Return True if wake word is detected in the given audio window."""
    energy = np.sqrt(np.mean(audio_window ** 2))
    if energy < energy_threshold:
        return False, energy, None
    features = extract_features(audio_window, sample_rate)
    desired_length = 44
    if features is None:
        return False, energy, None
    if features.shape[0] < desired_length:
        features = np.pad(features, ((0, desired_length - features.shape[0]), (0, 0)), mode='constant')
    else:
        features = features[:desired_length]
    features = features.reshape(1, desired_length, 120)
    prediction = model.predict(features, verbose=0)[0][0]
    return prediction > confidence_threshold, energy, prediction

class VoiceAssistant:
  
    def __init__(self):
        """Initialize the voice assistant components"""
        print("Initializing Voice Assistant...")

        # Initialize speech recognizer
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone(device_index=1)  # Adjust device index if needed

        # Initialize conversation history
        self.conversation_history = self.load_conversation_history()
        self.handle_weather_action = handle_tool_requests
        # Audio configuration  
        self.audio_channels = 1  # Channel configuration for microphone recording
        self.tts_speed = 1.3     # Speech speed multiplier (1.0 = normal, 1.3 = 30% faster)
        self.mic_device_id = 1   # USB microphone device ID
        self.mic_gain_factor = 0.8  # Reduce gain for sensitive USB mic

        # Audio processing
        self.sample_rate = 22050
        self.duration = 1.5
        self.debug_mode = True            # Show detailed output

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
                {"role": "system", "content": "You are a helpful, friendly, and concise voice assistant named Sofi. Provide short and direct answers suitable for voice responses."}
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
        self.conversation_history.append({"role": "user", "content": user_message})
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            # Ask OpenAI to return a JSON with tool/action info
            tool_prompt = (
                "You are a voice assistant. Based on the user's message, respond ONLY with a JSON object specifying the tool to use and action needed."
                "always transliterate the response in english even query is in different language."
                "if user message is in hindi or different language respond in that language. and provide language flag in response. also use the same language for tools query do not transliterate the user message."
                "Example for Spotify play: {\"tool\": \"spotify\", \"action\": \"play\", \"target\": \"album\", \"name\": \"Shape of You\"}. "
                "Example for Spotify resume stopped song: {\"tool\": \"spotify\", \"action\": \"resume\"}. "
                "Example for Spotify next: {\"tool\": \"spotify\", \"action\": \"next\"}. "
                "Example for Spotify stop: {\"tool\": \"spotify\", \"action\": \"stop\"}. "
                "Example for Google Search (for any questions needs current data, news, facts): {\"tool\": \"google_search\", \"action\": \"search\", \"query\": \"latest news in AI\"}. "
                "Example for Weather API (for weather-related queries): {\"tool\": \"weather\", \"action\": \"get_current_weather\", \"location\": \"London\"}. "
                "Example for Weather API (for weather-related queries): {\"tool\": \"weather\", \"action\": \"get_forecast\", \"location\": \"pune\", \"days\": 3}. "
                "Example for current time use API (for weather-related queries): {\"tool\": \"weather\", \"action\": \"get_timezone\", \"location\": \"pune\"}. "
                "If no tool is needed and l can answer directly, respond with: {\"tool\": \"none\", \"response\": \"your direct answer here\",{\"lang\": \"en\"}. "
                "if location is not provided always use Pune as default location."
                "User message: " + user_message
            )
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[{"role": "system", "content": tool_prompt}],
                max_tokens=100,
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
                    
                    # Brief ambient noise adjustment to calibrate
                    print("Calibrating microphone...")
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    print(f"Adjusted energy threshold: {recognizer.energy_threshold}")
                        
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
    
    def get_ai_response(self, user_message):
        """Get a formatted response from OpenAI for general conversation."""
        self.conversation_history.append({"role": "user", "content": user_message})
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=self.conversation_history,
                max_tokens=150,
                temperature=0.7
            )
            reply = response.choices[0].message.content.strip()
            self.conversation_history.append({"role": "assistant", "content": reply})
            self.save_conversation_history()
            return reply
        except Exception as e:
            print(f"Error getting AI response: {e}")
            return "Sorry, I'm having trouble thinking right now."
    
    def speak(self, text, voice="en-IN-AartiNeural", rate="+10%", speed_multiplier=1.0, lang= "en"):
        """
        Simple Edge TTS function for voice assistant integration
        
        Args:
            text: Text to speak
            voice: Edge TTS voice name
            rate: Speech rate ("+0%", "+30%", "+50%", etc.)
            speed_multiplier: Additional pygame playback speed control
        """
        print(f"Speaking with Edge TTS: {text}")
        if lang == "hi":
            voice = "hi-IN-AartiNeural"
        try:
            # Run the async function in a new event loop
            asyncio.run(self._generate_and_play(text, voice, rate, speed_multiplier))
            
        except Exception as e:
            print(f"Edge TTS failed: {e}")

    async def _generate_and_play(self, text, voice, rate, speed_multiplier):
        """Internal async function to generate and play TTS"""
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp_file_path = tmp_file.name
        tmp_file.close()
        
        try:
            # Generate speech
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(tmp_file_path)
            
            if os.path.exists(tmp_file_path):
                # Play with pygame
                base_frequency = 22050
             
                pygame.mixer.init(frequency=base_frequency, size=-16, channels=2, buffer=512)
                
                pygame.mixer.music.load(tmp_file_path)
                pygame.mixer.music.play()
                
                # Wait for playback to complete
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(50)
                
                pygame.mixer.quit()
                
        finally:
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
        
    
        
    
        
    def pause_listening(self, seconds=3):
        """Pause listening to avoid detecting the assistant's own voice"""
        import time
        print(f"Pausing listening for {seconds} seconds...")
        time.sleep(seconds)
    
    def check_microphones(self):
        """Check available microphones and their indices"""
        print("\nAvailable microphones:")
        for i, microphone_name in enumerate(sr.Microphone.list_microphone_names()):
            print(f"  {i}: {microphone_name}")
        print(f"Currently using microphone index: {self.mic_device_id}")
        
        # Test current microphone
        try:
            recognizer = sr.Recognizer()
            with sr.Microphone(device_index=self.mic_device_id) as source:
                print(f"Testing microphone {self.mic_device_id}...")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                print(f"Energy threshold: {recognizer.energy_threshold}")
                print("Microphone is working!")
        except Exception as e:
            print(f"Error with current microphone: {e}")
            print("Consider changing the device_index in the code")
    
    def play_beep_sound(self, beep_file = None):
        """Play a simple beep sound to indicate assistant is listening"""
        try:
            import pygame
            
            # Use the specific beep file
            if not beep_file:
                beep_file = "beep/short-beep-tone-47916.mp3"

            if os.path.exists(beep_file):
                pygame.mixer.init()
                pygame.mixer.music.load(beep_file)
                pygame.mixer.music.play()
                
                # Wait for the short beep to finish
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(10)
                
                pygame.mixer.quit()
            else:
                print(f"Beep file not found: {beep_file}")
                # Fallback to system beep

        except Exception as e:
            print(f"Error playing beep: {e}")
    
    
    
    def handle_spotify_action(self, tool_response):
        """Handle Spotify actions with enhanced feedback and error handling"""
        try:
            print(f"tool_response: {tool_response}")
            
            # Execute the Spotify action
            temp_connector = SpotifyConnector(None)
            result = temp_connector.main(tool_response)
            
            if result:
                self.speak(result)
                
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
                self.speak("Spotify action completed, but I didn't receive details about what happened.")
            
        except Exception as e:
            error_message = str(e)
            print(f"Spotify error: {error_message}")
            
            # Provide more specific error messages
            if "No active Spotify device" in error_message:
                self.speak("I couldn't find an active Spotify device. Please open Spotify on your device and try again.")
            elif "No track" in error_message or "No album" in error_message or "No artist" in error_message:
                self.speak("I couldn't find that song on Spotify. Try using different keywords or check the spelling.")
            elif "internet" in error_message.lower() or "connection" in error_message.lower():
                self.speak("I'm having trouble connecting to Spotify. Please check your internet connection.")
            else:
                self.speak("Sorry, I couldn't control Spotify right now. There was an unexpected error.")

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

    def audio_callback(self, indata, frames, time_info, status):
        """Audio callback function for real-time audio processing"""
        if status:
            print(f"Audio callback status: {status}")
        
        audio_samples = indata[:, 0]
        self.audio_buffer.extend(audio_samples)

    def process_user_command(self, user_command):
        """Process user command and execute appropriate actions with interrupt support"""
        # Check for exit commands
        if any(word in user_command for word in ["exit", "quit", "goodbye", "bye"]):
            self.speak("Goodbye!")
            self.detection_running = False
            return True  # Signal to break from main loop
        
        # Get tool action from OpenAI
        tool_response = self.get_tool_action(user_command)
        print(tool_response)
        
        # Handle different tool responses
        if tool_response["tool"] == "spotify":
            self.handle_spotify_action(tool_response)
            print("Spotify action completed. Ready for next command.")

        if tool_response["tool"] == "weather":
            response = self.handle_weather_action(tool_response)
            ai_response = self.get_ai_response(response)
            self.speak(ai_response)
            print("Weather action completed. Ready for next command.")

        elif tool_response["tool"] in ["search", "google_search", "web_search", "brave_search"]:
            result = self.handle_search_action(tool_response)
            self.speak(result)
            
            # Check if search result needs clarification or follow-up
            if self.is_question_or_needs_clarification(result):
                time.sleep(0.3)
                return self.handle_follow_up_conversation()
            else:
                print("Search completed. Ready for next command.")

        elif tool_response["tool"] == "none":
            return self.handle_direct_response(tool_response, user_command)
            
        else:
            # Fallback for any other case
            return self.handle_fallback_conversation(user_command)
        
        return False  # Continue main loop
    
    def handle_direct_response(self, tool_response, user_command):
        """Handle direct response from OpenAI without tools"""
        if "response" in tool_response:
            response_text = tool_response["response"]
            self.speak(response_text)
            
            # Check if the direct response needs follow-up
            if self.is_question_or_needs_clarification(response_text):
                time.sleep(0.3)
                return self.handle_follow_up_conversation()
        else:
            # Fallback to general AI response
            ai_response = self.get_ai_response(user_command)
            self.speak(ai_response)
            
            # Check if this AI response needs follow-up too
            if self.is_question_or_needs_clarification(ai_response):
                time.sleep(0.3)
                return self.handle_follow_up_conversation()
        
        print("Direct response completed. Ready for next command.")
        return False
    
    def handle_fallback_conversation(self, user_command):
        """Handle fallback conversation with follow-up support"""
        ai_response = self.get_ai_response(user_command)
        self.speak(ai_response)
        
        time.sleep(0.3)
        
        if self.is_question_or_needs_clarification(ai_response):
            return self.handle_follow_up_conversation()
        else:
            print("AI response is complete. Ready for next command.")
            return False
    
    def handle_follow_up_conversation(self):
        """Handle follow-up conversation when AI asks questions"""
        print("AI is asking a question or needs clarification. Continuing conversation...")
        self.pause_listening(0.5)  # Longer pause for better audio separation
        print("Now listening for follow-up response...")
        
        # Try to get follow-up response
        follow_up_command = self.listen_for_command(is_follow_up=True)
        if follow_up_command:
            print(f"Received valid follow-up response: '{follow_up_command}'")
            ai_response = self.get_ai_response(follow_up_command)
            self.speak(ai_response)
            
            # Check if this response also needs follow-up
            if self.is_question_or_needs_clarification(ai_response):
                return self.handle_final_follow_up()
        else:
            print("No valid follow-up response detected after multiple attempts")
            self.speak("I didn't hear your response. Feel free to wake me up again if you need anything!")
        
        return False
    
    def handle_final_follow_up(self):
        """Handle final follow-up attempt"""
        print("AI has another question. One more follow-up attempt...")
        self.pause_listening(1.5)
        final_follow_up = self.listen_for_command(is_follow_up=True)
        if final_follow_up:
            final_response = self.get_ai_response(final_follow_up)
            self.speak(final_response)
        else:
            self.speak("I'll end our conversation here. Feel free to wake me up again anytime!")
        
        return False
    
    def handle_wake_word_detection(self):
        """Handle actions when wake word is detected"""
        print("Wake word detected! Listening for command...")
        
        # Play simple beep sound for instant feedback
        self.play_beep_sound()
        self.pause_listening(0.3)  # Minimal pause
        
        user_command = self.listen_for_command()
        
        if user_command:
            should_exit = self.process_user_command(user_command)
            if should_exit:
                return True  # Signal to break from main loop
        else:
            print("No command detected, waiting for next input...")
        
        return False  # Continue main loop

    def main_conversation_thread(self):
        """Thread function for continuous wake word detection"""
        print("Main conversation thread started")
        conversation_active = False
        
        while self.detection_running:
            # Check if we have enough audio data
            if len(self.audio_buffer) < self.window_samples:
                time.sleep(self.step_duration)
                continue
            
            # Skip detection during conversation to avoid interruptions
            if conversation_active:
                time.sleep(self.step_duration)
                continue
                
            # Wake word detection
            audio_window = np.array(self.audio_buffer)
            detected, energy, confidence = detect_wakeword(audio_window, self.model, self.sample_rate)
            
            # Show detection attempts with energy > 0.005 for debugging
            if energy and energy > 0.005:
                print(f"Wakeword check: Detected={detected}, Energy={energy:.4f}, Confidence={confidence}")
            
            # Handle wake word detection
            if detected:
                conversation_active = True
                
                should_exit = self.handle_wake_word_detection()
                if should_exit:
                    break
                
                conversation_active = False
                print("Returning to wake word listening...")
                
            time.sleep(self.step_duration)
        
    def run(self):
        """Main loop to run the voice assistant with conversation continuity"""
        print("Listening for wake word...")
        
        # Initialize wake word detection variables
        self.model = load_model('model_training/saved_model/WWD_improved.h5')
        self.window_duration = 1.5  # seconds (back to training size for accuracy)
        self.step_duration = 0.3    # seconds (faster than 0.5 but not too fast)
        self.window_samples = int(self.window_duration * self.sample_rate)
        self.audio_buffer = deque(maxlen=self.window_samples)
        self.detection_running = True
        self.stream = None
        try:
            self.play_beep_sound(beep_file = "beep/startup_sound.wav")
            
            self.stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='float32', callback=self.audio_callback)
            with self.stream:
                t = threading.Thread(target=self.main_conversation_thread, daemon=True)
                t.start()
                while self.detection_running:
                    time.sleep(0.1)  # Keep main thread alive
        except KeyboardInterrupt:
            print("\nProgram stopped by user")
            self.detection_running = False
        except Exception as e:
            print(f"Error in main loop: {e}")
            self.detection_running = False
        finally:
            print("Voice assistant shutting down...")

if __name__ == "__main__":
    try:
        assistant = VoiceAssistant()
        assistant.run()
    except Exception as e:
        import traceback
        print("\n Voice assistant stopped due to an error:")
        traceback.print_exc()
        print(f"Error details: {type(e).__name__}: {e}")
