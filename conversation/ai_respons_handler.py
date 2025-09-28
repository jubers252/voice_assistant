import time
import os
from openai import OpenAI
from conversation.conversation_manager import ConversationManager



class AIResponseHandler:
    def __init__(self, conversation_manager=None, audio_processors=None, recognizer=None):
        """Initialize AIResponseHandler with required components."""
        self.conversation_manager = conversation_manager if conversation_manager else ConversationManager()
        self.audio_processors = audio_processors
        self.recognizer = recognizer
        self.conversation_history = self.conversation_manager.conversation_history


    def get_ai_response(self, user_message, is_tool_response=False):
        """Get a formatted response from OpenAI for general conversation."""
        # Ensure user_message is always a string
        if not isinstance(user_message, str):
            user_message = str(user_message)
        
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # For tool responses, create a temporary conversation with the tool data
            if is_tool_response:
                temp_messages = self.conversation_history.copy()
                temp_messages.append({"role": "user", "content": f"Please summarize this information for the user in a natural, conversational way. Always respond in same language as user query. For Hindi queries, use proper Hindi Devanagari script (not Roman transliteration) for better text-to-speech pronunciation. Do not add any special characters in response, make it plain text with new line if required since response will be used for TTS: {user_message}"})
                messages_to_send = temp_messages
            else:
                # For regular conversation, add user message to history
                self.conversation_history.append({"role": "user", "content": user_message})
                # Add comprehensive TTS and language formatting instruction with context awareness
                temp_messages = self.conversation_history.copy()
                temp_messages.append({"role": "system", "content": "IMPORTANT RESPONSE GUIDELINES: 1) Use the conversation history to understand context and provide relevant answers to follow-up questions. 2) If the user refers to 'this', 'that', 'it', or asks follow-up questions, reference the previous conversation. 3) Respond in the same language as the user's query. 4) For Hindi queries, use proper Hindi Devanagari script (not Roman transliteration) for better text-to-speech pronunciation. 5) Use plain text only - no special characters, markdown, asterisks, or formatting. 6) Use simple punctuation only. 7) Keep responses concise and conversational for voice output. 8) This response will be converted to speech, so ensure it sounds natural when spoken aloud."})
                messages_to_send = temp_messages
            
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=messages_to_send,
                max_tokens=150,
                temperature=0.7
            )
            reply = response.choices[0].message.content.strip()
            
            # Add assistant response to conversation history
            self.conversation_history.append({"role": "assistant", "content": reply})
            self.conversation_manager.conversation_history = self.conversation_history
            self.conversation_manager.save_conversation_history()
            
            return reply
        except Exception as e:
            print(f"Error getting AI response: {e}")
            return "Sorry, I'm having trouble thinking right now."
        

    
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

    def handle_direct_response(self, tool_response, user_command):
        """Handle direct response from OpenAI without tools"""
        # Give feedback for complex conversational queries
        if any(keyword in user_command.lower() for keyword in ["explain", "tell me about", "what is", "how does", "why", "describe"]):
            self.audio_processors.speak("Let me think about that")
            time.sleep(0.3)
        
        # Add the user command to history since it's a conversational message
        self.conversation_history.append({"role": "user", "content": user_command})
        
        if "response" in tool_response:
            response_text = tool_response["response"]
            # Add assistant response to history
            self.conversation_history.append({"role": "assistant", "content": response_text})
            self.conversation_manager.conversation_history = self.conversation_history
            self.conversation_manager.save_conversation_history()
            self.audio_processors.speak(response_text)
            
            # Check if the direct response needs follow-up
            if self.is_question_or_needs_clarification(response_text):
                time.sleep(0.3)
                return self.handle_follow_up_conversation()
        else:
            # Fallback to general AI response (already handles conversation history)
            ai_response = self.get_ai_response(user_command)
            self.audio_processors.speak(ai_response)
            
            # Check if this AI response needs follow-up too
            if self.is_question_or_needs_clarification(ai_response):
                time.sleep(0.3)
                return self.handle_follow_up_conversation()
        
        print("Direct response completed. Ready for next command.")
        return False
    
    def handle_fallback_conversation(self, user_command):
        """Handle fallback conversation with follow-up support"""
        # Give feedback for processing
        if len(user_command) > 20:  # Longer queries might need processing time
            self.audio_processors.speak("Let me process that for you")
            time.sleep(0.3)
        
        # This is a conversational message, so add to history and get AI response
        ai_response = self.get_ai_response(user_command)
        self.audio_processors.speak(ai_response)
        
        time.sleep(0.3)
        
        if self.is_question_or_needs_clarification(ai_response):
            return self.handle_follow_up_conversation()
        else:
            print("AI response is complete. Ready for next command.")
            return False
    
    def handle_follow_up_conversation(self):
        """Handle follow-up conversation when AI asks questions"""
        print("AI is asking a question or needs clarification. Continuing conversation...")
        # Pause using audio_processors helper for consistent behavior
        self.audio_processors.pause_listening(0.5)  # Longer pause for better audio separation
        print("Now listening for follow-up response...")
        self.audio_processors.play_beep_sound()
        # Try to get follow-up response
        follow_up_command = self.recognizer.listen_for_command(is_follow_up=True)
        if follow_up_command:
            print(f"Received valid follow-up response: '{follow_up_command}'")
            ai_response = self.get_ai_response(follow_up_command)
            self.audio_processors.speak(ai_response)
            
            # Check if this response also needs follow-up
            if self.is_question_or_needs_clarification(ai_response):
                return self.handle_final_follow_up()
        else:
            print("No valid follow-up response detected after multiple attempts")
            self.audio_processors.speak("I didn't hear your response. Feel free to wake me up again if you need anything!")
        
        return False
    
    def handle_final_follow_up(self):
        """Handle final follow-up attempt"""
        print("AI has another question. One more follow-up attempt...")
        self.audio_processors.pause_listening(1.5)
        final_follow_up = self.recognizer.listen_for_command(is_follow_up=True)
        if final_follow_up:
            final_response = self.get_ai_response(final_follow_up)
            self.audio_processors.speak(final_response)
        else:
            self.audio_processors.speak("I'll end our conversation here. Feel free to wake me up again anytime!")
        
        return False