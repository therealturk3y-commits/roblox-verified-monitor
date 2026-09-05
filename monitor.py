import json
import os
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://robloxverifieds.com/verified"
STATE_FILE = "processed_users.json"

PAGE_SIZE = int(os.getenv("PAGE_SIZE", "25"))
PAGE_DELAY = float(os.getenv("PAGE_DELAY", "2"))
MESSAGE_DELAY = float(os.getenv("MESSAGE_DELAY", "1.5"))

BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CURRENT_CHANNEL = os.environ["CURRENT_USERS_CHANNEL_ID"]
NEW_CHANNEL = os.environ["NEW_USERS_CHANNEL_ID"]

session = requests.Session()
session.headers["User-Agent"] = (
    "Mozilla/5.0 (compatible; RobloxVerifiedMonitor/1.0)"
)


def load_ids():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return set(map(str, json.load(f)))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_ids(ids):
    temp = STATE_FILE + ".tmp"

    with open(temp, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, indent=2)

    os.replace(temp, STATE_FILE)


def discord_send(channel_id, embed):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    while True:
        response = requests.post(
            url,
            headers=headers,
            json={"embeds": [embed]},
            timeout=30
        )

        if response.status_code == 429:
            try:
                wait = float(
                    response.json().get("retry_after", 5)
                )
            except Exception:
                wait = 5

            time.sleep(wait)
            continue

        response.raise_for_status()
        return


def get_page(page):
    while True:
        try:
            response = session.get(
                BASE_URL,
                params={
                    "page": page,
                    "sort": "name_asc"
                },
                timeout=30
            )

            if response.status_code == 429:
                time.sleep(60)
                continue

            response.raise_for_status()
            return response.text

        except requests.RequestException:
            time.sleep(15)


def parse_users(html):
    soup = BeautifulSoup(html, "html.parser")

    users = []
    seen = set()

    for link in soup.find_all(
        "a",
        href=re.compile(r"^/user/\d+$")
    ):
        match = re.search(
            r"/user/(\d+)",
            link.get("href", "")
        )

        if not match:
            continue

        user_id = match.group(1)

        if user_id in seen:
            continue

        seen.add(user_id)

        text = link.get_text(
            " ",
            strip=True
        )

        username_match = re.search(
            r"@([A-Za-z0-9_]+)",
            text
        )

        username = (
            username_match.group(1)
            if username_match
            else text.split()[0]
            if text
            else user_id
        )

        display_name = (
            text.split("@", 1)[0].strip()
            if "@" in text
            else text
        )

        users.append({
            "id": user_id,
            "username": username,
            "display": display_name or username,
            "profile":
                f"https://www.roblox.com/users/{user_id}/profile"
        })

    return users


def get_avatar(user_id):
    try:
        response = requests.get(
            "https://thumbnails.roblox.com/v1/users/avatar-headshot",
            params={
                "userIds": user_id,
                "size": "420x420",
                "format": "Png",
                "isCircular": "false"
            },
            timeout=30
        )

        response.raise_for_status()

        data = response.json().get("data", [])

        if data:
            return data[0].get("imageUrl")

    except Exception:
        pass

    return None


def make_embed(user, title):
    embed = {
        "title": title,
        "url": user["profile"],
        "fields": [
            {
                "name": "Username",
                "value": f"`@{user['username']}`",
                "inline": True
            },
            {
                "name": "Display Name",
                "value": f"`{user['display']}`",
                "inline": True
            },
            {
                "name": "Roblox User ID",
                "value": f"`{user['id']}`",
                "inline": True
            },
            {
                "name": "Profile",
                "value":
                    f"[Open Roblox Profile]"
                    f"({user['profile']})"
            }
        ],
        "timestamp":
            datetime.now(timezone.utc).isoformat(),
        "footer": {
            "text": "Roblox Verified Monitor"
        }
    }

    avatar_url = get_avatar(user["id"])

    if avatar_url:
        embed["thumbnail"] = {
            "url": avatar_url
        }

    return embed


def scan():
    known = load_ids()

    # Empty database = first scan
    first_scan = len(known) == 0

    discovered = []

    page = 1

    while True:
        print(f"Scanning page {page}...")

        html = get_page(page)
        users = parse_users(html)

        print(
            f"Found {len(users)} users on page {page}"
        )

        if not users:
            break

        discovered.extend(users)

        # Last page
        if len(users) < PAGE_SIZE:
            break

        page += 1

        time.sleep(PAGE_DELAY)

    # -----------------------------------------
    # FIRST SCAN
    # -----------------------------------------

    if first_scan:
        print(
            f"Initial scan: {len(discovered)} users"
        )

        for user in discovered:
            discord_send(
                CURRENT_CHANNEL,
                make_embed(
                    user,
                    "👤 Current Verified Roblox User"
                )
            )

            known.add(user["id"])
            save_ids(known)

            time.sleep(MESSAGE_DELAY)

        print("Initial population complete.")
        return

    # -----------------------------------------
    # FUTURE SCANS
    # -----------------------------------------

    new_count = 0

    for user in discovered:

        if user["id"] in known:
            continue

        print(
            f"NEW USER: @{user['username']}"
        )

        discord_send(
            NEW_CHANNEL,
            make_embed(
                user,
                "🟢 New Verified Roblox User"
            )
        )

        known.add(user["id"])

        save_ids(known)

        new_count += 1

        time.sleep(MESSAGE_DELAY)

    print(
        f"Scan complete. "
        f"New users: {new_count}"
    )


if __name__ == "__main__":
    scan()
