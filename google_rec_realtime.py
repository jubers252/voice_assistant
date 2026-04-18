import queue
import sys
import sounddevice as sd
from google.cloud import speech
from dotenv import load_dotenv  

load_dotenv()  # Load environment variables from .env file
# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms chunks

class MicrophoneStream:
    """Opens a recording stream as a generator yielding the audio chunks."""
    def __init__(self, rate, chunk):
        self._rate = rate
        self._chunk = chunk
        self._buff = queue.Queue()
        self.closed = True

    def __enter__(self):
        self.closed = False
        # Create the sounddevice input stream
        self._stream = sd.InputStream(
            samplerate=self._rate,
            channels=1,
            dtype='int16',
            blocksize=self._chunk,
            callback=self._fill_buffer
        )
        self._stream.start()
        return self

    def __exit__(self, type, value, traceback):
        self._stream.stop()
        self._stream.close()
        self.closed = True
        self._buff.put(None)

    def _fill_buffer(self, indata, frames, time, status):
        """Callback to put audio into the queue."""
        if status:
            print(status, file=sys.stderr)
        self._buff.put(indata.tobytes())

    def generator(self):
        while not self.closed:
            chunk = self._buff.get()
            if chunk is None:
                return
            yield chunk

def listen_print_loop(responses):
    """Iterates through server responses and prints them."""
    for response in responses:
        if not response.results:
            continue

        result = response.results[0]
        if not result.alternatives:
            continue

        transcript = result.alternatives[0].transcript

        if result.is_final:
            print(f"Final Result: {transcript}")
        else:
            # Print intermediate results (so you see text as you speak)
            print(f"Interim: {transcript}", end="\r")

def main():
    client = speech.SpeechClient()

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code="en-US",
        alternative_language_codes=["es-ES", "fr-FR", "de-DE", "hi-IN"], # Add up to 4 more
        enable_automatic_punctuation=True,
    )

    streaming_config = speech.StreamingRecognitionConfig(
        config=config, 
        interim_results=True
    )

    with MicrophoneStream(RATE, CHUNK) as stream:
        audio_generator = stream.generator()
        
        # Map the audio chunks to the Request object
        requests = (
            speech.StreamingRecognizeRequest(audio_content=content)
            for content in audio_generator
        )

        print("Listening... (Press Ctrl+C to stop)")
        responses = client.streaming_recognize(
            config=streaming_config,
            requests=requests,
        )

        try:
            listen_print_loop(responses)
        except KeyboardInterrupt:
            print("\nStopped.")

if __name__ == "__main__":
    main()