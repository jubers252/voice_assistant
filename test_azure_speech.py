#!/usr/bin/env python3
"""
Test script for Azure Speech Recognition
Tests both direct microphone capture and pre-captured audio
"""

import os
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

load_dotenv()

speech_key = os.getenv('tts_key')
endpoint = os.getenv('tts_endpoint')


def recognize_from_microphone():
    """Test Azure with auto language detection for English and Hindi"""
    print("\n=== Testing Azure with Auto Language Detection ===")
    print("Languages: English (en-US), Hindi (hi-IN)")
    print()
    
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, endpoint=endpoint)
    
    # Configure auto language detection for English and Hindi
    auto_detect_source_language_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
        languages=["en-US", "hi-IN"]
    )

    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    
    # Create recognizer with auto language detection
    speech_recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config,
        auto_detect_source_language_config=auto_detect_source_language_config
    )

    print("Speak into your microphone (English or Hindi)...")
    speech_recognition_result = speech_recognizer.recognize_once_async().get()

    if speech_recognition_result.reason == speechsdk.ResultReason.RecognizedSpeech:
        # Get detected language
        detected_language = speech_recognition_result.properties.get(
            speechsdk.PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult
        )
        print(f"✓ SUCCESS")
        print(f"  Detected Language: {detected_language}")
        print(f"  Recognized: {speech_recognition_result.text}")
    elif speech_recognition_result.reason == speechsdk.ResultReason.NoMatch:
        print(f"✗ NO MATCH: {speech_recognition_result.no_match_details}")
    elif speech_recognition_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_recognition_result.cancellation_details
        print(f"✗ CANCELED: {cancellation_details.reason}")
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print(f"  Error details: {cancellation_details.error_details}")
            print("  Did you set the speech resource key and endpoint values?")

recognize_from_microphone()