"""
Simple Image Scraper for Strands Agent
Uses Brave Search API to find and download images
"""

from dotenv import load_dotenv
import os
import logging
import requests
import shutil
from pathlib import Path

load_dotenv()



def search_and_download_images(query, num_images=5, save_folder="images"):
    """
    Simple image search and download function for Strands Agent.
    
    Args:
        query (str): What to search for
        num_images (int): Number of images to download (default: 5)
        save_folder (str): Folder to save images (default: "images")
    
    """
    try:
        # Create save folder
        for file in os.listdir(save_folder):
            file_path = os.path.join(save_folder, file)
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)

        save_path = Path(save_folder) / query.replace(" ", "_")
        save_path.mkdir(parents=True, exist_ok=True)
        
        # Search with Brave API
        api_url = "https://api.search.brave.com/res/v1/images/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": os.getenv("brave_api_key")
        }
        
        response = requests.get(api_url, params={"q": query, "count": num_images}, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        if 'results' not in data or not data['results']:
            return {
                'success': False,
                'message': f'No images found for "{query}"',
                'images': []
            }
        
      

        downloaded = []
        for idx, result in enumerate(data['results'][:num_images]):
            try:
                if 'properties' not in result or 'url' not in result['properties']:
                    continue
                
                image_url = result['properties']['url']
                title = result.get('title', f'image_{idx}')
                
                # Download with better timeout and headers
                img_response = requests.get(
                    image_url, 
                    timeout=10,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                )
                img_response.raise_for_status()
                
                # Get extension - handle query parameters in URL
                url_path = image_url.split('?')[0]  # Remove query params
                ext = Path(url_path).suffix
                
                # Fallback to content-type if no extension found
                if not ext:
                    content_type = img_response.headers.get('content-type', 'image/jpeg')
                    ext_map = {
                        'image/jpeg': '.jpg',
                        'image/png': '.png',
                        'image/webp': '.webp',
                        'image/gif': '.gif'
                    }
                    ext = ext_map.get(content_type.split(';')[0], '.jpg')
                
                filename = f"{idx}_{title[:40].replace(' ', '_').replace('/', '_')}{ext}"
                filepath = save_path / filename
                
                with open(filepath, 'wb') as f:
                    f.write(img_response.content)
                
                downloaded.append({
                    'filename': filename,
                    'path': str(filepath),
                    'url': image_url,
                    'title': title
                })
                
            except requests.exceptions.RequestException as e:
                print(f"Failed to download image {idx} (URL: {image_url[:60]}...): {e}")
                continue
            except Exception as e:
                print(f"Error processing image {idx}: {e}")
                continue
        
        return {
            'success': True,
            'message': f'Downloaded {len(downloaded)} images for "{query}"',
            'images': downloaded,
            'folder': str(save_path)
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'images': []
        }

def search_videos(query, num_videos=5):
    """
    Search for videos using Brave Search API.
    
    Args:
        query (str): What to search for
        num_videos (int): Number of videos to return (default: 5)
    
    Returns:
        dict: {
            'success': bool,
            'message': str,
            'videos': list of {
                'title': str,
                'url': str,
                'source': str,
                'description': str,
                'thumbnail': str
            }
        }
    """
    try:
        # Search with Brave API
        api_url = "https://api.search.brave.com/res/v1/videos/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": os.getenv("brave_api_key")
        }
        
        response = requests.get(api_url, params={"q": query, "count": num_videos}, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        if 'results' not in data or not data['results']:
            return {
                'success': False,
                'message': f'No videos found for "{query}"',
                'videos': []
            }
        
        # Extract video links
        videos = []
        for idx, result in enumerate(data['results'][:num_videos]):
            try:
                title = result.get('title', f'video_{idx}')
                url = result.get('url', '')
                source = result.get('source', 'Unknown')
                description = result.get('description', '')
                
                # Get thumbnail if available
                thumbnail = ''
                if 'properties' in result and 'thumbnail' in result['properties']:
                    thumbnail = result['properties']['thumbnail'].get('src', '')
                
                if url:
                    videos.append({
                        'title': title,
                        'url': url,
                        'source': source,
                        'description': description,
                        'thumbnail': thumbnail
                    })
                    
            except Exception as e:
                print(f"Failed to extract video {idx}: {e}")
                continue
        
        return {
            'success': True,
            'message': f'Found {len(videos)} videos for "{query}"',
            'videos': videos
        }
        
    except Exception as e:
        print(f"Error searching videos: {e}")
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'videos': []
        }

# Test
if __name__ == "__main__":
    # Test image search
    result = search_and_download_images("oppo find x9 ultra orange colour", num_images=5)
  
    print(result["images"])
    
    # Test video search
    # print("\n--- Video Search ---")
    # video_result = search_videos("salhaudding ayyubi episode 87 season", num_videos=5)
    # print(f"✓ Success: {video_result['success']}")
    # print(f"✓ Message: {video_result['message']}")
    # print(f"✓ Found: {len(video_result['videos'])} videos")
    # if video_result['videos']:
    #     for vid in video_result['videos']:
    #         print(f"  - {vid['title']}: {vid['url']}")