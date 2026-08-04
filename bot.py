import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import json
import re
import random
import aiohttp
from datetime import timedelta, datetime, timezone
import pytz
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
KLIPY_API_KEY = os.getenv("KLIPY_API_KEY")

WELCOME_CHANNEL_ID  = 1501909942754344965
WELCOME_TITLE       = "🏴‍☠️ A new crewmate has arrived!"
WELCOME_COLOR       = discord.Color.gold()

WELCOME_DESCRIPTION = (
    "Welcome aboard, {member}! You're crew member #{count}.\n"
    "Check out the links below to get started! 🏴‍☠️"
)

WELCOME_CHANNELS = [
    ("🎭 Self Roles",      1501910210363789504),
    ("🎨 Colour Roles",    1504147015339085905),
    ("📜 Rules",           1501941624429609040),
    ("📢 Announcements",   1501909942754344962),
]

WELCOME_ROLES = [
    ("🏴‍☠️ Crewmate",     777777777777777777),
    ("🎮 Gamer",           888888888888888888),
]

CHANNELS_PER_ROW = 2

LOG_CHANNEL_ID = 1501943719249707018
ROLE_HIERARCHY = ["King of the Pirates", "Admin", "Manager", "Moderator"]
BAD_WORDS = ["badword1", "badword2"]
WARNINGS = {}
_welcome_channel_override = {}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ============================================================================
# /help COMMAND — dropdown category menu, light One Piece theme
# Paste this whole block anywhere in your bot.py (after `bot = commands.Bot(...)`
# is defined). No other changes needed — it's fully self-contained.
# ============================================================================

COMMAND_CATEGORIES = {
    "🛡️ Moderation": [
        ("/warn", "Warn a member"),
        ("/warnings", "Check a member's warnings"),
        ("/clearwarnings", "Clear all warnings for a member"),
        ("/kick", "Kick a member"),
        ("/ban", "Ban a member"),
        ("/unban", "Unban a user"),
        ("/mute", "Timeout a member"),
        ("/unmute", "Remove a timeout"),
        ("/purge", "Delete multiple messages"),
        ("/ignorechannel", "Toggle command usage in a channel"),
        ("/ignoreuser", "Toggle command usage for a user"),
        ("/ignorerole", "Toggle command usage for a role"),
    ],
    "🎭 Roles & Server": [
        ("/addrole", "Add a role to a member"),
        ("/removerole", "Remove a role from a member"),
        ("/role", "Add/remove/toggle a role on a member"),
        ("/roleall", "Add/remove a role for everyone, bots, or humans"),
        ("/createrole", "Create a new role"),
        ("/deleterole", "Delete a role"),
        ("/rolecolor", "Change a role's color"),
        ("/rolename", "Rename a role"),
        ("/mentionable", "Toggle whether a role can be mentioned"),
        ("/addmod", "Add a moderator role"),
        ("/delmod", "Remove a moderator role"),
        ("/listmods", "List all moderator roles"),
        ("/nick", "Change the bot's nickname"),
        ("/setnick", "Change a member's nickname"),
        ("/addemote", "Add a custom emote to the server"),
    ],
    "📜 Welcome & Announcements": [
        ("/setwelcome", "Set the welcome message channel"),
        ("/testwelcome", "Preview the welcome message"),
        ("/announce", "Send an announcement"),
        ("/setsticky", "Set a sticky message in a channel"),
        ("/removesticky", "Remove a sticky message"),
        ("/liststicky", "List all sticky messages"),
        ("/setintrosticky", "Post the intro template as a sticky"),
    ],
    "🎂 Birthdays": [
        ("/birthday", "Register your birthday"),
        ("/listbirthdays", "List all saved birthdays"),
        ("/removebirthday", "Remove your own birthday"),
        ("/removeuserbday", "Remove a member's birthday"),
        ("/edituserbday", "Edit a member's birthday"),
        ("/clearallbirthdays", "Clear every saved birthday"),
        ("/testbirthday", "Test the birthday wish instantly"),
        ("/setwishchannel", "Set the birthday announcement channel"),
        ("/setbirthdaysetupchannel", "Set the birthday registration channel"),
    ],
    "🎉 Giveaways & Fun": [
        ("/giveaway", "Create, end, or reroll a giveaway"),
        ("/customcmd", "Create/manage custom !commands"),
        ("/afk", "Set your AFK status"),
    ],
    "💰 Bounty Board": [
        ("/mycharacter", "Join the Bounty Board (first use) or view your character"),
        ("/tutorial", "Learn how the bounty game works"),
        ("/battle", "Challenge another pirate to a bounty battle"),
        ("/bounty", "View your (or someone's) bounty profile"),
        ("/daily", "Claim your daily bounty reward (streak-based)"),
        ("/reroll", "Reroll for a new random character (costs bounty, 24h cooldown)"),
        ("/bountyboard", "See the top bounties in the server"),
        ("/givebounty", "Award bounty to a member (mod only)"),
    ],
}

# Nakama action words are their own thing (not a slash command), shown
# on a dedicated page in the dropdown instead of squeezed into one line.
NAKAMA_ACTIONS = [
    "cry", "hug", "pat", "slap", "punch", "wave", "smile", "dance",
    "poke", "blush", "facepalm", "bonk", "baka", "nom", "bite",
    "highfive", "yeet", "laugh",
]

HELP_EMBED_COLOR = discord.Color.gold()
HELP_TITLE = "🏴‍☠️ Ship's Command Log"
HELP_FOOTER = "Set sail with any command below ⚓"

NAKAMA_CATEGORY_LABEL = "🐾 Nakama Actions"

def build_overview_embed() -> discord.Embed:
    embed = discord.Embed(
        title=HELP_TITLE,
        description="Pick a category from the dropdown below to see what's available.",
        color=HELP_EMBED_COLOR,
    )
    for category, cmds in COMMAND_CATEGORIES.items():
        embed.add_field(name=category, value=f"{len(cmds)} commands", inline=True)
    embed.add_field(name=NAKAMA_CATEGORY_LABEL, value=f"{len(NAKAMA_ACTIONS)} actions", inline=True)
    embed.set_footer(text=HELP_FOOTER)
    return embed

def build_category_embed(category: str) -> discord.Embed:
    embed = discord.Embed(title=f"{HELP_TITLE} — {category}", color=HELP_EMBED_COLOR)

    if category == NAKAMA_CATEGORY_LABEL:
        embed.description = (
            "Start any message with **nakama** followed by one of these words "
            "to trigger a reaction GIF. Mention someone to aim it at them.\n\n"
            "**Example:** `nakama hug @friend`\n\n"
            + ", ".join(f"`{action}`" for action in NAKAMA_ACTIONS)
        )
    else:
        lines = [f"**{name}** — {desc}" for name, desc in COMMAND_CATEGORIES[category]]
        embed.description = "\n".join(lines)

    embed.set_footer(text=HELP_FOOTER)
    return embed

class HelpCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=category, value=category)
            for category in COMMAND_CATEGORIES
        ]
        options.append(discord.SelectOption(label=NAKAMA_CATEGORY_LABEL, value=NAKAMA_CATEGORY_LABEL))
        super().__init__(
            placeholder="📖 Choose a category to browse...",
            options=options,
            custom_id="help:category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        embed = build_category_embed(self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpCategorySelect())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

@bot.tree.command(name="help", description="Show all available bot commands")
async def help_command(interaction: discord.Interaction):
    embed = build_overview_embed()
    view = HelpView()
    await interaction.response.send_message(embed=embed, view=view)


def has_mod_role(interaction: discord.Interaction) -> bool:
    user_roles = [r.name for r in interaction.user.roles]
    return any(role in user_roles for role in ROLE_HIERARCHY)

def get_welcome_channel_id(guild_id: int) -> int:
    return _welcome_channel_override.get(guild_id, WELCOME_CHANNEL_ID)

async def log_action(guild, action, moderator, target, reason=None):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title=f"🔨 {action}", color=discord.Color.red())
        embed.add_field(name="Target", value=str(target), inline=True)
        embed.add_field(name="Moderator", value=str(moderator), inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        await log_channel.send(embed=embed)

def build_welcome_embed(member: discord.Member) -> discord.Embed:
    description = WELCOME_DESCRIPTION.format(
        member=member.mention,
        name=member.display_name,
        count=member.guild.member_count,
    )
    embed = discord.Embed(title=WELCOME_TITLE, description=description, color=WELCOME_COLOR)
    embed.set_thumbnail(url=member.display_avatar.url)

    if WELCOME_CHANNELS:
        channel_chunks = [
            WELCOME_CHANNELS[i:i + CHANNELS_PER_ROW]
            for i in range(0, len(WELCOME_CHANNELS), CHANNELS_PER_ROW)
        ]
        for chunk in channel_chunks:
            for label, ch_id in chunk:
                embed.add_field(name=label, value=f"<#{ch_id}>", inline=True)
            for _ in range(CHANNELS_PER_ROW - len(chunk)):
                embed.add_field(name="\u200b", value="\u200b", inline=True)

    if WELCOME_ROLES:
        role_mentions = " ".join(f"<@&{rid}>" for _, rid in WELCOME_ROLES)
        embed.add_field(name="🎭 Your Roles", value=role_mentions, inline=False)

    embed.set_footer(text="Welcome to the crew! ⚓")
    return embed

def format_timedelta(delta: timedelta) -> str:
    days = delta.days
    years, days = divmod(days, 365)
    months, days = divmod(days, 30)

    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days or not parts:
        parts.append(f"{days} day{'s' if days != 1 else ''}")

    return ", ".join(parts)

# ============================================================================
# BOUNTY BOARD + CHARACTER ROSTER — FINAL VERSION
# Paste this whole block anywhere in bot.py, after `bot = commands.Bot(...)`.
# Requires: json, os, random, datetime/timezone (already imported in bot.py)
# ============================================================================

GITHUB_BASE = "https://raw.githubusercontent.com/gitgoodreal/NakamaBot/main/images"

def make_stages(names_and_urls):
    return [
        {"min_level": lvl, "stage_name": name, "image_url": url, "stage_mult": 1.0 + (i * 0.05)}
        for i, (lvl, name, url) in enumerate(names_and_urls)
    ]

CHARACTERS = [
    {
        "name": "Monkey D. Luffy",
        "rarity": "Legendary",
        "stat_mult": {"attack": 1.25, "defense": 0.95, "speed": 1.05, "hp": 1.0},
        "moves": [
            {"name": "Rubber Pistol",     "power": 45,  "accuracy": 100, "unlock": 1},
            {"name": "Rubber Gatling",    "power": 65,  "accuracy": 90,  "unlock": 10},
            {"name": "Gear Second Rush",  "power": 0,   "accuracy": 100, "unlock": 15, "guard": True},
            {"name": "Red Roc",           "power": 135, "accuracy": 65,  "unlock": 45},
        ],
        "stages": make_stages([
            (1,  "East Blue Straw Hat", f"{GITHUB_BASE}/luffy/level1luffy.jpg"),
            (15, "Alabasta Adventurer", f"{GITHUB_BASE}/luffy/level2luffy.jpg"),
            (30, "Enies Lobby Fighter", f"{GITHUB_BASE}/luffy/level3luffy.jpg"),
            (45, "New World Captain",   f"{GITHUB_BASE}/luffy/level4luffy.jpg"),
            (60, "Awakened Gear Form",  f"{GITHUB_BASE}/luffy/level5luffy.jpg"),
        ]),
    },
    {
        "name": "Roronoa Zoro",
        "rarity": "Rare",
        "stat_mult": {"attack": 1.3, "defense": 1.0, "speed": 0.95, "hp": 0.95},
        "moves": [
            {"name": "Onigiri Slash",      "power": 50,  "accuracy": 95,  "unlock": 1},
            {"name": "Tiger Trap",         "power": 60,  "accuracy": 90,  "unlock": 10},
            {"name": "Iron Stance",        "power": 0,   "accuracy": 100, "unlock": 15, "guard": True},
            {"name": "Three-Sword Cyclone","power": 125, "accuracy": 65,  "unlock": 45},
        ],
        "stages": make_stages([
            (1,  "East Blue Swordsman",     f"{GITHUB_BASE}/zoro/level1zoro.jpg"),
            (15, "Baroque Works Era",       f"{GITHUB_BASE}/zoro/level2zoro.jpg"),
            (30, "Enies Lobby Duelist",     f"{GITHUB_BASE}/zoro/level3zoro.jpg"),
            (45, "Post-Timeskip Swordsman", f"{GITHUB_BASE}/zoro/level4zoro.jpg"),
            (60, "Wano Onigashima Form",    f"{GITHUB_BASE}/zoro/level5zoro.jpg"),
        ]),
    },
    {
        "name": "Sanji",
        "rarity": "Rare",
        "stat_mult": {"attack": 1.15, "defense": 0.95, "speed": 1.2, "hp": 0.95},
        "moves": [
            {"name": "Collier Kick",       "power": 45,  "accuracy": 95,  "unlock": 1},
            {"name": "Diable Step",        "power": 65,  "accuracy": 85,  "unlock": 10},
            {"name": "Sky Guard",          "power": 0,   "accuracy": 100, "unlock": 15, "guard": True},
            {"name": "Blazing Party Kick", "power": 120, "accuracy": 70,  "unlock": 45},
        ],
        "stages": make_stages([
            (1,  "East Blue Cook",         f"{GITHUB_BASE}/sanji/level1sanji.jpg"),
            (15, "Baratie Sous Chef",      f"{GITHUB_BASE}/sanji/level2sanji.jpg"),
            (30, "Enies Lobby Fighter",    f"{GITHUB_BASE}/sanji/level3sanji.jpg"),
            (45, "Post-Timeskip Vinsmoke", f"{GITHUB_BASE}/sanji/level4sanji.jpg"),
            (60, "Ignition Form",          f"{GITHUB_BASE}/sanji/level5sanji.jpg"),
        ]),
    },
    {
        "name": "Nico Robin",
        "rarity": "Rare",
        "stat_mult": {"attack": 1.1, "defense": 1.1, "speed": 0.9, "hp": 1.0},
        "moves": [
            {"name": "Twin Arms",          "power": 45,  "accuracy": 95,  "unlock": 1},
            {"name": "Hundred Fleur",      "power": 70,  "accuracy": 85,  "unlock": 10},
            {"name": "Clutch Guard",       "power": 0,   "accuracy": 100, "unlock": 15, "guard": True},
            {"name": "Gigantesco Mano",    "power": 125, "accuracy": 65,  "unlock": 45},
        ],
        "stages": make_stages([
            (1,  "Baroque Works Agent",     f"{GITHUB_BASE}/robin/level1robin.jpg"),
            (15, "Straw Hat Archaeologist", f"{GITHUB_BASE}/robin/level2robin.jpg"),
            (30, "Enies Lobby Scholar",     f"{GITHUB_BASE}/robin/level3robin.jpg"),
            (45, "Post-Timeskip Robin",     f"{GITHUB_BASE}/robin/level4robin.jpg"),
            (60, "Full Bloom Form",         f"{GITHUB_BASE}/robin/level5robin.jpg"),
        ]),
    },
    {
        "name": "Franky",
        "rarity": "Rare",
        "stat_mult": {"attack": 1.2, "defense": 1.15, "speed": 0.8, "hp": 1.1},
        "moves": [
            {"name": "Strong Hammer",      "power": 50,  "accuracy": 95,  "unlock": 1},
            {"name": "Weapons Left",       "power": 65,  "accuracy": 85,  "unlock": 10},
            {"name": "Iron Body Guard",    "power": 0,   "accuracy": 100, "unlock": 15, "guard": True},
            {"name": "Radical Beam",       "power": 130, "accuracy": 60,  "unlock": 45},
        ],
        "stages": make_stages([
            (1,  "Water 7 Shipwright",      f"{GITHUB_BASE}/franky/level1franky.jpg"),
            (15, "Franky House Boss",       f"{GITHUB_BASE}/franky/level2franky.jpg"),
            (30, "Enies Lobby Cyborg",      f"{GITHUB_BASE}/franky/level3franky.jpg"),
            (45, "General Franky",          f"{GITHUB_BASE}/franky/level4franky.jpg"),
            (60, "Radical Overhaul",        f"{GITHUB_BASE}/franky/level5franky.jpg"),
        ]),
    },
    {
        "name": "Nami",
        "rarity": "Common",
        "stat_mult": {"attack": 0.85, "defense": 0.85, "speed": 1.3, "hp": 0.9},
        "moves": [
            {"name": "Weather Staff Jab",  "power": 35,  "accuracy": 100, "unlock": 1},
            {"name": "Thunderbolt Tempo",  "power": 60,  "accuracy": 85,  "unlock": 10},
            {"name": "Mirage Guard",       "power": 0,   "accuracy": 100, "unlock": 15, "guard": True},
            {"name": "Thunder Lance",      "power": 110, "accuracy": 70,  "unlock": 45},
        ],
        "stages": make_stages([
            (1,  "East Blue Navigator",     f"{GITHUB_BASE}/nami/level1nami.jpg"),
            (15, "Baroque Works Era",       f"{GITHUB_BASE}/nami/level2nami.jpg"),
            (30, "Enies Lobby Navigator",   f"{GITHUB_BASE}/nami/level3nami.jpg"),
            (45, "Post-Timeskip Nami",      f"{GITHUB_BASE}/nami/level4nami.jpg"),
            (60, "Zeus-Empowered Form",     f"{GITHUB_BASE}/nami/level5nami.jpg"),
        ]),
    },
    {
        "name": "Usopp",
        "rarity": "Common",
        "stat_mult": {"attack": 0.9, "defense": 0.9, "speed": 1.15, "hp": 0.9},
        "moves": [
            {"name": "Sling Shot",         "power": 35,  "accuracy": 100, "unlock": 1},
            {"name": "Green Star Barrage", "power": 55,  "accuracy": 90,  "unlock": 10},
            {"name": "Smokescreen Guard",  "power": 0,   "accuracy": 100, "unlock": 15, "guard": True},
            {"name": "Fire Bird Star",     "power": 105, "accuracy": 70,  "unlock": 45},
        ],
        "stages": make_stages([
            (1,  "East Blue Sniper",        f"{GITHUB_BASE}/usopp/level1ussop.jpg"),
            (15, "Baroque Works Era",       f"{GITHUB_BASE}/usopp/level2ussop.jpg"),
            (30, "Enies Lobby Sogeking",    f"{GITHUB_BASE}/usopp/level3ussop.jpg"),
            (45, "Post-Timeskip Sniper",    f"{GITHUB_BASE}/usopp/level4ussop.jpg"),
            (60, "Pop Green Master",        f"{GITHUB_BASE}/usopp/level5ussop.jpg"),
        ]),
    },
    {
        "name": "Tony Tony Chopper",
        "rarity": "Common",
        "stat_mult": {"attack": 0.95, "defense": 1.0, "speed": 1.0, "hp": 1.05},
        "moves": [
            {"name": "Hoof Jab",           "power": 40,  "accuracy": 100, "unlock": 1},
            {"name": "Guard Point Charge", "power": 55,  "accuracy": 90,  "unlock": 10},
            {"name": "Heavy Point Guard",  "power": 0,   "accuracy": 100, "unlock": 15, "guard": True},
            {"name": "Monster Point Rush", "power": 110, "accuracy": 70,  "unlock": 45},
        ],
        "stages": make_stages([
            (1,  "Ship's Doctor",           f"{GITHUB_BASE}/chopper/level1choppa.jpg"),
            (15, "Baroque Works Era",       f"{GITHUB_BASE}/chopper/level2choppa.jpg"),
            (30, "Enies Lobby Rumble Ball", f"{GITHUB_BASE}/chopper/level3choppa.jpg"),
            (45, "Post-Timeskip Doctor",    f"{GITHUB_BASE}/chopper/level4choppa.jpg"),
            (60, "Monster Point",           f"{GITHUB_BASE}/chopper/level5choppa.jpg"),
        ]),
    },
]

RARITY_WEIGHTS = {"Common": 60, "Rare": 32, "Legendary": 8}

def roll_character() -> dict:
    weights = [RARITY_WEIGHTS[c["rarity"]] for c in CHARACTERS]
    return random.choices(CHARACTERS, weights=weights, k=1)[0]

def get_character(name: str) -> dict:
    for c in CHARACTERS:
        if c["name"] == name:
            return c
    return CHARACTERS[0]

def get_character_stage(character: dict, level: int) -> dict:
    current = character["stages"][0]
    for stage in character["stages"]:
        if level >= stage["min_level"]:
            current = stage
        else:
            break
    return current

def get_stage_index(character: dict, level: int) -> int:
    return character["stages"].index(get_character_stage(character, level))


# ── Bounty profile storage ───────────────────────────────────────────────────

BOUNTY_FILE = "bounty_config.json"
BOUNTY_DATA = {}

def default_bounty_profile() -> dict:
    character = roll_character()
    return {
        "bounty": 500_000,
        "level": 1,
        "xp": 0,
        "wins": 0,
        "losses": 0,
        "last_attack": 0,
        "last_reroll": 0,
        "last_chat_xp": 0,
        "last_daily": 0,
        "daily_streak": 0,
        "character": character["name"],
    }

def save_bounty_data():
    with open(BOUNTY_FILE, "w") as f:
        json.dump(BOUNTY_DATA, f, indent=2)

def load_bounty_data():
    global BOUNTY_DATA
    if os.path.exists(BOUNTY_FILE):
        with open(BOUNTY_FILE) as f:
            BOUNTY_DATA = json.load(f)
        print(f"✅ Loaded bounty data for {len(BOUNTY_DATA)} user(s)")

load_bounty_data()

def get_bounty_profile(user_id: int):
    """Returns the profile if this user has started playing, else None. Does NOT auto-create."""
    return BOUNTY_DATA.get(str(user_id))

def create_bounty_profile(user_id: int) -> dict:
    """Explicitly enrolls a user."""
    uid = str(user_id)
    profile = default_bounty_profile()
    BOUNTY_DATA[uid] = profile
    save_bounty_data()
    return profile

def ensure_bounty_profile(user_id: int):
    """Returns (profile, is_new). Creates a profile on first use if one doesn't exist yet."""
    existing = get_bounty_profile(user_id)
    if existing is not None:
        return existing, False
    return create_bounty_profile(user_id), True

BOUNTY_RANKS = [
    (0,             "🐣 Rookie"),
    (1_000_000,     "🌊 East Blue Pirate"),
    (10_000_000,    "⚔️ Grand Line Pirate"),
    (50_000_000,    "🔥 Supernova"),
    (100_000_000,   "🏴‍☠️ Warlord-Class"),
    (500_000_000,   "👑 Yonko Commander"),
    (1_000_000_000, "🌟 Emperor of the Sea"),
]

def get_bounty_rank(bounty: int) -> str:
    rank = BOUNTY_RANKS[0][1]
    for threshold, name in BOUNTY_RANKS:
        if bounty >= threshold:
            rank = name
        else:
            break
    return rank

def xp_for_level(level: int) -> int:
    return level * 100

def add_bounty_xp(profile: dict, amount: int) -> list:
    profile["xp"] += amount
    levels_gained = []
    while profile["xp"] >= xp_for_level(profile["level"]):
        profile["xp"] -= xp_for_level(profile["level"])
        profile["level"] += 1
        levels_gained.append(profile["level"])
    return levels_gained

def get_battle_stats(level: int, character_name: str) -> dict:
    char = get_character(character_name)
    stage = get_character_stage(char, level)
    mult = char["stat_mult"]
    boost = stage["stage_mult"]
    base = {
        "max_hp": 50 + level * 12,
        "attack": 10 + level * 3,
        "defense": 8 + level * 2,
        "speed": 10 + level * 2,
    }
    return {
        "max_hp": int(base["max_hp"] * mult["hp"] * boost),
        "attack": int(base["attack"] * mult["attack"] * boost),
        "defense": int(base["defense"] * mult["defense"] * boost),
        "speed": int(base["speed"] * mult["speed"] * boost),
    }

def available_bounty_moves(level: int, character_name: str) -> list:
    char = get_character(character_name)
    unlocked = [m for m in char["moves"] if m["unlock"] <= level]
    return unlocked[-4:]

BATTLE_COOLDOWN_SECONDS = 3600
STEAL_PERCENT = 0.10

CHAT_XP_COOLDOWN_SECONDS = 60  # per-user cooldown between XP-earning messages
CHAT_XP_MIN = 5
CHAT_XP_MAX = 15

async def on_message_chat_xp(message: discord.Message):
    """Awards small random XP for chatting, on a per-user cooldown to prevent spam farming."""
    if message.author.bot or not message.guild:
        return

    profile = get_bounty_profile(message.author.id)
    if profile is None:
        return  # hasn't joined the Bounty Board — no passive XP for non-players

    now = datetime.now(timezone.utc).timestamp()
    if now - profile.get("last_chat_xp", 0) < CHAT_XP_COOLDOWN_SECONDS:
        return

    profile["last_chat_xp"] = now
    char = get_character(profile["character"])
    pre_level = profile["level"]

    gained = random.randint(CHAT_XP_MIN, CHAT_XP_MAX)
    levels_gained = add_bounty_xp(profile, gained)
    save_bounty_data()

    if levels_gained:
        old_stage = get_character_stage(char, pre_level)
        new_stage = get_character_stage(char, profile["level"])
        if new_stage != old_stage:
            try:
                await message.channel.send(
                    f"🌟 {message.author.mention}'s **{char['name']}** evolved into their "
                    f"**{new_stage['stage_name']}** look! (Now Lv.{profile['level']})"
                )
            except discord.Forbidden:
                pass


class MoveButton(discord.ui.Button):
    def __init__(self, move: dict):
        style = discord.ButtonStyle.secondary if move.get("guard") else discord.ButtonStyle.danger
        super().__init__(label=move["name"], style=style)
        self.move = move

    async def callback(self, interaction: discord.Interaction):
        view: "BountyBattleView" = self.view
        await view.apply_move(interaction, self.move)


class BountyBattleView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, profile1: dict, profile2: dict):
        super().__init__(timeout=90)
        self.players = {
            challenger.id: {"user": challenger, "profile": profile1},
            opponent.id:   {"user": opponent,   "profile": profile2},
        }
        stats1 = get_battle_stats(profile1["level"], profile1["character"])
        stats2 = get_battle_stats(profile2["level"], profile2["character"])
        self.stats = {challenger.id: stats1, opponent.id: stats2}
        self.hp = {challenger.id: stats1["max_hp"], opponent.id: stats2["max_hp"]}
        self.max_hp = {challenger.id: stats1["max_hp"], opponent.id: stats2["max_hp"]}
        self.guarding = {challenger.id: False, opponent.id: False}
        self.turn_order = [challenger.id, opponent.id] if stats1["speed"] >= stats2["speed"] else [opponent.id, challenger.id]
        self.turn_index = 0
        self.log = []
        self.message = None
        self.build_buttons()

    @property
    def current_id(self):
        return self.turn_order[self.turn_index % 2]

    @property
    def other_id(self):
        return self.turn_order[(self.turn_index + 1) % 2]

    def build_buttons(self):
        self.clear_items()
        profile = self.players[self.current_id]["profile"]
        for move in available_bounty_moves(profile["level"], profile["character"]):
            self.add_item(MoveButton(move))

    def hp_bar(self, uid: int, length: int = 10) -> str:
        pct = max(self.hp[uid], 0) / self.max_hp[uid]
        filled = round(pct * length)
        return "🟩" * filled + "⬛" * (length - filled)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title="⚔️ Bounty Battle!", color=discord.Color.gold())
        for uid in self.turn_order:
            user = self.players[uid]["user"]
            char = get_character(self.players[uid]["profile"]["character"])
            embed.add_field(
                name=f"{user.display_name} ({char['name']})",
                value=f"{self.hp_bar(uid)}\n{max(self.hp[uid], 0)}/{self.max_hp[uid]} HP",
                inline=True,
            )
        if self.log:
            embed.description = "\n".join(self.log[-4:])
        embed.set_footer(text=f"{self.players[self.current_id]['user'].display_name}'s turn — choose a move")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.current_id:
            await interaction.response.send_message("⏳ It's not your turn!", ephemeral=True)
            return False
        return True

    async def apply_move(self, interaction: discord.Interaction, move: dict):
        attacker_id, defender_id = self.current_id, self.other_id
        attacker_name = self.players[attacker_id]["user"].display_name
        defender_name = self.players[defender_id]["user"].display_name

        if move.get("guard"):
            self.guarding[attacker_id] = True
            self.log.append(f"🛡️ {attacker_name} used **{move['name']}**! Damage reduced next turn.")
        else:
            hit = random.randint(1, 100) <= move["accuracy"]
            if not hit:
                self.log.append(f"💨 {attacker_name} used **{move['name']}** but missed!")
            else:
                atk = self.stats[attacker_id]["attack"]
                dfn = self.stats[defender_id]["defense"]
                variance = random.uniform(0.85, 1.0)
                dmg = max(1, int(((move["power"] * atk / dfn) / 3) * variance))
                if self.guarding[defender_id]:
                    dmg //= 2
                    self.guarding[defender_id] = False
                self.hp[defender_id] = max(0, self.hp[defender_id] - dmg)
                self.log.append(f"💥 {attacker_name} used **{move['name']}** — {dmg} damage to {defender_name}!")

        if self.hp[defender_id] <= 0:
            await self.end_battle(interaction, winner_id=attacker_id, loser_id=defender_id)
            return

        self.turn_index += 1
        self.build_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def end_battle(self, interaction: discord.Interaction, winner_id: int, loser_id: int):
        winner = self.players[winner_id]["user"]
        loser = self.players[loser_id]["user"]
        winner_profile = self.players[winner_id]["profile"]
        loser_profile = self.players[loser_id]["profile"]

        winner_char = get_character(winner_profile["character"])
        pre_battle_level = winner_profile["level"]

        stolen = int(loser_profile["bounty"] * STEAL_PERCENT)
        loser_profile["bounty"] = max(0, loser_profile["bounty"] - stolen)
        winner_profile["bounty"] += stolen
        winner_profile["wins"] += 1
        loser_profile["losses"] += 1
        levels_gained = add_bounty_xp(winner_profile, 50)
        add_bounty_xp(loser_profile, 15)
        save_bounty_data()

        self.log.append(f"🏆 **{winner.display_name} wins the battle!**")
        self.log.append(f"💰 Stole ฿{stolen:,} from {loser.display_name}!")
        if levels_gained:
            self.log.append(f"⬆️ {winner.display_name} leveled up to Lv.{levels_gained[-1]}!")
            old_stage = get_character_stage(winner_char, pre_battle_level)
            new_stage = get_character_stage(winner_char, winner_profile["level"])
            if new_stage != old_stage:
                self.log.append(f"🌟 {winner.display_name}'s **{winner_char['name']}** evolved into their **{new_stage['stage_name']}** look!")

        embed = self.build_embed()
        embed.description = "\n".join(self.log[-6:])
        embed.set_footer(text="Battle ended")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class BattleChallengeView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚔️ Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        profile1 = get_bounty_profile(self.challenger.id)
        profile2 = get_bounty_profile(self.opponent.id)
        battle_view = BountyBattleView(self.challenger, self.opponent, profile1, profile2)
        await interaction.response.edit_message(content=None, embed=battle_view.build_embed(), view=battle_view)
        battle_view.message = await interaction.original_response()
        self.stop()

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content=f"{self.opponent.display_name} declined the challenge.", embed=None, view=None)
        self.stop()


