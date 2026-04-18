"""
Dynamic Prompt Generator for Voice Assistant
Generates custom prompts based on tools required for user's request
Uses LLM-based (GPT-4o-mini) intent detection instead of keyword matching
"""


import logging
from typing import Dict, List, Tuple, Set
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import os
from functools import lru_cache
from dotenv import load_dotenv
from datetime import datetime
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Tool descriptions organized by category
TOOL_DESCRIPTIONS = {
    "get_current_weather": "Get current weather for a location. Use when: 'what is the weather', 'is it raining', 'temperature'. Input: city name",
    "get_weather_forecast": "Get 3-day weather forecast. Use when: 'forecast', 'will it rain tomorrow'. Input: city name",
    "get_timezone": "Get timezone and current time. Use when: 'what time is it in', 'timezone of'. Input: city name",
    "get_travel_time": "Get travel time and traffic information between two locations. Use when: 'how long to reach', 'travel time', 'distance', 'how far is', 'what's the traffic', 'commute time'. Input: 'origin to destination' (e.g., 'Pisoli Pune to Kondhwa Pune')",
    
    "control_home_automation": 'Control smart home devices (lights, fans, zero light etc). ALWAYS use for: turn on/off light, fan, or any device. Queries: turn on light, turn off fan, light on, fan off, device status. Format: "status" or "control|device_name:true"',
    
    "play_youtube_music_song": "Play specific song on YouTube Music. Use for: 'play Bohemian Rhapsody', 'play Beatles song'",
    "play_youtube_music_playlist": "Play themed playlist on YouTube Music. Use for: 'play romantic songs', 'play workout playlist'",
    "play_youtube_music_artist": "Play all songs by artist on YouTube Music. Use for: 'play Beatles', 'play Taylor Swift'",
    "control_youtube_music_playback": "Control YouTube Music playback (pause, resume, next, previous, stop)",
    
    "play_spotify_track": "Play specific track on Spotify (ONLY if explicitly requested)",
    "play_spotify_album": "Play album on Spotify (ONLY if explicitly requested)",
    "play_spotify_artist": "Play artist on Spotify (ONLY if explicitly requested)",
    "control_spotify_playback": "Control Spotify playback (ONLY if user says 'on Spotify')",
    
    "search_web": "Search the web for live data. Use for: latest, current, trending, prices, news, weather, updates",
    "search_amazon_single_product": "Search single product on Amazon with details",
    "search_amazon_multi_product": "Search multiple products on Amazon for comparison",
    "track_amazon_orders": "Track Amazon order status",
    
    "set_reminder": "Set a reminder for user. Include time and what to remind about",
    "list_reminders": "Show all active reminders",
    "cancel_reminder": "Cancel a specific reminder",
    "check_reminders": "Check if any reminders are active",
    
    "schedule_event": "Schedule a DAILY recurring event at specific time. Use when: 'schedule at 9 AM', 'event at 2 PM', 'every day at'. Format input as: 'time|instruction|event_id'. Examples: '9:00 AM|Say good morning|morning', '2 PM|Ask about work|afternoon'",
    
    "send_telegram_message": "Send telegram message. Input: recipient name and message text",
    "send_telegram_photo": "Send photo via Telegram. Input: recipient name and photo description",
    "send_telegram_document": "Send document via Telegram. Input: recipient name and document info",
    "send_telegram_video": "Send video via Telegram. Input: recipient name and video description",
    
    "control_system_volume": "Control system volume (increase, decrease, mute, set level)",
    
    "zepto_ordering_tool": "SHOPPING TOOL: Search products, add to cart, checkout. Actions: login|clear_cart|search|product|add_product|item|qty|index|order_details|checkout|place_order|cleanup",
    "zepto_order_history": "BROWSE PAST: Show completed orders history. Use ONLY when user says 'my orders' or 'order history'.",
    "zepto_order_again": "QUICK REORDER: Reorder by index (0=recent). Use when user says 'order again'.",
    "zepto_track_orders": "DELIVERY STATUS: Check where order is and ETA. Use when user asks 'where', 'track', 'delivery'.",
    
    "ask_follow_up_question": "Ask user a follow-up question to clarify intent",
}

