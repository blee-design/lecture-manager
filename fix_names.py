from lecture_manager.db import get_connection, TABLE_NAME
from lecture_manager.utils import build_original_filename, print_colored, COLORS

def regenerate_all_filenames():
    print_colored("[i] Connecting to database...", COLORS.BLUE)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all records
    cursor.execute(f"SELECT * FROM {TABLE_NAME}")
    records = cursor.fetchall()

    print_colored(f"[i] Checking {len(records)} records...", COLORS.BLUE)

    updated = 0
    for row in records:
        # Build what the new filename SHOULD be based on current data
        new_name = build_original_filename(row)
        old_name = row.get('original_filename')

        # Only update if they differ (and new_name isn't empty)
        if new_name and new_name != old_name:
            cursor.execute(f"UPDATE {TABLE_NAME} SET original_filename = %s WHERE id = %s", (new_name, row['id']))
            updated += 1

    conn.commit()
    cursor.close()
    conn.close()

    if updated > 0:
        print_colored(f"[✓] Successfully regenerated original_filename for {updated} records.", COLORS.GREEN)
    else:
        print_colored("[i] All original filenames are already up-to-date.", COLORS.YELLOW)

if __name__ == "__main__":
    regenerate_all_filenames()
