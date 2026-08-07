#!/usr/bin/env python3
from lecture_manager.db import get_connection
from lecture_manager.utils import print_colored, COLORS, color_text

def clear_all_questions():
    conn = get_connection()
    cursor = conn.cursor()

    # Disable foreign key checks
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

    # Truncate supporting tables if they exist
    tables = ['question_options', 'question_matching_pairs', 'question_hints']
    for table in tables:
        cursor.execute(f"SHOW TABLES LIKE '{table}'")
        if cursor.fetchone():
            cursor.execute(f"TRUNCATE TABLE {table}")
            print_colored(f"[✓] Truncated {table}", COLORS.GREEN)

    # Truncate main questions table
    cursor.execute("TRUNCATE TABLE questions")
    print_colored("[✓] Truncated questions (auto-increment reset to 1)", COLORS.GREEN)

    # Re-enable foreign key checks
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    cursor.close()
    conn.close()

    print_colored("[✓] All question data cleared successfully.", COLORS.GREEN)

if __name__ == "__main__":
    confirm = input(color_text("This will DELETE ALL question data! Are you sure? (yes/no): ", COLORS.RED))
    if confirm.lower() == 'yes':
        clear_all_questions()
    else:
        print_colored("[i] Aborted.", COLORS.YELLOW)