# Base prompt sections that are always included
BASE_LANGUAGE_RULES = """
always respond in same language as per user query language.
default location is Pune, India (for weather, timezone, local context)
RESPONSE RULES
- Keep responses short, clear, and conversational
- Use simple spoken language
- No special characters
- Never ask questions in response text use follow_up_question tool instead
- Always use tools for actions, never say "I am unable to" perform actions
- Reference conversation history for context
- Before using any tool, Always check latest user intent from conversation history

QUESTIONS
- If clarification is required, ALWAYS use ask_follow_up_question tool
- If you want to offer help or suggestions, ALWAYS use ask_follow_up_question tool for listening to user response
- Any response that needs a question MUST use the tool
"""

ZEPTO_RULES = """ZEPTO SHOPPING - AGENT IMPLEMENTATION GUIDE

⚡ CRITICAL WORKFLOW FOR ALL ZEPTO REQUESTS (order/buy/shop/grocery):

STEP 1: ALWAYS CHECK DATABASE FIRST
- Call: zepto_ordering_tool with input "get_latest"
- This returns database status of any incomplete order
- Response will tell you whether to resume or start fresh

IF RESPONSE = "No incomplete orders found":
→ Proceed to STEP 2 (Fresh Order)

IF RESPONSE = "INCOMPLETE ZEPTO ORDER FOUND":
→ Ask user: "I found your incomplete order with [items] at ₹[price]. Should I continue?"
→ If YES: Resume from the current_task mentioned in response
→ If NO: Call zepto_ordering_tool with "clear_cart" to start fresh

STEP 2: FRESH ORDER WORKFLOW
1. zepto_ordering_tool|login
2. zepto_ordering_tool|search|product_name  
3. Ask user which product (0-5): use ask_follow_up_question
4. zepto_ordering_tool|add_product|product_name|quantity|index
5. Ask: "Anything else?" (keep adding items)
6. zepto_ordering_tool|order_details  
7. zepto_ordering_tool|checkout
8. Ask confirmation: "Should I place the order?"
9. zepto_ordering_tool|place_order
10. zepto_ordering_tool|cleanup

STEP 3: RESUMING INCOMPLETE ORDER
- Get current_task from database response
- If current_task is "searching": Resume search
- If current_task is "item_added": Show cart (order_details) and ask for more items
- If current_task is "checkout": Go to payment
- If current_task is "payment_confirmation": Confirm and place order
- Continue from there with remaining steps

OTHER REQUESTS:
- "my orders" / "order history" → zepto_order_history
- "order again" → zepto_order_again[index]  
- "track order" → zepto_track_orders

CRITICAL RULES:
1. NEVER skip the "get_latest" check - ALWAYS call it first
2. If incomplete order exists, MUST ask user before resuming
3. Only start fresh if no incomplete order OR user explicitly says 'new order'
4. Show prices with ₹, format responses conversationally
5. Always use ask_follow_up_question for user choices
6. Default payment: Cash on Delivery (COD)
"""

MUSIC_RULES = """MUSIC PLAYBACK

YOUTUBE MUSIC (DEFAULT)
FOR ANY MUSIC PLAYBACK REQUESTS
If user says: play, resume, pause, stop, next, skip (without mentioning Spotify)
→ ALWAYS use YouTube Music tools instead of Spotify

Available tools:
- play_youtube_music_song: Play specific song
- play_youtube_music_artist: Play all songs by artist
- play_youtube_music_playlist: Play themed playlist
- control_youtube_music_playback: Control playback

Mappings:
- play or resume → resume
- pause or stop → pause
- next or skip → next
- previous or back → previous

SPOTIFY PLAYBACK (ONLY IF EXPLICITLY REQUESTED)
FOR SPOTIFY-SPECIFIC MUSIC REQUESTS
If user says: "on Spotify", "from Spotify", "using Spotify", "Spotify [song]"
→ Use Spotify tools instead of YouTube Music

Mappings:
- play or resume → resume
- pause or stop → pause
- next or skip → next

For specific content:
- Track → play_spotify_track
- Album → play_spotify_album
- Artist → play_spotify_artist
"""

WEB_SEARCH_RULES = """WEB SEARCH (MANDATORY FOR LIVE DATA)
- ALWAYS use search_web when user asks for: latest, current, today, live, trending, right now, prices, updates
- Never answer live data from memory
- Pass only the raw search query string
"""

