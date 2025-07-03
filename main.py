ort discord
from discord.ext import commands
import os
import json
import re
from flask import Flask
from threading import Thread
import asyncio

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
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# === Load protected names ===
PROTECTED_FILE = "protected_names.json"
FALLBACK_FORMAT = "{count}-in-vc"
MOD_ROLE_NAME = "Mod"

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

# === Helper ===
def extract_channel_id(raw):
    match = re.search(r"<#?(\d{17,19})>|(\d{17,19})|channels/\d+/(\d{17,19})", raw)
    if match:
        return int(match.group(1) or match.group(2) or match.group(3))
    return None

def get_member_names(channel):
    members = channel.members if hasattr(channel, 'members') else []
    return [m.display_name for m in members if not m.bot]

def format_vc_name(members):
    if len(members) == 1:
        return f"[{members[0]}]"
    elif len(members) == 2:
        return f"[{members[0]}-{members[1]}]"
    elif len(members) == 3:
        return f"[{members[0]}-{members[1]}-{members[2]}]"
    else:
        return f"[{FALLBACK_FORMAT.replace('{count}', str(len(members)))}]"

async def enforce_name(channel):
    guild_id = channel.guild.id
    if guild_id in ticket_names and channel.id in ticket_names[guild_id]:
        raw_locked = ticket_names[guild_id][channel.id]
        name = raw_locked

        if "{vc}" in name:
            members = get_member_names(channel)
            name = name.replace("{vc}", format_vc_name(members))

        name = name.replace(' ', '-').lower()
        if channel.name != name:
            try:
                await channel.edit(name=name)
                print(f"🔁 Enforced rename: {channel.name} → {name}")
            except Exception as e:
                print(f"❌ Failed to rename: {e}")

# === Events ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_voice_state_update(member, before, after):
    await asyncio.sleep(1)
    for vc in set(filter(None, [before.channel, after.channel])):
        await enforce_name(vc)

@bot.event
async def on_guild_channel_update(before, after):
    await enforce_name(after)

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
            return await ctx.send("⚠️ Invalid channel reference.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Could not find the channel.")
        new_name = ' '.join(args[1:]).replace(' ', '-').lower()
    else:
        return await ctx.send("⚠️ Usage: `!rename [channel] <new name>`")

    guild_id = ctx.guild.id
    if guild_id in ticket_names and channel.id in ticket_names[guild_id]:
        locked_name = ticket_names[guild_id][channel.id]
        return await ctx.send(f"🚫 Rename attempt blocked for <#{channel.id}>.\nName is locked as `{locked_name}`.")

    try:
        old_name = channel.name
        await channel.edit(name=new_name)
        await ctx.send(f"✅ Renamed <#{channel.id}> from `{old_name}` to `{new_name}`.")
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
            return await ctx.send("⚠️ Invalid channel reference.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Could not find the channel.")
        desired_name = ' '.join(args[1:])
    else:
        return await ctx.send("⚠️ Usage: `!lockname [channel] <desired-name>`")

    guild_id = ctx.guild.id
    if guild_id not in ticket_names:
        ticket_names[guild_id] = {}
    ticket_names[guild_id][channel.id] = desired_name
    save_protected()

    await enforce_name(channel)
    await ctx.send(f"🔐 Locked name of <#{channel.id}> as `{desired_name}`.")

@bot.command()
async def unlockname(ctx, channel_ref: str = None):
    channel = ctx.channel
    if channel_ref:
        channel_id = extract_channel_id(channel_ref)
        if not channel_id:
            return await ctx.send("⚠️ Invalid channel reference.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Could not find the channel.")

    guild_id = ctx.guild.id
    if guild_id in ticket_names and channel.id in ticket_names[guild_id]:
        del ticket_names[guild_id][channel.id]
        save_protected()
        await ctx.send(f"🔓 Unlocked name for <#{channel.id}>.")
    else:
        await ctx.send("⚠️ This channel isn't being auto-renamed or wasn't found.")

@bot.command(name="lockedlist")
async def lockedlist(ctx):
    guild_id = ctx.guild.id
    locked = ticket_names.get(guild_id, {})
    if not locked:
        return await ctx.send("ℹ️ No channels are currently locked in this server.")
    msg = "**🔒 Locked Channels:**\n"
    for channel_id, name in locked.items():
        channel = bot.get_channel(channel_id)
        label = f"<#{channel_id}>" if channel else f"(Missing {channel_id})"
        msg += f"- {label} ➝ `{name}`\n"
    await ctx.send(msg)

@bot.command()
async def variablelist(ctx):
    await ctx.send(
        "**🔧 Available Variables:**\n"
        "- `{vc}` ➝ Dynamic VC member names or fallback (e.g. `[Ruki-Jul-Kim]`, `[4-in-vc]`)\n"
        "- `{online}` ➝ Future feature\n"
        "- `{onlinemods}` ➝ Future feature (requires !setmodrole)"
    )

@bot.command()
async def help(ctx):
    help_text = (
        "**📜 Renamer Bot – Command List**\n"
        "➡️ You can use channel mentions (like `#channel`), links, or raw channel IDs.\n\n"
        "**🆘 !help**\n➝ Shows this help message.\n\n"
        "**✅ !status**\n➝ Shows if the bot is online and how many channels are locked.\n\n"
        "**✏️ !rename**\n`!rename new-name` ➝ Renames the current channel.\n"
        "`!rename #channel new-name` ➝ Renames a specific channel.\n\n"
        "**🔒 !lockname**\n`!lockname desired-name` ➝ Locks the *current channel*.\n"
        "`!lockname #channel desired-name` ➝ Locks a *specific channel*.\n\n"
        "**🔓 !unlockname**\n`!unlockname` ➝ Unlocks the *current channel*.\n"
        "`!unlockname #channel` ➝ Unlocks a *specific channel*.\n\n"
        "**📃 !lockedlist**\n➝ Shows all currently locked channels and their names.\n\n"
        "**🔧 !variablelist**\n➝ Shows available dynamic name variables."
    )
    await ctx.send(help_text)

# === Launch bot ===
keep_alive()
print("🚀 Starting bot...")
bot.run(os.environ["DISCORD_TOKEN"])
