import requests
import os
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()


def get_travel_time_with_traffic(origin: str, destination: str) -> dict:
    """
    Get travel time and traffic information between two locations.
    
    Args:
        origin (str): Starting location
        destination (str): Ending location
    
    Returns:
        dict: Contains distance, durations, and traffic impact
    """
    API_KEY = os.environ.get("GOOGLE_API_KEY")
    if not API_KEY:
        raise ValueError("GOOGLE_API_KEY environment variable not set")
    
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={quote(origin)}&destinations={quote(destination)}&departure_time=now&key={API_KEY}"
    
    response = requests.get(url).json()
    
    if response.get('status') != 'OK':
        raise ValueError(f"API Error: {response.get('error_message', response.get('status'))}")
    
    element = response['rows'][0]['elements'][0]
    
    standard_seconds = element['duration']['value']
    traffic_seconds = element.get('duration_in_traffic', {}).get('value', standard_seconds)
    delay_seconds = traffic_seconds - standard_seconds
    
    return {
        'distance': element['distance']['text'],
        'standard_duration': element['duration']['text'],
        'duration_in_traffic': element.get('duration_in_traffic', {}).get('text', element['duration']['text']),
        'traffic_delay_seconds': delay_seconds,
        'traffic_impact_percent': round((delay_seconds / standard_seconds * 100), 2) if standard_seconds > 0 else 0
    }


if __name__ == "__main__":
    origin = "pisoli Pune"
    destination = "handewadi Pune"
    
    travel_info = get_travel_time_with_traffic(origin, destination)
    print(travel_info)