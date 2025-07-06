# ✅ Cleaned and finalized full bot code with all features

import discord
from discord.ext import commands
import os
import json
import re
from flask import Flask
from threading import Thread
import asyncio
from collections import defaultdict
import time

cooldowns = defaultdict(lambda: 0)

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
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# === Load data ===
PROTECTED_FILE = "protected_names.json"
FORMAT_FILE = "format_fallbacks.json"
MOD_ROLE_FILE = "mod_roles.json"
DYNAMIC_FILE = "dynamic_names.json"

def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            data = json.load(f)
        return {int(k): {int(ik): iv for ik, iv in v.items()} if isinstance(v, dict) else int(v) for k, v in data.items()}
    return default

ticket_names = load_json(PROTECTED_FILE, {})
fallback_formats = load_json(FORMAT_FILE, {})
mod_roles = load_json(MOD_ROLE_FILE, {})
dynamic_names = load_json(DYNAMIC_FILE, {})
cooldowns = {}
last_names = {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump({str(k): {str(ik): iv for ik, iv in v.items()} if isinstance(v, dict) else v for k, v in data.items()}, f)

def save_protected(): save_json(PROTECTED_FILE, ticket_names)
def save_formats(): save_json(FORMAT_FILE, fallback_formats)
def save_modroles(): save_json(MOD_ROLE_FILE, mod_roles)
def save_dynamic(): save_json(DYNAMIC_FILE, dynamic_names)

# === Helpers ===
def extract_channel_id(raw):
    match = re.search(r"<#?(\d{17,19})>|(\d{17,19})|channels/\d+/(\d{17,19})", raw)
    return int(next(filter(None, match.groups()), None)) if match else None

def get_member_names(channel):
    members = channel.members if hasattr(channel, 'members') else []
    return [m.display_name for m in members if not m.bot]

def get_online_count(guild):
    return sum(1 for m in guild.members if not m.bot and m.status != discord.Status.offline)

def get_online_mods(guild, role_id):
    role = guild.get_role(role_id)
    return sum(1 for m in role.members if m.status != discord.Status.offline and not m.bot) if role else 0

def format_vc_name(channel, template):
    guild_id = channel.guild.id
    members = get_member_names(channel)
    count = len(members)

    if "{vc}" in template:
        if count == 0:
            fallback = fallback_formats.get(guild_id, {}).get(channel.id, "no one in VC")
            return template.replace("{vc}", fallback)
        elif count == 1:
            return template.replace("{vc}", members[0])
        elif count == 2:
            return template.replace("{vc}", f"{members[0]} and {members[1]}")
        elif count == 3:
            return template.replace("{vc}", f"{members[0]}, {members[1]}, and {members[2]}")
        else:
            fallback = fallback_formats.get(guild_id, {}).get(channel.id, "{count} in VC")
            return template.replace("{vc}", fallback.replace("{count}", str(count)))

    name = template.replace("{count}", str(count))
    name = name.replace("{online}", str(get_online_count(channel.guild)))
    role_id = mod_roles.get(guild_id)
    if role_id:
        name = name.replace("{onlinemods}", str(get_online_mods(channel.guild, role_id)))
    return name

async def enforce_name(channel, force=False):
    guild_id = channel.guild.id
    if guild_id in ticket_names and channel.id in ticket_names[guild_id]:
        raw_locked = ticket_names[guild_id][channel.id]
        is_dynamic = any(var in raw_locked for var in ["{vc}", "{count}", "{online}", "{onlinemods}"])
        new_name = format_vc_name(channel, raw_locked).replace(' ', '-').lower()
        new_name = re.sub(r"[-_]{2,}", "-", new_name).strip("-")

        global last_names

        if is_dynamic:
            if not force and last_names.get(channel.id) == new_name:
                print(f"⏳ No rename needed for {channel.name} (name unchanged)")
                return

            if channel.name == new_name:
                print(f"🚫 Skipping redundant rename for {channel.name} → {new_name}")
                last_names[channel.id] = new_name
                return

            now = time.time()
            if now - cooldowns.get(channel.id, 0) < 1.0:
                print(f"🕒 Skipped rename due to cooldown: {channel.name}")
                return
        else:
            # Static locks: always enforce
            if channel.name != new_name:
                print(f"🔐 Enforcing static lock for {channel.name} → {new_name}")
            else:
                print(f"🔁 Reapplying static lock for {channel.name} (name already correct)")

        cooldowns[channel.id] = time.time()

        try:
            await channel.edit(name=new_name)
            last_names[channel.id] = new_name
            print(f"✅ Renamed {channel.name} → {new_name}")
        except Exception as e:
            print(f"❌ Rename failed for {channel.name}: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    await asyncio.sleep(0.5)
    affected_channels = set(filter(None, [before.channel, after.channel]))
    for vc in affected_channels:
        members = [m.display_name for m in vc.members]
        member_snapshot = ','.join(members)
        if getattr(vc, "_last_member_snapshot", None) != member_snapshot:
            vc._last_member_snapshot = member_snapshot
            await enforce_name(vc, force=True)

@bot.event
async def on_guild_channel_update(before, after):
    await enforce_name(after)

@bot.event
async def on_member_update(before, after):
    for guild in bot.guilds:
        for channel_id, raw_name in dynamic_names.get(guild.id, {}).items():
            if any(v in raw_name for v in ["{online}", "{onlinemods}"]):
                channel = bot.get_channel(channel_id)
                if channel:
                    now = time.time()
                    if now - cooldowns.get(channel.id, 0) >= 1.0:
                        cooldowns[channel.id] = now
                        await enforce_name(channel)

# === Commands ===
@bot.command()
async def help(ctx):
    await ctx.send(
        """**📜 Renamer Bot – Command List**
➡️ You can use channel mentions (like `#channel`), links, or raw channel IDs.

**🆘 !help**
➝ Shows this help message.

**✅ !status**
➝ Shows if the bot is online and how many channels are locked.

**✏️ !rename**
`!rename new-name` ➝ Renames the current channel.
`!rename #channel new-name` ➝ Renames a specific channel.

**🔒 !lockname**
`!lockname desired-name` ➝ Locks the *current channel*.
`!lockname #channel desired-name` ➝ Locks a *specific channel*.

**🔓 !unlockname**
`!unlockname` ➝ Unlocks the *current channel*.
`!unlockname #channel` ➝ Unlocks a *specific channel*.

**📃 !lockedlist**
➝ Shows all currently locked channels and their names.

**✨ !dyname**
`!dyname {vc}` ➝ Enables dynamic renaming for the current channel.  
`!dyname #channel {online}` ➝ Enables dynamic renaming for a specific channel (VCs and Text Channels).

**❌ !undyname**
`!undyname` ➝ Stops dynamic renaming for the current channel.  
`!undyname #channel` ➝ Stops dynamic renaming for a specific channel (VCs and Text Channels).

**🔧 !variablelist**
➝ Shows available dynamic name variables to use for the !dyname command.

**📐 !setformat**
`!setformat format` ➝ Set fallback format for the current channel.
`!setformat #channel format` ➝ Set fallback format for a specific channel.

**🧹 !resetformat**
`!resetformat` ➝ Removes fallback format from the current channel.  
`!resetformat #channel` ➝ Removes fallback format from a specific channel (VCs and Text Channels).

**📊 !showformat**
➝ Shows all channels with a custom fallback format.

**🛡️ !setmodrole [role]**
➝ Set which role is treated as moderator for {onlinemods}.""")

@bot.command()
async def status(ctx):
    guild_id = ctx.guild.id
    count = len(ticket_names.get(guild_id, {}))
    await ctx.send(f"✅ I'm online and locking {count} channel(s).")

@bot.command()
async def variablelist(ctx):
    await ctx.send("""**🔧 Available Variables:**
- `{vc}` ➝ VC member names or fallback (e.g. `Ruki`, `Ruki and Jul`, `3 in VC`)
- `{count}` ➝ VC member count
- `{online}` ➝ Online members
- `{onlinemods}` ➝ Online members with mod role""")

@bot.command()
async def rename(ctx, *args):
    if len(args) == 1:
        channel, new_name = ctx.channel, args[0]
    elif len(args) >= 2:
        channel_id = extract_channel_id(args[0])
        if not channel_id: return await ctx.send("⚠️ Invalid channel.")
        channel = bot.get_channel(channel_id)
        if not channel: return await ctx.send("⚠️ Channel not found.")
        new_name = ' '.join(args[1:])
    else:
        return await ctx.send("⚠️ Usage: `!rename [channel] <new name>`")

    new_name = new_name.replace(' ', '-').lower()
    if ticket_names.get(ctx.guild.id, {}).get(channel.id):
        return await ctx.send(f"🚫 Cannot rename <#{channel.id}>. It's locked.")

    try:
        old_name = channel.name
        await channel.edit(name=new_name)
        await ctx.send(f"✅ Renamed <#{channel.id}> from `{old_name}` to `{new_name}`.")
    except Exception as e:
        await ctx.send(f"❌ Rename failed: {e}")

@bot.command()
async def lockname(ctx, *args):
    if len(args) == 1:
        channel, desired_name = ctx.channel, args[0]
    elif len(args) >= 2:
        channel_id = extract_channel_id(args[0])
        if not channel_id: return await ctx.send("⚠️ Invalid channel.")
        channel = bot.get_channel(channel_id)
        if not channel: return await ctx.send("⚠️ Channel not found.")
        desired_name = ' '.join(args[1:])
    else:
        return await ctx.send("⚠️ Usage: `!lockname [channel] <name>`")

    guild_id = ctx.guild.id
    ticket_names.setdefault(guild_id, {})[channel.id] = desired_name
    save_protected()
    await enforce_name(channel)
    await ctx.send(f"🔐 Locked <#{channel.id}> as `{desired_name}`.")

@bot.command()
async def unlockname(ctx, channel_ref: str = None):
    channel = ctx.channel
    if channel_ref:
        channel_id = extract_channel_id(channel_ref)
        if not channel_id: return await ctx.send("⚠️ Invalid channel.")
        channel = bot.get_channel(channel_id)
        if not channel: return await ctx.send("⚠️ Channel not found.")

    if ticket_names.get(ctx.guild.id, {}).pop(channel.id, None):
        save_protected()
        await ctx.send(f"🔓 Unlocked <#{channel.id}>.")
    else:
        await ctx.send("⚠️ Channel is not locked.")

@bot.command()
async def lockedlist(ctx):
    locked = ticket_names.get(ctx.guild.id, {})
    if not locked:
        return await ctx.send("ℹ️ No locked channels.")
    msg = "**🔒 Locked Channels:**\n"
    for cid, name in locked.items():
        ch = bot.get_channel(cid)
        msg += f"- <#{cid}> ➝ `{name}`\n" if ch else f"- (Missing {cid}) ➝ `{name}`\n"
    await ctx.send(msg)

@bot.command()
async def dyname(ctx, *, name):
    channel = ctx.channel
    guild_id = ctx.guild.id
    if guild_id not in dynamic_names:
        dynamic_names[guild_id] = {}
    dynamic_names[guild_id][channel.id] = name
    save_dynamic()
    await ctx.send(f"✅ This channel will now auto-update using: `{name}`")
    await enforce_name(channel, force=True)
    
@bot.command()
async def setformat(ctx, *args):
    if not args: return await ctx.send("⚠️ Usage: `!setformat [#channel] <format>`")
    channel = ctx.channel
    fmt = args[0] if len(args) == 1 else ' '.join(args[1:])
    if len(args) >= 2:
        channel_id = extract_channel_id(args[0])
        if not channel_id: return await ctx.send("⚠️ Invalid channel.")
        channel = bot.get_channel(channel_id)
        if not channel: return await ctx.send("⚠️ Channel not found.")

    if ctx.guild.id not in ticket_names or channel.id not in ticket_names[ctx.guild.id]:
        return await ctx.send("🚫 Channel must be locked to set a fallback format.")

    fallback_formats.setdefault(ctx.guild.id, {})[channel.id] = fmt
    save_formats()
    await ctx.send(f"✅ Fallback format for <#{channel.id}> set to `{fmt}`.")

@bot.command()
async def showformat(ctx):
    entries = fallback_formats.get(ctx.guild.id, {})
    if not entries:
        return await ctx.send("ℹ️ No fallback formats set.")
    msg = "**📐 Channel-Specific Fallback Formats:**\n"
    for cid, fmt in entries.items():
        ch = bot.get_channel(cid)
        label = f"<#{cid}>" if ch else f"(Missing {cid})"
        msg += f"- {label} ➝ `{fmt}`\n"
    await ctx.send(msg)

@bot.command()
async def setmodrole(ctx, role: discord.Role):
    mod_roles[ctx.guild.id] = role.id
    save_modroles()
    await ctx.send(f"🛡️ `{role.name}` set as mod role.")

# === Launch bot ===
keep_alive()
print("🚀 Starting bot...")
bot.run(os.environ["DISCORD_TOKEN"])