# ── Slash commands ───────────────────────────────────────────────────────────


@bot.tree.command(name="battle", description="Challenge another pirate to a bounty battle!")
@app_commands.describe(opponent="Who do you want to battle?")
async def battle(interaction: discord.Interaction, opponent: discord.Member):
    if opponent.id == interaction.user.id:
        await interaction.response.send_message("❌ You can't battle yourself!", ephemeral=True)
        return
    if opponent.bot:
        await interaction.response.send_message("❌ You can't battle a bot!", ephemeral=True)
        return

    profile = get_bounty_profile(interaction.user.id)
    if profile is None:
        await interaction.response.send_message(
            "❌ You haven't joined the Bounty Board yet! Use `/mycharacter` first.", ephemeral=True
        )
        return
    if get_bounty_profile(opponent.id) is None:
        await interaction.response.send_message(
            f"❌ {opponent.display_name} hasn't joined the Bounty Board yet — they need to use `/mycharacter` first.",
            ephemeral=True,
        )
        return

    now = datetime.now(timezone.utc).timestamp()
    remaining = BATTLE_COOLDOWN_SECONDS - (now - profile.get("last_attack", 0))
    if remaining > 0:
        mins = int(remaining // 60) + 1
        await interaction.response.send_message(f"⏳ You're still recovering! Try again in **{mins} minute(s)**.", ephemeral=True)
        return

    profile["last_attack"] = now
    save_bounty_data()

    view = BattleChallengeView(interaction.user, opponent)
    await interaction.response.send_message(
        f"⚔️ {opponent.mention}, **{interaction.user.display_name}** has challenged you to a bounty battle! Accept?",
        view=view,
    )

@bot.tree.command(name="bounty", description="View your bounty profile, or someone else's")
@app_commands.describe(user="Whose profile to view (leave blank for yourself)")
async def bounty(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    profile = get_bounty_profile(target.id)
    if profile is None:
        if target.id == interaction.user.id:
            await interaction.response.send_message(
                "You haven't joined the Bounty Board yet! Use `/mycharacter` to get your first bounty.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(f"{target.display_name} hasn't joined the Bounty Board yet.", ephemeral=True)
        return
    stats = get_battle_stats(profile["level"], profile["character"])
    rank = get_bounty_rank(profile["bounty"])
    char = get_character(profile["character"])
    stage = get_character_stage(char, profile["level"])

    embed = discord.Embed(title=f"🏴‍☠️ {target.display_name}'s Bounty Poster", color=discord.Color.gold())
    embed.set_thumbnail(url=stage["image_url"])
    embed.add_field(name="💰 Bounty", value=f"฿{profile['bounty']:,}", inline=True)
    embed.add_field(name="🎖️ Rank", value=rank, inline=True)
    embed.add_field(name="📊 Level", value=f"Lv. {profile['level']}", inline=True)
    embed.add_field(name="⚔️ Record", value=f"{profile['wins']}W - {profile['losses']}L", inline=True)
    embed.add_field(name="🎴 Character", value=f"{char['name']} — *{stage['stage_name']}*", inline=True)
    embed.add_field(name="❤️ Max HP", value=str(stats["max_hp"]), inline=True)
    embed.add_field(name="🗡️ ATK / 🛡️ DEF", value=f"{stats['attack']} / {stats['defense']}", inline=True)
    embed.add_field(name="✨ XP", value=f"{profile['xp']}/{xp_for_level(profile['level'])}", inline=False)
    embed.set_footer(text="Fight other pirates with /battle to grow your bounty!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="mycharacter", description="View your assigned One Piece character")
async def mycharacter(interaction: discord.Interaction):
    profile = get_bounty_profile(interaction.user.id)
    is_new = profile is None
    if is_new:
        profile = create_bounty_profile(interaction.user.id)

    char = get_character(profile["character"])
    stage = get_character_stage(char, profile["level"])

    embed = discord.Embed(title=f"🎴 {char['name']} — {stage['stage_name']}", color=discord.Color.gold())
    if is_new:
        embed.description = (
            f"🏴‍☠️ You've set sail! Starting bounty: **฿{profile['bounty']:,}**\n"
            f"To check the top pirates in the server, use `/bountyboard`."
        )
    embed.add_field(name="Rarity", value=char["rarity"], inline=True)
    embed.add_field(name="Level", value=f"Lv. {profile['level']}", inline=True)
    embed.set_image(url=stage["image_url"])
    roadmap = "\n".join(
        f"{'✅' if profile['level'] >= s['min_level'] else '🔒'} Lv.{s['min_level']} — {s['stage_name']}"
        for s in char["stages"]
    )
    embed.add_field(name="Evolution Roadmap", value=roadmap, inline=False)
    move_list = "\n".join(f"• {m['name']}" for m in char["moves"])
    embed.add_field(name="Moves", value=move_list, inline=False)
    await interaction.response.send_message(embed=embed)

REROLL_COOLDOWN_SECONDS = 24 * 3600  # 24 hours
REROLL_COST = 100_000

@bot.tree.command(name="reroll", description="Reroll for a new random character (costs bounty, 7-day cooldown)")
async def reroll(interaction: discord.Interaction):
    profile = get_bounty_profile(interaction.user.id)
    if profile is None:
        await interaction.response.send_message(
            "❌ You haven't joined the Bounty Board yet! Use `/mycharacter` first.", ephemeral=True
        )
        return
    now = datetime.now(timezone.utc).timestamp()
    remaining = REROLL_COOLDOWN_SECONDS - (now - profile.get("last_reroll", 0))

    if remaining > 0:
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        await interaction.response.send_message(
            f"⏳ You can reroll again in **{hours}h {minutes}m**.", ephemeral=True
        )
        return

    if profile["bounty"] < REROLL_COST:
        await interaction.response.send_message(
            f"❌ Rerolling costs ฿{REROLL_COST:,}, but you only have ฿{profile['bounty']:,}.", ephemeral=True
        )
        return

    old_character = get_character(profile["character"])
    new_character = roll_character()
    profile["bounty"] -= REROLL_COST
    profile["character"] = new_character["name"]
    profile["last_reroll"] = now
    save_bounty_data()

    embed = discord.Embed(
        title="🎲 Reroll Complete!",
        description=(
            f"You spent ฿{REROLL_COST:,} and rerolled from **{old_character['name']}** "
            f"to **{new_character['name']}** ({new_character['rarity']})!"
        ),
        color=discord.Color.gold(),
    )
    stage = get_character_stage(new_character, profile["level"])
    embed.set_thumbnail(url=stage["image_url"])
    embed.set_footer(text="Your level, XP, and bounty stay the same — only your character changed.")
    await interaction.response.send_message(embed=embed)

DAILY_COOLDOWN_SECONDS = 24 * 3600  # 24 hours between claims
DAILY_BASE_REWARD = 50_000
DAILY_STREAK_INCREMENT = 20_000

@bot.tree.command(name="daily", description="Claim your daily bounty reward — streak grows the longer you keep it up!")
async def daily(interaction: discord.Interaction):
    profile = get_bounty_profile(interaction.user.id)
    if profile is None:
        await interaction.response.send_message(
            "❌ You haven't joined the Bounty Board yet! Use `/mycharacter` first.", ephemeral=True
        )
        return

    now = datetime.now(timezone.utc).timestamp()
    remaining = DAILY_COOLDOWN_SECONDS - (now - profile.get("last_daily", 0))
    if remaining > 0:
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        await interaction.response.send_message(
            f"⏳ You've already claimed today! Come back in **{hours}h {minutes}m**.", ephemeral=True
        )
        return

    profile["daily_streak"] = profile.get("daily_streak", 0) + 1
    streak = profile["daily_streak"]
    reward = DAILY_BASE_REWARD + DAILY_STREAK_INCREMENT * (streak - 1)
    profile["bounty"] += reward
    profile["last_daily"] = now
    save_bounty_data()

    embed = discord.Embed(
        title="🎁 Daily Bounty Claimed!",
        description=(
            f"You earned **฿{reward:,}**!\n\n"
            f"🔥 Streak: **Day {streak}**\n"
            f"💰 New bounty: ฿{profile['bounty']:,}"
        ),
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Come back in 24 hours to keep your streak going — missed days don't reset it!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="bountyboard", description="See the top bounties in the server")
async def bountyboard(interaction: discord.Interaction):
    sorted_users = sorted(BOUNTY_DATA.items(), key=lambda x: x[1]["bounty"], reverse=True)[:10]
    if not sorted_users:
        await interaction.response.send_message("No bounties recorded yet — go battle someone with /battle!")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, profile) in enumerate(sorted_users):
        medal = medals[i] if i < 3 else f"{i + 1}."
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"Unknown ({uid})"
        lines.append(f"{medal} **{name}** — ฿{profile['bounty']:,} ({get_bounty_rank(profile['bounty'])})")
    embed = discord.Embed(title="📋 THE BOUNTY BOARD", description="\n".join(lines), color=discord.Color.gold())
    embed.set_footer(text="Most wanted pirates in the crew")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="givebounty", description="Award bounty to a member (mod only)")
@app_commands.describe(user="Member to award bounty to", amount="Amount of bounty to add")
async def givebounty(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    profile = get_bounty_profile(user.id)
    if profile is None:
        profile = create_bounty_profile(user.id)
    profile["bounty"] += amount
    save_bounty_data()
    await interaction.response.send_message(f"✅ Gave ฿{amount:,} to {user.mention}. New bounty: ฿{profile['bounty']:,}", ephemeral=True)


# ============================================================================
# /tutorial COMMAND — nested dropdown tutorial for the bounty game.
# Paste this AFTER the bounty/character roster block (it uses CHARACTERS,
# get_character, BOUNTY_RANKS which are defined there), and before the
# "# ── Events" section.
# ============================================================================

TUTORIAL_STATIC_PAGES = {
    "how_to_play": {
        "title": "📖 How to Play",
        "description": (
            "**1.** Use `/mycharacter` to join — you'll be randomly assigned a One Piece "
            "character and a starting bounty of ฿500,000, automatically, the first time you run it.\n"
            "**1b.** Don't like your character? `/reroll` gets you a new random one for "
            "฿100,000, once every 24 hours. Your level, XP, and bounty carry over unchanged.\n"
            "**2.** Check your profile anytime with `/bounty` or `/mycharacter`.\n"
            "**2b.** Claim `/daily` every 24 hours for free bounty — ฿50,000 base, "
            "+฿20,000 for every extra day in your streak. Missing a day doesn't reset your streak.\n"
            "**3.** Challenge others with `/battle @user` to fight for bounty.\n"
            "**4.** Winning steals 10% of the loser's bounty and gives you more XP.\n"
            "**5.** XP levels you up — new moves unlock at Lv.10, 15, and 45. You earn XP "
            "from winning/losing battles, **and** a small amount just from chatting in the server "
            "(once per minute, so spamming won't farm it faster).\n"
            "**6.** Leveling also evolves your character's look at Lv.15, 30, 45, and 60.\n"
            "**7.** One battle challenge per hour, win or lose.\n"
            "**8.** Check `/bountyboard` anytime to see the top pirates in the server."
        ),
    },
    "battle_basics": {
        "title": "⚔️ Battle Basics",
        "description": (
            "**Turn order:** Whoever has higher Speed goes first each battle.\n\n"
            "**Moves:** Each turn you pick from up to 4 unlocked moves. Most deal damage; "
            "one per character is a **Guard** move that halves incoming damage on the opponent's next hit.\n\n"
            "**Accuracy:** Every move has a hit chance — stronger moves tend to miss more often, "
            "so it's a risk/reward choice each turn.\n\n"
            "**Winning:** First to reduce the opponent's HP to 0 wins. You'll steal 10% of their "
            "bounty and gain 50 XP (the loser still gets 15 XP just for fighting).\n\n"
            "**Cooldown:** After you challenge someone, you can't challenge again for 1 hour — "
            "win or lose."
        ),
    },
}

def build_ranks_tutorial_embed() -> discord.Embed:
    lines = [f"**{name}** — starts at ฿{threshold:,}" for threshold, name in BOUNTY_RANKS]
    embed = discord.Embed(title="🎖️ Ranks & Bounty", description="\n".join(lines), color=discord.Color.gold())
    embed.set_footer(text="Your rank updates automatically based on your current bounty.")
    return embed

def describe_stat(value: float) -> str:
    if value >= 1.2:
        return "🔥 High"
    if value >= 1.05:
        return "⬆️ Above Average"
    if value >= 0.95:
        return "➖ Average"
    return "⬇️ Low"

def build_character_tutorial_embed(character: dict) -> discord.Embed:
    mult = character["stat_mult"]
    embed = discord.Embed(title=f"🎴 {character['name']} — {character['rarity']}", color=discord.Color.gold())
    embed.set_thumbnail(url=character["stages"][0]["image_url"])
    embed.add_field(
        name="Stat Profile",
        value=(
            f"🗡️ Attack: {describe_stat(mult['attack'])}\n"
            f"🛡️ Defense: {describe_stat(mult['defense'])}\n"
            f"⚡ Speed: {describe_stat(mult['speed'])}\n"
            f"❤️ HP: {describe_stat(mult['hp'])}"
        ),
        inline=True,
    )
    move_lines = []
    for m in character["moves"]:
        if m.get("guard"):
            move_lines.append(f"🛡️ **{m['name']}** — unlocks Lv.{m['unlock']} (halves next hit)")
        else:
            move_lines.append(f"⚔️ **{m['name']}** — unlocks Lv.{m['unlock']} (Power {m['power']}, Accuracy {m['accuracy']}%)")
    embed.add_field(name="Moveset", value="\n".join(move_lines), inline=False)
    stage_lines = [f"Lv.{s['min_level']} — {s['stage_name']}" for s in character["stages"]]
    embed.add_field(name="Evolution Stages", value="\n".join(stage_lines), inline=False)
    embed.set_footer(text="Use /mycharacter to see YOUR progress if you have this character.")
    return embed


class CharacterTutorialSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=c["name"], description=c["rarity"], value=c["name"])
            for c in CHARACTERS
        ]
        super().__init__(placeholder="🎴 Pick a character to see their moves...", options=options)

    async def callback(self, interaction: discord.Interaction):
        character = get_character(self.values[0])
        embed = build_character_tutorial_embed(character)
        await interaction.response.edit_message(embed=embed, view=self.view)


class TutorialCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="📖 How to Play", value="how_to_play"),
            discord.SelectOption(label="⚔️ Battle Basics", value="battle_basics"),
            discord.SelectOption(label="🎖️ Ranks & Bounty", value="ranks_bounty"),
            discord.SelectOption(label="🎴 Characters & Movesets", value="characters"),
        ]
        super().__init__(placeholder="📚 Choose a topic...", options=options)

    async def callback(self, interaction: discord.Interaction):
        view: "TutorialView" = self.view
        await view.show_category(interaction, self.values[0])


