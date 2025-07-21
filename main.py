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

rename_queues = defaultdict(asyncio.Queue)
rename_tasks = {}
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

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# === Load data ===

PROTECTED_FILE = "protected_names.json"
MOD_ROLE_FILE = "mod_roles.json"

def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    return default

ticket_names = load_json(PROTECTED_FILE, {})
mod_roles = load_json(MOD_ROLE_FILE, {})

def save_json(file, data):
    with open(file, "w") as f:
        json.dump({str(k): v for k, v in data.items()}, f)

def save_protected():
    save_json(PROTECTED_FILE, ticket_names)

def save_modroles():
    save_json(MOD_ROLE_FILE, mod_roles)

# === Enforce name ===

async def enforce_name(channel, force=False):
    guild_id = channel.guild.id
    if guild_id in ticket_names and channel.id in ticket_names[guild_id]:
        new_name = ticket_names[guild_id][channel.id].replace(' ', '-').lower()
        new_name = re.sub(r"[-_]{2,}", "-", new_name).strip("-")

        if channel.name == new_name:
            if not force and (time.time() - cooldowns.get(channel.id, 0)) < 10:
                print(f"❌ Skipping redundant rename for {channel.name} → {new_name}")
                return
            else:
                print(f"🔁 Reapplying static lock for {channel.name} (name already correct)")
        else:
            print(f"🔐 Enforcing static lock for {channel.name} → {new_name}")

        cooldowns[channel.id] = time.time()

        try:
            await queue_rename(channel, new_name)
        except Exception as e:
            print(f"❌ Rename failed for {channel.name}: {e}")

@bot.event
async def on_guild_channel_update(before, after):
    await enforce_name(after)

# === Mod Role Check ===

def is_mod(ctx):
    allowed_roles = mod_roles.get(ctx.guild.id, [])
    return any(role.id in allowed_roles for role in ctx.author.roles)

# === Commands ===

@bot.command()
async def help(ctx):
    await ctx.send("""\n📜 Renamer Bot – Command List
➡️ You can use channel mentions (like #channel), links, or raw channel IDs.

🚘 !help ➔ Shows this help message.

✅ !status ➔ Shows if the bot is online and how many channels are locked.

✏️ !rename [channel] <new name> ➔ Renames a channel.

🔒 !lockname [channel] <name> ➔ Locks a channel name.

🔓 !unlockname [channel] ➔ Unlocks a locked channel.

📃 !lockedlist ➔ Shows all currently locked channels.

🛡️ !setmodrole [role] ➔ Add a role that can use bot commands.
🧹 !removemodrole [role] ➔ Remove a mod role.
📋 !viewmodlist ➔ See current mod roles.""")

@bot.command()
async def status(ctx):
    guild_id = ctx.guild.id
    count = len(ticket_names.get(guild_id, {}))
    await ctx.send(f"✅ I'm online and locking {count} channel(s).")

@bot.command()
async def rename(ctx, *args):
    if not is_mod(ctx): return await ctx.send("⛔ You don't have permission to use this.")

    if len(args) == 1:
        channel, new_name = ctx.channel, args[0]
    elif len(args) >= 2:
        channel_id = extract_channel_id(args[0])
        if not channel_id:
            return await ctx.send("⚠️ Invalid channel.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Channel not found.")
        new_name = ' '.join(args[1:])
    else:
        return await ctx.send("⚠️ Usage: !rename [channel] <new name>")

    new_name = new_name.replace(' ', '-').lower()
    if ticket_names.get(ctx.guild.id, {}).get(channel.id):
        return await ctx.send(f"❌ Cannot rename <#{channel.id}>. It's locked.")

    try:
        old_name = channel.name
        await queue_rename(channel, new_name)
        await ctx.send(f"✅ Renamed <#{channel.id}> from `{old_name}` to `{new_name}`.")
    except Exception as e:
        await ctx.send(f"❌ Rename failed: {e}")

