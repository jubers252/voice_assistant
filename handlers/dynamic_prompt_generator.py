"""
Dynamic Prompt Generator for Voice Assistant
Generates custom prompts based on tools required for user's request
"""

import re
from typing import Dict, List, Tuple, Set
from langchain_core.tools import BaseTool

# Tool-to-keywords mapping (English + Romanized Hindi/Hinglish)
# Keywords are combined so both English and Hindi (Romanized) queries work
# Example: "play" (English) and "bajao" (Hindi) will both match music tools
TOOL_KEYWORDS = {
    # Weather tools
    "get_current_weather": ["weather", "mausam", "vedar","tapman", "temperature", "cold", "hot", "raining", "rain", "sunny", "cloudy", "forecast",
                            "thandi", "garam", "barish", "dhoop", "badal"],
    "get_weather_forecast": ["forecast", "tomorrow", "next day", "week", "rain tomorrow", "weather tomorrow",
                             "pehle din", "kal", "agle hfte", "kal ki barish"],
    "get_timezone": ["timezone", "time in", "what time is it in", "current time", "time zone", "time",
                     "samay", "kaunsa samay", "vartman samay"],
    
    # Travel and traffic
    "get_travel_time": ["travel time", "how long", "distance", "how far", "traffic", "reach", "commute", "route",
                        "safar", "kitni dur", "time lagega", "raasta", "traffic jam", "jam"],
    
    # Home automation
    "control_home_automation": ["light", "fan", "zero", "device", "turn on", "turn off", "automation", "smart home", "devices",
                                "roshni", "bulb", "pankha", "switch on", "switch off", "band karo", "kholo"],
    
    # Music - YouTube (default)
    "play_youtube_music_song": ["play", "music", "song", "resume", "artist",
                                "bajao", "gana", "sangeet", "repeat", "shuru karo"],
    "play_youtube_music_playlist": ["playlist", "play playlist", "romantic", "workout",
                                    "gaaon ki list", "pyar wale gane"],
    "play_youtube_music_artist": ["artist", "singer", "gayak"],
    "control_youtube_music_playback": ["pause", "stop", "next", "skip", "previous", "back",
                                       "roko", "band karo", "agle gane", "chhodo", "pichla"],
    
    # Music - Spotify (explicit)
    "play_spotify_track": ["spotify", "on spotify", "from spotify", "using spotify", "spotify songs",
                          "spotify par", "spotify se"],
    "play_spotify_album": ["spotify album", "spotify collection"],
    "play_spotify_artist": ["spotify artist", "spotify singer"],
    "control_spotify_playback": ["spotify"],
    
    # Search and Amazon
    "search_web": ["search", "news", "latest", "current", "trending", "right now", "live", "prices", "updates",
                   "khoj", "samachar", "nayi", "abhi", "dam", "tulna"],
    "search_amazon_single_product": ["amazon", "product", "price", "compare", "rating",
                                     "maal", "kimat", "daim", "star"],
    "search_amazon_multiple_products": ["amazon", "compare", "options",
                                    "tulna karo", "vikal"],
    "track_amazon_orders": ["amazon order", "track order", "order status",
                          "order kahan hai", "delivery kab hogi", "amazon"],
    
    # Reminders
    "set_reminder": ["remind", "reminder", "set reminder", "remember", "schedule",
                     "yaad dilao", "alarm", "sudharo", "yaad rakho"],
    "list_reminders": ["list reminders", "show reminders", "my reminders",
                       "sare reminders", "mere reminders"],
    "cancel_reminder": ["cancel reminder", "delete reminder", "remove reminder",
                       "reminder hatao", "mita do"],
    "check_reminders": ["check reminder", "any reminders", "do i have reminders",
                       "reminder hai", "kuch yaad hai"],
    
    # Scheduled Events
    "schedule_event": ["schedule event", "schedule at", "set event", "add event","event", "schedule", "recurring event", "daily event",
                       "every day at", "at 9 am", "at 10 am", "at 2 pm", "at 6 pm", "at noon", "at midnight",
                       "schedule at", "set daily", "recurring reminder",
                       "event at", "reminder daily", "daily check",
                       "yojana banao", "har din", "schedule karo", "yaad rakhna"],
    
    # Telegram
    "send_telegram_message": ["telegram", "message", "send message", "whatsapp", "chat",
                             "sandesh", "bhejo", "msg", "baat karo", "mobile", "phone"],
    "send_telegram_photo": ["telegram photo", "send photo", "share photo",
                           "tasveer", "photo", "shaare karo", "mobile", "phone"],
    "send_telegram_document": ["telegram document", "send document", "share document",
                              "dastavez", "file", "mobile", "phone"],
    "send_telegram_video": ["telegram video", "send video", "share video",
                           "video", "mobile", "phone"],
    
    # Volume
    "control_system_volume": ["volume", "mute", "unmute", "loud", "quiet", "increase", "decrease",
                       "awaaz", "sound", "kum", "zyada", "sunao"],
    
    # Zepto shopping
    "zepto_ordering_tool": ["jaipur","zepto", "grocery", "order", "shopping", "buy", "milk", "bread", "vegetables",
                       "kirana", "mangwao", "delivery"],

    "zepto_order_history": ["jaipur","order history", "past orders", "previous orders",
                           "pehle se order"],
    "zepto_order_again": ["jaipur","order again", "reorder", "same order",
                         "phir se order karo"],
    "zepto_track_orders": ["jaipur","track order", "order status", "delivery", "track",
                          "track karo", "delivery kab", "kahaan hai order"],
    
    # Follow-up questions
    "ask_follow_up_question": ["which", "what", "prefer", "like", "choose", "select",
                              "kaun sa", "kaunsa", "pasand", "chuno"],
}

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
BASE_LANGUAGE_RULES = """LANGUAGE
Hindi input → respond only in हिंदी देवनागरी
English input → respond only in English
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
- For "latest" products, use search_web first then refine with Amazon search
- Always ask follow-up if user needs more details about specific product
- Provide 2-3 top recommendations for browsing
- Include direct Amazon links for easy purchase
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

class DynamicPromptGenerator:
    """Generate custom prompts based on detected tool requirements"""
    
    def __init__(self):
        self.tool_keywords = TOOL_KEYWORDS
        self.tool_descriptions = TOOL_DESCRIPTIONS
    
    def detect_required_tools(self, user_input: str) -> Set[str]:
        """
        Detect which tools are likely needed based on user input
        
        Args:
            user_input: User's command/question
            
        Returns:
            Set of tool names that match the user's intent
        """
        user_input_lower = user_input.lower()
        detected_tools = set()
        
        # Score each tool based on keyword matches
        tool_scores = {}
        
        for tool_name, keywords in self.tool_keywords.items():
            score = 0
            for keyword in keywords:
                if keyword in user_input_lower:
                    score += 1
            
            if score > 0:
                tool_scores[tool_name] = score
        
        # Sort by score and take top matches
        if tool_scores:
            # Take tools with score > 0
            detected_tools = set(tool for tool, score in tool_scores.items() if score > 0)
        
        # Special handling: if Zepto mentioned, include all Zepto tools
        if "zepto" in user_input_lower or "grocery" in user_input_lower or "order" in user_input_lower:
            detected_tools.update([
                "zepto_ordering_tool",
                "zepto_order_history",
                "zepto_order_again",
                "zepto_track_orders"
            ])

        if "amazon" in user_input_lower or "order" in user_input_lower or "track" in user_input_lower:
            detected_tools.update([
                "search_amazon_single_product",
                "search_amazon_multiple_products",
                "track_amazon_orders"
            ])
        
        # Special handling: music defaults to YouTube
        if any(word in user_input_lower for word in ["play", "pause", "resume", "next", "skip"]):
            if "spotify" not in user_input_lower:
                # Default to YouTube Music
                detected_tools.update([
                    "play_youtube_music_song",
                    "play_youtube_music_playlist",
                    "play_youtube_music_artist",
                    "control_youtube_music_playback"
                ])
                # Remove Spotify tools
                detected_tools.discard("play_spotify_track")
                detected_tools.discard("play_spotify_album")
                detected_tools.discard("play_spotify_artist")
                detected_tools.discard("control_spotify_playback")
        
        # Always include follow-up question tool (for clarification)
        detected_tools.add("ask_follow_up_question")
        
        # Always include telegram tools (for communication in any context)
        detected_tools.update([
            "send_telegram_message",
            "send_telegram_photo",
            "send_telegram_document",
            "send_telegram_video"
        ])
        
        # Add logging
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"✅ Detected tools for '{user_input_lower}': {sorted(detected_tools)}")
        
        return detected_tools
    
    def generate_custom_prompt(self, user_input: str, detected_tools: Set[str] = None) -> Tuple[str, List[str]]:
        """
        Generate a custom prompt based on detected tools
        
        Args:
            user_input: User's command/question
            detected_tools: Optional set of tool names to include. If None, will detect automatically.
            
        Returns:
            Tuple of (custom_prompt, tool_names_list)
        """
        if detected_tools is None:
            detected_tools = self.detect_required_tools(user_input)
        
        # Start with base sections
        prompt_sections = [
            "You are Sofi, a female voice assistant based in Pune, India.\n",
            BASE_LANGUAGE_RULES,
        ]
        
        tool_descriptions_for_tools = []
        
        # Add relevant rules based on detected tools
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
        
        return custom_prompt, sorted(list(detected_tools))
    
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


def create_focused_prompt(user_input: str, all_tools: List[BaseTool]) -> Tuple[str, List[BaseTool]]:
    """
    Convenience function to generate focused prompt and tools for a user input
    
    Args:
        user_input: User's command/question
        all_tools: List of all available tools
        
    Returns:
        Tuple of (custom_prompt, filtered_tools)
    """
    generator = DynamicPromptGenerator()
    custom_prompt, tool_names = generator.generate_custom_prompt(user_input)
    filtered_tools = generator.create_filtered_tool_list(all_tools, tool_names)
    
    return custom_prompt, filtered_tools


if __name__ == "__main__":
    # Test the generator
    generator = DynamicPromptGenerator()
    
    # Test cases
    test_inputs = [
     
        "order groceries from zepto",
       
    ]
    
    for test_input in test_inputs:
        tools = generator.detect_required_tools(test_input)
        prompt, tool_names = generator.generate_custom_prompt(test_input, tools)
        print(f"\nInput: {test_input}")
        print(f"Detected tools: {tool_names}")
        print(f"Prompt length: {(prompt)} chars")
        print("---")
