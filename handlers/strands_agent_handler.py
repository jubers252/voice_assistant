
from urllib import response

from strands import Agent, tool
import uuid
from asyncio.log import logger
import os
from datetime import datetime, time as dt_time
import threading
import json
import concurrent.futures
import queue
import speech_recognition as sr
# Ensure project root is in path when running this file directly

# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import time
import re
import difflib
import warnings
import urllib3
import gc
from connectors.zepto_order_database import ZeptoOrderDatabase

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from strands.models.openai import OpenAIModel
import chromadb
from chromadb.utils import embedding_functions
from handlers.system_prompt import SOFI_SYSTEM_PROMPT
import nest_asyncio
from playwright.sync_api import sync_playwright
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
from connectors.get_images_and_video import search_and_download_images, search_videos
import asyncio
from handlers.agent_session_manager import MySQLiteRepository
from strands.session.repository_session_manager import RepositorySessionManager
from strands.agent.conversation_manager import SlidingWindowConversationManager
from handlers.event_scheduler import EventScheduler
from audio.audio_processor import AudioProcessors
warnings.filterwarnings("ignore", message=".*Failed to establish a new connection.*")
load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")

class StrandsAgent(Agent):
    """Strands Agent with tool usage and dynamic prompt generation"""
    
    def __init__(self, session_id: str, model:OpenAIModel, pixel_led=None, recognizer=None, audio_processors=None):
        """Initialize the agent with connectors, conversation manager, and dynamic prompt generator."""
        
        # Initialize connectors
        self.volume_control = VolumeController()
        self.spotify_connector = SpotifyConnector(None)
        self.search_connector = GeminiSearch()
        self.telegram_bot = TelegramBot()
        self.reminder_manager = ReminderManager()
        self.bigbasket_tools = BigBasketTools()
        self.zepto_db = ZeptoOrderDatabase()
        self.home_automation = HomeAutomation()
        self.youtube_music = MusicPlayer()
        self.audio_processors = audio_processors
        self.audio_processors = AudioProcessors()

        self.pixel_led = pixel_led
        if self.audio_processors:
            self.audio_processors.set_pixel_led(self.pixel_led) 
        self.recognizer = recognizer  
        self.conversation_history = []
        self.event_scheduler = EventScheduler()
        if recognizer:
            self.spotify_connector.set_speech_recognizer(recognizer)


        zepto_phone = os.getenv('ZEPTO_PHONE_NUMBER', '9028129764')
  
        self.zepto_scraper = ZeptoScraper(zepto_phone, headless=True)

        self._zepto_loop = None
        self._zepto_thread = None
        self._setup_zepto_loop()
        nest_asyncio.apply()
        # Sliding window for the "last 10 messages" logic
        conv_manager = SlidingWindowConversationManager(window_size=10)
        repo = MySQLiteRepository("assistant_memory.db")
        session_manager = RepositorySessionManager(
            session_id=session_id,
            session_repository=repo
        )
        # embedding model for rag
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key= openai_api_key,
                model_name="text-embedding-3-small"
                )

        client = chromadb.PersistentClient(path="./chroma_memory")
        self.collection = client.get_or_create_collection(
                name="chat_history", 
                embedding_function=openai_ef
            )

        super().__init__(
            model=model,
            system_prompt=SOFI_SYSTEM_PROMPT,
            tools=[
                self.get_current_weather,
                self.get_travel_time,
                self._create_home_automation_tool,
                self._create_weather_forecast_tool,
                self._create_timezone_tool,
                self._create_spotify_play_track_tool,
                self._create_spotify_play_album_tool,
                self._create_spotify_play_artist_tool,
                self._create_spotify_control_tool,
                self._create_search_tool,
                self._create_amazon_single_product_tool,
                self._create_amazon_multi_product_tool,
                self._create_amazon_order_tracking_tool,
                self._create_set_reminder_tool,
                self._create_list_reminders_tool,
                self._create_cancel_reminder_tool,
                self._create_check_reminders_tool,
                self._create_telegram_message_tool,
                self._create_telegram_photo_tool,
                self._create_telegram_document_tool,
                self._create_telegram_video_tool,
                self._create_volume_control_tool,
                self._zepto_ordering_tool,
                self._create_zepto_order_history_tool,
                self._create_zepto_order_again_tool,
                self._create_zepto_track_orders_tool,
                self._create_youtube_music_play_song_tool,
                self._create_youtube_music_play_playlist_tool,
                self._create_youtube_music_play_artist_tool,
                self._create_youtube_music_control_tool,
                self._create_follow_up_question_tool,
                self.add_event_tool,
                self.save_fact,
                self.search_past_conversations,
                self.get_images_tool,
                self.get_video_tool,

            ],
            session_manager=session_manager,
            conversation_manager=conv_manager
        )
        
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._agent_lock = threading.Lock()  # Prevent concurrent LLM calls (not thread-safe)
        self._last_follow_up_question = ""
        self._last_follow_up_question_at = 0.0
     

    def _normalize_text(self, text: str) -> str:
        """Normalize text for robust similarity checks."""
        text = (text or "").lower().strip()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return text


    def _is_repeat_of_recent_follow_up(self, response_text: str) -> bool:
        """Return True if response is a near-duplicate of a recently spoken follow-up question."""
        if not self._last_follow_up_question:
            return False

        current = self._normalize_text(response_text)
        previous = self._normalize_text(self._last_follow_up_question)

        if not current or not previous:
            return False

        # Exact/containment checks first, then fuzzy similarity for paraphrases.
        if current == previous or current in previous or previous in current:
            return True

        similarity = difflib.SequenceMatcher(None, current, previous).ratio()
        return similarity >= 0.68


    def _setup_zepto_loop(self):
        """Setup a persistent event loop for Zepto operations in a dedicated thread"""
               
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
        
        timeout = 5
        start = time.time()
        while self._zepto_loop is None and (time.time() - start) < timeout:
            time.sleep(0.1)
    
    def _run_in_zepto_loop(self, coro, timeout=120):
        """Run coroutine in the persistent Zepto event loop"""
        
        if self._zepto_loop is None:
            raise RuntimeError("Zepto event loop not initialized")
        
        future = asyncio.run_coroutine_threadsafe(coro, self._zepto_loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return "Operation timed out"
        except Exception as e:
            raise e

    def save_and_embed_message(self, role, content):
       
        # 1. Add to ChromaDB for permanent RAG
        self.collection.add(
            documents=[content],
            metadatas=[{"role": role}],
            ids=[str(uuid.uuid4())]
        )

    @tool
    def get_images_tool(self, query: str, num_images: int = 5) -> list[str]:
        """
        get images for a query and return list of image URLs. Use when user says: 'show me pictures of', 'find images of', 'get me photos of'. Input: search query (e.g., 'cute cats', 'Eiffel Tower at night').
        Args:
        query (str): What to search for
        num_images (int): Number of images to return (default: 5)
    
    Returns:
        dict: {
            'success': bool,
            'message': str,
            'images': list of {
                'filename': str,
                'path': str,
                'url': str,
                'title': str
            }
        }
        """
        try:
            result = search_and_download_images(query, num_images=num_images)
            if result['success']:
                return [img['url'] for img in result['images']]
            else:
                return [f"Error: {result['message']}"]
        
        except Exception as e:
            return [f"Error scraping images: {str(e)}"]

    @tool
    def get_video_tool(self, query: str, num_videos: int = 5) -> list[str]:
        """
        Search for videos using Brave Search API and return list of video URLs. Use when user says: 'show me videos of', 'find videos of', 'get me clips of'. Input: search query (e.g., 'funny dog videos', 'latest music videos').
        Args:
            query (str): What to search for
            num_videos (int): Number of videos to return (default: 5)
            """
        try:
            result = search_videos(query, num_videos=num_videos)
            if result['success']:
                return [video['url'] for video in result['videos']]
            else:
                return [f"Error: {result['message']}"]
        
        except Exception as e:
            return [f"Error searching videos: {str(e)}"]

    
    @tool
    def add_event_tool(self, event_time: dt_time, prompt: str, event_id: str = None):
        """Schedule a proactive event to run at a specific time. Use when user says: 'remind me to [do something] at [time]', or schedule an event to perform some action at a specific time. 
        At the scheduled time, the event will automatically pass the prompt message to the agent for processing and action completion.
        Args:
            event_time: Time for the event in HH:MM format (e.g., "14:30" or "9:00 AM")
            prompt: The action/message to execute at scheduled time (e.g., "Turn on the lights", "order milk from zepto on daily 9:00 AM")
            event_id: Optional unique ID for the event (auto-generated if not provided)
        """
        try:
            if not event_id:
                event_id = str(uuid.uuid4())
            
            hour = event_time.hour
            minute = event_time.minute
            
            self.event_scheduler.add_event(event_time, prompt, event_id)

            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            events_file = os.path.join(current_dir, 'events.json')
            
            try:
                if os.path.exists(events_file):
                    with open(events_file, 'r') as f:
                        data = json.load(f)
                else:
                    data = {"events": []}
            except json.JSONDecodeError:
                data = {"events": []}
            
            new_event = {
                "hour": hour,
                "minute": minute,
                "prompt": prompt,
                "event_id": event_id
            }
            
            data["events"].append(new_event)

            with open(events_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            return f"Event '{prompt}' scheduled for {event_time.strftime('%H:%M')} with ID {event_id}"
        except Exception as e:
            return f"Error scheduling event: {str(e)}"

    @tool
    def list_schedule_event(self):
        """List all scheduled events. Use when user says: 'what are my scheduled events', 'what are my upcoming events'. This will return a list of all upcoming scheduled events with their prompts and scheduled times."""
        events =  self.event_scheduler.get_events()
        return events
    

    @tool
    def search_past_conversations(self, query: str) -> str:
        """
        Search through the entire history of our past conversations. 
        Use this if the user refers to something we discussed a long time ago.
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=3
        )
        
        if not results['documents'][0]:
            return "No relevant past conversations found."
            
        return "\n---\n".join(results['documents'][0])
    

    @tool
    def save_fact(self, key: str, value: str):
        """Saves a permanent fact about the user in the agent's long-term state.
        
        Args:
            key: The category or name of the fact (e.g., 'name', 'age', 'job')
            value: The specific information to remember
        """
   
        profile = self.state.get("profile") or {}
        
        profile[key] = value
        self.state.set("profile", profile)
        
        return f"I've updated your {key} to '{value}' in my records."
    
    @tool
    def get_current_weather(self, location: str):
        """
        Retrieves the current weather and temperature for a specific city.
        Use this when the user asks about rain, temperature, or general weather conditions.
        
        Args:
            location: The name of the city (e.g., 'Pune', 'New York').
        """
        try:
            tool_request = {
                "tool": "weather", 
                "action": "get_current_weather",
                "location": location
            }
            # Assuming handle_tool_requests is available in your scope
            result = handle_tool_requests(tool_request)
            return f"Current weather in {location}: {result}"
        except Exception as e:
            return f"Weather retrieval error: {str(e)}"
    
    @tool
    def get_travel_time(self, origin: str, destination: str):
        """
        Calculates travel distance, duration, and real-time traffic impact between two locations.
        Use this for queries like 'how long to reach', 'how far is', or 'what's the traffic'.
        
        Args:
            origin: Starting point address or city (e.g., 'Pisoli, Pune').
            destination: Ending point address or city (e.g., 'Kondhwa, Pune').
        """
        try:
            # get_travel_time_with_traffic is your existing core logic function
            result = get_travel_time_with_traffic(origin, destination)
            
            return (
                f"Travel from {origin} to {destination}:\n"
                f"- Distance: {result['distance']}\n"
                f"- Standard time: {result['standard_duration']}\n"
                f"- Current time (with traffic): {result['duration_in_traffic']}\n"
                f"- Delay: {result['traffic_delay_seconds']}s (+{result['traffic_impact_percent']}%)"
            )
        except Exception as e:
            return f"Travel calculation error: {str(e)}"

    @tool
    def _create_home_automation_tool(self, command: str):
        """Use this tool to control smart home devices (lights, fans, zero light etc). ALWAYS use for: turn on/off light, fan, or any device. Queries: turn on light, turn off fan, light on, fan off, device status, what devices are on. Format: "status" to check all device states, or "control|device_name:true|device_name:false" to set devices. Device names: light, fan, zero, etc.
        Args:
            command: The command string to control or check the status of devices e.g., "status" or "control|light:true|fan:false".
        """
        try:
            obj = HomeAutomation()
            parts = command.split("|")
            action = parts[0].lower().strip()

            if action == "status":
                status = obj.get_status()
                if status:
                    status_str = ", ".join([f"{k}: {'on' if v else 'off'}" for k, v in status.items()])
                    return f"Current device status: {status_str}"
                else:
                    return "Unable to retrieve device status"

            elif action == "control":
                if len(parts) < 2:
                    return "Please provide devices. Format: control|light:true|fan:false"

                devices = {}
                for i in range(1, len(parts)):
                    pair = parts[i].split(":")
                    if len(pair) == 2:
                        device_name = pair[0].strip()
                        device_value = pair[1].strip().lower()
                        devices[device_name] = device_value in ['true', '1', 'yes', 'on']

                if not devices:
                    return "No valid devices found"

                obj.send_cmd(devices)
                return "Updated devices"

            else:
                return "Home automation actions: status or control"

        except Exception as e:
            return f"Home automation error: {str(e)}"
            
    @tool        
    def _create_weather_forecast_tool(self, location: str): 
            """ Get 3-day weather forecast. Use when: 'forecast', 'will it rain tomorrow'. Input: city name
            Args:
            location: The location for which to get the weather forecast (e.g., 'Pune').

            """
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
    
        
    @tool
    def _create_timezone_tool(self, location: str):
        """Get timezone and current time. Use when: 'what time is it in', 'timezone of'. Input: city name
        Args:
            location: The location for which to get the timezone (e.g., 'Pune').
        """
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

    @tool    
    def _create_spotify_play_track_tool(self, track_name: str):
            """Play a song on Spotify. Use when: 'play [song]', 'put on [track]'. Input: song name
            Args:
                track_name: The name of the track to play on Spotify (e.g., 'Shape of You').
            """
        
            try:
                # Set music playing flag immediately
                if self.recognizer:
                    self.recognizer.set_music_playing(True)
                
                def spotify_task():
                    tool_response = {
                        "tool": "spotify",
                        "action": "play",
                        "target": "track",
                        "name": track_name
                    }
                    return self.spotify_connector.handle_spotify_action_with_feedback(
                        tool_response, self.conversation_history
                    )
                
                # Run Spotify in executor pool to avoid audio conflicts
                self.executor.submit(spotify_task)
                
                return f"Starting track playback: {track_name}"
            except Exception as e:
                return f"Spotify track error: {str(e)}"
        
            
    @tool
    def _create_spotify_play_album_tool(self, album_name: str):
        """Play an album on Spotify. Use when: 'play album [name]'. Input: album name
        Args:
        album_name: The name of the album to play on Spotify (e.g., 'Divide' by Ed Sheeran).
        """
    
        try:
            # Set music playing flag immediately
            if self.recognizer:
                self.recognizer.set_music_playing(True)
            
            def spotify_task():
                tool_response = {
                    "tool": "spotify",
                    "action": "play",
                    "target": "album",
                    "name": album_name
                }
                return self.spotify_connector.handle_spotify_action_with_feedback(
                    tool_response, self.conversation_history
                )
            
            # Run Spotify in executor pool to avoid audio conflicts
            self.executor.submit(spotify_task)
            
            return f"Starting album playback: {album_name}"
        except Exception as e:
            return f"Spotify album error: {str(e)}"
        
    
    @tool
    def _create_spotify_play_artist_tool(self, artist_name: str):
        """Play music by an artist on Spotify. Use when: 'play [artist]', 'put on [artist] music'. Input: artist name
        Args:    artist_name: The name of the artist to play on Spotify (e.g., 'Ed Sheeran').
        """
        try:
            # Set music playing flag immediately
            if self.recognizer:
                self.recognizer.set_music_playing(True)
            
            def spotify_task():
                tool_response = {
                    "tool": "spotify",
                    "action": "play",
                    "target": "artist",
                    "name": artist_name
                }
                return self.spotify_connector.handle_spotify_action_with_feedback(
                    tool_response, self.conversation_history
                )
            
            # Run Spotify in executor pool to avoid audio conflicts
            self.executor.submit(spotify_task)
            
            return f"Starting artist playback: {artist_name}"
        except Exception as e:
            return f"Spotify artist error: {str(e)}"
            
    @tool
    def _create_spotify_control_tool(self, action: str):
        """Resume, pause, or skip Spotify playback. CRITICAL: Use when user says: 'play', 'resume', 'continue', 'pause', 'stop', 'next', 'skip'. Input format: pause|resume|next|skip (e.g., 'resume' to play music, 'pause' to stop, 'next' to skip song)
        Args:    action: The playback control action (e.g., 'pause', 'resume', 'next')."""

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
            
            def spotify_control_task():
                tool_response = {
                    "tool": "spotify",
                    "action": spotify_action
                }
                return self.spotify_connector.handle_spotify_action_with_feedback(
                    tool_response,  self.conversation_history
                )
            
            # Run Spotify control in executor pool to avoid audio conflicts
            self.executor.submit(spotify_control_task)
            
            return f"Spotify control: {action_lower}"
        except Exception as e:
            return f"Spotify control error: {str(e)}"
        

    @tool
    def _create_search_tool(self, query: str):
        """Search the internet for LATEST/CURRENT information. MANDATORY for: latest news, current prices, today's info, recent updates, live status. Use when: 'what's latest', 'current', 'today', 'right now', 'latest news about', 'trending'. Input: search query (e.g., 'latest Bitcoin price', 'current weather today', 'trending news')
        Args:    query: The search query string (e.g., 'latest news about AI').
        """
    
        try:
            # Use your existing search connector
            tool_request = {"query": query, "tool": "search"}
            result = self.search_connector.handle_search_action_with_feedback(tool_request)
            return result[:500]  # Limit response length
        except Exception as e:
            return f"Search error: {str(e)}"

        
    @tool
    def _create_amazon_single_product_tool(self, query: str):
        """Search Amazon for detailed information about a specific single product with price, rating, and direct product link. Use when user wants detailed info about one product. Input: product name only (e.g., 'iphone 15' NOT '1|iphone 15').
        Args:   
        query: The product name to search for on Amazon (e.g., 'iphone 15').  """
        
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
 

    @tool
    def _create_amazon_multi_product_tool(self, query: str):
        """Search Amazon for multiple products to compare options with prices, ratings, and direct product links. Use when user wants to see several product choices or browse options. Input: product name only (e.g., 'iphone 15' NOT '1|iphone 15')
        Args:    query: The product name to search for on Amazon (e.g., 'iphone 15')."""
    
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


    @tool
    def _create_amazon_order_tracking_tool(self, days_input: str):
        """Track Amazon orders from recent days. Input: number of days (e.g., '5' or 'last 7 days'). Use when user wants to know about their recent Amazon orders. The tool will return a summary of orders from the specified number of days.
        Args:    days_input: A string indicating the number of recent days to track orders for (e.g., '5', 'last 7 days').
        """
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

   
    @tool
    def _create_set_reminder_tool(self, reminder_input: str):
        """Set a TEMPORARY notification/alarm - deleted after triggered or when cleared. Use for: one-time alerts, time-based notifications, meeting reminders. Input: 'text|time|recurring' (recurring='once' or 'daily'). Examples: 'Call mom|in 30 minutes|once', 'Take medicine|2:00 PM|once', 'Gym|6 AM|daily'
        ARGs: reminder_input: A string containing the reminder details in the format 'text|time|recurring'.
        - text: The reminder message (e.g., 'Call mom').
        - time: The time for the reminder (e.g., 'in 30 minutes', '2:00 PM').
        - recurring: The recurrence pattern ('once' or 'daily')."""
    
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

   
    @tool
    def _create_list_reminders_tool(self):
        """List all active reminders. No input required."""
    
        try:
            action_data = {"action": "list"}
            result = self.reminder_manager.handle_reminder_action(action_data)
            return result
        except Exception as e:
            return f"List reminders error: {str(e)}"


    @tool
    def _create_cancel_reminder_tool(self, reminder_id: str):
        """Cancel a specific reminder by ID. Input should be the reminder ID number.
        Args:    reminder_id: The ID number of the reminder to cancel (e.g., '1')."""
        
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


    @tool
    def _create_check_reminders_tool(self):
        """Check for any due reminders right now. No input required."""
    
        try:
            action_data = {"action": "check"}
            result = self.reminder_manager.handle_reminder_action(action_data)
            return result
        except Exception as e:
            return f"Check reminders error: {str(e)}"
    
  

    @tool
    def _create_schedule_event_tool(self, event_input: str):
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


    @tool
    def _create_telegram_message_tool(self, message: str) :
        """Send a text message via Telegram. Input should be the message text.
        Args:    message: The text message to send via Telegram (e.g., 'Hello from my agent!')."""
    
        try:
            tool_response = {
                "action": "send_message",
                "message": message
            }
            result = self.telegram_bot.telegram_handler(tool_response)
            return f"Message sent to Telegram: {message}"
        except Exception as e:
            return f"Telegram message error: {str(e)}"
    

    @tool
    def _create_telegram_photo_tool(self, photo_info: str):
        """Send a photo via Telegram. Input format: 'photo_path|caption' or just 'photo_path'. Note: URLs may not work directly - local files preferred.
        Args:    
        photo_info: A string containing the photo path and optional caption, separated by a pipe (e.g., 'path/to/photo.jpg|This is a caption'). The photo_path can be a local file path or a URL, but local files are more reliable for Telegram."""

        try:
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


    @tool
    def _create_telegram_document_tool(self, doc_info: str):
        """Send a document via Telegram. Input format: 'document_path|caption' or just 'document_path'.
        Args:   
          doc_info: A string containing the document path and optional caption, separated by a pipe (e.g., 'path/to/document.pdf|This is a caption'). The document_path can be a local file path or a URL, but local files are more reliable for Telegram."""
        
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
    

    @tool
    def _create_telegram_video_tool(self, video_info: str):
        """Send a video via Telegram. Input format: 'video_path|caption' or just 'video_path'.
        Args:    
          video_info: A string containing the video path and optional caption, separated by a pipe (e.g., 'path/to/video.mp4|This is a caption'). The video_path can be a local file path or a URL, but local files are more reliable for Telegram."""

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


    @tool
    def _create_volume_control_tool(self, command: str):
        """Control system volume. Commands: 'increase', 'decrease', 'mute', 'unmute', 'set', or 'status'. Format: action|step|level (e.g., 'increase|10' or 'decrease|10' or 'set||50').
        Args:   
          command: A string command to control volume, formatted as 'action|step|level'. Examples: 'increase|10' to raise volume by 10%, 'decrease|5' to lower by 5%, 'set||50' to set volume to 50%, 'mute' to mute, 'unmute' to unmute, 'status' to check current volume."""
    
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
    

    @tool
    def _zepto_ordering_tool(self, input_str: str):
        """Zepto grocery ordering and database check. ACTIONS: 1) get_latest - check for incomplete order in database (CALL THIS FIRST), 2) login, 3) clear_cart, 4) search|product_name, 5) add_product|product_name|quantity|index, 6) order_details, 7) checkout, 8) place_order, 9) cleanup. Format: 'action|product|quantity|index'. ALWAYS use get_latest first when user mentions Zepto/order. ALWAYS ask user confirmation before place_order.
        ARGS: input_str: A string containing the action and parameters for Zepto ordering, formatted as 'action|product_name|quantity|product_index'. """
        
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


    @tool
    def _create_zepto_order_history_tool(self, max_orders: str = "3"):
        """Get recent Zepto order history. Input: number of orders to fetch (default 3). Returns list of recent orders with status, date, amount, and item count.
        Args:    max_orders: A string representing the number of recent orders to retrieve (e.g., '3'). Defaults to '3' if not provided or invalid."""
        
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


    @tool
    def _create_zepto_order_again_tool(self, order_index: str = "0"):
        """Reorder a previous Zepto order. Input: order index (0 for most recent, 1 for second most recent, etc.). This adds all items from that order to your cart.
        Args:    order_index: A string representing the index of the order to reorder (e.g., '0' for most recent, '1' for second most recent)."""
    
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
    
   
    @tool
    def _create_zepto_track_orders_tool(self, params: str = "3|none"):
        """Track recent Zepto orders with optional detailed info. Input format: 'max_orders|detail_index' (e.g., '5|0' to get 5 orders with details for first one) or just 'max_orders' (e.g., '3'). Returns order summaries with status, date, amount. If detail_index provided, includes tracking info for that order.
        Args:    params: A string containing the parameters for tracking orders, formatted as 'max_orders|detail_index' or just 'max_orders'."""
    
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
    
   
    @tool
    def _create_youtube_music_play_song_tool(self, song_name: str, volume: int = None):
        """Play a specific song on YouTube Music. Use when: 'play [song name]', 'put on [song]'. Input: song name (e.g., 'Bohemian Rhapsody').
        Args:    song_name: The name of the song to play on YouTube Music (e.g., 'Bohemian Rhapsody').
                 volume: Optional volume level 0-100."""

        try:
            if self.recognizer:
                self.recognizer.set_music_playing(True)

            self.executor.submit(self.youtube_music.play, song_name, volume)
            vol_label = f" at {volume}%" if volume is not None else ""
            return f"Starting song playback: {song_name}{vol_label}"
        except Exception as e:
            return f"YouTube Music song error: {str(e)}"

    @tool
    def _create_youtube_music_play_playlist_tool(self, playlist_name: str, volume: int = None):
        """Play a YouTube Music playlist. Use when: 'play playlist [name]', 'play [playlist theme]'. Input: playlist name or theme (e.g., 'romantic songs', 'workout', 'chill vibes').
        Args:    playlist_name: The name or theme of the playlist to play on YouTube Music (e.g., 'chill vibes')."""

        try:
            if self.recognizer:
                self.recognizer.set_music_playing(True)

            self.executor.submit(self.youtube_music.play_playlist, playlist_name, volume=volume)
            vol_label = f" at {volume}%" if volume is not None else ""
            return f"Starting playlist: {playlist_name}{vol_label}"
        except Exception as e:
            return f"YouTube Music playlist error: {str(e)}"
    
    @tool
    def _create_youtube_music_play_artist_tool(self, artist_name: str, volume: int = None):
        """Play all available songs by an artist on YouTube Music. Use when: 'play [artist name]', 'put on [artist] music', 'play songs by [artist]'. Input: artist name (e.g., 'The Beatles', 'Taylor Swift').
        Args:    artist_name: The name of the artist whose songs to play on YouTube Music (e.g., 'The Beatles')."""
    
        try:
            if self.recognizer:
                self.recognizer.set_music_playing(True)

            self.executor.submit(self.youtube_music.play_all_artist_tracks, artist_name, volume)
            vol_label = f" at {volume}%" if volume is not None else ""
            return f"Starting artist playlist: {artist_name}{vol_label}"
        except Exception as e:
            return f"YouTube Music artist error: {str(e)}"
    
    
    @tool
    def _create_youtube_music_control_tool(self, action: str):
        """Control YouTube Music playback. Actions: pause, stop, resume, next, previous. Use when: 'pause', 'stop', 'play', 'resume', 'next song', 'skip', 'previous'. Input: action name (e.g., 'pause', 'stop', 'next', 'resume').
        Args:    action: A string command to control YouTube Music playback. Supported actions: 'pause', 'stop', 'resume', 'next', 'previous'. Example inputs: 'pause', 'resume', 'next song', 'skip', 'previous'."""
    
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


    @tool
    def _create_follow_up_question_tool(self, input_text: str):
        """Ask user a follow-up question, wait for answer. Input: the question to ask.
        Args:    input_text: The question to speak to the user (e.g. 'Which city do you want the weather for?')"""

        try:
            question = input_text.strip()
            print("Follow-up tool asking:", question)

            if self.pixel_led:
                self.pixel_led.set_speaking()

            # Speak question and wait until fully played before opening mic.
            self.executor.submit(self.audio_processors.speak, question)
            self._last_follow_up_question = question
            self._last_follow_up_question_at = time.time()

            # Brief pause so executor thread has time to set is_speaking = True
            time.sleep(0.3)
            # Poll until TTS finishes
            while getattr(self.audio_processors, 'is_speaking', False):
                time.sleep(0.1)

            time.sleep(0.5)  # Settle so speaker output clears before mic opens

            if self.pixel_led:
                self.pixel_led.set_listening()

            if self.recognizer:
                recognizer = self.recognizer
            else:
                recognizer = SpeechRecognizer(sr.Recognizer(), self.audio_processors, pixel_led=self.pixel_led)

            self.audio_processors.play_beep_sound()
            time.sleep(0.2)

            follow_up_command = recognizer.listen_for_command(is_follow_up=True, timeout=20, max_retries=0)
            
            if follow_up_command:
                # Return the response in a way that makes it clear this is answering the question
                return f"User's answer to your question: '{follow_up_command}'. Now complete the original task based on this answer without searching again."
            else:
                
                return "User did not respond to the question. Proceed with default action or inform user."
                
        except Exception as e:
            return f"Follow-up error: {str(e)}"
    

    def process_user_command(self, user_command: str, scheduled: bool = False):
            """
            Main method that replaces your original process_user_command
            Now uses intelligent agent instead of manual tool selection
            Includes follow-up conversation support and conversation history awareness

            Args:
                user_command: The command text to process
                scheduled: If True, skip instead of blocking when agent is already busy
            
            Returns:
                dict: Contains 'response' (full response) and 'tts_text' (cleaned for speech)
                or None if command was exit
            """
            
            # Check for exit commands (same as original)
            if any(word in user_command.lower() for word in ["exit", "quit", "goodbye", "bye"]):
                # Speak goodbye (LED controlled in audio_processor)
                self.audio_processors.speak("Goodbye!")
                return None

            # Scheduled events skip if the agent is already busy (wake-word command in progress)
            if scheduled and not self._agent_lock.acquire(blocking=False):
                print(f"[SCHEDULER] Agent busy, skipping scheduled event: {user_command[:50]}")
                return None
            elif not scheduled:
                self._agent_lock.acquire(blocking=True)

            try:
                # Set LED to processing/thinking state (blinking)
                if self.pixel_led:
                    self.pixel_led.set_processing()

                # Use the current agent instance and the actual user command.
                raw_response = self(user_command)

                if isinstance(raw_response, dict):
                    response_text = raw_response.get("response") or str(raw_response)
                else:
                    response_text = str(raw_response)

                urls = []
                seen_urls = set()
                for match in re.findall(r'https?://\S+', response_text):
                    clean_url = match.rstrip('.,;:)}"\'')
                    if clean_url and clean_url not in seen_urls:
                        seen_urls.add(clean_url)
                        urls.append(clean_url)

                # Avoid speaking the same follow-up question twice (tool already spoke it).
                if not self._is_repeat_of_recent_follow_up(response_text):
                    self.executor.submit(self.audio_processors.speak, response_text)
                else:
                    print("Skipping duplicate follow-up question speech from final response")

                if self.pixel_led:
                    self.pixel_led.set_listening()

                self.save_and_embed_message("user", user_command)
                self.save_and_embed_message("assistant", response_text)

                gc.collect()
                return {
                    "response": response_text,
                    "tts_text": response_text,
                    "urls": urls
                }
            except Exception as e:
                error_msg = f"Sorry, I encountered an error: {str(e)}"
                self.executor.submit(self.audio_processors.speak, error_msg)
                gc.collect()
                return {
                    "response": error_msg,
                    "tts_text": error_msg,
                    "urls": []
                }
            finally:
                self._agent_lock.release()
        
if __name__ == "__main__":
    # Example of initializing the agent and testing a tool
    openai_api_key = os.getenv("OPENAI_API_KEY")

    model = OpenAIModel(
        model_id="gpt-5.4-mini",
        client_args={
            "api_key": openai_api_key,
        },
        params={
            "temperature": 0.7,
            "max_completion_tokens": 2000
        }
    )
    my_pi_agent = StrandsAgent(model=model, session_id="pi_01")
    response = my_pi_agent.process_user_command("i m getting bored what should i do")
    print(response)
