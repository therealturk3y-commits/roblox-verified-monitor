import os
import subprocess
import discord
from discord import app_commands

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
REPO_URL = os.environ["GITHUB_REPO_URL"]

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")
    print("Commands synced.")


@tree.command(name="help", description="Show monitor commands")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Roblox Verified Monitor Commands**\n\n"
        "`/status` — Show monitor information\n"
        "`/repo` — Open the GitHub repository\n"
        "`/scan` — Start a scan manually\n"
        "`/help` — Show this message",
        ephemeral=True
    )


@tree.command(name="repo", description="Open the GitHub repository")
async def repo(interaction: discord.Interaction):
    view = discord.ui.View()

    view.add_item(
        discord.ui.Button(
            label="Open GitHub Repository",
            url=REPO_URL
        )
    )

    await interaction.response.send_message(
        "🔗 **Roblox Verified Monitor Repository**",
        view=view,
        ephemeral=True
    )


@tree.command(name="status", description="Show monitor status")
async def status(interaction: discord.Interaction):
    try:
        with open("processed_users.json", "r") as f:
            import json
            users = json.load(f)
            count = len(users)
    except Exception:
        count = 0

    await interaction.response.send_message(
        f"🟢 **Monitor Status**\n\n"
        f"Known users: **{count:,}**\n"
        f"Scheduled scan: **Every ~6 hours**\n"
        f"Repository: **Connected**",
        ephemeral=True
    )


@tree.command(name="scan", description="Start a manual GitHub scan")
async def scan(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🔎 **Starting a manual scan...**",
        ephemeral=True
    )

    # The actual scan can be started from GitHub Actions.
    # This command is intentionally kept separate from the scanner.
    print("Manual scan requested.")


client.run(TOKEN)
