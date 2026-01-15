"""
LangChain-based Command Processor
This replaces your current CommandProcessor with an intelligent agent
"""


import os
import threading
import time
import speech_recognition as sr
from typing import Dict, Any
from dotenv import load_dotenv
from audio.audio_processor import clean_text_for_speech
import re
import warnings
import urllib3
import gc
import json
# Suppress urllib3 warnings from Selenium WebDriver connections
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*Failed to establish a new connection.*")

# LangChain imports
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import Tool, StructuredTool
from langchain.agents import create_agent
from pydantic import BaseModel, Field

# LangGraph imports for multi-agent routing
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import operator

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


# LangGraph State Definition
class AgentState(TypedDict):
    """State for multi-agent routing system with shared data"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_input: str
    next_agent: str  # Which agent to route to (or 'END' to finish)
    final_response: str
    # Shared data between agents (can store anything: product_details, search_results, etc.)
    shared_context: dict
    requires_handoff: bool  # Flag if agent needs to hand off to another


class LangChainAgentProcessor:
    """
    LangChain-based replacement for CommandProcessor
    This intelligently decides which tools to use based on user input
    """
    
    def __init__(self, conversation_history, audio_processors, conversation_manager=None, pixel_led=None, recognizer=None):
        """
        Initialize LangChain Agent Processor
        
        Required parameters:
        - conversation_history: List to store conversation history
        - audio_processors: Handler for speech/TTS functionality
        - pixel_led: Optional PixelLEDController for visual feedback
        - recognizer: Optional SpeechRecognizer instance (for follow-up questions)
        """
        
        # Store the handlers that are actually used
        self.conversation_history = conversation_history
        self.audio_processors = audio_processors
        self.pixel_led = pixel_led
        self.recognizer = recognizer  # Store recognizer for follow-up questions
        self.reminder_manager = ReminderManager()
        # Optional ConversationManager instance to persist history
        self.conversation_manager = conversation_manager
        self.volume_controller = VolumeController()
        # Initialize connectors (same as original)
        self.spotify_connector = SpotifyConnector(None)
        self.search_connector = GeminiSearch()
        self.telegram_bot = TelegramBot()
        self.big_basket_connector = BigBasketTools()
        zepto_phone = os.getenv('ZEPTO_PHONE_NUMBER', '9028129764')
        # Set headless=False for Windows Firefox stability
        self.zepto_scraper = ZeptoScraper(zepto_phone, headless=True)
        self.home_automation = HomeAutomation()
        # Create a persistent event loop for Zepto in a dedicated thread
        self._zepto_loop = None
        self._zepto_thread = None
        self._setup_zepto_loop()
        
        # Persistent state file path
        self.state_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'agent_state.json')
        
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
                print(f"Amazon single product tool error: {e}")
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
                print(f"Amazon multi-product tool error: {e}")
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
                
                # Handle different return types
                if result is False or result is None:
                    # No orders found or scraping failed
                    return f"No orders found from the last {days} days."
                elif isinstance(result, list) and result:
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
            description="""Send a text message via Telegram to the user's mobile. Use this when user asks to 'send', 'share', or 'forward' something to their phone/mobile/telegram. 
            Input should be the complete message text including any URLs, product details, or information to send. 
            ALWAYS call this tool when user wants to send something - don't just say you'll send it.""",
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
        """Zepto grocery ordering tool (placeholder)"""
        def zepto_function(input_str: str) -> str:
            try:
                # Parse from RIGHT to handle product names with pipes
                # Format: action|product_name|quantity|product_index
                # Example: add_product|Maccain French Fires | Crispy $ ready to cook|2|4
                
                parts = input_str.split("|")
              
                action = parts[0].lower().strip()

                quantity = 1
                product_index = 0
                product = ""
                
                if len(parts) >= 4:
                    # Last part is product_index
                    last_part = parts[-1].strip()
                    if last_part.isdigit():
                        product_index = int(last_part)
                        print(f"[ZEPTO DEBUG] Product index from last part: {product_index}")
                    else:
                        print(f"[ZEPTO DEBUG] Warning: Last part '{last_part}' is not numeric, using default 0")
                    
                    # Second to last is quantity
                    second_last = parts[-2].strip()
                    if second_last.isdigit():
                        quantity = int(second_last)
                        print(f"[ZEPTO DEBUG] Quantity from 2nd-last part: {quantity}")
                    else:
                        print(f"[ZEPTO DEBUG] Warning: 2nd-last part '{second_last}' is not numeric, using default 1")
                    
                    # Everything in between is product name (can contain pipes)
                    product = "|".join(parts[1:-2]).strip()
                    print(f"[ZEPTO DEBUG] Product name from middle parts: '{product}'")
                    
                elif len(parts) >= 3:
                    # Could be: action|product|quantity
                    last_part = parts[-1].strip()
                    if last_part.isdigit():
                        quantity = int(last_part)
                        print(f"[ZEPTO DEBUG] Quantity: {quantity}")
                    else:
                        print(f"[ZEPTO DEBUG] Warning: Last part not numeric: '{last_part}'")
                    
                    product = "|".join(parts[1:-1]).strip()
                    print(f"[ZEPTO DEBUG] Product name: '{product}'")
                    
                elif len(parts) >= 2:
                    product = parts[1].strip()
                    print(f"[ZEPTO DEBUG] Product name only: '{product}'")
                
                # Validate for add_product action
                if action == "add_product":
                    if not product:
                        return "Error: Product name is empty. Format: add_product|product_name|quantity|index"
                    if quantity < 1:
                        return f"Error: Invalid quantity {quantity}. Must be >= 1"
                    if product_index < 0:
                        return f"Error: Invalid product index {product_index}. Must be >= 0"
                    print(f"[ZEPTO DEBUG] Validation passed. Product='{product}', Qty={quantity}, Index={product_index}")
                
                if action == "login":
                    self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    return "Zepto login initiated."
                if action == "clear_cart":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        print("Not logged in - try logging in first.")
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    result = self._run_in_zepto_loop(self.zepto_scraper.clear_cart())
                    return f"Zepto clear cart result: {result}"
                elif action == "search":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        print("Not logged in - try logging in first.")
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    product_list = self._run_in_zepto_loop(self.zepto_scraper.search_and_extract_products(product))
                    return f"Zepto search results: {product_list}"
                elif action == "add_product":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        print("Not logged in - try logging in first.")
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    print(f"[ZEPTO DEBUG] Calling add_product_to_cart with: product='{product}', quantity={quantity}, index={product_index}")
                    result = self._run_in_zepto_loop(self.zepto_scraper.add_product_to_cart(product, quantity, product_index))
                    return f"Zepto add product result: {result}"
                elif action == "order_details":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        print("Not logged in - try logging in first.")
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    order_info = self._run_in_zepto_loop(self.zepto_scraper.get_order_details())
                    return f"Zepto order details: {order_info}"
                elif action == "checkout":
                    if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                        print("Not logged in - try logging in first.")
                        self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                    payment_result = self._run_in_zepto_loop(self.zepto_scraper.checkout())
                    
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
                        print("Order placed successfully.") 
                        return "Zepto order placed successfully."
                    self._run_in_zepto_loop(self.zepto_scraper.cleanup())
                elif action == "cleanup":
                    self._run_in_zepto_loop(self.zepto_scraper.cleanup())
                    return "Zepto browser closed."
                else:
                    return f"Unknown action: {action}. Supported: login, search, add_product, order_details, checkout, place_order, cleanup"
            except Exception as e:
                print(f"[ZEPTO ERROR] {str(e)}")
                return f"Zepto tool error: {str(e)}"
        
        return Tool(
            name="zepto_ordering_tool",
            description="Zepto grocery shopping. Workflow: 1) login 2)clear_cart 3)search|product_name 4) add_product|product_name|quantity|index 5) order_details 6) checkout (auto-selects COD) 7) ask confirmation 8) place_order 9) cleanup. Format: 'action|product|quantity|index'. ALWAYS ask user confirmation before place_order using ask_follow_up_question tool.",
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
                
                # Ensure logged in
                if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                    print("Not logged in - logging in first.")
                    self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                
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
                
                # Ensure logged in
                if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                    print("Not logged in - logging in first.")
                    self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                
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
                
                # Ensure logged in
                if not self._run_in_zepto_loop(self.zepto_scraper.is_logged_in()):
                    print("Not logged in - logging in first.")
                    self._run_in_zepto_loop(self.zepto_scraper.setup_browser())
                
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


    def _create_follow_up_question_tool(self) -> Tool:
        """Tool for the AI to ask follow-up questions and continue listening"""
        def ask_follow_up_function(question: str) -> str:
            try:
                # Speak the follow-up question (LED controlled in audio_processor)
                self.audio_processors.speak(question)
                
                # Wait for speech to complete using is_speaking flag
                print("Waiting for speech to complete...")
                while hasattr(self.audio_processors, 'is_speaking') and self.audio_processors.is_speaking:
                    time.sleep(0.1)
                
                print("Speech completed, ready for follow-up...")
                time.sleep(0.5)  # Longer buffer to ensure TTS cleanup
                
                # Now listen for follow-up response
                print(f"AI asked: {question}")
                print("Now listening for follow-up response...")
                
                # Create recognizer with better microphone handling
                recognizer = SpeechRecognizer(self.audio_processors)

                self.audio_processors.play_beep_sound()
                time.sleep(0.2)
                
                # Listen with longer timeout for follow-up
                follow_up_command = recognizer.listen_for_command(is_follow_up=True, timeout=20, max_retries=1)
                
                if follow_up_command:
                    print(f"Received follow-up response: '{follow_up_command}'")
                    
                    # Use router LLM to analyze if this needs re-routing
                    router_analysis = f"""Analyze this user response to determine if it's a simple answer or a new command:

USER RESPONSE: "{follow_up_command}"

Is this:
A) A simple answer (product choice like "first one"/"third"/"boat", confirmation like "yes"/"no", quantity, etc.)
B) A new command requiring different capabilities (send to telegram, search something, play music, etc.)

Respond with only: SIMPLE_ANSWER or NEW_COMMAND"""
                    
                    analysis_result = self.router_llm.invoke([HumanMessage(content=router_analysis)])
                    decision = analysis_result.content.strip().upper()
                    
                    print(f"[FOLLOW-UP] Router analysis: {decision}")
                    
                    if "NEW_COMMAND" in decision:
                        # This is a new command - re-process through main workflow
                        print(f"[FOLLOW-UP] Detected new command, re-routing through LangGraph")
                        try:
                            # Process through main workflow
                            self.process_user_command(follow_up_command)
                            return "Follow-up command was processed successfully."
                        except Exception as e:
                            return f"Error processing follow-up command: {str(e)}"
                    else:
                        # Simple answer - return to agent
                        return f"User's answer: '{follow_up_command}'. Now complete the task based on this answer."
                else:
                    return "No follow-up response received"
                    
            except Exception as e:
                return f"Follow-up error: {str(e)}"
        
        return Tool(
            name="ask_follow_up_question",
            description="Ask clarifying questions when needed: volume direction, device selection, product/quantity choice, confirmation, payment method, time setup. Use for any ambiguous user input. Format: natural question text.",
            func=ask_follow_up_function
        )
    
        


    def _setup_langchain_agent(self):
        """Setup LangGraph multi-agent system with specialized agents"""
        
        # ============================================
        # STEP 1: Organize tools by agent specialty
        # ============================================
        
        # Simple Agent Tools (fast model) - Basic operations
        self.simple_tools = [
            self._create_current_weather_tool(),
            self._create_weather_forecast_tool(),
            self._create_timezone_tool(),
            self._create_home_automation_tool(),
            self._create_spotify_play_track_tool(),
            self._create_spotify_play_album_tool(),
            self._create_spotify_play_artist_tool(),
            self._create_spotify_control_tool(),
            self._create_volume_control_tool(),
        ]
        
        # Shopping Agent Tools (smart model) - E-commerce operations
        self.shopping_tools = [
            self._create_amazon_single_product_tool(),
            self._create_amazon_multi_product_tool(),
            self._zepto_ordering_tool(),
            self._create_zepto_order_history_tool(),
            self._create_zepto_order_again_tool(),
            self._create_zepto_track_orders_tool(),

        ]
        
        # Communication Agent Tools (fast model) - Messaging & reminders
        self.communication_tools = [
            self._create_telegram_message_tool(),
            self._create_telegram_photo_tool(),
            self._create_telegram_document_tool(),
            self._create_telegram_video_tool(),
            self._create_set_reminder_tool(),
            self._create_list_reminders_tool(),
            self._create_cancel_reminder_tool(),
            self._create_check_reminders_tool(),
        ]
        
        # Analysis Agent Tools (smart model) - Complex reasoning
        self.analysis_tools = [
            self._create_search_tool(),
            self._create_amazon_order_tracking_tool(),
        ]
        
        # Follow-up tool available to all agents
        self.follow_up_tool = self._create_follow_up_question_tool()
        
        # ============================================
        # STEP 2: Initialize different LLMs
        # ============================================
        
        # Fast model for simple operations (excellent tool calling at low cost)
        self.fast_llm = ChatOpenAI(
            model="gpt-4.1-nano",
            temperature=0.7,
            openai_api_key=os.getenv('OPENAI_API_KEY'),
        )
        
        # Smart model for complex reasoning (best tool calling)
        self.smart_llm = ChatOpenAI(
            model="gpt-4.1-mini",
            temperature=0.3,
            openai_api_key=os.getenv('OPENAI_API_KEY'),
        )
        
        # Router model (lightweight for routing decisions)
        self.router_llm = ChatOpenAI(
            model="gpt-4.1-nano",
            temperature=0,
            openai_api_key=os.getenv('OPENAI_API_KEY'),
        )
        
        # ============================================
        # STEP 3: Create the multi-agent workflow
        # ============================================
        
        self._create_langgraph_workflow()
    
    def _load_agent_state(self) -> dict:
        """Load persisted agent state from JSON file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[STATE] Could not load agent state: {e}")
        return {
            "shared_context": {},
            "conversation_history": []
        }
    
    def _save_agent_state(self, state: dict):
        """Save agent state to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            # Convert state to JSON-serializable format
            save_data = {
                "shared_context": state.get("shared_context", {}),
                "last_agent": state.get("next_agent", ""),
                "timestamp": time.time()
            }
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            print(f"[STATE] Saved agent state to {self.state_file}")
        except Exception as e:
            print(f"[STATE] Could not save agent state: {e}")
    
    def _create_langgraph_workflow(self):
        """Create LangGraph workflow with router and specialized agents"""
        
        # Load persisted state
        persisted_state = self._load_agent_state()
        
        # ============================================
        # Define Agent Nodes
        # ============================================
        
        def router_node(state: AgentState) -> AgentState:
            """Router decides which specialized agent to use"""
            user_input = state["user_input"]
            
            # ALWAYS refresh conversation history from live memory (critical for follow-ups)
            # Initialize or update shared_context with fresh history
            if not state.get("shared_context"):
                state["shared_context"] = {}
            
            # Load recent conversation history (last 5 messages)
            recent_history = []
            if self.conversation_history:
                # Get last 5 user-assistant exchanges (10 messages total)
                recent_history = self.conversation_history[-10:]
                print(f"[ROUTER] Loading {len(recent_history)} messages from LIVE conversation history")
                print(f"[ROUTER] Most recent message: {recent_history[-1] if recent_history else 'None'}")
            else:
                print("[ROUTER] No conversation history available")
            state["shared_context"]["recent_conversation"] = recent_history
            
            # Format conversation history for router context
            history_context = ""
            if recent_history:
                history_context = "\n\nRECENT CONVERSATION HISTORY:\n"
                for msg in recent_history[-6:]:  # Last 3 exchanges
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    history_context += f"{role.upper()}: {content}\n"
            
            router_prompt = f"""Analyze the conversation history and current query to route to the correct agent.

