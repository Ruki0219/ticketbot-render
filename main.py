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

# === Load protected names ===
PROTECTED_FILE = "protected_names.json"

if os.path.exists(PROTECTED_FILE):
    with open(PROTECTED_FILE, "r") as f:
        ticket_names = json.load(f)
        ticket_names = {int(guild_id): {int(chan_id): name for chan_id, name in chans.items()}
                        for guild_id, chans in ticket_names.items()}
else:
    ticket_names = {}

def save_protected():
    with open(PROTECTED_FILE, "w") as f:
        json.dump({str(gid): {str(cid): name for cid, name in chans.items()}
                   for gid, chans in ticket_names.items()}, f)

# === Events ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_guild_channel_update(before, after):
    guild_id = after.guild.id
    if guild_id in ticket_names and after.id in ticket_names[guild_id]:
        expected_name = ticket_names[guild_id][after.id]
        expected_discord_name = expected_name.replace(' ', '-').lower()

        if after.name != expected_discord_name:
            try:
                await after.edit(name=expected_discord_name)
                print(f"🔁 Renamed {after.name} back to {expected_discord_name}")

                # 🔔 Notification on rename attempt
                if isinstance(after, discord.TextChannel):
                    try:
                        await after.send(
                            f"🚫 Rename attempt blocked for <#{after.id}>.\n"
                            f"Name is locked as `{expected_discord_name}`."
                        )
                    except Exception as send_error:
                        print(f"⚠️ Failed to send notification: {send_error}")

            except Exception as e:
                print(f"❌ Failed to rename: {e}")

# === Helper ===
def extract_channel_id(raw):
    match = re.search(r"<#?(\d{17,19})>|(\d{17,19})|channels/\d+/(\d{17,19})", raw)
    if match:
        return int(match.group(1) or match.group(2) or match.group(3))
    return None

# === Commands ===
@bot.command()
async def status(ctx):
    guild_id = ctx.guild.id
    count = len(ticket_names.get(guild_id, {}))
    await ctx.send(f"✅ I'm online and currently locking {count} channel(s) in this server.")

@bot.command()
async def rename(ctx, *args):
    if len(args) == 1:
        new_name = args[0].replace(' ', '-').lower()
        channel = ctx.channel
    elif len(args) >= 2:
        channel_id = extract_channel_id(args[0])
        if not channel_id:
            return await ctx.send("⚠️ Invalid channel mention, link, or ID.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Could not find the channel.")
        new_name = ' '.join(args[1:]).replace(' ', '-').lower()
    else:
        return await ctx.send("⚠️ Usage: `!rename [channel] <new name>`")

    try:
        old_name = channel.name
        await channel.edit(name=new_name)
        await ctx.send(f"✅ Renamed channel <#{channel.id}> from `{old_name}` to `{new_name}`.")
    except Exception as e:
        await ctx.send(f"❌ Failed to rename: {e}")

@bot.command()
async def lockname(ctx, *args):
    if len(args) == 1:
        channel = ctx.channel
        desired_name = args[0]
    elif len(args) >= 2:
        channel_id = extract_channel_id(args[0])
        if not channel_id:
            return await ctx.send("⚠️ Invalid channel mention, link, or ID.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Could not find the channel.")
        desired_name = ' '.join(args[1:])
    else:
        return await ctx.send("⚠️ Usage: `!lockname [channel] <desired-name>`")

    normalized_name = desired_name.replace(' ', '-').lower()

    guild_id = ctx.guild.id
    if guild_id not in ticket_names:
        ticket_names[guild_id] = {}
    ticket_names[guild_id][channel.id] = normalized_name
    save_protected()

    await ctx.send(f"🔐 Locked name of <#{channel.id}> as `{normalized_name}`.")

@bot.command()
async def unlockname(ctx, channel_ref: str = None):
    if channel_ref:
        channel_id = extract_channel_id(channel_ref)
        if not channel_id:
            return await ctx.send("⚠️ Invalid channel mention, link, or ID.")
        channel = bot.get_channel(channel_id)
    else:
        channel = ctx.channel

    guild_id = ctx.guild.id
    if guild_id in ticket_names and channel.id in ticket_names[guild_id]:
        del ticket_names[guild_id][channel.id]
        save_protected()
        await ctx.send(f"🔓 Unlocked name for <#{channel.id}>. It can now be changed freely.")
    else:
        await ctx.send("⚠️ This channel isn't being auto-renamed or wasn't found.")

@bot.command(name="lockedlist")
async def lockedlist(ctx):
    guild_id = ctx.guild.id
    locked = ticket_names.get(guild_id, {})

    if not locked:
        return await ctx.send("ℹ️ No channels are currently locked in this server.")
    
    message = "**🔒 Locked Channels:**\n"
    for channel_id, name in locked.items():
        channel = bot.get_channel(channel_id)
        channel_display = f"<#{channel_id}>" if channel else f"(Deleted or inaccessible channel {channel_id})"
        message += f"- {channel_display} ➡️ `{name}`\n"
    
    await ctx.send(message)

@bot.command()
async def help(ctx):
    help_text = (
        "**📜 Renamer Bot – Command List**\n"
        "➡️ You can use channel mentions (like `#channel`), links, or raw channel IDs.\n"
        "\n"
        "**🆘 !help**\n"
        "➝ Shows this help message.\n"
        "\n"
        "**✅ !status**\n"
        "➝ Shows if the bot is online and how many channels are locked in *this server*.\n"
        "\n"
        "**✏️ !rename**\n"
        "`!rename new-name` ➝ Renames the current channel.\n"
        "`!rename #channel new-name` ➝ Renames a specific channel.\n"
        "\n"
        "**🔒 !lockname**\n"
        "`!lockname desired-name` ➝ Locks the *current channel*'s name.\n"
        "`!lockname #channel desired-name` ➝ Locks a *specific channel's* name.\n"
        "\n"
        "**🔓 !unlockname**\n"
        "`!unlockname` ➝ Unlocks the *current channel*.\n"
        "`!unlockname #channel` ➝ Unlocks a *specific channel*.\n"
        "\n"
        "**📃 !lockedlist**\n"
        "➝ Shows all currently locked channels and their names for *this server*.\n"
        "\n"
    )
    await ctx.send(help_text)

# === Launch bot ===
keep_alive()
print("🚀 Starting bot...")
bot.run(os.environ["DISCORD_TOKEN"])
