# Intelligent Voice Assistant

A sophisticated voice-activated AI assistant built with Python, featuring wake word detection, natural language processing, and integration with multiple services like Spotify, weather, web search, and more.

## Features

- **Wake Word Detection** - Custom trained neural network for hands-free activation
- **AI-Powered Conversations** - OpenAI GPT-4 integration for intelligent responses
- **Spotify Control** - Play music, playlists, and control playback
- **Weather Updates** - Real-time weather information
- **Web Search** - DuckDuckGo integration for web queries
- **Amazon Order Tracking** - Check your recent orders and delivery status
- **Smart Reminders** - Set and manage time-based reminders
- **Multi-language TTS** - Enhanced Hindi and English text-to-speech
- **Modular Architecture** - Clean, maintainable, and extensible codebase

## Architecture

The project follows a modular architecture with clear separation of concerns:

```
voice_assistant/
├── audio/              # Audio processing and TTS
├── connectors/         # External service integrations  
├── conversation/       # AI chat and conversation logic
├── handlers/           # Coordination and routing logic
├── speech/            # Speech recognition
├── model/             # Wake word detection models
├── model_training/     # Training scripts and data
└── Main files
```

### Detailed Folder Structure

```
voice_assistant/
├── voice_assistant.py              # Main application entry point
├── voice_assistant_refactored.py   # Refactored modular version
├── requirements.txt                # Python dependencies
├── .env                           # Environment variables (create this)
├── setup.txt                      # Setup instructions
├── reminders.json                 # Persistent reminders storage
│
├── audio/
│   ├── __init__.py
│   ├── audio_processor.py            # Audio I/O and TTS processing
│   └── wake_word_detector.py         # Neural network wake word detection
│
├── connectors/
│   ├── __init__.py
│   ├── spotify_connector.py          # Spotify Web API integration
│   ├── weather_connector.py          # Weather API integration
│   ├── search_engine.py              # DuckDuckGo web search
│   ├── amazon_order_tracker.py       # Amazon order tracking
│   ├── amzon_connector.py            # Amazon web scraping
│   ├── reminder_manager.py           # Reminder system
│   ├── amazon_in_constants.py        # Amazon India constants
│   └── amazon_in_selectors.py        # Amazon web selectors
│
├── conversation/
│   ├── __init__.py
│   ├── conversation_manager.py       # Conversation state management
│   ├── ai_respons_handler.py        # OpenAI API integration
│   └── feedback_handler.py          # User feedback processing
│
├── handlers/
│   ├── __init__.py
│   ├── wake_word_manager.py          # Wake word detection coordination
│   ├── command_processor.py          # User command routing
│   └── tool_action_handler.py        # AI-powered intent recognition
│
├── speech/
│   ├── __init__.py
│   └── speech_recognizer.py          # Speech-to-text processing
│
├── model/
│   └── WWD_improved.h5               # Trained wake word model
│
├── model_training/
│   ├── training.py                   # Model training script
│   ├── PreparingData.py             # Data preparation
│   ├── PreprocessingData.py         # Data preprocessing
│   ├── prediction.py                # Model prediction testing
│   ├── audio_data/                  # Training audio samples
│   ├── background_sound/            # Background noise samples
│   ├── final_audio_data_csv/        # Processed training data
│   └── saved_model/                 # Model checkpoints
│
├── beep/
│   ├── short-beep-tone-47916.mp3    # Notification sound
│   └── startup_sound.wav            # Startup sound
│
├── data/
│   └── conversation_history.json    # Conversation logs
│
├── output/
│   ├── amazon_session.pkl           # Amazon session data
│   └── *.html                       # Amazon order pages
│
└── tests/
    └── __init__.py                   # Unit tests (future)
```

## Quick Start

### Prerequisites

- Python 3.8+ 
- Microphone and speakers
- Internet connection for AI and external services

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd voice_assistant
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**
Create a `.env` file in the root directory:
```env
# OpenAI API
OPENAI_API_KEY=your_openai_api_key

# Spotify API (optional)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

# Weather API (optional)
WEATHER_API_KEY=your_weather_api_key

# Amazon credentials (optional)
AMAZON_EMAIL=your_amazon_email
AMAZON_PASSWORD=your_amazon_password
```

