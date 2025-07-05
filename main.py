# ✅ Cleaned and finalized full bot code with all features

import discord
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

# === Load data ===
PROTECTED_FILE = "protected_names.json"
FORMAT_FILE = "format_fallbacks.json"
MOD_ROLE_FILE = "mod_roles.json"

if os.path.exists(PROTECTED_FILE):
    with open(PROTECTED_FILE, "r") as f:
        ticket_names = json.load(f)
        ticket_names = {int(gid): {int(cid): name for cid, name in chans.items()} for gid, chans in ticket_names.items()}
else:
    ticket_names = {}

if os.path.exists(FORMAT_FILE):
    with open(FORMAT_FILE, "r") as f:
        fallback_formats = json.load(f)
        fallback_formats = {int(gid): {int(cid): fmt for cid, fmt in chans.items()} for gid, chans in fallback_formats.items()}
else:
    fallback_formats = {}

if os.path.exists(MOD_ROLE_FILE):
    with open(MOD_ROLE_FILE, "r") as f:
        mod_roles = json.load(f)
        mod_roles = {int(gid): int(rid) for gid, rid in mod_roles.items()}
else:
    mod_roles = {}

def save_protected():
    with open(PROTECTED_FILE, "w") as f:
        json.dump({str(gid): {str(cid): name for cid, name in chans.items()} for gid, chans in ticket_names.items()}, f)

def save_formats():
    with open(FORMAT_FILE, "w") as f:
        json.dump({str(gid): {str(cid): fmt for cid, fmt in chans.items()} for gid, chans in fallback_formats.items()}, f)

def save_modroles():
    with open(MOD_ROLE_FILE, "w") as f:
        json.dump({str(gid): rid for gid, rid in mod_roles.items()}, f)

# === Helpers ===
def extract_channel_id(raw):
    match = re.search(r"<#?(\d{17,19})>|(\d{17,19})|channels/\d+/(\d{17,19})", raw)
    if match:
        return int(match.group(1) or match.group(2) or match.group(3))
    return None

def get_member_names(channel):
    members = channel.members if hasattr(channel, 'members') else []
    return [m.display_name for m in members if not m.bot]

def get_online_count(guild):
    return sum(1 for m in guild.members if not m.bot and m.status != discord.Status.offline)

def get_online_mods(guild, role_id):
    role = guild.get_role(role_id)
    if not role:
        return 0
    return sum(1 for m in role.members if m.status != discord.Status.offline and not m.bot)

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

    name = template
    name = name.replace("{count}", str(count))
    name = name.replace("{online}", str(get_online_count(channel.guild)))
    role_id = mod_roles.get(guild_id)
    if role_id:
        name = name.replace("{onlinemods}", str(get_online_mods(channel.guild, role_id)))
    return name

async def enforce_name(channel):
    guild_id = channel.guild.id
    if guild_id in ticket_names and channel.id in ticket_names[guild_id]:
        raw_locked = ticket_names[guild_id][channel.id]
        name = format_vc_name(channel, raw_locked).replace(' ', '-').lower()
        name = re.sub(r"[-_]{2,}", "-", name).strip("-")  # normalize name
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
async def setformat(ctx, *args):
    if len(args) < 1:
        return await ctx.send("⚠️ Usage: !setformat [#channel] <format>")
    if len(args) == 1:
        channel = ctx.channel
        fmt = args[0]
    else:
        channel_id = extract_channel_id(args[0])
        if not channel_id:
            return await ctx.send("⚠️ Invalid channel reference.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Could not find the channel.")
        fmt = ' '.join(args[1:])

    guild_id = ctx.guild.id
    if guild_id not in ticket_names or channel.id not in ticket_names[guild_id]:
        return await ctx.send("🚫 You can only set fallback format for locked channels containing dynamic variables.")
    if guild_id not in fallback_formats:
        fallback_formats[guild_id] = {}
    fallback_formats[guild_id][channel.id] = fmt
    save_formats()
    await ctx.send(f"✅ Fallback format for <#{channel.id}> set to `{fmt}`.")

@bot.command()
async def showformat(ctx):
    guild_id = ctx.guild.id
    entries = fallback_formats.get(guild_id, {})
    if not entries:
        return await ctx.send("ℹ️ No fallback formats set in this server.")
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
    await ctx.send(f"🛡️ Set `{role.name}` as the moderator role.")

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

**📐 !setformat**
`!setformat format` ➝ Set fallback format for this channel.
`!setformat #channel format` ➝ Set fallback format for another channel.

**📊 !showformat**
➝ Shows all channels with a custom fallback format.

**🛡️ !setmodrole [role]**
➝ Set which role is treated as moderator for {onlinemods}.

**🔧 !variablelist**
➝ Shows available dynamic name variables.""")

@bot.command()
async def status(ctx):
    guild_id = ctx.guild.id
    count = len(ticket_names.get(guild_id, {}))
    await ctx.send(f"✅ I'm online and currently locking {count} channel(s) in this server.")

@bot.command()
async def variablelist(ctx):
    await ctx.send(
        """**🔧 Available Variables:**
- `{vc}` ➝ Dynamic VC member names or fallback (e.g. `Ruki`, `Ruki and Jul`, `3 in VC`, etc.)
- `{count}` ➝ Number of users in VC
- `{online}` ➝ Total online users in the server
- `{onlinemods}` ➝ Online members with the mod role
""")

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

# === Launch bot ===
keep_alive()
print("🚀 Starting bot...")
bot.run(os.environ["DISCORD_TOKEN"])
