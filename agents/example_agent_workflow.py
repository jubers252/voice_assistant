"""
LangChain Agent Implementation Example for Voice Assistant

This shows how agents work with autonomous decision-making and tool usage.
"""

from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.memory import ConversationBufferWindowMemory
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
import os
from dotenv import load_dotenv

# Example: How your existing connectors become LangChain tools
def create_weather_tool():
    """Convert your weather connector to LangChain tool"""
    def get_weather(location: str) -> str:
        # Your existing weather connector code
        from connectors.weather_connector import handle_tool_requests
        tool_request = {"tool": "weather", "location": location}
        result = handle_tool_requests(tool_request)
        return f"Weather in {location}: {result}"
    
    return Tool(
        name="get_weather",
        description="Get current weather for a location. Input should be a city name.",
        func=get_weather
    )

def create_spotify_tool():
    """Convert your Spotify connector to LangChain tool"""
    def control_spotify(action: str) -> str:
        # Your existing Spotify connector code
        from connectors.spotify_connector import SpotifyConnector
        spotify = SpotifyConnector(None)
        
        if "play" in action.lower():
            return "Playing music on Spotify"
        elif "pause" in action.lower():
            return "Pausing Spotify"
        elif "next" in action.lower():
            return "Skipping to next track"
        return f"Spotify action: {action}"
    
    return Tool(
        name="control_spotify",
        description="Control Spotify playback. Actions: play, pause, next, previous",
        func=control_spotify
    )

def create_search_tool():
    """Convert your search connector to LangChain tool"""
    def search_web(query: str) -> str:
        # Your existing search connector code
        from connectors.search_engine import GeminiSearch
        search = GeminiSearch()
        result = search.handle_search_action_with_feedback({"query": query})
        return result[:500]  # Limit response length
    
    return Tool(
        name="search_web",
        description="Search the web for information. Input should be a search query.",
        func=search_web
    )

class VoiceAssistantAgent:
    """Main agent that replaces your current command processor"""
    
    def __init__(self):
        load_dotenv()
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.7,
            openai_api_key=os.getenv('OPENAI_API_KEY')
        )
        
        # Memory for conversation context
        self.memory = ConversationBufferWindowMemory(
            memory_key="chat_history",
            return_messages=True,
            k=10  # Remember last 10 exchanges
        )
        
        # Setup tools
        self.tools = [
            create_weather_tool(),
            create_spotify_tool(),
            create_search_tool()
        ]
        
        # Create agent
        self.setup_agent()
    
    def setup_agent(self):
        """Setup the autonomous agent"""
        
        # System prompt defines agent behavior
        system_prompt = """
        You are an intelligent voice assistant that helps users with various tasks.
        
        You have access to these tools:
        - get_weather: Get weather information for any location
        - control_spotify: Control Spotify music playback
        - search_web: Search the internet for information
        
        Instructions:
        1. Listen to the user's request carefully
        2. Decide which tool(s) you need to use
        3. Use tools in the right order if multiple are needed
        4. Provide helpful, conversational responses
        5. Remember previous conversation context
        
        Always be helpful, friendly, and concise in your responses.
        If you're unsure about something, ask for clarification.
        """
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        # Create agent
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        # Create executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,  # Shows reasoning process
            handle_parsing_errors=True,
            max_iterations=3,
            early_stopping_method="generate"
        )
    
    def process_voice_command(self, user_input: str) -> str:
        """
        Process voice command using agent
        This replaces your current process_user_command method
        """
        try:
            # Agent autonomously decides what to do
            result = self.agent_executor.invoke({"input": user_input})
            return result["output"]
            
        except Exception as e:
            return f"Sorry, I encountered an error: {str(e)}"

# Example usage showing the workflow
def demonstrate_agent_workflow():
    """Show how the agent works with different types of requests"""
    
    agent = VoiceAssistantAgent()
    
    # Example conversations
    examples = [
        "What's the weather like in New York?",
        "Play some music on Spotify",
        "Search for the latest news about AI",
        "What's the weather in London and then play some relaxing music",
        "Can you tell me about the weather and then search for good restaurants nearby?"
    ]
    
    print("=== LangChain Agent Workflow Demo ===\n")
    
    for i, user_input in enumerate(examples, 1):
        print(f"Example {i}: {user_input}")
        print("-" * 50)
        
        # This is what happens internally:
        print("Agent thinking process:")
        print("1. Analyzing user request...")
        print("2. Deciding which tools to use...")
        print("3. Executing tools in order...")
        print("4. Generating response...")
        
        # Actual agent response
        response = agent.process_voice_command(user_input)
        print(f"Agent Response: {response}")
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    demonstrate_agent_workflow()