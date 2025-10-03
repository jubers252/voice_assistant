from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_whatsapp_number = os.getenv('TWILIO_WHATSAPP_NUMBER')

def send_whatsapp_message(to_number, message):
    """
    Send a WhatsApp message using Twilio API
    
    Args:
        to_number (str): Recipient's phone number in format 'whatsapp:+1234567890'
        message (str): Message content to send
    
    Returns:
        str: Message SID if successful, None if failed
    """
    try:
     
        # Initialize Twilio client
        client = Client(account_sid, auth_token)
        
        # Send message
        message = client.messages.create(
            body=message,
            from_=f"whatsapp:{twilio_whatsapp_number}",
            to=to_number
        )
        
        print(f"Message sent successfully! SID: {message.sid}")
        return message.sid
        
    except Exception as e:
        print(f"Error sending message: {str(e)}")
        return None


def send_whatsapp_image(to_number, image_url, caption=""):
    """
    Send a WhatsApp image message using Twilio API
    
    Args:
        to_number (str): Recipient's phone number in format 'whatsapp:+1234567890'
        image_url (str): Public URL of the image (must be accessible via HTTPS)
        caption (str): Optional caption for the image
    
    Returns:
        str: Message SID if successful, None if failed
    """
    try:
        # Your Twilio credentials (store these as environment variables)
       

        # Initialize Twilio client
        client = Client(account_sid, auth_token)
        
        # Send image message
        message = client.messages.create(
            body=caption,
            media_url=[image_url],
            from_=f"whatsapp:{twilio_whatsapp_number}",
            to=to_number
        )
        
        print(f"Image sent successfully! SID: {message.sid}")
        return message.sid
        
    except Exception as e:
        print(f"Error sending image: {str(e)}")
        return None


def send_whatsapp_media(to_number, media_url, message_text="", media_type="image"):
    """
    Send WhatsApp media (image, video, audio, document) using Twilio API
    
    Args:
        to_number (str): Recipient's phone number in format 'whatsapp:+1234567890'
        media_url (str): Public URL of the media file
        message_text (str): Optional text message to accompany the media
        media_type (str): Type of media ('image', 'video', 'audio', 'document')
    
    Returns:
        str: Message SID if successful, None if failed
    """
    try:
       
        # Initialize Twilio client
        client = Client(account_sid, auth_token)
        
        # Send media message
        message = client.messages.create(
            body=message_text,
            media_url=[media_url],
            from_=f"whatsapp:{twilio_whatsapp_number}",
            to=to_number
        )
        
        print(f"{media_type.capitalize()} sent successfully! SID: {message.sid}")
        return message.sid
        
    except Exception as e:
        print(f"Error sending {media_type}: {str(e)}")
        return None

# Example usage
if __name__ == "__main__":
    recipient = f"whatsapp:{os.getenv('TO_NUMBER')}"
    
    # Send text message
    msg = 'Hello! checkout the product link- https://www.amazon.in/VIVO-Fold5-Titanium-Additional-Exchange/dp/B0FGCRRG7M/ref=pd_ci_mcx_mh_mcx_views_0_image?pd_rd_w=B9FKJ&content-ida=amzn1.sym.04d3fdac-1b15-414f-91d2-0c9aaaf137d6%3Aamzn1.symc.30e3dbb4-8dd8-4bad-b7a1-a45bcdbc49b8&pf_rd_p=04d3fdac-1b15-414f-91d2-0c9aaaf137d6&pf_rd_r=JDWFHZZYF9G1JP1WG96S&pd_rd_wg=w7UcC&pd_rd_r=a012fc3c-1a50-4075-b984-2ca976b15f09&pd_rd_i=B0FGCRRG7M'
    send_whatsapp_message(recipient, msg)
    
    # Send image with caption
    image_url = 'https://m.media-amazon.com/images/I/81QoDTzKadL._SX679_.jpg'
    caption = 'Check out this product!'
    send_whatsapp_image(recipient, image_url, caption)
    
    # Send media (video, audio, document)
    # video_url = 'https://example.com/video.mp4'
    # send_whatsapp_media(recipient, video_url, "Here's a video!", "video")