CURRENT USER QUERY: "{user_input}"
{history_context}

AVAILABLE AGENTS AND THEIR TOOLS:

SIMPLE Agent:
- get_weather, play_spotify_music, stop_spotify, control_volume, turn_lights_on/off, turn_fan_on/off, turn_ac_on/off

SHOPPING Agent:  
- search_amazon_product, search_amazon_multi_products, zepto_add_product_to_cart, zepto_order_history, zepto_track_orders, zepto_checkout

COMMUNICATION Agent:
- send_telegram_message, send_telegram_photo, send_telegram_document, send_telegram_video, add_reminder, list_reminders, delete_reminder, mark_reminder_complete

ANALYSIS Agent:
- perform_web_search, track_amazon_orders

ROUTING INSTRUCTIONS:
1. Analyze the history to understand context (e.g., if "it" or "that" refers to a product, order, or search result)
2. Match the query to the agent with the necessary tools
3. For compound actions (get data + send), route to data retrieval agent first
4. If query references previous results (e.g., "send it", "send that product"), check if data is already available:
   - If data exists in history → COMMUNICATION
   - If data needs to be fetched → data agent first (SHOPPING/ANALYSIS)

Respond with ONLY: SIMPLE, SHOPPING, COMMUNICATION, or ANALYSIS"""
            
            response = self.router_llm.invoke([HumanMessage(content=router_prompt)])
            route = response.content.strip().upper()
            
            # Validate and default to SIMPLE if unclear
            if route not in ["SIMPLE", "SHOPPING", "COMMUNICATION", "ANALYSIS"]:
                route = "SIMPLE"
            
            print(f"[ROUTER] Query: '{user_input}' → Routed to: {route}")
            
            state["next_agent"] = route.lower()
            state["messages"] = [HumanMessage(content=user_input)]
            return state
        
        def simple_agent_node(state: AgentState) -> AgentState:
            """Simple agent for basic operations - Uses gpt-4.1-nano"""
            tools = self.simple_tools + [self.follow_up_tool]
            
            system_message = """You are Sofi, a female voice assistant in Pune, India.

