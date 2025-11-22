#### IMPORTS ####################
import sounddevice as sd
from scipy.io.wavfile import write
import os


SAMPLE_RATE = 16000
RECORD_SECONDS = 1
SAVE_DIR = os.path.join(os.path.dirname(__file__), "audio_data")  # Always save in model_training/audio
os.makedirs(SAVE_DIR, exist_ok=True)


def record_audio_and_save(save_path, n_times=50):
    """
    This function will run `n_times` and everytime you press Enter you have to speak the wake word

    Parameters
    ----------
    n_times: int, default=50

        The function will run n_times default is set to 50.

    save_path: str
        Where to save the wav file which is generated in every iteration.
    """

    input("To start recording Wake Word press Enter: ")
    for i in range(300, n_times):
        fs = 22050  # Original recording sample rate
        seconds = 2

        myrecording = sd.rec(int(seconds * fs), samplerate=fs, channels=1)
        sd.wait()
        filename = f"wakeword_{i}.wav"
        write(os.path.join(save_path, filename), fs, myrecording)
        input(f"Press to record next or two stop press ctrl + C ({i + 1}/{n_times}): ")

def record_background_sound(save_path, n_times=900):
    """
    This function will run automatically `n_times` and record your background sounds so you can make some
    keybaord typing sound and saying something gibberish.
    Note: Keep in mind that you DON'T have to say the wake word this time.

    Parameters
    ----------
    n_times: int, default=50
        The function will run n_times default is set to 50.

    save_path: str
        Where to save the wav file which is generated in every iteration.
        Note: DON'T set it to the same directory where you have saved the wake word or it will overwrite the files.
    """

    input("To start recording your background sounds press Enter: ")
    for i in range(900, n_times):
        fs = 22050  # Original recording sample rate
        seconds = 2 

        myrecording = sd.rec(int(seconds * fs), samplerate=fs, channels=1)
        sd.wait()
        write(os.path.join(save_path, str(i) + ".wav"), fs, myrecording)
        print(f"Currently on {i+1}/{n_times}")

# Step 1: Record yourself saying the Wake Word
# print("Recording the Wake Word:\n")
# record_background_sound(SAVE_DIR, n_times=1000) 
# Step 2: Record your background sounds (Just let it run, it will auto
# matically record)
# print("Recording the Background sounds:\n")
record_audio_and_save(SAVE_DIR, n_times=350)



# print('Wake word recording tool')
# print('Type "wake" for wake word, "notwake" for non-wake word/background, or "exit" to quit.')

# count = 0
# while True:
#     label = input('Label (wake/notwake/exit): ').strip().lower()
#     if label == 'exit':
#         break
#     if label not in ['wake', 'notwake']:
#         print('Invalid label. Try again.')
#         continue
#     print(f'Recording {label} sample...')
#     recording = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
#     sd.wait()
#     filename = f'{label}_{count}.wav'
#     write(os.path.join(SAVE_DIR, filename), SAMPLE_RATE, recording)
#     print(f'Saved {filename}')
#     count += 1
