"""
LangChain Agent using Ollama with Telegram and Weather API Tools
This uses a local Ollama model instead of OpenAI for the LLM backend
"""

import os
import sys
import logging
from typing import Dict, Any, List
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# LangChain imports
from langchain.agents import AgentExecutor, create_react_agent
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import PromptTemplate
from langchain.tools import Tool
from langchain_community.llms import Ollama

# Import your existing connectors
from connectors.weather_connector import WeatherAPIConnector
from connectors.telegram_bot import TelegramBot

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class LangChainOllamaAgent:
    """
    LangChain Agent using Ollama with Telegram and Weather API tools
    """
    
    def __init__(self, model_name: str = "llama3.2", ollama_base_url: str = "http://localhost:11434"):
        """
        Initialize LangChain Ollama Agent
        
        Args:
            model_name: Name of Ollama model to use (default: llama3.2)
            ollama_base_url: Base URL for Ollama API (default: http://localhost:11434)
        """
        
        # Initialize connectors
        self.weather_connector = WeatherAPIConnector()
        self.telegram_bot = TelegramBot()
        
        # LangChain-specific setup
        self.model_name = "gemma3:1b-it-q4_K_M"
        self.ollama_base_url = "http://localhost:11434"
        self.agent_executor = None
        self.tools = []
        self.conversation_history = []
        
        self._setup_langchain_agent()
    
    def _create_current_weather_tool(self) -> Tool:
        """Get current weather for a location"""
        def current_weather_function(location: str) -> str:
            try:
                result = self.weather_connector.get_simple_weather(location)
                return result
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
                result = self.weather_connector.get_weather_forecast_summary(location, days=3)
                return result
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
                result = self.weather_connector.get_timezone(location)
                return result
            except Exception as e:
                return f"Timezone error: {str(e)}"
        
        return Tool(
            name="get_timezone",
            description="Get timezone and current local time for a specific location. Input should be a city name or location.",
            func=timezone_function
        )
    
    def _create_telegram_message_tool(self) -> Tool:
        """Send text message via Telegram"""
        def telegram_message_function(message: str) -> str:
            try:
                chat_id = os.getenv('TELEGRAM_CHAT_ID')
                if not chat_id:
                    return "Error: TELEGRAM_CHAT_ID not configured in environment variables"
                
                tool_response = {
                    "action": "send_message",
                    "message": message
                }
                result = self.telegram_bot.telegram_handler(tool_response)
                
                if result and result.get('message_id'):
                    return f"Message sent successfully to Telegram (ID: {result['message_id']})"
                else:
                    return "Message sent to Telegram"
            except Exception as e:
                return f"Telegram message error: {str(e)}"
        
        return Tool(
            name="send_telegram_message",
            description="Send a text message via Telegram to the configured chat. Input should be the message text to send.",
            func=telegram_message_function
        )
    
    def _create_telegram_photo_tool(self) -> Tool:
        """Send photo via Telegram"""
        def telegram_photo_function(photo_info: str) -> str:
            try:
                chat_id = os.getenv('TELEGRAM_CHAT_ID')
                if not chat_id:
                    return "Error: TELEGRAM_CHAT_ID not configured in environment variables"
                
                # Parse photo_info - format: "photo_url|caption" or just "photo_url"
                parts = photo_info.split('|', 1)
                photo_path = parts[0].strip()
                caption = parts[1].strip() if len(parts) > 1 else ""
                
                tool_response = {
                    "action": "send_photo",
                    "photo": photo_path,
                    "caption": caption
                }
                result = self.telegram_bot.telegram_handler(tool_response)
                
                if result and result.get('message_id'):
                    return f"Photo sent successfully to Telegram"
                else:
                    return "Photo sent to Telegram"
            except Exception as e:
                return f"Telegram photo error: {str(e)}"
        
        return Tool(
            name="send_telegram_photo",
            description="Send a photo via Telegram. Input format: 'photo_url|caption' or just 'photo_url'. Use image URLs or local file paths.",
            func=telegram_photo_function
        )
    
    def _create_telegram_document_tool(self) -> Tool:
        """Send document via Telegram"""
        def telegram_document_function(doc_info: str) -> str:
            try:
                chat_id = os.getenv('TELEGRAM_CHAT_ID')
                if not chat_id:
                    return "Error: TELEGRAM_CHAT_ID not configured in environment variables"
                
                # Parse doc_info - format: "document_path|caption" or just "document_path"
                parts = doc_info.split('|', 1)
                doc_path = parts[0].strip()
                caption = parts[1].strip() if len(parts) > 1 else ""
                
                tool_response = {
                    "action": "send_document",
                    "document": doc_path,
                    "caption": caption
                }
                result = self.telegram_bot.telegram_handler(tool_response)
                
                if result and result.get('message_id'):
                    return f"Document sent successfully to Telegram"
                else:
                    return "Document sent to Telegram"
            except Exception as e:
                return f"Telegram document error: {str(e)}"
        
        return Tool(
            name="send_telegram_document",
            description="Send a document via Telegram. Input format: 'document_path|caption' or just 'document_path'.",
            func=telegram_document_function
        )

    def _setup_langchain_agent(self):
        """Setup the LangChain agent with Ollama LLM and tools"""
        
        # Create tools
        self.tools = [
            self._create_current_weather_tool(),
            self._create_weather_forecast_tool(),
            self._create_timezone_tool(),
            self._create_telegram_message_tool(),
            self._create_telegram_photo_tool(),
            self._create_telegram_document_tool(),
        ]
        
        # Initialize Ollama LLM with performance optimizations
        try:
            llm = Ollama(
                model=self.model_name,
                base_url=self.ollama_base_url,
                num_predict=256,  # Limit response length for speed
                num_ctx=2048,     # Smaller context window for faster processing
                top_k=20,         # Reduce sampling space
                top_p=0.9,        # Focus on most likely tokens
                repeat_penalty=1.1,
                verbose=False     # Reduce logging overhead
            )
            logger.info(f"Initialized Ollama with model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Ollama: {e}")
            raise ValueError(f"Ollama initialization failed. Make sure Ollama is running at {self.ollama_base_url}")
        
        # Setup memory for conversation context
        memory = ConversationBufferWindowMemory(
            memory_key="chat_history",
            return_messages=False,
            k=2  # Remember only last 2 exchanges for speed
        )
        
        # Create ReAct prompt template
        template = """You are a helpful AI assistant with access to tools for weather information and Telegram messaging.

You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Previous conversation:
{chat_history}

Question: {input}
{agent_scratchpad}"""

        prompt = PromptTemplate.from_template(template)
        
        # Create agent
        agent = create_react_agent(
            llm=llm,
            tools=self.tools,
            prompt=prompt
        )
        
        # Create agent executor with optimizations
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=memory,
            verbose=False,  # Reduce logging for speed
            handle_parsing_errors=True,
            max_iterations=5,  # Reduce max iterations for faster responses
            early_stopping_method="generate"  # Stop early when answer is found
        )
        
        logger.info(f"LangChain Ollama agent initialized with {len(self.tools)} tools")
        logger.info(f"Available tools: {[tool.name for tool in self.tools]}")
    
    def run(self, user_input: str) -> str:
        """
        Process user input and return agent response
        
        Args:
            user_input: User's question or command
            
        Returns:
            Agent's response
        """
        try:
            logger.info(f"Processing user input: {user_input}")
            
            result = self.agent_executor.invoke({"input": user_input})
            response = result.get("output", "I'm sorry, I couldn't process that request.")
            
            # Add to conversation history
            self.conversation_history.append({
                "user": user_input,
                "assistant": response
            })
            
            logger.info(f"Agent response: {response}")
            return response
            
        except Exception as e:
            error_msg = f"Error processing request: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Get information about the agent's current state"""
        return {
            "model": self.model_name,
            "ollama_url": self.ollama_base_url,
            "tools_count": len(self.tools),
            "tool_names": [tool.name for tool in self.tools],
            "conversation_length": len(self.conversation_history)
        }
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        if self.agent_executor and hasattr(self.agent_executor, 'memory'):
            self.agent_executor.memory.clear()
        logger.info("Conversation history cleared")


