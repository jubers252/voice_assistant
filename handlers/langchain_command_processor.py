"""
LangChain-based Command Processor (Dummy Version)
This replaces your current CommandProcessor with an intelligent agent
"""


import os
import threading
import platform
import time
import speech_recognition as sr
from typing import Dict, Any
from dotenv import load_dotenv
import re
# LangChain imports (install with: pip install langchain langchain-openai)
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.memory import ConversationBufferWindowMemory
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool

# Import your existing connectors
from connectors.weather_connector import handle_tool_requests
from connectors.amzon_connector import get_amazon_result
from connectors.amazon_order_tracker import get_order
from connectors.spotify_connector import SpotifyConnector
from connectors.search_engine import GeminiSearch
from connectors.telegram_bot import TelegramBot
from connectors.reminder_manager import ReminderManager
from speech.speech_recognizer import SpeechRecognizer
from connectors.bigbasket_connector import BigBasketTools
load_dotenv()


class LangChainAgentProcessor:
    """
    LangChain-based replacement for CommandProcessor
    This intelligently decides which tools to use based on user input
    """
    
    def __init__(self, conversation_history, audio_processors, conversation_manager=None):
        """
        Initialize LangChain Agent Processor
        
        Required parameters:
        - conversation_history: List to store conversation history
        - audio_processors: Handler for speech/TTS functionality
        """
        
        # Store the handlers that are actually used
        self.conversation_history = conversation_history
        self.audio_processors = audio_processors
        self.reminder_manager = ReminderManager()
        # Optional ConversationManager instance to persist history
        self.conversation_manager = conversation_manager

        # Initialize connectors (same as original)
        self.spotify_connector = SpotifyConnector(None)
        self.search_connector = GeminiSearch()
        self.telegram_bot = TelegramBot()
        self.big_basket_connector = BigBasketTools()
        
        # LangChain-specific setup
        self.agent_executor = None
        self.tools = []
        
        self._setup_langchain_agent()
    
    def _create_current_weather_tool(self) -> Tool:
        """Get current weather for a location"""
        def current_weather_function(location: str) -> str:
            try:
                tool_request = {
                    "tool": "weather", 
                    "action": "get_current_weather",
                    "location": location
                }
                result = handle_tool_requests(tool_request)
                return f"Current weather in {location}: {result}"
            except Exception as e:
                return f"Current weather error: {str(e)}"
        
        return Tool(
            name="get_current_weather",
            description="Get current weather conditions for a specific location. Input should be a city name or location.",
            func=current_weather_function
        )
    
    def _create_weather_forecast_tool(self) -> Tool:
        """Get weather forecast for a location"""
        def forecast_function(location: str) -> str:
            try:
                tool_request = {
                    "tool": "weather", 
                    "action": "get_forecast",
                    "location": location
                }
                result = handle_tool_requests(tool_request)
                return f"Weather forecast for {location}: {result}"
            except Exception as e:
                return f"Weather forecast error: {str(e)}"
        
        return Tool(
            name="get_weather_forecast",
            description="Get weather forecast (3-day) for a specific location. Input should be a city name or location.",
            func=forecast_function
        )
    
    def _create_timezone_tool(self) -> Tool:
        """Get timezone information for a location"""
        def timezone_function(location: str) -> str:
            try:
                tool_request = {
                    "tool": "weather", 
                    "action": "get_timezone",
                    "location": location
                }
                result = handle_tool_requests(tool_request)
                return f"Timezone for {location}: {result}"
            except Exception as e:
                return f"Timezone error: {str(e)}"
        
        return Tool(
            name="get_timezone",
            description="Get timezone and current local time for a specific location. Input should be a city name or location.",  
            func=timezone_function
        )
    
    def _create_spotify_play_track_tool(self) -> Tool:
        """Play a specific track on Spotify"""
        def play_track_function(track_name: str) -> str:
            try:
                def spotify_thread_func():
                    tool_response = {
                        "tool": "spotify",
                        "action": "play",
                        "target": "track",
                        "name": track_name
                    }
                    return self.spotify_connector.handle_spotify_action_with_feedback(
                        tool_response, self.conversation_history
                    )
                
                # Run Spotify in separate thread to avoid audio conflicts
                spotify_thread = threading.Thread(target=spotify_thread_func, daemon=True)
                spotify_thread.start()
                
                return f"Starting track playback: {track_name}"
            except Exception as e:
                return f"Spotify track error: {str(e)}"
        
        return Tool(
            name="play_spotify_track",
            description="Play a specific song/track on Spotify. Input should be the track name.",
            func=play_track_function
        )
    
    def _create_spotify_play_album_tool(self) -> Tool:
        """Play a specific album on Spotify"""
        def play_album_function(album_name: str) -> str:
            try:
                def spotify_thread_func():
                    tool_response = {
                        "tool": "spotify",
                        "action": "play",
                        "target": "album",
                        "name": album_name
                    }
                    return self.spotify_connector.handle_spotify_action_with_feedback(
                        tool_response, self.conversation_history
                    )
                
                # Run Spotify in separate thread to avoid audio conflicts
                spotify_thread = threading.Thread(target=spotify_thread_func, daemon=True)
                spotify_thread.start()
                
                return f"Starting album playback: {album_name}"
            except Exception as e:
                return f"Spotify album error: {str(e)}"
        
        return Tool(
            name="play_spotify_album",
            description="Play a specific album on Spotify. Input should be the album name.",
            func=play_album_function
        )
    
    def _create_spotify_play_artist_tool(self) -> Tool:
        """Play music by a specific artist on Spotify"""
        def play_artist_function(artist_name: str) -> str:
            try:
                def spotify_thread_func():
                    tool_response = {
                        "tool": "spotify",
                        "action": "play",
                        "target": "artist",
                        "name": artist_name
                    }
                    return self.spotify_connector.handle_spotify_action_with_feedback(
                        tool_response, self.conversation_history
                    )
                
                # Run Spotify in separate thread to avoid audio conflicts
                spotify_thread = threading.Thread(target=spotify_thread_func, daemon=True)
                spotify_thread.start()
                
                return f"Starting artist playback: {artist_name}"
            except Exception as e:
                return f"Spotify artist error: {str(e)}"
        
        return Tool(
            name="play_spotify_artist",
            description="Play music by a specific artist on Spotify. Input should be the artist name.",
            func=play_artist_function
        )
    
    def _create_spotify_control_tool(self) -> Tool:
        """Control Spotify playback (pause, resume, next)"""
        def control_function(action: str) -> str:
            try:
                action_lower = action.lower().strip()
                
                if action_lower in ['pause', 'stop']:
                    spotify_action = "stop"
                elif action_lower in ['resume', 'continue', 'play']:
                    spotify_action = "resume"
                elif action_lower in ['next', 'skip']:
                    spotify_action = "next"
                else:
                    return "Use: pause, resume, or next"
                
                def spotify_control_thread_func():
                    tool_response = {
                        "tool": "spotify",
                        "action": spotify_action
                    }
                    return self.spotify_connector.handle_spotify_action_with_feedback(
                        tool_response,  self.conversation_history
                    )
                
                # Run Spotify control in separate thread to avoid audio conflicts
                spotify_thread = threading.Thread(target=spotify_control_thread_func, daemon=True)
                spotify_thread.start()
                
                return f"Spotify control: {action_lower}"
            except Exception as e:
                return f"Spotify control error: {str(e)}"
        
        return Tool(
            name="control_spotify_playback",
            description="Control Spotify playback. Use 'pause', 'resume', or 'next'.",
            func=control_function
        )
    
    def _create_search_tool(self) -> Tool:
        """Convert search connector to LangChain tool"""
        def search_function(query: str) -> str:
            try:
                # Use your existing search connector
                tool_request = {"query": query, "tool": "search"}
                result = self.search_connector.handle_search_action_with_feedback(tool_request)
                return result[:500]  # Limit response length
            except Exception as e:
                return f"Search error: {str(e)}"
        
        return Tool(
            name="search_web",
            description="Search the internet for information. Input should be a search query or question.",
            func=search_function
        )
    
    def _create_amazon_single_product_tool(self) -> Tool:
        """Search Amazon for detailed information about a single product"""
        def single_product_function(query: str) -> str:
            try:
                tool_request = {
                    "tool": "amazon", 
                    "action": "single_product_search",
                    "query": query
                }
                result = get_amazon_result(tool_request)
                # Format the result nicely for the LLM
                if isinstance(result, dict):
                    title = result.get('title', 'Unknown Product')
                    price = result.get('price', 'Price not available')
                    rating = result.get('rating', 'No rating')
                    url = result.get('url', 'N/A')
                    asin = result.get('asin', 'N/A')
                    
                    # Include more details if available
                    response = f"Product: {title}\n Price: {price}\n Rating: {rating}/5\n Link: {url}"
                    
                    # Add image if available
                    if result.get('image'):
                        response += f"\n Image: {result.get('image')}"
                    
                    # Add ASIN for reference
                    if asin != 'N/A':
                        response += f"\nASIN: {asin}"
                    
                    return response
                return f"Single product result: {str(result)[:800]}..."
            except Exception as e:
                return f"Amazon single product search error: {str(e)}"
        
        return Tool(
            name="search_amazon_single_product",
            description="Search Amazon for detailed information about a specific single product with price, rating, and direct product link. Use when user wants detailed info about one product.",
            func=single_product_function
        )
    
    def _create_amazon_multi_product_tool(self) -> Tool:
        """Search Amazon for multiple products (comparison/browse)"""
        def multi_product_function(query: str) -> str:
            try:
                tool_request = {
                    "tool": "amazon", 
                    "action": "multi_product_search",
                    "query": query,
                    "max_results": 5
                }
                result = get_amazon_result(tool_request)
                # Format multiple products nicely
                if isinstance(result, list):
                    formatted_results = []
                    for i, product in enumerate(result[:3], 1):  # Limit to top 3 for readability
                        title = product.get('title', 'Unknown Product')
                        price = product.get('price', 'Price not available')
                        url = product.get('url', 'N/A')
                        rating = product.get('rating', 'No rating')
                        
                        product_info = f"{i}.  {title}\n    {price}\n   {rating}/5\n   {url}"
                        formatted_results.append(product_info)
                    
                    return f"🛒 Amazon Search Results:\n\n" + "\n\n".join(formatted_results)
                return f"Multiple products result: {str(result)[:800]}..."
            except Exception as e:
                return f"Amazon multi-product search error: {str(e)}"
        
        return Tool(
            name="search_amazon_multiple_products",
            description="Search Amazon for multiple products to compare options with prices, ratings, and direct product links. Use when user wants to see several product choices or browse options.",
            func=multi_product_function
        )
    
    def _create_amazon_order_tracking_tool(self) -> Tool:
        """Track Amazon orders from recent days"""
        def order_tracking_function(days_input: str) -> str:
            try:
                # Extract number of days, default to 5
               
                days = 5
                numbers = re.findall(r'\d+', days_input)
                if numbers:
                    days = max(1, min(int(numbers[0]), 30))  # Limit 1-30 days
                
                tool_request = {
                    "tool": "amazon_order_tracking",
                    "action": "get_recent_orders", 
                    "days": days
                }
                result = get_order(tool_request)
                
                if isinstance(result, list) and result:
                    return f"Found {len(result)} orders from last {days} days: {str(result)[:400]}..."
                elif isinstance(result, list):
                    return f"No orders found from the last {days} days."
                else:
                    return f"Order tracking: {str(result)[:300]}..."
            except Exception as e:
                return f"Order tracking error: {str(e)}"
        
        return Tool(
            name="track_amazon_orders",
            description="Track Amazon orders from recent days. Input: number of days (e.g., '5' or 'last 7 days').",
            func=order_tracking_function
        )
    
    def _create_set_reminder_tool(self) -> Tool:
        """Set a reminder tool"""
        def set_reminder_function(reminder_input: str) -> str:
            try:
                # Parse reminder input - expected format: "text|time" or just "text"
                parts = reminder_input.split('|', 1) if '|' in reminder_input else [reminder_input, ""]
                text = parts[0].strip()
                time_str = parts[1].strip() if len(parts) > 1 else "in 5 minutes"  # Default time
                
                action_data = {
                    "action": "set",
                    "text": text,
                    "time": time_str
                }
                result = self.reminder_manager.handle_reminder_action(action_data)
                return result
            except Exception as e:
                return f"Set reminder error: {str(e)}"
        
        return Tool(
            name="set_reminder",
            description="Set a reminder for the user. Input format: 'reminder text|time' (e.g., 'Call mom|in 30 minutes' or 'Meeting|tomorrow at 2 PM'). If no time specified, defaults to 5 minutes.",
            func=set_reminder_function
        )
    
    def _create_list_reminders_tool(self) -> Tool:
        """List all active reminders tool"""
        def list_reminders_function(query: str) -> str:
            try:
                action_data = {"action": "list"}
                result = self.reminder_manager.handle_reminder_action(action_data)
                return result
            except Exception as e:
                return f"List reminders error: {str(e)}"
        
        return Tool(
            name="list_reminders",
            description="List all active reminders. No input required.",
            func=list_reminders_function
        )
    
    def _create_cancel_reminder_tool(self) -> Tool:
        """Cancel a specific reminder tool"""
        def cancel_reminder_function(reminder_id: str) -> str:
            try:
                # Parse reminder ID
                try:
                    id_num = int(reminder_id.strip())
                except ValueError:
                    return "Please provide a valid reminder ID number."
                
                action_data = {
                    "action": "cancel",
                    "id": id_num
                }
                result = self.reminder_manager.handle_reminder_action(action_data)
                return result
            except Exception as e:
                return f"Cancel reminder error: {str(e)}"
        
        return Tool(
            name="cancel_reminder",
            description="Cancel a specific reminder by ID. Input should be the reminder ID number.",
            func=cancel_reminder_function
        )
    
    def _create_check_reminders_tool(self) -> Tool:
        """Check for due reminders tool"""
        def check_reminders_function(query: str) -> str:
            try:
                action_data = {"action": "check"}
                result = self.reminder_manager.handle_reminder_action(action_data)
                return result
            except Exception as e:
                return f"Check reminders error: {str(e)}"
        
        return Tool(
            name="check_reminders",
            description="Check for any due reminders right now. No input required.",
            func=check_reminders_function
        )
    
    def _create_telegram_message_tool(self) -> Tool:
        """Send text message via Telegram"""
        def telegram_message_function(message: str) -> str:
            try:
                tool_response = {
                    "action": "send_message",
                    "message": message
                }
                result = self.telegram_bot.telegram_handler(tool_response)
                return f"Message sent to Telegram: {message}"
            except Exception as e:
                return f"Telegram message error: {str(e)}"
        
        return Tool(
            name="send_telegram_message",
            description="Send a text message via Telegram. Input should be the message text.",
            func=telegram_message_function
        )
    
    def _create_telegram_photo_tool(self) -> Tool:
        """Send photo via Telegram"""
        def telegram_photo_function(photo_info: str) -> str:
            try:
                # Parse photo_info - expected format: "photo_path|caption" or just "photo_path"
                parts = photo_info.split('|', 1)
                photo_path = parts[0].strip()
                caption = parts[1].strip() if len(parts) > 1 else ""
                
                # Validate if it's a URL or file path
                if photo_path.startswith(('http://', 'https://')):
                    # For URLs, we need to note that Telegram may have restrictions
                    caption_note = f"{caption}\n[Note: URL photo - may require download first]" if caption else "[Note: URL photo - may require download first]"
                else:
                    caption_note = caption
                
                tool_response = {
                    "action": "send_photo",
                    "photo": photo_path,
                    "caption": caption_note
                }
                result = self.telegram_bot.telegram_handler(tool_response)
                
                if result and result.get('message_id'):
                    return f"Photo sent successfully to Telegram: {photo_path[:50]}..."
                else:
                    return f"Failed to send photo to Telegram. Note: URLs may need to be downloaded first. Path: {photo_path[:50]}..."
            except Exception as e:
                return f"Telegram photo error: {str(e)}. Note: For URLs, try downloading the image first."
        
        return Tool(
            name="send_telegram_photo",
            description="Send a photo via Telegram. Input format: 'photo_path|caption' or just 'photo_path'. Note: URLs may not work directly - local files preferred.",
            func=telegram_photo_function
        )
    
    def _create_telegram_document_tool(self) -> Tool:
        """Send document via Telegram"""
        def telegram_document_function(doc_info: str) -> str:
            try:
                # Parse doc_info - expected format: "document_path|caption" or just "document_path"
                parts = doc_info.split('|', 1)
                doc_path = parts[0].strip()
                caption = parts[1].strip() if len(parts) > 1 else ""
                
                tool_response = {
                    "action": "send_document",
                    "document": doc_path,
                    "caption": caption
                }
                result = self.telegram_bot.telegram_handler(tool_response)
                return f"Document sent to Telegram: {doc_path}"
            except Exception as e:
                return f"Telegram document error: {str(e)}"
        
        return Tool(
            name="send_telegram_document",
            description="Send a document via Telegram. Input format: 'document_path|caption' or just 'document_path'.",
            func=telegram_document_function
        )
    
    def _create_telegram_video_tool(self) -> Tool:
        """Send video via Telegram"""
        def telegram_video_function(video_info: str) -> str:
            try:
                # Parse video_info - expected format: "video_path|caption" or just "video_path"
                parts = video_info.split('|', 1)
                video_path = parts[0].strip()
                caption = parts[1].strip() if len(parts) > 1 else ""
                
                tool_response = {
                    "action": "send_video",
                    "video": video_path,
                    "caption": caption
                }
                result = self.telegram_bot.telegram_handler(tool_response)
                return f"Video sent to Telegram: {video_path}"
            except Exception as e:
                return f"Telegram video error: {str(e)}"
        
        return Tool(
            name="send_telegram_video",
            description="Send a video via Telegram. Input format: 'video_path|caption' or just 'video_path'.",
            func=telegram_video_function
        )
    
    def _create_volume_control_tool(self) -> Tool:
        """Control system volume - cross-platform version"""
        def volume_control_function(command: str) -> str:
            try:
                import subprocess
                
                command_lower = command.lower()
                current_os = platform.system()
                
                if current_os == "Windows":
                    # Windows implementation
                    if 'mute' in command_lower:
                        try:
                            subprocess.run(['nircmd.exe', 'mutesysvolume', '1'], shell=True)
                            return "Volume muted"
                        except:
                            subprocess.run(['powershell', '-c', 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("{VOLUME_MUTE}")'])
                            return "Volume muted"
                    
                    elif 'unmute' in command_lower:
                        try:
                            subprocess.run(['nircmd.exe', 'mutesysvolume', '0'], shell=True)
                            return "Volume unmuted"
                        except:
                            subprocess.run(['powershell', '-c', 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("{VOLUME_MUTE}")'])
                            return "Volume unmuted"
                    
                    elif 'up' in command_lower or 'increase' in command_lower:
                        try:
                            subprocess.run(['nircmd.exe', 'changesysvolume', '2000'], shell=True)
                            return "Volume increased"
                        except:
                            subprocess.run(['powershell', '-c', 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("{VOLUME_UP}")'])
                            return "Volume increased"
                    
                    elif 'down' in command_lower or 'decrease' in command_lower:
                        try:
                            subprocess.run(['nircmd.exe', 'changesysvolume', '-2000'], shell=True)
                            return "Volume decreased"
                        except:
                            subprocess.run(['powershell', '-c', 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("{VOLUME_DOWN}")'])
                            return "Volume decreased"
                            
                elif current_os == "Linux":
                    # Linux implementation using amixer
                    if 'mute' in command_lower:
                        subprocess.run(['amixer', 'set', 'Master', 'mute'], check=True)
                        return "Volume muted"
                    
                    elif 'unmute' in command_lower:
                        subprocess.run(['amixer', 'set', 'Master', 'unmute'], check=True)
                        return "Volume unmuted"
                    
                    elif 'up' in command_lower or 'increase' in command_lower:
                        subprocess.run(['amixer', 'set', 'Master', '5%+'], check=True)
                        return "Volume increased"
                    
                    elif 'down' in command_lower or 'decrease' in command_lower:
                        subprocess.run(['amixer', 'set', 'Master', '5%-'], check=True)
                        return "Volume decreased"
                
                else:
                    return f"Volume control not supported on {current_os}. Only Windows and Linux are supported."
                    
                return "Say: volume up, volume down, mute, or unmute"
                    
            except Exception as e:
                return f"Volume control error: {str(e)}"
        
        return Tool(
            name="control_system_volume",
            description="Control system volume. Say 'volume up', 'volume down', 'mute', or 'unmute'.",
            func=volume_control_function
        )
    

    def _create_follow_up_question_tool(self) -> Tool:
        """Tool for the AI to ask follow-up questions and continue listening"""
        def ask_follow_up_function(question: str) -> str:
            try:
                # Speak the follow-up question
                self.audio_processors.speak(question)
                
                # Wait for speech to complete using is_speaking flag
                print("Waiting for speech to complete...")
                while hasattr(self.audio_processors, 'is_speaking') and self.audio_processors.is_speaking:
                    time.sleep(0.1)
                
                print("Speech completed, ready for follow-up...")
                time.sleep(1.0)  # Longer buffer to ensure TTS cleanup
                
                # Now listen for follow-up response
                print(f"AI asked: {question}")
                print("Now listening for follow-up response...")
                
                # Create recognizer with better microphone handling
                recognizer = SpeechRecognizer()

                self.audio_processors.play_beep_sound()
                time.sleep(0.2)
                
                # Listen with longer timeout for follow-up
                follow_up_command = recognizer.listen_for_command(is_follow_up=True, timeout=20, max_retries=3)
                
                if follow_up_command:
                    print(f"Received follow-up response: '{follow_up_command}'")
                    return f"User responded: {follow_up_command}"
                else:
                    return "No follow-up response received"
                    
            except Exception as e:
                return f"Follow-up error: {str(e)}"
        
        return Tool(
            name="ask_follow_up_question",
            description="MANDATORY tool when you need to ask ANY question or need clarification from user. If your response would have a question mark '?', you MUST use this tool instead of responding with text. This tool speaks your question and waits for user's voice response. Input: your question text. NEVER ask questions in your text response - ALWAYS use this tool for questions.",
            func=ask_follow_up_function
        )
    
    def _create_bigbasket_tool(self) -> Tool:
        """BigBasket shopping tool: add products, clear cart, checkout, place order"""
        def bigbasket_function(input_str: str) -> str:
            try:
                # Parse input - handle formats: "action", "action|product", "action|product|quantity"
                parts = input_str.split("|")
                action = parts[0].lower().strip()
                product = parts[1].strip() if len(parts) > 1 else ""
                quantity = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 1
                
                if action == "login":
                    result = self.big_basket_connector.login_to_bigbasket()
                    return f"BigBasket login: {result}"
                elif action == "search":
                    if not product:
                        return "Please specify a product to search."
                    result = self.big_basket_connector.search_product_info(product)
                    return f"BigBasket search results: {result}"
                elif action == "clear_cart":
                    result = self.big_basket_connector.clear_cart()
                    return f"BigBasket clear cart: {result}"
                elif action == "add_product":
                    if not product:
                        return "Please specify a product to add."
                    result = self.big_basket_connector.add_product_to_cart(product, quantity)
                    
                    # Handle different result statuses
                    if result.get('status') == 'success':
                        msg = f"Added {quantity} x {product} to cart"
                        
                        # Use actual cart item details if available
                        if result.get('added_item'):
                            item = result['added_item']
                            msg = f"Added {item['quantity']} x {item['name']}"
                            if item.get('price'):
                                msg += f" at {item['price']}"
                        
                        return msg + "."
                    elif result.get('status') == 'out_of_stock':
                        msg = result.get('message', f"{product} is out of stock")
                        alternatives = result.get('alternatives', [])
                        if alternatives:
                            alt_list = "\n".join([f"{i+1}. {alt.get('name', alt)}" for i, alt in enumerate(alternatives[:5])])
                            return f"{msg}\n\nAvailable alternatives:\n{alt_list}\n\nWould you like to add any of these alternatives instead?"
                        return f"{msg}. No alternatives found."
                    elif result.get('status') == 'alternatives':
                        msg = result.get('message', 'Product not found')
                        alternatives = result.get('alternatives', [])
                        if alternatives:
                            alt_list = "\n".join([f"{i+1}. {alt.get('name', alt)}" for i, alt in enumerate(alternatives[:5])])
                            return f"{msg}\n\nDid you mean:\n{alt_list}\n\nPlease confirm which product you want."
                        return f"{msg}"
                    else:
                        error = result.get('error', 'Unknown error')
                        return f"Failed to add {product}: {error}"
                elif action == "add_multiple":
                    if not product:
                        return "Please specify products to add in format: product1:qty1,product2:qty2"
                    result = self.big_basket_connector.add_multiple_products(product)
                    
                    # Format response for multiple products
                    if result.get('status') in ['success', 'partial', 'failed']:
                        summary = result.get('summary', {})
                        results_list = result.get('results', [])
                        
                        # Build summary message
                        msg = f"Added {summary.get('successful', 0)} out of {summary.get('total_products', 0)} products.\n\n"
                        
                        # List successes
                        successes = [r for r in results_list if r['status'] == 'added']
                        if successes:
                            msg += "✓ Successfully added:\n"
                            for r in successes:
                                msg += f"  - {r['product']} (qty: {r['quantity']})\n"
                        
                        # List out-of-stock items
                        out_of_stock = [r for r in results_list if r['status'] == 'out_of_stock']
                        if out_of_stock:
                            msg += "\n⚠ Out of stock:\n"
                            for r in out_of_stock:
                                msg += f"  - {r['product']}\n"
                                if r.get('alternatives'):
                                    msg += f"    Alternatives available: {len(r['alternatives'])} options\n"
                        
                        # List failures
                        failures = [r for r in results_list if r['status'] not in ['added', 'out_of_stock']]
                        if failures:
                            msg += "\n✗ Could not add:\n"
                            for r in failures:
                                msg += f"  - {r['product']}: {r.get('message', 'Not found')}\n"
                        
                        # Ask for confirmation if there are out-of-stock items
                        if out_of_stock:
                            msg += "\nWould you like to see alternatives for out-of-stock items?"
                        
                        return msg
                    else:
                        return f"BigBasket add multiple error: {result.get('error', 'Unknown error')}"
                elif action == "checkout":
                    result = self.big_basket_connector.proceed_to_checkout()
                    return f"BigBasket checkout: {result}"
                elif action == "place_order":
                    result = self.big_basket_connector.place_order_cod()
                    return f"BigBasket place order: {result}"
                elif action == "close_browser":
                    self.big_basket_connector.close_browser()
                    return f"BigBasket browser session closed."
                else:
                    return "Supported actions: login, search, clear_cart, add_product, add_multiple, checkout, place_order, close_browser"
            except Exception as e:
                return f"BigBasket tool error: {str(e)}"
        return Tool(
            name="bigbasket_tool",
            description="BigBasket grocery shopping. When user wants to ORDER/BUY groceries: 1) login 2) clear_cart 3) add_product/add_multiple 4) ask confirmation using ask_follow_up_question 5) checkout 6) place_order 7) close_browser. Format: 'action|product|quantity' for add_product, 'add_multiple|product1:qty1,product2:qty2' for multiple items, or just 'action' for login/checkout/place_order. ALWAYS ask user confirmation before checkout using ask_follow_up_question tool.",
            func=bigbasket_function
        )

    def _setup_langchain_agent(self):
        """Setup the LangChain agent with tools and memory"""
        
        # Create tools from your existing connectors
        self.tools = [
            self._create_current_weather_tool(),
            self._create_weather_forecast_tool(),
            self._create_timezone_tool(),
            self._create_spotify_play_track_tool(),
            self._create_spotify_play_album_tool(),
            self._create_spotify_play_artist_tool(),
            self._create_spotify_control_tool(),
            self._create_search_tool(),
            self._create_amazon_single_product_tool(),
            self._create_amazon_multi_product_tool(),
            self._create_amazon_order_tracking_tool(),
            self._create_set_reminder_tool(),
            self._create_list_reminders_tool(),
            self._create_cancel_reminder_tool(),
            self._create_check_reminders_tool(),
            self._create_telegram_message_tool(),
            self._create_telegram_photo_tool(),
            self._create_telegram_document_tool(),
            self._create_telegram_video_tool(),
            self._create_volume_control_tool(),
            self._create_follow_up_question_tool(),
            self._create_bigbasket_tool()
        ]
        
        # Initialize LLM
        llm = ChatOpenAI(
            model="gpt-4.1",
            temperature=0.7,
            openai_api_key=os.getenv('OPENAI_API_KEY')
        )
        
        # Setup memory for conversation context
        memory = ConversationBufferWindowMemory(
            memory_key="chat_history",
            return_messages=True,
            k=10  # Remember last 10 exchanges
        )
        
        # Create system prompt
        system_prompt = """You are Sofi, a voice assistant in Pisoli, Pune.

**CRITICAL RULE - ASKING QUESTIONS:**
YOU CANNOT ASK QUESTIONS IN YOUR RESPONSE TEXT!
If your response would contain a question mark "?" → YOU MUST call the ask_follow_up_question tool instead.
If you need ANY clarification → YOU MUST call ask_follow_up_question tool, NOT respond with text.
If user has multiple choices → YOU MUST call ask_follow_up_question to ask which one.

Examples of WRONG behavior (DO NOT DO THIS):
 "Would you like to add this to cart?" → WRONG! Must call ask_follow_up_question("Would you like to add this to cart?")
 "Which size do you want?" → WRONG! Must call ask_follow_up_question("Which size do you want?")
 "Should I proceed?" → WRONG! Must call ask_follow_up_question("Should I proceed?")

**LANGUAGE RULE:**
- Hindi question → respond in Devanagari ONLY (मौसम not mausam)
- English question → respond in English
- NEVER mix scripts or transliterate Hindi

**CAPABILITIES:** weather, Spotify, search, Amazon, reminders, Telegram, volume, BigBasket

**BigBasket ORDERING (IMPORTANT):**
 For product information presented via TTS, summarize key details as short, spoken-friendly bullet points (2-4 concise items).
        BigBasket Shopping:
        - Workflow: login → search → show results → ask selection → clear_cart → add_product → checkout → place_order → close_browser
        - For 'search'/'add_product': pass both action and product parameters
         - Always show search results and clear the cart before adding to cart
        - Always get confirmation from user before calling 'place_order'
       
Brief TTS-friendly, do not add any special character in responses."""
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        # Create agent
        agent = create_openai_functions_agent(
            llm=llm,
            tools=self.tools,
            prompt=prompt
        )
        
        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=memory,
            verbose=True,  # Shows the agent's reasoning process
            handle_parsing_errors=True,
            max_iterations=25  # Increased for complex workflows like BigBasket ordering
            # Removed early_stopping_method as it's deprecated in newer versions
        )
        
        print("LangChain agent initialized with tools:", [tool.name for tool in self.tools])
    

        
    def process_user_command(self, user_command: str) -> bool:
        """
        Main method that replaces your original process_user_command
        Now uses intelligent agent instead of manual tool selection
        Includes follow-up conversation support
        """
        
        # Check for exit commands (same as original)
        if any(word in user_command.lower() for word in ["exit", "quit", "goodbye", "bye"]):
            self.audio_processors.speak("Goodbye!")
            return True
        
        try:
            # Define the agent processing function
            def agent_processing():
                result = self.agent_executor.invoke({"input": user_command})
                response = result["output"]
                
                # Add to conversation history
                self.conversation_history.append({"role": "user", "content": user_command})
                self.conversation_history.append({"role": "assistant", "content": response})

                # Persist conversation history if a ConversationManager is provided
                try:
                    if getattr(self, 'conversation_manager', None):
                        self.conversation_manager.save_conversation_history()
                except Exception as save_err:
                    print(f"Warning: failed to save conversation history: {save_err}")

                # Speak the response
                self.audio_processors.speak(response)
                return response
            
            # Process directly without delayed feedback
            response = agent_processing()
            
            # No need to check for follow-up questions - the LLM will use the ask_follow_up_question tool when needed
            
            print("Agent processing completed. Ready for next command.")
            return False
            
        except Exception as e:
            error_msg = f"Sorry, I encountered an error: {str(e)}"
            print(f"Agent error: {e}")
            self.audio_processors.speak(error_msg)
            return False
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Get information about the agent's current state"""
        return {
            "tools_count": len(self.tools),
            "agent_active": self.agent_executor is not None,
            "tool_names": [tool.name for tool in self.tools] if self.tools else []
        }



if __name__ == "__main__":
    # Test the LangChain processor functionality
    print("Testing LangChainAgentProcessor...")
    
    # Mock handlers for testing
    class MockHandler:
        def speak(self, text, lang='en'):
            print(f"[SPEAK]: {text}")
        
        def get_tool_action(self, command):
            return {"tool": "none", "message": "test"}
        
        def handle_reminder_action(self, request):
            return "Mock reminder created"
        
        def telegram_handler(self, request):
            return "Mock telegram message sent"
    
    # Create mock conversation history
    conversation_history = []
    
    try:
        # Test initialization - only required parameters
        processor = LangChainAgentProcessor(
            conversation_history=conversation_history,
            audio_processors=MockHandler()
        )
        
        print("✓ LangChainAgentProcessor initialized successfully")
        agent_info = processor.get_agent_info()
        print(f"✓ Agent info: {agent_info}")
        print(f"✓ Available tools: {', '.join(agent_info['tool_names'])}")
        
        # Test individual tool creation
        current_weather_tool = processor._create_current_weather_tool()
        forecast_tool = processor._create_weather_forecast_tool()
        timezone_tool = processor._create_timezone_tool()
        single_amazon_tool = processor._create_amazon_single_product_tool()
        multi_amazon_tool = processor._create_amazon_multi_product_tool()
        order_tracking_tool = processor._create_amazon_order_tracking_tool()
        telegram_message_tool = processor._create_telegram_message_tool()
        telegram_photo_tool = processor._create_telegram_photo_tool()
        telegram_document_tool = processor._create_telegram_document_tool()
        telegram_video_tool = processor._create_telegram_video_tool()
        
        print("All weather tool creation methods work")
        print("All Amazon tool creation methods work")
        print("Amazon order tracking tool created successfully")
        print("All Telegram tool creation methods work")
        print("LangChain processor is ready for use!")
        print(f"Total tools available: {len(processor.tools)}")
        print("process_user_command method ready for voice assistant integration")
        
    except Exception as e:
        print(f" Error during testing: {e}")
        import traceback
        traceback.print_exc()