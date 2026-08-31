#!/usr/bin/env python3
"""
Convert old JSON question format (with options, pairs, hints) to the new format
compatible with the current question bank import.

Handles: multichoice, matching, essay, truefalse.

Usage:
    python convert_old_to_new.py old.json --output new.json
        [--date YYYY-MM-DD] [--institution STR] [--level STR] [--paper STR]
        [--extract-subject] [--source STR]
        [--auto-detect]   # enable automatic Nepali/English detection (default)
        [--no-auto-detect] # disable automatic detection (use manual split only)
"""

import json
import os
import sys
import re
import argparse
from datetime import datetime

# ---------- Helper functions ----------

def has_devanagari(text):
    """Check if text contains Devanagari Unicode characters."""
    return bool(re.search(r'[\u0900-\u097F]', text))

def split_nepali_english(text, auto_detect=True):
    """
    Split text into Nepali and English parts.
    Strategies (in order):
      1. <br> separator (Nepali <br> English)
      2. Parentheses at the end: Nepali (English)
      3. If auto_detect is True and Devanagari is present:
         - If only Devanagari -> Nepali, English empty
         - If only non-Devanagari -> English, Nepali empty
         - If both: try to separate by patterns, fallback to whole as Nepali.
    """
    if not text:
        return "", ""

    # Strategy 1: <br> separator
    if "<br>" in text:
        parts = text.split("<br>", 1)
        nepali = parts[0].strip()
        english = parts[1].strip() if len(parts) > 1 else ""
        return nepali, english

    # Strategy 2: Parentheses at the end: Nepali (English)
    match = re.search(r'^(.*?)\s*\(([^)]+)\)$', text)
    if match:
        nepali = match.group(1).strip()
        english = match.group(2).strip()
        return nepali, english

    # Strategy 3: Automatic detection (if enabled)
    if auto_detect:
        has_nep = has_devanagari(text)
        # If no Devanagari, treat as English
        if not has_nep:
            return "", text
        # If only Devanagari (no Latin letters), treat as Nepali
        if not re.search(r'[a-zA-Z]', text):
            return text, ""
        # Mixed: try to extract English part (often at the end after a space or punctuation)
        # Look for a pattern: Nepali text followed by space and English text,
        # or Nepali text followed by English in parentheses (already handled)
        # Simple heuristic: split on last occurrence of '।' or '। ' or '. '
        # Or split on last occurrence of space before a Latin word.
        # We'll do a more robust approach: find the longest suffix that is mostly Latin.
        words = text.split()
        if len(words) > 1:
            # Check from the end for Latin-only words
            eng_words = []
            nep_words = []
            for w in reversed(words):
                if re.search(r'[a-zA-Z]', w) and not has_devanagari(w):
                    eng_words.append(w)
                else:
                    break
            if eng_words:
                # The English part is the last N words
                eng_part = ' '.join(reversed(eng_words))
                nep_part = ' '.join(words[:-len(eng_words)])
                return nep_part.strip(), eng_part.strip()
        # Fallback: whole as Nepali
        return text, ""

    # If auto_detect is disabled and no separators found, treat whole as Nepali
    return text, ""

def extract_subject_from_group(group):
    """Extract subject from group string (text before first parenthesis)."""
    if not group:
        return ""
    if '(' in group:
        subject = group.split('(')[0].strip()
        return subject.rstrip(',')
    return group

def pad_question_number(qno):
    try:
        return f"{int(qno):02d}"
    except (ValueError, TypeError):
        return str(qno).strip().zfill(2)

def convert_options(options):
    """Convert options from {text, correct} to {text, fraction, feedback, display_order}."""
    new_opts = []
    if not options:
        return new_opts
    for idx, opt in enumerate(options):
        fraction = 100.0 if opt.get('correct', False) else 0.0
        new_opts.append({
            'text': opt.get('text', ''),
            'fraction': fraction,
            'feedback': opt.get('feedback', ''),
            'display_order': idx
        })
    return new_opts

def convert_pairs(pairs):
    """Convert pairs from {subquestion, answer} to new format with display_order."""
    new_pairs = []
    if not pairs:
        return new_pairs
    for idx, pair in enumerate(pairs):
        new_pairs.append({
            'subquestion': pair.get('subquestion', ''),
            'answer': pair.get('answer', ''),
            'display_order': idx
        })
    return new_pairs

