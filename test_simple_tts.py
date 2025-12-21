"""
Simple Edge TTS Test
Test converting numbers in Hindi text to ensure clear pronunciation
"""

import asyncio
import edge_tts
import pygame
import os

async def test_tts(text, voice="en-IN-AartiNeural", output_file="test_output.mp3"):
    """Test Edge TTS with given text"""
    print(f"Text: {text}")
    print(f"Voice: {voice}")
    
    # Generate speech
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
    print(f"Saved to: {output_file}")
    
    # Play the audio
    pygame.mixer.init()
    pygame.mixer.music.load(output_file)
    pygame.mixer.music.play()
    
    # Wait for playback to finish
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)
    
    pygame.mixer.quit()
    print("Playback completed\n")

async def main():
    """Test different number formats in Hindi"""
    
    # Test cases
    test_cases = [
        # Original - numbers in Hindi words
       
        
        # Mixed example
        "A2 farm dudh  2 लीटर दूध चाहिए जो ₹150 का है"
    ]
    
    for i, text in enumerate(test_cases):
        print(f"\n--- Test {i+1} ---")
        output_file = f"test_output_{i+1}.mp3"
        await test_tts(text, output_file=output_file)
        
        # Clean up
        if os.path.exists(output_file):
            os.remove(output_file)
    
    print("\nAll tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
