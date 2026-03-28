# bot/cogs/economy.py
import discord
from discord.ext import commands, tasks
from discord import app_commands # pyright: ignore[reportAttributeAccessIssue]
import json
import os
import datetime
import random
from typing import Any, Dict

from config import ECONOMY_FILE, DATA_DIR


def ensure_data_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(ECONOMY_FILE):
        with open(ECONOMY_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=4)


def load_economy() -> Dict[str, Dict[str, Any]]:
    ensure_data_files()
    try:
        with open(ECONOMY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_economy(data: Dict[str, Dict[str, Any]]) -> None:
    with open(ECONOMY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


class Economy(commands.Cog): # pyright: ignore[reportMissingTypeArgument]
    def __init__(self, bot: commands.Bot) -> None: # type: ignore
        self.bot = bot
        self.economy_data: Dict[str, Dict[str, Any]] = load_economy()
        self.check_temporary_roles.start()

    def get_user(self, user_id: int) -> Dict[str, Any]:
        uid = str(user_id)
        if uid not in self.economy_data:
            self.economy_data[uid] = {
                "pieniadze": 0,
                "ekwipunek": [],
                "role_expiry": None,
                "last_daily": 0,
            }
        return self.economy_data[uid]

    def save(self) -> None:
        save_economy(self.economy_data)

    @app_commands.command(name="hajs", description="Sprawdź swoje saldo") # pyright: ignore[reportUntypedFunctionDecorator]
    async def hajs(self, interaction: discord.Interaction): # pyright: ignore[reportUnknownParameterType, reportAttributeAccessIssue]
        u = self.get_user(interaction.user.id)
        await interaction.response.send_message(
            f"💰 Twoje saldo: **{u['pieniadze']}$**"
        )

    @app_commands.command(name="pracuj", description="Zarabiaj pieniądze pracując") # pyright: ignore[reportUntypedFunctionDecorator]
    async def pracuj(self, interaction: discord.Interaction): # type: ignore
        u = self.get_user(interaction.user.id)
        z = random.randint(50, 150)
        u['pieniadze'] += z
        self.save()
        await interaction.response.send_message(f"🛠️ Zarobiłeś **{z}$**!")

    @app_commands.command(name="daily", description="Odbierz swój dzienny bonus pieniężny") # type: ignore
    async def daily(self, interaction: discord.Interaction): # pyright: ignore[reportAttributeAccessIssue, reportUnknownParameterType]
        u = self.get_user(interaction.user.id)
        last_daily = u.get("last_daily", 0)
        now = datetime.datetime.now().timestamp()

        if now - last_daily < 86400:
            remaining = int(86400 - (now - last_daily))
            hours, remainder = divmod(remaining, 3600)
            minutes, _ = divmod(remainder, 60)
            return await interaction.response.send_message(
                f"⏳ Możesz odebrać daily za: **{hours}h {minutes}m**",
                ephemeral=True
            )

        bonus = 500
        u['pieniadze'] += bonus
        u['last_daily'] = now
        self.save()
        await interaction.response.send_message(
            f"🎁 Odebrałeś swój dzienny bonus: **{bonus}$**!"
        )

    @app_commands.command(name="sklep", description="Kup przedmioty lub role") # pyright: ignore[reportUntypedFunctionDecorator]
    async def sklep(self, interaction: discord.Interaction): # pyright: ignore[reportAttributeAccessIssue, reportUnknownParameterType]
        embed = discord.Embed(
            title="🛒 Sklep Serwerowy",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="1. Rola 'Ultra Legenda' (30 dni)",
            value="Cena: **5000$**\nUżyj `/kup 1`",
            inline=False
        )
        embed.add_field(
            name="2. Losowy Prezent",
            value="Cena: **1000$**\nUżyj `/kup 2`",
            inline=False
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="kup", description="Kupuje przedmiot ze sklepu") # pyright: ignore[reportUntypedFunctionDecorator]
    async def kup(self, interaction: discord.Interaction, przedmiot_id: int): # type: ignore
        u = self.get_user(interaction.user.id)

        if przedmiot_id == 1:
            cena = 5000
            if u['pieniadze'] < cena:
                return await interaction.response.send_message(
                    "❌ Nie masz wystarczająco pieniędzy na tę rolę!",
                    ephemeral=True
                )

            u['pieniadze'] -= cena
            u['role_expiry'] = (
                datetime.datetime.now() + datetime.timedelta(days=30)
            ).timestamp()
            self.save()
            await interaction.response.send_message(
                "🎉 Kupiłeś rolę 'Ultra Legenda' na 30 dni! Ciesz się przywilejami tej roli!",
                ephemeral=True
            )

            for guild in self.bot.guilds:
                member = guild.get_member(interaction.user.id)
                if member:
                    role = discord.utils.get(guild.roles, name="Ultra Legenda")
                    if role:
                        try:
                            await member.add_roles(role)
                        except discord.Forbidden:
                            print(
                                f"❌ BŁĄD: Bot ma za niską rolę w hierarchii, aby nadać 'Ultra Legenda' użytkownikowi {member.name}!"
                            )
        elif przedmiot_id == 2:
            cena = 1000
            if u['pieniadze'] < cena:
                return await interaction.response.send_message(
                    "❌ Nie masz wystarczająco pieniędzy na ten prezent!",
                    ephemeral=True
                )

            u['pieniadze'] -= cena
            self.save()
            await interaction.response.send_message(
                "🎁 Kupiłeś losowy prezent! Otwieram...",
                ephemeral=True
            )
            await asyncio.sleep(2) # type: ignore

            prezenty = [
                "1000$",
                "5000$",
                "Ultra Legenda (7 dni)",
                "Ultra Legenda (14 dni)",
                "Ultra Legenda (30 dni)"
            ]
            wygrana = random.choice(prezenty)

            if wygrana.endswith("$"):
                kwota = int(wygrana.replace("$", ""))
                u['pieniadze'] += kwota
                self.save()
                await interaction.followup.send(
                    f"🎉 Gratulacje! Wygrałeś: **{wygrana}**! Dodałem {kwota}$ do twojego konta.",
                    ephemeral=True
                )
            else:
                days = 7
                if "14" in wygrana:
                    days = 14
                elif "30" in wygrana:
                    days = 30

                u['role_expiry'] = (
                    datetime.datetime.now() + datetime.timedelta(days=days)
                ).timestamp()
                self.save()

                added_role = False
                for guild in self.bot.guilds:
                    member = guild.get_member(interaction.user.id)
                    if member:
                        role = discord.utils.get(guild.roles, name="Ultra Legenda")
                        if role:
                            try:
                                await member.add_roles(role)
                                added_role = True
                            except discord.Forbidden:
                                pass

                if added_role:
                    await interaction.followup.send(
                        f"🎉 Gratulacje! Wygrałeś: **{wygrana}**, otrzymałeś rolę Ultra Legenda na {days} dni!",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"🎉 Gratulacje! Wygrałeś: **{wygrana}**! Niestety nie mogę przypisać roli (brak roli lub brak uprawnień).",
                        ephemeral=True
                    )
        else:
            await interaction.response.send_message(
                "❌ Nieprawidłowy numer przedmiotu!",
                ephemeral=True
            )

    @tasks.loop(minutes=1)
    async def check_temporary_roles(self):
        now = datetime.datetime.now().timestamp()
        for uid, data in self.economy_data.items():
            expiry = data.get('role_expiry')
            if expiry and now > expiry:
                for guild in self.bot.guilds:
                    member = guild.get_member(int(uid))
                    if member:
                        role = discord.utils.get(guild.roles, name="Ultra Legenda")
                        if role and role in member.roles:
                            await member.remove_roles(role)
                data['role_expiry'] = None
                self.save()

    @check_temporary_roles.before_loop # pyright: ignore[reportArgumentType]
    async def before_check_temporary_roles(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot): # pyright: ignore[reportMissingTypeArgument, reportUnknownParameterType]
    await bot.add_cog(Economy(bot)) # pyright: ignore[reportGeneralTypeIssues]