# File config.py

import os
import json
from .utils import color_text, print_colored, COLORS

CONFIG_FILE = os.path.expanduser("~/.lecture_manager_config.json")
db_config = None

def load_or_create_config():
    global db_config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                db_config = json.load(f)
            print_colored("[✓] Loaded database configuration.", COLORS.GREEN)
            return
        except Exception as e:
            print_colored(f"[!] Error reading config: {e}. Will create new one.", COLORS.YELLOW)

    print("\n" + "═" * 50)
    print_colored("  DATABASE CONFIGURATION", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Please enter your MariaDB/MySQL connection details.")
    host = input(color_text("Host (default: localhost): ", COLORS.MAGENTA)).strip() or "localhost"
    database = input(color_text("Database name: ", COLORS.MAGENTA)).strip()
    user = input(color_text("Username: ", COLORS.MAGENTA)).strip()
    password = input(color_text("Password: ", COLORS.MAGENTA)).strip()
    port = input(color_text("Port (default: 3306): ", COLORS.MAGENTA)).strip() or "3306"

    if not database or not user:
        print_colored("[!] Database name and username are required.", COLORS.RED)
        exit(1)

    db_config = {
        'host': host,
        'database': database,
        'user': user,
        'password': password,
        'port': int(port)
    }

    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(db_config, f, indent=2)
        print_colored(f"[✓] Configuration saved to {CONFIG_FILE}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Failed to save config: {e}", COLORS.RED)

def edit_config():
    global db_config
    print("\n" + "═" * 50)
    print_colored("  EDIT DATABASE CONFIGURATION", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Current settings:")
    print(f"  Host     : {db_config.get('host', '')}")
    print(f"  Database : {db_config.get('database', '')}")
    print(f"  User     : {db_config.get('user', '')}")
    print(f"  Port     : {db_config.get('port', 3306)}")
    print("(Leave blank to keep current value)")

    host = input(color_text(f"Host [{db_config.get('host', 'localhost')}]: ", COLORS.MAGENTA)).strip() or db_config.get('host', 'localhost')
    database = input(color_text(f"Database [{db_config.get('database', '')}]: ", COLORS.MAGENTA)).strip() or db_config.get('database', '')
    user = input(color_text(f"Username [{db_config.get('user', '')}]: ", COLORS.MAGENTA)).strip() or db_config.get('user', '')
    password = input(color_text(f"Password [{db_config.get('password', '')}]: ", COLORS.MAGENTA)).strip() or db_config.get('password', '')
    port = input(color_text(f"Port [{db_config.get('port', 3306)}]: ", COLORS.MAGENTA)).strip() or db_config.get('port', 3306)

    if not database or not user:
        print_colored("[!] Database name and username are required. Aborting.", COLORS.RED)
        return

    new_config = {
        'host': host,
        'database': database,
        'user': user,
        'password': password,
        'port': int(port)
    }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(new_config, f, indent=2)
        db_config = new_config
        print_colored("[✓] Configuration updated and saved.", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Failed to save config: {e}", COLORS.RED)
