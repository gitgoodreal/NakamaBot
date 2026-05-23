import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import json
from datetime import timedelta, datetime, timezone
import pytz
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

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
_verifying_now = set()  # Tracks users mid-verification to prevent on_member_update double-firing
ROLE_HIERARCHY = ["King of the Pirates", "Admin", "Manager", "Moderator"]
BAD_WORDS = ["badword1", "badword2"]
WARNINGS = {}
_welcome_channel_override = {}

VERIFY_CONFIG = {}
VERIFY_CONFIG_FILE = "verify_config.json"

# ── Change 4: redirect to Discord after OAuth ──────────────────────────────────
# The Cloudflare worker should redirect to this URL after auth succeeds.
# Set your redirect URI in the OAuth2 app to:  https://discord.com/channels/@me
VERIFY_URL = "https://nakama-auth.existslays.workers.dev"

def save_verify_config():
    serializable = {str(k): v for k, v in VERIFY_CONFIG.items()}
    with open(VERIFY_CONFIG_FILE, "w") as f:
        json.dump(serializable, f)

def load_verify_config():
    global VERIFY_CONFIG
    if os.path.exists(VERIFY_CONFIG_FILE):
        with open(VERIFY_CONFIG_FILE, "r") as f:
            data = json.load(f)
            VERIFY_CONFIG = {int(k): v for k, v in data.items()}
        print(f"✅ Loaded verify config for {len(VERIFY_CONFIG)} guild(s)")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

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

# ── Verification views ─────────────────────────────────────────────────────────

class VerifyButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Verify Me", style=discord.ButtonStyle.success, custom_id="verify:button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_verification_success(interaction)

class RulesVerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📜 I agree to the rules", style=discord.ButtonStyle.primary, custom_id="verify:rules")
    async def rules_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_verification_success(interaction)

class QuestionVerifyModal(discord.ui.Modal, title="🔐 Verification"):
    answer = discord.ui.TextInput(
        label="Your Answer",
        placeholder="Type your answer here...",
        required=True,
    )

    def __init__(self, correct_answer: str):
        super().__init__()
        self.correct_answer = correct_answer.strip().lower()

    async def on_submit(self, interaction: discord.Interaction):
        if self.answer.value.strip().lower() == self.correct_answer:
            await handle_verification_success(interaction)
        else:
            await interaction.response.send_message("❌ Incorrect answer! Please try again.", ephemeral=True)

class QuestionVerifyView(discord.ui.View):
    def __init__(self, correct_answer: str):
        super().__init__(timeout=None)
        self.correct_answer = correct_answer

    @discord.ui.button(label="🔐 Answer to Verify", style=discord.ButtonStyle.primary, custom_id="verify:question")
    async def question_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = VERIFY_CONFIG.get(interaction.guild.id)
        if not config:
            await interaction.response.send_message("❌ Verification not configured.", ephemeral=True)
            return
        modal = QuestionVerifyModal(correct_answer=config["answer"])
        await interaction.response.send_modal(modal)

async def handle_verification_success(interaction: discord.Interaction):
    """Shared handler for all in-server verification methods."""
    config = VERIFY_CONFIG.get(interaction.guild.id)
    if not config:
        print(f"❌ [VERIFY] No config found for guild {interaction.guild.id}")
        await interaction.response.send_message("❌ Verification not set up yet.", ephemeral=True)
        return

    member = interaction.user
    guild  = interaction.guild

    verified_role   = guild.get_role(config["verified_role_id"])
    unverified_role = guild.get_role(config["unverified_role_id"])

    print(f"[VERIFY] {member} ({member.id}) attempting verification in {guild.name}")
    print(f"[VERIFY] verified_role={verified_role} (id={config['verified_role_id']}) | unverified_role={unverified_role} (id={config['unverified_role_id']})")

    if not verified_role:
        print(f"❌ [VERIFY] Verified role ID {config['verified_role_id']} not found in guild!")
        await interaction.response.send_message("❌ Verified role not found. Contact an admin.", ephemeral=True)
        await log_action(guild, "Verification Error", bot.user, member, f"Verified role ID {config['verified_role_id']} not found")
        return

    if verified_role in member.roles:
        print(f"[VERIFY] {member} is already verified, skipping")
        await interaction.response.send_message("✅ You're already verified!", ephemeral=True)
        return

    try:
        if unverified_role and unverified_role in member.roles:
            await member.remove_roles(unverified_role, reason="Verified")
            print(f"✅ [VERIFY] Removed unverified role from {member}")
        else:
            print(f"⚠️ [VERIFY] Unverified role not on {member} or not found, skipping removal")

        _verifying_now.add(member.id)
        await member.add_roles(verified_role, reason="Passed verification")
        print(f"✅ [VERIFY] Added verified role to {member}")

    except discord.Forbidden as e:
        print(f"❌ [VERIFY] Forbidden — bot lacks permissions. Bot top role position: {guild.me.top_role.position}, verified role position: {verified_role.position}")
        print(f"❌ [VERIFY] Error: {e}")
        await interaction.response.send_message("❌ I don't have permission to assign roles. Please contact an admin.", ephemeral=True)
        await log_action(guild, "Verification Error — Forbidden", bot.user, member,
                         f"Bot top role pos: {guild.me.top_role.position} | Verified role pos: {verified_role.position}")
        return
    except discord.HTTPException as e:
        print(f"❌ [VERIFY] HTTPException assigning roles to {member}: status={e.status} text={e.text}")
        await interaction.response.send_message("❌ Something went wrong assigning your role. Try again.", ephemeral=True)
        await log_action(guild, "Verification Error — HTTP", bot.user, member, f"{e.status}: {e.text}")
        return

    await interaction.response.send_message(
        f"🎉 You're now verified! Welcome to the server, {member.mention}!", ephemeral=True
    )
    print(f"✅ [VERIFY] {member} successfully verified in {guild.name}")
    _verifying_now.discard(member.id)
    await log_action(guild, "Member Verified", bot.user, member)

