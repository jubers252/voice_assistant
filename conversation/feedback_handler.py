import time
import threading
import random


class FeedbackHandler:
    def __init__(self, audio_processors):
        """Initialize FeedbackHandler with audio processors for speech output."""
        self.audio_processors = audio_processors

    def give_processing_feedback(self, tool_type, query_hint=""):
        """Provide immediate feedback while processing AI agent requests"""
        
        # Only keep langchain_agent feedback messages since we're using AI agent for everything
        feedback_messages = {
            "langchain_agent": [
                "I'm processing your request",
                "Let me think about that",
                "Working on your request",
                "I'm analyzing what you need",
                "Processing your command",
                "Let me help you with that",
                "I'm working on it",
                "Give me a moment to process that"
            ]
        }
        
        # Get appropriate message for the agent
        messages = feedback_messages.get("langchain_agent", ["I'm working on your request"])
        
        # Select context-aware message based on query content
        if query_hint:
            query_lower = query_hint.lower()
            if any(word in query_lower for word in ["weather", "temperature", "forecast"]):
                message = "Let me check the weather for you"
            elif any(word in query_lower for word in ["amazon", "product", "buy", "order"]):
                message = "Let me search for that product"
            elif any(word in query_lower for word in ["music", "play", "spotify", "song"]):
                message = "Let me handle your music request"
            elif any(word in query_lower for word in ["search", "find", "look up"]):
                message = "Let me search for that information"
            elif any(word in query_lower for word in ["telegram", "message", "send"]):
                message = "Let me send that for you"
            elif any(word in query_lower for word in ["reminder", "remind", "remember"]):
                message = "Let me set that reminder"
            else:
                # Use random message for variety
                message = random.choice(messages)
        else:
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
            """Give feedback after 10 seconds if action is still running"""
            nonlocal feedback_given
            time.sleep(20)  # Wait 15 seconds
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