class TutorialView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.category_select = TutorialCategorySelect()
        self.add_item(self.category_select)

    async def show_category(self, interaction: discord.Interaction, category: str):
        self.clear_items()
        self.add_item(self.category_select)

        if category == "characters":
            self.add_item(CharacterTutorialSelect())
            embed = discord.Embed(
                title="🎴 Characters & Movesets",
                description="Pick a character below to see their full stat profile, moves, and evolution roadmap.",
                color=discord.Color.gold(),
            )
        elif category == "ranks_bounty":
            embed = build_ranks_tutorial_embed()
        else:
            page = TUTORIAL_STATIC_PAGES[category]
            embed = discord.Embed(title=page["title"], description=page["description"], color=discord.Color.gold())

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


@bot.tree.command(name="tutorial", description="Learn how to play the Bounty Board game")
async def tutorial(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Bounty Board Tutorial",
        description=(
            "New to the bounty game? Pick a topic below to learn the ropes:\n\n"
            "📖 **How to Play** — the full game loop\n"
            "⚔️ **Battle Basics** — how fights actually work\n"
            "🎖️ **Ranks & Bounty** — what your bounty amount means\n"
            "🎴 **Characters & Movesets** — every character's stats and moves"
        ),
        color=discord.Color.gold(),
    )
    view = TutorialView()
    await interaction.response.send_message(embed=embed, view=view)


# ── Events ─────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    load_sticky_config()
    bot.add_view(AddBirthdayView())
    bot.loop.create_task(birthday_checker())
    await bot.tree.sync()

    await asyncio.sleep(3)

    for channel_id, config in list(STICKY_CONFIG.items()):
        try:
            channel = bot.get_channel(channel_id)
            if not channel:
                continue
            try:
                await channel.fetch_message(config["last_id"])
            except discord.NotFound:
                msg_text = config.get("message", "")
                style = config.get("style", "plain")
                if style == "embed":
                    embed = discord.Embed(description=msg_text, color=discord.Color.gold())
                    embed.set_footer(text="\U0001f4cc Sticky Message")
                    sent = await channel.send(embed=embed)
                else:
                    sent = await channel.send(msg_text)
                STICKY_CONFIG[channel_id]["last_id"] = sent.id
                save_sticky_config()
                print(f"✅ Reposted sticky in #{channel.name}")
        except Exception as e:
            print(f"⚠️ Could not repost sticky in channel {channel_id}: {e}")
    print(f"✅ {bot.user} is online! Synced slash commands globally.")

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild

    channel_id = get_welcome_channel_id(guild.id)
    channel = guild.get_channel(channel_id)
    if channel:
        embed = build_welcome_embed(member)
        await channel.send(content=member.mention, embed=embed)

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    channel_id = get_welcome_channel_id(guild.id)
    channel = guild.get_channel(channel_id)
    if not channel:
        return
    if member.joined_at:
        time_in_server = format_timedelta(datetime.now(timezone.utc) - member.joined_at)
        time_text = f"They were with us for **{time_in_server}**."
    else:
        time_text = ""
    await channel.send(
        f"👋 **{member.display_name}** has left the server. "
        f"We're now at **{guild.member_count}** crew member{'s' if guild.member_count != 1 else ''}. "
        f"{time_text}"
    )

spam_tracker = {}

# ── Nakama GIF system ──────────────────────────────────────────────────────────
NAKAMA_GIF_MAP = {
    "cry":      "cry",
    "crying":   "cry",
    "hug":      "hug",
    "hugs":     "hug",
    "pat":      "pat",
    "pats":     "pat",
    "slap":     "slap",
    "slaps":    "slap",
    "punch":    "punch",
    "punches":  "punch",
    "wave":     "wave",
    "waving":   "wave",
    "smile":    "smile",
    "smiling":  "smile",
    "happy":    "smile",
    "dance":    "dance",
    "dancing":  "dance",
    "poke":     "poke",
    "poking":   "poke",
    "blush":    "blush",
    "blushing": "blush",
    "facepalm": "facepalm",
    "bonk":     "bonk",
    "bonks":    "bonk",
    "baka":     "baka",
    "nom":      "nom",
    "bite":     "bite",
    "bites":    "bite",
    "highfive": "highfive",
    "yeet":     "yeet",
    "laugh":    "laugh",
    "laughing": "laugh",
}

NAKAMA_GIF_MESSAGES = {
    "cry":       ("😢 {author} is crying...", "😢 {author} cries on {target}'s shoulder..."),
    "hug":       ("🤗 {author} hugs the air!", "There there~ 🤗 {author} hugs {target}!"),
    "pat":       ("👋 {author} pats themselves?", "( ´ ▽ ` ) {author} pats {target}!"),
    "slap":      ("👋 {author} slaps the air!", "👋 {author} slaps {target}! Ouch!"),
    "punch":     ("👊 {author} punches the air!", "👊 {author} punches {target}! BAM!"),
    "wave":      ("👋 {author} waves!", "👋 {author} waves at {target}!"),
    "smile":     ("😊 {author} smiles!", "😊 {author} smiles at {target}!"),
    "dance":     ("💃 {author} is dancing!", "💃 {author} dances with {target}!"),
    "poke":      ("👉 {author} pokes the air!", "👉 {author} pokes {target}!"),
    "blush":     ("😳 {author} is blushing!", "😳 {author} blushes at {target}!"),
    "facepalm":  ("🤦 {author} facepalms!", "🤦 {author} facepalms at {target}..."),
    "bonk":      ("🔨 {author} bonks the air!", "🔨 {author} bonks {target}! No horny!"),
    "baka":      ("😤 {author} calls someone baka!", "😤 {author} calls {target} a baka!"),
    "nom":       ("😋 {author} noms!", "😋 {author} noms {target}!"),
    "bite":      ("😬 {author} bites the air!", "😬 {author} bites {target}!"),
    "highfive":  ("🙌 {author} wants a high five!", "🙌 {author} high fives {target}!"),
    "yeet":      ("🌀 {author} yeeted themselves!", "🌀 {author} yeets {target} into the sky!"),
    "laugh":     ("😂 {author} is laughing!", "😂 {author} laughs at {target}!"),
}

