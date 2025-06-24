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

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

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

# === Helper to extract channel ID from mention/link/raw ===
def extract_channel_id(raw):
    # Matches <#123456789012345678>, links, or plain IDs
    match = re.search(r"<#?(\d{17,19})>|(\d{17,19})|channels/\d+/(\d{17,19})", raw)
    if match:
        return int(match.group(1) or match.group(2))
    return None

# === Commands ===
@bot.command()
async def status(ctx):
    await ctx.send(f"✅ I'm online and currently locking {len(ticket_names)} ticket(s).")

@bot.command()
async def rename(ctx, *args):
    if len(args) == 1:
        # Only new name provided, use current channel
        new_name = args[0]
        channel = ctx.channel
    elif len(args) >= 2:
        channel_id = extract_channel_id(args[0])
        if not channel_id:
            return await ctx.send("⚠️ Invalid channel mention, link, or ID.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Could not find the channel.")
        new_name = ' '.join(args[1:])
    else:
        return await ctx.send("⚠️ Usage: `!rename [channel] <new name>`")

    try:
        old_name = channel.name
        await channel.edit(name=new_name)
        await ctx.send(f"✅ Renamed channel <#{channel.id}> from `{old_name}` to `{new_name}`.")
    except Exception as e:
        await ctx.send(f"❌ Failed to rename: {e}")

@bot.command()
async def lockname(ctx, channel_ref: str, *, desired_name: str):
    channel_id = extract_channel_id(channel_ref)
    if channel_id:
        ticket_names[channel_id] = desired_name
        save_protected()
        await ctx.send(f"🔐 Locked name of <#{channel_id}> as `{desired_name}`.")
    else:
        await ctx.send("⚠️ Invalid channel mention, link, or ID.")

@bot.command()
async def unlockname(ctx, channel_ref: str):
    channel_id = extract_channel_id(channel_ref)
    if channel_id in ticket_names:
        del ticket_names[channel_id]
        save_protected()
        await ctx.send(f"🔓 Unlocked name for <#{channel_id}>. It can now be changed freely.")
    else:
        await ctx.send("⚠️ This channel isn't being auto-renamed or wasn't found.")

@bot.command()
async def help(ctx):
    help_text = (
        "**📜 TicketRenamer Bot – Command List**\n"
        "➡️ Use these commands to interact with the TicketRenamer bot. You can use channel mentions (like `#ticket-0004`), links, or raw channel IDs.\n"
        "\n"
        "**🆘 !help**\n"
        "Shows the full list of commands and their usage.\n"
        "\n"
        "**✅ !status**\n"
        "Shows if the bot is online and how many channels are currently locked.\n"
        "\n"
        "**✏️ !rename**\n"
        "`!rename new-name` ➡️ Renames the current channel.\n"
        "`!rename #channel new-name` ➡️ Renames a specific channel.\n"
        "\n"
        "**🔒 !lockname**\n"
        "`!lockname #channel desired-name` ➡️ Locks a channel’s name.\n"
        "\n"
        "**🔓 !unlockname**\n"
        "`!unlockname #channel` ➡️ Unlocks a channel so its name can change freely."
    )
    await ctx.send(help_text)

# === Launch bot ===
keep_alive()
print("🚀 Starting bot...")
bot.run(os.environ["DISCORD_TOKEN"])