def main():
    """Example usage of LangChain Ollama Agent"""
    
    print("=" * 60)
    print("LangChain Ollama Agent - Weather & Telegram Tools")
    print("=" * 60)
    
    try:
        # Initialize agent
        agent = LangChainOllamaAgent(model_name="llama3.2")
        
        # Display agent info
        info = agent.get_agent_info()
        print(f"\nAgent Information:")
        print(f"  Model: {info['model']}")
        print(f"  Ollama URL: {info['ollama_url']}")
        print(f"  Available Tools: {', '.join(info['tool_names'])}")
        print(f"\n" + "=" * 60)
        
        # Example queries
        example_queries = [
            "What's the weather like in Pune?",
            "Get me a 3-day weather forecast for Mumbai",
            "What time is it in London?",
            "Send a message to Telegram saying 'Hello from Ollama Agent!'"
        ]
        
        print("\nExample Queries:")
        for i, query in enumerate(example_queries, 1):
            print(f"{i}. {query}")
        
        # Interactive mode
        print(f"\n" + "=" * 60)
        print("Interactive Mode (type 'quit' to exit)")
        print("=" * 60 + "\n")
        
        while True:
            user_input = input("You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if not user_input:
                continue
            
            # Get agent response
            response = agent.run(user_input)
            print(f"\nAgent: {response}\n")
            print("-" * 60 + "\n")
        
    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")
        print("\nSetup Instructions:")
        print("1. Install Ollama: https://ollama.ai")
        print("2. Pull a model: ollama pull llama3.2")
        print("3. Start Ollama: ollama serve")
        print("4. Set environment variables:")
        print("   - WEATHER_API_KEY (from weatherapi.com)")
        print("   - TELEGRAM_TOKEN (from @BotFather)")
        print("   - TELEGRAM_CHAT_ID (your chat ID)")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