# ── Klipy GIF fetching (replaces old waifu.pics source) ─────────────────────
NAKAMA_KLIPY_QUERY = {
    "cry":      "anime crying",
    "hug":      "anime hug",
    "pat":      "anime headpat",
    "slap":     "anime slap",
    "punch":    "anime punch",
    "wave":     "anime wave hello",
    "smile":    "anime smile",
    "dance":    "anime dance",
    "poke":     "anime poke",
    "blush":    "anime blush",
    "facepalm": "anime facepalm",
    "bonk":     "anime bonk",
    "baka":     "anime baka",
    "nom":      "anime eating cute",
    "bite":     "anime bite",
    "highfive": "anime high five",
    "yeet":     "anime yeet throw",
    "laugh":    "anime laughing",
}

def _find_media_url(node):
    """
    Recursively search a Klipy result item for a usable media URL.
    Klipy nests GIF variants inside a 'files' object but the exact keys
    aren't fixed publicly, so this walks the structure instead of hardcoding
    a path. Prefers URLs that look like actual media files (gif/mp4/webp).
    """
    if isinstance(node, str):
        if node.startswith("http") and any(node.lower().split("?")[0].endswith(ext) for ext in (".gif", ".mp4", ".webp", ".webm")):
            return node
        return None
    if isinstance(node, dict):
        if "url" in node and isinstance(node["url"], str):
            found = _find_media_url(node["url"])
            if found:
                return found
        for key in ("gif", "md", "sm", "hd", "sd", "original", "files"):
            if key in node:
                found = _find_media_url(node[key])
                if found:
                    return found
        for value in node.values():
            found = _find_media_url(value)
            if found:
                return found
    if isinstance(node, list):
        for item in node:
            found = _find_media_url(item)
            if found:
                return found
    return None

async def fetch_klipy_gif(category: str):
    """Fetch a GIF url from Klipy for the given nakama category. Returns None on failure."""
    if not KLIPY_API_KEY:
        print("[NAKAMA] KLIPY_API_KEY is not set")
        return None

    query = NAKAMA_KLIPY_QUERY.get(category, category)
    url = f"https://api.klipy.com/api/v1/{KLIPY_API_KEY}/gifs/search"
    params = {"q": query, "per_page": 24, "page": 1, "rating": "pg-13"}

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    print(f"[NAKAMA] klipy status: {resp.status} (attempt {attempt + 1})")
                    if resp.status != 200:
                        await asyncio.sleep(1)
                        continue
                    data = await resp.json()
                    if not data.get("result"):
                        print(f"[NAKAMA] klipy result=false: {data}")
                        await asyncio.sleep(1)
                        continue
                    items = data.get("data", {}).get("data", [])
                    if not items:
                        print("[NAKAMA] klipy returned no items")
                        return None
                    for item in random.sample(items, min(5, len(items))):
                        gif_url = _find_media_url(item)
                        if gif_url:
                            return gif_url
                    return None
        except Exception as e:
            print(f"[NAKAMA] klipy error on attempt {attempt + 1}: {e}")
            await asyncio.sleep(1)
    return None


async def on_message_nakama(message):
    print(f"[NAKAMA] triggered with: '{message.content}'")

    content = message.content.lower().strip()
    words = content.split()

    print(f"[NAKAMA] words: {words}")

    if not words or words[0] != "nakama":
        print("[NAKAMA] first word is not 'nakama', returning")
        return

    category = None
    for word in words[1:]:
        clean = word.strip("!?,.")
        print(f"[NAKAMA] checking word: '{clean}'")
        if clean in NAKAMA_GIF_MAP:
            category = NAKAMA_GIF_MAP[clean]
            print(f"[NAKAMA] matched category: {category}")
            break

    if not category:
        print("[NAKAMA] no matching category found, returning")
        return

    author_name = message.author.display_name
    target = message.mentions[0] if message.mentions else None
    target_name = target.display_name if target else None

    messages = NAKAMA_GIF_MESSAGES.get(
        category,
        ("{author} uses " + category + "!", "{author} uses " + category + " on {target}!")
    )

    if target_name:
        text = messages[1].format(author=author_name, target=target_name)
    else:
        text = messages[0].format(author=author_name)

    print(f"[NAKAMA] fetching GIF for category: {category}")

    gif_url = await fetch_klipy_gif(category)

    if not gif_url:
        print("[NAKAMA] all attempts failed, aborting")
        await message.channel.send(f"{text} *(GIF unavailable right now)*")
        return

    embed = discord.Embed(description=text, color=discord.Color.gold())
    embed.set_image(url=gif_url)
    embed.set_footer(text="🏴‍☠️ NakamaBot")
    await message.channel.send(embed=embed)
    print(f"[NAKAMA] embed sent successfully!")


# ── MERGED on_message ──────────────────────────────────────────────────────────
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # ── AFK check ────────────────────────────────────────────────────────────
    await on_message_afk(message)

    # ── Bounty chat XP ─────────────────────────────────────────────────────
    await on_message_chat_xp(message)

    # ── Nakama GIF trigger ────────────────────────────────────────────────────
    await on_message_nakama(message)

    # ── Custom commands ───────────────────────────────────────────────────────
    content_stripped = message.content.strip()
    if content_stripped.startswith("!"):
        cmd_name = content_stripped[1:].split()[0].lower()
        if cmd_name in CUSTOM_COMMANDS and CUSTOM_COMMANDS[cmd_name]["enabled"]:
            await message.channel.send(CUSTOM_COMMANDS[cmd_name]["response"])
            return

    # ── Bad word filter ───────────────────────────────────────────────────────
    content = message.content.lower()
    if any(word in content for word in BAD_WORDS):
        await message.delete()
        await message.channel.send(f"{message.author.mention} Watch your language! ⚠️", delete_after=5)
        await log_action(message.guild, "Auto-Mod: Bad Word", bot.user, message.author, message.content)
        return

    # ── Spam detection ────────────────────────────────────────────────────────
    SPAM_EXEMPT_CHANNEL_ID = 1502196110540673054  # #spamming-channel — spam is allowed here
    if message.channel.id != SPAM_EXEMPT_CHANNEL_ID:
        uid = message.author.id
        now = asyncio.get_event_loop().time()
        if uid not in spam_tracker:
            spam_tracker[uid] = []
        spam_tracker[uid] = [t for t in spam_tracker[uid] if now - t < 5]
        spam_tracker[uid].append(now)
        if len(spam_tracker[uid]) >= 5:
            await message.delete()
            await message.channel.send(f"{message.author.mention} Slow down, stop spamming! ⚠️", delete_after=5)
            await log_action(message.guild, "Auto-Mod: Spam", bot.user, message.author)
            spam_tracker[uid] = []
            return

    await bot.process_commands(message)

    # ── Sticky messages ───────────────────────────────────────────────────────
    sticky = STICKY_CONFIG.get(message.channel.id)
    if sticky:
        try:
            old = await message.channel.fetch_message(sticky["last_id"])
            await old.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
        try:
            style = sticky.get("style", "plain")
            if style == "embed":
                embed = discord.Embed(description=sticky["message"], color=discord.Color.gold())
                embed.set_footer(text="📌 Sticky Message")
                sent = await message.channel.send(embed=embed)
            else:
                sent = await message.channel.send(f"📌 {sticky['message']}")
            STICKY_CONFIG[message.channel.id]["last_id"] = sent.id
            save_sticky_config()
        except discord.Forbidden:
            pass

# ── Mod commands ───────────────────────────────────────────────────────────────

@bot.tree.command(name="setwelcome", description="Set the channel where welcome messages are sent")
@app_commands.describe(channel="The channel to send welcome messages in")
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    _welcome_channel_override[interaction.guild.id] = channel.id
    await interaction.response.send_message(f"✅ Welcome messages will now be sent in {channel.mention}!", ephemeral=True)

@bot.tree.command(name="testwelcome", description="Preview the welcome message as if you just joined")
async def testwelcome(interaction: discord.Interaction):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    embed = build_welcome_embed(interaction.user)
    await interaction.response.send_message(content=f"👀 **Welcome message preview:**\n{interaction.user.mention}", embed=embed, ephemeral=False)

AFK_USERS = {}

@bot.tree.command(name="afk", description="Set your AFK status")
@app_commands.describe(reason="Your AFK reason")
async def afk(interaction: discord.Interaction, reason: str = "AFK"):
    AFK_USERS[interaction.user.id] = {"reason": reason}
    await interaction.response.send_message(f"🌙 **{interaction.user.display_name}** is now AFK: *{reason}*")
    try:
        original_nick = interaction.user.display_name
        await interaction.user.edit(nick=f"[AFK] {original_nick}"[:32])
    except discord.Forbidden:
        pass

async def on_message_afk(message):
    if message.author.id in AFK_USERS:
        afk_data = AFK_USERS.pop(message.author.id)
        await message.channel.send(
            f"👋 Welcome back, {message.author.mention}! Removed your AFK status. (Was AFK: *{afk_data['reason']}*)",
            delete_after=5
        )
        try:
            nick = message.author.display_name
            if nick.startswith("[AFK] "):
                await message.author.edit(nick=nick[6:] or None)
        except discord.Forbidden:
            pass

    for mentioned in message.mentions:
        if mentioned.id in AFK_USERS:
            afk_data = AFK_USERS[mentioned.id]
            await message.channel.send(f"💤 **{mentioned.display_name}** is AFK: *{afk_data['reason']}*", delete_after=8)

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason for warning")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    uid = str(member.id)
    if uid not in WARNINGS:
        WARNINGS[uid] = []
    WARNINGS[uid].append(reason)
    count = len(WARNINGS[uid])
    await interaction.response.send_message(f"⚠️ {member.mention} has been warned. Total warnings: **{count}**\nReason: {reason}")
    await log_action(interaction.guild, "Warn", interaction.user, member, reason)
    if count >= 3:
        await interaction.followup.send(f"🚨 {member.mention} has reached 3 warnings and has been timed out for 1 hour!")
        await member.timeout(timedelta(hours=1), reason="3 warnings reached")
        await log_action(interaction.guild, "Auto-Timeout (3 warnings)", bot.user, member)

@bot.tree.command(name="warnings", description="Check warnings for a member")
@app_commands.describe(member="Member to check")
async def warnings(interaction: discord.Interaction, member: discord.Member):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    uid = str(member.id)
    warns = WARNINGS.get(uid, [])
    if not warns:
        await interaction.response.send_message(f"✅ {member.mention} has no warnings.")
    else:
        warn_list = "\n".join([f"{i+1}. {w}" for i, w in enumerate(warns)])
        await interaction.response.send_message(f"⚠️ **{member.display_name}** has {len(warns)} warning(s):\n{warn_list}")

@bot.tree.command(name="clearwarnings", description="Clear all warnings for a member")
@app_commands.describe(member="Member to clear warnings for")
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    WARNINGS[str(member.id)] = []
    await interaction.response.send_message(f"✅ Cleared all warnings for {member.mention}.")
    await log_action(interaction.guild, "Clear Warnings", interaction.user, member)

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="Member to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 {member.mention} has been kicked. Reason: {reason}")
    await log_action(interaction.guild, "Kick", interaction.user, member, reason)

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="Member to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 {member.mention} has been banned. Reason: {reason}")
    await log_action(interaction.guild, "Ban", interaction.user, member, reason)

@bot.tree.command(name="unban", description="Unban a user")
@app_commands.describe(username="Username to unban (e.g. user#1234)")
async def unban(interaction: discord.Interaction, username: str):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    banned = [entry async for entry in interaction.guild.bans()]
    for entry in banned:
        if str(entry.user) == username:
            await interaction.guild.unban(entry.user)
            await interaction.response.send_message(f"✅ {entry.user} has been unbanned.")
            await log_action(interaction.guild, "Unban", interaction.user, entry.user)
            return
    await interaction.response.send_message(f"❌ User `{username}` not found in ban list.")

@bot.tree.command(name="mute", description="Timeout a member")
@app_commands.describe(member="Member to mute", minutes="Duration in minutes", reason="Reason for mute")
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int = 10, reason: str = "No reason provided"):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    await interaction.response.send_message(f"🔇 {member.mention} has been muted for {minutes} minutes. Reason: {reason}")
    await log_action(interaction.guild, "Mute", interaction.user, member, reason)

@bot.tree.command(name="unmute", description="Remove timeout from a member")
@app_commands.describe(member="Member to unmute")
async def unmute(interaction: discord.Interaction, member: discord.Member):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    await member.timeout(None)
    await interaction.response.send_message(f"🔊 {member.mention} has been unmuted.")
    await log_action(interaction.guild, "Unmute", interaction.user, member)

@bot.tree.command(name="purge", description="Delete multiple messages")
@app_commands.describe(amount="Number of messages to delete")
async def purge(interaction: discord.Interaction, amount: int):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    await interaction.response.send_message(f"🧹 Deleting {amount} messages...", ephemeral=True)
    await interaction.channel.purge(limit=amount)
    await log_action(interaction.guild, "Purge", interaction.user, interaction.channel, f"{amount} messages deleted")

@bot.tree.command(name="addrole", description="Add a role to a member")
@app_commands.describe(member="Member to give role to", role="Role to add")
async def addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    await member.add_roles(role)
    await interaction.response.send_message(f"✅ Added **{role.name}** to {member.mention}.")
    await log_action(interaction.guild, "Add Role", interaction.user, member, role.name)

