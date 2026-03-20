#### IMPORTS ####################
import sounddevice as sd
from scipy.io.wavfile import write
import os
import numpy as np


SAMPLE_RATE = 16000  # 22.05 kHz
RECORD_SECONDS = 2
DIGITAL_GAIN = 1.0  # Amplify recorded audio (1.0 = no gain, 5.0 = 5x louder)
SAVE_DIR = os.path.join(os.path.dirname(__file__), "audio_data")  # Always save in model_training/audio_data
os.makedirs(SAVE_DIR, exist_ok=True)


def apply_digital_gain(audio, gain=DIGITAL_GAIN):
    
    """
    Apply digital gain to audio data.
    
    Parameters:
    -----------
    audio: numpy array
        Audio samples
    gain: float
        Gain multiplier (1.0 = no change, 4.0 = 4x louder)
    
    Returns:
    --------
    numpy array
        Amplified audio (clipped to prevent overflow)
    """
    amplified = audio * gain
    
    # Clip to prevent overflow (keep in valid range)
    # For 16-bit audio: -32768 to 32767
    amplified = np.clip(amplified, -1.0, 1.0)
    
    return amplified


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
    for i in range(0, n_times):
        myrecording = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
        sd.wait()
        
        # Apply digital gain
        # myrecording = apply_digital_gain(myrecording, gain=DIGITAL_GAIN)
        
        filename = f"wakeword_{i}.wav"
        write(os.path.join(save_path, filename), SAMPLE_RATE, myrecording)
        input(f"Press to record next or two stop press ctrl + C ({i + 1}/{n_times}): ")

def record_background_sound(save_path, n_times=2500):
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
    for i in range(4000, n_times):
        myrecording = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
        sd.wait()
        write(os.path.join(save_path, str(i) + ".wav"), SAMPLE_RATE, myrecording)
        print(f"Currently on {i+1}/{n_times}")

# Step 1: Record yourself saying the Wake Word
# print("record_audio_and_save the Wake Word:\n")
record_audio_and_save(SAVE_DIR, n_times=150)

# Step 2: Record your background sounds (Just let it run, it will automatically record)
# matically record)
# print("Recording the Background sounds:\n")
# record_audio_and_save(SAVE_DIR, n_times=400)



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
