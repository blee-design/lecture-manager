import os
from .db import get_connection
from .utils import print_colored, COLORS, color_text

SIM_BRANDS = ['NTC', 'NCELL', 'SMART', 'SKY']

def sim_menu():
    while True:
        print("\n" + "═" * 50)
        print_colored("  📱 SIM DETAILS MANAGER", COLORS.CYAN, bold=True)
        print("═" * 50)
        print("  1. Add a new SIM")
        print("  2. View all SIMs")
        print("  3. Search SIMs")
        print("  4. Update a SIM")
        print("  5. Delete a SIM")
        print("  0. Return to main menu")
        print("═" * 50)
        choice = input(color_text("Choose (0-5): ", COLORS.MAGENTA)).strip()

        if choice == '0': break
        elif choice == '1': add_sim()
        elif choice == '2': view_sims()
        elif choice == '3': search_sims()
        elif choice == '4': update_sim()
        elif choice == '5': delete_sim()
        else: print_colored("[!] Invalid choice.", COLORS.RED)
        input("\nPress Enter to continue...")

def add_sim():
    print("\n" + "─" * 40)
    print_colored("  ADD NEW SIM", COLORS.GREEN, bold=True)
    print("─" * 40)

    cell = input(color_text("Cell Number: ", COLORS.MAGENTA)).strip()
    if not cell: return

    sec_code = input(color_text("Security Code (8 digits): ", COLORS.MAGENTA)).strip() or "00000000"
    pin1 = input(color_text("PIN 1: ", COLORS.MAGENTA)).strip() or None
    pin2 = input(color_text("PIN 2 (optional): ", COLORS.MAGENTA)).strip() or None
    puk1 = input(color_text("PUK 1 (8 digits): ", COLORS.MAGENTA)).strip() or "00000000"
    puk2 = input(color_text("PUK 2 (8 digits, optional): ", COLORS.MAGENTA)).strip() or "00000000"

    print(f"\nBrands: {', '.join(SIM_BRANDS)}")
    while True:
        brand = input(color_text("Brand: ", COLORS.MAGENTA)).strip().upper()
        if brand in SIM_BRANDS:
            break
        print_colored(f"[!] Invalid brand. Choose from: {', '.join(SIM_BRANDS)}", COLORS.RED)

    owner = input(color_text("Owner Name: ", COLORS.MAGENTA)).strip() or "UNKNOWN"
    user = input(color_text("User Name: ", COLORS.MAGENTA)).strip() or "UNKNOWN"

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO sim_details
            (cell_number, security_code, pin_1, pin_2, puk_1, puk_2, brand, owner, `user`)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (cell, sec_code, pin1, pin2, puk1, puk2, brand, owner, user))
        conn.commit()
        print_colored(f"[✓] SIM {cell} added successfully.", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Error adding SIM: {e}", COLORS.RED)
    finally:
        cursor.close()
        conn.close()

def view_sims():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM sim_details ORDER BY brand, owner")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print_colored("[i] No SIMs found.", COLORS.YELLOW)
        return

    print("\n" + "─" * 90)
    print(f"  {'ID':<4} | {'Cell Number':<12} | {'Brand':<6} | {'Owner':<15} | {'User':<15} | {'PINs':<10}")
    print("─" * 90)
    for r in rows:
        pins = f"P1:{r['pin_1'] or '---'} / P2:{r['pin_2'] or '---'}"
        cell = str(r['cell_number'] or '—')
        brand = str(r['brand'] or '—')
        owner = (r['owner'] or '')[:15]
        user = (r['user'] or '')[:15]
        print(f"  {r['id']:<4} | {cell:<12} | {brand:<6} | {owner:<15} | {user:<15} | {pins}")
    print("─" * 90)

def search_sims():
    query = input(color_text("Search by Cell, Owner, or Brand: ", COLORS.MAGENTA)).strip()
    if not query: return

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    like = f"%{query}%"
    cursor.execute("""
        SELECT * FROM sim_details
        WHERE cell_number LIKE %s OR owner LIKE %s OR `user` LIKE %s OR brand LIKE %s
    """, (like, like, like, like))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print_colored("[i] No matches found.", COLORS.YELLOW)
        return

    print(f"\n  " + color_text(f"Found {len(rows)} match(es):", COLORS.GREEN, bold=True))

    for r in rows:
        cell = str(r.get('cell_number') or '—')
        brand = str(r.get('brand') or '—')
        owner = str(r.get('owner') or '—')[:18]
        user = str(r.get('user') or '—')[:18]
        sec = str(r.get('security_code') or '00000000').zfill(8)
        pin1 = str(r.get('pin_1') or '—')
        pin2 = str(r.get('pin_2') or '—')
        puk1 = str(r.get('puk_1') or '00000000').zfill(8)
        puk2 = str(r.get('puk_2') or '00000000').zfill(8)

        added = r['date'].strftime('%Y-%m-%d') if r.get('date') else '—'
        updated = r['updated_on'].strftime('%Y-%m-%d') if r.get('updated_on') else '—'

        print(color_text(f"  ┌─── 📱 SIM ID: {r['id']} ─────────────────────────────────────┐", COLORS.CYAN))
        print(color_text("  │ ", COLORS.CYAN) + f"📞 {color_text('Number:', COLORS.YELLOW)} {cell:<15} " + color_text("│", COLORS.CYAN) + f" 📶 {color_text('Brand:', COLORS.YELLOW)} {brand}")
        print(color_text("  │ ", COLORS.CYAN) + f"👤 {color_text('Owner :', COLORS.YELLOW)} {owner:<15} " + color_text("│", COLORS.CYAN) + f" 👥 {color_text('User :', COLORS.YELLOW)} {user}")
        print(color_text("  │ ", COLORS.CYAN) + f"📅 {color_text('Added :', COLORS.YELLOW)} {added:<15} " + color_text("│", COLORS.CYAN) + f" 🔄 {color_text('Updt :', COLORS.YELLOW)} {updated}")
        print(color_text("  ├─── 🔐 SECURITY ───────────────────────────────────────────┤", COLORS.CYAN))
        print(color_text("  │ ", COLORS.CYAN) + f"🔑 {color_text('PIN 1 :', COLORS.YELLOW)} {pin1:<10} " + color_text("│", COLORS.CYAN) + f" 🔑 {color_text('PIN 2 :', COLORS.YELLOW)} {pin2}")
        print(color_text("  │ ", COLORS.CYAN) + f"🔓 {color_text('PUK 1 :', COLORS.YELLOW)} {puk1:<10} " + color_text("│", COLORS.CYAN) + f" 🔓 {color_text('PUK 2 :', COLORS.YELLOW)} {puk2}")
        print(color_text("  │ ", COLORS.CYAN) + f"🛡️  {color_text('SEC   :', COLORS.YELLOW)} {sec}")
        print(color_text("  └──────────────────────────────────────────────────────────┘", COLORS.CYAN))
        print()

def update_sim():
    identifier = input(color_text("Enter DB ID or Cell Number to update: ", COLORS.MAGENTA)).strip()
    if not identifier: return

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if identifier.isdigit():
        cursor.execute("SELECT * FROM sim_details WHERE id = %s", (identifier,))
    else:
        cursor.execute("SELECT * FROM sim_details WHERE cell_number = %s", (identifier,))

    row = cursor.fetchone()
    if not row:
        print_colored("[!] SIM not found.", COLORS.RED)
        cursor.close(); conn.close(); return

    sim_id = row['id']

    print(f"\nUpdating SIM: {row['cell_number']} (Leave blank to keep current)")

    new_cell = input(f"Cell Number [{row['cell_number']}]: ").strip() or row['cell_number']
    new_owner = input(f"Owner [{row['owner']}]: ").strip() or row['owner']
    new_user = input(f"User [{row['user']}]: ").strip() or row['user']
    new_brand = input(f"Brand [{row['brand']}]: ").strip().upper() or row['brand']

    try:
        cursor.execute("""
            UPDATE sim_details
            SET cell_number = %s, owner = %s, `user` = %s, brand = %s
            WHERE id = %s
        """, (new_cell, new_owner, new_user, new_brand, sim_id))
        conn.commit()
        print_colored("[✓] SIM updated.", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Error: {e}", COLORS.RED)
    finally:
        cursor.close(); conn.close()

def delete_sim():
    identifier = input(color_text("Enter DB ID or Cell Number to delete: ", COLORS.MAGENTA)).strip()
    if not identifier: return

    confirm = input(color_text(f"Are you sure you want to delete '{identifier}'? (y/n): ", COLORS.RED)).strip().lower()
    if confirm != 'y': return

    conn = get_connection()
    cursor = conn.cursor()

    if identifier.isdigit():
        cursor.execute("DELETE FROM sim_details WHERE id = %s", (identifier,))
    else:
        cursor.execute("DELETE FROM sim_details WHERE cell_number = %s", (identifier,))
    conn.commit()
    if cursor.rowcount > 0:
        print_colored("[✓] SIM deleted.", COLORS.GREEN)
    else:
        print_colored("[!] SIM not found.", COLORS.RED)
    cursor.close()
    conn.close()
