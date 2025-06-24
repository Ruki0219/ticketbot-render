import discord
from discord.ext import commands
import os
import json
import re
from flask import Flask
from threading import Thread

# === Flask keep_alive setup ===
app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# === Bot setup ===
intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# === Load protected tickets ===
PROTECTED_FILE = "protected_tickets.json"

if os.path.exists(PROTECTED_FILE):
    with open(PROTECTED_FILE, "r") as f:
        ticket_names = json.load(f)
        ticket_names = {int(k): v for k, v in ticket_names.items()}
else:
    ticket_names = {}

def save_protected():
    with open(PROTECTED_FILE, "w") as f:
        json.dump(ticket_names, f)

# === Bot events ===
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

# === Helper to extract channel ID ===
def extract_channel_id(raw):
    match = re.search(r"(\d{17,19})$", raw)
    return int(match.group(1)) if match else None

# === Commands ===
@bot.command()
async def status(ctx):
    await ctx.send(f"✅ I'm online and currently locking {len(ticket_names)} ticket(s).")

@bot.command()
async def rename(ctx, channel_ref: str, *, new_name: str):
    channel_id = extract_channel_id(channel_ref)
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                await channel.edit(name=new_name)
                await ctx.send(f"✅ Renamed <#{channel_id}> to `{new_name}`.")
            except Exception as e:
                await ctx.send(f"❌ Failed to rename: {e}")
        else:
            await ctx.send("⚠️ Could not find the channel.")
    else:
        await ctx.send("⚠️ Invalid channel link or ID.")

@bot.command()
async def lockname(ctx, channel_ref: str, *, desired_name: str):
    channel_id = extract_channel_id(channel_ref)
    if channel_id:
        ticket_names[channel_id] = desired_name
        save_protected()
        await ctx.send(f"🔒 Locked name of <#{channel_id}> as `{desired_name}`.")
    else:
        await ctx.send("⚠️ Invalid channel link or ID.")

@bot.command()
async def unlockname(ctx, channel_ref: str):
    channel_id = extract_channel_id(channel_ref)
    if channel_id in ticket_names:
        del ticket_names[channel_id]
        save_protected()
        await ctx.send(f"🔓 Unlocked name for <#{channel_id}>. It can now be changed freely.")
    else:
        await ctx.send("⚠️ This channel isn't being auto-renamed or wasn't found.")

# === Launch bot ===
keep_alive()
print("🚀 Starting bot...")
bot.run(os.environ["DISCORD_TOKEN"])
