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

    print("\n" + "─" * 80)
    print(f"  {'ID':<4} | {'Mail ID':<30} | {'Owner':<15} | {'Supercell':<15}")
    print("─" * 80)
    for r in rows:
        print(f"  {r['id']:<4} | {r['mail_id']:<30} | {(r['owner'] or '')[:15]:<15} | {(r['supercell'] or '')[:15]:<15}")
    print("─" * 80)

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

    print(f"\n--- SEARCH RESULTS ({len(rows)} found) ---")
    for r in rows:
        print(f"  ID: {r['id']} | {r['mail_id']} | Owner: {r['owner']} | Pass: {r['passwd']}")
        print(f"  Remark: {r['remark']} | Supercell: {r['supercell']}")

def update_email():
    email_id = input(color_text("Enter Email ID to update (Database ID): ", COLORS.MAGENTA)).strip()
    if not email_id.isdigit(): return

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM email WHERE id = %s", (email_id,))
    row = cursor.fetchone()
    if not row:
        print_colored("[!] Email not found.", COLORS.RED)
        cursor.close(); conn.close(); return

    print(f"\nUpdating Email: {row['mail_id']} (Leave blank to keep current)")

    new_mail = input(f"Mail ID [{row['mail_id']}]: ").strip() or row['mail_id']
    new_owner = input(f"Owner [{row['owner']}]: ").strip() or row['owner']
    new_passwd = input(f"Password [{row['passwd']}]: ").strip() or row['passwd']
    new_remark = input(f"Remark [{row['remark']}]: ").strip() or row['remark']

    try:
        cursor.execute("""
            UPDATE email
            SET mail_id = %s, owner = %s, passwd = %s, remark = %s
            WHERE id = %s
        """, (new_mail, new_owner, new_passwd, new_remark, email_id))
        conn.commit()
        print_colored("[✓] Email updated.", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Error: {e}", COLORS.RED)
    finally:
        cursor.close(); conn.close()

def delete_email():
    email_id = input(color_text("Enter Email ID to delete (Database ID): ", COLORS.MAGENTA)).strip()
    if not email_id.isdigit(): return

    confirm = input(color_text(f"Are you sure you want to delete Email ID {email_id}? (y/n): ", COLORS.RED)).strip().lower()
    if confirm != 'y': return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email WHERE id = %s", (email_id,))
    conn.commit()
    if cursor.rowcount > 0:
        print_colored("[✓] Email deleted.", COLORS.GREEN)
    else:
        print_colored("[!] Email not found.", COLORS.RED)
    cursor.close()
    conn.close()
