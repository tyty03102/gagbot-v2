import discord
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

class InviteChallenge:
    def __init__(self, data_file: str = 'invite_challenge.json'):
        self.data_file = data_file
        self.challenges = self.load_challenges()
        
    def load_challenges(self) -> Dict:
        """Load challenge data from file."""
        try:
            with open(self.data_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logging.error(f"Error loading invite challenges: {e}")
            return {}
    
    def save_challenges(self):
        """Save challenge data to file."""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.challenges, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving invite challenges: {e}")
    
    def create_challenge(self, guild_id: int, duration_days: int = 7, prize: str = "Special Role") -> Dict:
        """Create a new invite challenge."""
        challenge_id = str(int(time.time()))
        end_time = int(time.time()) + (duration_days * 24 * 60 * 60)
        
        challenge = {
            "id": challenge_id,
            "guild_id": guild_id,
            "start_time": int(time.time()),
            "end_time": end_time,
            "duration_days": duration_days,
            "prize": prize,
            "active": True,
            "participants": {},
            "invites_before": {},
            "winners": []
        }
        
        self.challenges[challenge_id] = challenge
        self.save_challenges()
        return challenge
    
    def end_challenge(self, challenge_id: str) -> Optional[Dict]:
        """End a challenge and determine winners."""
        if challenge_id not in self.challenges:
            return None
        
        challenge = self.challenges[challenge_id]
        challenge["active"] = False
        
        # Calculate final scores
        final_scores = {}
        for user_id, data in challenge["participants"].items():
            current_invites = data.get("current_invites", 0)
            final_scores[user_id] = current_invites
        
        # Find winners (top 3)
        sorted_scores = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
        challenge["winners"] = [user_id for user_id, score in sorted_scores[:3] if score > 0]
        challenge["final_scores"] = final_scores
        
        self.save_challenges()
        return challenge
    
    def get_active_challenge(self, guild_id: int) -> Optional[Dict]:
        """Get the active challenge for a guild."""
        for challenge in self.challenges.values():
            if (challenge["guild_id"] == guild_id and 
                challenge["active"] and 
                challenge["end_time"] > int(time.time())):
                return challenge
        return None
    
    def get_challenge_leaderboard(self, challenge_id: str) -> List[tuple]:
        """Get the current leaderboard for a challenge."""
        if challenge_id not in self.challenges:
            return []
        
        challenge = self.challenges[challenge_id]
        leaderboard = []
        
        for user_id, data in challenge["participants"].items():
            current_invites = data.get("current_invites", 0)
            leaderboard.append((user_id, current_invites))
        
        # Sort by invite count (descending)
        leaderboard.sort(key=lambda x: x[1], reverse=True)
        return leaderboard
    
    def update_participant_invites(self, challenge_id: str, user_id: int, current_invites: int):
        """Update a participant's invite count."""
        if challenge_id not in self.challenges:
            return
        
        challenge = self.challenges[challenge_id]
        
        if str(user_id) not in challenge["participants"]:
            challenge["participants"][str(user_id)] = {
                "joined_time": int(time.time()),
                "current_invites": current_invites
            }
        else:
            challenge["participants"][str(user_id)]["current_invites"] = current_invites
        
        self.save_challenges()
    
    async def get_user_invite_count(self, guild, user_id: int) -> int:
        """Get the current invite count for a user."""
        try:
            invites = await guild.invites()
            total_invites = 0
            for inv in invites:
                if inv.inviter and inv.inviter.id == user_id:
                    total_invites += inv.uses
            return total_invites
        except Exception as e:
            logging.error(f"Error getting invite count for user {user_id}: {e}")
            return 0
    
    def format_time_remaining(self, end_time: int) -> str:
        """Format the time remaining in a human-readable format."""
        remaining = end_time - int(time.time())
        if remaining <= 0:
            return "Ended"
        
        days = remaining // (24 * 60 * 60)
        hours = (remaining % (24 * 60 * 60)) // (60 * 60)
        minutes = (remaining % (60 * 60)) // 60
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    def format_leaderboard_embed(self, challenge: Dict, guild) -> discord.Embed:
        """Create an embed for the challenge leaderboard."""
        embed = discord.Embed(
            title="🏆 Invite Challenge Leaderboard",
            description=f"**Prize:** {challenge['prize']}\n"
                       f"**Time Remaining:** {self.format_time_remaining(challenge['end_time'])}",
            color=discord.Color.gold()
        )
        
        leaderboard = self.get_challenge_leaderboard(challenge["id"])
        
        if not leaderboard:
            embed.add_field(
                name="No Participants",
                value="No one has joined the challenge yet!",
                inline=False
            )
        else:
            leaderboard_text = ""
            for i, (user_id, invites) in enumerate(leaderboard[:10], 1):
                try:
                    member = guild.get_member(int(user_id))
                    username = member.display_name if member else f"User {user_id}"
                    
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                    leaderboard_text += f"{medal} **{username}** - {invites} invites\n"
                except Exception as e:
                    logging.error(f"Error formatting leaderboard entry: {e}")
                    continue
            
            embed.add_field(
                name="Current Rankings",
                value=leaderboard_text or "No participants",
                inline=False
            )
        
        embed.set_footer(text=f"Challenge ID: {challenge['id']}")
        return embed
    
    async def auto_join_all_members(self, challenge_id: str, guild):
        """Automatically add all existing guild members to the challenge."""
        if challenge_id not in self.challenges:
            return
        
        challenge = self.challenges[challenge_id]
        added_count = 0
        
        for member in guild.members:
            if not member.bot:  # Skip bots
                try:
                    current_invites = await self.get_user_invite_count(guild, member.id)
                    self.update_participant_invites(challenge_id, member.id, current_invites)
                    added_count += 1
                except Exception as e:
                    logging.error(f"Error auto-joining member {member.id}: {e}")
        
        logging.info(f"Auto-joined {added_count} members to challenge {challenge_id}")
        return added_count
    
    async def auto_join_new_member(self, challenge_id: str, guild, member_id: int):
        """Automatically add a new member to the active challenge."""
        if challenge_id not in self.challenges:
            return
        
        try:
            current_invites = await self.get_user_invite_count(guild, member_id)
            self.update_participant_invites(challenge_id, member_id, current_invites)
            logging.info(f"Auto-joined new member {member_id} to challenge {challenge_id}")
        except Exception as e:
            logging.error(f"Error auto-joining new member {member_id}: {e}")

# Global instance
invite_challenge = InviteChallenge() 