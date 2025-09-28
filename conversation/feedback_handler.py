import time
import threading
import random


class FeedbackHandler:
    def __init__(self, audio_processors):
        """Initialize FeedbackHandler with audio processors for speech output."""
        self.audio_processors = audio_processors

    def give_processing_feedback(self, tool_type, query_hint=""):
        """Provide immediate feedback while processing different types of requests"""
        
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
