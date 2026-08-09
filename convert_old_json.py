#!/usr/bin/env python3
"""
Convert old JSON question format (from earlier Lecture Manager versions)
to the new format compatible with the current Question Bank import.

Usage:
    python convert_old_json.py input.json --output output.json
        [--date YYYY-MM-DD] [--institution STR] [--level STR] [--paper STR]
        [--extract-subject]

If options are omitted, the script will prompt interactively.
"""

import json
import os
import sys
import re
import argparse
from datetime import datetime

def split_nepali_english(text):
    """
    Split text into Nepali and English parts.
    Assumes the format: "Nepali<br>English" or "Nepali (English)".
    """
    nepali = text
    english = ""

    # Try <br> separator
    if "<br>" in text:
        parts = text.split("<br>", 1)
        nepali = parts[0].strip()
        english = parts[1].strip() if len(parts) > 1 else ""
        return nepali, english

    # Try parentheses with English
    # Pattern: Nepali text (English text) or Nepali text (English)
    # We'll look for a final parenthesis at the end.
    match = re.search(r'^(.*?)\s*\(([^)]+)\)$', text)
    if match:
        nepali = match.group(1).strip()
        english = match.group(2).strip()
        return nepali, english

    # If no separator, treat whole as Nepali
    return nepali, english

def extract_subject_from_group(group):
    """
    Extract a subject from the group string.
    Example: "भूगोल, वातावरण र सामान्य ज्ञान (Geography...)"
    -> returns "भूगोल, वातावरण र सामान्य ज्ञान"
    """
    if not group:
        return ""
    # Take everything before the first '('
    if '(' in group:
        subject = group.split('(')[0].strip()
        # Remove trailing comma or separator
        subject = subject.rstrip(',')
        return subject
    return group

def pad_question_number(qno):
    """Convert question number to zero-padded two-digit string."""
    if qno is None:
        return "01"
    try:
        return f"{int(qno):02d}"
    except (ValueError, TypeError):
        return str(qno).strip().zfill(2)

def convert_old_json(input_file, output_file, defaults, extract_subject=False):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("Error: JSON must be a list of questions.")
        sys.exit(1)

    new_data = []
    for item in data:
        # Create new question dict
        new_q = {}

        # Copy fields that are already in the right format
        for field in ['type', 'options', 'general_feedback', 'grader_info',
                      'grade', 'lines', 'penalty', 'fraction_correct', 'fraction_wrong']:
            if field in item:
                new_q[field] = item[field]

        # Process question number
        qno = item.get('question_no')
        new_q['question_number'] = pad_question_number(qno)

        # Split text
        text = item.get('text', '')
        nepali, english = split_nepali_english(text)
        new_q['nepali_transcription'] = nepali
        new_q['english_transcription'] = english

        # Add global defaults
        new_q['question_date'] = defaults.get('date', '')
        new_q['institution'] = defaults.get('institution', '')
        new_q['level'] = defaults.get('level', '')
        new_q['paper'] = defaults.get('paper', '')

        # Handle group and subject
        group = item.get('group', '')
        new_q['group'] = group

        if extract_subject:
            subject = extract_subject_from_group(group)
            new_q['subject'] = subject
        else:
            # If no extraction, leave subject empty (user can set later)
            new_q['subject'] = ''

        # Chapter is not in old format – leave empty
        new_q['chapter'] = ''

        # Notes (if any) – old format didn't have notes, but we can optionally take general_feedback?
        # We'll keep notes empty.
        new_q['notes'] = ''

        # Source (optional) – we can set to filename or 'legacy'
        new_q['source'] = os.path.basename(input_file)

        new_data.append(new_q)

    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Converted {len(new_data)} questions to {output_file}")

def main():
    parser = argparse.ArgumentParser(
        description="Convert old Lecture Manager JSON to new format.",
        epilog="If options are omitted, you will be prompted interactively."
    )
    parser.add_argument('input', help='Input JSON file (old format)')
    parser.add_argument('-o', '--output', help='Output JSON file (new format)')
    parser.add_argument('--date', help='Default Date (YYYY-MM-DD)')
    parser.add_argument('--institution', help='Default Institution')
    parser.add_argument('--level', help='Default Level')
    parser.add_argument('--paper', help='Default Paper')
    parser.add_argument('--extract-subject', action='store_true',
                        help='Extract subject from group field (text before first parenthesis)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found.")
        sys.exit(1)

    # Determine output filename
    if args.output:
        output_file = args.output
    else:
        base, _ = os.path.splitext(args.input)
        output_file = f"{base}_converted.json"

    # Gather defaults interactively if not provided
    defaults = {}
    if args.date:
        defaults['date'] = args.date
    else:
        defaults['date'] = input("Enter default Date (YYYY-MM-DD): ").strip()
    if args.institution:
        defaults['institution'] = args.institution
    else:
        defaults['institution'] = input("Enter default Institution: ").strip()
    if args.level:
        defaults['level'] = args.level
    else:
        defaults['level'] = input("Enter default Level: ").strip()
    if args.paper:
        defaults['paper'] = args.paper
    else:
        defaults['paper'] = input("Enter default Paper: ").strip()

    # Confirm
    print("\nDefaults to apply to ALL questions:")
    print(f"  Date        : {defaults['date']}")
    print(f"  Institution : {defaults['institution']}")
    print(f"  Level       : {defaults['level']}")
    print(f"  Paper       : {defaults['paper']}")
    if args.extract_subject:
        print("  Subject will be extracted from 'group' field.")
    else:
        print("  Subject will be left empty (you can update later).")
    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        sys.exit(0)

    convert_old_json(args.input, output_file, defaults, args.extract_subject)

if __name__ == "__main__":
    main()
