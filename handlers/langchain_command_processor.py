"""
LangChain-based Command Processor
This replaces your current CommandProcessor with an intelligent agent
"""


from asyncio.log import logger
import os
import threading
import json

from datetime import datetime
import time
from typing import Dict, Any
from dotenv import load_dotenv
from audio.audio_processor import clean_text_for_speech
import re
import warnings
import urllib3
import gc
from connectors.zepto_order_database import ZeptoOrderDatabase
# Suppress urllib3 warnings from Selenium WebDriver connections
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*Failed to establish a new connection.*")
# LangChain imports (install with: pip install langchain langchain-openai langchain-community langgraph)
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import Tool, StructuredTool, BaseTool
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Annotated
import operator
# Import system prompt
from handlers.system_prompt import SOFI_SYSTEM_PROMPT

# Import dynamic prompt generator
from handlers.dynamic_prompt_generator import DynamicPromptGenerator

# Import your existing connectors
from connectors.volume_control import VolumeController 
from connectors.weather_connector import handle_tool_requests
from connectors.amzon_connector import get_amazon_result
from connectors.amazon_order_tracker import get_order
from connectors.spotify_connector import SpotifyConnector
from connectors.search_engine import GeminiSearch
from connectors.telegram_bot import TelegramBot
from connectors.reminder_manager import ReminderManager
from speech.speech_recognizer import SpeechRecognizer
from connectors.bigbasket_connector import BigBasketTools
from connectors.zepto_order_automation import ZeptoScraper
from connectors.home_automation import HomeAutomation
from connectors.yt_music import MusicPlayer
from connectors.map import get_travel_time_with_traffic
import asyncio

load_dotenv()


def detect_language(text: str) -> str:
    """Detect if text is in Hindi or English"""
    # Count Devanagari characters
    devanagari_count = sum(1 for c in text if '\u0900' <= c <= '\u097F')
    # Count English characters
    english_count = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    
    if devanagari_count > english_count * 0.5:
        return 'hindi'
    return 'english'


