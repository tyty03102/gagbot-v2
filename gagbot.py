import discord
import asyncio
import requests
import logging
from datetime import datetime
import time
import json
from discord import app_commands
from config import TOKEN, STOCK_CHANNEL_ID, ROLE_CHANNEL_ID, EMOJI_ROLE_MAP, ALERT_ROLE_ID, LOGS_CHANNEL_ID, NEWS_CHANNEL_ID, TEST_CHANNEL_ID, UPDATES_CHANNEL_ID, HARVEST_CHANNEL_ID, WEATHER_CHANNEL_ID, WELCOME_CHANNEL_ID, ABOUT_CHANNEL_ID
import pytz
from scraper import fetch_stock_data
from calculator import calculator  # Add this import
from api import api_fallback  # Add this import
from invite import invite_challenge  # Add invite challenge import
import os

# Configure all required intents
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
intents.members = True  # Enable members intent for fetch_member
intents.reactions = True  # Enable reactions intent

# Set Phoenix timezone
PHOENIX_TZ = pytz.timezone('America/Phoenix')

# Cache file path
CACHE_FILE = 'bot_cache.json'

def load_cache():
    """Load cached data from file."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Error loading cache: {e}")
    return {
        "last_data": None,
        "repeated_data_count": 0,
        "is_website_broken": False,
        "last_weather_alert": None,
        "fallback_switch_time": None
    }

def save_cache(data):
    """Save data to cache file."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Error saving cache: {e}")

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        
        # Load cached data
        cache = load_cache()
        self.last_data = cache.get("last_data")
        self.repeated_data_count = cache.get("repeated_data_count", 0)
        self.is_website_broken = cache.get("is_website_broken", False)
        self.last_weather_alert = cache.get("last_weather_alert")
        self.fallback_switch_time = cache.get("fallback_switch_time")
        self.logs_channel_id = LOGS_CHANNEL_ID
        self.just_switched_to_fallback = False  # Track if we just switched to fallback
        self.just_restored_main_api = False  # Track if we just restored main API
        logging.info("Bot initialized with cached data")
        
        # Sync the fallback state to ensure consistency
        self.sync_fallback_state()

    def save_state(self):
        """Save current state to cache."""
        cache_data = {
            "last_data": self.last_data,
            "repeated_data_count": self.repeated_data_count,
            "is_website_broken": self.is_website_broken,
            "last_weather_alert": self.last_weather_alert,
            "fallback_switch_time": self.fallback_switch_time
        }
        save_cache(cache_data)
        logging.info("Bot state saved to cache")

    def sync_fallback_state(self):
        """Ensure the API fallback state is in sync with the bot's internal state."""
        if self.is_website_broken and not api_fallback.is_using_fallback:
            # Bot thinks website is broken but API fallback doesn't
            api_fallback.switch_to_fallback()
            logging.info("Synced API fallback state - switched to fallback")
        elif not self.is_website_broken and api_fallback.is_using_fallback:
            # Bot thinks website is working but API fallback is still active
            api_fallback.reset_fallback()
            logging.info("Synced API fallback state - reset to main")

    async def monitor_main_website(self):
        """Background task to monitor main website health every 15 minutes when in fallback mode."""
        while True:
            try:
                if self.is_website_broken:
                    # Wait at least 15 minutes before checking main website health
                    # This gives the main website time to actually update its data
                    logging.info("Monitoring main website health (checking every 15 minutes)...")
                    
                    # Check if we've been in fallback mode for at least 15 minutes
                    if self.fallback_switch_time:
                        time_since_switch = int(time.time()) - self.fallback_switch_time
                        if time_since_switch < 900:  # 15 minutes = 900 seconds
                            wait_time = 900 - time_since_switch
                            logging.info(f"Waiting {wait_time} more seconds before checking main website health (minimum 15 minutes in fallback)")
                            await asyncio.sleep(wait_time)
                    
                    main_api_working = await check_main_website_health()
                    
                    if main_api_working:
                        logging.info("Main website health check passed - switching back to main API")
                        self.is_website_broken = False
                        self.fallback_switch_time = None
                        self.just_restored_main_api = True
                        channel = self.get_channel(STOCK_CHANNEL_ID)
                        if channel:
                            alert_embed = discord.Embed(
                                title="✅ API Restored",
                                description="The main API is back online. The bot will now use the main data source.",
                                color=discord.Color.green()
                            )
                            await channel.send(alert_embed)
                            logging.info("Website back online alert sent")
                            await self.send_log("Website back online alert sent", "INFO")
                            api_fallback.reset_fallback()
                            self.save_state()
                    else:
                        logging.info("Main website health check failed - continuing with fallback API")
                
                # Wait 15 minutes before next check (instead of 5 minutes)
                await asyncio.sleep(900)
                
            except Exception as e:
                logging.error(f"Error in main website monitoring: {e}")
                await asyncio.sleep(900)  # Wait 15 minutes before retrying

    async def setup_hook(self):
        self.tree.add_command(calc_group)
        await self.tree.sync()

    async def post_stock(self):
        try:
            stock_data = await fetch_all_stock()
            current_time = int(time.time())
            stock_data['timestamp'] = current_time

            if self.last_data:
                last_seeds = self.last_data.get("seeds", [])
                current_seeds = stock_data.get("seeds", [])
                if json.dumps(last_seeds, sort_keys=True) == json.dumps(current_seeds, sort_keys=True):
                    self.repeated_data_count += 1
                    logging.info(f"Detected repeated data {self.repeated_data_count} times")
                    
                    # If we have repeated data 3 or 4 times, test main website health
                    if 3 <= self.repeated_data_count < 5 and not self.is_website_broken:
                        # Test main website health before switching to fallback
                        logging.info("Testing main website health due to repeated data...")
                        main_api_working = await check_main_website_health()
                        
                        if not main_api_working:
                            # Website is actually down, switch to fallback
                            channel = self.get_channel(STOCK_CHANNEL_ID)
                            if channel:
                                self.is_website_broken = True
                                self.fallback_switch_time = int(time.time())
                                self.just_switched_to_fallback = True
                                logging.warning(f"Main website health check failed after {self.repeated_data_count} repeated data cycles - switching to fallback API")
                                
                                alert_embed = discord.Embed(
                                    title="⚠️ API Alert",
                                    description="The main API appears to be unavailable. The bot will temporarily switch to the backup API and check the main API every 15 minutes until it's back up. Results may be slightly delayed.",
                                    color=discord.Color.orange()
                                )
                                await channel.send(embed=alert_embed)
                                logging.warning("Website unavailable alert sent - switching to API fallback")
                                await self.send_log("Website unavailable alert sent - switching to API fallback", "WARNING")
                                
                                api_fallback.switch_to_fallback()
                                self.save_state()
                                
                                return "switched_to_fallback"
                            else:
                                logging.error("Could not find stock channel to send API alert. Fallback not initiated.")
                        else:
                            # Website is working, but data is stale. Don't reset counter.
                            # Allow it to reach 5 to force a fallback.
                            logging.info("Main website health check passed, but data is still repeated. Awaiting more cycles before fallback.")

                    elif self.repeated_data_count >= 5 and not self.is_website_broken:
                        # If we get to 5 repeated data cycles, force switch to fallback regardless
                        channel = self.get_channel(STOCK_CHANNEL_ID)
                        if channel:
                            self.is_website_broken = True
                            self.fallback_switch_time = int(time.time())
                            self.just_switched_to_fallback = True
                            logging.warning(f"Detected repeated data {self.repeated_data_count} times - forcing switch to fallback API")
                            
                            alert_embed = discord.Embed(
                                title="⚠️ API Alert",
                                description="The main API appears to be unavailable. The bot will temporarily switch to the backup API and check the main API every 15 minutes until it's back up. Results may be slightly delayed.",
                                color=discord.Color.orange()
                            )
                            await channel.send(embed=alert_embed)
                            logging.warning("Website unavailable alert sent - switching to API fallback")
                            await self.send_log("Website unavailable alert sent - switching to API fallback", "WARNING")
                            
                            api_fallback.switch_to_fallback()
                            self.save_state()
                            
                            return "switched_to_fallback"
                        else:
                            logging.error("Could not find stock channel to send API alert. Fallback not initiated.")
                    
                    return False
                else:
                    self.repeated_data_count = 0
                    logging.info("Got new seed data - resetting repeated data counter")
                    # The main website monitoring task handles API restoration automatically
                    # No need to check here since we have a dedicated background task
            if stock_data:
                channel = self.get_channel(STOCK_CHANNEL_ID)
                if channel is None:
                    error_msg = "Stock channel not found"
                    logging.error(error_msg)
                    await self.send_log(error_msg, "ERROR")
                    return False
                embed = format_embed(stock_data)
                await channel.send(embed=embed)
                self.last_data = stock_data.copy()
                self.save_state()
                # Then send pings with item summaries
                mentions = []

                # Role IDs (for pings)
                mythical_seed_role_id = EMOJI_ROLE_MAP.get("🦄")
                legendary_seed_role_id = EMOJI_ROLE_MAP.get("🌟")
                rare_seed_role_id = EMOJI_ROLE_MAP.get("🔥")
                gear_role_id = EMOJI_ROLE_MAP.get("🧰")
                egg_role_id = EMOJI_ROLE_MAP.get("🥚")
                weather_role_id = EMOJI_ROLE_MAP.get("🌧️")

                # Keywords to watch for (lowercase for matching)
                mythical_seed_keywords = {"pineapple", "kiwi", "pear", "bell"}
                legendary_seed_keywords = {"watermelon", "green apple", "avocado", "banana"}
                gear_keywords = {"lightning", "master", "godly", "friendship", "mirror"}
                egg_keywords = {"bug", "mythical", "paradise"}

                mythical_seed_matches = [s for s in stock_data.get("seeds", []) if any(k in s.lower() for k in mythical_seed_keywords)]
                legendary_seed_matches = [s for s in stock_data.get("seeds", []) if any(k in s.lower() for k in legendary_seed_keywords)]
                gear_matches = [g for g in stock_data.get("gear", []) if any(k in g.lower() for k in gear_keywords)]
                egg_matches = [e for e in stock_data.get("egg", []) if any(k in e.lower() for k in egg_keywords)]

                # Remove duplicates while preserving order
                mythical_seed_matches = list(dict.fromkeys(mythical_seed_matches))
                legendary_seed_matches = list(dict.fromkeys(legendary_seed_matches))
                gear_matches = list(dict.fromkeys(gear_matches))
                egg_matches = list(dict.fromkeys(egg_matches))

                # Send each alert type in a separate message
                if mythical_seed_matches and mythical_seed_role_id:
                    mention_text = f"<@&{mythical_seed_role_id}>\n**🦄 Mythical Seeds:**\n" + "\n".join(mythical_seed_matches)
                    await channel.send(mention_text)

                if legendary_seed_matches and legendary_seed_role_id:
                    mention_text = f"<@&{legendary_seed_role_id}>\n**🌟 Legendary Seeds:**\n" + "\n".join(legendary_seed_matches)
                    await channel.send(mention_text)

                # Special alert for rare seeds
                try:
                    # More precise matching for rare seeds
                    rare_seeds = []
                    all_seeds_lower = [s.lower() for s in stock_data.get("seeds", [])]
                    
                    for seed_name_original in stock_data.get("seeds", []):
                        seed_lower = seed_name_original.lower()
                        if "ember lily" in seed_lower or "emberlily" in seed_lower:
                            rare_seeds.append(("ember", seed_name_original))
                        elif "beanstalk" in seed_lower:
                            rare_seeds.append(("beanstalk", seed_name_original))
                        elif "sugar apple" in seed_lower:
                            rare_seeds.append(("sugar_apple", seed_name_original))
                        elif "loquat" in seed_lower:
                            rare_seeds.append(("loquat", seed_name_original))
                        elif "feijoa" in seed_lower:
                            rare_seeds.append(("feijoa", seed_name_original))

                    if rare_seeds:
                        news_channel = self.get_channel(NEWS_CHANNEL_ID)
                        if news_channel and rare_seed_role_id:
                            for seed_type, seed_name in rare_seeds:
                                alert_text = ""
                                if seed_type == "ember":
                                    alert_text = f"<@&{rare_seed_role_id}> 🔥 **EMBER LILY ALERT!!!** 🔥\n{seed_name} is now in the shop!!!"
                                    await channel.send(alert_text)
                                elif seed_type == "beanstalk":
                                    alert_text = f"<@&{rare_seed_role_id}> 🌱 **BEANSTALK ALERT!!!** 🌱\n{seed_name} is now in the shop!!!"
                                    await channel.send(alert_text)
                                elif seed_type == "sugar_apple":
                                    alert_text = f"<@&{rare_seed_role_id}> 🍎 **SUGAR APPLE ALERT!!!** 🍎\n{seed_name} is now in the shop!!!"
                                    await news_channel.send(alert_text)
                                elif seed_type == "loquat":
                                    alert_text = f"<@&{rare_seed_role_id}> 🍈 **LOQUAT ALERT!!!** 🍈\n{seed_name} is now in the shop!!!"
                                    await channel.send(alert_text)
                                elif seed_type == "feijoa":
                                    alert_text = f"<@&{rare_seed_role_id}> 🍐 **FEIJOA ALERT!!!** 🍐\n{seed_name} is now in the shop!!!"
                                    await channel.send(alert_text)
                                
                                await self.send_log(f"Rare seed alert sent: {seed_name}", "INFO")
                        else:
                            if not news_channel:
                                error_msg = "Could not find news channel for rare seed alerts"
                                logging.error(error_msg)
                                await self.send_log(error_msg, "ERROR")
                            if not rare_seed_role_id:
                                error_msg = "Rare seed role ID not found in EMOJI_ROLE_MAP"
                                logging.error(error_msg)
                                await self.send_log(error_msg, "ERROR")
                except Exception as e:
                    error_msg = f"Error sending rare seed alert: {e}"
                    logging.error(error_msg, exc_info=True)
                    await self.send_log(error_msg, "ERROR")

                if gear_matches and gear_role_id:
                    mention_text = f"<@&{gear_role_id}>\n**🧰 Gear:**\n" + "\n".join(gear_matches)
                    await channel.send(mention_text)

                # Only send egg pings every 30 minutes (with 3-minute window)
                now = datetime.now(PHOENIX_TZ)
                if egg_matches and now.minute % 30 < 3 and egg_role_id:
                    mention_text = f"<@&{egg_role_id}>\n**🥚 Eggs:**\n" + "\n".join(egg_matches)
                    await channel.send(mention_text)

                return True
            return False
        except Exception as e:
            logging.error(f"Error in post_stock: {e}")
            return False

    async def stock_loop(self):
        while True:
            try:
                now = datetime.now(PHOENIX_TZ)
                if self.is_website_broken:
                    minutes_since_5min_mark = now.minute % 5
                    seconds_into_5min_block = minutes_since_5min_mark * 60 + now.second
                    
                    # Wait until 90 seconds past the next 5-minute mark
                    # e.g., if it's 12:02, wait for 12:05 + 90s = 12:06:30
                    wait_seconds = (300 - seconds_into_5min_block) + 90
                    
                    if self.just_switched_to_fallback:
                        logging.info(f"Just switched to fallback - will wait {wait_seconds} seconds for first fallback post at next 5-min mark + 1:30")
                        self.just_switched_to_fallback = False
                        await asyncio.sleep(wait_seconds)
                        now = datetime.now(PHOENIX_TZ)
                    else:
                        logging.info(f"Using backup API - will send at next 5-minute mark + 1:30 (waiting {wait_seconds} seconds)")
                        await asyncio.sleep(wait_seconds)
                else:
                    seconds_since_5min_mark = (now.minute % 5) * 60 + now.second
                    wait_seconds = 300 - seconds_since_5min_mark
                    next_update_minute = ((now.minute // 5) * 5 + 5) % 60
                    if self.just_restored_main_api:
                        logging.info(f"Just restored main API - will wait {wait_seconds} seconds for first main API post at next 5-min mark")
                        self.just_restored_main_api = False
                        await asyncio.sleep(wait_seconds)
                        now = datetime.now(PHOENIX_TZ)
                    else:
                        logging.info(f"Using main API - will send at {now.hour:02d}:{next_update_minute:02d}:00 (waiting {wait_seconds} seconds)")
                        await asyncio.sleep(wait_seconds)
                    # Add a 7-second delay before posting when using main API
                    logging.info("Main API: Waiting an additional 7 seconds to ensure data is fresh.")
                    await asyncio.sleep(7)
                max_retries = 5
                retry_delay = 5
                success = False
                last_result = None
                for attempt in range(max_retries):
                    try:
                        result = await self.post_stock()
                        last_result = result
                        if result == "switched_to_fallback":
                            logging.info("Switched to fallback - will wait for fallback delay before posting any fallback update.")
                            success = False
                            break
                        elif result:
                            logging.info("Successfully posted stock update")
                            success = True
                            break
                        else:
                            logging.info(f"Attempt {attempt + 1}/{max_retries}: No changes detected, retrying...")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                    except Exception as e:
                        error_msg = f"Attempt {attempt + 1}/{max_retries} failed: {e}"
                        logging.error(error_msg, exc_info=True)
                        await self.send_log(error_msg, "ERROR")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                # If we just switched to fallback, immediately restart the loop so fallback logic is used
                if last_result == "switched_to_fallback":
                    continue
                if not success:
                    logging.warning("Failed to post stock update after all retries")
                    await self.send_log("Failed to post stock update after all retries", "WARNING")
            except Exception as e:
                error_msg = f"Error in stock loop: {e}"
                logging.error(error_msg, exc_info=True)
                await self.send_log(error_msg, "ERROR")
                await asyncio.sleep(60)

    async def harvest_ping_loop(self):
        """Sends a ping for the harvest event every hour."""
        await self.wait_until_ready()
        channel = self.get_channel(HARVEST_CHANNEL_ID)
        if not channel:
            logging.error(f"Could not find harvest channel with ID {HARVEST_CHANNEL_ID} for harvest ping.")
            return

        harvest_role_id = EMOJI_ROLE_MAP.get("🌽")
        if not harvest_role_id:
            logging.error("Harvest ping role ID not found in EMOJI_ROLE_MAP.")
            return

        while True:
            now = datetime.now(PHOENIX_TZ)
            # Calculate seconds until the next hour
            wait_seconds = 3600 - (now.minute * 60 + now.second + now.microsecond / 1_000_000)
            logging.info(f"Next harvest ping will be in {wait_seconds:.2f} seconds.")
            await asyncio.sleep(wait_seconds)

            try:
                message = f"<@&{harvest_role_id}> 🌽 It's time for the hourly harvest! 🌽"
                await channel.send(message)
                logging.info("Sent hourly harvest ping.")
                await self.send_log("Sent hourly harvest ping.", "INFO")
            except Exception as e:
                logging.error(f"Failed to send harvest ping: {e}")
                await self.send_log(f"Failed to send harvest ping: {e}", "ERROR")

    async def weather_alert_loop(self):
        """Checks for special weather alerts every minute."""
        await self.wait_until_ready()
        channel = self.get_channel(WEATHER_CHANNEL_ID)
        if not channel:
            logging.error(f"Could not find weather channel with ID {WEATHER_CHANNEL_ID} for weather alerts.")
            return

        weather_role_id = EMOJI_ROLE_MAP.get("🌧️")
        if not weather_role_id:
            logging.error("Weather alert role ID not found in EMOJI_ROLE_MAP.")
            return

        # Counter to track when to log (every 5 minutes)
        log_counter = 0

        while True:
            try:
                # Calculate seconds until the next minute
                now = datetime.now(PHOENIX_TZ)
                seconds_since_minute_mark = now.second
                wait_seconds = 60 - seconds_since_minute_mark
                
                # Only log every 5 minutes
                if log_counter % 5 == 0:
                    logging.info(f"Weather check - will send at next minute mark + 7s (waiting {wait_seconds} seconds)")
                await asyncio.sleep(wait_seconds)
                
                # Add a 7-second delay before checking weather
                if log_counter % 5 == 0:
                    logging.info("Weather check: Waiting an additional 7 seconds to ensure data is fresh.")
                await asyncio.sleep(7)
                
                stock_data = await fetch_all_stock()
                weather_items = stock_data.get("weather", [])

                if weather_items:
                    # Get the most recent weather
                    current_weather = weather_items[0].lower()
                    # Check if it's a special weather (not rain, frost, snow, or windy)
                    if not any(weather in current_weather for weather in ["rain", "frost", "snow", "windy"]):
                        # Only ping if it's different from the last alert
                        if current_weather != self.last_weather_alert:
                            # Clean up weather text by removing "- Most Recent"
                            weather_text = weather_items[0].replace(" - Most Recent", "")
                            mention_text = f"<@&{weather_role_id}>\n**🌧️ Special Weather Alert:**\n{weather_text}"
                            await channel.send(mention_text)
                            self.last_weather_alert = current_weather
                            self.save_state()  # Save state after weather alert
                            logging.info(f"Sent weather alert for: {current_weather}")
                            await self.send_log(f"Weather alert sent: {current_weather}", "INFO")
                        else:
                            # Only log skipped alerts every 5 minutes
                            if log_counter % 5 == 0:
                                logging.info(f"Skipped weather alert for {current_weather} as it's the same as last alert")

                # Increment counter
                log_counter += 1

            except Exception as e:
                logging.error(f"Error in weather_alert_loop: {e}", exc_info=True)
                await self.send_log(f"Error in weather_alert_loop: {e}", "ERROR")
                await asyncio.sleep(60) # Wait a minute before retrying on error

    async def on_ready(self):
        """Called when the bot is ready and connected to Discord."""
        logging.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logging.info('------')
        
        # Send initial stock data to test channel
        try:
            test_channel = self.get_channel(TEST_CHANNEL_ID)
            if test_channel:
                stock_data = await fetch_all_stock()
                embed = format_embed(stock_data)
                await test_channel.send(embed=embed)
                logging.info("Sent initial stock data to test channel")
                
                # Send initial weather data to test channel
                weather_items = stock_data.get("weather", [])
                if weather_items:
                    # Clean up weather text by removing "- Most Recent"
                    weather_text = weather_items[0].replace(" - Most Recent", "")
                    weather_embed = discord.Embed(
                        title="🌧️ Current Weather",
                        description=f"{weather_text}",
                        color=discord.Color.blue()
                    )
                    weather_embed.set_footer(text="Grow A Garden Weather Bot")
                    await test_channel.send(embed=weather_embed)
                    logging.info("Sent initial weather data to test channel")
        except Exception as e:
            logging.error(f"Failed to send initial data: {e}")
        
        # Start the stock loop
        asyncio.create_task(self.stock_loop())
        
        # Start the main website monitoring task
        asyncio.create_task(self.monitor_main_website())
        
        # Start the hourly harvest ping loop
        asyncio.create_task(self.harvest_ping_loop())
        
        # Start the weather alert loop
        asyncio.create_task(self.weather_alert_loop())
        
        # Send role message if needed
        await send_role_message()
        
        # Check all members' roles
        await check_all_members_roles()

    async def send_log(self, content, level="INFO"):
        """Send a log message to the Discord logs channel."""
        try:
            # Only send ERROR level logs and website status changes
            if (level == "ERROR" or 
                "Website unavailable alert sent" in content or 
                "Website back online alert sent" in content or
                "switching to API fallback" in content or
                "API fallback" in content):
                channel = self.get_channel(self.logs_channel_id)
                if channel:
                    # Format the message with timestamp and level
                    timestamp = datetime.now(PHOENIX_TZ).strftime("%Y-%m-%d %H:%M:%S")
                    formatted_message = f"[{timestamp}] [{level}] {content}"
                    await channel.send(f"```{formatted_message}```")
        except Exception as e:
            logging.error(f"Failed to send log to Discord: {e}")

client = MyClient()

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# Global variable to store the ID of the role-selection message
ROLE_MESSAGE_ID = None

async def fetch_all_stock():
    """
    Fetches stock data using the scraper and formats it for the bot.
    Handles both main website scraping and API fallback data formats.
    Normalizes keys and ensures only lists are iterated to prevent 'int object is not iterable' errors.
    """
    try:
        # Check if we should use fallback API
        if client.is_website_broken or api_fallback.is_using_fallback:
            logging.info("Using fallback API due to main website issues")
            stock_data = await api_fallback.fetch_stock_data()
        else:
            # Try main website first
            stock_data = await fetch_stock_data()
            
            # If main website returned empty data, try fallback
            if not stock_data or all(not items for items in stock_data.values()):
                logging.info("Main website returned empty data, trying fallback API")
                stock_data = await api_fallback.fetch_stock_data()

        # Normalize keys: support both singular and plural forms
        normalized = {
            "seeds": stock_data.get("seeds", []),
            "gear": stock_data.get("gear", stock_data.get("gears", [])),
            "egg": stock_data.get("egg", stock_data.get("eggs", [])),
            "weather": stock_data.get("weather", [])
        }

        results = {k: [] for k in normalized}

        def get_name(item):
            if isinstance(item, str):
                return item.strip()
            elif isinstance(item, dict):
                return str(item.get("name", "")).strip()
            return str(item).strip()

        for key, items in normalized.items():
            if not isinstance(items, list):
                logging.warning(f"Stock data key '{key}' is not a list (type: {type(items)}), skipping.")
                continue
            for item in items:
                name = get_name(item)
                if name:
                    results[key].append(name)
        return results
    except Exception as e:
        logging.warning(f"Failed to fetch stock: {e}")
        return {"seeds": [], "gear": [], "egg": [], "weather": []}

async def check_main_website_health() -> bool:
    """
    Check if the main website is accessible and working.
    Returns True if the website is healthy AND returning fresh data, False otherwise.
    """
    try:
        import aiohttp
        from bs4 import BeautifulSoup
        
        url = "https://growagardenvalues.com/stock/stocks.php"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    logging.warning(f"Main website returned status {response.status}")
                    return False
                
                content = await response.text()
                
                # Check if the page contains expected content
                if 'stock-section' not in content:
                    logging.warning("Main website health check failed - no stock sections found")
                    return False
                
                # Now check if the data is fresh by fetching actual stock data
                # and comparing it with the last known data
                try:
                    from scraper import fetch_stock_data
                    fresh_data = await fetch_stock_data()
                    
                    if not fresh_data or all(not items for items in fresh_data.values()):
                        logging.warning("Main website health check failed - returned empty data")
                        return False
                    
                    # If we have cached data, check if it's different (indicating fresh data)
                    if client.last_data:
                        last_seeds = client.last_data.get("seeds", [])
                        current_seeds = fresh_data.get("seeds", [])
                        
                        # If the data is the same as what we had before, it might be stale
                        if json.dumps(last_seeds, sort_keys=True) == json.dumps(current_seeds, sort_keys=True):
                            logging.warning("Main website health check failed - data appears to be stale (same as cached data)")
                            return False
                    
                    logging.info("Main website health check passed - website accessible and returning fresh data")
                    return True
                    
                except Exception as e:
                    logging.warning(f"Main website health check failed - error fetching fresh data: {e}")
                    return False
                    
    except Exception as e:
        logging.error(f"Main website health check failed: {e}")
        return False

def format_embed(data):
    def has_content(lst):
        return bool(lst) and any(str(x).strip() for x in lst)

    if not any(has_content(v) for v in data.values()):
        return discord.Embed(
            title="⚠️ No stock data available.",
            description="Try again later!",
            color=discord.Color.orange()
        )

    embed = discord.Embed(
        title="🛒 Grow A Garden Shop Update",
        description=f"Updated at <t:{int(time.time())}:T>",
        color=discord.Color.green()
    )

    if has_content(data["seeds"]):
        embed.add_field(
            name="🌱 Seeds",
            value="\n".join(data["seeds"]),
            inline=False
        )

    if has_content(data["gear"]):
        embed.add_field(
            name="🧰 Gear",
            value="\n".join(data["gear"]),
            inline=False
        )

    if has_content(data["egg"]):
        embed.add_field(
            name="🥚 Egg Items",
            value="\n".join(data["egg"]),
            inline=False
        )

    embed.set_footer(text="Grow A Garden Stock Bot")
    return embed

@client.tree.command(name="hi", description="Learn about the bot and its features")
async def hi(interaction: discord.Interaction):
    stock_channel = client.get_channel(STOCK_CHANNEL_ID)
    role_channel = client.get_channel(ROLE_CHANNEL_ID)
    weather_channel = client.get_channel(WEATHER_CHANNEL_ID)
    
    embed = discord.Embed(
        title="👋 Hi! I'm the Grow A Garden Stock Bot!",
        description="I was created by Tyla to help you stay updated with the latest items in the Grow A Garden shop!",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="📊 Stock Updates",
        value=f"I post regular updates about available seeds, gear, and eggs in {stock_channel.mention} every 5 minutes!",
        inline=False
    )
    
    embed.add_field(
        name="🔔 Role Alerts",
        value=f"Visit {role_channel.mention} to set up alerts for specific items:\n"
              "🦄 – Get notified about mythical seeds\n"
              "🌟 – Get notified about legendary seeds\n"
              "🔥 – Get notified about rare seeds\n"
              "🧰 – Get notified about rare gear\n"
              "🥚 – Get notified about rare eggs\n"
              f"🌧️ – Get notified about weather events in {weather_channel.mention}",
        inline=False
    )
    
    embed.add_field(
        name="✨ Special Feature",
        value="If you have the Gear, Egg, and Rare Seed roles (🧰, 🥚, 🔥), you'll automatically get the Alert Master role!",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

async def send_role_message():
    """
    Sends a message listing available alert roles with corresponding emojis.
    Users can react to this message to obtain or remove roles.
    """
    global ROLE_MESSAGE_ID
    channel = client.get_channel(ROLE_CHANNEL_ID)
    if channel is None:
        logging.warning(f"Role channel ID {ROLE_CHANNEL_ID} not found.")
        return

    # Check if a role message already exists
    async for message in channel.history(limit=100):
        if message.author == client.user and "React below to get alert roles!" in message.content:
            ROLE_MESSAGE_ID = message.id
            logging.info(f"Found existing role message (ID: {ROLE_MESSAGE_ID})")
            
            # Ensure all reactions are present
            current_reactions = [str(reaction.emoji) for reaction in message.reactions]
            for emoji in EMOJI_ROLE_MAP:
                if emoji not in current_reactions:
                    await message.add_reaction(emoji)
                    logging.info(f"Added missing reaction {emoji}")
            return

    # If no existing message found, send a new one
    stock_channel = client.get_channel(STOCK_CHANNEL_ID)
    harvest_channel = client.get_channel(HARVEST_CHANNEL_ID)
    weather_channel = client.get_channel(WEATHER_CHANNEL_ID)
    text = (
        "**React below to get alert roles!**\n\n"
        f"🦄 – Mythical Seeds Alerts (Get notified about mythical seeds in {stock_channel.mention})\n"
        f"🌟 – Legendary Seeds Alerts (Get notified about legendary seeds in {stock_channel.mention})\n"
        f"🔥 – Rare Seeds Alerts (Get notified about rare seeds in {stock_channel.mention})\n"
        f"🧰 – Gear Alerts (Get notified about rare gear in {stock_channel.mention})\n"
        f"🥚 – Egg Alerts (Get notified about rare eggs in {stock_channel.mention})\n"
        f"🌧️ – Weather Alerts (Get notified about weather events in {weather_channel.mention})\n"
        f"🌽 – Harvest Ping (Get notified about the hourly harvest event in {harvest_channel.mention})\n\n"
        "**✨ Special Feature:** If you have the Gear, Egg, and Rare Seed roles (🧰, 🥚, 🔥), you'll automatically get the Alert Master role!"
    )
    message = await channel.send(text)

    for emoji in EMOJI_ROLE_MAP:
        await message.add_reaction(emoji)

    ROLE_MESSAGE_ID = message.id
    logging.info(f"Sent new role-selection message (ID: {ROLE_MESSAGE_ID})")

async def check_and_assign_alert_role(member):
    """
    Checks if a member has all three required roles and assigns the alert role if they do.
    """
    try:
        # Get role IDs from the map
        rare_seed_role_id = EMOJI_ROLE_MAP.get("🔥")
        egg_role_id = EMOJI_ROLE_MAP.get("🥚")
        gear_role_id = EMOJI_ROLE_MAP.get("🧰")

        if not all([rare_seed_role_id, egg_role_id, gear_role_id]):
            logging.error("One or more role IDs for alert role check are missing from EMOJI_ROLE_MAP.")
            return

        # Get all three required roles (rare seeds, egg, gear)
        rare_seed_role = member.guild.get_role(rare_seed_role_id)
        egg_role = member.guild.get_role(egg_role_id)
        gear_role = member.guild.get_role(gear_role_id)
        alert_role = member.guild.get_role(ALERT_ROLE_ID)

        if not all([rare_seed_role, egg_role, gear_role, alert_role]):
            logging.error("One or more roles for alert role check not found in the server")
            return

        # Check if member has all three required roles (rare seeds, eggs, gear)
        has_all_roles = all(role in member.roles for role in [rare_seed_role, egg_role, gear_role])
        
        # Add or remove alert role based on whether they have all three required roles
        if has_all_roles and alert_role not in member.roles:
            await member.add_roles(alert_role)
            logging.info(f"Added alert role to {member.display_name}")
        elif not has_all_roles and alert_role in member.roles:
            await member.remove_roles(alert_role)
            logging.info(f"Removed alert role from {member.display_name}")
    except Exception as e:
        logging.error(f"Error in check_and_assign_alert_role: {e}", exc_info=True)

async def check_all_members_roles():
    """
    Checks all members' roles and assigns the alert role if they have all three required roles.
    """
    try:
        channel = client.get_channel(ROLE_CHANNEL_ID)
        if not channel:
            logging.error("Role channel not found")
            return

        guild = channel.guild
        if not guild:
            logging.error("Guild not found")
            return

        # Get role IDs from the map
        rare_seed_role_id = EMOJI_ROLE_MAP.get("🔥")
        egg_role_id = EMOJI_ROLE_MAP.get("🥚")
        gear_role_id = EMOJI_ROLE_MAP.get("🧰")

        if not all([rare_seed_role_id, egg_role_id, gear_role_id]):
            logging.error("One or more role IDs for alert role check are missing from EMOJI_ROLE_MAP.")
            return

        # Get all required roles
        rare_seed_role = guild.get_role(rare_seed_role_id)
        egg_role = guild.get_role(egg_role_id)
        gear_role = guild.get_role(gear_role_id)
        alert_role = guild.get_role(ALERT_ROLE_ID)

        if not all([rare_seed_role, egg_role, gear_role, alert_role]):
            logging.error("One or more roles for alert role check not found in the server")
            return

        # Check all members
        for member in guild.members:
            if not member.bot:  # Skip bots
                has_all_roles = all(role in member.roles for role in [rare_seed_role, egg_role, gear_role])
                
                # Add or remove alert role based on whether they have all three roles
                if has_all_roles and alert_role not in member.roles:
                    await member.add_roles(alert_role)
                    logging.info(f"Added alert role to {member.display_name}")
                elif not has_all_roles and alert_role in member.roles:
                    await member.remove_roles(alert_role)
                    logging.info(f"Removed alert role from {member.display_name}")

    except Exception as e:
        logging.error(f"Error in check_all_members_roles: {e}", exc_info=True)

@client.event
async def on_member_update(before, after):
    """
    Checks for role changes and updates alert role accordingly.
    """
    # Only proceed if roles have changed
    if before.roles != after.roles:
        await check_and_assign_alert_role(after)

@client.event
async def on_member_join(member):
    """
    Handle new member joins and update invite tracking, plus check roles.
    """
    try:
        # Send welcome message
        welcome_channel = client.get_channel(WELCOME_CHANNEL_ID)
        if welcome_channel:
            role_channel = client.get_channel(ROLE_CHANNEL_ID)
            about_channel = client.get_channel(ABOUT_CHANNEL_ID)
            if role_channel and about_channel:
                welcome_embed = discord.Embed(
                    title="🎉 Welcome to SCGAGS",
                    description=f"Hello {member.mention}! Welcome\n\n"
                               f"**Get Started:**\n"
                               f"• Visit {role_channel.mention} to set up your alert roles\n"
                               f"• Check out our stock updates in <#{STOCK_CHANNEL_ID}>\n"
                               f"• Go to {about_channel.mention} to learn more about the bot\n\n"
                               f"We're excited to have you here! 🌱",
                    color=discord.Color.green()
                )
                welcome_embed.set_thumbnail(url=member.display_avatar.url)
                welcome_embed.set_footer(text="Grow A Garden Community")
                await welcome_channel.send(embed=welcome_embed)
                logging.info(f"Sent welcome message for {member.display_name}")
            else:
                # Fallback if channels not found
                welcome_embed = discord.Embed(
                    title="🎉 Welcome to SCGAGS",
                    description=f"Hello {member.mention}! Welcome\n\n"
                               f"**Get Started:**\n"
                               f"• Check out our stock updates in <#{STOCK_CHANNEL_ID}>\n"
                               f"• Go to <#{ABOUT_CHANNEL_ID}> to learn more about the bot\n\n"
                               f"We're excited to have you here! 🌱",
                    color=discord.Color.green()
                )
                welcome_embed.set_thumbnail(url=member.display_avatar.url)
                welcome_embed.set_footer(text="Grow A Garden Community")
                await welcome_channel.send(embed=welcome_embed)
                logging.info(f"Sent welcome message for {member.display_name}")
        
        # Check if there's an active challenge
        active_challenge = invite_challenge.get_active_challenge(member.guild.id)
        if active_challenge:
            # Auto-join the new member to the challenge
            await invite_challenge.auto_join_new_member(active_challenge["id"], member.guild, member.id)
            
            # Update all participants' invite counts
            for user_id in active_challenge["participants"]:
                current_invites = await invite_challenge.get_user_invite_count(member.guild, int(user_id))
                invite_challenge.update_participant_invites(active_challenge["id"], int(user_id), current_invites)
            
            logging.info(f"Updated invite counts for challenge {active_challenge['id']} after {member.display_name} joined")
        
    except Exception as e:
        logging.error(f"Error in on_member_join: {e}")
    
    # Check new member's roles and assign alert role if they have all required roles
    await check_and_assign_alert_role(member)

@client.event
async def on_raw_reaction_add(payload):
    """
    Assigns a role when a user adds a reaction on the role-selection message.
    """
    logging.info(f"Reaction added: {payload.emoji} by user {payload.user_id} on message {payload.message_id}")
    
    if payload.message_id != ROLE_MESSAGE_ID:
        logging.info(f"Ignoring reaction on message {payload.message_id} (not role message)")
        return

    guild = client.get_guild(payload.guild_id)
    if guild is None:
        logging.warning(f"Could not find guild {payload.guild_id}")
        return

    role_id = EMOJI_ROLE_MAP.get(str(payload.emoji))
    if role_id is None:
        logging.warning(f"No role mapping found for emoji {payload.emoji}")
        return

    try:
        member = await guild.fetch_member(payload.user_id)
        role = guild.get_role(role_id)
        
        if not role:
            logging.error(f"Role with ID {role_id} not found in the server")
            return
            
        if not member:
            logging.error(f"Member with ID {payload.user_id} not found in the server")
            return
            
        # Check if bot has permission to manage roles
        bot_member = guild.get_member(client.user.id)
        if not bot_member.guild_permissions.manage_roles:
            logging.error("Bot does not have 'Manage Roles' permission")
            return
            
        # Check if bot's role is higher than the role it's trying to assign
        bot_role = bot_member.top_role
        if bot_role.position <= role.position:
            logging.error(f"Bot's role ({bot_role.name}) must be higher than the role it's trying to assign ({role.name})")
            return
            
        await member.add_roles(role)
        logging.info(f"Successfully assigned role {role.name} to {member.display_name}")
        
        # Check if they should get the alert role
        await check_and_assign_alert_role(member)
        
    except discord.Forbidden as e:
        logging.error(f"Permission error when assigning role: {e}")
        if "Missing Permissions" in str(e):
            logging.error("Bot needs 'Manage Roles' permission and its role must be higher than the roles it's trying to assign")
    except Exception as e:
        logging.error(f"Failed to assign role on reaction add: {e}", exc_info=True)

@client.event
async def on_raw_reaction_remove(payload):
    """
    Removes a role when a user removes a reaction on the role-selection message.
    """
    if payload.message_id != ROLE_MESSAGE_ID:
        return

    guild = client.get_guild(payload.guild_id)
    if guild is None:
        return

    role_id = EMOJI_ROLE_MAP.get(str(payload.emoji))
    if role_id is None:
        return

    try:
        member = await guild.fetch_member(payload.user_id)
        role = guild.get_role(role_id)
        
        if not role or not member:
            return
            
        # Check if bot has permission to manage roles
        bot_member = guild.get_member(client.user.id)
        if not bot_member.guild_permissions.manage_roles:
            logging.error("Bot does not have 'Manage Roles' permission")
            return
            
        # Check if bot's role is higher than the role it's trying to remove
        bot_role = bot_member.top_role
        if bot_role.position <= role.position:
            logging.error(f"Bot's role ({bot_role.name}) must be higher than the role it's trying to remove ({role.name})")
            return
            
        await member.remove_roles(role)
        logging.info(f"Removed role {role.name} from {member.display_name}")
        
        # Check if they should still have the alert role
        await check_and_assign_alert_role(member)
        
    except discord.Forbidden as e:
        logging.error(f"Permission error when removing role: {e}")
        if "Missing Permissions" in str(e):
            logging.error("Bot needs 'Manage Roles' permission and its role must be higher than the roles it's trying to remove")
    except Exception as e:
        logging.error(f"Failed to remove role on reaction remove: {e}", exc_info=True)

# Define the command group for /calc
calc_group = app_commands.Group(name="calc", description="Calculate crop value or list mutations")

@calc_group.command(name="value", description="Calculate the value of a crop with mutations")
@app_commands.describe(
    crop="The type of crop (e.g., apple)",
    growth_mutation="Growth mutation (default, golden, gold, rainbow)",
    temp_mutation="Temperature mutation (default, wet, chilled, frozen)",
    environmental_mutations="Comma-separated environmental mutations (e.g., chocolate,plasma)",
    weight_kg="Weight of the crop in kg (e.g., 2.85)"
)
async def calc_value(
    interaction: discord.Interaction,
    crop: str,
    weight_kg: float,
    growth_mutation: str = "default",
    temp_mutation: str = "default",
    environmental_mutations: str = ""
):
    """Calculate the total value of a crop."""
    # Split environmental mutations string into a list
    env_muts_list = [m.strip() for m in environmental_mutations.split(',') if m.strip()]

    # Validate inputs
    if weight_kg <= 0 and crop.lower() != "apple": # Only check if not apple, as apple has a default
        await interaction.response.send_message("❌ Weight (kg) must be greater than 0!", ephemeral=True)
        return

    # If weight_kg is 0.0 and crop is apple, use default weight
    if crop.lower() == "apple" and weight_kg == 0.0:
        weight_kg = calculator.crop_base_values["apple"]["default_weight"]

    # Calculate crop value
    result = calculator.calculate_crop_value(
        crop=crop,
        growth_mutation=growth_mutation,
        temp_mutation=temp_mutation,
        environmental_mutations=env_muts_list,
        weight_kg=weight_kg
    )

    # Format and send the result
    embed = calculator.format_calculation_result(result)
    await interaction.response.send_message(embed=embed)

@calc_group.command(name="mutations", description="List all available environmental mutations")
async def calc_mutations(interaction: discord.Interaction):
    """List all available environmental mutations."""
    mutations = calculator.get_environmental_mutations()
    if mutations:
        mutations_text = "\n".join([f"• {m.title()}" for m in mutations])
        embed = discord.Embed(
            title="✨ Available Environmental Mutations",
            description=mutations_text,
            color=discord.Color.purple()
        )
    else:
        embed = discord.Embed(
            title="❌ No Environmental Mutations Found",
            description="Could not retrieve environmental mutations.",
            color=discord.Color.red()
        )
    await interaction.response.send_message(embed=embed)

@calc_group.command(name="weights", description="List default weights for all plants")
async def calc_weights(interaction: discord.Interaction):
    """List default weights for all plants."""
    try:
        weights = calculator.get_default_weights()
        if weights:
            # Sort weights by plant name
            sorted_weights = sorted(weights.items(), key=lambda x: x[0].lower())
            
            # Create the list of plants
            plants_list = [f"• {plant.title()}: {weight} kg" for plant, weight in sorted_weights]
            
            # Join all plants with newlines and wrap in a code block
            plants_text = "```\n" + "\n".join(plants_list) + "\n```"
            
            embed = discord.Embed(
                title="🌱 Default Plant Weights",
                description=plants_text,
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ No Plant Weights Found",
                description="Could not retrieve plant weights.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
    except Exception as e:
        error_msg = f"Error in /calc weights command: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await client.send_log(error_msg, "ERROR")
        await interaction.response.send_message("❌ An error occurred while fetching plant weights. Please try again later.", ephemeral=True)

@client.tree.command(name="update", description="Send today's updates to the updates channel")
async def send_update(interaction: discord.Interaction):
    """Send today's updates to the updates channel."""
    try:
        # Create the update embed
        embed = discord.Embed(
            title="🔄 Bot Update v1.30.3",
            description="Latest improvements and additions to the Grow A Garden Bot:",
            color=discord.Color.blue()
        )
        #REMOVED NEW FEATURES SECTION ADD BACK NEXT UPDATE
        # Add bot improvements section
        bot_improvements = [
            "🌧️ **Weather Alert Improvements** - Windy weather is now excluded from weather pings"
        ]
        embed.add_field(
            name="🤖 Bot Improvements",
            value="\n".join([f"• {improvement}" for improvement in bot_improvements]),
            inline=False
        )

        embed.set_footer(text="Grow A Garden Bot Update v1.30.3")
        
        # Send to updates channel
        updates_channel = interaction.client.get_channel(UPDATES_CHANNEL_ID)
        if updates_channel:
            # Get the alerts role
            alerts_role = interaction.guild.get_role(ALERT_ROLE_ID)
            if alerts_role:
                await updates_channel.send(f"{alerts_role.mention} New bot update available!", embed=embed)
            else:
                await updates_channel.send(embed=embed)
            await interaction.response.send_message("✅ Update sent to the updates channel!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Could not find the updates channel!", ephemeral=True)
            
    except Exception as e:
        error_msg = f"Error in /update command: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.client.send_log(error_msg, "ERROR")
        await interaction.response.send_message("❌ An error occurred while sending the update. Please try again later.", ephemeral=True)

@client.tree.command(name="purge", description="Delete messages in the current channel")
@app_commands.describe(
    amount="Number of messages to delete (default: 100, max: 1000)",
    user="Only delete messages from this user (optional)"
)
@app_commands.checks.has_permissions(administrator=True)
async def purge(interaction: discord.Interaction, amount: int = 100, user: discord.Member = None):
    """Delete messages in the current channel."""
    try:
        # Limit amount to 1000 messages
        amount = min(amount, 1000)
        
        # Send initial response
        await interaction.response.send_message(f"🗑️ Deleting up to {amount} messages...", ephemeral=True)
        
        # Delete messages
        deleted = 0
        async for message in interaction.channel.history(limit=amount):
            if user is None or message.author == user:
                try:
                    await message.delete()
                    deleted += 1
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    await interaction.followup.send("❌ I don't have permission to delete messages!", ephemeral=True)
                    return
                except Exception as e:
                    logging.error(f"Error deleting message: {e}")
                    continue

        # Send completion message
        if user:
            await interaction.followup.send(f"✅ Deleted {deleted} messages from {user.mention}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Deleted {deleted} messages", ephemeral=True)
            
    except Exception as e:
        error_msg = f"Error in purge command: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.followup.send("❌ An error occurred while deleting messages.", ephemeral=True)

@purge.error
async def purge_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Only administrators can use this command!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An error occurred while trying to delete messages.", ephemeral=True)

@client.tree.command(name="switch", description="Switch between main website and API fallback (Admin only)")
@app_commands.describe(
    source="Choose which data source to use"
)
@app_commands.choices(source=[
    app_commands.Choice(name="Main Website", value="main"),
    app_commands.Choice(name="API Fallback", value="api")
])
@app_commands.checks.has_permissions(administrator=True)
async def switch_source(interaction: discord.Interaction, source: str):
    try:
        if source == "main":
            api_fallback.reset_fallback()
            # Reset bot's internal state
            client.is_website_broken = False
            client.fallback_switch_time = None
            client.repeated_data_count = 0
            message = "Switched to main website data source. The bot will now scrape the main website."
        else:  # api
            api_fallback.switch_to_fallback()
            # Set bot's internal state for fallback
            client.is_website_broken = True
            client.fallback_switch_time = int(time.time())
            message = "Switched to API fallback data source. The bot will use the backup API and send updates at XX:01, XX:06, XX:11, etc."
        
        # Save the state
        client.save_state()
        
        # Sync the fallback state
        client.sync_fallback_state()
        
        embed = discord.Embed(
            title="🔄 Data Source Switch",
            description=message,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await client.send_log(f"Data source manually switched to {source}", "INFO")
    except Exception as e:
        error_msg = f"Failed to switch data source: {e}"
        logging.error(error_msg)
        await interaction.response.send_message("Failed to switch data source. Please try again.", ephemeral=True)
        await client.send_log(error_msg, "ERROR")

@switch_source.error
async def switch_source_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message("An error occurred while switching data sources.", ephemeral=True)
        logging.error(f"Switch source error: {error}")

@client.tree.command(name="send", description="Send current stock data to the test channel")
@app_commands.checks.has_permissions(administrator=True)
async def send_test(interaction: discord.Interaction):
    """Send current stock data to the test channel."""
    try:
        # Get stock data
        stock_data = await fetch_all_stock()
        
        # Format and send embed
        embed = format_embed(stock_data)
        
        # Send to test channel
        test_channel = interaction.client.get_channel(TEST_CHANNEL_ID)
        if test_channel:
            await test_channel.send(embed=embed)
            await interaction.response.send_message("✅ Stock data sent to test channel!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Could not find the test channel!", ephemeral=True)
            
    except Exception as e:
        error_msg = f"Error in /send command: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.client.send_log(error_msg, "ERROR")
        await interaction.response.send_message("❌ An error occurred while sending stock data. Please try again later.", ephemeral=True)

@send_test.error
async def send_test_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Only administrators can use this command!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An error occurred while sending stock data.", ephemeral=True)

@client.tree.command(name="health", description="Check the health of the fallback API endpoints and main website")
@app_commands.checks.has_permissions(administrator=True)
async def check_health(interaction: discord.Interaction):
    """Check the health of the fallback API endpoints and main website."""
    try:
        # Check API health
        health_status = await api_fallback.check_api_health()
        
        # Check main website health
        main_website_health = await check_main_website_health()
        
        # Create embed
        embed = discord.Embed(
            title="🏥 System Health Check",
            description="Status of all data sources:",
            color=discord.Color.blue()
        )
        
        # Add main website health
        main_status_emoji = "✅" if main_website_health else "❌"
        main_status_text = "Online" if main_website_health else "Offline"
        embed.add_field(
            name=f"{main_status_emoji} Main Website",
            value=main_status_text,
            inline=True
        )
        
        # Add health status for each API endpoint
        for endpoint, status in health_status.items():
            status_emoji = "✅" if status else "❌"
            status_text = "Online" if status else "Offline"
            embed.add_field(
                name=f"{status_emoji} {endpoint.title()}",
                value=status_text,
                inline=True
            )
        
        # Add current fallback status
        fallback_status = "Active" if client.is_website_broken else "Inactive"
        fallback_emoji = "🔄" if client.is_website_broken else "✅"
        embed.add_field(
            name=f"{fallback_emoji} Fallback Status",
            value=fallback_status,
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        error_msg = f"Error in /health command: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.response.send_message("❌ An error occurred while checking system health.", ephemeral=True)

@check_health.error
async def check_health_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        logging.error(f"Error in /health command: {error}")

@client.tree.command(name="archive", description="Archives the current channel, making it read-only.")
@app_commands.checks.has_permissions(administrator=True)
async def archive(interaction: discord.Interaction):
    """
    Archives the channel where the command is invoked.

    This command sends an embed message to the channel indicating that it has
    been archived, and then it updates the channel's permissions to prevent
    non-administrator members from sending messages.
    """
    channel = interaction.channel

    # 1. Send an embed message
    embed = discord.Embed(
        title="🔒 Channel Archived",
        description="This channel has been archived. No new messages can be sent.",
        color=discord.Color.dark_grey()
    )
    await channel.send(embed=embed)

    # 2. Modify channel permissions
    try:
        # Get the @everyone role
        everyone_role = interaction.guild.default_role
        
        # Get existing overwrites for the role or create new ones
        overwrites = channel.overwrites_for(everyone_role)
        
        # Deny sending messages
        overwrites.send_messages = False
        
        # Apply the new permissions
        await channel.set_permissions(everyone_role, overwrite=overwrites)

        await interaction.response.send_message("✅ Channel successfully archived.", ephemeral=True)
        await client.send_log(f"Channel #{channel.name} was archived by {interaction.user.name}", "INFO")

    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to modify this channel's settings.", ephemeral=True)
        await client.send_log(f"Failed to archive channel #{channel.name} due to missing permissions.", "ERROR")
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
        await client.send_log(f"An error occurred while archiving channel #{channel.name}: {e}", "ERROR")

@archive.error
async def archive_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

@client.tree.command(name="lock", description="Locks the channel where the command is executed.")
@app_commands.checks.has_permissions(administrator=True)
async def lock(interaction: discord.Interaction):
    """
    Locks the channel where the command is invoked.

    This command sets permissions in the current channel
    to prevent non-administrators from sending messages or creating threads.
    """
    channel = interaction.channel
    everyone_role = interaction.guild.default_role
    
    try:
        # Get existing overwrites and update them
        overwrites = channel.overwrites_for(everyone_role)
        overwrites.send_messages = False
        overwrites.send_messages_in_threads = False
        overwrites.create_public_threads = False
        overwrites.create_private_threads = False

        await channel.set_permissions(everyone_role, overwrite=overwrites)

        await interaction.response.send_message(f"✅ Channel locked.", ephemeral=True)
        await client.send_log(f"Channel #{channel.name} locked by {interaction.user.name}", "INFO")

    except Exception as e:
        await interaction.response.send_message(f"An error occurred while locking the channel: {e}", ephemeral=True)
        await client.send_log(f"An error occurred while locking channel #{channel.name}: {e}", "ERROR")

@lock.error
async def lock_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

# Invite Challenge Commands
@client.tree.command(name="invite", description="Invite challenge commands")
@app_commands.describe(
    action="What to do with the invite challenge",
    duration="Duration in days (default: 7)",
    prize="Prize description (default: Special Role)"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Create", value="create"),
    app_commands.Choice(name="Join", value="join"),
    app_commands.Choice(name="Leaderboard", value="leaderboard"),
    app_commands.Choice(name="End", value="end"),
    app_commands.Choice(name="Status", value="status")
])
@app_commands.checks.has_permissions(manage_guild=True)
async def invite_challenge_cmd(
    interaction: discord.Interaction, 
    action: str, 
    duration: int = 7, 
    prize: str = "Special Role"
):
    """Manage invite challenges."""
    try:
        guild_id = interaction.guild.id
        
        if action == "create":
            # Check if there's already an active challenge
            active_challenge = invite_challenge.get_active_challenge(guild_id)
            if active_challenge:
                embed = discord.Embed(
                    title="❌ Challenge Already Active",
                    description=f"There's already an active invite challenge running!\n"
                               f"**Prize:** {active_challenge['prize']}\n"
                               f"**Time Remaining:** {invite_challenge.format_time_remaining(active_challenge['end_time'])}",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Create new challenge
            challenge = invite_challenge.create_challenge(guild_id, duration, prize)
            
            # Auto-join all existing members
            added_count = await invite_challenge.auto_join_all_members(challenge["id"], interaction.guild)
            
            embed = discord.Embed(
                title="🎉 Invite Challenge Created!",
                description=f"**Prize:** {prize}\n"
                           f"**Duration:** {duration} days\n"
                           f"**Ends:** <t:{challenge['end_time']}:F>\n"
                           f"**Auto-joined:** {added_count} members\n\n"
                           f"Everyone is automatically participating! Use `/leaderboard` to see rankings!",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Challenge ID: {challenge['id']}")
            
            await interaction.response.send_message(embed=embed)
            await client.send_log(f"Invite challenge created by {interaction.user.name}: {prize} for {duration} days, auto-joined {added_count} members", "INFO")
            
        elif action == "join":
            # Check if there's an active challenge
            active_challenge = invite_challenge.get_active_challenge(guild_id)
            if not active_challenge:
                embed = discord.Embed(
                    title="❌ No Active Challenge",
                    description="There's no active invite challenge to join!",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Get user's current invite count
            current_invites = await invite_challenge.get_user_invite_count(interaction.guild, interaction.user.id)
            
            # Update participant data
            invite_challenge.update_participant_invites(active_challenge["id"], interaction.user.id, current_invites)
            
            embed = discord.Embed(
                title="✅ Joined Invite Challenge!",
                description=f"You've successfully joined the invite challenge!\n"
                           f"**Current Invites:** {current_invites}\n"
                           f"**Prize:** {active_challenge['prize']}\n"
                           f"**Time Remaining:** {invite_challenge.format_time_remaining(active_challenge['end_time'])}\n\n"
                           f"Use `/invite leaderboard` to see the current rankings!",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        elif action == "leaderboard":
            # Check if there's an active challenge
            active_challenge = invite_challenge.get_active_challenge(guild_id)
            if not active_challenge:
                embed = discord.Embed(
                    title="❌ No Active Challenge",
                    description="There's no active invite challenge to show leaderboard for!",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Show leaderboard
            embed = invite_challenge.format_leaderboard_embed(active_challenge, interaction.guild)
            await interaction.response.send_message(embed=embed)
            
        elif action == "end":
            # Check if there's an active challenge
            active_challenge = invite_challenge.get_active_challenge(guild_id)
            if not active_challenge:
                embed = discord.Embed(
                    title="❌ No Active Challenge",
                    description="There's no active invite challenge to end!",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # End the challenge
            ended_challenge = invite_challenge.end_challenge(active_challenge["id"])
            
            if ended_challenge["winners"]:
                winners_text = ""
                for i, winner_id in enumerate(ended_challenge["winners"], 1):
                    member = interaction.guild.get_member(int(winner_id))
                    username = member.display_name if member else f"User {winner_id}"
                    invites = ended_challenge["final_scores"].get(winner_id, 0)
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                    winners_text += f"{medal} **{username}** - {invites} invites\n"
                
                embed = discord.Embed(
                    title="🏆 Invite Challenge Ended!",
                    description=f"**Prize:** {ended_challenge['prize']}\n\n**Winners:**\n{winners_text}",
                    color=discord.Color.gold()
                )
            else:
                embed = discord.Embed(
                    title="🏆 Invite Challenge Ended!",
                    description=f"**Prize:** {ended_challenge['prize']}\n\nNo one participated in this challenge.",
                    color=discord.Color.gold()
                )
            
            await interaction.response.send_message(embed=embed)
            await client.send_log(f"Invite challenge ended by {interaction.user.name}", "INFO")
            
        elif action == "status":
            # Check if there's an active challenge
            active_challenge = invite_challenge.get_active_challenge(guild_id)
            if not active_challenge:
                embed = discord.Embed(
                    title="❌ No Active Challenge",
                    description="There's no active invite challenge!",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Show challenge status
            participants_count = len(active_challenge["participants"])
            embed = discord.Embed(
                title="📊 Challenge Status",
                description=f"**Prize:** {active_challenge['prize']}\n"
                           f"**Participants:** {participants_count}\n"
                           f"**Time Remaining:** {invite_challenge.format_time_remaining(active_challenge['end_time'])}\n"
                           f"**Started:** <t:{active_challenge['start_time']}:F>",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Challenge ID: {active_challenge['id']}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        error_msg = f"Error in invite challenge command: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.response.send_message("❌ An error occurred while processing the invite challenge command.", ephemeral=True)
        await client.send_log(error_msg, "ERROR")

@invite_challenge_cmd.error
async def invite_challenge_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You need 'Manage Server' permission to use invite challenge commands!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An error occurred with the invite challenge command.", ephemeral=True)

@client.tree.command(name="joinchallenge", description="Join the current invite challenge")
async def join_challenge(interaction: discord.Interaction):
    """Join the current invite challenge."""
    try:
        guild_id = interaction.guild.id
        
        # Check if there's an active challenge
        active_challenge = invite_challenge.get_active_challenge(guild_id)
        if not active_challenge:
            embed = discord.Embed(
                title="❌ No Active Challenge",
                description="There's no active invite challenge to join!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Check if user already joined
        if str(interaction.user.id) in active_challenge["participants"]:
            embed = discord.Embed(
                title="❌ Already Joined",
                description="You've already joined this invite challenge!",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Get user's current invite count
        current_invites = await invite_challenge.get_user_invite_count(interaction.guild, interaction.user.id)
        
        # Update participant data
        invite_challenge.update_participant_invites(active_challenge["id"], interaction.user.id, current_invites)
        
        embed = discord.Embed(
            title="✅ Joined Invite Challenge!",
            description=f"You've successfully joined the invite challenge!\n"
                       f"**Current Invites:** {current_invites}\n"
                       f"**Prize:** {active_challenge['prize']}\n"
                       f"**Time Remaining:** {invite_challenge.format_time_remaining(active_challenge['end_time'])}\n\n"
                       f"Use `/invite leaderboard` to see the current rankings!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        error_msg = f"Error joining invite challenge: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.response.send_message("❌ An error occurred while joining the challenge.", ephemeral=True)
        await client.send_log(error_msg, "ERROR")

@client.tree.command(name="leaderboard", description="Show the current invite challenge leaderboard")
async def show_leaderboard(interaction: discord.Interaction):
    """Show the current invite challenge leaderboard."""
    try:
        guild_id = interaction.guild.id
        
        # Check if there's an active challenge
        active_challenge = invite_challenge.get_active_challenge(guild_id)
        if not active_challenge:
            embed = discord.Embed(
                title="❌ No Active Challenge",
                description="There's no active invite challenge to show leaderboard for!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Show leaderboard
        embed = invite_challenge.format_leaderboard_embed(active_challenge, interaction.guild)
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        error_msg = f"Error showing leaderboard: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.response.send_message("❌ An error occurred while showing the leaderboard.", ephemeral=True)
        await client.send_log(error_msg, "ERROR")

@client.tree.command(name="refreshinvites", description="Manually refresh invite counts for all participants (Admin only)")
@app_commands.checks.has_permissions(manage_guild=True)
async def refresh_invites(interaction: discord.Interaction):
    """Manually refresh invite counts for all participants."""
    try:
        guild_id = interaction.guild.id
        
        # Check if there's an active challenge
        active_challenge = invite_challenge.get_active_challenge(guild_id)
        if not active_challenge:
            embed = discord.Embed(
                title="❌ No Active Challenge",
                description="There's no active invite challenge to refresh!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Refresh invite counts for all participants
        updated_count = 0
        for user_id in active_challenge["participants"]:
            try:
                current_invites = await invite_challenge.get_user_invite_count(interaction.guild, int(user_id))
                invite_challenge.update_participant_invites(active_challenge["id"], int(user_id), current_invites)
                updated_count += 1
            except Exception as e:
                logging.error(f"Error refreshing invites for user {user_id}: {e}")
        
        embed = discord.Embed(
            title="✅ Invite Counts Refreshed",
            description=f"Successfully refreshed invite counts for {updated_count} participants!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await client.send_log(f"Invite counts refreshed for {updated_count} participants by {interaction.user.name}", "INFO")
        
    except Exception as e:
        error_msg = f"Error refreshing invite counts: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.response.send_message("❌ An error occurred while refreshing invite counts.", ephemeral=True)
        await client.send_log(error_msg, "ERROR")

@refresh_invites.error
async def refresh_invites_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An error occurred with the refresh command.", ephemeral=True)

@client.tree.command(name="myinvites", description="Check your current invite count")
async def check_my_invites(interaction: discord.Interaction):
    """Check your current invite count."""
    try:
        # Get user's current invite count
        current_invites = await invite_challenge.get_user_invite_count(interaction.guild, interaction.user.id)
        
        # Check if there's an active challenge
        active_challenge = invite_challenge.get_active_challenge(interaction.guild.id)
        if active_challenge:
            embed = discord.Embed(
                title="📊 Your Invite Stats",
                description=f"**Challenge Invites:** {current_invites}\n\n"
                           f"Active challenge running! Check `/leaderboard` to see rankings.",
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title="📊 Your Invite Stats",
                description=f"**Total Invites:** {current_invites}\n\n"
                           f"No active challenge running.",
                color=discord.Color.blue()
            )
        
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        error_msg = f"Error checking invite count: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.response.send_message("❌ An error occurred while checking your invite count.", ephemeral=True)

@client.tree.command(name="setinvites", description="Set someone's invite count for the active challenge (Admin only)")
@app_commands.describe(
    user="The user whose invite count to update",
    count="The new invite count to set"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def set_invites(interaction: discord.Interaction, user: discord.Member, count: int):
    """Set someone's invite count for the active challenge."""
    try:
        guild_id = interaction.guild.id
        
        # Check if there's an active challenge
        active_challenge = invite_challenge.get_active_challenge(guild_id)
        if not active_challenge:
            embed = discord.Embed(
                title="❌ No Active Challenge",
                description="There's no active invite challenge to update!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Ensure count is not negative
        if count < 0:
            await interaction.response.send_message("❌ Invite count cannot be negative!", ephemeral=True)
            return
        
        # Update the user's invite count
        invite_challenge.update_participant_invites(active_challenge["id"], user.id, count)
        
        embed = discord.Embed(
            title="✅ Invite Count Updated",
            description=f"**{user.display_name}**'s invite count has been set to **{count}**",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Updated by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Log the action
        await client.send_log(f"Invite count for {user.display_name} set to {count} by {interaction.user.name}", "INFO")
        
    except Exception as e:
        error_msg = f"Error setting invite count: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.response.send_message("❌ An error occurred while setting the invite count.", ephemeral=True)
        await client.send_log(error_msg, "ERROR")

@set_invites.error
async def set_invites_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An error occurred with the set invites command.", ephemeral=True)

@client.tree.command(name="addinvites", description="Add invites to someone's count for the active challenge (Admin only)")
@app_commands.describe(
    user="The user whose invite count to add to",
    count="The number of invites to add"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def add_invites(interaction: discord.Interaction, user: discord.Member, count: int):
    """Add invites to someone's count for the active challenge."""
    try:
        guild_id = interaction.guild.id
        
        # Check if there's an active challenge
        active_challenge = invite_challenge.get_active_challenge(guild_id)
        if not active_challenge:
            embed = discord.Embed(
                title="❌ No Active Challenge",
                description="There's no active invite challenge to update!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Get current count
        current_count = active_challenge["participants"].get(str(user.id), {}).get("current_invites", 0)
        new_count = current_count + count
        
        # Ensure count is not negative
        if new_count < 0:
            await interaction.response.send_message("❌ Resulting invite count cannot be negative!", ephemeral=True)
            return
        
        # Update the user's invite count
        invite_challenge.update_participant_invites(active_challenge["id"], user.id, new_count)
        
        embed = discord.Embed(
            title="✅ Invites Added",
            description=f"**{count}** invites added to **{user.display_name}**\n"
                       f"**Previous:** {current_count} → **New:** {new_count}",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Updated by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Log the action
        await client.send_log(f"{count} invites added to {user.display_name} (now {new_count}) by {interaction.user.name}", "INFO")
        
    except Exception as e:
        error_msg = f"Error adding invites: {str(e)}"
        logging.error(error_msg, exc_info=True)
        await interaction.response.send_message("❌ An error occurred while adding invites.", ephemeral=True)
        await client.send_log(error_msg, "ERROR")

@add_invites.error
async def add_invites_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An error occurred with the add invites command.", ephemeral=True)

async def main():
    global client
    try:
        await client.start(TOKEN)
    except Exception as e:
        logging.error(f"Error in main function: {e}")
        await client.send_log(f"Error in main function: {e}", "ERROR")
        await asyncio.sleep(60)  # Wait before retrying

asyncio.run(main())
