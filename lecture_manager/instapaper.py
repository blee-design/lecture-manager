# File: instapaper.py

import requests
from .db import get_connection
from .utils import print_colored, COLORS, color_text

TABLE_NAME = "instapaper_credentials"

def get_credentials():
    """Retrieve stored credentials from DB. Return dict or None."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def save_credentials(consumer_key, consumer_secret, username, password):
    """Store credentials in DB."""
    conn = get_connection()
    cursor = conn.cursor()
    # Upsert (replace if exists)
    cursor.execute(f"""
        REPLACE INTO {TABLE_NAME} (id, consumer_key, consumer_secret, username, password)
        VALUES (1, %s, %s, %s, %s)
    """, (consumer_key, consumer_secret, username, password))
    conn.commit()
    cursor.close()
    conn.close()

def setup_credentials_interactive():
    """Prompt user for Instapaper credentials and save them."""
    print("\n" + "═" * 50)
    print_colored("  INSTAPAPER SETUP", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("To save lectures/questions to Instapaper, we need your app credentials.")
    print("You can get a Consumer Key and Secret from:")
    print("  https://www.instapaper.com/developers")
    print("(Create a new app – it will be in 'Owner Only' mode.)")
    print("\nWe also need your Instapaper login credentials for the Simple API.")
    print("(These are stored locally and never shared.)")
    print("═" * 50)

    consumer_key = input(color_text("Consumer Key: ", COLORS.MAGENTA)).strip()
    consumer_secret = input(color_text("Consumer Secret: ", COLORS.MAGENTA)).strip()
    username = input(color_text("Instapaper Username: ", COLORS.MAGENTA)).strip()
    password = input(color_text("Instapaper Password: ", COLORS.MAGENTA)).strip()

    if not all([consumer_key, consumer_secret, username, password]):
        print_colored("[!] All fields are required. Setup cancelled.", COLORS.RED)
        return False

    save_credentials(consumer_key, consumer_secret, username, password)
    print_colored("[✓] Instapaper credentials saved successfully.", COLORS.GREEN)
    return True

def add_to_instapaper(url, title=None, tags=None):
    """
    Save a URL to Instapaper using the Simple API.
    Returns (success, message).
    """
    creds = get_credentials()
    if not creds:
        print_colored("[i] No Instapaper credentials found. Starting setup...", COLORS.YELLOW)
        if not setup_credentials_interactive():
            return False, "Setup cancelled."
        creds = get_credentials()

    endpoint = "https://www.instapaper.com/api/add"
    data = {
        "username": creds['username'],
        "password": creds['password'],
        "url": url,
    }
    if title:
        data["title"] = title
    if tags:
        data["tags"] = tags

    try:
        resp = requests.post(endpoint, data=data, timeout=10)
    except Exception as e:
        return False, f"Connection error: {e}"

    if resp.status_code == 201:
        return True, "✅ Saved to Instapaper successfully."
    else:
        # If credentials are invalid, offer to re-enter them
        if resp.status_code == 401:
            print_colored("[!] Authentication failed. Please re-enter your credentials.", COLORS.RED)
            if setup_credentials_interactive():
                # Retry once
                return add_to_instapaper(url, title, tags)
        return False, f"❌ Instapaper error {resp.status_code}: {resp.text}"
