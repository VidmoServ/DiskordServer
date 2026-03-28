# bot/cogs/moderation.py

import discord
from discord.ext import commands
from discord import app_commands
import datetime



class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.warns = {}  # user_id → list of warnings


    # --- POMOCNICZE ---

    def add_warn(self, user_id: int, reason: str):
        if user_id not in self.warns:
            self.warns[user_id] = []
        self.warns[user_id].append({
            "reason": reason,
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    })

    # --- KOMENDY ---


    @discord.app_commands.command(name="ban", description="Banuje użytkownika.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Brak powodu"):
        await user.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Zbanowano **{user}**. Powód: {reason}")

    @discord.app_commands.command(name="kick", description="Wyrzuca użytkownika z serwera.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Brak powodu"):
        await user.kick(reason=reason)
        await interaction.response.send_message(f"👢 Wyrzucono **{user}**. Powód: {reason}")

    @app_commands.command(name="clear", description="Czyści wiadomości z kanału.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"🧹 Usunięto **{amount}** wiadomości.", ephemeral=True)

    @app_commands.command(name="mute", description="Wycisza użytkownika.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, user: discord.Member, minutes: int, reason: str = "Brak powodu"):
        duration = datetime.timedelta(minutes=minutes)
        await user.timeout_for(duration, reason=reason)
        await interaction.response.send_message(
            f"🔇 Wyciszono **{user}** na {minutes} minut. Powód: {reason}"
        )

    @app_commands.command(name="unmute", description="Odcisza użytkownika.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, user: discord.Member):
        await user.timeout_until(None)
        await interaction.response.send_message(f"🔊 Odciszono **{user}**.")

    @app_commands.command(name="warn", description="Nadaje ostrzeżenie użytkownikowi.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        self.add_warn(user.id, reason)
        await interaction.response.send_message(
            f"⚠️ Ostrzeżenie dla **{user}**. Powód: {reason}"
        )

    @app_commands.command(name="warny", description="Pokazuje ostrzeżenia użytkownika.")
    async def warny(self, interaction: discord.Interaction, user: discord.Member):
        warns = self.warns.get(user.id, [])
        if not warns:
            return await interaction.response.send_message(f"✔️ **{user}** nie ma żadnych ostrzeżeń.")

        text = "\n".join([f"{i+1}. {w['reason']} ({w['time']})" for i, w in enumerate(warns)])
        await interaction.response.send_message(f"⚠️ Ostrzeżenia **{user}**:\n{text}")

    @app_commands.command(name="usun-warny", description="Usuwa wszystkie ostrzeżenia użytkownika.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def usun_warny(self, interaction: discord.Interaction, user: discord.Member):
        self.warns[user.id] = []
        await interaction.response.send_message(f"🗑️ Usunięto wszystkie ostrzeżenia użytkownika **{user}**.")


async def setup(bot):
    await bot.add_cog(Moderation(bot))