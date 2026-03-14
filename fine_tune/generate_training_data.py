#!/usr/bin/env python3
"""
Generate comprehensive training data for GPT-4o-mini fine-tuning
Based on ALL 26 tools from langchain_command_processor.py
"""

import json
import uuid
from typing import List, Dict


def generate_call_id():
    """Generate OpenAI-style call ID"""
    return f"call_{uuid.uuid4().hex[:24]}"


def create_tool_call(tool_name: str, arguments: dict) -> dict:
    """Create properly formatted tool call"""
    return {
        "id": generate_call_id(),
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(arguments, ensure_ascii=False)
        }
    }


def create_training_example(user_input: str, tool_name: str = None, arguments: dict = None, text_response: str = None):
    """Create a training example in OpenAI format"""
    messages = [{"role": "user", "content": user_input}]
    
    if tool_name and arguments is not None:
        # Assistant calls a tool
        messages.append({
            "role": "assistant",
            "tool_calls": [create_tool_call(tool_name, arguments)]
        })
    elif text_response:
        # Assistant gives text response
        messages.append({
            "role": "assistant",
            "content": text_response
        })
    
    return {"messages": messages}


def create_multi_turn_conversation(turns: List[Dict]) -> Dict:
    """
    Create multi-turn conversation example
    turns = [
        {"role": "user", "content": "..."},
        {"role": "assistant", "tool_calls": [...] or "content": "..."},
        {"role": "tool", "content": "...", "tool_call_id": "..."},  # tool response
        ...
    ]
    """
    return {"messages": turns}