@bot.tree.command(name="removerole", description="Remove a role from a member")
@app_commands.describe(member="Member to remove role from", role="Role to remove")
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    await member.remove_roles(role)
    await interaction.response.send_message(f"✅ Removed **{role.name}** from {member.mention}.")
    await log_action(interaction.guild, "Remove Role", interaction.user, member, role.name)


# ── Sticky Messages ────────────────────────────────────────────────────────────

STICKY_CONFIG = {}

# ── Birthday system ──────────────────────────────────────────────────────────
BIRTHDAY_CONFIG = {}
BIRTHDAY_CONFIG_FILE = "birthday_config.json"
BIRTHDAY_WISH_CHANNEL_ID = 1501909942754344965
BIRTHDAY_SETUP_CHANNEL_ID = None
BIRTHDAY_LAST_CHAIN_MSG_ID = None

def save_birthday_config():
    with open(BIRTHDAY_CONFIG_FILE, "w") as f:
        json.dump({
            "wish_channel": BIRTHDAY_WISH_CHANNEL_ID,
            "setup_channel": BIRTHDAY_SETUP_CHANNEL_ID,
            "last_chain_msg": BIRTHDAY_LAST_CHAIN_MSG_ID,
            "birthdays": {str(k): v for k, v in BIRTHDAY_CONFIG.items()}
        }, f, indent=2)

def load_birthday_config():
    global BIRTHDAY_CONFIG, BIRTHDAY_WISH_CHANNEL_ID, BIRTHDAY_SETUP_CHANNEL_ID, BIRTHDAY_LAST_CHAIN_MSG_ID
    if os.path.exists(BIRTHDAY_CONFIG_FILE):
        with open(BIRTHDAY_CONFIG_FILE, "r") as f:
            data = json.load(f)
        BIRTHDAY_WISH_CHANNEL_ID = data.get("wish_channel", 1501909942754344965)
        BIRTHDAY_SETUP_CHANNEL_ID = data.get("setup_channel")
        BIRTHDAY_LAST_CHAIN_MSG_ID = data.get("last_chain_msg")
        BIRTHDAY_CONFIG = {int(k): v for k, v in data.get("birthdays", {}).items()}
        print(f"✅ Loaded birthday config for {len(BIRTHDAY_CONFIG)} user(s)")

load_birthday_config()
STICKY_CONFIG_FILE = "sticky_config.json"

def save_sticky_config():
    serializable = {str(k): v for k, v in STICKY_CONFIG.items()}
    with open(STICKY_CONFIG_FILE, "w") as f:
        json.dump(serializable, f)

def load_sticky_config():
    global STICKY_CONFIG
    if os.path.exists(STICKY_CONFIG_FILE):
        with open(STICKY_CONFIG_FILE, "r") as f:
            data = json.load(f)
            STICKY_CONFIG = {int(k): v for k, v in data.items()}
        print(f"✅ Loaded sticky config for {len(STICKY_CONFIG)} channel(s)")

class StickyStyleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.style = None

    @discord.ui.button(label="📌 Plain Text", style=discord.ButtonStyle.secondary, custom_id="sticky:plain")
    async def plain_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.style = "plain"
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="✨ Embed", style=discord.ButtonStyle.primary, custom_id="sticky:embed")
    async def embed_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.style = "embed"
        await interaction.response.defer()
        self.stop()

async def post_sticky(channel: discord.TextChannel, message: str, style: str) -> discord.Message:
    if style == "embed":
        if len(message) > 4096:
            raise ValueError(f"Message is too long for an embed ({len(message)}/4096 characters). Please shorten it.")
        embed = discord.Embed(description=message, color=discord.Color.gold())
        embed.set_footer(text="📌 Sticky Message")
        return await channel.send(embed=embed)
    else:
        full_message = f"📌 {message}"
        if len(full_message) > 2000:
            raise ValueError(
                f"Message is too long for plain text ({len(full_message)}/2000 characters). "
                f"Please shorten it by {len(full_message) - 2000} character(s), or use the Embed style which supports up to 4096 characters."
            )
        return await channel.send(full_message)

