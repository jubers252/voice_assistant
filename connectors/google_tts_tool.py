import os
import struct
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

def create_wav_header(pcm_data, sample_rate=24000):
    """Creates a valid WAV header for the raw PCM audio data."""
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * (bits_per_sample // 8)
    block_align = num_channels * (bits_per_sample // 8)
    data_size = len(pcm_data)
    chunk_size = 36 + data_size

    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', chunk_size, b'WAVE', b'fmt ', 16, 1,
        num_channels, sample_rate, byte_rate, block_align, bits_per_sample,
        b'data', data_size
    )
    return header

def generate_speech(text, prompt, filename="output.wav"):
    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
    
    print("Generating audio...")
    
    # FIX: We must explicitly tell the model to READ the text.
    # If we don't, it might try to "reply" to the text, causing the error.
    prompt =prompt

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["audio"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
                    )
                ),
            )
        )

        # Check if we got valid audio parts
        if not response.candidates:
            print("Error: No candidates returned.")
            print(f"Response: {response}")
            return
            
        candidate = response.candidates[0]
        if not candidate.content:
            print("Error: No content in candidate.")
            print(f"Candidate: {candidate}")
            return
            
        if not candidate.content.parts:
            print("Error: No parts in content.")
            print(f"Content: {candidate.content}")
            return
        
        part = candidate.content.parts[0]
        if not hasattr(part, 'inline_data') or not part.inline_data:
            print("Error: Model returned no inline audio data.")
            print(f"Part: {part}")
            return
        
        audio_bytes = part.inline_data.data
        
        # Add the WAV header and save
        with open(filename, "wb") as f:
            f.write(create_wav_header(audio_bytes))
            f.write(audio_bytes)
        print(f"Success! Saved to: {filename}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # You can change the text inside the quotes below
    text_input = ""
    prompt = "generate cat sound"
    generate_speech(text_input, prompt)


class GoogleTTSTool:
    """Tool for generating custom voice/sound audio using Google Gemini TTS"""
    
    def __init__(self, audio_processor=None):
        self.audio_processor = audio_processor
        self.available_voices = ["Zephyr", "Aoede", "Charon", "Fenrir", "Kore", "Puck"]
    
    def generate_and_play(self, prompt, save_path=None):
        """
        Generate TTS audio from prompt and optionally play it.
        
        Args:
            prompt: Prompt describing what to generate (e.g., "Read this text aloud: Hello" or "generate cat sound")
            save_path: Optional path to save the audio file
            
        Returns:
            Success message or error message
        """
        try:
            import tempfile
            import time
            
            # Generate filename if not provided
            if save_path is None:
                timestamp = int(time.time())
                save_path = os.path.join(tempfile.gettempdir(), f"tts_generated_{timestamp}.wav")
            
            print(f"[TTS] Generating audio for prompt: '{prompt[:60]}...'")
            
            # Generate the audio
            generate_speech("", prompt, filename=save_path)
            
            if not os.path.exists(save_path):
                return "Failed to generate audio"
            
            # Play the audio if audio_processor is available
            if self.audio_processor:
                print(f"[TTS] Playing generated audio...")
                self.audio_processor.play_audio_file(save_path)
            
            return f"Generated and played audio for: {prompt[:60]}"
                
        except Exception as e:
            return f"Error generating audio: {str(e)}"
    
    def main(self, params):
        """
        Main entry point for the tool.
        
        Args:
            params: Dictionary with 'prompt' and optional 'save_path'
        
        Returns:
            Result message
        
        Examples:
            params = {'prompt': 'Read this text aloud: Hello world'}
            params = {'prompt': 'generate cat meowing sound'}
            params = {'prompt': 'generate dramatic thunder sound'}
        """
        prompt = params.get('prompt', '')
        save_path = params.get('save_path')
        
        if not prompt:
            return "Please provide a prompt to generate audio"
        
        return self.generate_and_play(prompt, save_path=save_path)