Handle: Weather, Spotify, Volume, Home Automation.

**PERSONALITY:**
- Friendly, helpful, and conversational
- Keep responses SHORT (1-2 sentences)
- Natural spoken language, no special characters

**LANGUAGE:**
- Hindi input → respond in हिंदी देवनागरी only (never roman transliteration)
- English input → respond in English only

**TOOL USAGE RULES:**
- For ANY Spotify or volume control request (play, pause, next, previous, volume up/down/mute), you MUST use the provided tool. Do NOT just describe the action—ALWAYS call the tool.
- For weather and home automation, also use the tool if available.
- Use ask_follow_up_question tool when clarification needed.
- NEVER ask questions in your response text."
            
            # Create agent using LangGraph's prebuilt agent
            agent_executor = create_agent(self.fast_llm, tools)
            
            # Prepare messages with system prompt and conversation history
            context_messages = []
            
            # Add recent conversation history for context
            if state.get("shared_context", {}).get("recent_conversation"):
                history = state["shared_context"]["recent_conversation"]
                history_text = "\n".join([
                    f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')}"
                    for msg in history[-10:]  # Last 5 exchanges
                ])
                context_messages.append(HumanMessage(content=f"[CONVERSATION HISTORY]\n{history_text}\n"))
            
            # Add system message and current query
            context_messages.append(HumanMessage(content=f"{system_message}\n\nUser: {state['user_input']}"))
            
            # Run the agent
            result = agent_executor.invoke({"messages": context_messages})
            
            # Extract the final AI message
            if result.get("messages"):
                final_message = result["messages"][-1]
                state["final_response"] = final_message.content if hasattr(final_message, 'content') else str(final_message)
            else:
                state["final_response"] = "I processed your request."
            
            return state
        
        def shopping_agent_node(state: AgentState) -> AgentState:
            """Shopping agent for e-commerce - Uses gpt-4o"""
            tools = self.shopping_tools + [self.follow_up_tool]
            
            system_message = """You are Sofi, a female voice assistant in Pune, India specializing in shopping.

Handle: Amazon searches, Zepto ordering, Product purchases.

**PERSONALITY:**
- Helpful shopping advisor
- Speak product details concisely for voice (2-3 key points)
- Keep responses SHORT and conversational

**LANGUAGE:**
- Hindi input → respond in हिंदी देवनागरी only
- English input → respond in English only

**CRITICAL - URL REQUIREMENT:**
When presenting product results, ALWAYS include the full URL for each product.
Format: "Product name – details, ₹Price. URL: https://www.amazon.in/..."

**RULES:**
- Check conversation history first - if user asks for same product recently searched, reuse those results
- ALWAYS include product URLs in your responses (user might want to send them later)
- ALWAYS get confirmation before placing orders (use ask_follow_up_question tool)
- For Zepto: login → clear_cart → search → show result to user → add_product → checkout → get user confirmation → place_order → cleanup
- NEVER ask questions in your response text, use the tool

**HISTORY REUSE:**
If conversation history shows a recent search for the same/similar product, reuse that information instead of searching again. Only search if it's a new/different product."""
            
            # Create agent using LangGraph's prebuilt agent
            agent_executor = create_agent(self.smart_llm, tools)
            
            # Prepare messages with system prompt and conversation history
            context_messages = []
            
            # Add recent conversation history for context
            if state.get("shared_context", {}).get("recent_conversation"):
                history = state["shared_context"]["recent_conversation"]
                history_text = "\n".join([
                    f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')}"
                    for msg in history[-10:]  # Last 5 exchanges
                ])
                context_messages.append(HumanMessage(content=f"[CONVERSATION HISTORY]\n{history_text}\n"))
            
            # Add system message and current query
            context_messages.append(HumanMessage(content=f"{system_message}\n\nUser: {state['user_input']}"))
            
            # Run the agent
            result = agent_executor.invoke({"messages": context_messages})
            
            # Extract the final AI message
            if result.get("messages"):
                final_message = result["messages"][-1]
                state["final_response"] = final_message.content if hasattr(final_message, 'content') else str(final_message)
            else:
                state["final_response"] = "I processed your shopping request."
            
            return state
        
        def communication_agent_node(state: AgentState) -> AgentState:
            """Communication agent for messaging - Uses gpt-4o for better tool calling"""
            tools = self.communication_tools + [self.follow_up_tool]
            
            print(f"[COMMUNICATION AGENT DEBUG] Available tools: {[t.name for t in tools]}")
            print(f"[COMMUNICATION AGENT DEBUG] Tool descriptions:")
            for t in tools:
                print(f"  - {t.name}: {t.description[:100]}...")
            
            system_message = """You are Sofi, a female voice assistant in Pune, India handling communications.

Handle: Telegram messages, Reminders.

**PERSONALITY:**
- Clear and efficient communicator
- Confirm actions taken
- Keep responses SHORT (1 sentence)

**LANGUAGE:**
- Hindi input → respond in हिंदी देवनागरी only
- English input → respond in English only

**CONTEXT-AWARE SENDING:**
When user says "send it", "share that", "send first product", etc:
1. Look at the [CONVERSATION HISTORY] section above
2. Find the most recent Assistant message containing product details/URLs
3. Extract ALL information: product name, price, rating, and URL (starts with https://)
4. Call send_telegram_message with the COMPLETE message including the URL
5. Example: "Zebronics Speaker ₹755 https://amazon.in/dp/..."

**CRITICAL RULES:**
- ALWAYS search conversation history for product URLs when user says send/share
- Include the full product details AND the URL in your telegram message
- MUST call send_telegram_message tool - don't just describe the action
- Only respond with confirmation AFTER calling the tool"""
            
            # Create agent using LangGraph's prebuilt agent
            print(f"[COMMUNICATION AGENT DEBUG] Creating agent with model: {self.smart_llm.model_name}")
            agent_executor = create_agent(self.smart_llm, tools)
            print(f"[COMMUNICATION AGENT DEBUG] Agent created, type: {type(agent_executor)}")
            
            # Prepare messages with system prompt and conversation history
            context_messages = []
            
            # Add recent conversation history for context
            if state.get("shared_context", {}).get("recent_conversation"):
                history = state["shared_context"]["recent_conversation"]
                history_text = "\n".join([
                    f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')}"
                    for msg in history[-10:]  # Last 5 exchanges
                ])
                context_messages.append(HumanMessage(content=f"[CONVERSATION HISTORY]\n{history_text}\n"))
                print(f"[COMMUNICATION AGENT DEBUG] Added {len(history)} messages from conversation history")
            
            # Add system message and current query
            context_messages.append(HumanMessage(content=f"{system_message}\n\nUser: {state['user_input']}"))
            print(f"[COMMUNICATION AGENT DEBUG] Total context messages: {len(context_messages)}")
            print(f"[COMMUNICATION AGENT DEBUG] User input: {state['user_input']}")
            
            # Run the agent
            print("[COMMUNICATION AGENT DEBUG] Invoking agent...")
            result = agent_executor.invoke({"messages": context_messages})
            print(f"[COMMUNICATION AGENT DEBUG] Agent invocation complete, result type: {type(result)}")
            print(f"[COMMUNICATION AGENT DEBUG] Result keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
            
            # Debug: Check if tools were called
            if result.get("messages"):
                print(f"[COMMUNICATION AGENT] Total messages in result: {len(result['messages'])}")
                for i, msg in enumerate(result["messages"]):
                    msg_type = type(msg).__name__
                    print(f"[COMMUNICATION AGENT] Message {i}: {msg_type}")
                    if hasattr(msg, 'content'):
                        print(f"  Content: {str(msg.content)[:200]}")
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        print(f"[COMMUNICATION AGENT] ✅ Tool calls detected: {[tc.get('name') for tc in msg.tool_calls]}")
                    else:
                        print(f"[COMMUNICATION AGENT] ❌ No tool calls in this message")
            
            # Extract the final AI message
            if result.get("messages"):
                final_message = result["messages"][-1]
                state["final_response"] = final_message.content if hasattr(final_message, 'content') else str(final_message)
            else:
                state["final_response"] = "I processed your communication request."
            
            return state
        
        def analysis_agent_node(state: AgentState) -> AgentState:
            """Analysis agent for complex queries - Uses gpt-4o"""
            tools = self.analysis_tools + [self.follow_up_tool]
            
            system_message = """You are Sofi, a female voice assistant in Pune, India specializing in research and analysis.

Handle: Web search, Order tracking, Latest news, Current prices.

**PERSONALITY:**
- Knowledgeable research assistant
- Summarize complex info for voice (2-3 key points)
- Keep responses SHORT but informative

**LANGUAGE:**
- Hindi input → respond in हिंदी देवनागरी only
- English input → respond in English only

**RULES:**
- ALWAYS search for latest/current information (don't rely on training data)
- Focus on most relevant facts
- Use ask_follow_up_question tool when clarification needed"""
            
            # Create agent using LangGraph's prebuilt agent
            agent_executor = create_agent(self.smart_llm, tools)
            
            # Prepare messages with system prompt and conversation history
            context_messages = []
            
            # Add recent conversation history for context
            if state.get("shared_context", {}).get("recent_conversation"):
                history = state["shared_context"]["recent_conversation"]
                history_text = "\n".join([
                    f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')}"
                    for msg in history[-10:]  # Last 5 exchanges
                ])
                context_messages.append(HumanMessage(content=f"[CONVERSATION HISTORY]\n{history_text}\n"))
            
            # Add system message and current query
            context_messages.append(HumanMessage(content=f"{system_message}\n\nUser: {state['user_input']}"))
            
            # Run the agent
            result = agent_executor.invoke({"messages": context_messages})
            
            # Extract the final AI message
            if result.get("messages"):
                final_message = result["messages"][-1]
                state["final_response"] = final_message.content if hasattr(final_message, 'content') else str(final_message)
            else:
                state["final_response"] = "I processed your analysis request."
            
            return state
        
        # ============================================
        # Build StateGraph
        # ============================================
        
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("router", router_node)
        workflow.add_node("simple", simple_agent_node)
        workflow.add_node("shopping", shopping_agent_node)
        workflow.add_node("communication", communication_agent_node)
        workflow.add_node("analysis", analysis_agent_node)
        
        # Set entry point
        workflow.set_entry_point("router")
        
        # Define routing logic
        def route_to_agent(state: AgentState) -> str:
            """Route based on router decision"""
            return state["next_agent"]
        
        # Add conditional edges from router to agents
        workflow.add_conditional_edges(
            "router",
            route_to_agent,
            {
                "simple": "simple",
                "shopping": "shopping",
                "communication": "communication",
                "analysis": "analysis"
            }
        )
        
        # All agents go to END
        workflow.add_edge("simple", END)
        workflow.add_edge("shopping", END)
        workflow.add_edge("communication", END)
        workflow.add_edge("analysis", END)
        
        # Compile the graph
        self.langgraph_app = workflow.compile()
        
        print("[LANGGRAPH] Multi-agent workflow initialized with 4 specialized agents")
    
    def process_user_command(self, user_command: str) -> bool:
        """
        Main method that replaces your original process_user_command
        Now uses LangGraph multi-agent system instead of manual tool selection
        Includes follow-up conversation support
        """
        
        # Check for exit commands (same as original)
        if any(word in user_command.lower() for word in ["exit", "quit", "goodbye", "bye"]):
            # Speak goodbye (LED controlled in audio_processor)
            self.audio_processors.speak("Goodbye!")
            return True
        
        try:
            # Set LED to processing/thinking state (blinking)
            if self.pixel_led:
                self.pixel_led.set_processing()
            
            # Define the agent processing function using LangGraph
            def agent_processing():
                # Use LangGraph multi-agent system
                initial_state = {
                    "messages": [],
                    "user_input": user_command,
                    "next_agent": "",
                    "final_response": "",
                    "shared_context": {},
                    "requires_handoff": False
                }
                
                # Run through LangGraph workflow
                final_state = self.langgraph_app.invoke(initial_state)
                response = final_state["final_response"]
                
                print(f"\n[RESPONSE] {response}\n")
                
                # Save agent state to file for cross-agent access
                self._save_agent_state(final_state)
                
                # Add to conversation history (store original response with URLs)
                self.conversation_history.append({"role": "user", "content": user_command})
                assistant_entry = {"role": "assistant", "content": response}
                self.conversation_history.append(assistant_entry)

                # Persist conversation history if a ConversationManager is provided
                try:
                    if getattr(self, 'conversation_manager', None):
                        self.conversation_manager.save_conversation_history()
                except Exception as save_err:
                    print(f"Warning: failed to save conversation history: {save_err}")

                if "ask_follow_up_question" not in response.lower():
                    # Remove URLs for TTS (keep them in conversation history)
                    import re
                    tts_text = re.sub(r'https?://\S+', '', response)  # Remove all URLs
                    tts_text = re.sub(r'URL:\s*', '', tts_text)  # Remove "URL:" label
                    tts_text = tts_text.strip()
                    
                    self.audio_processors.speak(tts_text)
                
                return response
            
            response = agent_processing()
            

            gc.collect()
            

            
            print("Agent processing completed. Ready for next command.")
            return False
            
        except Exception as e:
            error_msg = f"Sorry, I encountered an error: {str(e)}"
            print(f"Agent error: {e}")
            # Speak error message (LED controlled in audio_processor)
            self.audio_processors.speak(error_msg)
            # Clean up memory after error
            gc.collect()
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
