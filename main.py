import discord
from discord.ext import commands
import os
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

ticket_names = {
    1386642257192681533: "🆕-tasks-‼"
}

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_guild_channel_update(before, after):
    if after.id in ticket_names:
        expected_name = ticket_names[after.id]
        if after.name != expected_name:
            try:
                await after.edit(name=expected_name)
                print(f"🔁 Renamed {after.name} back to {expected_name}")
            except Exception as e:
                print(f"❌ Failed to rename: {e}")

keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
