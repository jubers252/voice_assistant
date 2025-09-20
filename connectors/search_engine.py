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
        _ensure_api_key()
        self.client = genai.Client()
        self.model = model
        self._grounding_tool = types.Tool(google_search=types.GoogleSearch())

    def quick_search(self, query: str, lang: Optional[str] = None) -> str:
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
            system_instruction=(
                "You are a helpful assistant. For location-based queries (weather, time, news, restaurants, events, traffic, etc.) "
                "where no specific location is mentioned, default to Pune, India. Give very brief, direct answers (maximum 2 sentences). "
                "Keep answers short and suitable for text-to-speech (avoid special characters). "
                f"IMPORTANT: Always respond in the same language as the user's query. "
                f"If user asks in Hindi, respond in Hindi BUT use Roman script (transliterated Hindi) for TTS compatibility. "
                f"If user asks in English, respond in English only. "
                f"Language detected: {lang or 'en'}. "
                f"If language is Hindi (hi), respond in Hindi but write it in Roman/Latin letters (like 'aaj ka mausam kaisa hai'). "
                f"If language is English (en), respond in English only. "
                f"Do NOT use Devanagari script (Hindi characters) - use Roman letters for Hindi words."
            ),
        )
        # Retry on transient errors (e.g. 503 / overloaded). Use exponential backoff with jitter.
        max_attempts = 4
        base_delay = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                
                resp = self.client.models.generate_content(
                    model=self.model,  # Use configured model
                    contents=query,
                    config=config,
                )
                return getattr(resp, "text", "") or "No answer found."
            except Exception as e:
                msg = str(e).lower()
                # Consider these messages transient and worth retrying
                transient_indicators = ["503", "unavailable", "overloaded", "temporarily", "rate limit"]
                if attempt >= max_attempts or not any(ind in msg for ind in transient_indicators):
                    # Final attempt or non-transient error: return a friendly message including the error
                    return f"Search failed: {str(e)}"

                # Sleep with exponential backoff + jitter and retry
                delay = base_delay * (2 ** (attempt - 1))
                jitter = random.uniform(0, 0.5)
                time.sleep(delay + jitter)
                continue

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

        # Retry on transient errors (503 / overloaded) with exponential backoff
        max_attempts = 4
        base_delay = 1.0
        resp = None
        last_exception = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self.client.models.generate_content(
                    model=m,
                    contents=query,
                    config=config,
                )
                last_exception = None
                break
            except Exception as e:
                last_exception = e
                msg = str(e).lower()
                transient_indicators = ["503", "unavailable", "overloaded", "temporarily", "rate limit"]
                if attempt >= max_attempts or not any(ind in msg for ind in transient_indicators):
                    break
                delay = base_delay * (2 ** (attempt - 1))
                jitter = random.uniform(0, 0.5)
                time.sleep(delay + jitter)
                continue

        if resp is None and last_exception is not None:
            return {
                "text": f"Search failed: {str(last_exception)}",
                "citations": [],
                "web_search_queries": [],
                "response_time": time.time() - start_time,
                "error": str(last_exception)
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
    # Quick manual test with hardcoded query
    import sys

    query = "what is weather in pune"
    lang = "en"
    
    try:
        _ensure_api_key() 
        gs = GeminiSearch()
        result = gs.quick_search(query, lang=lang)
        print(f"Query: {query}")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")