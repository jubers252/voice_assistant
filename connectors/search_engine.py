"""
Gemini-powered real-time search connector using Google Search grounding.

Default model: gemini-2.5-flash-lite (fastest and cheapest for real-time queries).
Alternatives:
  - gemini-2.5-flash (better quality, slightly slower)
  - gemini-2.5-pro (best reasoning, slowest)

Requires env var GOOGLE_API_KEY with a Gemini API key.
"""

from __future__ import annotations

import os
import time
import random
from typing import Dict, List, Optional
import warnings

from exa_py import Exa
from google import genai
from google.genai import types
from dotenv import load_dotenv
    
load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash-lite"


# Suppress Pydantic field shadowing warnings from google-genai SDK
warnings.filterwarnings("ignore", message="Field name .* shadows an attribute in parent", category=UserWarning)


class ExaSearch:
    """Simple wrapper for Exa web search.

    Methods
    -------
    search(query: str, num_results: int = 10, search_type: str = "auto") -> Dict
        Executes a web search and returns summarized text + citations.
    quick_search(query: str, lang: Optional[str] = None) -> str
        Fast search returning concise text response.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        _ensure_exa_api_key(api_key)
        self.api_key = api_key or os.environ.get("EXA_API_KEY") 
        self.client = Exa(self.api_key)

    def quick_search(self, query: str, lang: Optional[str] = None) -> str:
        """Fast search returning concise text for voice assistants."""
        try:
            result = self.client.search(
                query,
                num_results=1,
                type="auto",
                contents={"highlights": True},
            )

            entries = getattr(result, "results", None) or []
            if not entries:
                return "No relevant results found."

            snippets: List[str] = []
            for item in entries[:3]:
                highlights = getattr(item, "highlights", None) or []
                if highlights:
                    snippets.append(str(highlights[0]))
                elif getattr(item, "title", None):
                    snippets.append(str(item.title))

            if not snippets:
                return "No relevant highlights found."

            answer = " ".join(snippets).strip()
            return answer
        except Exception as e:
            return f"Search failed: {str(e)}"

    def search(self, query: str, num_results: int = 10, search_type: str = "auto") -> Dict:
        """Run an Exa query and return structured response with citations."""
        start_time = time.time()
        try:
            result = self.client.search(
                query,
                num_results=num_results,
                type=search_type,
                contents={"highlights": True},
            )

            entries = getattr(result, "results", None) or []
            citations: List[Dict[str, str]] = []
            text_parts: List[str] = []

            for item in entries:
                title = str(getattr(item, "title", "") or "")
                url = str(getattr(item, "url", "") or "")
                highlights = getattr(item, "highlights", None) or []

                if title or url:
                    citations.append({"title": title, "uri": url})

                if highlights:
                    text_parts.append(" ".join([str(h) for h in highlights if h]))
                elif title:
                    text_parts.append(title)

            text = " ".join([p for p in text_parts if p]).strip()
            if not text:
                text = "No relevant results found."

            return {
                "text": text,
                "citations": citations,
                "web_search_queries": [query],
                "response_time": time.time() - start_time,
            }
        except Exception as e:
            return {
                "text": f"Search failed: {str(e)}",
                "citations": [],
                "web_search_queries": [query],
                "response_time": time.time() - start_time,
                "error": str(e),
            }

    def handle_search_action_with_feedback(self, tool_response):
        """Handle search actions using Exa Search - returns raw result for processing."""
        try:
            print(f"Exa search tool_response: {tool_response}")

            query = tool_response.get("query", "")
            if not query:
                return "I need a search query to help you."

            lang = tool_response.get("lang", "en")
            answer = self.quick_search(query, lang)

            if answer:
                return answer
            return "I couldn't complete your search request."
        except Exception as e:
            error_message = str(e)
            print(f"Exa search error: {error_message}")
            return "Sorry, I couldn't search for that information right now."



def _ensure_exa_api_key(api_key: Optional[str] = None) -> None:
    if not (api_key or os.environ.get("EXA_API_KEY") or os.environ.get("EXA_API_TOKEN")):
        raise RuntimeError(
            "EXA_API_KEY (or EXA_API_TOKEN) is not set. Provide it in environment or pass api_key to ExaSearch."
        )




if __name__ == "__main__":
    # Quick manual test with hardcoded query
    import sys

    query = "todays news in pune"
    lang = "en"
    
    try:
        _ensure_exa_api_key()
        gs = ExaSearch()
        result = gs.quick_search(query, lang=lang)
        print(f"Query: {query}")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")