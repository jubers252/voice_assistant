"""
WeatherAPI.com connector - Minimal version for voice assistant.

Features:
- Current weather
- Weather forecasts (up to 14 days)  
- Timezone information

Setup:
1. Sign up at https://www.weatherapi.com/signup.aspx
2. Get your API key from https://www.weatherapi.com/login.aspx
3. Set environment variable: WEATHER_API_KEY=your_api_key_here

Pricing:
- Free: 1 million calls/month
"""

import os
import requests
from typing import Dict
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


class WeatherAPIConnector:
    """Minimal WeatherAPI.com connector for voice assistant."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("WEATHER_API_KEY")
        if not self.api_key:
            raise ValueError("WEATHER_API_KEY environment variable is required")
            
        self.base_url = "http://api.weatherapi.com/v1"
        self.headers = {"User-Agent": "WeatherConnector/1.0"}
    
    def get_current_weather(self, location: str, aqi: bool = False) -> Dict:
        """
        Get current weather for a location.
        
        Parameters:
        -----------
        location : str
            Location query (city name, coordinates, IP, etc.)
        aqi : bool
            Include air quality data
            
        Returns:
        --------
        Dict with current weather data
        """
        params = {
            "key": self.api_key,
            "q": location,
            "aqi": "yes" if aqi else "no"
        }
        
        return self._make_request("/current.json", params)
    
    def get_forecast(self, location: str, days: int = 3, aqi: bool = False, 
                    alerts: bool = False) -> Dict:
        """
        Get weather forecast for a location.
        
        Parameters:
        -----------
        location : str
            Location query
        days : int
            Number of forecast days (1-14)
        aqi : bool
            Include air quality data
        alerts : bool
            Include weather alerts
            
        Returns:
        --------
        Dict with forecast data
        """
        params = {
            "key": self.api_key,
            "q": location,
            "days": min(days, 14),
            "aqi": "yes" if aqi else "no",
            "alerts": "yes" if alerts else "no"
        }
        
        return self._make_request("/forecast.json", params)
    
    def get_timezone(self, location: str) -> Dict:
        """
        Get timezone information for a location.
        
        Parameters:
        -----------
        location : str
            Location query
            
        Returns:
        --------
        Dict with timezone data
        """
        params = {
            "key": self.api_key,
            "q": location
        }
        result = self._make_request("/timezone.json", params)
        current_time = f"Timezone info for {result['location']['name']}: {result['location']['localtime']}"
        return current_time

    def get_simple_weather(self, location: str = "Pune") -> str:
        """
        Get a simple weather summary for voice assistant.
        
        Parameters:
        -----------
        location : str
            Location name (defaults to Pune)
            
        Returns:
        --------
        str: Simple weather description
        """
        try:
            data = self.get_current_weather(location)
            
            if "error" in data:
                return f"Sorry, I couldn't get weather for {location}"
            
            current = data["current"]
            location_name = data["location"]["name"]
            
            temp_c = current["temp_c"]
            condition = current["condition"]["text"]
            feels_like = current["feelslike_c"]
            humidity = current["humidity"]
            
            return (f"Current weather in {location_name}: {temp_c}°C, {condition}. "
                   f"Feels like {feels_like}°C. Humidity {humidity}%.")
            
        except Exception as e:
            return f"Weather service temporarily unavailable: {str(e)}"
    
    def get_weather_forecast_summary(self, location: str = "Pune", days: int = 3) -> str:
        """
        Get a simple forecast summary for voice assistant.
        
        Parameters:
        -----------
        location : str
            Location name
        days : int
            Number of days to forecast
            
        Returns:
        --------
        str: Simple forecast description
        """
        try:
            data = self.get_forecast(location, days=days)
            
            if "error" in data:
                return f"Sorry, I couldn't get forecast for {location}"
            
            location_name = data["location"]["name"]
            forecast_days = data["forecast"]["forecastday"]
            
            summary = f"Weather forecast for {location_name}: "
            
            for day_data in forecast_days[:days]:
                date = day_data["date"]
                day_info = day_data["day"]
                
                max_temp = day_info["maxtemp_c"]
                min_temp = day_info["mintemp_c"]
                condition = day_info["condition"]["text"]
                
                # Format date nicely
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                if date_obj.date() == datetime.now().date():
                    day_name = "Today"
                elif date_obj.date() == (datetime.now() + timedelta(days=1)).date():
                    day_name = "Tomorrow"
                else:
                    day_name = date_obj.strftime("%A")
                
                summary += f"{day_name}: {condition}, high {max_temp}°C, low {min_temp}°C. "
            
            return summary.strip()
            
        except Exception as e:
            return f"Weather forecast service temporarily unavailable: {str(e)}"
    
    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """Make HTTP request to WeatherAPI."""
        url = self.base_url + endpoint
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            return {"error": f"Request failed: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}


def handle_tool_requests(tool_request: Dict) -> str:
    """Test the weather API connection."""
    try:
        weather = WeatherAPIConnector()
        
        print("=== Testing WeatherAPI Connection ===")
        action = tool_request.get("action")
        location = tool_request.get("location", "Pune")
        if action == "get_current_weather":
            result = weather.get_simple_weather(location)
            return result
        elif action == "get_forecast":
            result = weather.get_weather_forecast_summary(location, days=3)
            return result
        elif action == "get_timezone":
            result = weather.get_timezone(location)
            return result
        else:
            return {"error": "Unknown action"}

    except Exception as e:
        print(f"Weather API Test Failed: {e}")
        return False


if __name__ == "__main__":
    weather = WeatherAPIConnector()
    location = "Pune"
    result = weather.get_timezone(location)
    print(result)
