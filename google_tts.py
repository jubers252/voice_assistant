from google.cloud import texttospeech
from google.oauth2 import service_account


creds = service_account.Credentials.from_service_account_file(
    "/home/jubers/Documents/voice_assistant/nimble-gate-366207-d1ca63590ec3.json"
)

client = texttospeech.TextToSpeechClient(credentials=creds)
response = client.synthesize_speech(
    input=texttospeech.SynthesisInput(text="Hello! how are you doing today?"),
    voice=texttospeech.VoiceSelectionParams(
        language_code="en-IN",
        name="en-IN-Chirp3-HD-Zephyr",
    ),
    audio_config=texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=0.90,
    )
)

with open("test_hindi.mp3", "wb") as f:
    f.write(response.audio_content)

print("✅ Google Hindi TTS working")


response = client.list_voices()

for voice in response.voices:
    if "en-IN" in voice.language_codes:
        print(voice.name, voice.ssml_gender.name)