@bot.tree.command(name="setsticky", description="Set a sticky message in a channel")
@app_commands.describe(channel="Channel to stick the message in", message="The message to stick (plain text: 1998 chars max, embed: 4096 chars max)")
async def setsticky(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return

    view = StickyStyleView()
    await interaction.response.send_message("How do you want the sticky to look?", view=view, ephemeral=True)
    await view.wait()

    if not view.style:
        await interaction.edit_original_response(content="⏰ Timed out.", view=None)
        return

    try:
        sent = await post_sticky(channel, message, view.style)
    except ValueError as e:
        await interaction.edit_original_response(content=f"❌ {e}", view=None)
        return
    STICKY_CONFIG[channel.id] = {"message": message, "last_id": sent.id, "style": view.style}
    save_sticky_config()

    await interaction.edit_original_response(content=f"📌 Sticky message set in {channel.mention}.", view=None)

@bot.tree.command(name="removesticky", description="Remove the sticky message from a channel")
@app_commands.describe(channel="Channel to remove the sticky from")
async def removesticky(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return

    config = STICKY_CONFIG.pop(channel.id, None)
    if not config:
        await interaction.response.send_message(f"❌ No sticky message found in {channel.mention}.", ephemeral=True)
        return

    try:
        last_msg = await channel.fetch_message(config["last_id"])
        await last_msg.delete()
    except (discord.NotFound, discord.HTTPException):
        pass

    save_sticky_config()
    await interaction.response.send_message(f"✅ Sticky message removed from {channel.mention}.", ephemeral=True)

@bot.tree.command(name="liststicky", description="List all sticky messages in this server")
async def liststicky(interaction: discord.Interaction):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return

    guild_channel_ids = [c.id for c in interaction.guild.channels]
    stickies = {cid: v for cid, v in STICKY_CONFIG.items() if cid in guild_channel_ids}

    if not stickies:
        await interaction.response.send_message("No sticky messages set in this server.", ephemeral=True)
        return

    lines = [f"<#{cid}>: {v['message'][:60]}{'...' if len(v['message']) > 60 else ''}" for cid, v in stickies.items()]
    await interaction.response.send_message("📌 **Sticky Messages:**\n" + "\n".join(lines), ephemeral=True)


INTRO_TEMPLATE = """__**Stickied Message:**__
**✦˚₊ ⊹ About Me!**
┊ ⊹ Username (LNC Name):
┊ ⊹ Pronouns:
┊ ⊹ Age (Birthday):
┊ ⊹ Country:
┊ ⊹ Favourite Genre:
┊ ⊹ Personality Type:
─────────────────✧˖°>
**✦˚₊ ⊹ My Favourites!**
┊ ⊹ Novel:
┊ ⊹ Anime:
┊ ⊹ Manga/hwa:
─────────────────✧˖°>
**✦˚₊ ⊹ Community Interests!**
┊ ⊹ Games I Play:
┊ ⊹ Top 3 Novels:
┊ ⊹ Hobbies:
┊ ⊹ Favourite Tropes:
─────────────────✧˖°>
**✦˚₊ ⊹ Bonus Details!**
┊ ⊹ Open to DMs About:
┊ ⊹ An Unpopular Opinion:
┊ ⊹ Fun Fact About Me:>
--- **Please use the above template to fill in your details!** ---"""

@bot.tree.command(name="setintrosticky", description="Post the introduction template as a sticky in a channel")
@app_commands.describe(channel="Channel to post the intro sticky in")
async def setintrosticky(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    old = STICKY_CONFIG.get(channel.id)
    if old:
        try:
            old_msg = await channel.fetch_message(old["last_id"])
            await old_msg.delete()
        except Exception:
            pass

    sent = await channel.send(INTRO_TEMPLATE)
    STICKY_CONFIG[channel.id] = {"message": INTRO_TEMPLATE, "last_id": sent.id, "style": "plain"}
    save_sticky_config()

    await interaction.followup.send(f"📌 Intro sticky set in {channel.mention}.", ephemeral=True)


# ── Common timezones list ────────────────────────────────────────────────────
COMMON_TIMEZONES = [
    "Pacific/Midway", "Pacific/Honolulu", "America/Anchorage", "America/Los_Angeles",
    "America/Denver", "America/Chicago", "America/New_York", "America/Sao_Paulo",
    "America/Argentina/Buenos_Aires", "America/Noronha", "Atlantic/Azores",
    "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Helsinki",
    "Europe/Istanbul", "Asia/Dubai", "Asia/Kolkata", "Asia/Dhaka",
    "Asia/Bangkok", "Asia/Singapore", "Asia/Tokyo", "Asia/Seoul",
    "Australia/Sydney", "Pacific/Auckland", "Pacific/Fiji",
    "Asia/Jakarta", "Asia/Manila", "Asia/Taipei", "Asia/Hong_Kong",
    "Asia/Karachi", "Asia/Riyadh", "Africa/Cairo", "Africa/Nairobi",
    "America/Toronto", "America/Vancouver", "America/Mexico_City",
    "Europe/Moscow", "Europe/Amsterdam", "Europe/Rome", "Europe/Madrid",
    "Europe/Athens", "Asia/Tehran", "Asia/Kabul", "Asia/Tashkent",
    "Asia/Colombo", "Asia/Kathmandu", "Asia/Almaty", "Asia/Yangon",
]

async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    filtered = [tz for tz in COMMON_TIMEZONES if current.lower() in tz.lower()]
    return [app_commands.Choice(name=tz, value=tz) for tz in filtered[:25]]

class BirthdayModal(discord.ui.Modal, title="🎂 Set Your Birthday"):
    birth_day = discord.ui.TextInput(
        label="Day (1-31)",
        placeholder="e.g. 15",
        min_length=1,
        max_length=2,
        required=True,
    )
    birth_month = discord.ui.TextInput(
        label="Month (1-12)",
        placeholder="e.g. 7 for July",
        min_length=1,
        max_length=2,
        required=True,
    )

    def __init__(self, timezone_str: str):
        super().__init__()
        self.timezone_str = timezone_str

    async def on_submit(self, interaction: discord.Interaction):
        try:
            day = int(self.birth_day.value.strip())
            month = int(self.birth_month.value.strip())
            if not (1 <= day <= 31) or not (1 <= month <= 12):
                raise ValueError
            datetime(2000, month, day)
        except (ValueError, TypeError):
            await interaction.response.send_message("❌ Invalid date. Please enter a valid day (1-31) and month (1-12).", ephemeral=True)
            return

        BIRTHDAY_CONFIG[interaction.user.id] = {
            "day": day,
            "month": month,
            "timezone": self.timezone_str,
        }
        save_birthday_config()

        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(title="🎂 Birthday Registered", color=discord.Color.blurple())
            embed.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user}`)", inline=False)
            embed.add_field(name="Birthday", value=f"{day}/{month}", inline=True)
            embed.add_field(name="Timezone", value=self.timezone_str, inline=True)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.timestamp = discord.utils.utcnow()
            await log_channel.send(embed=embed)

        msg = f"\U0001f382 Birthday saved! You'll be wished on **{day}/{month}** at 12:00 AM **{self.timezone_str}**.\n\nWant to add yours too? Click below!"
        if BIRTHDAY_SETUP_CHANNEL_ID:
            setup_channel = interaction.client.get_channel(BIRTHDAY_SETUP_CHANNEL_ID)
            if setup_channel:
                global BIRTHDAY_LAST_CHAIN_MSG_ID
                if BIRTHDAY_LAST_CHAIN_MSG_ID:
                    try:
                        old_msg = await setup_channel.fetch_message(BIRTHDAY_LAST_CHAIN_MSG_ID)
                        await old_msg.delete()
                    except Exception:
                        pass
                new_chain_msg = await setup_channel.send(msg, view=AddBirthdayView())
                BIRTHDAY_LAST_CHAIN_MSG_ID = new_chain_msg.id
                save_birthday_config()
                await interaction.response.send_message("✅ Your birthday has been saved!", ephemeral=True)
                return
        await interaction.response.send_message(msg, view=AddBirthdayView())

# Grouped timezones for the dropdown
TIMEZONE_GROUPS = {
    "🌎 Americas": [
        "America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York",
        "America/Toronto", "America/Vancouver", "America/Mexico_City", "America/Sao_Paulo",
        "America/Argentina/Buenos_Aires", "America/Anchorage", "Pacific/Honolulu",
    ],
    "🌍 Europe & Africa": [
        "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Rome", "Europe/Madrid",
        "Europe/Amsterdam", "Europe/Helsinki", "Europe/Athens", "Europe/Istanbul",
        "Europe/Moscow", "Africa/Cairo", "Africa/Nairobi", "Atlantic/Azores",
    ],
    "🌏 Asia": [
        "Asia/Dubai", "Asia/Kolkata", "Asia/Dhaka", "Asia/Bangkok", "Asia/Singapore",
        "Asia/Tokyo", "Asia/Seoul", "Asia/Jakarta", "Asia/Manila", "Asia/Hong_Kong",
        "Asia/Taipei", "Asia/Karachi", "Asia/Riyadh", "Asia/Tehran", "Asia/Tashkent",
        "Asia/Colombo", "Asia/Kathmandu", "Asia/Almaty", "Asia/Yangon",
    ],
    "🏝️ Oceania": [
        "Australia/Sydney", "Australia/Melbourne", "Australia/Brisbane", "Australia/Perth",
        "Australia/Adelaide", "Australia/Darwin", "Australia/Hobart",
        "Pacific/Auckland", "Pacific/Fiji", "Pacific/Guam", "Pacific/Port_Moresby",
        "Pacific/Noumea", "Pacific/Tongatapu", "Pacific/Apia", "Pacific/Honolulu",
    ],
}

class TimezoneSelect(discord.ui.Select):
    def __init__(self, group_name: str, timezones: list):
        options = [discord.SelectOption(label=tz, value=tz) for tz in timezones]
        super().__init__(
            placeholder=f"Pick your timezone — {group_name}",
            options=options,
            custom_id=f"tz_select:{group_name}",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BirthdayModal(self.values[0]))

class AddBirthdayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎂 Add My Birthday", style=discord.ButtonStyle.primary, custom_id="birthday:add")
    async def add_birthday(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = TimezoneRegionView()
        await interaction.response.send_message(
            "🌍 **Step 1:** Pick your region to find your timezone:",
            view=view,
            ephemeral=True,
        )

class TimezoneRegionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        for group_name, timezones in TIMEZONE_GROUPS.items():
            self.add_item(TimezoneSelect(group_name, timezones))

    async def on_timeout(self):
        pass

@bot.tree.command(name="setwishchannel", description="Set the channel where birthday wishes are announced (mod only)")
@app_commands.describe(channel="The channel to send birthday announcements in")
async def setwishchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    global BIRTHDAY_WISH_CHANNEL_ID
    BIRTHDAY_WISH_CHANNEL_ID = channel.id
    save_birthday_config()
    await interaction.response.send_message(f"✅ Birthday wishes will be announced in {channel.mention}.", ephemeral=True)

@bot.tree.command(name="setbirthdaysetupchannel", description="Set the channel where the birthday registration chain lives (mod only)")
@app_commands.describe(channel="The channel where members register their birthdays")
async def setbirthdaysetupchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    global BIRTHDAY_SETUP_CHANNEL_ID
    BIRTHDAY_SETUP_CHANNEL_ID = channel.id
    save_birthday_config()
    view = AddBirthdayView()
    await channel.send("🎂 **Add your birthday to get wished at midnight!**\nClick the button below to get started.", view=view)
    await interaction.response.send_message(f"✅ Birthday setup channel set to {channel.mention}. The registration button has been posted there!", ephemeral=True)

@bot.tree.command(name="birthday", description="Set your birthday to get wished at midnight!")
@app_commands.describe(timezone="Search and select your timezone")
@app_commands.autocomplete(timezone=timezone_autocomplete)
async def birthday(interaction: discord.Interaction, timezone: str):
    if timezone not in pytz.all_timezones:
        await interaction.response.send_message(
            f"❌ `{timezone}` is not a valid timezone. Please pick one from the suggestions.",
            ephemeral=True,
        )
        return
    await interaction.response.send_modal(BirthdayModal(timezone))

@bot.tree.command(name="listbirthdays", description="List all saved birthdays in this server")
async def listbirthdays(interaction: discord.Interaction):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    if not BIRTHDAY_CONFIG:
        await interaction.response.send_message("No birthdays saved yet.", ephemeral=True)
        return
    lines = []
    for uid, data in BIRTHDAY_CONFIG.items():
        lines.append(f"<@{uid}>: {data['day']}/{data['month']} ({data['timezone']})")
    await interaction.response.send_message("🎂 **Birthdays:**\n" + "\n".join(lines), ephemeral=True)

@bot.tree.command(name="removebirthday", description="Remove your birthday from the list")
async def removebirthday(interaction: discord.Interaction):
    if interaction.user.id not in BIRTHDAY_CONFIG:
        await interaction.response.send_message("❌ You don't have a birthday saved.", ephemeral=True)
        return
    del BIRTHDAY_CONFIG[interaction.user.id]
    save_birthday_config()
    await interaction.response.send_message("✅ Your birthday has been removed.", ephemeral=True)

@bot.tree.command(name="clearallbirthdays", description="Remove every birthday from the list (mod only)")
async def clearallbirthdays(interaction: discord.Interaction):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    count = len(BIRTHDAY_CONFIG)
    BIRTHDAY_CONFIG.clear()
    save_birthday_config()
    await interaction.response.send_message(f"✅ Cleared all {count} birthday(s) from the list.", ephemeral=True)

@bot.tree.command(name="removeuserbday", description="Remove a specific member's birthday (mod only)")
@app_commands.describe(user="The member whose birthday you want to remove")
async def removeuserbday(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    if user.id not in BIRTHDAY_CONFIG:
        await interaction.response.send_message(f"❌ {user.mention} doesn't have a birthday saved.", ephemeral=True)
        return
    del BIRTHDAY_CONFIG[user.id]
    save_birthday_config()
    await interaction.response.send_message(f"✅ Removed birthday for {user.mention}.", ephemeral=True)

class EditBirthdayModal(discord.ui.Modal, title="✏️ Edit Birthday"):
    birth_day = discord.ui.TextInput(
        label="New Day (1-31)",
        placeholder="e.g. 15",
        min_length=1,
        max_length=2,
        required=True,
    )
    birth_month = discord.ui.TextInput(
        label="New Month (1-12)",
        placeholder="e.g. 7 for July",
        min_length=1,
        max_length=2,
        required=True,
    )

    def __init__(self, user: discord.Member, timezone_str: str):
        super().__init__()
        self.target_user = user
        self.timezone_str = timezone_str

    async def on_submit(self, interaction: discord.Interaction):
        try:
            day = int(self.birth_day.value.strip())
            month = int(self.birth_month.value.strip())
            if not (1 <= day <= 31) or not (1 <= month <= 12):
                raise ValueError
            datetime(2000, month, day)
        except (ValueError, TypeError):
            await interaction.response.send_message("❌ Invalid date. Please enter a valid day and month.", ephemeral=True)
            return
        BIRTHDAY_CONFIG[self.target_user.id] = {"day": day, "month": month, "timezone": self.timezone_str}
        save_birthday_config()
        await interaction.response.send_message(
            f"✅ Updated {self.target_user.mention}'s birthday to **{day}/{month}** ({self.timezone_str}).",
            ephemeral=True
        )

class EditTimezoneSelect(discord.ui.Select):
    def __init__(self, group_name: str, timezones: list, target_user: discord.Member):
        self.target_user = target_user
        options = [discord.SelectOption(label=tz, value=tz) for tz in timezones]
        super().__init__(placeholder=f"Pick timezone — {group_name}", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EditBirthdayModal(self.target_user, self.values[0]))

class EditTimezoneView(discord.ui.View):
    def __init__(self, target_user: discord.Member):
        super().__init__(timeout=60)
        for group_name, timezones in TIMEZONE_GROUPS.items():
            self.add_item(EditTimezoneSelect(group_name, timezones, target_user))

@bot.tree.command(name="edituserbday", description="Edit a specific member's birthday (mod only)")
@app_commands.describe(user="The member whose birthday you want to edit")
async def edituserbday(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    existing = BIRTHDAY_CONFIG.get(user.id)
    if existing:
        await interaction.response.send_modal(EditBirthdayModal(user, existing["timezone"]))
    else:
        view = EditTimezoneView(user)
        await interaction.response.send_message(
            f"🌍 Pick a timezone for {user.mention}:",
            view=view,
            ephemeral=True
        )

@bot.tree.command(name="testbirthday", description="Test the birthday wish instantly (mod only)")
@app_commands.describe(user="The user to test the birthday wish for")
async def testbirthday(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    dm_status = "✅ DM sent"
    try:
        await user.send(
            f"🎂 **Happy Birthday, {user.display_name}!** 🎉\n"
            f"Wishing you an amazing day filled with joy! "
            f"The whole server is celebrating with you! 🥳"
        )
    except Exception:
        dm_status = "❌ DM failed (user may have DMs disabled)"

    channel_status = "✅ Server announcement sent"
    if BIRTHDAY_WISH_CHANNEL_ID:
        channel = bot.get_channel(BIRTHDAY_WISH_CHANNEL_ID)
        if channel:
            await channel.send(
                f"@everyone\n"
                f"🎂 Today is {user.mention}'s birthday! "
                f"Let's all wish them a Happy Birthday! 🎉🥳"
            )
        else:
            channel_status = "❌ Birthday channel not found"
    else:
        channel_status = "❌ No birthday channel set — use /setbirthdaychannel first"

    await interaction.followup.send(
        f"**Birthday test for {user.mention}:**\n{dm_status}\n{channel_status}",
        ephemeral=True
    )

async def birthday_checker():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now_utc = datetime.now(timezone.utc)
        for user_id, data in list(BIRTHDAY_CONFIG.items()):
            try:
                tz = pytz.timezone(data["timezone"])
                now_local = now_utc.astimezone(tz)
                if now_local.month == data["month"] and now_local.day == data["day"] and now_local.hour == 0 and now_local.minute == 0:
                    last_wished = data.get("last_wished")
                    if last_wished != now_local.year:
                        try:
                            user = await bot.fetch_user(user_id)
                            await user.send(
                                f"🎂 **Happy Birthday, {user.display_name}!** 🎉\n"
                                f"Wishing you an amazing day filled with joy! "
                                f"The whole server is celebrating with you! 🥳"
                            )
                        except Exception:
                            pass

                        if BIRTHDAY_WISH_CHANNEL_ID:
                            channel = bot.get_channel(BIRTHDAY_WISH_CHANNEL_ID)
                            if channel:
                                await channel.send(
                                    f"@everyone\n"
                                    f"🎂 Today is <@{user_id}>'s birthday! "
                                    f"Let's all wish them a Happy Birthday! 🎉🥳"
                                )
                        BIRTHDAY_CONFIG[user_id]["last_wished"] = now_local.year
                        save_birthday_config()
            except Exception as e:
                print(f"Birthday check error for {user_id}: {e}")
        await asyncio.sleep(60)


# ── Role & Server Management ─────────────────────────────────────────────────

@bot.tree.command(name="addmod", description="Add a moderator role (mod only)")
@app_commands.describe(role="The role to add as moderator")
async def addmod(interaction: discord.Interaction, role: discord.Role):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    if role.name not in ROLE_HIERARCHY:
        ROLE_HIERARCHY.append(role.name)
    await interaction.response.send_message(f"✅ **{role.name}** added as a moderator role.", ephemeral=True)

@bot.tree.command(name="delmod", description="Remove a moderator role (mod only)")
@app_commands.describe(role="The role to remove from moderators")
async def delmod(interaction: discord.Interaction, role: discord.Role):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    if role.name in ROLE_HIERARCHY:
        ROLE_HIERARCHY.remove(role.name)
    await interaction.response.send_message(f"✅ **{role.name}** removed from moderator roles.", ephemeral=True)

@bot.tree.command(name="listmods", description="List all moderator roles")
async def listmods(interaction: discord.Interaction):
    roles = ", ".join(ROLE_HIERARCHY) if ROLE_HIERARCHY else "None"
    await interaction.response.send_message(f"🛡️ **Moderator Roles:** {roles}", ephemeral=True)

@bot.tree.command(name="createrole", description="Create a new role (mod only)")
@app_commands.describe(name="Role name", color="Hex color e.g. #ff0000", hoist="Show separately in member list")
async def createrole(interaction: discord.Interaction, name: str, color: str = None, hoist: bool = False):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    role_color = discord.Color.default()
    if color:
        try:
            role_color = discord.Color(int(color.strip("#"), 16))
        except ValueError:
            await interaction.response.send_message("❌ Invalid color. Use hex like `#ff0000`.", ephemeral=True)
            return
    role = await interaction.guild.create_role(name=name, color=role_color, hoist=hoist)
    await interaction.response.send_message(f"✅ Role **{role.name}** created.", ephemeral=True)

@bot.tree.command(name="deleterole", description="Delete a role (mod only)")
@app_commands.describe(role="The role to delete")
async def deleterole(interaction: discord.Interaction, role: discord.Role):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await role.delete()
    await interaction.response.send_message(f"✅ Role **{role.name}** deleted.", ephemeral=True)

@bot.tree.command(name="rolecolor", description="Change a role's color (mod only)")
@app_commands.describe(role="The role to update", color="Hex color e.g. #ff0000")
async def rolecolor(interaction: discord.Interaction, role: discord.Role, color: str):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    try:
        new_color = discord.Color(int(color.strip("#"), 16))
    except ValueError:
        await interaction.response.send_message("❌ Invalid color. Use hex like `#ff0000`.", ephemeral=True)
        return
    await role.edit(color=new_color)
    await interaction.response.send_message(f"✅ **{role.name}** color updated.", ephemeral=True)

@bot.tree.command(name="rolename", description="Rename a role (mod only)")
@app_commands.describe(role="The role to rename", new_name="New name for the role")
async def rolename(interaction: discord.Interaction, role: discord.Role, new_name: str):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    old_name = role.name
    await role.edit(name=new_name)
    await interaction.response.send_message(f"✅ **{old_name}** renamed to **{new_name}**.", ephemeral=True)

@bot.tree.command(name="nick", description="Change the bot's nickname (mod only)")
@app_commands.describe(new_nickname="New nickname for the bot")
async def nick(interaction: discord.Interaction, new_nickname: str):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.guild.me.edit(nick=new_nickname)
    await interaction.response.send_message(f"✅ Bot nickname changed to **{new_nickname}**.", ephemeral=True)

@bot.tree.command(name="setnick", description="Change a member's nickname (mod only)")
@app_commands.describe(user="The member", new_nickname="New nickname")
async def setnick(interaction: discord.Interaction, user: discord.Member, new_nickname: str):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await user.edit(nick=new_nickname)
    await interaction.response.send_message(f"✅ **{user}**'s nickname set to **{new_nickname}**.", ephemeral=True)

@bot.tree.command(name="mentionable", description="Toggle a role's mentionability (mod only)")
@app_commands.describe(role="The role", value="True to make mentionable, False to disable")
async def mentionable(interaction: discord.Interaction, role: discord.Role, value: bool):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await role.edit(mentionable=value)
    status = "mentionable" if value else "not mentionable"
    await interaction.response.send_message(f"✅ **{role.name}** is now {status}.", ephemeral=True)

@bot.tree.command(name="role", description="Add or remove a role from a member (mod only)")
@app_commands.describe(user="The member", action="add or remove", role="The role")
@app_commands.choices(action=[
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove"),
    app_commands.Choice(name="toggle", value="toggle"),
])
async def role_cmd(interaction: discord.Interaction, user: discord.Member, action: str, role: discord.Role):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    if action == "add":
        await user.add_roles(role)
        await interaction.response.send_message(f"✅ Added **{role.name}** to {user.mention}.", ephemeral=True)
    elif action == "remove":
        await user.remove_roles(role)
        await interaction.response.send_message(f"✅ Removed **{role.name}** from {user.mention}.", ephemeral=True)
    elif action == "toggle":
        if role in user.roles:
            await user.remove_roles(role)
            await interaction.response.send_message(f"✅ Removed **{role.name}** from {user.mention}.", ephemeral=True)
        else:
            await user.add_roles(role)
            await interaction.response.send_message(f"✅ Added **{role.name}** to {user.mention}.", ephemeral=True)

@bot.tree.command(name="roleall", description="Add or remove a role from all members (mod only)")
@app_commands.describe(action="add or remove", role="The role", target="all, bots, or humans")
@app_commands.choices(action=[
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove"),
], target=[
    app_commands.Choice(name="all", value="all"),
    app_commands.Choice(name="bots", value="bots"),
    app_commands.Choice(name="humans", value="humans"),
])
async def roleall(interaction: discord.Interaction, action: str, role: discord.Role, target: str = "all"):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    members = interaction.guild.members
    if target == "bots":
        members = [m for m in members if m.bot]
    elif target == "humans":
        members = [m for m in members if not m.bot]
    count = 0
    for member in members:
        try:
            if action == "add":
                await member.add_roles(role)
            else:
                await member.remove_roles(role)
            count += 1
        except Exception:
            pass
    await interaction.followup.send(f"✅ {action.capitalize()}ed **{role.name}** for {count} {target}.", ephemeral=True)

# ── Ignore System ─────────────────────────────────────────────────────────────
IGNORED_CHANNELS = set()
IGNORED_USERS = set()
IGNORED_ROLES = set()

@bot.tree.command(name="ignorechannel", description="Toggle command usage in a channel (mod only)")
@app_commands.describe(channel="Channel to toggle")
async def ignorechannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    if channel.id in IGNORED_CHANNELS:
        IGNORED_CHANNELS.remove(channel.id)
        await interaction.response.send_message(f"✅ Commands re-enabled in {channel.mention}.", ephemeral=True)
    else:
        IGNORED_CHANNELS.add(channel.id)
        await interaction.response.send_message(f"✅ Commands disabled in {channel.mention}.", ephemeral=True)

@bot.tree.command(name="ignoreuser", description="Toggle command usage for a user (mod only)")
@app_commands.describe(user="User to toggle")
async def ignoreuser(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    if user.id in IGNORED_USERS:
        IGNORED_USERS.remove(user.id)
        await interaction.response.send_message(f"✅ Commands re-enabled for {user.mention}.", ephemeral=True)
    else:
        IGNORED_USERS.add(user.id)
        await interaction.response.send_message(f"✅ Commands disabled for {user.mention}.", ephemeral=True)

@bot.tree.command(name="ignorerole", description="Toggle command usage for a role (mod only)")
@app_commands.describe(role="Role to toggle")
async def ignorerole(interaction: discord.Interaction, role: discord.Role):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    if role.id in IGNORED_ROLES:
        IGNORED_ROLES.remove(role.id)
        await interaction.response.send_message(f"✅ Commands re-enabled for **{role.name}**.", ephemeral=True)
    else:
        IGNORED_ROLES.add(role.id)
        await interaction.response.send_message(f"✅ Commands disabled for **{role.name}**.", ephemeral=True)

# ── Custom Commands ───────────────────────────────────────────────────────────
CUSTOM_COMMANDS = {}
CUSTOM_COMMANDS_FILE = "custom_commands.json"

def save_custom_commands():
    with open(CUSTOM_COMMANDS_FILE, "w") as f:
        json.dump(CUSTOM_COMMANDS, f, indent=2)

def load_custom_commands():
    global CUSTOM_COMMANDS
    if os.path.exists(CUSTOM_COMMANDS_FILE):
        with open(CUSTOM_COMMANDS_FILE) as f:
            CUSTOM_COMMANDS = json.load(f)
        print(f"✅ Loaded {len(CUSTOM_COMMANDS)} custom commands")

load_custom_commands()

@bot.tree.command(name="customcmd", description="Manage custom commands (mod only)")
@app_commands.describe(action="create, delete, enable, disable, list, show", name="Command name", response="Response text (for create)")
@app_commands.choices(action=[
    app_commands.Choice(name="create", value="create"),
    app_commands.Choice(name="delete", value="delete"),
    app_commands.Choice(name="enable", value="enable"),
    app_commands.Choice(name="disable", value="disable"),
    app_commands.Choice(name="list", value="list"),
    app_commands.Choice(name="show", value="show"),
])
async def customcmd(interaction: discord.Interaction, action: str, name: str = None, response: str = None):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    if action == "create":
        if not name or not response:
            await interaction.response.send_message("❌ Provide both name and response.", ephemeral=True)
            return
        CUSTOM_COMMANDS[name.lower()] = {"response": response, "enabled": True}
        save_custom_commands()
        await interaction.response.send_message(f"✅ Custom command `!{name}` created.", ephemeral=True)
    elif action == "delete":
        if name and name.lower() in CUSTOM_COMMANDS:
            del CUSTOM_COMMANDS[name.lower()]
            save_custom_commands()
            await interaction.response.send_message(f"✅ Custom command `!{name}` deleted.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Command not found.", ephemeral=True)
    elif action == "enable":
        if name and name.lower() in CUSTOM_COMMANDS:
            CUSTOM_COMMANDS[name.lower()]["enabled"] = True
            save_custom_commands()
            await interaction.response.send_message(f"✅ `!{name}` enabled.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Command not found.", ephemeral=True)
    elif action == "disable":
        if name and name.lower() in CUSTOM_COMMANDS:
            CUSTOM_COMMANDS[name.lower()]["enabled"] = False
            save_custom_commands()
            await interaction.response.send_message(f"✅ `!{name}` disabled.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Command not found.", ephemeral=True)
    elif action == "list":
        if not CUSTOM_COMMANDS:
            await interaction.response.send_message("No custom commands yet.", ephemeral=True)
            return
        lines = [f"`!{n}` — {'✅' if v['enabled'] else '❌'}" for n, v in CUSTOM_COMMANDS.items()]
        await interaction.response.send_message("**Custom Commands:**\n" + "\n".join(lines), ephemeral=True)
    elif action == "show":
        if name and name.lower() in CUSTOM_COMMANDS:
            cmd = CUSTOM_COMMANDS[name.lower()]
            await interaction.response.send_message(f"`!{name}` → {cmd['response']} ({'enabled' if cmd['enabled'] else 'disabled'})", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Command not found.", ephemeral=True)

# ── Announce ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="announce", description="Send an announcement (mod only)")
@app_commands.describe(channel="Channel to send to", message="The announcement", ping="Who to ping: none, everyone, here, or a role name")
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, message: str, ping: str = "none"):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    prefix = ""
    if ping == "everyone":
        prefix = "@everyone\n"
    elif ping == "here":
        prefix = "@here\n"
    elif ping not in ("none", ""):
        role = discord.utils.get(interaction.guild.roles, name=ping)
        if role:
            prefix = f"{role.mention}\n"
    await channel.send(f"{prefix}{message}")
    await interaction.response.send_message(f"✅ Announcement sent to {channel.mention}.", ephemeral=True)

# ── Giveaway System ───────────────────────────────────────────────────────────

GIVEAWAYS = {}
GIVEAWAYS_FILE = "giveaways.json"

def save_giveaways():
    with open(GIVEAWAYS_FILE, "w") as f:
        json.dump({str(k): v for k, v in GIVEAWAYS.items()}, f, indent=2)

def load_giveaways():
    global GIVEAWAYS
    if os.path.exists(GIVEAWAYS_FILE):
        with open(GIVEAWAYS_FILE) as f:
            data = json.load(f)
        GIVEAWAYS = {int(k): v for k, v in data.items()}
        print(f"✅ Loaded {len(GIVEAWAYS)} giveaways")

load_giveaways()

def parse_duration(duration: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    match = re.fullmatch(r"(\d+)([smhd])", duration.strip().lower())
    if not match:
        raise ValueError("Invalid duration")
    return int(match.group(1)) * units[match.group(2)]

@bot.tree.command(name="giveaway", description="Create and manage giveaways (mod only)")
@app_commands.describe(
    action="create, end, or reroll",
    channel="Channel for the giveaway (create only)",
    winners="Number of winners (create only)",
    duration="Duration e.g. 1h, 30m, 2d (create only)",
    name="Giveaway prize name (create only)",
    message_id="Message ID to end or reroll"
)
@app_commands.choices(action=[
    app_commands.Choice(name="create", value="create"),
    app_commands.Choice(name="end", value="end"),
    app_commands.Choice(name="reroll", value="reroll"),
])
async def giveaway(interaction: discord.Interaction, action: str,
                   channel: discord.TextChannel = None, winners: int = 1,
                   duration: str = None, name: str = None, message_id: str = None):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return

    if action == "create":
        if not channel or not duration or not name:
            await interaction.response.send_message("❌ Provide channel, duration, and name.", ephemeral=True)
            return
        try:
            seconds = parse_duration(duration)
        except ValueError:
            await interaction.response.send_message("❌ Invalid duration. Use format like `1h`, `30m`, `2d`.", ephemeral=True)
            return

        end_time = datetime.now(timezone.utc).timestamp() + seconds
        embed = discord.Embed(
            title=f"🎉 GIVEAWAY — {name}",
            description=f"React with 🎉 to enter!\n\n**Winners:** {winners}\n**Ends:** <t:{int(end_time)}:R>",
            color=discord.Color.gold()
        )
        embed.set_footer(text="NakamaShip™ Giveaway")
        msg = await channel.send(embed=embed)
        await msg.add_reaction("🎉")

        GIVEAWAYS[msg.id] = {
            "channel_id": channel.id,
            "winners": winners,
            "end_time": end_time,
            "name": name,
            "entries": []
        }
        save_giveaways()

        await interaction.response.send_message(f"✅ Giveaway started in {channel.mention}!", ephemeral=True)

        async def end_giveaway_later():
            await asyncio.sleep(seconds)
            await conclude_giveaway(msg.id)

        asyncio.create_task(end_giveaway_later())

    elif action in ("end", "reroll"):
        if not message_id:
            await interaction.response.send_message("❌ Provide a message ID.", ephemeral=True)
            return
        mid = int(message_id)
        await interaction.response.defer(ephemeral=True)
        await conclude_giveaway(mid, reroll=(action == "reroll"))
        await interaction.followup.send("✅ Done!", ephemeral=True)

async def conclude_giveaway(message_id: int, reroll: bool = False):
    data = GIVEAWAYS.get(message_id)
    if not data:
        return
    channel = bot.get_channel(data["channel_id"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(message_id)
    except Exception:
        return

    entries = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if not user.bot:
                    entries.append(user)

    num_winners = data["winners"]
    if not entries:
        await channel.send("🎉 Giveaway ended — no valid entries!")
        return

    picked = random.sample(entries, min(num_winners, len(entries)))
    mentions = ", ".join(w.mention for w in picked)
    prefix = "🔄 Rerolled!" if reroll else "🎉 Giveaway ended!"
    await channel.send(f"{prefix} **{data['name']}** winners: {mentions} — congratulations!")

# ── Add Emote ─────────────────────────────────────────────────────────────────
@bot.tree.command(name="addemote", description="Add an emote to the server (mod only)")
@app_commands.describe(name="Emote name", url="Image URL for the emote")
async def addemote(interaction: discord.Interaction, name: str, url: str):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                await interaction.followup.send("❌ Could not fetch image.", ephemeral=True)
                return
            image_data = await resp.read()
    try:
        emoji = await interaction.guild.create_custom_emoji(name=name, image=image_data)
        await interaction.followup.send(f"✅ Emote {emoji} added!", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

bot.run(TOKEN)