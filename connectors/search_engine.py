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
from typing import Dict, List, Optional
import warnings

from google import genai
from google.genai import types
from dotenv import load_dotenv
    
load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash-lite"


# Suppress Pydantic field shadowing warnings from google-genai SDK
warnings.filterwarnings("ignore", message="Field name .* shadows an attribute in parent", category=UserWarning)


class GeminiSearch:
    """Simple wrapper for Gemini Google Search grounding.

    Methods
    -------
    search(query: str, model: str = DEFAULT_MODEL) -> Dict
        Executes a grounded web search and returns text + citations.
    quick_search(query: str) -> str
        Fast search returning only the answer text (no citations).
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        # Client reads GOOGLE_API_KEY from env by default
        self.client = genai.Client()
        self.model = model
        self._grounding_tool = types.Tool(google_search=types.GoogleSearch())

    def quick_search(self, query: str) -> str:
        """Fast search returning only answer text, optimized for voice assistants.
        
        Parameters
        ----------
        query : str
            The search query
            
        Returns
        -------
        str
            Just the answer text, no metadata
        """
        config = types.GenerateContentConfig(
            tools=[self._grounding_tool],
            system_instruction="You are a helpful assistant. For location-based queries (weather, time, news, restaurants, events, traffic, etc.) where no specific location is mentioned, default to Pune, India. Give very brief, direct answers. Maximum 2 sentences.",
        )
        
        try:
            resp = self.client.models.generate_content(
                model="gemini-2.5-flash-lite",  # Use Flash-Lite for speed
                contents=query,
                config=config,
            )
            return getattr(resp, "text", "") or "No answer found."
        except Exception as e:
            return f"Search failed: {str(e)}"

    def search(self, query: str, model: Optional[str] = None, timeout: int = 30) -> Dict:
        """Run a grounded web query and return response with citations.

        Parameters
        ----------
        query : str
            The search query
        model : str, optional
            Override the default model
        timeout : int
            Request timeout in seconds (default: 30)

        Returns
        -------
        dict with keys:
          - text: str (the model's grounded answer)
          - citations: List[Dict[str, str]] with {"title", "uri"}
          - web_search_queries: List[str] used by the tool (if available)
          - response_time: float (seconds taken)
        """
        start_time = time.time()
        m = model or self.model

        config = types.GenerateContentConfig(
            tools=[self._grounding_tool],
            # Add performance optimizations
            system_instruction="You are a helpful assistant. For any location-based queries (weather, time, news, restaurants, etc.) where no specific location is mentioned, default to Pune, India. Provide concise, accurate answers based on search results. Be brief but informative.",
        )

        try:
            resp = self.client.models.generate_content(
                model=m,
                contents=query,
                config=config,
            )
        except Exception as e:
            return {
                "text": f"Search failed: {str(e)}",
                "citations": [],
                "web_search_queries": [],
                "response_time": time.time() - start_time,
                "error": str(e)
            }

        text = getattr(resp, "text", "") or ""

        citations: List[Dict[str, str]] = []
        web_queries: List[str] = []

        # Extract grounding metadata if present
        try:
            cand = resp.candidates[0]
            gm = getattr(cand, "grounding_metadata", None)
            if gm:
                # Queries
                if getattr(gm, "web_search_queries", None):
                    web_queries = list(gm.web_search_queries)

                # Chunks (sources)
                chunks = getattr(gm, "grounding_chunks", [])
                for ch in chunks:
                    web = getattr(ch, "web", None)
                    if web and getattr(web, "uri", None):
                        citations.append({
                            "title": getattr(web, "title", ""),
                            "uri": web.uri,
                        })
        except Exception:
            # Be resilient if schema differs across SDK versions
            pass

        response_time = time.time() - start_time
        
        return {
            "text": text,
            "citations": citations,
            "web_search_queries": web_queries,
            "response_time": response_time,
        }


def _ensure_api_key() -> None:
    if not os.environ.get("GOOGLE_API_KEY"):
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Obtain a Gemini API key from AI Studio and set it in the environment."
        )


if __name__ == "__main__":
    # Quick manual test: python connectors/search_engine.py "latest weather in London"
    import sys

    _ensure_api_key()

    query = " ".join(sys.argv[1:]) or "What is the latest headline from BBC?"
    print(f"Searching for: {query}")
    print("⏳ Please wait...")
    
    gs = GeminiSearch()
    out = gs.search(query)
    
    print(f"⚡ Response time: {out['response_time']:.2f} seconds")
    print("Answer:\n", out["text"])  # model's grounded answer
    
    if out.get("error"):
        print(f"❌ Error: {out['error']}")
    
    if out["citations"]:
        print("\nSources:")
        for i, c in enumerate(out["citations"], 1):
            print(f"  [{i}] {c['title']} - {c['uri']}")
    
    if out["web_search_queries"]:
        print(f"\nSearch queries used: {', '.join(out['web_search_queries'])}")