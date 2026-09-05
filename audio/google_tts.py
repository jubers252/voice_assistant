import os
import re
import sys
from google.cloud import texttospeech
from google.cloud.translate_v3 import TranslationServiceClient
from google.cloud.texttospeech import TextToSpeechClient, SynthesisInput, VoiceSelectionParams, AudioConfig, AudioEncoding
from dotenv import load_dotenv


load_dotenv()  # Load environment variables from .env file
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id-12345")


PATH_TO_JSON_KEY = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
VOICE_MAPPING = {
    "en": {"language_code": "en-IN", "name": "en-IN-Chirp3-HD-Leda"},
    "hi": {"language_code": "hi-IN", "name": "hi-IN-Chirp3-HD-Leda"},
    "es": {"language_code": "es-ES", "name": "es-ES-Neural2-F"},
    "fr": {"language_code": "fr-FR", "name": "fr-FR-Neural2-B"}
}
DEFAULT_VOICE = {"language_code": "en-IN", "name": "en-IN-Chirp3-HD-Leda"}


def convert_hindi_text_to_ssml(raw_text):
    """
    this function converts Hindi text to SSML format for better speech synthesis.
    It replaces punctuation with appropriate pauses and wraps the text in <speak> tags.
    """
    text = raw_text.strip()
    sentence_break = '<break time="100ms"/>'
    
    # Keep decimal numbers like 25.5 intact while turning sentence punctuation into pauses.
    text = re.sub(r'।+', sentence_break, text)
    text = re.sub(r'(?<!\d)\.(?!\d)|(?<=\d)\.(?!\d)|(?<!\d)\.(?=\d)', sentence_break, text)
    
    # 2. कॉमा (,) को थोड़े छोटे ठहराव (50ms) से बदलें
    text = re.sub(r'[,]+', '<break time="50ms"/>', text)
    
    # 3. पूरे टेक्स्ट को <speak> टैग में लपेटें
    return f"<speak>{text}</speak>"

def google_detect_language(text, project_id):
    """
    Uses Google Cloud Translation API to accurately detect the language of the text.
    """
    try:
        # Initialize client cleanly using the explicitly imported class
        translate_client = TranslationServiceClient()
        
        # Location 'global' is required for the text detection endpoint
        parent = f"projects/{project_id}/locations/global"
        
        response = translate_client.detect_language(
            content=text,
            parent=parent,
            mime_type="text/plain"
        )
        
        # Extract the primary language with the highest confidence score
        primary_detection = response.languages[0]
        detected_lang = primary_detection.language_code  # e.g., 'hi' or 'en'
        confidence = primary_detection.confidence
        
        print(f"Google AI Detection: '{detected_lang}' (Confidence: {confidence:.2f})")
        return detected_lang

    except Exception as e:
        print(f"Google Language Detection failed: {e}. Falling back to 'en'.", file=sys.stderr)
        return "en"


def generate_speech_with_auto_detect(text_to_speak, output_filename="output.mp3"):
    """
    Main orchestrator that utilizes Google Detection before creating TTS audio.
    """
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = PATH_TO_JSON_KEY

    if not os.path.exists(PATH_TO_JSON_KEY) or PROJECT_ID == "your-gcp-project-id-12345":
        print("Error: Fix your PROJECT_ID and PATH_TO_JSON_KEY setup at the top of the file.", file=sys.stderr)
        return False

    # 1. Ask Google to identify the language
    detected_lang = google_detect_language(text_to_speak, PROJECT_ID)
    ssml_payload = convert_hindi_text_to_ssml(text_to_speak)
    print(f"Generated SSML for Google TTS:\n{ssml_payload}\n")
    # 2. Match it to our routing map
    voice_profile = VOICE_MAPPING.get(detected_lang, DEFAULT_VOICE)
    print(f"Routing to: {voice_profile['name']} ({voice_profile['language_code']})")

    # 3. Call Google Text-to-Speech
    try:
        tts_client = TextToSpeechClient(
            client_options={"quota_project_id": PROJECT_ID}
        )

        synthesis_input = SynthesisInput(ssml=ssml_payload)
        voice = VoiceSelectionParams(
            language_code=voice_profile["language_code"],
            name=voice_profile["name"]
        )
        audio_config = AudioConfig(
            audio_encoding=AudioEncoding.MP3,
            speaking_rate=0.90,
        )

        print("Requesting voice synthesis...")
        response = tts_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        with open(output_filename, "wb") as out:
            out.write(response.audio_content)
            print(f"Success! Audio written to '{output_filename}'\n")
            return output_filename

    except Exception as e:
        print(f"TTS Error: {e}", file=sys.stderr)
        return False


def get_all_available_voices():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = PATH_TO_JSON_KEY
    client = texttospeech.TextToSpeechClient()
    
    # Request the full list of supported voices from Google Cloud
    response = client.list_voices()
    
    print(f"{'Voice Name':<25} | {'Language Codes':<18} | {'Gender':<10}")
    print("-" * 60)
    
    for voice in response.voices:
        # Pulling the standard SSML gender string enum representation
        gender = texttospeech.SsmlVoiceGender(voice.ssml_gender).name
        languages = ", ".join(voice.language_codes)
        if "hi" in languages or "en" in languages:
            print(f"{voice.name:<25} | {languages:<18} | {gender:<10}")

if __name__ == "__main__":
    # Test 1: Hindi sentence
    generate_speech_with_auto_detect(
        "पुणे में आज मौसम धूप वाला है। तापमान 33 डिग्री सेल्सियस है। Feels like 25.5 डिग्री है, और humidity 34 percent है।",

        output_filename="detected_hindi.mp3"
    )

    # # Test 2: Standard English text
    # generate_speech_with_auto_detect(
    #     "Tomorrow in Pune looks sunny. High around 34.2 degrees and low around 23.5 degrees.", 
    #     output_filename="detected_english.mp3"
    # )
    get_all_available_voices()