def generate_all_training_data() -> List[Dict]:
    """Generate training data for all 26 tools"""
    
    training_data = []
    
    # ============ 1. WEATHER TOOLS ============
    # get_current_weather
    training_data.extend([
        create_training_example("जयपुर का मौसम कैसा है", "get_current_weather", {"location": "Jaipur"}),
        create_training_example("what's the weather in Mumbai", "get_current_weather", {"location": "Mumbai"}),
        create_training_example("दिल्ली में बारिश हो रही है क्या", "get_current_weather", {"location": "Delhi"}),
        create_training_example("temperature in Bangalore", "get_current_weather", {"location": "Bangalore"}),
        create_training_example("पुणे का तापमान बताओ", "get_current_weather", {"location": "Pune"}),
    ])
    
    # get_weather_forecast
    training_data.extend([
        create_training_example("कल मुंबई में मौसम कैसा रहेगा", "get_weather_forecast", {"location": "Mumbai"}),
        create_training_example("weather forecast for Delhi", "get_weather_forecast", {"location": "Delhi"}),
        create_training_example("अगले 3 दिन का मौसम बताओ चेन्नई", "get_weather_forecast", {"location": "Chennai"}),
    ])
    
    # get_timezone
    training_data.extend([
        create_training_example("न्यूयॉर्क में कितने बजे हैं", "get_timezone", {"location": "New York"}),
        create_training_example("what time is it in London", "get_timezone", {"location": "London"}),
        create_training_example("टोक्यो का टाइमज़ोन क्या है", "get_timezone", {"location": "Tokyo"}),
    ])
    
    # ============ 2. HOME AUTOMATION ============
    training_data.extend([
        create_training_example("light on karo", "control_home_automation", {"command": "control|light:true"}),
        create_training_example("लाइट बंद करो", "control_home_automation", {"command": "control|light:false"}),
        create_training_example("fan on", "control_home_automation", {"command": "control|fan:true"}),
        create_training_example("पंखा बंद करो", "control_home_automation", {"command": "control|fan:false"}),
        create_training_example("zero light on karo", "control_home_automation", {"command": "control|zero:true"}),
        create_training_example("light aur fan dono on karo", "control_home_automation", {"command": "control|light:true|fan:true"}),
        create_training_example("सभी devices बंद करो", "control_home_automation", {"command": "control|light:false|fan:false|zero:false"}),
        create_training_example("home devices status", "control_home_automation", {"command": "status"}),
        create_training_example("घर के उपकरणों की स्थिति बताओ", "control_home_automation", {"command": "status"}),
    ])
    
    # ============ 3. SPOTIFY TOOLS ============
    # play_spotify_track
    training_data.extend([
        create_training_example("play arijit singh songs", "play_spotify_track", {"track_name": "arijit singh songs"}),
        create_training_example("Shape of You बजाओ", "play_spotify_track", {"track_name": "Shape of You"}),
        create_training_example("play romantic songs", "play_spotify_track", {"track_name": "romantic songs"}),
        create_training_example("गाना चलाओ तुम हो", "play_spotify_track", {"track_name": "तुम हो"}),
    ])
    
    # play_spotify_album
    training_data.extend([
        create_training_example("play album Thriller", "play_spotify_album", {"album_name": "Thriller"}),
        create_training_example("album Kalank बजाओ", "play_spotify_album", {"album_name": "Kalank"}),
    ])
    
    # play_spotify_artist
    training_data.extend([
        create_training_example("play songs by Ed Sheeran", "play_spotify_artist", {"artist_name": "Ed Sheeran"}),
        create_training_example("Shreya Ghoshal के गाने बजाओ", "play_spotify_artist", {"artist_name": "Shreya Ghoshal"}),
    ])
    
    # control_spotify_playback
    training_data.extend([
        create_training_example("music pause karo", "control_spotify_playback", {"action": "pause"}),
        create_training_example("संगीत रोको", "control_spotify_playback", {"action": "pause"}),
        create_training_example("resume music", "control_spotify_playback", {"action": "resume"}),
        create_training_example("गाना फिर से चलाओ", "control_spotify_playback", {"action": "resume"}),
        create_training_example("next song", "control_spotify_playback", {"action": "next"}),
        create_training_example("अगला गाना", "control_spotify_playback", {"action": "next"}),
        create_training_example("spotify band karo", "control_spotify_playback", {"action": "pause"}),
    ])
    
    # ============ 4. WEB SEARCH ============
    training_data.extend([
        create_training_example("latest news search karo", "search_web", {"query": "latest news"}),
        create_training_example("आज की ताज़ा खबरें खोजो", "search_web", {"query": "आज की ताज़ा खबरें"}),
        create_training_example("Bitcoin price today", "search_web", {"query": "Bitcoin price today"}),
        create_training_example("भारत में कोरोना के मामले", "search_web", {"query": "भारत में कोरोना के मामले"}),
        create_training_example("trending topics", "search_web", {"query": "trending topics"}),
    ])
    
    # ============ 5. AMAZON TOOLS ============
    # COMPLETE AMAZON WORKFLOWS
    
    # Workflow: Amazon product search with clarification
    amazon_search_call = create_tool_call("ask_follow_up_question", {
        "input_text": "कृपया बताइए, कौन सा हेडफोन चाहिए? जैसे Sony, JBL, Boat आदि?"
    })
    amazon_product_call = create_tool_call("search_amazon_single_product", {"query": "Sony WH-1000XM4"})
    
    training_data.append(create_multi_turn_conversation([
        {"role": "user", "content": "amazon se headphones order karo"},
        {"role": "assistant", "tool_calls": [amazon_search_call]},
        {"role": "tool", "content": "User's answer: Sony wala latest model", "tool_call_id": amazon_search_call["id"]},
        {"role": "assistant", "tool_calls": [amazon_product_call]},
        {"role": "tool", "content": "Sony WH-1000XM4: ₹24,990, Rating: 4.5/5, 15,234 reviews", "tool_call_id": amazon_product_call["id"]},
        {"role": "assistant", "content": "Sony WH-1000XM4 हेडफोन मिल गया। कीमत ₹24,990 है और रेटिंग 4.5 स्टार है।"}
    ]))
    
    # Simple Amazon examples
    training_data.extend([
        create_training_example("amazon pe iPhone 15 ki details dikhao", "search_amazon_single_product", {"query": "iPhone 15"}),
        create_training_example("Sony headphones price on amazon", "search_amazon_single_product", {"query": "Sony headphones"}),
        create_training_example("laptop Dell Inspiron की जानकारी", "search_amazon_single_product", {"query": "Dell Inspiron laptop"}),
    ])
    
    # search_amazon_multiple_products
    training_data.extend([
        create_training_example("amazon par wireless earbuds compare karo", "search_amazon_multiple_products", {"query": "wireless earbuds"}),
        create_training_example("best running shoes on amazon", "search_amazon_multiple_products", {"query": "running shoes"}),
        create_training_example("स्मार्टवॉच के विकल्प दिखाओ", "search_amazon_multiple_products", {"query": "smartwatch"}),
    ])
    
    # track_amazon_orders
    training_data.extend([
        create_training_example("पिछले 5 दिनों के amazon orders दिखाओ", "track_amazon_orders", {"days_input": "5"}),
        create_training_example("my recent amazon orders", "track_amazon_orders", {"days_input": "7"}),
        create_training_example("track my amazon packages", "track_amazon_orders", {"days_input": "5"}),
        create_training_example("last week ke orders check karo", "track_amazon_orders", {"days_input": "7"}),
    ])
    
    # ============ 6. REMINDER TOOLS ============
    # set_reminder
    training_data.extend([
        create_training_example("कल सुबह 8 बजे दवा लेने का reminder लगाओ", "set_reminder", {"reminder_input": "दवा लेना|tomorrow 8 AM|once"}),
        create_training_example("remind me to call mom in 30 minutes", "set_reminder", {"reminder_input": "call mom|in 30 minutes|once"}),
        create_training_example("daily morning 7 AM wake up alarm", "set_reminder", {"reminder_input": "wake up|7 AM|daily"}),
        create_training_example("meeting reminder for 2 PM tomorrow", "set_reminder", {"reminder_input": "meeting|tomorrow at 2 PM|once"}),
        create_training_example("हर रोज़ शाम 6 बजे workout reminder", "set_reminder", {"reminder_input": "workout|6 PM|daily"}),
    ])
    
    # list_reminders
    training_data.extend([
        create_training_example("मेरे सभी reminders दिखाओ", "list_reminders", {}),
        create_training_example("show all my reminders", "list_reminders", {}),
        create_training_example("active reminders kya hain", "list_reminders", {}),
    ])
    
    # cancel_reminder
    training_data.extend([
        create_training_example("reminder number 2 cancel karo", "cancel_reminder", {"reminder_id": "2"}),
        create_training_example("delete reminder 5", "cancel_reminder", {"reminder_id": "5"}),
        create_training_example("पहला reminder हटाओ", "cancel_reminder", {"reminder_id": "1"}),
    ])
    
    # check_reminders
    training_data.extend([
        create_training_example("koi reminder due hai kya", "check_reminders", {}),
        create_training_example("check pending reminders", "check_reminders", {}),
        create_training_example("अभी कोई reminder है क्या", "check_reminders", {}),
    ])
    
    # ============ 7. TELEGRAM TOOLS ============
    # send_telegram_message
    training_data.extend([
        create_training_example("telegram pe message bhejo hello", "send_telegram_message", {"message": "hello"}),
        create_training_example("send telegram message I'm on my way", "send_telegram_message", {"message": "I'm on my way"}),
        create_training_example("टेलीग्राम पर भेजो मैं पहुंच रहा हूं", "send_telegram_message", {"message": "मैं पहुंच रहा हूं"}),
    ])
    
    # send_telegram_photo
    training_data.extend([
        create_training_example("send photo to telegram", "send_telegram_photo", {"photo_info": "/path/to/photo.jpg|Check this out"}),
        create_training_example("telegram pe photo bhejo", "send_telegram_photo", {"photo_info": "/home/user/image.png|यह देखो"}),
    ])
    
    # send_telegram_document
    training_data.extend([
        create_training_example("send document on telegram", "send_telegram_document", {"doc_info": "/path/to/doc.pdf|Important file"}),
        create_training_example("telegram par file bhejo", "send_telegram_document", {"doc_info": "/home/user/report.docx|रिपोर्ट"}),
    ])
    
    # send_telegram_video
    training_data.extend([
        create_training_example("send video to telegram", "send_telegram_video", {"video_info": "/path/to/video.mp4|Watch this"}),
        create_training_example("telegram pe video bhejo", "send_telegram_video", {"video_info": "/home/user/clip.mp4|यह देखो"}),
    ])
    
    # ============ 8. VOLUME CONTROL ============
    training_data.extend([
        create_training_example("volume badhao", "control_system_volume", {"command": "increase|5"}),
        create_training_example("आवाज़ कम करो", "control_system_volume", {"command": "decrease|5"}),
        create_training_example("volume 50 percent karo", "control_system_volume", {"command": "set||50"}),
        create_training_example("mute volume", "control_system_volume", {"command": "mute||"}),
        create_training_example("unmute karo", "control_system_volume", {"command": "unmute||"}),
        create_training_example("volume kitna hai", "control_system_volume", {"command": "status||"}),
        create_training_example("increase volume by 10", "control_system_volume", {"command": "increase|10"}),
        create_training_example("volume 70 percent", "control_system_volume", {"command": "set||70"}),
    ])
    
    # ============ 9. ZEPTO TOOLS ============
    # COMPLETE ZEPTO WORKFLOWS - Multi-turn conversations
    
    # Workflow 1: Simple order with product name
    zepto_call_1 = create_tool_call("zepto_ordering_tool", {"input_str": "login"})
    zepto_call_2 = create_tool_call("zepto_ordering_tool", {"input_str": "clear_cart"})
    zepto_call_3 = create_tool_call("zepto_ordering_tool", {"input_str": "search|Amul milk"})
    follow_up_call_1 = create_tool_call("ask_follow_up_question", {
        "input_text": "मिले 5 प्रोडक्ट: 0. Amul Taaza 500ml ₹28, 1. Amul Gold 500ml ₹32, 2. Amul Taaza 1L ₹54, 3. Amul Gold 1L ₹62, 4. Amul Cow Milk 500ml ₹30|कौन सा Amul milk और कितनी quantity चाहिए? प्रोडक्ट नंबर बताएं।"
    })
    zepto_call_4 = create_tool_call("zepto_ordering_tool", {"input_str": "add_product|Amul Taaza 500ml|2|0"})
    zepto_call_5 = create_tool_call("zepto_ordering_tool", {"input_str": "order_details"})
    zepto_call_6 = create_tool_call("zepto_ordering_tool", {"input_str": "checkout"})
    confirm_call = create_tool_call("ask_follow_up_question", {
        "input_text": "आपका ऑर्डर तैयार है। कुल राशि ₹56। Cash on Delivery सेलेक्ट है। क्या मैं ऑर्डर प्लेस कर दूं?"
    })
    zepto_call_7 = create_tool_call("zepto_ordering_tool", {"input_str": "place_order"})
    zepto_call_8 = create_tool_call("zepto_ordering_tool", {"input_str": "cleanup"})
    
    training_data.append(create_multi_turn_conversation([
        {"role": "user", "content": "zepto se Amul milk order karo"},
        {"role": "assistant", "tool_calls": [zepto_call_1]},
        {"role": "tool", "content": "Zepto login initiated.", "tool_call_id": zepto_call_1["id"]},
        {"role": "assistant", "tool_calls": [zepto_call_2]},
        {"role": "tool", "content": "Cart cleared.", "tool_call_id": zepto_call_2["id"]},
        {"role": "assistant", "tool_calls": [zepto_call_3]},
        {"role": "tool", "content": "Found 5 products: Amul Taaza 500ml ₹28, Amul Gold 500ml ₹32, Amul Taaza 1L ₹54, Amul Gold 1L ₹62, Amul Cow Milk 500ml ₹30", "tool_call_id": zepto_call_3["id"]},
        {"role": "assistant", "tool_calls": [follow_up_call_1]},
        {"role": "tool", "content": "User's answer: 0 wala 2 quantity", "tool_call_id": follow_up_call_1["id"]},
        {"role": "assistant", "tool_calls": [zepto_call_4]},
        {"role": "tool", "content": "Added 2x Amul Taaza 500ml to cart", "tool_call_id": zepto_call_4["id"]},
        {"role": "assistant", "tool_calls": [zepto_call_5]},
        {"role": "tool", "content": "Cart: 2x Amul Taaza 500ml, Total: ₹56", "tool_call_id": zepto_call_5["id"]},
        {"role": "assistant", "tool_calls": [zepto_call_6]},
        {"role": "tool", "content": "Checkout ready, COD selected", "tool_call_id": zepto_call_6["id"]},
        {"role": "assistant", "tool_calls": [confirm_call]},
        {"role": "tool", "content": "User's answer: haan kar do", "tool_call_id": confirm_call["id"]},
        {"role": "assistant", "tool_calls": [zepto_call_7]},
        {"role": "tool", "content": "Order placed successfully", "tool_call_id": zepto_call_7["id"]},
        {"role": "assistant", "tool_calls": [zepto_call_8]},
        {"role": "tool", "content": "Browser closed", "tool_call_id": zepto_call_8["id"]},
        {"role": "assistant", "content": "आपका Zepto ऑर्डर सफलतापूर्वक प्लेस हो गया है।"}
    ]))
    
    # Workflow 2: Order with generic product (needs clarification)
    zepto_2_call_1 = create_tool_call("zepto_ordering_tool", {"input_str": "login"})
    zepto_2_call_2 = create_tool_call("zepto_ordering_tool", {"input_str": "clear_cart"})
    follow_up_2_call = create_tool_call("ask_follow_up_question", {
        "input_text": "कौन सा milk चाहिए? जैसे Amul, Mother Dairy, Nestle आदि?"
    })
    zepto_2_call_3 = create_tool_call("zepto_ordering_tool", {"input_str": "search|Mother Dairy milk"})
    follow_up_2b_call = create_tool_call("ask_follow_up_question", {
        "input_text": "मिले 4 प्रोडक्ट: 0. Mother Dairy Full Cream 500ml ₹30, 1. Mother Dairy Toned 500ml ₹26, 2. Mother Dairy Full Cream 1L ₹58, 3. Mother Dairy Toned 1L ₹50|कौन सा और कितनी quantity?"
    })
    zepto_2_call_4 = create_tool_call("zepto_ordering_tool", {"input_str": "add_product|Mother Dairy Full Cream 500ml|1|0"})
    zepto_2_call_5 = create_tool_call("zepto_ordering_tool", {"input_str": "order_details"})
    zepto_2_call_6 = create_tool_call("zepto_ordering_tool", {"input_str": "checkout"})
    confirm_2_call = create_tool_call("ask_follow_up_question", {
        "input_text": "कुल राशि ₹30। COD सेलेक्ट है। ऑर्डर confirm करूं?"
    })
    zepto_2_call_7 = create_tool_call("zepto_ordering_tool", {"input_str": "place_order"})
    zepto_2_call_8 = create_tool_call("zepto_ordering_tool", {"input_str": "cleanup"})
    
    training_data.append(create_multi_turn_conversation([
        {"role": "user", "content": "order milk from zepto"},
        {"role": "assistant", "tool_calls": [zepto_2_call_1]},
        {"role": "tool", "content": "Zepto login initiated.", "tool_call_id": zepto_2_call_1["id"]},
        {"role": "assistant", "tool_calls": [zepto_2_call_2]},
        {"role": "tool", "content": "Cart cleared.", "tool_call_id": zepto_2_call_2["id"]},
        {"role": "assistant", "tool_calls": [follow_up_2_call]},
        {"role": "tool", "content": "User's answer: Mother Dairy wala", "tool_call_id": follow_up_2_call["id"]},
        {"role": "assistant", "tool_calls": [zepto_2_call_3]},
        {"role": "tool", "content": "Found 4 Mother Dairy products", "tool_call_id": zepto_2_call_3["id"]},
        {"role": "assistant", "tool_calls": [follow_up_2b_call]},
        {"role": "tool", "content": "User's answer: pehla wala 1", "tool_call_id": follow_up_2b_call["id"]},
        {"role": "assistant", "tool_calls": [zepto_2_call_4]},
        {"role": "tool", "content": "Added to cart", "tool_call_id": zepto_2_call_4["id"]},
        {"role": "assistant", "tool_calls": [zepto_2_call_5]},
        {"role": "tool", "content": "Cart total: ₹30", "tool_call_id": zepto_2_call_5["id"]},
        {"role": "assistant", "tool_calls": [zepto_2_call_6]},
        {"role": "tool", "content": "Ready for checkout", "tool_call_id": zepto_2_call_6["id"]},
        {"role": "assistant", "tool_calls": [confirm_2_call]},
        {"role": "tool", "content": "User's answer: yes", "tool_call_id": confirm_2_call["id"]},
        {"role": "assistant", "tool_calls": [zepto_2_call_7]},
        {"role": "tool", "content": "Order placed", "tool_call_id": zepto_2_call_7["id"]},
        {"role": "assistant", "tool_calls": [zepto_2_call_8]},
        {"role": "tool", "content": "Cleanup done", "tool_call_id": zepto_2_call_8["id"]},
        {"role": "assistant", "content": "Order placed successfully!"}
    ]))
    
    # Workflow 3: Multiple items order
    zepto_3_call_1 = create_tool_call("zepto_ordering_tool", {"input_str": "login"})
    zepto_3_call_2 = create_tool_call("zepto_ordering_tool", {"input_str": "clear_cart"})
    zepto_3_call_3 = create_tool_call("zepto_ordering_tool", {"input_str": "search|bread"})
    follow_3a = create_tool_call("ask_follow_up_question", {
        "input_text": "मिले products: 0. Britannia Bread ₹35, 1. Modern Bread ₹30, 2. Harvest Gold ₹32|कौन सा bread?"
    })
    zepto_3_call_4 = create_tool_call("zepto_ordering_tool", {"input_str": "add_product|Britannia Bread|2|0"})
    zepto_3_call_5 = create_tool_call("zepto_ordering_tool", {"input_str": "search|eggs"})
    follow_3b = create_tool_call("ask_follow_up_question", {
        "input_text": "Eggs: 0. Brown Eggs 6pc ₹45, 1. White Eggs 6pc ₹38, 2. Brown Eggs 12pc ₹88|कौन से eggs?"
    })
    zepto_3_call_6 = create_tool_call("zepto_ordering_tool", {"input_str": "add_product|Brown Eggs 6pc|1|0"})
    zepto_3_call_7 = create_tool_call("zepto_ordering_tool", {"input_str": "order_details"})
    zepto_3_call_8 = create_tool_call("zepto_ordering_tool", {"input_str": "checkout"})
    confirm_3 = create_tool_call("ask_follow_up_question", {
        "input_text": "कुल: 2x Britannia Bread + 1x Brown Eggs। राशि ₹115। Confirm?"
    })
    zepto_3_call_9 = create_tool_call("zepto_ordering_tool", {"input_str": "place_order"})
    zepto_3_call_10 = create_tool_call("zepto_ordering_tool", {"input_str": "cleanup"})
    
    training_data.append(create_multi_turn_conversation([
        {"role": "user", "content": "zepto se bread aur eggs order karo"},
        {"role": "assistant", "tool_calls": [zepto_3_call_1]},
        {"role": "tool", "content": "Logged in", "tool_call_id": zepto_3_call_1["id"]},
        {"role": "assistant", "tool_calls": [zepto_3_call_2]},
        {"role": "tool", "content": "Cart cleared", "tool_call_id": zepto_3_call_2["id"]},
        {"role": "assistant", "tool_calls": [zepto_3_call_3]},
        {"role": "tool", "content": "Found bread products", "tool_call_id": zepto_3_call_3["id"]},
        {"role": "assistant", "tool_calls": [follow_3a]},
        {"role": "tool", "content": "User's answer: Britannia 2", "tool_call_id": follow_3a["id"]},
        {"role": "assistant", "tool_calls": [zepto_3_call_4]},
        {"role": "tool", "content": "Added bread", "tool_call_id": zepto_3_call_4["id"]},
        {"role": "assistant", "tool_calls": [zepto_3_call_5]},
        {"role": "tool", "content": "Found eggs", "tool_call_id": zepto_3_call_5["id"]},
        {"role": "assistant", "tool_calls": [follow_3b]},
        {"role": "tool", "content": "User's answer: brown wale 6pc", "tool_call_id": follow_3b["id"]},
        {"role": "assistant", "tool_calls": [zepto_3_call_6]},
        {"role": "tool", "content": "Added eggs", "tool_call_id": zepto_3_call_6["id"]},
        {"role": "assistant", "tool_calls": [zepto_3_call_7]},
        {"role": "tool", "content": "Total ₹115", "tool_call_id": zepto_3_call_7["id"]},
        {"role": "assistant", "tool_calls": [zepto_3_call_8]},
        {"role": "tool", "content": "Checkout ready", "tool_call_id": zepto_3_call_8["id"]},
        {"role": "assistant", "tool_calls": [confirm_3]},
        {"role": "tool", "content": "User's answer: haan", "tool_call_id": confirm_3["id"]},
        {"role": "assistant", "tool_calls": [zepto_3_call_9]},
        {"role": "tool", "content": "Order placed", "tool_call_id": zepto_3_call_9["id"]},
        {"role": "assistant", "tool_calls": [zepto_3_call_10]},
        {"role": "tool", "content": "Done", "tool_call_id": zepto_3_call_10["id"]},
        {"role": "assistant", "content": "आपका ऑर्डर प्लेस हो गया।"}
    ]))
    
    # Individual zepto tool examples (for reference)
    training_data.extend([
        create_training_example("zepto order history dikhao", "zepto_order_history", {"max_orders": "3"}),
        create_training_example("पिछला zepto order फिर से करो", "zepto_order_again", {"order_index": "0"}),
        create_training_example("track my zepto deliveries", "zepto_track_orders", {"params": "3|none"}),
    ])
    
    # ============ 10. FOLLOW-UP QUESTIONS ============
    # ask_follow_up_question - Used when assistant needs clarification
    training_data.extend([
        # When user request is incomplete
        create_training_example("telegram pe message bhejo", "ask_follow_up_question", {"input_text": "कृपया बताइए, क्या संदेश भेजना है?"}),
        create_training_example("send message on telegram", "ask_follow_up_question", {"input_text": "कृपया बताइए, क्या संदेश भेजना है?"}),
        create_training_example("amazon se headphones order karo", "ask_follow_up_question", {"input_text": "कृपया बताइए, किस ब्रांड के हेडफोन चाहिए?"}),
        create_training_example("zepto se doodh order karo", "ask_follow_up_question", {"input_text": "कृपया बताइए, कौन सा दूध और कितनी मात्रा चाहिए?"}),
        create_training_example("reminder lagao", "ask_follow_up_question", {"input_text": "कृपया बताइए, किस समय और किस बात का रिमाइंडर लगाना है?"}),
        create_training_example("track my orders", "ask_follow_up_question", {"input_text": "कृपया बताइए, Amazon या Zepto के ऑर्डर देखना चाहते हैं?"}),
    ])
    
    # ============ 11. SIMPLE TEXT RESPONSES ============
    # Direct responses without tool calls
    training_data.extend([
        create_training_example("hello", text_response="नमस्ते! मैं आपकी कैसे मदद कर सकती हूँ?"),
        create_training_example("namaste", text_response="नमस्ते! मैं आपकी कैसे मदद कर सकती हूँ?"),
        create_training_example("thank you", text_response="आपका स्वागत है!"),
        create_training_example("धन्यवाद", text_response="आपका स्वागत है!"),
        create_training_example("good morning", text_response="शुभ प्रभात! आपका दिन शुभ हो।"),
        create_training_example("शुभ रात्रि", text_response="शुभ रात्रि! अच्छी नींद लें।"),
    ])
    
    return training_data