AMAZON_RULES = """AMAZON PRODUCT SEARCH RULES
When user wants to search for products on Amazon:
- Use search_amazon_single_product for specific product details (price, rating, URL)
- Use search_amazon_multi_product to show comparison of multiple options
- ALWAYS include product URLs in response (for saved history)
- Format results clearly: Product Name, Price, Rating, Reviews, URL
- Track amazon order status with amazon_order_tracking_tool when user asks about order tracking
- Always ask follow-up if user needs more details about specific product
- Provide 2-3 top recommendations for browsing
- Include direct Amazon links for easy purchase
"""

HOME_AUTOMATION_RULES = """HOME AUTOMATION AND DEVICE CONTROL
When user wants to control smart home devices (lights, fans, AC, etc):
- ALWAYS use control_home_automation tool for ANY device control request
- Recognize these patterns in ENGLISH: "turn on/off", "switch on/off", "lights on/off", "fan on/off", "device on/off", "status"
- Recognize these patterns in HINDI: "चालू करो" (chaalu karo = turn on), "बंद करो" (band karo = turn off), "स्थिति" (status), (work/device related)
- Examples in English: "turn on the light", "switch off the fan", "is the AC on"
- Examples in HINDI: "रोशनी चालू करो", "पंखा बंद करो", "डिवाइस की स्थिति"
- Always confirm the action taken
- Include device status in response
- For device names, extract from user input (light, fan, AC, door, etc)
"""

TRAVEL_RULES = """TRAVEL TIME AND TRAFFIC

When user asks about travel time, distance, or traffic:
- Use get_travel_time tool to fetch real-time traffic information
- Input format: 'origin to destination' (e.g., 'Pisoli Pune to Kondhwa Pune')
- Provide estimated travel time and traffic conditions
- Include relevant alerts (heavy traffic, delays, best route)
- Always provide current traffic status
- For multiple route options, ask user their preference
- Mention alternate routes if available

Examples:
- "How long to reach Hinjewadi from Pune?" → Use get_travel_time with "Pune to Hinjewadi"
- "What's the traffic on my route?" → Ask for source and destination, then use tool
- "Travel time from home to office?" → Ask for specific locations first
"""

EVENT_SCHEDULING_RULES = """EVENT SCHEDULING - DAILY AUTOMATION

Use schedule_event when user says: "schedule event", "every day at [time]", "turn on light at [time]"

INPUT FORMAT: "time|prompt|event_id"

FIELDS:
- TIME: "9:00 AM" or "09:00" (24-hour format)
- PROMPT: Clear instruction (e.g., "Say good morning", "Turn on the light")
- EVENT_ID: Unique ID using underscores (e.g., morning, evening_light_on)

EXAMPLES:
- "schedule at 9 AM to say good morning" → schedule_event|9:00 AM|Say good morning|morning
- "turn on light at 6 PM" → schedule_event|6:00 PM|Turn on the light|evening_light_on
- "play music at 7 AM" → schedule_event|7:00 AM|Play morning music|morning_music

REMINDERS VS EVENTS:
- "remind me to call mom in 30 min" → set_reminder (one-time, temporary)
- "call mom at 10 AM daily" → schedule_event (daily, permanent)
"""

TELEGRAM_RULES = """TELEGRAM - Share/Send via Telegram
Available: send_telegram_message, send_telegram_photo, send_telegram_document, send_telegram_video
Use when user wants to share/send/post anything on Telegram.
"""