# ── Change 5: DM-based verification ───────────────────────────────────────────
# Users can verify via DM as well as in the server.
# The bot listens for DMs and triggers verification there too.

class DMVerifyView(discord.ui.View):
    """Sent via DM so the user can verify without going to the server channel."""
    def __init__(self, guild_id: int, member: discord.Member):
        super().__init__(timeout=600)  # 10-minute window
        self.guild_id = guild_id
        self.member = member

    @discord.ui.button(label="✅ Verify Me", style=discord.ButtonStyle.success, custom_id="verify:dm_button")
    async def verify_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = VERIFY_CONFIG.get(self.guild_id)
        if not config:
            await interaction.response.send_message("❌ Verification is not configured for that server.", ephemeral=True)
            return

        guild = bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message("❌ Could not find the server.", ephemeral=True)
            return

        member = guild.get_member(self.member.id)
        if not member:
            await interaction.response.send_message("❌ You don't appear to be in the server anymore.", ephemeral=True)
            return

        verified_role   = guild.get_role(config["verified_role_id"])
        unverified_role = guild.get_role(config["unverified_role_id"])

        if verified_role and verified_role in member.roles:
            await interaction.response.send_message("✅ You're already verified!", ephemeral=True)
            return

        print(f"[VERIFY/DM] {member} ({member.id}) attempting DM verification for {guild.name}")
        print(f"[VERIFY/DM] verified_role={verified_role} | unverified_role={unverified_role}")

        if not verified_role:
            print(f"❌ [VERIFY/DM] Verified role ID {config['verified_role_id']} not found!")
            await interaction.response.send_message("❌ Verified role not found. Contact an admin.", ephemeral=True)
            await log_action(guild, "Verification Error (DM)", bot.user, member, f"Verified role ID {config['verified_role_id']} not found")
            return

        try:
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="Verified via DM")
                print(f"✅ [VERIFY/DM] Removed unverified role from {member}")
            else:
                print(f"⚠️ [VERIFY/DM] Unverified role not on {member} or not found, skipping removal")

            _verifying_now.add(member.id)
            await member.add_roles(verified_role, reason="Verified via DM")
            print(f"✅ [VERIFY/DM] Added verified role to {member}")

        except discord.Forbidden as e:
            print(f"❌ [VERIFY/DM] Forbidden — bot top role pos: {guild.me.top_role.position}, verified role pos: {verified_role.position}")
            print(f"❌ [VERIFY/DM] Error: {e}")
            await interaction.response.send_message("❌ I don't have permission to assign roles. Please contact an admin.", ephemeral=True)
            await log_action(guild, "Verification Error (DM) — Forbidden", bot.user, member,
                             f"Bot top role pos: {guild.me.top_role.position} | Verified role pos: {verified_role.position}")
            return
        except discord.HTTPException as e:
            print(f"❌ [VERIFY/DM] HTTPException: status={e.status} text={e.text}")
            await interaction.response.send_message("❌ Something went wrong assigning your role. Try again.", ephemeral=True)
            await log_action(guild, "Verification Error (DM) — HTTP", bot.user, member, f"{e.status}: {e.text}")
            return

        await interaction.response.send_message(f"🎉 You're now verified in **{guild.name}**! You have full access.", ephemeral=True)
        self.stop()
        _verifying_now.discard(member.id)
        print(f"✅ [VERIFY/DM] {member} successfully verified in {guild.name}")
        await log_action(guild, "Member Verified (DM)", bot.user, member)

