# 📁 Voice Assistant - Folder Structure Documentation

This document provides a comprehensive overview of the project's folder structure and the purpose of each component.

## 🏗️ Project Architecture Overview

```
voice_assistant/
├── 🎵 audio/              # Audio processing and text-to-speech
├── 🔌 connectors/         # External service integrations  
├── 💬 conversation/       # AI chat and conversation management
├── 🎯 handlers/           # Coordination and routing logic
├── 🗣️ speech/            # Speech recognition
├── 🧠 model/             # Machine learning models
├── 📊 model_training/     # Training scripts and data
├── 🔊 beep/              # Audio notification files
├── 📊 data/              # Application data storage
├── 📤 output/            # Generated output files
└── 🧪 tests/             # Unit tests and testing
```

## 📂 Detailed Directory Structure

### 🎵 `audio/` - Audio Processing Module
```
audio/
├── __init__.py                    # Module initialization
├── audio_processor.py            # Core audio I/O and TTS processing
└── wake_word_detector.py         # Neural network-based wake word detection
```

**Purpose**: Handles all audio-related functionality including:
- Text-to-speech synthesis (Edge TTS with Hindi/English support)
- Audio input/output stream management
- Wake word detection using trained neural network
- Audio callback handling and buffering

### 🔌 `connectors/` - External Service Integrations
```
connectors/
├── __init__.py                    # Module initialization
├── spotify_connector.py          # Spotify Web API integration
├── weather_connector.py          # Weather API integration  
├── search_engine.py              # DuckDuckGo web search
├── amazon_order_tracker.py       # Amazon order tracking logic
├── amzon_connector.py            # Amazon web scraping utilities
├── reminder_manager.py           # Reminder system management
├── amazon_in_constants.py        # Amazon India specific constants
└── amazon_in_selectors.py        # Web scraping selectors for Amazon
```

**Purpose**: Contains all external service integrations:
- **Spotify**: Music playback, playlist management, search
- **Weather**: Real-time weather data fetching
- **Search**: Web search capabilities via DuckDuckGo
- **Amazon**: Order tracking and account management
- **Reminders**: Time-based reminder system

### 💬 `conversation/` - AI Chat Management
```
conversation/
├── __init__.py                    # Module initialization
├── conversation_manager.py       # Conversation state and history
├── ai_respons_handler.py         # OpenAI API integration
└── feedback_handler.py           # User feedback processing
```

**Purpose**: Manages AI-powered conversations:
- **ConversationManager**: Maintains conversation history and context
- **AIResponseHandler**: Interfaces with OpenAI GPT-4 API
- **FeedbackHandler**: Processes user feedback and responses

### 🎯 `handlers/` - Coordination Logic
```
handlers/
├── __init__.py                    # Module initialization
├── wake_word_manager.py          # Wake word detection coordination
├── command_processor.py          # User command routing and processing
└── tool_action_handler.py        # AI-powered intent recognition
```

**Purpose**: Acts as the "traffic control" layer:
- **WakeWordManager**: Coordinates wake word detection with audio processing
- **CommandProcessor**: Routes user commands to appropriate connectors
- **ToolActionHandler**: Uses AI to determine user intent and route to tools

### 🗣️ `speech/` - Speech Recognition
```
speech/
├── __init__.py                    # Module initialization
└── speech_recognizer.py          # Speech-to-text processing
```

**Purpose**: Handles speech-to-text conversion:
- Voice activity detection
- Speech recognition using system APIs
- Audio preprocessing for better recognition

### 🧠 `model/` - Machine Learning Models
```
model/
└── WWD_improved.h5               # Trained wake word detection model
```

**Purpose**: Stores trained machine learning models:
- **WWD_improved.h5**: Wake word detection neural network model

### 📊 `model_training/` - Training Infrastructure
```
model_training/
├── training.py                   # Main model training script
├── PreparingData.py             # Audio data collection and preparation
├── PreprocessingData.py         # Data preprocessing and feature extraction
├── prediction.py                # Model prediction and testing
├── audio_data/                  # Wake word audio samples
│   ├── wakeword_0.wav
│   ├── wakeword_1.wav
│   └── ... (training samples)
├── background_sound/            # Background noise samples
├── final_audio_data_csv/        # Processed training data in CSV format
└── saved_model/                 # Model checkpoints and versions
```