4. **Run the assistant**
```bash
python voice_assistant.py
```

## Usage

### Basic Commands

- **Wake Word**: Say your configured wake word to activate
- **Conversations**: Ask questions, get AI responses
- **Music**: "Play some jazz music" or "Play my liked songs"
- **Weather**: "What's the weather like?" or "Weather in New York"
- **Search**: "Search for Python tutorials"
- **Reminders**: "Set reminder for 3 PM to call mom"
- **Orders**: "Check my Amazon orders"
- **Exit**: "Goodbye" or "Exit"

### Advanced Features

- **Contextual Conversations**: The assistant remembers conversation context
- **Multi-language Support**: Responds in Hindi and English
- **Background Processing**: Runs wake word detection in background
- **Error Recovery**: Graceful handling of network and API errors

## Configuration

### Audio Settings
- **Sample Rate**: 22050 Hz (configurable in audio_processor.py)
- **Wake Word Confidence**: Adjustable threshold in wake_word_detector.py
- **TTS Voices**: Configurable in audio_processor.py

### AI Settings
- **Model**: GPT-4.1 (configurable in ai_respons_handler.py)
- **Max Tokens**: 150 (adjustable for longer responses)
- **Temperature**: 0.7 (creativity level)

## External Services

### Required
- **OpenAI API**: For AI conversations and intent recognition

### Optional
- **Spotify Web API**: Music playback control
- **OpenWeatherMap API**: Weather information
- **Amazon Account**: Order tracking (uses web scraping)

## Running Different Versions

```bash
# Modular refactored version (recommended)
python voice_assistant.py


```

## Wake Word Training

To train your own wake word:

1. **Collect Audio Samples**
```bash
cd model_training
python PreparingData.py
```

2. **Preprocess Data**
```bash
python PreprocessingData.py
```

3. **Train Model**
```bash
python training.py
```

4. **Test Predictions**
```bash
python prediction.py
```

## Troubleshooting

### Common Issues

**Wake word not detected**
- Check microphone permissions
- Verify model file exists in `model/` directory
- Adjust confidence threshold in wake_word_detector.py

**No audio output**
- Check speaker/headphone connections
- Verify TTS engine installation
- Check audio device settings

**API errors**
- Verify API keys in .env file
- Check internet connection
- Ensure API quotas are not exceeded

**Import errors**
- Run `pip install -r requirements.txt`
- Check Python version compatibility
- Verify all modules are in correct directories

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Development

### Adding New Connectors

1. Create new connector in `connectors/` directory
2. Implement required methods (handle_action, etc.)
3. Add connector to `command_processor.py`
4. Update tool routing in `tool_action_handler.py`

### Code Style
- Follow PEP 8 conventions
- Use type hints where possible
- Add docstrings to all functions
- Keep functions focused and small

## Performance

- **Wake Word Detection**: ~300ms response time
- **Speech Recognition**: ~1-2 seconds
- **AI Response**: ~2-3 seconds (depends on OpenAI API)
- **Memory Usage**: ~100-200MB typical usage

## Privacy & Security

- **Local Processing**: Wake word detection runs locally
- **API Communications**: Secure HTTPS connections
- **Data Storage**: Minimal local conversation history
- **Credentials**: Stored securely in .env file (not committed)

## Future Enhancements

- [ ] Voice cloning and custom TTS voices
- [ ] Multi-user support with voice recognition
- [ ] Smart home device integration
- [ ] Mobile app companion
- [ ] Cloud deployment options
- [ ] Plugin system for easy extensions
- [ ] Visual dashboard for configuration

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- OpenAI for GPT-4 API
- Microsoft Edge TTS for voice synthesis
- Spotify for music API
- Python community for excellent libraries

---

**Made with care by Juber**

*For support, please open an issue on GitHub*
