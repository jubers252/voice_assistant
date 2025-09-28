#!/usr/bin/env python3
"""
Token counter utility for any file or string.
Uses tiktoken if available, otherwise falls back to regex-based tokenization.
Usage:
  python tools/token_count.py <file_path>
  python tools/token_count.py --text "your text here"
"""
import sys
import re
import os
from pathlib import Path

def count_tokens(text):
    # Try tiktoken if available
    try:
        import tiktoken
        enc = tiktoken.get_encoding('cl100k_base')
        tokens = enc.encode(text)
        return {
            'method': 'tiktoken (cl100k_base)',
            'token_count': len(tokens),
            'tokens': tokens[:30]  # show first 30 tokens
        }
    except Exception as e:
        # Fallback: split on words and punctuation
        fallback_tokens = re.findall(r"\w+|[^\s\w]", text)
        return {
            'method': 'regex fallback',
            'token_count': len(fallback_tokens),
            'tokens': fallback_tokens[:30]
        }

def main(file_path):
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    source = str(file_path)

    char_count = len(text)
    word_count = len(re.findall(r"\w+", text))
    result = count_tokens(text)
    
    print(f"Source: {source}")
    print(f"Characters: {char_count}")
    print(f"Words (\w+): {word_count}")
    print(f"Tokenization method: {result['method']}")
    print(f"Token count: {result['token_count']}")
    print(f"First 30 tokens: {result['tokens']}")

if __name__ == '__main__':
    file = r"/home/jubers/Documents/voice_assistant/amazon_vivo_x_fold_5_product_info.json"
    main(file)
