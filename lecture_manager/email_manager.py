from .db import get_connection
from .utils import print_colored, COLORS, color_text

def email_menu():
    while True:
        print("\n" + "═" * 50)
        print_colored("  ✉️  EMAIL MANAGER", COLORS.CYAN, bold=True)
        print("═" * 50)
        print("  1. Add a new Email")
        print("  2. View all Emails")
        print("  3. Search Emails")
        print("  4. Update an Email")
        print("  5. Delete an Email")
        print("  0. Return to main menu")
        print("═" * 50)
        choice = input(color_text("Choose (0-5): ", COLORS.MAGENTA)).strip()

        if choice == '0': break
        elif choice == '1': add_email()
        elif choice == '2': view_emails()
        elif choice == '3': search_emails()
        elif choice == '4': update_email()
        elif choice == '5': delete_email()
        else: print_colored("[!] Invalid choice.", COLORS.RED)
        input("\nPress Enter to continue...")

def add_email():
    print("\n" + "─" * 40)
    print_colored("  ADD NEW EMAIL", COLORS.GREEN, bold=True)
    print("─" * 40)

    mail_id = input(color_text("Email ID: ", COLORS.MAGENTA)).strip()
    if not mail_id: return

    supercell = input(color_text("Supercell (Default: Not available): ", COLORS.MAGENTA)).strip() or "Not available"
    owner = input(color_text("Owner: ", COLORS.MAGENTA)).strip() or None
    passwd = input(color_text("Password: ", COLORS.MAGENTA)).strip() or None
    remark = input(color_text("Remark (Default: Not available): ", COLORS.MAGENTA)).strip() or "Not available"

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO email (mail_id, supercell, owner, passwd, remark)
            VALUES (%s, %s, %s, %s, %s)
        """, (mail_id, supercell, owner, passwd, remark))
        conn.commit()
        print_colored(f"[✓] Email {mail_id} added successfully.", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Error adding email: {e}", COLORS.RED)
    finally:
        cursor.close()
        conn.close()

def view_emails():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM email ORDER BY id")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print_colored("[i] No emails found.", COLORS.YELLOW)
        return

    print("\n" + "═" * 60)
    print_colored(f"  📧 ALL EMAILS ({len(rows)} found)", COLORS.CYAN, bold=True)
    print("═" * 60)

    for r in rows:
        mail_id = str(r.get('mail_id') or '—')
        owner = str(r.get('owner') or '—')
        supercell = str(r.get('supercell') or '—')
        passwd = str(r.get('passwd') or '—')
        remark = str(r.get('remark') or '—')
        date = r['date'].strftime('%Y-%m-%d') if r.get('date') else '—'

        print(color_text(f"  ┌─── ✉️ EMAIL ID: {r['id']} ───────────────────────────────┐", COLORS.CYAN))
        print(color_text("  │ ", COLORS.CYAN) + f"📧 {color_text('Mail ID:', COLORS.YELLOW)} {mail_id}")
        print(color_text("  │ ", COLORS.CYAN) + f"👤 {color_text('Owner  :', COLORS.YELLOW)} {owner:<20} " + color_text("│", COLORS.CYAN) + f" 📅 {color_text('Date:', COLORS.YELLOW)} {date}")
        print(color_text("  ├─── 🔐 DETAILS ─────────────────────────────────────────┤", COLORS.CYAN))
        print(color_text("  │ ", COLORS.CYAN) + f"🔑 {color_text('Passwd :', COLORS.YELLOW)} {passwd}")
        print(color_text("  │ ", COLORS.CYAN) + f"🏢 {color_text('Supercell:', COLORS.YELLOW)} {supercell}")
        print(color_text("  │ ", COLORS.CYAN) + f"📝 {color_text('Remark :', COLORS.YELLOW)} {remark}")
        print(color_text("  └──────────────────────────────────────────────────────┘", COLORS.CYAN))
        print()

def search_emails():
    query = input(color_text("Search by Mail ID, Owner, or Remark: ", COLORS.MAGENTA)).strip()
    if not query: return

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    like = f"%{query}%"
    cursor.execute("""
        SELECT * FROM email
        WHERE mail_id LIKE %s OR owner LIKE %s OR remark LIKE %s
    """, (like, like, like))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print_colored("[i] No matches found.", COLORS.YELLOW)
        return

    print(f"\n  " + color_text(f"Found {len(rows)} match(es):", COLORS.GREEN, bold=True))

    for r in rows:
        mail_id = str(r.get('mail_id') or '—')
        owner = str(r.get('owner') or '—')
        supercell = str(r.get('supercell') or '—')
        passwd = str(r.get('passwd') or '—')
        remark = str(r.get('remark') or '—')
        date = r['date'].strftime('%Y-%m-%d') if r.get('date') else '—'

        print(color_text(f"  ┌─── ✉️ EMAIL ID: {r['id']} ───────────────────────────────┐", COLORS.CYAN))
        print(color_text("  │ ", COLORS.CYAN) + f"📧 {color_text('Mail ID:', COLORS.YELLOW)} {mail_id}")
        print(color_text("  │ ", COLORS.CYAN) + f"👤 {color_text('Owner  :', COLORS.YELLOW)} {owner:<20} " + color_text("│", COLORS.CYAN) + f" 📅 {color_text('Date:', COLORS.YELLOW)} {date}")
        print(color_text("  ├─── 🔐 DETAILS ─────────────────────────────────────────┤", COLORS.CYAN))
        print(color_text("  │ ", COLORS.CYAN) + f"🔑 {color_text('Passwd :', COLORS.YELLOW)} {passwd}")
        print(color_text("  │ ", COLORS.CYAN) + f"🏢 {color_text('Supercell:', COLORS.YELLOW)} {supercell}")
        print(color_text("  │ ", COLORS.CYAN) + f"📝 {color_text('Remark :', COLORS.YELLOW)} {remark}")
        print(color_text("  └──────────────────────────────────────────────────────┘", COLORS.CYAN))
        print()

def update_email():
    identifier = input(color_text("Enter DB ID or Mail ID to update: ", COLORS.MAGENTA)).strip()
    if not identifier: return

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if identifier.isdigit():
        cursor.execute("SELECT * FROM email WHERE id = %s", (identifier,))
    else:
        cursor.execute("SELECT * FROM email WHERE mail_id = %s", (identifier,))

    row = cursor.fetchone()
    if not row:
        print_colored("[!] Email not found.", COLORS.RED)
        cursor.close(); conn.close(); return

    email_id = row['id']

    while True:
        # Re-fetch to show the freshest data after each update
        cursor.execute("SELECT * FROM email WHERE id = %s", (email_id,))
        row = cursor.fetchone()

        print("\n" + "═" * 50)
        print_colored(f"  UPDATE EMAIL (ID: {row['id']})", COLORS.CYAN, bold=True)
        print("═" * 50)
        print(f"  1. Mail ID   : {row['mail_id']}")
        print(f"  2. Owner     : {row['owner']}")
        print(f"  3. Password  : {row['passwd']}")
        print(f"  4. Supercell : {row['supercell']}")
        print(f"  5. Remark    : {row['remark']}")
        print("  0. Finish / Exit")
        print("═" * 50)

        choice = input(color_text("Choose field to update (0-5): ", COLORS.MAGENTA)).strip()

        if choice == '0':
            break

        field_map = {
            '1': 'mail_id', '2': 'owner', '3': 'passwd', '4': 'supercell', '5': 'remark'
        }

        if choice not in field_map:
            print_colored("[!] Invalid choice.", COLORS.RED)
            continue

        field = field_map[choice]
        current_val = row.get(field)

        # Display current value
        display_val = current_val if current_val is not None else "(empty)"
        new_val = input(color_text(f"New {field.title()} [{display_val}]: ", COLORS.MAGENTA)).strip()

        if new_val == '':
            print_colored("[i] No change made.", COLORS.YELLOW)
            continue

        if str(current_val) == str(new_val):
            print_colored("[i] Value is identical. No DB change made.", COLORS.BLUE)
            continue

        # Apply update
        try:
            cursor.execute(f"UPDATE email SET {field} = %s WHERE id = %s", (new_val, email_id))
            conn.commit()
            if cursor.rowcount > 0:
                print_colored(f"[✓] {field.title()} updated.", COLORS.GREEN)
            else:
                print_colored("[!] Database did not register a change.", COLORS.YELLOW)
        except Exception as e:
            print_colored(f"[!] Error updating {field}: {e}", COLORS.RED)

    cursor.close()
    conn.close()

def delete_email():
    identifier = input(color_text("Enter DB ID or Mail ID to delete: ", COLORS.MAGENTA)).strip()
    if not identifier: return

    confirm = input(color_text(f"Are you sure you want to delete '{identifier}'? (y/n): ", COLORS.RED)).strip().lower()
    if confirm != 'y': return

    conn = get_connection()
    cursor = conn.cursor()

    if identifier.isdigit():
        cursor.execute("DELETE FROM email WHERE id = %s", (identifier,))
    else:
        cursor.execute("DELETE FROM email WHERE mail_id = %s", (identifier,))
    conn.commit()
    if cursor.rowcount > 0:
        print_colored("[✓] Email deleted.", COLORS.GREEN)
    else:
        print_colored("[!] Email not found.", COLORS.RED)
    cursor.close()
    conn.close()