@bot.command()
async def lockname(ctx, *args):
    if not is_mod(ctx): return await ctx.send("⛔ You don't have permission to use this.")

    if len(args) == 1:
        channel, desired_name = ctx.channel, args[0]
    elif len(args) >= 2:
        channel_id = extract_channel_id(args[0])
        if not channel_id:
            return await ctx.send("⚠️ Invalid channel.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Channel not found.")
        desired_name = ' '.join(args[1:])
    else:
        return await ctx.send("⚠️ Usage: !lockname [channel] <name>")

    guild_id = ctx.guild.id
    ticket_names.setdefault(guild_id, {})[channel.id] = desired_name
    save_protected()
    await ctx.send(f"🔐 Locked <#{channel.id}> as `{desired_name}`.")
    await enforce_name(channel, force=True)

@bot.command()
async def unlockname(ctx, channel_ref: str = None):
    if not is_mod(ctx): return await ctx.send("⛔ You don't have permission to use this.")

    channel = ctx.channel
    if channel_ref:
        channel_id = extract_channel_id(channel_ref)
        if not channel_id:
            return await ctx.send("⚠️ Invalid channel.")
        channel = bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("⚠️ Channel not found.")

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
    msg = "🔒 Locked Channels:\n"
    for cid, name in locked.items():
        ch = bot.get_channel(cid)
        msg += f"- <#{cid}> ➝ {name}\n" if ch else f"- (Missing {cid}) ➝ {name}\n"
    await ctx.send(msg)

@bot.command()
async def setmodrole(ctx, role: discord.Role):
    mod_roles.setdefault(ctx.guild.id, [])
    if role.id in mod_roles[ctx.guild.id]:
        return await ctx.send(f"ℹ️ {role.name} is already a mod role.")
    mod_roles[ctx.guild.id].append(role.id)
    save_modroles()
    await ctx.send(f"🛡️ {role.name} added as a mod role.")

@bot.command()
async def removemodrole(ctx, role: discord.Role):
    roles = mod_roles.get(ctx.guild.id, [])
    if role.id not in roles:
        return await ctx.send(f"ℹ️ {role.name} is not currently a mod role.")
    roles.remove(role.id)
    save_modroles()
    await ctx.send(f"🗑️ {role.name} removed from mod roles.")

@bot.command()
async def viewmodlist(ctx):
    roles = mod_roles.get(ctx.guild.id, [])
    if not roles:
        return await ctx.send("ℹ️ No mod roles set.")
    names = [discord.utils.get(ctx.guild.roles, id=rid).name for rid in roles if discord.utils.get(ctx.guild.roles, id=rid)]
    await ctx.send("🪪 Current mod roles: " + ", ".join(names))

# === Safe rename queuing to prevent rate limits ===

async def queue_rename(channel: discord.TextChannel, target_name: str):
    queue = rename_queues[channel.id]
    await queue.put(target_name)
    if channel.id not in rename_tasks:
        rename_tasks[channel.id] = asyncio.create_task(handle_rename_queue(channel))

async def handle_rename_queue(channel: discord.TextChannel):
    queue = rename_queues[channel.id]
    while not queue.empty():
        try:
            target_name = await queue.get()
            await asyncio.sleep(1.5)
            if channel.name != target_name:
                await channel.edit(name=target_name)
                print(f"✅ Renamed {channel.name} to {target_name}")
            else:
                print(f"⏳ Skipping rename; already named {target_name}")
            await asyncio.sleep(10)
        except discord.HTTPException as e:
            print(f"❌ Rename error (rate limit?): {e}")
            await asyncio.sleep(30)
        except Exception as e:
            print(f"❌ Unexpected error in rename queue: {e}")
    del rename_tasks[channel.id]

# === Helper ===

def extract_channel_id(raw):
    match = re.search(r"<#?(\d{17,19})>|(\d{17,19})|channels/\d+/(\d{17,19})", raw)
    return int(next(filter(None, match.groups()), None)) if match else None

# === Launch bot ===

keep_alive()
print("🚀 Starting bot...")
bot.run(os.environ["DISCORD_TOKEN"])