# ── Setup helpers ──────────────────────────────────────────────────────────────

class MethodSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.chosen_method = None

    @discord.ui.button(label="🖱️ Button Click", style=discord.ButtonStyle.secondary)
    async def btn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen_method = "button"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="📜 Rules Agreement", style=discord.ButtonStyle.secondary)
    async def btn_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen_method = "rules"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="❓ Question & Answer", style=discord.ButtonStyle.secondary)
    async def btn_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen_method = "question"
        self.stop()
        await interaction.response.defer()

class QuestionSetupModal(discord.ui.Modal, title="Set Verification Question"):
    question = discord.ui.TextInput(label="Question", placeholder="e.g. What is our server about?")
    answer   = discord.ui.TextInput(label="Answer (case-insensitive)", placeholder="e.g. gaming")

    async def on_submit(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.stop()

class QuestionModalLaunchView(discord.ui.View):
    def __init__(self, modal: QuestionSetupModal):
        super().__init__(timeout=120)
        self.modal = modal

    @discord.ui.button(label="📝 Set Question & Answer", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.modal)
        self.stop()

# ── /setupverify ───────────────────────────────────────────────────────────────

@bot.tree.command(name="setupverify", description="Set up the verification system for this server")
async def setupverify(interaction: discord.Interaction):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return

    guild = interaction.guild
    method_view = MethodSelectView()
    await interaction.response.send_message(
        "**🔐 Verification Setup — Step 1/3**\n\nChoose a verification method:",
        view=method_view, ephemeral=True
    )
    await method_view.wait()

    if not method_view.chosen_method:
        await interaction.edit_original_response(content="⏰ Setup timed out.", view=None)
        return

    method = method_view.chosen_method
    question_text = None
    answer_text   = None

    if method == "question":
        modal = QuestionSetupModal()
        await interaction.edit_original_response(
            content="**🔐 Verification Setup — Step 2/3**\n\nClick below to set your question & answer:",
            view=QuestionModalLaunchView(modal)
        )
        await modal.wait()
        if not hasattr(modal, 'interaction'):
            await interaction.edit_original_response(content="⏰ Setup timed out.", view=None)
            return
        question_text = modal.question.value
        answer_text   = modal.answer.value
        await modal.interaction.response.defer()
    else:
        await interaction.edit_original_response(
            content="**🔐 Verification Setup — Step 2/3**\n\n⏳ Setting up roles...", view=None
        )

    existing_config = VERIFY_CONFIG.get(guild.id, {})

    VERIFIED_ROLE_ID = 1503577648868233424
    verified_role = guild.get_role(VERIFIED_ROLE_ID)
    if not verified_role:
        await interaction.edit_original_response(
            content="❌ Could not find the Verified role (ID `1503577648868233424`). Make sure it exists in this server.",
            view=None
        )
        return

    # ── Change 1: never auto-create a verification channel ────────────────────
    # Reuse any previously stored channel; if none, ask the mod to provide one.
    existing_channel = guild.get_channel(existing_config.get("channel_id", 0))
    if not existing_channel:
        await interaction.edit_original_response(
            content=(
                "⚠️ No verification channel found from a previous setup.\n"
                "Please create the channel yourself, then run `/setverifychannel #channel` "
                "followed by `/setupverify` again."
            ),
            view=None
        )
        return

    verify_channel = existing_channel

    # Unverified role: reuse existing or create fresh
    unverified_role = guild.get_role(existing_config.get("unverified_role_id", 0))
    if not unverified_role:
        unverified_role = await guild.create_role(
            name="🔒 Unverified",
            color=discord.Color.dark_gray(),
            reason="Auto-created by verification setup"
        )

    VERIFY_CONFIG[guild.id] = {
        "method":             method,
        "question":           question_text,
        "answer":             answer_text,
        "verified_role_id":   verified_role.id,
        "unverified_role_id": unverified_role.id,
        "channel_id":         verify_channel.id,
    }
    save_verify_config()

    await verify_channel.purge(limit=10)

    if method == "button":
        embed = discord.Embed(
            title="🔐 Verification Required",
            description=(
                "Welcome! To access the rest of the server, please verify yourself.\n\n"
                "You can verify **right here** by clicking the button, or check your DMs for a link."
            ),
            color=discord.Color.blue()
        )
        view = VerifyButtonView()
    elif method == "rules":
        embed = discord.Embed(
            title="📜 Rules Agreement",
            description=(
                "Welcome! Please read the server rules and agree to them to gain access.\n\n"
                "By clicking below, you confirm you have read and agree to all server rules."
            ),
            color=discord.Color.orange()
        )
        view = RulesVerifyView()
    elif method == "question":
        embed = discord.Embed(
            title="❓ Answer to Verify",
            description=(
                f"Welcome! Please answer the following question to verify:\n\n"
                f"**{question_text}**\n\n"
                f"Click the button below to submit your answer."
            ),
            color=discord.Color.purple()
        )
        view = QuestionVerifyView(correct_answer=answer_text)

    embed.set_footer(text="You will receive the Verified role upon completion.")
    await verify_channel.send(embed=embed, view=view)

    for channel in guild.channels:
        if channel.id == verify_channel.id:
            continue
        try:
            await channel.set_permissions(
                unverified_role, read_messages=False,
                reason="Verification system: restrict unverified members"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    method_label = {"button": "Button Click", "rules": "Rules Agreement", "question": "Question & Answer"}[method]
    await interaction.edit_original_response(
        content=(
            f"✅ **Verification setup complete!**\n\n"
            f"📌 **Method:** {method_label}\n"
            f"📢 **Channel:** {verify_channel.mention}\n"
            f"✅ **Verified Role:** {verified_role.mention}\n"
            f"🔒 **Unverified Role:** {unverified_role.mention}\n\n"
            f"New members will automatically receive the Unverified role and be directed to {verify_channel.mention}."
        ),
        view=None
    )
    await log_action(guild, "Verification Setup", interaction.user, verify_channel, f"Method: {method_label}")

# ── /setverifychannel ──────────────────────────────────────────────────────────
# Since we no longer auto-create the channel, mods set it manually once.

@bot.tree.command(name="setverifychannel", description="Set the channel used for verification")
@app_commands.describe(channel="The channel you created for verification")
async def setverifychannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return

    guild = interaction.guild
    config = VERIFY_CONFIG.get(guild.id, {})
    config["channel_id"] = channel.id
    VERIFY_CONFIG[guild.id] = config
    save_verify_config()

    await interaction.response.send_message(
        f"✅ Verification channel set to {channel.mention}. Now run `/setupverify` to finish setup.",
        ephemeral=True
    )

# ── /resetverify ───────────────────────────────────────────────────────────────
# Change 2: also delete the unverified role on reset.

@bot.tree.command(name="resetverify", description="Reset and redo the verification setup")
async def resetverify(interaction: discord.Interaction):
    if not has_mod_role(interaction):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return

    guild = interaction.guild
    config = VERIFY_CONFIG.pop(guild.id, None)

    if config:
        # Delete the unverified role so it doesn't linger
        unverified_role = guild.get_role(config.get("unverified_role_id", 0))
        if unverified_role:
            try:
                await unverified_role.delete(reason="Verification reset by moderator")
            except (discord.Forbidden, discord.HTTPException):
                pass

    save_verify_config()
    await interaction.response.send_message(
        "🔄 Verification config cleared and Unverified role deleted.\n"
        "Run `/setverifychannel #channel` then `/setupverify` to set it up again.",
        ephemeral=True
    )

# ── Events ─────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    load_verify_config()
    load_sticky_config()
    bot.add_view(VerifyButtonView())
    bot.add_view(RulesVerifyView())
    bot.add_view(AddBirthdayView())
    bot.loop.create_task(birthday_checker())
    await bot.tree.sync()
    print(f"✅ {bot.user} is online! Synced slash commands globally.")

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    config = VERIFY_CONFIG.get(guild.id)

    if config:
        # Assign unverified role on join
        unverified_role = guild.get_role(config["unverified_role_id"])
        if unverified_role:
            try:
                await member.add_roles(unverified_role, reason="New member — awaiting verification")
            except discord.Forbidden:
                pass

        verify_channel = guild.get_channel(config["channel_id"])

        # Send a single embed DM — no verify button, just website link
        try:
            embed = discord.Embed(
                title=f"👋 Welcome to {guild.name}!",
                description=(
                    "To gain full access to the server you need to verify yourself.\n\n"
                    f"🌐 **Click the link below to verify:**\n{VERIFY_URL}\n\n"
                    + (f"💬 Or head to {verify_channel.mention} in the server." if verify_channel else "")
                ),
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            embed.set_footer(text="Takes less than 10 seconds — no forms, no email.")
            await member.send(embed=embed)
            print(f"✅ DM sent to {member}")
        except discord.Forbidden:
            print(f"❌ Could not DM {member} — DMs are closed")
    else:
        print(f"⚠️ No verify config for guild {guild.id}")

    # Welcome embed
    channel_id = get_welcome_channel_id(guild.id)
    channel = guild.get_channel(channel_id)
    if channel:
        embed = build_welcome_embed(member)
        await channel.send(content=member.mention, embed=embed)

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Watch for the verified role being added (e.g. via website OAuth) and DM the user."""
    config = VERIFY_CONFIG.get(after.guild.id)
    if not config:
        return

    verified_role   = after.guild.get_role(config["verified_role_id"])
    unverified_role = after.guild.get_role(config["unverified_role_id"])

    if not verified_role:
        return

    # Verified role just appeared on this member
    if verified_role not in before.roles and verified_role in after.roles:
        # Skip if the bot's own verify flow already handled this — avoids double welcome/DM
        if after.id in _verifying_now:
            _verifying_now.discard(after.id)
            return
        print(f"✅ [ROLE UPDATE] {after} just got the verified role in {after.guild.name}")

        # Remove unverified role if still present (worker may have missed it)
        if unverified_role and unverified_role in after.roles:
            try:
                await after.remove_roles(unverified_role, reason="Verified — cleanup via on_member_update")
                print(f"✅ [ROLE UPDATE] Removed unverified role from {after}")
            except discord.Forbidden:
                print(f"❌ [ROLE UPDATE] Forbidden when removing unverified role from {after}")
            except discord.HTTPException as e:
                print(f"❌ [ROLE UPDATE] HTTPException removing unverified role: {e.status} {e.text}")

        await log_action(after.guild, "Member Verified (Website)", bot.user, after)

spam_tracker = {}

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await on_message_afk(message)

    content = message.content.lower()
    if any(word in content for word in BAD_WORDS):
        await message.delete()
        await message.channel.send(f"{message.author.mention} Watch your language! ⚠️", delete_after=5)
        await log_action(message.guild, "Auto-Mod: Bad Word", bot.user, message.author, message.content)
        return

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

    # ── Repost sticky if one exists for this channel ───────────────────────────
    sticky = STICKY_CONFIG.get(message.channel.id)
    if sticky:
        try:
            # Delete old sticky
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

@bot.event
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

STICKY_CONFIG = {}          # {channel_id: {"message": str, "last_id": int}}

# ── Birthday system ──────────────────────────────────────────────────────────
BIRTHDAY_CONFIG = {}        # {user_id: {"day": int, "month": int, "timezone": str}}
BIRTHDAY_CONFIG_FILE = "birthday_config.json"
BIRTHDAY_WISH_CHANNEL_ID = 1501909942754344965  # General chat — where wishes are sent
BIRTHDAY_SETUP_CHANNEL_ID = None               # Birthday wishes channel — where setup chain lives
BIRTHDAY_LAST_CHAIN_MSG_ID = None              # ID of the last chain message (to disable its button)

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

    # Delete the last sticky message
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

    # Delete old sticky if one exists
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
            # Quick sanity check
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

        # Log to the server log channel
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
        # Post the chain message in the setup channel if configured, else reply inline
        if BIRTHDAY_SETUP_CHANNEL_ID:
            setup_channel = interaction.client.get_channel(BIRTHDAY_SETUP_CHANNEL_ID)
            if setup_channel:
                global BIRTHDAY_LAST_CHAIN_MSG_ID
                # Disable the button on the previous chain message
                if BIRTHDAY_LAST_CHAIN_MSG_ID:
                    try:
                        old_msg = await setup_channel.fetch_message(BIRTHDAY_LAST_CHAIN_MSG_ID)
                        await old_msg.delete()
                    except Exception:
                        pass
                # Post fresh message with the button
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
    # Post the initial chain message in the setup channel
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
    # Pre-fill timezone if they already have one, otherwise show picker
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

    # DM the user
    dm_status = "✅ DM sent"
    try:
        await user.send(
            f"🎂 **Happy Birthday, {user.display_name}!** 🎉\n"
            f"Wishing you an amazing day filled with joy! "
            f"The whole server is celebrating with you! 🥳"
        )
    except Exception:
        dm_status = "❌ DM failed (user may have DMs disabled)"

    # Post in birthday channel
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
                        # DM the birthday person
                        try:
                            user = await bot.fetch_user(user_id)
                            await user.send(
                                f"🎂 **Happy Birthday, {user.display_name}!** 🎉\n"
                                f"Wishing you an amazing day filled with joy! "
                                f"The whole server is celebrating with you! 🥳"
                            )
                        except Exception:
                            pass  # DMs may be closed

                        # Ping @everyone in birthday channel
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

bot.run(TOKEN)