def convert_hints(hints):
    """Convert hints to new format (if any)."""
    new_hints = []
    if not hints:
        return new_hints
    for idx, hint in enumerate(hints):
        new_hints.append({
            'text': hint.get('text', ''),
            'clear_incorrect': hint.get('clear_incorrect', False),
            'show_num_correct': hint.get('show_num_correct', False),
            'hint_number': idx + 1
        })
    return new_hints

def convert_old_json(input_file, output_file, defaults, extract_subject=False, source=None, auto_detect=True):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("Error: JSON must be a list of questions.")
        sys.exit(1)

    new_data = []
    for item in data:
        qno = item.get('question_no')
        question_number = pad_question_number(qno)

        # Split text using automatic detection if enabled
        text = item.get('text', '')
        nepali, english = split_nepali_english(text, auto_detect)

        # Determine type
        qtype = item.get('type', 'essay').lower()

        # Convert type-specific fields
        options = []
        pairs = []
        hints = []

        if qtype in ('multichoice', 'truefalse'):
            options = convert_options(item.get('options', []))
        elif qtype == 'matching':
            pairs = convert_pairs(item.get('pairs', []))
        # essay: no options/pairs

        # Hints are optional for any type
        hints = convert_hints(item.get('hints', []))

        # Build new question dict
        new_q = {
            'question_number': question_number,
            'type': qtype,
            'nepali_transcription': nepali,
            'english_transcription': english,
            'options': options,
            'pairs': pairs,
            'hints': hints,
            'general_feedback': item.get('general_feedback', ''),
            'grader_info': item.get('grader_info', ''),
            'marks': item.get('grade', 1),          # grade becomes marks
            'grade': 1,                             # default (Moodle grade, not used)
            'lines': item.get('lines', 15),
            'penalty': item.get('penalty', 0),
            'group': item.get('group', ''),
            'fraction_correct': item.get('fraction_correct', 100),
            'fraction_wrong': item.get('fraction_wrong', -20),
            'shuffle_answers': True,
            'show_num_correct': False,
            'correct_feedback': '',
            'partially_correct_feedback': '',
            'incorrect_feedback': '',
            'response_lines': item.get('lines', 15),
            'attachments': 0,
            'filetypes': '.doc,.docx,.pdf,.png,.jpg,.jpeg',
            'maxbytes': 2097152,
            'notes': '',
            'chapter': '',
            'syllabus_code': '',
            'source': source or os.path.basename(input_file),
            # Defaults from user
            'question_date': defaults.get('date', ''),
            'institution': defaults.get('institution', ''),
            'level': defaults.get('level', ''),
            'paper': defaults.get('paper', ''),
            'subject': ''
        }

        # Extract subject if requested
        if extract_subject:
            new_q['subject'] = extract_subject_from_group(new_q['group'])
        else:
            new_q['subject'] = ''

        new_data.append(new_q)

    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Converted {len(new_data)} questions to {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Convert old MCQ/matching/essay JSON to new format.")
    parser.add_argument('input', help='Input JSON file (old format)')
    parser.add_argument('-o', '--output', help='Output JSON file (new format)')
    parser.add_argument('--date', help='Default Date (YYYY-MM-DD)')
    parser.add_argument('--institution', help='Default Institution')
    parser.add_argument('--level', help='Default Level')
    parser.add_argument('--paper', help='Default Paper')
    parser.add_argument('--extract-subject', action='store_true',
                        help='Extract subject from group field')
    parser.add_argument('--source', help='Source name (default: filename)')
    parser.add_argument('--auto-detect', action='store_true', default=True,
                        help='Enable automatic Nepali/English detection (default)')
    parser.add_argument('--no-auto-detect', action='store_false', dest='auto_detect',
                        help='Disable automatic detection (use manual split only)')
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
    defaults['date'] = args.date or input("Enter default Date (YYYY-MM-DD): ").strip()
    defaults['institution'] = args.institution or input("Enter default Institution: ").strip()
    defaults['level'] = args.level or input("Enter default Level: ").strip()
    defaults['paper'] = args.paper or input("Enter default Paper: ").strip()

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
    print(f"  Auto‑detect : {'ON' if args.auto_detect else 'OFF'}")
    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        sys.exit(0)

    convert_old_json(args.input, output_file, defaults, args.extract_subject, args.source, args.auto_detect)

if __name__ == "__main__":
    main()
