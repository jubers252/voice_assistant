import os
from pydoc import text
import requests
from dotenv import load_dotenv
import logging
from typing import Optional, Union, Dict, Any

# Set up logging  
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Telegram Bot class for sending messages, images, and media using Telegram Bot API
    """
    
    def __init__(self, bot_token: Optional[str] = None):
        """
        Initialize Telegram Bot
        
        Args:
            bot_token (str): Telegram Bot Token (optional, will use env var if not provided)
        """
        load_dotenv()
        
        self.bot_token = bot_token or os.getenv('TELEGRAM_TOKEN')
        
        if not self.bot_token:
            raise ValueError("Missing Telegram Bot Token. Please set TELEGRAM_BOT_TOKEN environment variable or pass it as parameter.")
        
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        # Test the bot token
        if self._test_connection():
            logger.info("Telegram Bot initialized successfully")
        else:
            raise ValueError("Invalid Telegram Bot Token or connection failed")
    
    def _test_connection(self) -> bool:
        """
        Test the bot token by calling getMe API
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/getMe", timeout=10)
            if response.status_code == 200:
                bot_info = response.json()
                if bot_info.get('ok'):
                    logger.info(f"Bot connected: @{bot_info['result']['username']}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def _make_request(self, method: str, data: Dict[str, Any], file_field: Optional[str] = None) -> Dict[str, Any]:
        """
        Make a request to Telegram Bot API
        
        Args:
            method (str): API method name
            data (dict): Request data
            file_field (str): Name of the field containing file path (e.g., 'photo', 'document')
            
        Returns:
            dict: API response
        """
        try:
            url = f"{self.base_url}/{method}"
            
            # Handle file uploads
            files = None
            if file_field and file_field in data:
                file_path = data[file_field]
                
                # Check if it's a local file path (not a URL or file_id)
                if isinstance(file_path, str) and os.path.isfile(file_path):
                    files = {file_field: open(file_path, 'rb')}
                    # Remove from data since it will be sent as files
                    data = {k: v for k, v in data.items() if k != file_field}
            
            # For long-polling (getUpdates), the HTTP read timeout must exceed the poll timeout
            poll_timeout = data.get('timeout', 0) if method == 'getUpdates' else 0
            http_timeout = max(30, poll_timeout + 10)

            # Send request with files if provided
            if files:
                try:
                    response = requests.post(url, data=data, files=files, timeout=http_timeout)
                    response.raise_for_status()
                    return response.json()
                finally:
                    # Close all opened files
                    for file_obj in files.values():
                        if hasattr(file_obj, 'close'):
                            file_obj.close()
            else:
                response = requests.post(url, data=data, timeout=http_timeout)
                response.raise_for_status()
                return response.json()
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return {"ok": False, "error": str(e)}
    
    def send_message(self, chat_id: Union[str, int], text: str, parse_mode: str = "HTML") -> Optional[Dict[str, Any]]:
        """
        Send a text message
        
        Args:
            chat_id (str|int): Chat ID or username (@username)
            text (str): Message text to send
            parse_mode (str): Parse mode (HTML, Markdown, or None)
        
        Returns:
            dict: Message info if successful, None if failed
        """
        try:
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            
            response = self._make_request('sendMessage', data)
            
            if response.get('ok'):
                message_id = response['result']['message_id']
                logger.info(f"Message sent successfully! Message ID: {message_id}")
                return response['result']
            else:
                logger.error(f"Failed to send message: {response.get('description', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
    
    def send_photo(self, chat_id: Union[str, int], photo: str, caption: str = "", parse_mode: str = "HTML") -> Optional[Dict[str, Any]]:
        """
        Send a photo
        
        Args:
            chat_id (str|int): Chat ID or username
            photo (str): Photo URL or file path
            caption (str): Photo caption
            parse_mode (str): Parse mode for caption
        
        Returns:
            dict: Message info if successful, None if failed
        """
        try:
            data = {
                'chat_id': chat_id,
                'photo': photo,
                'caption': caption,
                'parse_mode': parse_mode
            }
            
            response = self._make_request('sendPhoto', data, file_field='photo')
            
            if response.get('ok'):
                message_id = response['result']['message_id']
                logger.info(f"Photo sent successfully! Message ID: {message_id}")
                return response['result']
            else:
                logger.error(f"Failed to send photo: {response.get('description', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error sending photo: {e}")
            return None
    
    def send_document(self, chat_id: Union[str, int], document: str, caption: str = "", parse_mode: str = "HTML") -> Optional[Dict[str, Any]]:
        """
        Send a document
        
        Args:
            chat_id (str|int): Chat ID or username
            document (str): Document URL or file path
            caption (str): Document caption
            parse_mode (str): Parse mode for caption
        
        Returns:
            dict: Message info if successful, None if failed
        """
        try:
            data = {
                'chat_id': chat_id,
                'document': document,
                'caption': caption,
                'parse_mode': parse_mode
            }
            
            response = self._make_request('sendDocument', data, file_field='document')
            
            if response.get('ok'):
                message_id = response['result']['message_id']
                logger.info(f"Document sent successfully! Message ID: {message_id}")
                return response['result']
            else:
                logger.error(f"Failed to send document: {response.get('description', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error sending document: {e}")
            return None
    
    def send_video(self, chat_id: Union[str, int], video: str, caption: str = "", parse_mode: str = "HTML") -> Optional[Dict[str, Any]]:
        """
        Send a video
        
        Args:
            chat_id (str|int): Chat ID or username
            video (str): Video URL or file path
            caption (str): Video caption
            parse_mode (str): Parse mode for caption
        
        Returns:
            dict: Message info if successful, None if failed
        """
        try:
            data = {
                'chat_id': chat_id,
                'video': video,
                'caption': caption,
                'parse_mode': parse_mode
            }
            
            response = self._make_request('sendVideo', data)
            
            if response.get('ok'):
                message_id = response['result']['message_id']
                logger.info(f"Video sent successfully! Message ID: {message_id}")
                return response['result']
            else:
                logger.error(f"Failed to send video: {response.get('description', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error sending video: {e}")
            return None
    
    def send_audio(self, chat_id: Union[str, int], audio: str, caption: str = "", parse_mode: str = "HTML") -> Optional[Dict[str, Any]]:
        """
        Send an audio file
        
        Args:
            chat_id (str|int): Chat ID or username
            audio (str): Audio URL or file path
            caption (str): Audio caption
            parse_mode (str): Parse mode for caption
        
        Returns:
            dict: Message info if successful, None if failed
        """
        try:
            data = {
                'chat_id': chat_id,
                'audio': audio,
                'caption': caption,
                'parse_mode': parse_mode
            }
            
            response = self._make_request('sendAudio', data)
            
            if response.get('ok'):
                message_id = response['result']['message_id']
                logger.info(f"Audio sent successfully! Message ID: {message_id}")
                return response['result']
            else:
                logger.error(f"Failed to send audio: {response.get('description', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            return None
    
    def get_chat_info(self, chat_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """
        Get information about a chat
        
        Args:
            chat_id (str|int): Chat ID or username
        
        Returns:
            dict: Chat info if successful, None if failed
        """
        try:
            data = {'chat_id': chat_id}
            response = self._make_request('getChat', data)
            
            if response.get('ok'):
                return response['result']
            else:
                logger.error(f"Failed to get chat info: {response.get('description', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting chat info: {e}")
            return None
    
    def get_bot_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the bot
        
        Returns:
            dict: Bot info if successful, None if failed
        """
        try:
            response = requests.get(f"{self.base_url}/getMe", timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return result['result']
            return None
        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
            return None

    def get_updates(self, offset: int = 0, timeout: int = 30, allowed_updates: list = None) -> Optional[list]:
        """
        Get pending messages and updates from Telegram (polling method)
        
        Args:
            offset (int): ID of the first update to be returned
            timeout (int): Timeout in seconds for long polling
            allowed_updates (list): Types of updates to receive (e.g., ['message', 'callback_query'])
        
        Returns:
            list: List of updates, or None if failed
        """
        try:
            data = {
                'offset': offset,
                'timeout': timeout
            }
            
            if allowed_updates:
                # Convert list to JSON format for API
                import json
                data['allowed_updates'] = json.dumps(allowed_updates)
            
            response = self._make_request('getUpdates', data)
            
            if response.get('ok'):
                updates = response.get('result', [])
                if updates:
                    logger.info(f"Received {len(updates)} update(s)")
                return updates
            else:
                error_msg = response.get('description') or response.get('error', 'Unknown error')
                logger.error(f"Failed to get updates: {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
            return None
    
    def extract_message_data(self, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract message data from a Telegram update
        
        Args:
            update (dict): Update object from Telegram API
        
        Returns:
            dict: Extracted message data including message text, sender info, etc.
        """
        try:
            if 'message' not in update:
                return None
            
            message = update['message']
            update_id = update.get('update_id')
            
            # Extract basic message info
            message_data = {
                'update_id': update_id,
                'message_id': message.get('message_id'),
                'chat_id': message['chat']['id'],
                'sender_id': message['from']['id'],
                'sender_name': message['from'].get('first_name', '') + ' ' + message['from'].get('last_name', ''),
                'sender_username': message['from'].get('username', 'N/A'),
                'timestamp': message.get('date'),
                'type': 'unknown'
            }
            
            # Extract content based on message type
            if 'text' in message:
                message_data['type'] = 'text'
                message_data['content'] = message['text']
            elif 'photo' in message:
                message_data['type'] = 'photo'
                message_data['photo_id'] = message['photo'][-1]['file_id']  # Get largest photo
                message_data['caption'] = message.get('caption', '')
            elif 'document' in message:
                message_data['type'] = 'document'
                message_data['document_id'] = message['document']['file_id']
                message_data['file_name'] = message['document'].get('file_name', '')
                message_data['caption'] = message.get('caption', '')
            elif 'audio' in message:
                message_data['type'] = 'audio'
                message_data['audio_id'] = message['audio']['file_id']
                message_data['caption'] = message.get('caption', '')
            elif 'voice' in message:
                message_data['type'] = 'voice'
                message_data['voice_id'] = message['voice']['file_id']
            elif 'video' in message:
                message_data['type'] = 'video'
                message_data['video_id'] = message['video']['file_id']
                message_data['caption'] = message.get('caption', '')
            
            return message_data
            
        except Exception as e:
            logger.error(f"Error extracting message data: {e}")
            return None
    
    def receive_messages(self, callback=None, allowed_updates: list = None):
        """
        Continuously receive messages from users (blocking polling loop)
        
        Args:
            callback (function): Function to call for each received message. 
                                Should accept message_data dict as parameter.
            allowed_updates (list): Types of updates to receive (e.g., ['message'])
        
        Example:
            def handle_message(msg_data):
                print(f"Received: {msg_data['content']} from {msg_data['sender_name']}")
            
            bot.receive_messages(callback=handle_message)
        """
        try:
            offset = 0
            logger.info("Starting message receiver loop...")
            
            while True:
                updates = self.get_updates(offset=offset, timeout=30, allowed_updates=allowed_updates)
                
                if updates:
                    for update in updates:
                        try:
                            message_data = self.extract_message_data(update)
                            
                            if message_data:
                                logger.info(f"Message from {message_data['sender_name']} ({message_data['type']}): {message_data.get('content', message_data.get('file_name', 'N/A'))}")
                                
                                # Call user's callback if provided
                                if callback:
                                    callback(message_data)
                            
                            # Update offset to avoid getting same message again
                            offset = update['update_id'] + 1
                            
                        except Exception as e:
                            logger.error(f"Error processing update {update.get('update_id')}: {e}")
                            continue
                    
        except KeyboardInterrupt:
            logger.info("Message receiver stopped by user")
        except Exception as e:
            logger.error(f"Error in receive_messages loop: {e}")
    
    def receive_message_once(self) -> Optional[Dict[str, Any]]:
        """
        Receive a single message (non-blocking, returns immediately if no message)
        
        Returns:
            dict: Message data if available, None otherwise
        """
        try:
            updates = self.get_updates(offset=0, timeout=0)  # timeout=0 makes it non-blocking
            
            if updates:
                for update in updates:
                    message_data = self.extract_message_data(update)
                    if message_data:
                        logger.info(f"Received message from {message_data['sender_name']}")
                        return message_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error receiving single message: {e}")
            return None

    def telegram_handler(self, tool_request):
        """
        Handle incoming Telegram updates (webhook or polling)
        
        Args:
            tool_request (dict): Incoming update from Telegram
        
        Returns:
            dict: Processed update info
        """
        try:
            chat_id = os.getenv('TELEGRAM_CHAT_ID', '@your_username')
            action = tool_request.get('action', 'get_update')
            if action == 'send_message':
                message = tool_request['message']
                response = self.send_message(
                    chat_id=chat_id,
                    text=message
                )
                return response
            elif action == 'send_photo':
                photo = tool_request['photo']
                caption = tool_request.get('caption', '')
                response = self.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption
                )
                return response
            elif action == 'send_document':
                document = tool_request['document']
                caption = tool_request.get('caption', '')
                response = self.send_document(
                    chat_id=chat_id,
                    document=document,
                    caption=caption
                )
                return response
            elif action == 'send_video':
                video = tool_request['video']
                caption = tool_request.get('caption', '')
                response = self.send_video(
                    chat_id=chat_id,
                    video=video,
                    caption=caption
                )
                return response 
            elif action == 'send_audio':
                audio = tool_request['audio']
                caption = tool_request.get('caption', '')
                response = self.send_audio(
                    chat_id=chat_id,
                    audio=audio,
                    caption=caption
                )
                return response
            elif action == 'get_update':
                # Fetch incoming messages from users
                updates = self.get_updates()
                if updates:
                    messages = []
                    for update in updates:
                        msg_data = self.extract_message_data(update)
                        if msg_data:
                            messages.append(msg_data)
                    return {"status": "success", "messages": messages, "count": len(messages)}
                else:
                    return {"status": "success", "messages": [], "count": 0}
        except Exception as e:
            logger.error(f"Error handling update: {e}")
            return {}

# Example usage and legacy functions
if __name__ == "__main__":
    try:
        # Initialize Telegram bot
        bot = TelegramBot()
        
        # Get chat ID from environment or use a default
        chat_id = os.getenv('TELEGRAM_CHAT_ID', '@your_username')  # Replace with your chat ID or username
        
        # Example 1: Send text message
        message_text = "Hello from Python Telegram Bot!"
        bot.send_message(chat_id, message_text)
        bot.receive_messages()  # Start receiving messages (blocking call)
        # Example 2: Send photo with caption
        # photo_url = "https://m.media-amazon.com/images/I/81QoDTzKadL._SX679_.jpg"
        # photo_caption = "Check out this amazing product!"
        # bot.send_photo(chat_id, photo_url, photo_caption)
        
        # Example 3: Receive a single message (non-blocking)
        # message = bot.receive_message_once()
        # if message:
        #     print(f"Received {message['type']} from {message['sender_name']}: {message.get('content', 'media')}")
        
        # Example 4: Continuously receive messages with callback
        def handle_user_message(msg_data):
            """Callback function to handle incoming messages"""
            sender = msg_data['sender_name']
            msg_type = msg_data['type']
            content = msg_data.get('content', msg_data.get('file_name', 'media'))
            
            print(f"\n📱 Message from {sender} ({msg_type}):")
            print(f"   Content: {content}")
            print(f"   Chat ID: {msg_data['chat_id']}")
            
            # Example: Send auto-reply
            # if msg_type == 'text':
            #     reply = f"Echo: {content}"
            #     bot.send_message(msg_data['chat_id'], reply)
        
        # Start receiving messages
        print("Starting bot... (press Ctrl+C to stop)")
        print("Waiting for messages from Telegram users...\n")
        bot.receive_messages(callback=handle_user_message, allowed_updates=['message'])
        
        # Uncomment to get bot info instead
        # bot_info = bot.get_bot_info()
        # if bot_info:
        #     print(f"Bot Info: @{bot_info['username']} - {bot_info['first_name']}")
            
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nTo set up your bot:")
        print("1. Create a bot with @BotFather on Telegram")
        print("2. Get your bot token")
        print("3. Set TELEGRAM_BOT_TOKEN environment variable")
        print("4. Set TELEGRAM_CHAT_ID environment variable (your chat ID or @username)")
    except Exception as e:
        print(f"Unexpected error: {e}")