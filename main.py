import discord
from discord.ext import commands
import os
TOKEN = os.getenv("TOKEN")




# --- INTENTS ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True
intents.presences = True



class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        await self.load_extension("cogs.economy")
        await self.load_extension("cogs.music")
        await self.load_extension("cogs.moderation")
        await self.load_extension("cogs.reports")
        await self.load_extension("cogs.tiktok")
        await self.load_extension("cogs.xp")
        await self.load_extension("cogs.antyspam")
        GUILD_ID = 1426563806213177508
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))

    async def on_ready(self):
        print(f"Zalogowano jako {self.user} (ID: {self.user.id})")
        print("------")
        print("Bot jest gotowy do pracy!")
        print("Śmieszek Załadowany!")
bot = MyBot()
if __name__ == "__main__":
    bot.run(TOKEN)