**Purpose**: Complete training pipeline for wake word detection:
- Data collection and augmentation
- Feature extraction and preprocessing
- Model training and validation
- Performance testing and evaluation

### 🔊 `beep/` - Audio Assets
```
beep/
├── short-beep-tone-47916.mp3    # Wake word detection notification
└── startup_sound.wav            # Application startup sound
```

**Purpose**: Audio notification files for user feedback

### 📊 `data/` - Application Data
```
data/
└── conversation_history.json    # Persistent conversation logs
```

**Purpose**: Stores application data and user information

### 📤 `output/` - Generated Files
```
output/
├── amazon_session.pkl           # Amazon login session data
├── orders_last_5_days_page_0.html # Amazon order pages (cached)
└── orders_last_5_days_page_1.html
```

**Purpose**: Temporary and cached files generated during operation

## 🔧 Root Level Files

```
├── voice_assistant.py              # Main application entry point
├── requirements.txt                # Python package dependencies
├── .env                           # Environment variables (create manually)
├── setup.txt                     # Setup and installation instructions
├── reminders.json                # Persistent reminder storage
├── temp_audio.wav                # Temporary audio recording file
├── README.md                     # Project documentation
└── FOLDER_STRUCTURE.md           # This file
```

## 🔄 Data Flow Architecture

```
User Voice Input
       ↓
🎵 audio/wake_word_detector.py
       ↓
🎯 handlers/wake_word_manager.py
       ↓
🗣️ speech/speech_recognizer.py
       ↓
🎯 handlers/command_processor.py
       ↓
🎯 handlers/tool_action_handler.py (AI Intent Recognition)
       ↓
🔌 connectors/* (Appropriate Service)
       ↓
💬 conversation/ai_respons_handler.py (If needed)
       ↓
🎵 audio/audio_processor.py (TTS Output)
       ↓
User Audio Output
```

## 🎛️ Module Dependencies

### Core Dependencies
- `audio/` ← Base audio processing
- `speech/` ← Speech recognition
- `conversation/` ← AI conversation management

### Handler Dependencies
- `handlers/wake_word_manager.py` ← `audio/`, `speech/`
- `handlers/command_processor.py` ← `connectors/*`, `conversation/`
- `handlers/tool_action_handler.py` ← OpenAI API

### Connector Dependencies
- `connectors/spotify_connector.py` ← Spotify Web API
- `connectors/weather_connector.py` ← Weather API
- `connectors/search_engine.py` ← DuckDuckGo
- `connectors/amazon_*.py` ← Web scraping libraries

## 🚀 Extension Points

### Adding New Connectors
1. Create new file in `connectors/`
2. Implement standard interface methods
3. Add routing logic in `handlers/command_processor.py`
4. Update intent recognition in `handlers/tool_action_handler.py`

### Adding New Audio Features
1. Extend `audio/audio_processor.py` for new TTS capabilities
2. Modify `audio/wake_word_detector.py` for additional detection models

### Adding New AI Capabilities
1. Extend `conversation/ai_respons_handler.py` for new AI models
2. Add new conversation types in `conversation/conversation_manager.py`

## 📈 Performance Considerations

### Memory Usage
- **Model Loading**: Wake word model (~50MB) loaded at startup
- **Audio Buffers**: Real-time audio buffering (~1-2MB)
- **Conversation History**: Limited to recent conversations

### Processing Speed
- **Wake Word Detection**: Real-time processing with 300ms latency
- **Speech Recognition**: 1-2 seconds for typical commands
- **AI Response**: 2-3 seconds depending on OpenAI API

### Optimization Tips
- Models loaded once at startup
- Audio processing in separate threads
- Caching for frequently used data
- Efficient memory management for audio buffers

---

This modular architecture ensures:
- **Maintainability**: Easy to modify individual components
- **Scalability**: Simple to add new features and connectors
- **Testability**: Each module can be tested independently
- **Readability**: Clear separation of concerns and responsibilities