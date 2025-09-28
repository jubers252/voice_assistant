import requests
import json
from dotenv import load_dotenv  
import os

load_dotenv()  # Load environment variables from .env file


def send_whatsapp_message(message_text=None, image_url=None, image_caption=None):
    """Simple function to send WhatsApp message
    
    Args:
        message_text (str): Custom text message to send
        template_name (str): Template name to send (default: hello_world)
        image_url (str): URL of image to send
        image_caption (str): Caption for the image
    """
    
    # Configuration
    phone_number_id = os.environ.get("PHONE_NUMBER_ID")
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    to_number = os.environ.get("TO_NUMBER")
    
    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # Choose payload based on message type
    if image_url:
        # Send image message
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "image",
            "image": {
                "link": image_url
            }
        }
        # Add caption if provided
        if image_caption:
            payload["image"]["caption"] = image_caption
            
    elif message_text:
        # Send custom text message
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {
                "body": message_text
            }
        }
 
 
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        return response.json() if response.content else {"status_code": response.status_code}
        
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}

# Test the function
if __name__ == "__main__":
    print("WhatsApp Message Sender")
    print("=" * 25)
    message_text = "Hello, This is from voice assistant!"
    image_url = "https://m.media-amazon.com/images/I/61lZTc-n+2L._SL1500_.jpg"
    image_caption = "This is a test image"
    send_whatsapp_message(image_url=image_url, image_caption=image_caption)