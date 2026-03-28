# bot/cogs/music.py

import discord
from discord.ext import commands
import yt_dlp
import asyncio
from typing import List, Dict, Any




YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "auto",  # <-- automatyczne wyszukiwanie na wielu platformach
    "source_address": "0.0.0.0"

}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn"

}


class MusicQueue:
    def __init__(self):
        self.songs: List[Dict[str, Any]] = []

    def add(self, info):
        self.songs.append(info)

    def pop(self):
        if self.songs:
            return self.songs.pop(0)
        return None

    def clear(self):
        self.songs.clear()

    def __len__(self):
        return len(self.songs)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues: Dict[int, MusicQueue] = {}  # guild_id → queue
        self.current_voice: Dict[int, discord.VoiceClient] = {}

    def get_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()
        return self.queues[guild_id]

    async def play_next(self, guild_id: int):
        queue = self.get_queue(guild_id)
        vc = self.current_voice.get(guild_id)

        if not vc or not queue.songs:
            if vc:
                await asyncio.sleep(10)
                if not queue.songs and vc.is_connected():
                    await vc.disconnect()
            return

        song = queue.pop()
        url = song["url"]
        title = song["title"]

        source = discord.FFmpegPCMAudio(
            url,
            before_options=FFMPEG_OPTIONS["before_options"],
            options=FFMPEG_OPTIONS["options"]
        )

        vc.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                self.play_next(guild_id),
                self.bot.loop
            )
        )

    def search_song(self, query: str):
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)

            if "entries" in info:
                info = info["entries"][0]

            return {
                "title": info.get("title", "Nieznany tytuł"),
                "url": info["url"]
            }

    # --- KOMENDY ---

    @discord.app_commands.command(name="play", description="Odtwarza muzykę z YouTube, SoundCloud, Spotify i innych.")
    async def play(self, interaction: discord.Interaction, *, query: str):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Musisz być na kanale głosowym!", ephemeral=True)

        await interaction.response.defer()

        guild_id = interaction.guild_id
        queue = self.get_queue(guild_id)

        # Połączenie z kanałem
        vc = self.current_voice.get(guild_id)
        if not vc or not vc.is_connected():
            vc = await interaction.user.voice.channel.connect()
            self.current_voice[guild_id] = vc

        # Wyszukiwanie utworu
        song = self.search_song(query)
        queue.add(song)

        await interaction.followup.send(f"🎵 Dodano do kolejki: **{song['title']}**")

        if not vc.is_playing():
            await self.play_next(guild_id)

    @discord.app_commands.command(name="skip", description="Pomija aktualny utwór.")
    async def skip(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        vc = self.current_voice.get(guild_id)

        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Pominięto utwór.")
        else:
            await interaction.response.send_message("Nic nie gra.", ephemeral=True)

    @discord.app_commands.command(name="stop", description="Zatrzymuje muzykę i czyści kolejkę.")
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        queue = self.get_queue(guild_id)
        vc = self.current_voice.get(guild_id)

        queue.clear()

        if vc and vc.is_connected():
            await vc.disconnect()

        await interaction.response.send_message("🛑 Zatrzymano muzykę i wyczyszczono kolejkę.")

    @discord.app_commands.command(name="queue", description="Pokazuje aktualną kolejkę.")
    async def queue_cmd(self, interaction: discord.Interaction):
        queue = self.get_queue(interaction.guild_id)

        if len(queue) == 0:
            return await interaction.response.send_message("🎶 Kolejka jest pusta.")

        text = "\n".join([f"{i+1}. {song['title']}" for i, song in enumerate(queue.songs)])
        await interaction.response.send_message(f"📜 **Kolejka:**\n{text}")

    @discord.app_commands.command(name="pause", description="Pauzuje muzykę.")
    async def pause(self, interaction: discord.Interaction):
        vc = self.current_voice.get(interaction.guild_id)
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Pauza.")
        else:
            await interaction.response.send_message("Nic nie gra.", ephemeral=True)

    @discord.app_commands.command(name="resume", description="Wznawia muzykę.")
    async def resume(self, interaction: discord.Interaction):
        vc = self.current_voice.get(interaction.guild_id)
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Wznowiono.")
        else:
            await interaction.response.send_message("Muzyka nie jest zapauzowana.", ephemeral=True)




async def setup(bot):
    await bot.add_cog(Music(bot))