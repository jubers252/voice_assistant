# Official Voice Assistant Project Structure

## Overview
This document outlines the official folder structure for the Voice Assistant project after refactoring for better modularity, maintainability, and scalability.

## Project Structure

```
voice_assistant/
│
├── 📁 audio/                          # Audio processing components
│   ├── __init__.py
│   ├── audio_processor.py             # Audio recording, streaming, callbacks
│   ├── wake_word_detector.py          # Wake word detection logic
│   └── feature_extractor.py           # MFCC and audio feature extraction
│
├── 📁 speech/                         # Speech recognition and TTS
│   ├── __init__.py
│   ├── speech_recognizer.py           # Speech-to-text functionality
│   ├── text_to_speech.py              # TTS with interruption support
│   └── voice_profiles.py              # Voice selection and profiles
│
├── 📁 conversation/                   # Conversation management
│   ├── __init__.py
│   ├── conversation_manager.py        # Conversation flow and history
│   ├── ai_response_handler.py         # OpenAI API interactions
│   └── context_manager.py             # Context and memory management
│
├── 📁 handlers/                       # Tool-specific handlers
│   ├── __init__.py
│   ├── base_handler.py                # Base class for all handlers
│   ├── spotify_handler.py             # Spotify integration
│   ├── weather_handler.py             # Weather and time services
│   ├── amazon_handler.py              # Amazon product search
│   ├── search_handler.py              # Web search functionality
│   └── order_tracking_handler.py      # Amazon order tracking
│
├── 📁 config/                         # Configuration management
│   ├── __init__.py
│   ├── config.py                      # Main configuration class
│   ├── audio_config.py                # Audio-specific settings
│   ├── api_config.py                  # API keys and endpoints
│   └── device_config.py               # Device-specific configurations
│
├── 📁 utils/                          # Utility functions
│   ├── __init__.py
│   ├── audio_utils.py                 # Audio utility functions
│   ├── text_utils.py                  # Text processing utilities
│   ├── file_utils.py                  # File handling utilities
│   └── decorators.py                  # Common decorators (retry, timing, etc.)
│
├── 📁 connectors/                     # External service connectors (existing)
│   ├── __init__.py
│   ├── spotify_connector.py           # Original Spotify connector
│   ├── weather_connector.py           # Original weather connector
│   ├── amazon_connector.py            # Original Amazon connector
│   ├── search_engine.py               # Original search engine
│   └── ... (other existing connectors)
│
├── 📁 model/                          # ML models (existing)
│   └── WWD_improved.h5                # Wake word detection model
│
├── 📁 model_training/                 # Model training scripts (existing)
│   ├── training.py
│   ├── prediction.py
│   └── ... (other training files)
│
├── 📁 data/                           # Data storage
│   ├── conversation_history.json      # Moved from root
│   ├── user_preferences.json          # User settings
│   └── cache/                         # Temporary cache files
│
├── 📁 beep/                           # Audio assets (existing)
│   ├── short-beep-tone-47916.mp3
│   └── startup_sound.wav
│
├── 📁 output/                         # Output files (existing)
│   ├── amazon_session.pkl
│   └── ... (other output files)
│
├── 📁 tests/                          # Unit and integration tests
│   ├── __init__.py
│   ├── test_audio_processor.py        # Audio processing tests
│   ├── test_speech_services.py        # Speech service tests
│   ├── test_conversation_manager.py   # Conversation tests
│   ├── test_handlers.py               # Handler tests
│   └── test_integration.py            # End-to-end tests
│
├── 📁 docs/                           # Documentation
│   ├── API.md                         # API documentation
│   ├── SETUP.md                       # Setup instructions
│   ├── ARCHITECTURE.md                # Architecture overview
│   └── CONTRIBUTING.md                # Contribution guidelines
│
├── 📄 voice_assistant.py              # Main orchestrator class (refactored)
├── 📄 main.py                         # Entry point for the application
├── 📄 requirements.txt                # Python dependencies
├── 📄 .env.example                    # Environment variables template
├── 📄 .gitignore                      # Git ignore file
├── 📄 README.md                       # Project overview
├── 📄 CHANGELOG.md                    # Version history
└── 📄 FOLDER_STRUCTURE.md             # This file
```

## Module Descriptions

### 🎵 Audio Module (`audio/`)
Handles all audio-related operations including recording, streaming, wake word detection, and feature extraction.

**Key Files:**
- `audio_processor.py` - Main audio processing class
- `wake_word_detector.py` - Wake word detection logic
- `feature_extractor.py` - MFCC and audio feature extraction

### 🗣️ Speech Module (`speech/`)
Manages speech recognition and text-to-speech functionality with advanced features like interruption support.

**Key Files:**
- `speech_recognizer.py` - Speech-to-text conversion
- `text_to_speech.py` - TTS with interruption and threading
- `voice_profiles.py` - Voice selection and configuration

### 💬 Conversation Module (`conversation/`)
Handles conversation flow, AI interactions, and context management.

**Key Files:**
- `conversation_manager.py` - Main conversation orchestrator
- `ai_response_handler.py` - OpenAI API integration
- `context_manager.py` - Context and memory management

### 🔧 Handlers Module (`handlers/`)
Contains tool-specific handlers for various external services.

**Key Files:**
- `base_handler.py` - Base class with common functionality
- Individual handler files for each service (Spotify, Weather, Amazon, etc.)

### ⚙️ Config Module (`config/`)
Centralized configuration management for all aspects of the application.

**Key Files:**
- `config.py` - Main configuration class
- Specific config files for different components

### 🛠️ Utils Module (`utils/`)
Common utility functions used across the application.

**Key Files:**
- Various utility modules for different purposes
- `decorators.py` - Common decorators for retry, timing, etc.

## Migration Benefits

### 1. **Separation of Concerns**
Each module has a specific responsibility, making the code easier to understand and maintain.

### 2. **Improved Testability**
Individual components can be tested in isolation with unit tests.

### 3. **Better Scalability**
New features can be added as separate modules without affecting existing functionality.

### 4. **Enhanced Reusability**
Modules can be reused in other projects or imported independently.

### 5. **Easier Debugging**
Issues can be isolated to specific modules, making debugging more efficient.

### 6. **Team Development**
Multiple developers can work on different modules simultaneously.

## Implementation Strategy

1. **Phase 1**: Create module structure and base classes
2. **Phase 2**: Extract and refactor existing functionality
3. **Phase 3**: Implement new modular architecture
4. **Phase 4**: Add comprehensive tests
5. **Phase 5**: Update documentation and examples

## Backward Compatibility

The refactored structure maintains backward compatibility with existing code while providing a cleaner, more maintainable architecture for future development.