# bot/cogs/antyspam.py

import discord
from discord.ext import commands
from discord import app_commands
import time
from typing import Dict, List


class AntiSpam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Konfiguracja antyspamu
        self.message_limit = 99999        # ile wiadomości...
        self.time_window = 999         # ...w ilu sekundach
        self.timeout_minutes = 1       # timeout za spam

        # Dane użytkowników
        self.user_messages: Dict[int, List[float]] = {}  # user_id → timestamps
        self.last_message: Dict[int, str] = {}           # user_id → last message

    # --- FUNKCJE POMOCNICZE ---

    def add_message(self, user_id: int):
        now = time.time()
        if user_id not in self.user_messages:
            self.user_messages[user_id] = []
        self.user_messages[user_id].append(now)

        # Usuwamy stare wiadomości spoza okna czasowego
        self.user_messages[user_id] = [
            t for t in self.user_messages[user_id]
            if now - t <= self.time_window
        ]

    def is_spam(self, user_id: int, content: str):
        msgs = self.user_messages.get(user_id, [])

        # 1. Zbyt szybkie pisanie
        if len(msgs) >= self.message_limit:
            return True, "Piszesz zbyt szybko."

        # 2. Powtarzanie tej samej wiadomości
        if self.last_message.get(user_id) == content:
            return True, "Powtarzasz tę samą wiadomość."

        # 3. CAPS LOCK spam
        if len(content) > 8 and content.isupper():
            return True, "Używasz zbyt dużo wielkich liter."

        # 4. Masowe pingowanie
        if content.count("@") >= 3:
            return True, "Pingujesz zbyt wiele osób."

        return False, ""

    async def punish(self, message: discord.Message, reason: str):
        user = message.author

        # Timeout
        try:
            await user.timeout_for(
                duration=discord.utils.utcnow() + discord.timedelta(minutes=self.timeout_minutes),
                reason=f"Antyspam: {reason}"
            )
        except:
            pass

        # Wiadomość na kanał
        try:
            await message.channel.send(
                f"⚠️ {user.mention}, wykryto spam: **{reason}**\n"
                f"Nałożono timeout na {self.timeout_minutes} minut."
            )
        except:
            pass

        # Logi (opcjonalnie)
        log_channel = discord.utils.get(message.guild.text_channels, name="logi")
        if log_channel:
            await log_channel.send(
                f"🛑 **Antyspam**\n"
                f"Użytkownik: {user.mention}\n"
                f"Powód: {reason}\n"
                f"Kanał: {message.channel.mention}"
            )

    # --- EVENT: WYKRYWANIE SPAMU ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        user_id = message.author.id
        content = message.content

        # Rejestrujemy wiadomość
        self.add_message(user_id)

        # Sprawdzamy spam
        spam, reason = self.is_spam(user_id, content)
        self.last_message[user_id] = content

        if spam:
            await self.punish(message, reason)
            try:
                await message.delete()
            except:
                pass

    # --- KOMENDY ADMINISTRACYJNE ---

    @app_commands.command(name="antyspam-info", description="Pokazuje ustawienia antyspamu.")
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ Antyspam — ustawienia",
            color=discord.Color.orange()
        )
        embed.add_field(name="Limit wiadomości", value=self.message_limit)
        embed.add_field(name="Okno czasowe (s)", value=self.time_window)
        embed.add_field(name="Timeout (min)", value=self.timeout_minutes)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="antyspam-ustaw", description="Ustawia parametry antyspamu.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ustaw(self, interaction: discord.Interaction, limit: int, sekundy: int, timeout: int):
        self.message_limit = limit
        self.time_window = sekundy
        self.timeout_minutes = timeout

        await interaction.response.send_message(
            f"✔️ Ustawiono antyspam:\n"
            f"• Limit wiadomości: {limit}\n"
            f"• Okno czasowe: {sekundy}s\n"
            f"• Timeout: {timeout} min"
        )

    @app_commands.command(name="antyspam-wylacz", description="Wyłącza antyspam.")
    @app_commands.checks.has_permissions(administrator=True)
    async def wylacz(self, interaction: discord.Interaction):
        self.message_limit = 9999
        self.time_window = 9999
        await interaction.response.send_message("🛑 Antyspam został wyłączony.")


async def setup(bot):
    await bot.add_cog(AntiSpam(bot))