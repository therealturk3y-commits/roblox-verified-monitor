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
PAGE_DELAY = float(os.getenv("PAGE_DELAY", "1.5"))

BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CURRENT_CHANNEL = os.environ["CURRENT_USERS_CHANNEL_ID"]
NEW_CHANNEL = os.environ["NEW_USERS_CHANNEL_ID"]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; RobloxVerifiedMonitor/1.0)"
})


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def load_ids():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(str(x) for x in json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_ids(ids):
    temp_file = STATE_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, indent=2)

    os.replace(temp_file, STATE_FILE)


# --------------------------------------------------
# DISCORD
# --------------------------------------------------

def send_discord_message(channel_id, embeds):
    """
    Discord allows up to 10 embeds in one message.
    """

    url = (
        f"https://discord.com/api/v10/"
        f"channels/{channel_id}/messages"
    )

    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "embeds": embeds
    }

    while True:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60
        )

        if response.status_code == 429:
            try:
                retry_after = float(
                    response.json().get("retry_after", 5)
                )
            except Exception:
                retry_after = 5

            print(
                f"Discord rate limit. "
                f"Waiting {retry_after:.2f}s..."
            )

            time.sleep(retry_after)
            continue

        response.raise_for_status()
        return


# --------------------------------------------------
# WEBSITE
# --------------------------------------------------

def get_page(page):
    while True:
        try:
            response = session.get(
                BASE_URL,
                params={
                    "page": page,
                    "sort": "name_asc"
                },
                timeout=45
            )

            if response.status_code == 429:
                print("Website rate limited. Waiting 60 seconds...")
                time.sleep(60)
                continue

            response.raise_for_status()

            return response.text

        except requests.RequestException as e:
            print(f"Page {page} request failed: {e}")
            print("Retrying in 15 seconds...")
            time.sleep(15)


def parse_users(html):
    soup = BeautifulSoup(html, "html.parser")

    users = []
    seen_ids = set()

    # Roblox Verifieds user pages appear as /user/<ID>
    links = soup.find_all(
        "a",
        href=re.compile(r"^/user/\d+$")
    )

    for link in links:

        href = link.get("href", "")

        match = re.search(
            r"/user/(\d+)",
            href
        )

        if not match:
            continue

        user_id = match.group(1)

        if user_id in seen_ids:
            continue

        seen_ids.add(user_id)

        text = link.get_text(
            " ",
            strip=True
        )

        username_match = re.search(
            r"@([A-Za-z0-9_]+)",
            text
        )

        if username_match:
            username = username_match.group(1)
            display_name = text.split("@", 1)[0].strip()
        else:
            username = text.strip()
            display_name = text.strip()

        if not username:
            username = user_id

        if not display_name:
            display_name = username

        users.append({
            "id": user_id,
            "username": username,
            "display": display_name,
            "profile":
                f"https://www.roblox.com/users/{user_id}/profile"
        })

    return users


# --------------------------------------------------
# ROBLOX AVATAR
# --------------------------------------------------

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

    except Exception as e:
        print(
            f"Could not get avatar for {user_id}: {e}"
        )

    return None


# --------------------------------------------------
# EMBEDS
# --------------------------------------------------

def create_embed(user, title):

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


# --------------------------------------------------
# INITIAL POPULATION
# --------------------------------------------------

def initial_population(users, known):

    print()
    print("======================================")
    print(" INITIAL POPULATION")
    print("======================================")
    print(f"Users found: {len(users)}")
    print()

    # Discord supports a maximum of 10 embeds/message.
    batch = []

    total = len(users)

    for index, user in enumerate(users, start=1):

        print(
            f"Preparing {index}/{total}: "
            f"@{user['username']}"
        )

        embed = create_embed(
            user,
            "👤 Current Verified Roblox User"
        )

        batch.append(embed)

        known.add(user["id"])

        # Send every 10 users
        if len(batch) == 10:

            send_discord_message(
                CURRENT_CHANNEL,
                batch
            )

            print(
                f"Sent batch "
                f"{index - len(batch) + 1}-{index}"
            )

            batch = []

    # Send remaining users
    if batch:
        send_discord_message(
            CURRENT_CHANNEL,
            batch
        )

        print(
            f"Sent final batch "
            f"({len(batch)} users)"
        )

    save_ids(known)

    print()
    print(
        f"Initial population complete: "
        f"{len(known)} users"
    )


# --------------------------------------------------
# FUTURE SCANS
# --------------------------------------------------

def check_for_new_users(users, known):

    new_users = []

    for user in users:

        if user["id"] in known:
            continue

        new_users.append(user)

    print()
    print(
        f"New users detected: "
        f"{len(new_users)}"
    )

    for user in new_users:

        print(
            f"NEW: @{user['username']} "
            f"({user['id']})"
        )

        embed = create_embed(
            user,
            "🟢 New Verified Roblox User"
        )

        send_discord_message(
            NEW_CHANNEL,
            [embed]
        )

        # Only mark it known after Discord accepted it.
        known.add(user["id"])

    if new_users:
        save_ids(known)


# --------------------------------------------------
# SCAN ALL PAGES
# --------------------------------------------------

def scan_all_pages():

    all_users = []
    page = 1

    while True:

        print(
            f"Scanning page {page}..."
        )

        html = get_page(page)

        users = parse_users(html)

        print(
            f"Page {page}: "
            f"{len(users)} users"
        )

        # Empty page = end
        if not users:
            break

        # Prevent duplicate users across pages
        existing = {
            user["id"]
            for user in all_users
        }

        for user in users:

            if user["id"] not in existing:
                all_users.append(user)

        # If this page is not full,
        # it is the last page.
        if len(users) < PAGE_SIZE:
            print(
                f"Page {page} is not full. "
                f"Reached final page."
            )
            break

        page += 1

        time.sleep(PAGE_DELAY)

    return all_users


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    print()
    print("======================================")
    print(" ROBLOX VERIFIED MONITOR")
    print("======================================")
    print()

    known = load_ids()

    print(
        f"Known users in database: "
        f"{len(known)}"
    )

    users = scan_all_pages()

    print()
    print(
        f"Total users discovered: "
        f"{len(users)}"
    )

    # Empty database = first scan
    if not known:

        initial_population(
            users,
            known
        )

    else:

        check_for_new_users(
            users,
            known
        )

    print()
    print("Scan finished.")
    print()


if __name__ == "__main__":
    main()
