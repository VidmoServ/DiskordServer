# bot/cogs/reports.py

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import datetime
from typing import Dict, Any

from config import DATA_DIR


REPORTS_FILE = f"{DATA_DIR}/reports.json"


# --- PLIK DANYCH ---

def ensure_reports_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(REPORTS_FILE):
        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)


def load_reports() -> Dict[str, Dict[str, Any]]:
    ensure_reports_file()
    try:
        with open(REPORTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_reports(data: Dict[str, Dict[str, Any]]):
    with open(REPORTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# --- MODAL ---

class ReportModal(discord.ui.Modal, title="📩 Zgłoszenie"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    temat = discord.ui.TextInput(label="Temat", placeholder="Np. skarga, błąd, propozycja")
    opis = discord.ui.TextInput(label="Opis", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.create_report(interaction, str(self.temat), str(self.opis))


# --- COG ---

class Reports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reports = load_reports()

    # --- TWORZENIE ZGŁOSZENIA ---

    async def create_report(self, interaction: discord.Interaction, temat: str, opis: str):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("Błąd: brak gildii.", ephemeral=True)

        # Tworzymy ID zgłoszenia
        report_id = str(len(self.reports) + 1)

        # Tworzymy wątek
        channel = discord.utils.get(guild.text_channels, name="zgloszenia")
        if channel is None:
            return await interaction.response.send_message(
                "❌ Brak kanału #zgloszenia.",
                ephemeral=True
            )

        thread = await channel.create_thread(
            name=f"Zgłoszenie #{report_id} — {interaction.user.display_name}",
            auto_archive_duration=1440
        )

        # Zapis do bazy
        self.reports[report_id] = {
            "user_id": interaction.user.id,
            "temat": temat,
            "opis": opis,
            "status": "otwarte",
            "thread_id": thread.id,
            "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        save_reports(self.reports)

        # Wiadomość w wątku
        embed = discord.Embed(
            title=f"📩 Zgłoszenie #{report_id}",
            color=discord.Color.orange()
        )
        embed.add_field(name="Temat", value=temat, inline=False)
        embed.add_field(name="Opis", value=opis, inline=False)
        embed.add_field(name="Użytkownik", value=interaction.user.mention)
        embed.set_footer(text="Administracja odpowie tak szybko, jak to możliwe.")

        await thread.send(embed=embed)

        # Potwierdzenie dla użytkownika
        await interaction.response.send_message(
            f"✔️ Twoje zgłoszenie zostało utworzone! Sprawdź wątek: {thread.mention}",
            ephemeral=True
        )

        # Logi
        log_channel = discord.utils.get(guild.text_channels, name="logi")
        if log_channel:
            await log_channel.send(
                f"📝 **Nowe zgłoszenie #{report_id}** od {interaction.user.mention} w {thread.mention}"
            )

    # --- KOMENDY ---

    @app_commands.command(name="zgloszenie", description="Otwiera formularz zgłoszenia.")
    async def zgloszenie(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ReportModal(self))

    @app_commands.command(name="zgloszenia", description="Lista zgłoszeń (admin).")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def lista(self, interaction: discord.Interaction):
        if not self.reports:
            return await interaction.response.send_message("📭 Brak zgłoszeń.")

        text = ""
        for rid, data in self.reports.items():
            text += f"**#{rid}** — {data['temat']} — {data['status']}\n"

        embed = discord.Embed(
            title="📜 Lista zgłoszeń",
            description=text,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="zamknij-zgloszenie", description="Zamyka zgłoszenie (admin).")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def zamknij(self, interaction: discord.Interaction, id: int):
        rid = str(id)

        if rid not in self.reports:
            return await interaction.response.send_message("❌ Nie ma takiego zgłoszenia.", ephemeral=True)

        data = self.reports[rid]
        thread = interaction.guild.get_thread(data["thread_id"])

        if thread:
            await thread.send("🔒 Zgłoszenie zostało zamknięte przez administrację.")
            await thread.edit(archived=True, locked=True)

        self.reports[rid]["status"] = "zamknięte"
        save_reports(self.reports)

        await interaction.response.send_message(f"✔️ Zamknięto zgłoszenie #{rid}.")

        # Logi
        log_channel = discord.utils.get(interaction.guild.text_channels, name="logi")
        if log_channel:
            await log_channel.send(
                f"🔒 **Zgłoszenie #{rid} zamknięte** przez {interaction.user.mention}"
            )


async def setup(bot):
    await bot.add_cog(Reports(bot))