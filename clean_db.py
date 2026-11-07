import sys
from lecture_manager.db import get_connection, TABLE_NAME
from lecture_manager.utils import normalize_time_str, normalize_title_case, build_original_filename
from lecture_manager.utils import print_colored, COLORS, color_text

def clean_database():
    print("\n" + "═" * 60)
    print_colored("  🧹 DATABASE NORMALIZATION TOOL", COLORS.CYAN, bold=True)
    print("═" * 60)
    print("This will clean up times (e.g., 5:00 AM -> 05:00 AM)")
    print("and convert ALL CAPS titles to proper Title Case.")
    print("It will also regenerate original_filenames to match.")
    print("═" * 60)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all records
    cursor.execute(f"SELECT * FROM {TABLE_NAME}")
    records = cursor.fetchall()

    if not records:
        print_colored("[i] No records found in the database.", COLORS.YELLOW)
        return

    changes_made = 0

    for row in records:
        updated_fields = {}

        # 1. Normalize Time
        old_time = row.get('time')
        if old_time:
            new_time = normalize_time_str(old_time)
            if new_time != old_time:
                updated_fields['time'] = new_time

        # 2. Normalize Topic
        old_topic = row.get('topic')
        if old_topic:
            new_topic = normalize_title_case(old_topic)
            if new_topic != old_topic:
                updated_fields['topic'] = new_topic

        # 3. Normalize Chapter
        old_chapter = row.get('chapter')
        if old_chapter:
            new_chapter = normalize_title_case(old_chapter)
            if new_chapter != old_chapter:
                updated_fields['chapter'] = new_chapter

        # If we made any changes to this row, apply them
        if updated_fields:
            # Apply changes to a temporary copy of the row to rebuild the filename
            temp_row = dict(row)
            temp_row.update(updated_fields)

            # Rebuild original_filename
            new_filename = build_original_filename(temp_row)
            if new_filename and new_filename != row.get('original_filename'):
                updated_fields['original_filename'] = new_filename

            # Execute Update
            set_clause = ", ".join(f"{k} = %s" for k in updated_fields.keys())
            values = list(updated_fields.values())
            values.append(row['id'])

            try:
                cursor.execute(f"UPDATE {TABLE_NAME} SET {set_clause} WHERE id = %s", values)
                changes_made += 1

                # Print the changes
                print(f"\n  Updated DB ID: {row['id']} ({row['video_id']})")
                for k, v in updated_fields.items():
                    if k != 'original_filename':
                        print(f"    • {k.title():<10}: {row.get(k)}  →  {v}")
            except Exception as e:
                print_colored(f"[!] Failed to update ID {row['id']}: {e}", COLORS.RED)

    conn.commit()
    cursor.close()
    conn.close()

    print("\n" + "═" * 60)
    if changes_made > 0:
        print_colored(f"  ✓ Successfully cleaned and updated {changes_made} record(s).", COLORS.GREEN)
    else:
        print_colored("  ✓ Database is already clean. No changes needed.", COLORS.GREEN)
    print("═" * 60 + "\n")

if __name__ == "__main__":
    clean_database()