class LangChainAgentProcessor:
    """
    LangChain-based replacement for CommandProcessor
    This intelligently decides which tools to use based on user input
    """
    
    def __init__(self, conversation_history, audio_processors, conversation_manager=None, pixel_led=None, recognizer=None, use_dynamic_prompts=True):
        """
        Initialize LangChain Agent Processor
        
        Required parameters:
        - conversation_history: List to store conversation history
        - audio_processors: Handler for speech/TTS functionality
        - pixel_led: Optional PixelLEDController for visual feedback
        - recognizer: Optional SpeechRecognizer instance (for follow-up questions)
        
        Optional parameters:
        - use_dynamic_prompts: Whether to use dynamic prompt generation (default: True)
        """
        
        # Store the handlers that are actually used
        self.audio_processors = audio_processors
        self.pixel_led = pixel_led
        self.recognizer = recognizer  # Store recognizer for follow-up questions
        self.reminder_manager = ReminderManager()
        # Optional ConversationManager instance to persist history
        self.conversation_manager = conversation_manager
        
        # Dynamic prompt configuration
        self.use_dynamic_prompts = use_dynamic_prompts
        self.prompt_generator = DynamicPromptGenerator() if use_dynamic_prompts else None
        
        # Load conversation history from manager if provided, otherwise use provided history
        if conversation_manager:
            self.conversation_history = conversation_manager.conversation_history
        else:
            self.conversation_history = conversation_history if conversation_history else []
        self.volume_controller = VolumeController()
        # Initialize connectors (same as original)
        self.spotify_connector = SpotifyConnector(None)
        if recognizer:
            self.spotify_connector.set_speech_recognizer(recognizer)

        self.search_connector = GeminiSearch()
        self.telegram_bot = TelegramBot()
        self.big_basket_connector = BigBasketTools()
        zepto_phone = os.getenv('ZEPTO_PHONE_NUMBER', '9028129764')
        # Set headless=False for Windows Firefox stability
        self.zepto_scraper = ZeptoScraper(zepto_phone, headless=False)
        self.home_automation = HomeAutomation()
        # Create a persistent event loop for Zepto in a dedicated thread
        self._zepto_loop = None
        self._zepto_thread = None
        self._setup_zepto_loop()
        
        # Initialize YouTube Music player
        self.youtube_music = MusicPlayer()
        
        # Initialize Zepto Order Database
        self.zepto_db = ZeptoOrderDatabase()
        
        # LangChain-specific setup
        self.agent_executor = None
        self.tools = []
        
        self._setup_langchain_agent()
    
    def _setup_zepto_loop(self):
        """Setup a persistent event loop for Zepto operations in a dedicated thread"""
        import threading
        import queue
        
        self._zepto_queue = queue.Queue()
        
        def run_loop():
            # Create event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._zepto_loop = loop
            
            # Keep loop running
            try:
                loop.run_forever()
            finally:
                loop.close()
        
        self._zepto_thread = threading.Thread(target=run_loop, daemon=True)
        self._zepto_thread.start()
        
        # Wait for loop to be ready
        import time
        timeout = 5
        start = time.time()
        while self._zepto_loop is None and (time.time() - start) < timeout:
            time.sleep(0.1)
    
    def _run_in_zepto_loop(self, coro, timeout=120):
        """Run coroutine in the persistent Zepto event loop"""
        import concurrent.futures
        
        if self._zepto_loop is None:
            raise RuntimeError("Zepto event loop not initialized")
        
        future = asyncio.run_coroutine_threadsafe(coro, self._zepto_loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return "Operation timed out"
        except Exception as e:
            raise e
    
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
            description="Get current weather. Use when: 'what is the weather', 'is it raining', 'temperature'. Input: city name",
            func=current_weather_function
        )
    

    def _create_travel_time_tool(self) -> Tool:
        """Get travel time and traffic information between two locations"""
        def travel_time_function(origin_destination: str) -> str:
            try:
                # Parse origin and destination from input
                parts = origin_destination.split(" to ")
                if len(parts) != 2:
                    # Try alternate format: origin | destination
                    parts = origin_destination.split("|")
                    if len(parts) != 2:
                        return "Please provide origin and destination. Format: 'origin to destination' or 'origin | destination'"
                
                origin = parts[0].strip()
                destination = parts[1].strip()
                
                result = get_travel_time_with_traffic(origin, destination)
                
                # Format the response
                response = f"Travel Information from {origin} to {destination}:\n"
                response += f"Distance: {result['distance']}\n"
                response += f"Travel time (no traffic): {result['standard_duration']}\n"
                response += f"Travel time (in traffic): {result['duration_in_traffic']}\n"
                response += f"Traffic delay: {result['traffic_delay_seconds']} seconds\n"
                response += f"Traffic impact: +{result['traffic_impact_percent']}%"
                
                return response
            except Exception as e:
                return f"Travel time error: {str(e)}"
        
        return Tool(
            name="get_travel_time",
            description="Get travel time and traffic information between two locations. Use when: 'how long to reach', 'travel time', 'distance', 'how far is', 'what's the traffic'. Input: 'origin to destination' (e.g., 'Pisoli Pune to Kondhwa Pune')",
            func=travel_time_function
        )
    
    def _create_home_automation_tool(self) -> Tool:
        """Control home automation devices"""
        def home_automation_function(command: str) -> str:
            try:
                parts = command.split("|")
                action = parts[0].lower().strip()
                
                if action == "status":
                    status = self.home_automation.get_status()
                    if status:
                        status_str = ", ".join([f"{k}: {'on' if v else 'off'}" for k, v in status.items()])
                        return f"Current device status: {status_str}"
                    else:
                        return "Unable to retrieve device status"
                
                elif action == "control":
                    if len(parts) < 2:
                        return "Please provide devices. Format: control|light:true|fan:false"
                    
                    # Parse device:value pairs from pipe-separated string
                    devices = {}
                    for i in range(1, len(parts)):
                        pair = parts[i].split(":")
                        if len(pair) == 2:
                            device_name = pair[0].strip()
                            device_value = pair[1].strip().lower()
                            # Convert string to boolean
                            devices[device_name] = device_value in ['true', '1', 'yes', 'on']
                    
                    if not devices:
                        return "No valid devices found"
                    
                    self.home_automation.send_cmd(devices)
                    return "Updated devices"
                
                else:
                    return "Home automation actions: status or control"
                    
            except Exception as e:
                return f"Home automation error: {str(e)}"
        
        return Tool(
            name="control_home_automation",
            description='Use this tool to control smart home devices (lights, fans, zero light etc). ALWAYS use for: turn on/off light, fan, or any device. Queries: turn on light, turn off fan, light on, fan off, device status, what devices are on. Format: "status" to check all device states, or "control|device_name:true|device_name:false" to set devices. Device names: light, fan, zero, etc.',
            func=home_automation_function
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
            description="Get 3-day weather forecast. Use when: 'forecast', 'will it rain tomorrow'. Input: city name",
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
            description="Get timezone and current time. Use when: 'what time is it in', 'timezone of'. Input: city name",  
            func=timezone_function
        )
    
    def _create_spotify_play_track_tool(self) -> Tool:
        """Play a specific track on Spotify"""
        def play_track_function(track_name: str) -> str:
            try:
                # Set music playing flag immediately (before async thread)
                if self.recognizer:
                    self.recognizer.set_music_playing(True)
                
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
            description="Play a song on Spotify. Use when: 'play [song]', 'put on [track]'. Input: song name",
            func=play_track_function
        )
    
    def _create_spotify_play_album_tool(self) -> Tool:
        """Play a specific album on Spotify"""
        def play_album_function(album_name: str) -> str:
            try:
                # Set music playing flag immediately (before async thread)
                if self.recognizer:
                    self.recognizer.set_music_playing(True)
                
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
            description="Play an album on Spotify. Use when: 'play album [name]'. Input: album name",
            func=play_album_function
        )
    
    def _create_spotify_play_artist_tool(self) -> Tool:
        """Play music by a specific artist on Spotify"""
        def play_artist_function(artist_name: str) -> str:
            try:
                # Set music playing flag immediately (before async thread)
                if self.recognizer:
                    self.recognizer.set_music_playing(True)
                
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
            description="Play music by an artist on Spotify. Use when: 'play [artist]', 'put on [artist] music'. Input: artist name",
            func=play_artist_function
        )
    
    def _create_spotify_control_tool(self) -> Tool:
        """Control Spotify playback (pause, resume, next)"""
        def control_function(action: str) -> str:
            try:
                action_lower = action.lower().strip()
                
                if action_lower in ['pause', 'stop']:
                    spotify_action = "stop"
                    # Set music flag to False immediately
                    if self.recognizer:
                        self.recognizer.set_music_playing(False)
                elif action_lower in ['resume', 'continue', 'play']:
                    spotify_action = "resume"
                    # Set music flag to True immediately
                    if self.recognizer:
                        self.recognizer.set_music_playing(True)
                elif action_lower in ['next', 'skip']:
                    spotify_action = "next"
                    # Music keeps playing, flag stays True
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
            description="Resume, pause, or skip Spotify playback. CRITICAL: Use when user says: 'play', 'resume', 'continue', 'pause', 'stop', 'next', 'skip'. Input format: pause|resume|next|skip (e.g., 'resume' to play music, 'pause' to stop, 'next' to skip song)",
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
            description="Search the internet for LATEST/CURRENT information. MANDATORY for: latest news, current prices, today's info, recent updates, live status. Use when: 'what's latest', 'current', 'today', 'right now', 'latest news about', 'trending'. Input: search query (e.g., 'latest Bitcoin price', 'current weather today', 'trending news')",
            func=search_function
        )
    
    def _create_amazon_single_product_tool(self) -> Tool:
        """Search Amazon for detailed information about a single product"""
        def single_product_function(query: str) -> str:
            try:
                # Sanitize query - remove any index prefixes like "1|", "2|" etc
                query = query.strip()
                if '|' in query:
                    # Remove anything before the first pipe that looks like an index
                    parts = query.split('|', 1)
                    if parts[0].strip().isdigit():
                        query = parts[1].strip()
                
                tool_request = {
                    "tool": "amazon", 
                    "action": "single_product_search",
                    "query": query
                }
                result = get_amazon_result(tool_request)
                
                # Return data directly to agent with full URL
                if isinstance(result, dict) and result.get('title'):
                    title = result.get('title', 'Unknown Product')
                    price = result.get('price', 'Price not available')
                    rating = result.get('rating', 'No rating')
                    reviews = result.get('reviews_count', 'No reviews')
                    url = result.get('url', 'N/A')
                    sales_volume = result.get('sales_volume')
                    
                    # Return formatted data directly - agent will speak naturally
                    product_data = f"""Product: {title}
                    Price: {price}
                    Rating: {rating} out of 5 stars
                    Reviews: {reviews}"""
                            
                    if sales_volume:
                        product_data += f"\nSales Volume: {sales_volume}"
                    
                    product_data += f"\nURL: {url}"
                    
                    return product_data
                elif isinstance(result, dict):
                    return "Sorry, I couldn't find detailed information about that product. Please try another search."
                return f"Amazon search result: {str(result)[:500]}"
            except Exception as e:
                return f"Sorry, I encountered an error while searching Amazon. Please try again."
        
        return Tool(
            name="search_amazon_single_product",
            description="Search Amazon for detailed information about a specific single product with price, rating, and direct product link. Use when user wants detailed info about one product. Input: product name only (e.g., 'iphone 15' NOT '1|iphone 15').",
            func=single_product_function
        )
    
    def _create_amazon_multi_product_tool(self) -> Tool:
        """Search Amazon for multiple products (comparison/browse)"""
        def multi_product_function(query: str) -> str:
            try:
                # Sanitize query - remove any index prefixes like "1|", "2|" etc
                query = query.strip()
                if '|' in query:
                    # Remove anything before the first pipe that looks like an index
                    parts = query.split('|', 1)
                    if parts[0].strip().isdigit():
                        query = parts[1].strip()
                
                tool_request = {
                    "tool": "amazon", 
                    "action": "multi_product_search",
                    "query": query,
                    "max_results": 5
                }
                result = get_amazon_result(tool_request)
                
                # Return data directly to agent with full URLs
                if isinstance(result, list) and len(result) > 0:
                    product_list = []
                    for i, product in enumerate(result[:3], 1):  # Limit to top 3 for readability
                        title = product.get('title', 'Unknown Product')
                        price = product.get('price', 'Price not available')
                        rating = product.get('rating', 'No rating')
                        reviews = product.get('reviews_count', 'No reviews')
                        url = product.get('url', 'URL not available')
                        
                        product_summary = f"Product {i}: {title}\nPrice: {price}\nRating: {rating} out of 5 stars\nReviews: {reviews}\nURL: {url}"
                        product_list.append(product_summary)
                    
                    # Return directly - agent will format naturally for speech
                    return "\n\n".join(product_list)
                else:
                    return "Sorry, I couldn't find any products matching your search. Please try a different search term."
            except Exception as e:
                return f"Sorry, I encountered an error while searching Amazon. Please try again."
        
        return Tool(
            name="search_amazon_multiple_products",
            description="Search Amazon for multiple products to compare options with prices, ratings, and direct product links. Use when user wants to see several product choices or browse options. Input: product name only (e.g., 'iphone 15' NOT '1|iphone 15').",
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
                    days = max(1, min(int(numbers[0]), 90))  # Limit 1-90 days
                
                tool_request = {
                    "tool": "amazon_order_tracking",
                    "action": "get_recent_orders", 
                    "days": days
                }
                result = get_order(tool_request)
                
                if isinstance(result, list) and result:
                    return f"Found {len(result)} orders from last {days} days: {str(result)}..."
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
                # Parse reminder input - expected format: "text|time|recurring" or "text|time" or just "text"
                parts = reminder_input.split('|')
                text = parts[0].strip()
                time_str = parts[1].strip() if len(parts) > 1 else "in 5 minutes"  # Default time
                recurring = parts[2].strip() if len(parts) > 2 else "once"  # Default: one-time reminder
                
                result = self.reminder_manager.add_reminder(text, time_str, recurring=recurring)
                return result
            except Exception as e:
                return f"Set reminder error: {str(e)}"
        
        return Tool(
            name="set_reminder",
            description="Set a reminder or daily alarm for the user. Input format: 'reminder text|time|recurring' where recurring is 'once' (default) or 'daily'. Examples: 'Call mom|in 30 minutes|once', 'Wake up|7 AM|daily', 'Meeting|tomorrow at 2 PM'. For daily alarms like morning wake-up, use 'daily'. If no time specified, defaults to 5 minutes. Daily reminders repeat every day at the same time.",
            func=set_reminder_function
        )
    
    def _create_list_reminders_tool(self) -> StructuredTool:
        """List all active reminders tool"""
        def list_reminders_function() -> str:
            try:
                action_data = {"action": "list"}
                result = self.reminder_manager.handle_reminder_action(action_data)
                return result
            except Exception as e:
                return f"List reminders error: {str(e)}"
        
        return StructuredTool.from_function(
            func=list_reminders_function,
            name="list_reminders",
            description="List all active reminders. No input required."
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
    
    def _create_check_reminders_tool(self) -> StructuredTool:
        """Check for due reminders tool"""
        def check_reminders_function() -> str:
            try:
                action_data = {"action": "check"}
                result = self.reminder_manager.handle_reminder_action(action_data)
                return result
            except Exception as e:
                return f"Check reminders error: {str(e)}"
        
        return StructuredTool.from_function(
            func=check_reminders_function,
            name="check_reminders",
            description="Check for any due reminders right now. No input required."
        )
    
    def _create_schedule_event_tool(self) -> Tool:
        """Add a scheduled event tool"""
        def schedule_event_function(event_input: str) -> str:
            """
            Schedule an event. Input format: 'time|prompt|event_id'
            Examples: '9:00 AM|Good morning!|morning', '2:30 PM|Afternoon check|afternoon'
            """
            try:
              
                
                # Parse input format: "HH:MM|prompt|event_id" or "HH:MM AM/PM|prompt|event_id"
                parts = event_input.split('|')
                if len(parts) < 3:
                    return "Invalid format. Use: 'time|prompt|event_id'. Example: '9:00 AM|Good morning!|morning'"
                
                time_str = parts[0].strip()
                prompt = parts[1].strip()
                event_id = parts[2].strip()
                
                # Parse time
                try:
                    # Handle both "9:00 AM" and "09:00" formats
                    if 'AM' in time_str.upper() or 'PM' in time_str.upper():
                        time_obj = datetime.strptime(time_str, "%I:%M %p").time()
                    else:
                        time_obj = datetime.strptime(time_str, "%H:%M").time()
                    
                    hour = time_obj.hour
                    minute = time_obj.minute
                except ValueError:
                    return f"Invalid time format: {time_str}. Use: '9:00 AM' or '09:00' (24-hour)"
                
                # Find events.json
                current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                events_file = os.path.join(current_dir, 'events.json')
                
                # Read existing events
                try:
                    if os.path.exists(events_file):
                        with open(events_file, 'r') as f:
                            data = json.load(f)
                    else:
                        data = {"events": []}
                except json.JSONDecodeError:
                    data = {"events": []}
                
                # Check if event already exists
                for event in data.get("events", []):
                    if event.get("event_id") == event_id:
                        return f"Event '{event_id}' already exists. Try a different event_id."
                
                # Add new event
                new_event = {
                    "hour": hour,
                    "minute": minute,
                    "prompt": prompt,
                    "event_id": event_id
                }
                
                data["events"].append(new_event)
                
                # Write back to file
                with open(events_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                return f"Event scheduled! '{event_id}' at {time_str} with message: '{prompt}'"
                
            except Exception as e:
                return f"Schedule event error: {str(e)}"
        
        return Tool(
            name="schedule_event",
            description="Schedule a recurring event that triggers at a specific time daily. User can say things like 'Schedule an event at 9 AM to say good morning' or 'Add reminder at 2:30 PM'. Input format: 'time|prompt|event_id'. Examples: '9:00 AM|Good morning!|morning', '2:30 PM|How is afternoon?|afternoon', '6 PM|Evening check|evening'. Time can be in 24-hour format (09:00) or 12-hour format (9:00 AM).",
            func=schedule_event_function
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
        """Control system volume using main_control from volume_control module"""
        def volume_control_function(command: str) -> str:
            try:
                from connectors.volume_control import main_control
                
                # Parse the command format: "action|step|level"
                parts = command.split("|")
                action = parts[0].lower().strip()
                step = 5
                level = None
                
                # Parse step parameter
                if len(parts) > 1 and parts[1].strip():
                    step = int(parts[1].strip())
                
                # Parse level parameter
                if len(parts) > 2 and parts[2].strip():
                    level = int(parts[2].strip())
                
                # Call main_control with parsed arguments
                result = main_control(action, step=step, level=level)
                
                # Format response for TTS
                if action == "status":
                    return f"Volume is at {result['volume']}%. Muted: {result['muted']}"
                elif action == "increase":
                    return f"Volume increased to {result}%"
                elif action == "decrease":
                    return f"Volume decreased to {result}%"
                elif action == "set":
                    return f"Volume set to {result}%"
                elif action in ["mute", "unmute"]:
                    return f"Volume {action}d successfully"
                else:
                    return "Volume command executed"
                    
            except Exception as e:
                return f"Volume control error: {str(e)}"
        
        return Tool(
            name="control_system_volume",
            description="Control system volume. Commands: 'increase', 'decrease', 'mute', 'unmute', 'set', or 'status'. Format: action|step|level (e.g., 'increase|10' or 'decrease|10' or 'set||50')",
            func=volume_control_function
        )
    
    def _zepto_ordering_tool(self) -> Tool:
        """Zepto grocery ordering tool with database tracking"""
        def zepto_function(input_str: str) -> str:
            try:
                # Parse from RIGHT to handle product names with pipes
                # Format: action|product_name|quantity|product_index
                # Example: add_product|Maccain French Fires | Crispy $ ready to cook|2|4
                
                parts = input_str.split("|")
              
                action = parts[0].lower().strip()
                
                # NEW: Check latest incomplete order from database
                if action == "get_latest":
                    latest_order = self.zepto_db.get_latest_order()
                    
                    if not latest_order:
                        return "No incomplete Zepto orders found in the database. Ready to start a fresh order!"
                    
                    # Format the order for the agent to understand and act on
                    order_id = latest_order.get('id', 'N/A')
                    status = latest_order.get('status', 'unknown')
                    current_task = latest_order.get('current_task', 'order_details')
                    items = latest_order.get('items', [])
                    total_price = latest_order.get('total_price', 0)
                    created_at = latest_order.get('created_at', 'N/A')
                    if "payment" in current_task.lower() or "checkout" in current_task.lower():
                        current_task = "order_details"
                    # Format items list
                    items_str = ', '.join(items) if items else 'No items'
                   
                    result = f"""INCOMPLETE ZEPTO ORDER FOUND:
                    Order ID: {order_id}
                    Status: {status}
                    Current Task: {current_task}
                    Items: {items_str}
                    Total Price: ₹{total_price}
                    Created: {created_at}

                    DO NOT START FRESH. This order must be resumed. Ask user: "I found your incomplete order with {items_str} at ₹{total_price}. Should I continue from where we left off?"

                    If user says YES: Call zepto_ordering with action "{current_task}" to resume
                    If user says NO: Call zepto_ordering with "clear_cart" to start fresh"""
                    return result

                quantity = 1
                product_index = 0
                product = ""
                
                if len(parts) >= 4:
                    last_part = parts[-1].strip()
                    if last_part.isdigit():
                        product_index = int(last_part)
                    else:
                        pass
                    
                    second_last = parts[-2].strip()
                    if second_last.isdigit():
                        quantity = int(second_last)
                    else:
                        pass
                    
                    product = "|".join(parts[1:-2]).strip()
                    
                elif len(parts) >= 3:
                    last_part = parts[-1].strip()
                    if last_part.isdigit():
                        quantity = int(last_part)
                    else:
                        pass
                    
                    product = "|".join(parts[1:-1]).strip()
                    
                elif len(parts) >= 2:
                    product = parts[1].strip()
                
                # Validate for add_product action
                if action == "add_product":
                    if not product:
                        return "Error: Product name is empty. Format: add_product|product_name|quantity|index"
                    if quantity < 1:
                        return f"Error: Invalid quantity {quantity}. Must be >= 1"
                    if product_index < 0:
                        return f"Error: Invalid product index {product_index}. Must be >= 0"
                
                if action == "login":
                    self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    # Save initial order state
                    order_id = self.zepto_db.save_order(status="pending", current_task="login", items=[], total_price=0.0, error=False)
                    return "Zepto login initiated."
                elif action == "clear_cart":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    result = self._run_in_zepto_loop(self.zepto_scraper.clear_cart())
                    return f"Zepto clear cart result: {result}"
                elif action == "search":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    product_list = self._run_in_zepto_loop(self.zepto_scraper.search_and_extract_products(product))
                    # Update order task to searching
                    latest_order = self.zepto_db.get_latest_order()
                    if latest_order:
                        self.zepto_db.update_task(latest_order['id'], "searching", f"Searched for: {product}")
                    else:
                        order_id = self.zepto_db.save_order(status="pending", current_task="searching", items=[], error=False, context=f"Searched for: {product}")
                    return f"Zepto search results: {product_list}"
                elif action == "add_product":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    result = self._run_in_zepto_loop(self.zepto_scraper.add_product_to_cart(product, quantity, product_index))
                    
                    # Update order with new item
                    latest_order = self.zepto_db.get_latest_order()
                    if latest_order:
                        items = latest_order.get('items', [])
                        # Add or update item in list
                        item_str = f"{product} x{quantity}"
                        if item_str not in items:
                            items.append(item_str)
                        self.zepto_db.update_items(latest_order['id'], items)
                        self.zepto_db.update_task(latest_order['id'], "item_added", f"Added: {product} x{quantity}")
                    else:
                        order_id = self.zepto_db.save_order(status="pending", current_task="item_added", items=[f"{product} x{quantity}"], error=False, context=f"Added: {product} x{quantity}")
                    
                    return f"Zepto add product result: {result}"
                elif action == "order_details":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    order_info = self._run_in_zepto_loop(self.zepto_scraper.get_order_details())
                    return f"Zepto order details: {order_info}"
                elif action == "checkout":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    payment_result = self._run_in_zepto_loop(self.zepto_scraper.checkout())
                    
                    # Update order status to payment
                    latest_order = self.zepto_db.get_latest_order()
                    if latest_order:
                        self.zepto_db.update_task(latest_order['id'], "payment_confirmation", "Checkout initiated")
                    
                    # Add confirmation prompt for COD payment
                    if payment_result.get('cod_available'):
                        methods_str = ', '.join(payment_result.get('payment_methods', ['Cash on Delivery']))
                        return (f"Payment page is ready. Cash on Delivery (COD) has been selected. "
                                f"Payment methods available: {methods_str}. "
                                f"Do you want to confirm and proceed with Cash on Delivery payment?")
                    else:
                        return f"Zepto payment result: {payment_result}"
                elif action == "place_order":
                    result = self._run_in_zepto_loop(self.zepto_scraper.click_proceed_final())
                    if result and result.get("status") == "clicked":
                        # Update order to completed
                        latest_order = self.zepto_db.get_latest_order()
                        if latest_order:
                            self.zepto_db.update_status(latest_order['id'], "completed")
                            self.zepto_db.update_task(latest_order['id'], "order_placed", "Order successfully placed")
                        return "Zepto order placed successfully."
                    else:
                        # Set error flag
                        latest_order = self.zepto_db.get_latest_order()
                        if latest_order:
                            self.zepto_db.set_error(latest_order['id'], True, "Failed to place order")
                    self._run_in_zepto_loop(self.zepto_scraper.cleanup())
                elif action == "cleanup":
                    self._run_in_zepto_loop(self.zepto_scraper.cleanup())
                    return "Zepto browser closed."
                else:
                    return f"Unknown action: {action}. Supported: login, search, add_product, order_details, checkout, place_order, cleanup"
            except Exception as e:
                # Set error flag when exception occurs
                latest_order = self.zepto_db.get_latest_order()
                if latest_order:
                    self.zepto_db.set_error(latest_order['id'], True, str(e))
                return f"Zepto tool error: {str(e)}"
        
        return Tool(
            name="zepto_ordering_tool",
            description="Zepto grocery ordering and database check. ACTIONS: 1) get_latest - check for incomplete order in database (CALL THIS FIRST), 2) login, 3) clear_cart, 4) search|product_name, 5) add_product|product_name|quantity|index, 6) order_details, 7) checkout, 8) place_order, 9) cleanup. Format: 'action|product|quantity|index'. ALWAYS use get_latest first when user mentions Zepto/order. ALWAYS ask user confirmation before place_order.",
            func=zepto_function
        )

    def _create_zepto_order_history_tool(self) -> Tool:
        """Get recent Zepto order history"""
        def order_history_function(max_orders: str = "3") -> str:
            try:
                # Parse max_orders
                try:
                    max_orders_int = int(max_orders.strip())
                except:
                    max_orders_int = 3
                
                # Get order history
                orders = self._run_in_zepto_loop(
                    self.zepto_scraper.get_order_history(max_orders=max_orders_int)
                )
                
                if not orders:
                    return "No orders found in your Zepto order history."
                
                # Format response
                result = f"Found {len(orders)} recent orders:\n"
                for order in orders:
                    result += f"\n{order['order_number']}. {order['status']} - {order['amount']}"
                    result += f"\n   Date: {order['date']}"
                    result += f"\n   Items: {order['item_count']}"
                    result += f"\n   Order ID: {order['order_id'][:16]}..."
                
                return result
            except Exception as e:
                return f"Failed to get order history: {str(e)}"
        
        return Tool(
            name="zepto_order_history",
            description="Get recent Zepto order history. Input: number of orders to fetch (default 3). Returns list of recent orders with status, date, amount, and item count.",
            func=order_history_function
        )
    
    def _create_zepto_order_again_tool(self) -> Tool:
        """Reorder a previous Zepto order"""
        def order_again_function(order_index: str = "0") -> str:
            try:
                # Parse order index
                try:
                    index = int(order_index.strip())
                except:
                    return "Invalid order index. Please provide a number (0 for most recent order)."
                
                # Reorder
                success = self._run_in_zepto_loop(
                    self.zepto_scraper.order_again(order_index=index)
                )
                
                if success:
                    return f"Successfully added order {index} to cart! Use order_details to see cart contents, then checkout to proceed."
                else:
                    return f"Failed to reorder. Please check if order index {index} exists using order_history first."
            except Exception as e:
                return f"Failed to reorder: {str(e)}"
        
        return Tool(
            name="zepto_order_again",
            description="Reorder a previous Zepto order. Input: order index (0 for most recent, 1 for second most recent, etc.). This adds all items from that order to your cart.",
            func=order_again_function
        )
    
    def _create_zepto_track_orders_tool(self) -> Tool:
        """Track recent orders with optional detailed info"""
        def track_orders_function(params: str = "3|none") -> str:
            try:
                # Parse params: "max_orders|detail_index" or just "max_orders"
                parts = params.split('|')
                max_orders = int(parts[0].strip()) if parts[0].strip().isdigit() else 3
                detail_index = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else None
                
                # Track orders
                result = self._run_in_zepto_loop(
                    self.zepto_scraper.track_recent_orders(
                        max_orders=max_orders,
                        get_details_for_index=detail_index
                    )
                )
                
                if result['total_orders'] == 0:
                    return "No orders found."
                
                # Format response
                response = f"Found {result['total_orders']} orders:\n"
                for order in result['orders']:
                    response += f"\n[{order['order_number']-1}] {order['status']} - {order['amount']}"
                    response += f"\n    {order['date']} | {order['item_count']} items"
                
                # Add detailed info if requested
                if result['detailed_order']:
                    details = result['detailed_order']
                    response += f"\n\nDetailed info for order {detail_index}:"
                    response += f"\n  Status: {details.get('status', 'N/A')}"
                    response += f"\n  Amount: {details.get('total_amount', 'N/A')}"
                    response += f"\n  Order Date: {details.get('order_date', 'N/A')}"
                    if details.get('arriving_in'):
                        response += f"\n  Arriving in: {details['arriving_in']}"
                
                return response
            except Exception as e:
                return f"Failed to track orders: {str(e)}"
        
        return Tool(
            name="zepto_track_orders",
            description="Track recent Zepto orders with optional detailed info. Input format: 'max_orders|detail_index' (e.g., '5|0' to get 5 orders with details for first one) or just 'max_orders' (e.g., '3'). Returns order summaries with status, date, amount. If detail_index provided, includes tracking info for that order.",
            func=track_orders_function
        )

    def _create_youtube_music_play_song_tool(self) -> Tool:
        """Play a specific song on YouTube Music"""
        def play_song_function(song_name: str) -> str:
            try:
                # Set music playing flag immediately
                if self.recognizer:
                    self.recognizer.set_music_playing(True)
                
                def yt_music_thread_func():
                    self.youtube_music.play(song_name)
                
                # Run YouTube Music in separate thread to avoid audio conflicts
                yt_thread = threading.Thread(target=yt_music_thread_func, daemon=True)
                yt_thread.start()
                
                return f"Starting song playback: {song_name}"
            except Exception as e:
                return f"YouTube Music song error: {str(e)}"
        
        return Tool(
            name="play_youtube_music_song",
            description="Play a specific song on YouTube Music. Use when: 'play [song name]', 'put on [song]'. Input: song name (e.g., 'Bohemian Rhapsody')",
            func=play_song_function
        )
    
    def _create_youtube_music_play_playlist_tool(self) -> Tool:
        """Play a YouTube Music playlist"""
        def play_playlist_function(playlist_name: str) -> str:
            try:
                # Set music playing flag immediately
                if self.recognizer:
                    self.recognizer.set_music_playing(True)
                
                def yt_playlist_thread_func():
                    self.youtube_music.play_playlist(playlist_name)
                
                # Run in separate thread
                yt_thread = threading.Thread(target=yt_playlist_thread_func, daemon=True)
                yt_thread.start()
                
                return f"Starting playlist: {playlist_name}"
            except Exception as e:
                return f"YouTube Music playlist error: {str(e)}"
        
        return Tool(
            name="play_youtube_music_playlist",
            description="Play a YouTube Music playlist. Use when: 'play playlist [name]', 'play [playlist theme]'. Input: playlist name or theme (e.g., 'romantic songs', 'workout', 'chill vibes')",
            func=play_playlist_function
        )
    
    def _create_youtube_music_play_artist_tool(self) -> Tool:
        """Play all tracks by a specific artist on YouTube Music"""
        def play_artist_function(artist_name: str) -> str:
            try:
                # Set music playing flag immediately
                if self.recognizer:
                    self.recognizer.set_music_playing(True)
                
                def yt_artist_thread_func():
                    self.youtube_music.play_all_artist_tracks(artist_name)
                
                # Run in separate thread
                yt_thread = threading.Thread(target=yt_artist_thread_func, daemon=True)
                yt_thread.start()
                
                return f"Starting artist playlist: {artist_name}"
            except Exception as e:
                return f"YouTube Music artist error: {str(e)}"
        
        return Tool(
            name="play_youtube_music_artist",
            description="Play all available songs by an artist on YouTube Music. Use when: 'play [artist name]', 'put on [artist] music', 'play songs by [artist]'. Input: artist name (e.g., 'The Beatles', 'Taylor Swift')",
            func=play_artist_function
        )
    
    def _create_youtube_music_control_tool(self) -> Tool:
        """Control YouTube Music playback"""
        def control_function(action: str) -> str:
            try:
                action_lower = action.lower().strip()
                
                if action_lower in ['pause', 'stop']:
                    self.youtube_music.pause()
                    # Set music flag to False
                    if self.recognizer:
                        self.recognizer.set_music_playing(False)
                    return "YouTube Music paused"
                
                elif action_lower in ['resume', 'continue', 'play']:
                    self.youtube_music.resume()
                    # Set music flag to True
                    if self.recognizer:
                        self.recognizer.set_music_playing(True)
                    return "YouTube Music resumed"
                
                elif action_lower in ['next', 'skip']:
                    self.youtube_music.next()
                    return "Skipped to next track"
                
                elif action_lower in ['previous', 'prev', 'back']:
                    self.youtube_music.previous()
                    return "Skipped to previous track"
                
                else:
                    return "Use: pause, stop, resume, next, previous"
                
            except Exception as e:
                return f"YouTube Music control error: {str(e)}"
        
        return Tool(
            name="control_youtube_music_playback",
            description="Control YouTube Music playback. Actions: pause, stop, resume, next, previous. Use when: 'pause', 'stop', 'play', 'resume', 'next song', 'skip', 'previous'. Input: action name (e.g., 'pause', 'stop', 'next', 'resume')",
            func=control_function
        )

    def _create_follow_up_question_tool(self) -> Tool:
        """Tool for the AI to ask follow-up questions and continue listening"""
        def ask_follow_up_function(input_text: str) -> str:
            try:
                # Parse input - format: "preamble|question" or just "question"
                # Preamble is optional context/information to speak before asking the question
                parts = input_text.split('|', 1)
                if len(parts) == 2:
                    preamble = parts[0].strip()
                    question = parts[1].strip()
                else:
                    preamble = None
                    question = input_text.strip()
                
                # Set LED to speaking state
                if self.pixel_led:
                    self.pixel_led.set_speaking()
                
                # If there's a preamble, speak it first
                if preamble:
                    self.audio_processors.speak(preamble)
                    # Wait for preamble to complete
                    while hasattr(self.audio_processors, 'is_speaking') and self.audio_processors.is_speaking:
                        time.sleep(0.1)
                    time.sleep(0.3)  # Brief pause between preamble and question
                
                # Speak the follow-up question (LED controlled in audio_processor)
                self.audio_processors.speak(question)
                
                # Wait for speech to complete using is_speaking flag
                while hasattr(self.audio_processors, 'is_speaking') and self.audio_processors.is_speaking:
                    time.sleep(0.1)
                
                time.sleep(0.5)  # Longer buffer to ensure TTS cleanup
                
                # Set LED to listening state
                if self.pixel_led:
                    self.pixel_led.set_listening()
                
                # Now listen for follow-up response
                # Use existing recognizer (with Spotify connector and Google Cloud v2 config)
                # If no recognizer provided, create a basic one
                if self.recognizer:
                    recognizer = self.recognizer
                else:
                    recognizer = SpeechRecognizer(self.audio_processors)

                self.audio_processors.play_beep_sound()
                time.sleep(0.2)
                
                # Listen with longer timeout for follow-up
                # Music detection happens inside listen_for_command, which will reduce timeout to 5s if music is playing
                follow_up_command = recognizer.listen_for_command(is_follow_up=True, timeout=20, max_retries=0)
                
                if follow_up_command:
                    # Return the response in a way that makes it clear this is answering the question
                    return f"User's answer to your question: '{follow_up_command}'. Now complete the original task based on this answer without searching again."
                else:
                    
                    return "User did not respond to the question. Proceed with default action or inform user."
                    
            except Exception as e:
                return f"Follow-up error: {str(e)}"
        
        return Tool(
            name="ask_follow_up_question",
            description="MANDATORY tool when you need to ask ANY question or need clarification from user. Format: 'information to speak first|your question' or just 'your question'. Use the pipe separator to provide context/information BEFORE asking the question. Example: 'Three products found: Product A ₹100, Product B ₹200, Product C ₹300|Which one would you like to purchase?' This will speak the product info FIRST, then ask the question. If your response would have a question mark '?', you MUST use this tool. NEVER ask questions in your text response.",
            func=ask_follow_up_function
        )
    


    def _setup_langchain_agent(self):
        """Setup the LangChain agent with tools and memory"""
        
        # Create tools from your existing connectors
        self.tools = [
            self._create_current_weather_tool(),
            self._create_weather_forecast_tool(),
            self._create_timezone_tool(),
            self._create_home_automation_tool(),
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
            self._create_schedule_event_tool(),
            self._create_telegram_message_tool(),
            self._create_telegram_photo_tool(),
            self._create_telegram_document_tool(),
            self._create_telegram_video_tool(),
            self._create_volume_control_tool(),
            self._create_youtube_music_play_song_tool(),
            self._create_youtube_music_play_playlist_tool(),
            self._create_youtube_music_play_artist_tool(),
            self._create_youtube_music_control_tool(),
            self._create_follow_up_question_tool(),
            self._zepto_ordering_tool(),
            self._create_zepto_order_history_tool(),
            self._create_zepto_order_again_tool(),
            self._create_travel_time_tool(),
            self._create_zepto_track_orders_tool()
        ]
        
        # Log available tools
        if self.use_dynamic_prompts:
           print(f"✨ Dynamic Prompts ENABLED - Available Tools: {[t.name for t in self.tools]}")
        else:
            print(f"📘 System Prompt Mode - Available Tools: {[t.name for t in self.tools]}")
        
        # Initialize LLM
        llm = ChatOpenAI(
            model="gpt-4.1-mini",
            temperature=1,  
            openai_api_key=os.getenv('OPENAI_API_KEY'),
        )
        
        # Setup memory for conversation context using simple message list
        class WindowedChatHistory(BaseChatMessageHistory):
            """Simple in-memory chat history with windowing (keeps last k exchanges)"""
            def __init__(self, k: int = 10):
                self.messages: list[BaseMessage] = []
                self.k = k
            
            @property
            def messages_windowed(self):
                """Return only last k*2 messages (k exchanges = k*2 messages)"""
                return self.messages[-self.k*2:] if len(self.messages) > self.k*2 else self.messages
            
            def add_message(self, message: BaseMessage) -> None:
                self.messages.append(message)
            
            def clear(self) -> None:
                self.messages = []
        
        memory_interface = WindowedChatHistory(k=10)
        
        # Use the system prompt from system_prompt.py
        system_prompt = SOFI_SYSTEM_PROMPT
        
        # Setup LangGraph agent (modern approach for LangChain v1.2.7+)
        # Define the agent state
        class AgentState(TypedDict):
            messages: Annotated[list[BaseMessage], operator.add]
        
        # Create the LLM with tool binding
        tool_list = self.tools
        
        # Build the agent graph
        workflow = StateGraph(AgentState)
        
        # Define the agent node
        def agent_node(state: AgentState):
            # Create prompt with system message
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
            ])
            
            chain = prompt | llm.bind_tools(tool_list)
            result = chain.invoke({"messages": state["messages"]})
            return {"messages": [result]}
        
        # Add nodes to graph
        workflow.add_node("agent", agent_node)
        
        # Add tool node for tool calls
        tools_node = ToolNode(tool_list)
        workflow.add_node("tools", tools_node)
        
        # Define routing logic
        def route_tools(state: AgentState):
            if isinstance(state["messages"][-1], AIMessage):
                if hasattr(state["messages"][-1], "tool_calls") and state["messages"][-1].tool_calls:
                    return "tools"
            return END
        
        # Add edges
        workflow.add_conditional_edges("agent", route_tools, {"tools": "tools", END: END})
        workflow.add_edge("tools", "agent")
        workflow.set_entry_point("agent")
        
        # Compile the graph
        self.agent_executor = workflow.compile()
    
    def _create_focused_agent_executor(self, user_command: str):
        """Create a focused agent executor with custom prompt and filtered tools"""
        if not self.use_dynamic_prompts:
            return self.agent_executor
        
        try:
            custom_prompt, tool_names = self.prompt_generator.generate_custom_prompt(user_command)
            filtered_tools = self.prompt_generator.create_filtered_tool_list(self.tools, tool_names)
            
            print(f"🎯 Dynamic Prompt Active for: '{user_command}'")
            print(f"📋 Requested Tools: {tool_names}")
            print(f"✅ Filtered Tools: {[t.name for t in filtered_tools]}")
            
            llm = ChatOpenAI(model="gpt-4.1-mini", temperature=1, openai_api_key=os.getenv('OPENAI_API_KEY'))
            
            class AgentState(TypedDict):
                messages: Annotated[list[BaseMessage], operator.add]
            
            def agent_node(state: AgentState):
                prompt = ChatPromptTemplate.from_messages([
                    ("system", custom_prompt),
                    MessagesPlaceholder(variable_name="messages"),
                ])
                chain = prompt | llm.bind_tools(filtered_tools)
                return {"messages": [chain.invoke({"messages": state["messages"]})]}
            
            def route_tools(state: AgentState):
                msg = state["messages"][-1]
                if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                    return "tools"
                return END
            
            workflow = StateGraph(AgentState)
            workflow.add_node("agent", agent_node)
            workflow.add_node("tools", ToolNode(filtered_tools))
            workflow.add_conditional_edges("agent", route_tools, {"tools": "tools", END: END})
            workflow.add_edge("tools", "agent")
            workflow.set_entry_point("agent")
            
            return workflow.compile()
        except Exception:
            return self.agent_executor

        
    def process_user_command(self, user_command: str):
        """
        Main method that replaces your original process_user_command
        Now uses intelligent agent instead of manual tool selection
        Includes follow-up conversation support and conversation history awareness
        
        Returns:
            dict: Contains 'response' (full response) and 'tts_text' (cleaned for speech)
            or None if command was exit
        """
        
        # Check for exit commands (same as original)
        if any(word in user_command.lower() for word in ["exit", "quit", "goodbye", "bye"]):
            # Speak goodbye (LED controlled in audio_processor)
            self.audio_processors.speak("Goodbye!")
            return None
        
        try:
            # Set LED to processing/thinking state (blinking)
            if self.pixel_led:
                self.pixel_led.set_processing()
            
            # Build message history for agent context (keep last 10 user-assistant exchanges)
            messages = []
            
            # Add previous conversation context (last 20 messages = 10 exchanges)
            for hist_entry in self.conversation_history[-20:]:
                if hist_entry["role"] == "user":
                    messages.append(HumanMessage(content=hist_entry["content"]))
                elif hist_entry["role"] == "assistant":
                    messages.append(AIMessage(content=hist_entry["content"]))
            
            # Add current user message
            user_message = HumanMessage(content=user_command)
            messages.append(user_message)
            
            # Get the appropriate agent executor (dynamic or static)
            agent_executor = self._create_focused_agent_executor(user_command) if self.use_dynamic_prompts else self.agent_executor
            
            # Invoke the agent with full context
            result = agent_executor.invoke({"messages": messages})
            
            # Extract the response from the final message
            final_message = result["messages"][-1]
            response = final_message.content if isinstance(final_message, AIMessage) else str(final_message)
            
            # Extract URLs from response (especially for Amazon products)
            urls = re.findall(r'https?://\S+', response)
            # Remove duplicates while preserving order and clean up URLs
            seen_urls = set()
            unique_urls = []
            for url in urls:
                # Clean up URLs (remove trailing punctuation)
                clean_url = url.rstrip('.,;:)}"\'')
                if clean_url not in seen_urls:
                    seen_urls.add(clean_url)
                    unique_urls.append(clean_url)
            
            # Add to conversation history with URLs if found
            self.conversation_history.append({"role": "user", "content": user_command})
            assistant_entry = {"role": "assistant", "content": response}
            if unique_urls:
                assistant_entry["urls"] = unique_urls
            self.conversation_history.append(assistant_entry)
            
            # Persist conversation history if a ConversationManager is provided
            if getattr(self, 'conversation_manager', None):
                try:
                    self.conversation_manager.conversation_history = self.conversation_history
                    self.conversation_manager.save_conversation_history()
                except Exception:
                    pass
            

            used_follow_up = False
            for msg in result.get("messages", []):
                if hasattr(msg, 'tool_calls'):
                    for tool_call in getattr(msg, 'tool_calls', []):
                        if hasattr(tool_call, 'name') and tool_call.name == 'ask_follow_up_question':
                            used_follow_up = True
                            break
            
            # Only speak if ask_follow_up_question wasn't used
            if not used_follow_up:
                try:
                    tts_text = clean_text_for_speech(response)
                except Exception:
                    tts_text = response
                self.audio_processors.speak(tts_text)
            else:
                tts_text = response
            
            # Explicitly clean up memory after agent processing
            gc.collect()
            
            # Return response for external handlers (e.g., Telegram)
            return {
                "response": response,
                "tts_text": tts_text,
                "urls": unique_urls
            }
            
        except Exception as e:
            error_msg = f"Sorry, I encountered an error: {str(e)}"
            self.audio_processors.speak(error_msg)
            # Clean up memory after error
            gc.collect()
            return {
                "response": error_msg,
                "tts_text": error_msg,
                "urls": []
            }
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Get information about the agent's current state"""
        return {
            "tools_count": len(self.tools),
            "agent_active": self.agent_executor is not None,
            "tool_names": [tool.name for tool in self.tools] if self.tools else []
        }



if __name__ == "__main__":
    pass