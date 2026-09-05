import os
import tempfile
import time

from dotenv import load_dotenv
import azure.cognitiveservices.speech as speechsdk


load_dotenv()


VOICE_MAPPING = {
    "hi": "hi-IN-AartiNeural",
    "en": "en-IN-AartiNeural",
}
DEFAULT_VOICE = VOICE_MAPPING["en"]


def generate_azure_tts(text, speech_file_path=None, lang="en"):
    """Generate speech with Azure TTS and save it to a wav file.

    Returns the generated file path on success, or None on failure.
    """
    start_time = time.time()

    try:
        azure_key = os.getenv("tts_key")
        azure_region = os.getenv("tts_region", "centralindia")

        if not azure_key:
            raise ValueError("Azure TTS key not found in environment (tts_key)")

        if not speech_file_path:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            speech_file_path = tmp.name
            tmp.close()

        voice_name = VOICE_MAPPING.get(lang, DEFAULT_VOICE)

        azure_config = speechsdk.SpeechConfig(subscription=azure_key, region=azure_region)
        azure_config.speech_synthesis_voice_name = voice_name

        audio_config = speechsdk.audio.AudioOutputConfig(filename=speech_file_path)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=azure_config,
            audio_config=audio_config,
        )

        print(f"Generating Azure TTS (voice={voice_name}, lang={lang})")
        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            generation_time = time.time() - start_time
            print(f"Azure TTS generation took: {generation_time:.2f} seconds -> {speech_file_path}")
            return speech_file_path

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print(f"Azure TTS canceled: {cancellation_details.reason}")
            if cancellation_details.error_details:
                print(f"Error details: {cancellation_details.error_details}")

        return None

    except Exception as e:
        print(f"Azure TTS error: {e}")
        return None
