
from dotenv import load_dotenv
import speech_recognition as sr

# Load environment variables
load_dotenv()

class SpeechRecognizer:
    def __init__(self, device_index=1):
        self.device_index = device_index
        self.recognizer = sr.Recognizer()
        self._setup_recognizer()

    def _setup_recognizer(self):
        self.recognizer.energy_threshold = 400
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 1.5
        self.recognizer.phrase_threshold = 0.5
        self.recognizer.non_speaking_duration = 1.5

    def _print_attempt(self, retry_count, is_follow_up):
        if retry_count == 0:
            print("Please respond..." if is_follow_up else "Say your command...")
        else:
            print(f"I didn't catch that. Please try again... (attempt {retry_count + 1})")

    def listen_for_command(self, timeout=20, is_follow_up=False, max_retries=2):
        """
        Listen for user command with follow-up functionality and retry logic.
        """
        if is_follow_up:
            print("[ASSISTANT] Listening for follow-up response...")
            timeout = min(timeout, 20)
        else:
            print("[ASSISTANT] Listening for command...")

        retry_count = 0
        while retry_count <= max_retries:
            try:
                with sr.Microphone(device_index=self.device_index) as source:
                    self._print_attempt(retry_count, is_follow_up)
                    print("i m listening...")
                    listen_timeout = timeout if retry_count == 0 else timeout + 3
                    audio = self.recognizer.listen(source, timeout=listen_timeout, phrase_time_limit=12)

                print(f"[ASSISTANT] Audio length: {len(audio.frame_data) / audio.sample_rate:.2f} seconds")
                print("Recognizing...")

                if len(audio.frame_data) < 1000:
                    print("[ASSISTANT] Audio too short, trying again...")
                    retry_count += 1
                    continue

                command = self._recognize_audio(audio)
                if command:
                    return command
                else:
                    retry_count += 1
                    continue

            except sr.WaitTimeoutError:
                print(f"[ASSISTANT] No speech detected. Trying again... ({retry_count + 1}/{max_retries + 1})")
                retry_count += 1
                continue
            except Exception as e:
                print(f"[ASSISTANT] Recognition failed: {e}. Trying again... ({retry_count + 1}/{max_retries + 1})")
                retry_count += 1
                continue
        print("[ASSISTANT] No valid command detected after multiple attempts.")
        return None

    def _recognize_audio(self, audio):
        try:
            command = self.recognizer.recognize_google(audio, language='en-US')
            print(f"[ASSISTANT] You said: {command}")
            cleaned_command = command.lower().strip()
            if len(cleaned_command) < 2:
                print("[ASSISTANT] Command too short, trying again...")
                return None
            return cleaned_command
        except (sr.RequestError, sr.UnknownValueError) as e:
            print(f"[ASSISTANT] Recognition error: {e}.")
            return None