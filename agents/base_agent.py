from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
import os
from dotenv import load_dotenv

load_dotenv()

class BaseAgent(ABC):
    """Base class for all LangChain agents"""
    
    def __init__(self, 
                 model_name: str = "gpt-3.5-turbo",
                 temperature: float = 0.7,
                 max_tokens: int = 1000):
        """
        Initialize base agent
        
        Args:
            model_name: OpenAI model to use
            temperature: Model temperature for creativity
            max_tokens: Maximum tokens in response
        """
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            openai_api_key=os.getenv('OPENAI_API_KEY')
        )
        
        # Initialize memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Will be populated by subclasses
        self.tools = []
        self.agent = None
        self.agent_executor = None
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get the system prompt for the agent"""
        pass
    
    @abstractmethod
    def setup_tools(self) -> List[Any]:
        """Setup and return tools for the agent"""
        pass
    
    def create_prompt_template(self) -> ChatPromptTemplate:
        """Create the prompt template for the agent"""
        system_prompt = self.get_system_prompt()
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        return prompt
    
    def initialize_agent(self):
        """Initialize the agent with tools and prompt"""
        # Setup tools
        self.tools = self.setup_tools()
        
        # Create prompt
        prompt = self.create_prompt_template()
        
        # Create agent
        self.agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5,
            early_stopping_method="generate"
        )
    
    def run(self, input_text: str) -> Dict[str, Any]:
        """
        Run the agent with input text
        
        Args:
            input_text: User input
            
        Returns:
            Dict containing response and metadata
        """
        try:
            if not self.agent_executor:
                self.initialize_agent()
            
            result = self.agent_executor.invoke({"input": input_text})
            
            return {
                "success": True,
                "response": result.get("output", "No response generated"),
                "intermediate_steps": result.get("intermediate_steps", []),
                "chat_history": self.memory.chat_memory.messages
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "response": "I encountered an error while processing your request."
            }
    
    def clear_memory(self):
        """Clear the agent's memory"""
        self.memory.clear()
    
    def get_memory_summary(self) -> str:
        """Get a summary of the conversation memory"""
        messages = self.memory.chat_memory.messages
        if not messages:
            return "No conversation history"
        
        summary = f"Conversation has {len(messages)} messages:\n"
        for i, msg in enumerate(messages[-5:]):  # Last 5 messages
            role = "Human" if msg.type == "human" else "AI"
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            summary += f"{i+1}. {role}: {content}\n"
        
        return summary