import discord
import asyncio
import requests
import logging
from datetime import datetime
import time
import json
from discord import app_commands
from config import TOKEN, STOCK_CHANNEL_ID, ROLE_CHANNEL_ID, EMOJI_ROLE_MAP, ALERT_ROLE_ID
import pytz

# Configure all required intents
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
intents.members = True  # Enable members intent for fetch_member
intents.reactions = True  # Enable reactions intent

# Set Phoenix timezone
PHOENIX_TZ = pytz.timezone('America/Phoenix')

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.last_data = None

    async def setup_hook(self):
        await self.tree.sync()

    async def post_stock(self):
        try:
        stock_data = fetch_all_stock()
            
            # Add timestamp to track when data was last fetched
            current_time = int(time.time())
            stock_data['timestamp'] = current_time

        # Check if stock data changed since last run
            if self.last_data is not None:
                # Compare data excluding timestamp
                last_data_copy = self.last_data.copy()
                current_data_copy = stock_data.copy()
                last_data_copy.pop('timestamp', None)
                current_data_copy.pop('timestamp', None)
                
                if json.dumps(last_data_copy, sort_keys=True) == json.dumps(current_data_copy, sort_keys=True):
            logging.info("No changes in stock data.")
            return False  # No new data
                
                # Check if data is too old (more than 10 minutes)
                if 'timestamp' in self.last_data and current_time - self.last_data['timestamp'] > 600:
                    logging.warning("Stock data is more than 10 minutes old, forcing update")
                    return True

        self.last_data = stock_data
        channel = self.get_channel(STOCK_CHANNEL_ID)
        if channel is None:
            logging.error("Stock channel not found")
            return False

        embed = format_embed(stock_data)

        # Send embed first
        await channel.send(embed=embed)
        logging.info("Posted stock embed.")

        # Then send pings with item summaries
        mentions = []

        # Role IDs (for pings)
        seed_role_id = EMOJI_ROLE_MAP["🌱"]
        gear_role_id = EMOJI_ROLE_MAP["🧰"]
        egg_role_id = EMOJI_ROLE_MAP["🥚"]
        bee_role_id = EMOJI_ROLE_MAP["🐝"]

        # Keywords to watch for (lowercase for matching)
        seed_keywords = {
            "beanstalk", "cacao", "grape", "dragon fruit", "mango", "pepper", "mushroom"
        }
        gear_keywords = {"lightning", "master", "godly"}
        bee_keywords = {"flower", "hive", "nectarine", "sprinkler"}

        seed_matches = [s for s in stock_data.get("seeds", []) if any(k in s.lower() for k in seed_keywords)]
        gear_matches = [g for g in stock_data.get("gear", []) if any(k in g.lower() for k in gear_keywords)]
        bee_matches = [b for b in stock_data.get("bee", []) if any(k in b.lower() for k in bee_keywords)]

        if seed_matches:
            mention_text = f"<@&{seed_role_id}>\n**🌱 Seeds:**\n" + "\n".join(seed_matches)
            mentions.append(mention_text)

        if gear_matches:
            mention_text = f"<@&{gear_role_id}>\n**🧰 Gear:**\n" + "\n".join(gear_matches)
            mentions.append(mention_text)

        # Only send bee pings on the hour (with 3-minute window)
            now = datetime.now(PHOENIX_TZ)
        if bee_matches and now.minute < 3:
            mention_text = f"<@&{bee_role_id}>\n**🐝 Bee Event:**\n" + "\n".join(bee_matches)
            mentions.append(mention_text)

        if mentions:
            full_mention = "\n\n".join(mentions)
            await channel.send(full_mention)

        return True
        except Exception as e:
            logging.error(f"Failed to post stock: {e}")
            return False

    async def stock_loop(self):
        while True:
            now = datetime.now(PHOENIX_TZ)
            seconds_since_5min_mark = (now.minute % 5) * 60 + now.second
            wait_seconds = 300 - seconds_since_5min_mark

            logging.info(f"Waiting {wait_seconds} seconds until next scheduled stock check...")
            await asyncio.sleep(wait_seconds)

            posted = await self.post_stock()
            while not posted:
                logging.info("Retrying in 5seconds because no new data yet...")
                await asyncio.sleep(5)
                posted = await self.post_stock()

    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        
        # Verify the role channel exists
        channel = self.get_channel(ROLE_CHANNEL_ID)
        if channel is None:
            logging.error(f"Role channel ID {ROLE_CHANNEL_ID} not found!")
            return

        # Send the role-selection message once on startup
        await send_role_message()
        
        # Verify the message was sent and ID was stored
        if ROLE_MESSAGE_ID is None:
            logging.error("Failed to set ROLE_MESSAGE_ID!")
        else:
            logging.info(f"Role message ID set to: {ROLE_MESSAGE_ID}")
            # Check all members' roles
            await check_all_members_roles()

        # Begin stock-updates
        channel = self.get_channel(STOCK_CHANNEL_ID)
        if channel is None:
            logging.warning(f"Stock channel ID {STOCK_CHANNEL_ID} not found.")
            return
        logging.info(f"Bot connected to stock channel: {channel.name} (ID: {channel.id})")

        # Trigger an immediate post on startup
        await self.post_stock()
        
        # Start the stock checking loop
        self.loop.create_task(self.stock_loop())

client = MyClient()

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# Global variable to store the ID of the role-selection message
ROLE_MESSAGE_ID = None