class DynamicPromptGenerator:
    """Generate custom prompts based on detected tool requirements using LLM-based intent detection"""
    
    def __init__(self, use_llm=True, model="gpt-4o-mini"):
        self.tool_descriptions = TOOL_DESCRIPTIONS
        self.use_llm = use_llm
        self.model = model
        
        # OPTIMIZATION: Cache tool descriptions (generated once, reused for all requests)
        self._cached_tools_list = "\n".join([
            f"- {tool}: {desc}" 
            for tool, desc in self.tool_descriptions.items()
        ])
        logger.info(f"Tool descriptions cached: {len(self._cached_tools_list)} chars")
        
        # Initialize LLM for intent detection (gpt-4o-mini for speed and cost efficiency)
        if use_llm:
            try:
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    logger.warning("OPENAI_API_KEY not found. LLM-based tool detection requires valid API key.")
                    self.use_llm = False
                    self.llm = None
                else:
                    self.llm = ChatOpenAI(
                        model=model,
                        temperature=0,
                        api_key=api_key,
                        timeout=5  # Fast timeout for tool selection
                    )
                    logger.info(f" LLM initialized: {model}")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM: {e}. LLM-based tool detection will not be available.")
                self.use_llm = False
                self.llm = None
        else:
            self.llm = None
    
    def _llm_detect_required_tools(self, user_input: str) -> Tuple[Set[str], str]:
        """
        Use LLM to detect which tools are needed AND the language of the input
        More semantically intelligent than keyword matching
        
        Args:
            user_input: User's command/question
            
        Returns:
            Tuple of (Set of tool names, language flag: 'hindi' or 'english')
        """
        if not self.llm:
            return set(), 'english'
        
        try:
            # OPTIMIZATION: Use cached tools list (generated once in __init__)
            prompt = f"""Detect language and select required tools for this request.

Request: "{user_input}"

Tools: {self._cached_tools_list}

TASK:
- Line 1: LANGUAGE: HINDI or ENGLISH
- Next lines: Selected tool names only (no explanations)

SELECTION RULES:
- Music: Spotify if mentioned, else YouTube Music
- Shopping: Zepto for groceries, Amazon for products
- Home: Any control/device/light/fan → control_home_automation
- Travel: distance/traffic/commute → get_travel_time
- Schedule: daily/event/time → schedule_event
- Reminders: remind/notification → reminder tools

LANGUAGE: """
            
            response = self.llm.invoke([HumanMessage(content=prompt)])
            lines = response.content.strip().split('\n')
            
            # Parse language from first line
            language = 'english'  # default
            tools_start_idx = 0
            
            if lines and 'LANGUAGE:' in lines[0].upper():
                lang_line = lines[0].upper()
                if 'HINDI' in lang_line:
                    language = 'hindi'
                    tools_start_idx = 1
                elif 'ENGLISH' in lang_line:
                    language = 'english'
                    tools_start_idx = 1
            
            # Parse tool names from remaining lines
            detected_tools = set()
            for tool_name in lines[tools_start_idx:]:
                tool_name = tool_name.strip().strip('-').strip()
                if tool_name and tool_name in self.tool_descriptions:
                    detected_tools.add(tool_name)
            
            # Ensure minimum set of tools (LLM should include these but enforce as safety)
            detected_tools.add("ask_follow_up_question")
            detected_tools.add("search_web")
         
            
            # Log detection
            logger.debug(f"LLM detected: Language={language}, Tools={sorted(detected_tools)} for '{user_input}'")
            
            return detected_tools, language
            
        except Exception as e:
            logger.error(f"LLM detection failed: {e}")
            raise RuntimeError(f"Tool detection failed: {e}")
    

    
    def detect_required_tools(self, user_input: str) -> Tuple[Set[str], str]:
        """
        Detect which tools are needed based on user input using LLM
        LLM analyzes the query and selects appropriate tools
        
        Args:
            user_input: User's command/question
            
        Returns:
            Tuple of (Set of tool names, language: 'hindi' or 'english')
            
        Raises:
            RuntimeError: If LLM is not initialized or detection fails
        """
      
        
        # PRIORITY 2: Always use LLM for accurate tool detection
        if not self.use_llm or not self.llm:
            raise RuntimeError(
                "LLM-based tool detection is disabled or not initialized. "
                "Please set use_llm=True and ensure OPENAI_API_KEY is configured."
            )
        
        detected_tools, llm_language = self._llm_detect_required_tools(user_input)
        if not detected_tools:
            raise RuntimeError(f"LLM failed to detect tools for input: {user_input}")
        
        # Use detected language (from language detection, not LLM's language detection)
        return detected_tools, llm_language
    
    def generate_custom_prompt(self, user_input: str, detected_tools: Set[str] = None, language: str = None) -> Tuple[str, List[str], str]:
        """
        Generate a custom prompt based on detected tools and language
        
        Args:
            user_input: User's command/question
            detected_tools: Optional set of tool names to include. If None, will detect automatically.
            language: Optional language flag ('hindi' or 'english'). If None, will detect automatically.
            
        Returns:
            Tuple of (custom_prompt, tool_names_list, language_flag)
        """
        if detected_tools is None:
            detected_tools, language = self.detect_required_tools(user_input)
        elif language is None:
            # If tools provided but not language, detect language from input
            devanagari_count = sum(1 for c in user_input if '\u0900' <= c <= '\u097F')
            language = 'hindi' if devanagari_count > 5 else 'english'
        # Start with base sections
        prompt_sections = [
            f"You are Sofi, a female voice assistant based in pisoli, Pune, India today {datetime.now().strftime('%B %d, %Y')}.\n",
            f"always respond in the {language} language.\n",
            BASE_LANGUAGE_RULES,
        ]
        
        tool_descriptions_for_tools = []
        
        # Add relevant rules based on detected tools
        if any("control_home_automation" in tool for tool in detected_tools):
            prompt_sections.append("\n" + HOME_AUTOMATION_RULES)
        
        if any("spotify" in tool for tool in detected_tools):
            prompt_sections.append("\n" + MUSIC_RULES)
        elif any("youtube_music" in tool for tool in detected_tools):
            prompt_sections.append("\n" + MUSIC_RULES)
        
        if any("zepto" in tool for tool in detected_tools):
            prompt_sections.append("\n" + ZEPTO_RULES)
        
        if any("amazon" in tool or "amazon_order" in tool for tool in detected_tools):
            prompt_sections.append("\n" + AMAZON_RULES)
        
        if any("search_web" in tool for tool in detected_tools):
            prompt_sections.append("\n" + WEB_SEARCH_RULES)
        
        if any("get_travel_time" in tool for tool in detected_tools):
            prompt_sections.append("\n" + TRAVEL_RULES)
        
        if any("schedule_event" in tool for tool in detected_tools):
            prompt_sections.append("\n" + EVENT_SCHEDULING_RULES)
        
        if any("send_telegram" in tool or "telegram" in tool for tool in detected_tools):
            prompt_sections.append("\n" + TELEGRAM_RULES)
        
        # Add tool descriptions
        prompt_sections.append("\nAVAILABLE TOOLS\n")
        for tool in sorted(detected_tools):
            if tool in self.tool_descriptions:
                prompt_sections.append(f"- {tool}: {self.tool_descriptions[tool]}")
                tool_descriptions_for_tools.append(tool)
        
        # Add capabilities section
        capabilities = sorted(list(detected_tools))
        prompt_sections.append(f"\n\nCAPABILITIES:\n{', '.join(capabilities)}")
        
        custom_prompt = "\n".join(prompt_sections)
        
        return custom_prompt, sorted(list(detected_tools)), language
    
    def create_filtered_tool_list(self, all_tools: List[BaseTool], tool_names: List[str]) -> List[BaseTool]:
        """
        Filter tools based on required tool names
        
        Args:
            all_tools: List of all available tools
            tool_names: List of tool names to keep
            
        Returns:
            Filtered list of tools
        """
        tool_name_set = set(tool_names)
        return [tool for tool in all_tools if tool.name in tool_name_set]


def create_focused_prompt(user_input: str, all_tools: List[BaseTool]) -> Tuple[str, List[BaseTool], str]:
    """
    Convenience function to generate focused prompt and tools for a user input
    
    Args:
        user_input: User's command/question
        all_tools: List of all available tools
        
    Returns:
        Tuple of (custom_prompt, filtered_tools, language)
    """
    generator = DynamicPromptGenerator()
    custom_prompt, tool_names, language = generator.generate_custom_prompt(user_input)
    filtered_tools = generator.create_filtered_tool_list(all_tools, tool_names)
    
    return custom_prompt, filtered_tools, language


if __name__ == "__main__":
    # Test the generator
    generator = DynamicPromptGenerator()
    
    # Test cases
    test_inputs = [
     
        "please send me the images on telegram",
       
    ]
    
    for test_input in test_inputs:
        tools, llm_language = generator.detect_required_tools(test_input)
        prompt, tool_names, language = generator.generate_custom_prompt(test_input, tools)
        # print(f"\nInput: {test_input}")
        # print(f"Detected tools: {tool_names}")
        print(f"Detected language: {language}")
        print(f"Prompt length: {(prompt)} chars")
        print("---")
