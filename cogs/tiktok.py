# Bot V2/cogs/tiktok.py
import discord
from discord.ext import commands, tasks
import discord.app_commands as app_commands

import aiohttp
import json
import os
import re
import logging
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from aiohttp import web

import config

# ==========================
# ŚCIEŻKI I PLIKI
# ==========================
BASE_DIR = Path(__file__).resolve().parent.parent  # Bot V2\
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "tiktok_data.json"
LOG_FILE = BASE_DIR / "tiktok.log"

# ==========================
# LOGOWANIE
# ==========================
logger = logging.getLogger("tiktok")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

# ==========================
# UI: Admin pagination view
# ==========================
class AdminPageView(discord.ui.View):
    def __init__(self, cog, page: int, per_page: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.page = page
        self.per_page = per_page

    @discord.ui.button(label="◀️ Poprzednia", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != config.ADMIN_ID:
            await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
            return
        if self.page <= 1:
            await interaction.response.defer()
            return
        self.page -= 1
        embed = self.cog.build_admin_page_embed(self.page, self.per_page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶️ Następna", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != config.ADMIN_ID:
            await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
            return
        max_page = self.cog.get_admin_max_page(self.per_page)
        if self.page >= max_page:
            await interaction.response.defer()
            return
        self.page += 1
        embed = self.cog.build_admin_page_embed(self.page, self.per_page)
        await interaction.response.edit_message(embed=embed, view=self)

# ==========================
# UI: User notification view (Unsub / Mute)
# ==========================
class TikTokView(discord.ui.View):
    def __init__(self, cog, username: str, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.username = username
        self.user_id = user_id

    @discord.ui.button(label="❌ Unsub", style=discord.ButtonStyle.danger)
    async def unsub_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("To nie jest Twoje powiadomienie.", ephemeral=True)
            return
        await self.cog.unsubscribe_user(self.username, self.user_id)
        await interaction.response.send_message(f"Przestałeś subskrybować **@{self.username}**.", ephemeral=True)

    @discord.ui.button(label="🔕 Mute 24h", style=discord.ButtonStyle.secondary)
    async def mute_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("To nie jest Twoje powiadomienie.", ephemeral=True)
            return
        await self.cog.mute_user(self.username, self.user_id)
        await interaction.response.send_message(f"Wyciszono powiadomienia z **@{self.username}** na 24h.", ephemeral=True)

# ==========================
# GŁÓWNY COG
# ==========================
class TikTokCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tiktok_data_file = DATA_FILE
        self.tiktok_data: dict = {}
        self.load_tiktok_data()

        # cache HTML: {username: (html, timestamp)}
        self.html_cache: dict[str, tuple[str, datetime]] = {}

        # start loops
        self.check_tiktok_updates.start()
        self.cleanup_dead_subs.start()

        # dashboard
        self.web_app = web.Application()
        self.web_app.add_routes([
            web.get("/", self.handle_dashboard),
            web.get("/action", self.handle_dashboard_action),
        ])
        self.runner = web.AppRunner(self.web_app)
        bot.loop.create_task(self.start_dashboard())

        logger.info("TikTokCog initialized.")

    # ==========================
    # POMOCNICZE – LOGI DO KANAŁU
    # ==========================
    async def send_log_channel(self, message: str, error: bool = False):
        channel_id = config.ERROR_CHANNEL_ID if error else config.LOG_CHANNEL_ID
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        try:
            await channel.send(message)
        except Exception as e:
            logger.error(f"Error sending log to channel: {e}")

    # ==========================
    # PLIK JSON
    # ==========================
    def load_tiktok_data(self):
        if self.tiktok_data_file.exists():
            try:
                with open(self.tiktok_data_file, "r", encoding="utf-8") as f:
                    self.tiktok_data = json.load(f)
            except Exception as e:
                logger.error(f"Error loading tiktok_data.json: {e}")
                self.tiktok_data = {}
        else:
            self.tiktok_data = {}
        logger.info("TikTok data loaded.")

    def save_tiktok_data(self):
        try:
            with open(self.tiktok_data_file, "w", encoding="utf-8") as f:
                json.dump(self.tiktok_data, f, ensure_ascii=False, indent=2)
            logger.info("TikTok data saved.")
        except Exception as e:
            logger.error(f"Error saving tiktok_data.json: {e}")

    # ==========================
    # SCRAPING + CACHE
    # ==========================
    async def fetch_html(self, url: str, cache_key: str | None = None):
        now = datetime.utcnow()
        if cache_key and cache_key in self.html_cache:
            html, ts = self.html_cache[cache_key]
            if now - ts < timedelta(minutes=5):
                return html

        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.google.com/"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=20) as resp:
                    if resp.status != 200:
                        logger.warning(f"Failed to fetch page {url}, status {resp.status}")
                        return None
                    html = await resp.text()
        except Exception as e:
            logger.error(f"Error fetching page {url}: {e}")
            return None

        if cache_key:
            self.html_cache[cache_key] = (html, now)
        return html

    # ==========================
    # API: próba pobrania przez zewnętrzne API (priorytet) + debug
    # ==========================
    async def get_tiktok_latest_via_api(self, username: str):
        if not getattr(config, "TIKTOK_API_ENABLED", False):
            return None

        api_key = getattr(config, "TIKTOK_API_KEY", "") or os.getenv("TIKTOK_API_KEY", "")
        api_url = getattr(config, "TIKTOK_API_URL", "").rstrip("/")
        if not api_key or not api_url:
            return None

        headers = {}
        auth_type = getattr(config, "TIKTOK_API_AUTH_TYPE", "Bearer")
        if auth_type.lower() == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers["x-api-key"] = api_key

        params = {"username": username}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers, params=params, timeout=20) as resp:
                    status = resp.status
                    text = await resp.text()

                    # Debug log surowej odpowiedzi
                    if getattr(config, "TIKTOK_API_DEBUG", False):
                        try:
                            debug_path = Path(BASE_DIR) / getattr(config, "TIKTOK_API_DEBUG_FILE", "tiktok_api_debug.log")
                            now = datetime.utcnow().isoformat()
                            with open(debug_path, "a", encoding="utf-8") as df:
                                df.write(f"--- {now} | username={username} | status={status} ---\n")
                                df.write(text + "\n\n")
                        except Exception as e:
                            logger.error(f"Failed to write API debug file: {e}\n{traceback.format_exc()}")

                    if status != 200:
                        logger.warning(f"API returned status {status} for {username}")
                        return None

                    try:
                        data = json.loads(text)
                    except Exception:
                        logger.error(f"API response not JSON for {username}")
                        return None
        except Exception as e:
            logger.error(f"API request error for {username}: {e}")
            return None

        try:
            # Dostosuj parsowanie do formatu Twojego providera
            videos = data.get("videos") or data.get("data") or []
            if not videos:
                return None
            latest = videos[0]
            return {
                "id": str(latest.get("id")),
                "url": latest.get("url") or f"https://www.tiktok.com/@{username}/video/{latest.get('id')}",
                "desc": latest.get("desc") or latest.get("description") or "",
                "cover": latest.get("cover") or latest.get("thumbnail") or None,
            }
        except Exception as e:
            logger.error(f"Error parsing API response for {username}: {e}")
            return None

    # ==========================
    # główna funkcja: najpierw API, potem scraping
    # ==========================
    async def get_tiktok_latest(self, username: str):
        api_result = await self.get_tiktok_latest_via_api(username)
        if api_result:
            return api_result

        url = f"https://www.tiktok.com/@{username}"
        html = await self.fetch_html(url, cache_key=username)
        if html is None:
            return None

        match = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', html)
        if not match:
            logger.warning(f"No SIGI_STATE script found for {username}")
            return None

        try:
            data = json.loads(match.group(1))
        except Exception as e:
            logger.error(f"Error parsing SIGI_STATE JSON for {username}: {e}")
            return None

        try:
            videos = list(data["ItemModule"].values())
            if not videos:
                logger.info(f"No videos found in ItemModule for {username}")
                return None
            latest = videos[0]
            vid_id = latest["id"]
            desc = latest.get("desc", "")
            video_url = f"https://www.tiktok.com/@{username}/video/{vid_id}"
            cover = None
            covers = latest.get("video", {}).get("cover", None)
            if isinstance(covers, str):
                cover = covers
            elif isinstance(covers, list) and covers:
                cover = covers[0]

            return {"id": vid_id, "url": video_url, "desc": desc, "cover": cover}
        except Exception as e:
            logger.error(f"Error extracting latest video for {username}: {e}")
            return None

    # ==========================
    # SUB / UNSUB / MUTE
    # ==========================
    async def unsubscribe_user(self, username: str, user_id: int):
        if username not in self.tiktok_data:
            return
        subs = self.tiktok_data[username].get("subscribers", [])
        if user_id in subs:
            subs.remove(user_id)
            self.tiktok_data[username]["subscribers"] = subs
        muted = self.tiktok_data[username].get("muted", {})
        if str(user_id) in muted:
            del muted[str(user_id)]
            self.tiktok_data[username]["muted"] = muted
        self.save_tiktok_data()
        logger.info(f"User {user_id} unsubscribed from {username}.")

    async def mute_user(self, username: str, user_id: int):
        if username not in self.tiktok_data:
            return
        muted = self.tiktok_data[username].get("muted", {})
        until = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        muted[str(user_id)] = until
        self.tiktok_data[username]["muted"] = muted
        self.save_tiktok_data()
        logger.info(f"User {user_id} muted {username} until {until}.")

    def is_muted(self, username: str, user_id: int) -> bool:
        if username not in self.tiktok_data:
            return False
        muted = self.tiktok_data[username].get("muted", {})
        ts = muted.get(str(user_id))
        if not ts:
            return False
        try:
            until = datetime.fromisoformat(ts)
        except Exception:
            return False
        return datetime.utcnow() < until

    # ==========================
    # LIMITY
    # ==========================
    def count_user_subs(self, user_id: int) -> int:
        count = 0
        for data in self.tiktok_data.values():
            if user_id in data.get("subscribers", []):
                count += 1
        return count

    def count_global_subs(self) -> int:
        return len(self.tiktok_data)

    # ==========================
    # KOMENDA /tiktok
    # ==========================
    @app_commands.command(name="tiktok", description="Subskrybuj TikTok po nazwie lub linku")
    @app_commands.describe(target="Nazwa użytkownika TikTok lub link do filmu")
    async def tiktok(self, interaction: discord.Interaction, target: str):
        await interaction.response.defer(ephemeral=True)
        username = None
        link_match = re.search(r"tiktok\.com/@([^/]+)/video/(\d+)", target)
        if link_match:
            username = link_match.group(1)
        else:
            username = target.strip().lstrip("@")

        if not username:
            await interaction.followup.send("Nie udało się rozpoznać użytkownika TikTok.")
            return

        user_subs = self.count_user_subs(interaction.user.id)
        if user_subs >= config.PREMIUM_LIMIT_PER_USER:
            await interaction.followup.send(f"Osiągnąłeś limit {config.PREMIUM_LIMIT_PER_USER} subskrypcji.")
            return

        global_subs = self.count_global_subs()
        if username not in self.tiktok_data and global_subs >= config.GLOBAL_LIMIT:
            await interaction.followup.send(f"Osiągnięto globalny limit {config.GLOBAL_LIMIT} subskrypcji.")
            return

        if username in self.tiktok_data:
            subs = self.tiktok_data[username].get("subscribers", [])
            if interaction.user.id not in subs:
                subs.append(interaction.user.id)
                self.tiktok_data[username]["subscribers"] = subs
                self.save_tiktok_data()
                await interaction.followup.send(f"Dodano Cię do subskrypcji **@{username}**.")
                logger.info(f"User {interaction.user.id} added to existing subscription {username}.")
            else:
                await interaction.followup.send(f"Już subskrybujesz **@{username}**.")
            return

        latest = await self.get_tiktok_latest(username)
        if latest is None:
            await interaction.followup.send(f"Nie udało się pobrać danych TikTok dla **@{username}**. Sprawdź nazwę lub link.")
            return

        self.tiktok_data[username] = {"last_video_id": latest["id"], "subscribers": [interaction.user.id], "muted": {}, "dead": False}
        self.save_tiktok_data()
        await interaction.followup.send(f"Subskrypcja **@{username}** została utworzona. Ostatni film: `{latest['id']}`.")
        logger.info(f"New subscription created for {username} by user {interaction.user.id}.")

    # ==========================
    # PĘTLA SPRAWDZAJĄCA
    # ==========================
    @tasks.loop(minutes=10)
    async def check_tiktok_updates(self):
        logger.info("Running TikTok update check...")
        for username, data in list(self.tiktok_data.items()):
            latest = await self.get_tiktok_latest(username)
            if latest is None:
                if not data.get("dead"):
                    data["dead"] = True
                    self.save_tiktok_data()
                    logger.info(f"Marked {username} as dead (no data).")
                continue

            if data.get("dead"):
                data["dead"] = False
                self.save_tiktok_data()

            last_id = data.get("last_video_id")
            if last_id != latest["id"]:
                logger.info(f"New video detected for {username}: {latest['id']}")
                self.tiktok_data[username]["last_video_id"] = latest["id"]
                self.save_tiktok_data()
                await self.notify_subscribers(username, latest)
            else:
                logger.info(f"No new video for {username} (last: {last_id}).")

    @check_tiktok_updates.before_loop
    async def before_check_tiktok_updates(self):
        await self.bot.wait_until_ready()
        logger.info("TikTok update loop started.")

    # ==========================
    # CZYSZCZENIE MARTWYCH
    # ==========================
    @tasks.loop(hours=24)
    async def cleanup_dead_subs(self):
        logger.info("Running dead subscriptions cleanup...")
        to_delete = []
        for username, data in self.tiktok_data.items():
            if data.get("dead"):
                to_delete.append(username)
        for username in to_delete:
            logger.info(f"Removing dead subscription {username}.")
            del self.tiktok_data[username]
        if to_delete:
            self.save_tiktok_data()

    @cleanup_dead_subs.before_loop
    async def before_cleanup_dead_subs(self):
        await self.bot.wait_until_ready()
        for cmd in self.bot.tree.walk_commands():
            print(cmd.name, cmd.parent)
        GUILD_ID = 1426563806213177508  # Twój serwer testowy
        await self.bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    # ==========================
    # POWIADOMIENIA
    # ==========================
    async def notify_subscribers(self, username: str, video_data: dict):
        url = video_data["url"]
        desc = video_data.get("desc", "")
        cover = video_data.get("cover")

        embed = discord.Embed(title=f"Nowy TikTok od @{username}", description=desc or "Nowy film!", color=discord.Color.magenta(), timestamp=datetime.utcnow())
        embed.add_field(name="Link", value=url, inline=False)
        embed.set_footer(text="TikTok notifier")
        if cover:
            embed.set_thumbnail(url=cover)

        for subscriber_id in self.tiktok_data[username].get("subscribers", []):
            if self.is_muted(username, subscriber_id):
                logger.info(f"User {subscriber_id} is muted for {username}, skipping notification.")
                continue
            user = self.bot.get_user(subscriber_id)
            if not user:
                logger.warning(f"Could not find user with ID {subscriber_id}")
                continue
            try:
                view = TikTokView(self, username, subscriber_id)
                await user.send(embed=embed, view=view)
                logger.info(f"Notification sent to {subscriber_id} for {username}.")
            except Exception as e:
                logger.error(f"Could not send notification to {subscriber_id}: {e}")
                await self.send_log_channel(f"Nie mogę wysłać powiadomienia do <@{subscriber_id}>: {e}", error=True)

    # ==========================
    # ADMIN – PAGINACJA I PANEL
    # ==========================
    async def is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == config.ADMIN_ID

    def get_admin_max_page(self, per_page: int) -> int:
        total = len(self.tiktok_data)
        if total == 0:
            return 1
        return (total - 1) // per_page + 1

    def build_admin_page_embed(self, page: int, per_page: int) -> discord.Embed:
        items = sorted(self.tiktok_data.items(), key=lambda x: x[0].lower())
        max_page = self.get_admin_max_page(per_page)
        page = max(1, min(page, max_page))
        start = (page - 1) * per_page
        end = start + per_page
        slice_items = items[start:end]

        embed = discord.Embed(title=f"📊 TikTok – Subskrypcje (strona {page}/{max_page})", color=discord.Color.blurple(), timestamp=datetime.utcnow())
        if not slice_items:
            embed.description = "Brak subskrypcji."
            return embed

        lines = []
        for username, data in slice_items:
            last = data.get("last_video_id", "brak")
            subs = data.get("subscribers", [])
            dead = data.get("dead", False)
            lines.append(f"**@{username}** – last: `{last}` – subów: {len(subs)} – dead: {dead}")
        embed.description = "\n".join(lines)
        return embed

    @app_commands.command(name="tiktok-admin", description="Panel administracyjny TikTok – lista subskrypcji (z paginacją)")
    @app_commands.describe(page="Numer strony (domyślnie 1)")
    async def tiktok_admin(self, interaction: discord.Interaction, page: int = 1):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
            return
        per_page = 10
        embed = self.build_admin_page_embed(page, per_page)
        view = AdminPageView(self, page, per_page)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="tiktok-remove", description="Usuń subskrypcję TikTok")
    async def tiktok_remove(self, interaction: discord.Interaction, username: str):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
            return
        username = username.strip().lstrip("@")
        if username not in self.tiktok_data:
            await interaction.response.send_message("Nie ma takiej subskrypcji.", ephemeral=True)
            return
        del self.tiktok_data[username]
        self.save_tiktok_data()
        logger.info(f"Subscription for {username} removed by admin {interaction.user.id}.")
        await interaction.response.send_message(f"Usunięto subskrypcję **@{username}**.", ephemeral=True)

    @app_commands.command(name="tiktok-test", description="Wyślij testowe powiadomienie do subskrybentów")
    async def tiktok_test(self, interaction: discord.Interaction, username: str):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
            return
        username = username.strip().lstrip("@")
        if username not in self.tiktok_data:
            await interaction.response.send_message("Nie ma takiej subskrypcji.", ephemeral=True)
            return
        fake_video = {"id": "TEST", "url": "https://www.tiktok.com/", "desc": "To jest testowe powiadomienie.", "cover": None}
        await self.notify_subscribers(username, fake_video)
        await interaction.response.send_message("Wysłano testowe powiadomienie.", ephemeral=True)

    @app_commands.command(name="tiktok-forcecheck", description="Wymuś ręczne sprawdzenie nowych filmów")
    async def tiktok_forcecheck(self, interaction: discord.Interaction):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
            return
        await self.check_tiktok_updates()
        await interaction.response.send_message("Ręcznie sprawdzono nowe filmy.", ephemeral=True)

    # ==========================
    # KOMENDA-PANEL: OTWIERANY PANEL Z AKCJAMI (SELECT + PRZYCISKI)
    # ==========================
    @app_commands.command(name="tiktok-panel", description="Otwórz panel administracyjny TikTok")
    async def tiktok_panel(self, interaction: discord.Interaction):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
            return

        options = []
        for i, username in enumerate(sorted(self.tiktok_data.keys(), key=lambda x: x.lower())):
            if i >= 25:
                break
            data = self.tiktok_data[username]
            label = f"@{username} ({len(data.get('subscribers', []))} subów)"
            options.append(discord.SelectOption(label=label, value=username))

        if not options:
            await interaction.response.send_message("Brak subskrypcji.", ephemeral=True)
            return

        class PanelSelect(discord.ui.View):
            def __init__(self, cog):
                super().__init__(timeout=120)
                self.cog = cog

            @discord.ui.select(placeholder="Wybierz subskrypcję", min_values=1, max_values=1, options=options)
            async def select_callback(self, select: discord.ui.Select, select_interaction: discord.Interaction):
                chosen = select.values[0]
                data = self.cog.tiktok_data.get(chosen, {})
                last = data.get("last_video_id", "brak")
                subs = data.get("subscribers", [])
                dead = data.get("dead", False)
                embed = discord.Embed(title=f"@{chosen}", description=f"Last: `{last}`\nSubów: {len(subs)}\nDead: {dead}", color=discord.Color.blurple())
                view = discord.ui.View()

                async def remove_cb(i: discord.Interaction):
                    del self.cog.tiktok_data[chosen]
                    self.cog.save_tiktok_data()
                    await i.response.send_message(f"Usunięto @{chosen}.", ephemeral=True)

                async def test_cb(i: discord.Interaction):
                    fake_video = {"id": "TEST", "url": "https://www.tiktok.com/", "desc": "Test (panel)", "cover": None}
                    await self.cog.notify_subscribers(chosen, fake_video)
                    await i.response.send_message("Wysłano test.", ephemeral=True)

                remove_btn = discord.ui.Button(label="Usuń", style=discord.ButtonStyle.danger)
                test_btn = discord.ui.Button(label="Wyślij test", style=discord.ButtonStyle.success)
                remove_btn.callback = remove_cb
                test_btn.callback = test_cb
                view.add_item(remove_btn)
                view.add_item(test_btn)
                await select_interaction.response.edit_message(embed=embed, view=view)

        view = PanelSelect(self)
        await interaction.response.send_message("Panel TikTok (wybierz subskrypcję):", view=view, ephemeral=True)

    # ==========================
    # DASHBOARD
    # ==========================
    async def start_dashboard(self):
        try:
            await self.runner.setup()
            site = web.TCPSite(self.runner, "0.0.0.0", config.DASHBOARD_PORT)
            await site.start()
            logger.info(f"TikTok dashboard started on port {config.DASHBOARD_PORT}.")
        except Exception as e:
            logger.error(f"Error starting dashboard: {e}")

    def check_dashboard_key(self, request: web.Request) -> bool:
        key = request.query.get("key")
        return key == config.DASHBOARD_KEY

    async def handle_dashboard(self, request: web.Request):
        if not self.check_dashboard_key(request):
            return web.Response(text="Unauthorized", status=401)

        rows = []
        for username, data in sorted(self.tiktok_data.items(), key=lambda x: x[0].lower()):
            last = data.get("last_video_id", "brak")
            subs = data.get("subscribers", [])
            dead = data.get("dead", False)
            rows.append(
                f"<tr><td>@{username}</td><td>{last}</td><td>{len(subs)}</td><td>{dead}</td>"
                f"<td><a href='/action?key={config.DASHBOARD_KEY}&action=remove&user={username}'>Usuń</a></td>"
                f"<td><a href='/action?key={config.DASHBOARD_KEY}&action=test&user={username}'>Test</a></td></tr>"
            )

        rows_html = "\n".join(rows) if rows else "<tr><td colspan='6'>Brak subskrypcji</td></tr>"
        html = f"""
        <html>
        <head><meta charset="utf-8"><title>TikTok Dashboard</title>
        <style>body{{font-family:Arial;color:#eee;background:#111}}table{{width:90%;margin:20px auto;background:#222;border-collapse:collapse}}th,td{{padding:8px;border:1px solid #444}}</style>
        </head>
        <body>
        <h1 style="text-align:center">TikTok Dashboard</h1>
        <table>
        <tr><th>Użytkownik</th><th>Ostatni film</th><th>Liczba subskrybentów</th><th>Dead</th><th>Usuń</th><th>Test</th></tr>
        {rows_html}
        </table></body></html>
        """
        return web.Response(text=html, content_type="text/html")

    async def handle_dashboard_action(self, request: web.Request):
        if not self.check_dashboard_key(request):
            return web.Response(text="Unauthorized", status=401)

        action = request.query.get("action")
        username = request.query.get("user", "").strip().lstrip("@")
        if not action or not username:
            return web.Response(text="Bad request", status=400)

        if action == "remove":
            if username in self.tiktok_data:
                del self.tiktok_data[username]
                self.save_tiktok_data()
                logger.info(f"Dashboard: removed subscription {username}.")
                return web.Response(text=f"Usunięto subskrypcję @{username}.")
            else:
                return web.Response(text="Nie ma takiej subskrypcji.", status=404)

        if action == "test":
            if username not in self.tiktok_data:
                return web.Response(text="Nie ma takiej subskrypcji.", status=404)
            fake_video = {"id": "TEST", "url": "https://www.tiktok.com/", "desc": "To jest testowe powiadomienie (dashboard).", "cover": None}
            await self.notify_subscribers(username, fake_video)
            return web.Response(text=f"Wysłano testowe powiadomienie dla @{username}.")

        return web.Response(text="Unknown action", status=400)

    # ==========================
    # KOMENDA TEST API I DEBUG
    # ==========================
    @app_commands.command(name="tiktok-api-test", description="Test połączenia z zewnętrznym API TikTok")
    @app_commands.describe(username="Nazwa użytkownika do testu")
    async def tiktok_api_test(self, interaction: discord.Interaction, username: str):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        api_res = await self.get_tiktok_latest_via_api(username)
        if api_res:
            embed = discord.Embed(title="API OK", color=discord.Color.green())
            embed.add_field(name="ID", value=api_res["id"], inline=False)
            embed.add_field(name="Link", value=api_res["url"], inline=False)
            if api_res.get("cover"):
                embed.set_thumbnail(url=api_res["cover"])
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("API nie zwróciło danych. Sprawdź klucz, endpoint i logi.", ephemeral=True)

    @app_commands.command(name="tiktok-api-debug", description="Pobierz ostatni zapis surowej odpowiedzi API")
    @app_commands.describe(mode="last (domyślnie)")
    async def tiktok_api_debug(self, interaction: discord.Interaction, mode: str = "last"):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
            return

        debug_file = Path(BASE_DIR) / getattr(config, "TIKTOK_API_DEBUG_FILE", "tiktok_api_debug.log")
        if not debug_file.exists():
            await interaction.response.send_message("Brak pliku debugowego.", ephemeral=True)
            return

        try:
            text = debug_file.read_text(encoding="utf-8")
            if not text:
                await interaction.response.send_message("Plik debugowy jest pusty.", ephemeral=True)
                return

            snippet = text[-1900:]
            await interaction.response.send_message(f"```\n{snippet}\n```", ephemeral=True)
        except Exception as e:
            logger.error(f"Error reading debug file: {e}")
            await interaction.response.send_message("Błąd odczytu pliku debugowego. Sprawdź logi.", ephemeral=True)

# ==========================
# SETUP
# ==========================
async def setup(bot: commands.Bot):
    await bot.add_cog(TikTokCog(bot))

            