def fetch_all_stock():
    try:
        logging.info("Fetching stock from new API endpoints")
        
        # Fetch gear and seeds
        gear_seeds_response = requests.get("https://growagardenstock.com/api/stock?type=gear-seeds")
        gear_seeds_response.raise_for_status()
        gear_seeds_data = gear_seeds_response.json()
        
        # Fetch eggs
        egg_response = requests.get("https://growagardenstock.com/api/stock?type=egg")
        egg_response.raise_for_status()
        egg_data = egg_response.json()

        results = {
            "gear": [],
            "seeds": [],
            "egg": [],
            "bee": []  # Temporarily disabled
        }

        # Process gear and seeds from first endpoint
        if "gear" in gear_seeds_data:
            results["gear"] = gear_seeds_data["gear"]
        if "seeds" in gear_seeds_data:
            results["seeds"] = gear_seeds_data["seeds"]

        # Process eggs from second endpoint
        if "egg" in egg_data:
            results["egg"] = egg_data["egg"]

    return results
    except Exception as e:
        logging.warning(f"Failed to fetch stock: {e}")
        return {"gear": [], "seeds": [], "egg": [], "bee": []}

def format_embed(data):
    if not any(data.values()):
        return discord.Embed(
            title="⚠️ No stock data available.",
            description="Try again later!",
            color=discord.Color.orange()
        )

    embed = discord.Embed(
        title="🛒 Grow A Garden Shop Update",
        description=f"Updated at <t:{int(time.time())}:t>",
        color=discord.Color.green()
    )

    if data["seeds"]:
        embed.add_field(
            name="🌱 Seeds",
            value="\n".join(data["seeds"]),
            inline=False
        )

    if data["gear"]:
        embed.add_field(
            name="🧰 Gear",
            value="\n".join(data["gear"]),
            inline=False
        )

    if data["egg"]:
        embed.add_field(
            name="🥚 Egg Items",
            value="\n".join(data["egg"]),
            inline=False
        )

    if data["bee"]:
        embed.add_field(
            name="🐝 Bee Event Items",
            value="\n".join(data["bee"]),
            inline=False
        )

    embed.set_footer(text="Grow A Garden Stock Bot")
    return embed

@client.tree.command(name="hi", description="Learn about the bot and its features")
async def hi(interaction: discord.Interaction):
    stock_channel = client.get_channel(STOCK_CHANNEL_ID)
    role_channel = client.get_channel(ROLE_CHANNEL_ID)
    
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
              "🌱 – Get notified about rare seeds\n"
              "🧰 – Get notified about rare gear\n"
              "🥚 – Get notified about rare eggs\n"
              "🐝 – Get notified about bee event items",
        inline=False
    )
    
    embed.add_field(
        name="✨ Special Feature",
        value="If you have all four alert roles, you'll automatically get the Alert Master role!",
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
    text = (
        "**React below to get alert roles!**\n\n"
        f"🌱 – Seeds Alerts (Get notified about rare seeds in {stock_channel.mention})\n"
        f"🧰 – Gear Alerts (Get notified about rare gear in {stock_channel.mention})\n"
        f"🥚 – Egg Alerts (Get notified about rare eggs in {stock_channel.mention})\n"
        f"🐝 – Bee Alerts (Get notified about bee event items in {stock_channel.mention})\n\n"
        "**✨ Special Feature:** If you have all four roles, you'll automatically get the Alert Master role!"
    )
    message = await channel.send(text)

    for emoji in EMOJI_ROLE_MAP:
        await message.add_reaction(emoji)

    ROLE_MESSAGE_ID = message.id
    logging.info(f"Sent new role-selection message (ID: {ROLE_MESSAGE_ID})")

async def check_and_assign_alert_role(member):
    """
    Checks if a member has all four roles and assigns the alert role if they do.
    """
    try:
        # Get all four roles
        seed_role = member.guild.get_role(EMOJI_ROLE_MAP["🌱"])
        gear_role = member.guild.get_role(EMOJI_ROLE_MAP["🧰"])
        egg_role = member.guild.get_role(EMOJI_ROLE_MAP["🥚"])
        bee_role = member.guild.get_role(EMOJI_ROLE_MAP["🐝"])
        alert_role = member.guild.get_role(ALERT_ROLE_ID)

        if not all([seed_role, gear_role, egg_role, bee_role, alert_role]):
            logging.error("One or more roles not found in the server")
            return

        # Check if member has all four roles
        has_all_roles = all(role in member.roles for role in [seed_role, gear_role, egg_role, bee_role])
        
        # Add or remove alert role based on whether they have all four roles
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
    Checks all members' roles and assigns the alert role if they have all four required roles.
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

        # Get all required roles
        seed_role = guild.get_role(EMOJI_ROLE_MAP["🌱"])
        gear_role = guild.get_role(EMOJI_ROLE_MAP["🧰"])
        egg_role = guild.get_role(EMOJI_ROLE_MAP["🥚"])
        bee_role = guild.get_role(EMOJI_ROLE_MAP["🐝"])
        alert_role = guild.get_role(ALERT_ROLE_ID)

        if not all([seed_role, gear_role, egg_role, bee_role, alert_role]):
            logging.error("One or more roles not found in the server")
        return

        # Check all members
        for member in guild.members:
            if not member.bot:  # Skip bots
                has_all_roles = all(role in member.roles for role in [seed_role, gear_role, egg_role, bee_role])
                
                # Add or remove alert role based on whether they have all four roles
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
    Checks new member's roles and assigns alert role if they have all required roles.
    """
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

async def main():
    await client.start(TOKEN)

asyncio.run(main())
