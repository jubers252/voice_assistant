from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import time
import pygame
import os

load_dotenv()

def generate_and_play_gpt_tts(text, voice="shimmer", model="gpt-4o-mini-tts", instructions=None):
    """Generate speech with OpenAI GPT TTS and play it"""
    
    client = OpenAI()
    speech_file_path = Path(__file__).parent / "gpt_tts_output.mp3"
    
    print(f"Generating audio with GPT TTS...")
    print(f"Text: {text}")
    print(f"Voice: {voice}")
    print(f"Model: {model}")
    
    start_time = time.time()
    
    try:
        # Generate TTS with streaming
        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=text,
            instructions=instructions if instructions else "Speak naturally and clearly.",
        ) as response:
            response.stream_to_file(speech_file_path)
        
        generation_time = time.time() - start_time
        print(f"⏱️  Audio generation took: {generation_time:.2f} seconds")
        
        # Play audio
        if os.path.exists(speech_file_path):
            print("Playing audio...")
            pygame.mixer.init()
            pygame.mixer.music.load(str(speech_file_path))
            pygame.mixer.music.play()
            
            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            
            pygame.mixer.quit()
            print("Playback complete!")
        else:
            print("Error: Audio file not created")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Available voices: alloy, echo, fable, onyx, nova, shimmer, coral (gpt-4o-mini-tts only)
    
    # Example 1: English text
    # text = "Hello! This is a test of OpenAI's GPT TTS. It generates natural sounding speech."
    # generate_and_play_gpt_tts(text, voice="shimmer", instructions="Read the following English text clearly and naturally in indian.")
    
    # Example 2: Hindi text
    text = "नमस्ते, यह गूगल टेक्स्ट टू स्पीच की जाँच है"
    generate_and_play_gpt_tts(text, voice="marin", instructions="Read the following Hindi text normally.")
    
    # Example 3: Different voices
    # generate_and_play_gpt_tts("This is the Nova voice.", voice="nova")
    # generate_and_play_gpt_tts("This is the Shimmer voice.", voice="shimmer")