def main():
    print("=" * 60)
    print("  Generating Comprehensive Training Data")
    print("  Based on 26 tools from langchain_command_processor.py")
    print("=" * 60)
    print()
    
    # Generate all training data
    training_data = generate_all_training_data()
    
    # Write to file
    output_file = "sofi_comprehensive_training.jsonl"
    with open(output_file, 'w', encoding='utf-8') as f:
        for example in training_data:
            f.write(json.dumps(example, ensure_ascii=False) + '\n')
    
    print(f"✅ Generated {len(training_data)} training examples")
    print(f"✨ Saved to: {output_file}")
    print()
    
    # Show tool distribution
    print("Training examples by category:")
    tool_counts = {}
    for example in training_data:
        messages = example['messages']
        # Find first assistant message
        for msg in messages:
            if msg.get('role') == 'assistant':
                if 'tool_calls' in msg:
                    tool_name = msg['tool_calls'][0]['function']['name']
                    tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                elif 'content' in msg:
                    tool_counts['text_response'] = tool_counts.get('text_response', 0) + 1
                break  # Only count first assistant response per example
    
    for tool, count in sorted(tool_counts.items()):
        print(f"  {tool}: {count} examples")
    
    print()
    print("Next steps:")
    print(f"1. Review the file: {output_file}")
    print("2. Add more examples if needed")
    print("3. Run: python finetune_gpt4.py")
    print()


if __name__ == "__main__":
    main()
