#!/usr/bin/env python3
"""
Delete all questions with a given question_date and reset AUTO_INCREMENT.
"""

import sys
from lecture_manager.db import get_connection
from lecture_manager.utils import print_colored, COLORS, color_text

def delete_questions_by_date(date_str, reset_id=True):
    conn = get_connection()
    cursor = conn.cursor()

    # Count how many will be deleted
    cursor.execute("SELECT COUNT(*) FROM questions WHERE question_date = %s", (date_str,))
    count = cursor.fetchone()[0]
    if count == 0:
        print_colored(f"No questions found for date {date_str}.", COLORS.YELLOW)
        cursor.close()
        conn.close()
        return

    print_colored(f"Found {count} question(s) on {date_str}.", COLORS.BLUE)

    # Show a sample
    cursor.execute("SELECT id, subject, question_number FROM questions WHERE question_date = %s LIMIT 5", (date_str,))
    sample = cursor.fetchall()
    print("Sample rows:")
    for row in sample:
        print(f"  ID: {row[0]}, Subject: {row[1]}, QNo: {row[2]}")

    confirm = input(color_text(f"Delete ALL {count} questions on {date_str}? (y/N): ", COLORS.RED))
    if confirm.lower() != 'y':
        print_colored("Aborted.", COLORS.YELLOW)
        cursor.close()
        conn.close()
        return

    # Delete
    cursor.execute("DELETE FROM questions WHERE question_date = %s", (date_str,))
    deleted = cursor.rowcount
    conn.commit()
    print_colored(f"✅ Deleted {deleted} questions.", COLORS.GREEN)

    # Reset auto_increment if requested
    if reset_id:
        cursor.execute("SELECT MAX(id) FROM questions")
        max_id = cursor.fetchone()[0]
        if max_id is None:
            max_id = 0
        new_auto = max_id + 1
        cursor.execute(f"ALTER TABLE questions AUTO_INCREMENT = {new_auto}")
        conn.commit()
        print_colored(f"✅ AUTO_INCREMENT reset to {new_auto}.", COLORS.GREEN)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else input("Enter question date (YYYY-MM-DD): ")
    delete_questions_by_date(date, reset_id=True)
