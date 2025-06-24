# Invite Challenge System

The invite challenge system allows server administrators to create competitions where members compete to invite the most people to the server within a specified time period.

## Features

- **Create Challenges**: Set up invite competitions with custom prizes and durations
- **Automatic Participation**: All existing members are automatically added when a challenge starts
- **Auto-Join New Members**: New members who join during a challenge are automatically added
- **Automatic Tracking**: Tracks invite counts automatically when new members join
- **Real-time Leaderboard**: View current rankings during the challenge
- **Winner Determination**: Automatically determines top 3 winners when challenge ends
- **Persistent Data**: Challenge data is saved to `invite_challenge.json`

## Commands

### Admin Commands (Require "Manage Server" permission)

#### `/invite create`
Creates a new invite challenge and automatically adds all existing members.
- **Duration**: Number of days the challenge will run (default: 7)
- **Prize**: Description of the prize (default: "Special Role")

#### `/invite end`
Ends the current active challenge and determines winners.

#### `/invite status`
Shows detailed information about the current challenge.

### User Commands (Available to all members)

#### `/leaderboard`
View the current leaderboard for the active challenge.

#### `/joinchallenge`
Join the current active invite challenge (if not already auto-joined).

#### `/invite join`
Alternative way to join a challenge (admin command but works for users too).

## How It Works

1. **Challenge Creation**: An admin creates a challenge with `/invite create`
2. **Auto-Join**: All existing members are automatically added to the challenge
3. **New Member Auto-Join**: New members who join during the challenge are automatically added
4. **Tracking**: The bot automatically tracks invite counts when new members join
5. **Leaderboard**: Members can check rankings with `/leaderboard`
6. **Ending**: Admin ends the challenge with `/invite end` to determine winners

## Important Notes

- Only one challenge can be active per server at a time
- **Everyone is automatically participating** - no need to manually join
- New members who join during a challenge are automatically added
- Invite counts are calculated as the difference between current invites and invites when the user joined the challenge
- The system tracks the top 3 winners
- Challenge data persists across bot restarts
- The bot needs "Manage Server" permission to track invites

## Example Usage

1. Admin creates challenge: `/invite create duration:7 prize:"VIP Role for 1 month"`
2. All members are automatically added
3. Members check rankings: `/leaderboard`
4. Admin ends challenge: `/invite end`

## Data Storage

Challenge data is stored in `invite_challenge.json` with the following structure:

```json
{
  "challenge_id": {
    "id": "challenge_id",
    "guild_id": 123456789,
    "start_time": 1234567890,
    "end_time": 1234567890,
    "duration_days": 7,
    "prize": "VIP Role",
    "active": true,
    "participants": {
      "user_id": {
        "joined_time": 1234567890,
        "current_invites": 5
      }
    },
    "invites_before": {
      "user_id": 3
    },
    "winners": [],
    "final_scores": {}
  }
}
```

## Permissions Required

- **Bot Permissions**: 
  - Manage Server (to track invites)
  - Send Messages
  - Embed Links
  - Use Slash Commands

- **User Permissions**:
  - Regular members can view leaderboards
  - Server managers can create, end, and manage challenges 