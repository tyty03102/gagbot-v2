# GagBot - Discord Bot for Stock Monitoring & Community Management

A feature-rich Discord bot designed for monitoring stock data, managing community roles, and providing various utility functions for Discord servers.

## Features

### 🛍️ Stock Monitoring
- Real-time stock data monitoring with automatic updates
- Fallback API system for reliability
- Phoenix timezone support
- Automatic alerts when stock data changes

### 🎭 Role Management
- Emoji-based role assignment system
- Automatic role management for new members
- Alert role system for notifications
- Welcome messages for new members

### 🧮 Calculator Commands
- Crop value calculator with mutation support
- Environmental mutation listings
- Default weight information for plants
- Advanced calculation features

### 🎯 Invite Challenge System
- Create and manage invite challenges
- Leaderboard tracking
- Prize management
- Automatic invite counting

### 🌦️ Weather & Event Alerts
- Weather alert system
- Harvest event notifications
- Automated ping systems

### 🛠️ Administrative Tools
- Channel archiving and locking
- Message purging
- Health monitoring
- API source switching

## Prerequisites

- Python 3.8 or higher
- Discord Bot Token
- Discord Server with appropriate permissions

## Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd gagbot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Playwright (for web scraping)**
   ```bash
   playwright install
   ```

4. **Configure the bot**
   - Copy `config_sample.py` to `config.py`
   - Edit `config.py` with your Discord bot token and channel IDs

## Configuration

Edit `config.py` with your specific settings:

```python
# Discord Bot Configuration
TOKEN = 'your-discord-bot-token'

# Channel IDs
STOCK_CHANNEL_ID = 1234567890123456789
ROLE_CHANNEL_ID = 1234567890123456789
LOGS_CHANNEL_ID = 1234567890123456789
# ... other channel IDs

# Role IDs
EMOJI_ROLE_MAP = {
    "🦄": 1234567890123456789, # Mythical Seeds
    "🌟": 1234567890123456789, # Legendary Seeds
    # ... other role mappings
}
```

## Usage

### Starting the Bot
```bash
python gagbot.py
```

### Available Commands

#### General Commands
- `/hi` - Learn about the bot and its features
- `/update` - Send today's updates to the updates channel

#### Calculator Commands
- `/calc value` - Calculate crop value with mutations
- `/calc mutations` - List available environmental mutations
- `/calc weights` - List default weights for all plants

#### Administrative Commands
- `/purge` - Delete messages in the current channel
- `/switch` - Switch between main website and API fallback
- `/health` - Check API health status
- `/archive` - Archive the current channel
- `/lock` - Lock the current channel

#### Invite Challenge Commands
- `/invite` - Manage invite challenges
- `/joinchallenge` - Join the current invite challenge
- `/leaderboard` - Show challenge leaderboard
- `/myinvites` - Check your invite count
- `/refreshinvites` - Manually refresh invite counts
- `/setinvites` - Set someone's invite count
- `/addinvites` - Add invites to someone's count

## Bot Permissions

The bot requires the following permissions:
- Send Messages
- Manage Messages
- Manage Roles
- Add Reactions
- Read Message History
- Use Slash Commands
- Manage Channels (for archive/lock features)

## File Structure

```
gagbot/
├── gagbot.py          # Main bot file
├── config.py          # Configuration (gitignored)
├── config_sample.py   # Sample configuration
├── requirements.txt   # Python dependencies
├── calculator.py      # Calculator functionality
├── scraper.py         # Web scraping utilities
├── api.py            # API fallback system
├── invite.py         # Invite challenge system
├── cmds              # Command definitions
└── README.md         # This file
```

## Features in Detail

### Stock Monitoring System
- Monitors stock data every 5 minutes
- Automatic fallback to backup API when main source is unavailable
- Health monitoring with 15-minute intervals
- Phoenix timezone support for accurate timing

### Role Management
- Emoji reaction system for role assignment
- Automatic role checking for new members
- Master alert role system
- Welcome message integration

### Calculator System
- Supports growth mutations (default, golden, gold, rainbow)
- Temperature mutations (default, wet, chilled, frozen)
- Environmental mutations (chocolate, plasma, etc.)
- Weight-based calculations

### Invite Challenge System
- Create time-limited challenges
- Automatic invite tracking
- Leaderboard management
- Prize system integration

## Troubleshooting

### Common Issues

1. **Bot not responding to commands**
   - Check if the bot has proper permissions
   - Verify the bot token is correct
   - Ensure slash commands are synced

2. **Stock data not updating**
   - Check internet connection
   - Verify API endpoints are accessible
   - Check logs for error messages

3. ** Role assignment not working**
   - Verify role IDs are correct
   - Check bot has "Manage Roles" permission
   - Ensure role hierarchy is correct

### Logs
The bot creates detailed logs in `logs.txt` for debugging purposes.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please check the logs or create an issue in the repository.

---