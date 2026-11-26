import requests
import json
import os
from typing import Dict, Optional

class WeatherAPI:
    def __init__(self, api_key: str):
        self.api_key = os.environ('WEATHER_KEY')
        self.base_url = "https://api.weatherapi.com/v1"
        
    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """Make HTTP request to WeatherAPI with error handling"""
        params['key'] = self.api_key
        
        try:
            response = requests.get(f"{self.base_url}/{endpoint}", params=params, timeout=8)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            return None

    def get_current_weather(self, location: str) -> Optional[Dict]:

        data = self._make_request(
            "current.json",
            {
                "q": location,
                "lang": "pt",
                "aqi": "no"
            }
        )

        if not data:
            return None

        current = data["current"]
        condition = current["condition"]

        icon = condition.get("icon", "")

        if icon.startswith("//"):
            icon = "https:" + icon

        return {
            "location": data["location"]["name"],
            "temperature_c": current["temp_c"],
            "condition": condition["text"],
            "icon": icon,
            "humidity": current["humidity"],
            "wind_kph": current["wind_kph"],
            "is_day": current["is_day"]
        }


weather = WeatherAPI(key)