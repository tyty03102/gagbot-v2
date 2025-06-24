import logging
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)

class APIFallback:
    def __init__(self):
        self.gear_seeds_url = "https://growagardenstock.com/api/stock?type=gear-seeds"
        self.egg_url = "https://growagardenstock.com/api/stock?type=egg"
        self.honey_url = "https://growagardenstock.com/api/special-stock?type=honey"
        self.logger = logging.getLogger(__name__)
        self.last_switch_time = None
        self.is_using_fallback = False
        self.switch_duration = timedelta(minutes=30)

    async def fetch_stock_data(self) -> Dict[str, List[str]]:
        """
        Fetch stock data from the API endpoints.
        Returns a dictionary with keys: seeds, gear, egg, bee
        Note: Weather data is not available in the fallback API
        """
        try:
            self.logger.info("Fetching data from fallback API endpoints...")
            async with aiohttp.ClientSession() as session:
                # Fetch gear and seeds
                try:
                    async with session.get(self.gear_seeds_url, timeout=10) as response:
                        response.raise_for_status()
                        gear_seeds_data = await response.json()
                        self.logger.info(f"Successfully fetched gear/seeds data: {len(gear_seeds_data.get('gear', []))} gear, {len(gear_seeds_data.get('seeds', []))} seeds")
                except Exception as e:
                    self.logger.error(f"Failed to fetch gear/seeds: {e}")
                    gear_seeds_data = {"gear": [], "seeds": []}
                
                # Fetch eggs
                try:
                    async with session.get(self.egg_url, timeout=10) as response:
                        response.raise_for_status()
                        egg_data = await response.json()
                        self.logger.info(f"Successfully fetched egg data: {len(egg_data.get('egg', []))} eggs")
                except Exception as e:
                    self.logger.error(f"Failed to fetch eggs: {e}")
                    egg_data = {"egg": []}

                # Fetch honey event items
                try:
                    async with session.get(self.honey_url, timeout=10) as response:
                        response.raise_for_status()
                        honey_data = await response.json()
                        self.logger.info(f"Successfully fetched honey data: {len(honey_data.get('honey', []))} items")
                except Exception as e:
                    self.logger.error(f"Failed to fetch honey: {e}")
                    honey_data = {"honey": []}

                # Transform the data
                transformed_data = self._transform_api_data({
                    "gear_seeds": gear_seeds_data,
                    "egg": egg_data,
                    "honey": honey_data
                })

                self.logger.info(f"Fallback API returned: {sum(len(v) for v in transformed_data.values())} total items")
                return transformed_data

        except Exception as e:
            self.logger.error(f"API fallback failed: {str(e)}")
            return {"seeds": [], "gears": [], "eggs": [], "event_shop": []}

    def _transform_api_data(self, data: Dict) -> Dict[str, List[str]]:
        """
        Transform API data to match the expected format.
        """
        try:
            # Extract data from each response
            gear_seeds = data.get("gear_seeds", {})
            egg_data = data.get("egg", {})
            honey_data = data.get("honey", {})
            
            # Create transformed data structure
            transformed_data = {
                "seeds": [],
                "gears": [],
                "eggs": [],
                "event_shop": [],
                "weather": []
            }
            
            # Process gear and seeds
            if "gear" in gear_seeds:
                transformed_data["gears"] = gear_seeds["gear"]
            if "seeds" in gear_seeds:
                transformed_data["seeds"] = gear_seeds["seeds"]
                
            # Process eggs
            if "egg" in egg_data:
                transformed_data["eggs"] = egg_data["egg"]
                
            # Process honey event items
            if "honey" in honey_data:
                transformed_data["event_shop"] = honey_data["honey"]
            
            return transformed_data
            
        except Exception as e:
            self.logger.error(f"Error transforming API data: {str(e)}")
            return {"seeds": [], "gears": [], "eggs": [], "event_shop": [], "weather": []}

    def _get_weather_emoji(self, weather_type: str) -> str:
        """Get the appropriate emoji for a weather type."""
        weather_emojis = {
            "Rain": "🌧️",
            "Thunderstorm": "⛈️",
            "Sun God": "🌤️",
            "Frost": "🌨️"
        }
        return weather_emojis.get(weather_type, "❓")

    def should_use_fallback(self) -> bool:
        """
        Determines if we should use the fallback API based on the last switch time.
        """
        if not self.is_using_fallback:
            return False
        
        if not self.last_switch_time:
            return False

        time_since_switch = datetime.now() - self.last_switch_time
        return time_since_switch < self.switch_duration

    def switch_to_fallback(self):
        """
        Switches to using the fallback API.
        """
        self.is_using_fallback = True
        self.last_switch_time = datetime.now()
        logging.info("Switched to fallback API. Will check main website again in 30 minutes.")

    def reset_fallback(self):
        """
        Resets the fallback state.
        """
        self.is_using_fallback = False
        self.last_switch_time = None
        logging.info("Switched back to main website scraping.")

    async def check_api_health(self) -> Dict[str, bool]:
        """
        Check the health of all API endpoints.
        Returns a dictionary with endpoint status.
        Note: Weather endpoint is not available in fallback API
        """
        health_status = {}
        
        try:
            async with aiohttp.ClientSession() as session:
                endpoints = {
                    "gear_seeds": self.gear_seeds_url,
                    "egg": self.egg_url,
                    "honey": self.honey_url
                }
                
                for name, url in endpoints.items():
                    try:
                        async with session.get(url, timeout=5) as response:
                            health_status[name] = response.status == 200
                    except Exception:
                        health_status[name] = False
                        
        except Exception as e:
            self.logger.error(f"Error checking API health: {e}")
            health_status = {name: False for name in endpoints.keys()}
            
        return health_status

# Create a global instance
api_fallback = APIFallback() 