# bot/cogs/xp.py

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
import time
from typing import Dict, Any

from config import DATA_DIR


XP_FILE = f"{DATA_DIR}/xp.json"


# --- PLIK DANYCH ---

def ensure_xp_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(XP_FILE):
        with open(XP_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)


def load_xp() -> Dict[str, Dict[str, Any]]:
    ensure_xp_file()
    try:
        with open(XP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_xp(data: Dict[str, Dict[str, Any]]):
    with open(XP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# --- COG ---

class XPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_xp()
        self.cooldowns = {}  # user_id → timestamp

    # --- FUNKCJE XP ---

    def get_user(self, user_id: int):
        uid = str(user_id)
        if uid not in self.data:
            self.data[uid] = {"xp": 0, "level": 1}
        return self.data[uid]

    def xp_needed(self, level: int) -> int:
        return 5 * (level ** 2) + 50 * level + 100

    def add_xp(self, user_id: int, amount: int):
        user = self.get_user(user_id)
        user["xp"] += amount

        # Sprawdzanie level-up
        needed = self.xp_needed(user["level"])
        leveled_up = False

        while user["xp"] >= needed:
            user["xp"] -= needed
            user["level"] += 1
            needed = self.xp_needed(user["level"])
            leveled_up = True

        save_xp(self.data)
        return leveled_up, user["level"]

    # --- EVENT: XP ZA WIADOMOŚCI ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        user_id = message.author.id
        now = time.time()

        # Cooldown 30 sekund
        if user_id in self.cooldowns and now - self.cooldowns[user_id] < 30:
            return

        self.cooldowns[user_id] = now

        xp_gain = random.randint(5, 15)
        leveled_up, new_level = self.add_xp(user_id, xp_gain)

        if leveled_up:
            try:
                await message.channel.send(
                    f"🎉 **{message.author.mention} awansował na poziom {new_level}!**"
                )
            except discord.Forbidden:
                pass

    # --- KOMENDY ---

    @app_commands.command(name="xp", description="Pokazuje twój XP i poziom.")
    async def xp(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        data = self.get_user(user.id)

        embed = discord.Embed(
            title=f"📊 Statystyki {user.display_name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Poziom", value=data["level"])
        embed.add_field(name="XP", value=data["xp"])
        embed.add_field(name="XP do następnego poziomu", value=self.xp_needed(data["level"]))

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ranking", description="Pokazuje top 10 użytkowników.")
    async def ranking(self, interaction: discord.Interaction):
        sorted_users = sorted(
            self.data.items(),
            key=lambda x: (x[1]["level"], x[1]["xp"]),
            reverse=True
        )

        text = ""
        for i, (uid, stats) in enumerate(sorted_users[:10], start=1):
            user = interaction.guild.get_member(int(uid))
            name = user.display_name if user else f"Użytkownik {uid}"
            text += f"**{i}. {name}** — Poziom {stats['level']} ({stats['xp']} XP)\n"

        embed = discord.Embed(
            title="🏆 Ranking XP",
            description=text,
            color=discord.Color.gold()
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ustaw-xp", description="Ustawia XP użytkownika (admin).")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_xp(self, interaction: discord.Interaction, user: discord.Member, xp: int):
        data = self.get_user(user.id)
        data["xp"] = xp
        save_xp(self.data)
        await interaction.response.send_message(f"✔️ Ustawiono XP użytkownika {user.display_name} na {xp}.")

    @app_commands.command(name="ustaw-level", description="Ustawia poziom użytkownika (admin).")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level(self, interaction: discord.Interaction, user: discord.Member, level: int):
        data = self.get_user(user.id)
        data["level"] = level
        save_xp(self.data)
        await interaction.response.send_message(f"✔️ Ustawiono poziom użytkownika {user.display_name} na {level}.")


async def setup(bot):
    await bot.add_cog(XPSystem(bot))