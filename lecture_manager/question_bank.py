"""
Question Bank Module – Student‑friendly Quick Lookup
- Type: "YYYY-MM-DD Institution Level [QNo]" to view a single question or whole paper.
- Also supports interactive forms for advanced search.
- Displays questions with marks, chapter (if any), and both transcriptions.
- Import from human‑readable .txt files (blocks separated by ---).
- Import/Export from JSON.
"""

import os
import csv
import json
import re
import shutil
from datetime import date, datetime
from collections import defaultdict
from decimal import Decimal
from types import SimpleNamespace
from .db import get_connection
from .utils import print_colored, color_text, COLORS, clean_field, html_to_terminal, sanitize_for_json
from .question_converter.exceptions import (
    ConverterError,
    ValidationError,
    ParseError,
    DuplicateQuestionError,
    IOError,
    MissingCorrectOptionError,
    MultipleCorrectOptionsError,
    InsufficientOptionsError,
    MatchingPairError,
    UnknownQuestionTypeError,
)

_last_filtered_questions = None

TABLE_NAME = 'questions'

# Exam-type vocabulary. Store the short key; show the friendly label.
EXAM_TYPES = [
    ('open',        'Open Competition'),
    ('internal',    'Internal Competition'),
    ('promotional', 'Promotional'),
    ('other',       'Other'),
]

EXAM_TYPE_LABELS = {k: v for k, v in EXAM_TYPES}

# ============================================================
# Display helpers (ANSI-aware) + syllabus linking
# ============================================================
_QB_WIDTH = 76
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _vlen(s):
    """Visible width of a string (strips ANSI)."""
    return len(_ANSI_RE.sub('', s))


def _rule():
    return "─" * _QB_WIDTH


def _title_rule(text):
    """Centered text with side rules."""
    padded = f"  {text}  "
    vis = _vlen(padded)
    side = max(0, (_QB_WIDTH - vis) // 2)
    left = "─" * side
    right = "─" * max(0, _QB_WIDTH - side - vis)
    return left + padded + right


def _section_header(text):
    return color_text(f"  {text}", COLORS.CYAN, bold=True)


# ---------- Syllabus resolver ----------
_SYLLABUS_CODE_RE = re.compile(r'\b(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?(?:-\d+)?)\b')


def resolve_question_syllabus(q):
    """
    Return a dict describing the question's syllabus context:
      {paper_key, paper_display, subject_code, subject_name,
       chapter_code, chapter_name, code_display, reason}

    'reason' is a short string explaining how we resolved it
    ('code match', 'chapter name match', 'raw code', 'none').
    """
    from .file_manager import _papers, describe_syllabus_id, _chapter_lookup, _subject_lookup

    out = {
        'paper_key': q.get('paper'),
        'paper_display': None,
        'subject_code': None,
        'subject_name': None,
        'chapter_code': None,
        'chapter_name': None,
        'code_display': None,
        'reason': 'none',
    }

    paper_key = out['paper_key']

    # Paper display
    if paper_key:
        papers = _papers()
        if paper_key in papers:
            out['paper_display'] = papers[paper_key]['display_name']
        else:
            out['paper_display'] = paper_key

    # Try to extract a numeric code from syllabus_code, then chapter
    candidate = None
    for source in (q.get('syllabus_code') or '', q.get('chapter') or ''):
        m = _SYLLABUS_CODE_RE.search(str(source))
        if m:
            candidate = m.group(1)
            break

    if not paper_key:
        chapter_text = q.get('chapter') or ''
        m = re.search(r'\(P(\d)-', chapter_text)
        if m:
            inferred = {'1': 'paper_i', '2': 'paper_ii', '3': 'paper_iii'}.get(m.group(1))
            if inferred and inferred in _papers():
                paper_key = inferred
                out['paper_key'] = inferred
                out['reason'] = 'inferred from chapter'
                # fall through to code resolution below
            else:
                out['code_display'] = candidate or (q.get('syllabus_code') or '').strip() or None
                return out
        else:
            out['code_display'] = candidate or (q.get('syllabus_code') or '').strip() or None
            return out

    if candidate:
        out['code_display'] = candidate
        desc = describe_syllabus_id(candidate, paper_key)
        out['subject_code'] = desc.get('subject_code')
        out['subject_name'] = desc.get('subject_name')
        out['chapter_code'] = desc.get('chapter_code')
        out['chapter_name'] = desc.get('chapter_name')
        if out['chapter_name'] or out['subject_name']:
            out['reason'] = 'code match'
            return out

    # Fallback: raw text
    out['code_display'] = (q.get('syllabus_code') or '').strip() or None

    # Fallback: match chapter name text
    chapter_text = (q.get('chapter') or '').strip().lower()
    if chapter_text and paper_key:
        lookup = _chapter_lookup()
        for (p, s, c), name in lookup.items():
            if p == paper_key and name.lower() in chapter_text:
                out['subject_code'] = s
                out['chapter_code'] = c
                out['chapter_name'] = name
                out['subject_name'] = _subject_lookup().get((paper_key, s))
                out['reason'] = 'chapter name match'
                return out

    if out['code_display']:
        out['reason'] = 'raw code'
    return out

# ---------- Database ----------
def create_question_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            source VARCHAR(255) NULL,
            question_date VARCHAR(20),
            institution VARCHAR(255),
            subject VARCHAR(255),
            paper VARCHAR(100),
            `group` VARCHAR(100),
            marks INT,
            chapter VARCHAR(255),
            question_number VARCHAR(50),
            nepali_transcription TEXT,
            english_transcription TEXT,
            level VARCHAR(100),
            notes TEXT NULL,
            general_feedback TEXT NULL,
            fraction_correct DECIMAL(10,2) DEFAULT 100.00,
            fraction_wrong DECIMAL(10,2) DEFAULT -20.00,
            shuffle_answers BOOLEAN DEFAULT TRUE,
            show_num_correct BOOLEAN DEFAULT FALSE,
            correct_feedback TEXT NULL,
            partially_correct_feedback TEXT NULL,
            incorrect_feedback TEXT NULL,
            response_lines INT DEFAULT 15,
            attachments INT DEFAULT 0,
            filetypes VARCHAR(255) DEFAULT '.doc,.docx,.pdf,.png,.jpg,.jpeg',
            maxbytes INT DEFAULT 2097152,
            grader_info TEXT NULL,
            penalty DECIMAL(10,2) DEFAULT 0.00,
            feedback_true TEXT NULL,
            feedback_false TEXT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_subject (subject),
            INDEX idx_institution (institution),
            INDEX idx_paper (paper),
            INDEX idx_level (level)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print_colored("[✓] Question table ready.", COLORS.GREEN)

def search_questions_by_chapter(chapter_pattern):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM questions WHERE chapter LIKE %s", (f"%{chapter_pattern}%",))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def _should_clear_english(nepali, english):
    """Return True if english is non‑empty and identical to nepali (ignoring case/trim)."""
    if not english or not nepali:
        return False
    return nepali.strip().lower() == english.strip().lower()

def normalize_question_number(qno):
    """
    Clean a question number for storage.

    - Trim whitespace
    - Strip an optional 'Q' / 'Q.' / 'Question ' prefix
    - Reject empty → None (so it becomes NULL, not '00')
    - Leave everything else as typed:  '1', '01', '1a', '1(a)', '1.5', '10a'

    Display-side: whatever comes out of this is what the user sees.
    Comparison/sort use the helpers below.
    """
    if qno is None:
        return None
    s = str(qno).strip()
    if not s:
        return None
    # Strip common prefixes
    s = re.sub(r'^(?:Q\.?\s*|Question\s+)', '', s, flags=re.IGNORECASE).strip()
    if not s:
        return None
    if len(s) > 50:
        s = s[:50]
    return s


def canonical_qno(qno):
    """
    Canonical form for comparison only (dup detection, equality).
    '01', '1', 'Q1', 'Q.1'  →  '1'
    '1A'                    →  '1a'
    '1a'                    →  '1a'
    '1.5', '1(a)'           →  unchanged (structure preserved)
    """
    if qno is None:
        return None
    s = str(qno).strip()
    if not s:
        return None
    s = re.sub(r'^(?:Q\.?\s*|Question\s+)', '', s, flags=re.IGNORECASE).strip()
    # Strip leading zeros from the numeric prefix only
    m = re.match(r'^0*(\d+)(.*)$', s)
    if m:
        return f"{int(m.group(1))}{m.group(2).lower()}"
    return s.lower()


def sort_key_qno(qno):
    """
    Python-side sort key: numeric prefix, then remainder.
    '1' < '1a' < '1b' < '2' < '10' < '10a' < '10b' < '11'
    Non-numeric labels sort after numeric ones.
    """
    if not qno:
        return (999999, '', '')
    s = canonical_qno(qno) or ''
    m = re.match(r'^(\d+)(.*)$', s)
    if m:
        return (int(m.group(1)), m.group(2), '')
    return (999998, s, '')

def format_bilingual_text(nepali, english):
    """Display Nepali and English combined.
    - Both present: 'Nepali (English)'
    - Only one present: just that one, no brackets
    - Neither: empty string
    """
    nepali = (nepali or '').strip()
    english = (english or '').strip()
    if nepali and english:
        return f"{nepali} ({english})"
    return nepali or english

def split_level_and_alias(raw):
    """
    Split a combined 'level' string into (level_number, alias).

    Handles these patterns:
      'Level 6 (Business Officer)'  → ('6', 'Business Officer')
      'Level 6 - Business Officer'  → ('6', 'Business Officer')
      'Level 6 Business Officer'    → ('6', 'Business Officer')
      'Level 6'                     → ('6', None)
      'Officer Level 6'             → ('6', 'Officer')
      'Business Officer Level 6'    → ('6', 'Business Officer')
      '6 Business Officer'          → ('6', 'Business Officer')
      'Business Officer 6'          → ('6', 'Business Officer')
      '6'                           → ('6', None)
      '6/7'                         → ('6/7', None)
      'Business Officer'            → (None, 'Business Officer')
      'Credit Officer - Technical'  → (None, 'Credit Officer - Technical')

    Returns (level_or_None, alias_or_None).
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None

    s = re.sub(r'\s+', ' ', s)

    # Case 1: pure number, or '6/7', '6,7', '6-7' → level only
    if re.fullmatch(r'\d{1,2}(?:[/,\-]\d{1,2})*', s):
        return s, None

    # Case 2: 'Level N ...' — Level at the start
    m = re.match(r'^Level\s+(\d{1,2}(?:[/,\-]\d{1,2})*)\s*(.*)$', s, re.IGNORECASE)
    if m:
        level_num = m.group(1)
        rest = _clean_alias(m.group(2))
        return level_num, rest

    # Case 3: '<prefix> Level N [suffix]' — Level in the middle/end,
    # optional parenthesised suffix after the number.
    # Handles both 'Officer Level 6' and 'Assistant Director Level 6 (Officer Third)'.
    m = re.match(r'^(.+?)\s+Level\s+(\d{1,2}(?:[/,\-]\d{1,2})*)\s*(.*)$',
                 s, re.IGNORECASE)
    if m:
        prefix    = _clean_alias(m.group(1))
        level_num = m.group(2)
        suffix    = m.group(3).strip()
        if suffix:
            suffix = suffix.strip().strip('()').strip()
            suffix = re.sub(r'^[\-–—:]\s*', '', suffix).strip()
            alias_text = f"{prefix} ({suffix})" if prefix else suffix
        else:
            alias_text = prefix
        return level_num, _clean_alias(alias_text)

    # Case 4: 'N <rest>' — number first, alias after
    m = re.match(r'^(\d{1,2}(?:[/,\-]\d{1,2})*)\s+(.+)$', s)
    if m:
        return m.group(1), _clean_alias(m.group(2))

    # Case 5: '<rest> N' — trailing 1-2 digit number as level
    m = re.match(r'^(.+?)\s+(\d{1,2}(?:[/,\-]\d{1,2})*)$', s)
    if m:
        return m.group(2), _clean_alias(m.group(1))

    # Case 6: no number → whole thing is alias
    return None, s


def split_level_and_alias(raw):
    """
    Split a combined 'level' string into (level_number, alias).

    Handles these patterns:
      'Level 6 (Business Officer)'  → ('6', 'Business Officer')
      'Level 6 - Business Officer'  → ('6', 'Business Officer')
      'Level 6 Business Officer'    → ('6', 'Business Officer')
      'Level 6'                     → ('6', None)
      'Officer Level 6'             → ('6', 'Officer')
      'Business Officer Level 6'    → ('6', 'Business Officer')
      '6 Business Officer'          → ('6', 'Business Officer')
      'Business Officer 6'          → ('6', 'Business Officer')
      '6'                           → ('6', None)
      '6/7'                         → ('6/7', None)
      'Business Officer'            → (None, 'Business Officer')
      'Credit Officer - Technical'  → (None, 'Credit Officer - Technical')

    Returns (level_or_None, alias_or_None).
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None

    s = re.sub(r'\s+', ' ', s)

    # Case 1: pure number, or '6/7', '6,7', '6-7' → level only
    if re.fullmatch(r'\d{1,2}(?:[/,\-]\d{1,2})*', s):
        return s, None

    # Case 2: 'Level N ...' — Level at the start
    m = re.match(r'^Level\s+(\d{1,2}(?:[/,\-]\d{1,2})*)\s*(.*)$', s, re.IGNORECASE)
    if m:
        level_num = m.group(1)
        rest = _clean_alias(m.group(2))
        return level_num, rest

    # Case 3: '<prefix> Level N [suffix]' — Level in the middle/end,
    # optional parenthesised suffix after the number.
    m = re.match(r'^(.+?)\s+Level\s+(\d{1,2}(?:[/,\-]\d{1,2})*)\s*(.*)$',
                 s, re.IGNORECASE)
    if m:
        prefix    = _clean_alias(m.group(1))
        level_num = m.group(2)
        suffix    = m.group(3).strip()
        if suffix:
            suffix = suffix.strip().strip('()').strip()
            suffix = re.sub(r'^[\-–—:]\s*', '', suffix).strip()
            alias_text = f"{prefix} ({suffix})" if prefix else suffix
        else:
            alias_text = prefix
        return level_num, _clean_alias(alias_text)

    # Case 4: 'N <rest>' — number first, alias after
    m = re.match(r'^(\d{1,2}(?:[/,\-]\d{1,2})*)\s+(.+)$', s)
    if m:
        return m.group(1), _clean_alias(m.group(2))

    # Case 5: '<rest> N' — trailing 1-2 digit number as level
    m = re.match(r'^(.+?)\s+(\d{1,2}(?:[/,\-]\d{1,2})*)$', s)
    if m:
        return m.group(2), _clean_alias(m.group(1))

    # Case 6: no number → whole thing is alias
    return None, s


def _clean_alias(text):
    """Trim, strip wrapping parens, drop leading/trailing dashes/colons."""
    if not text:
        return None
    t = text.strip().strip('()').strip()
    t = re.sub(r'^[\-–—:]\s*', '', t).strip()
    t = re.sub(r'[\-–—:]\s*$', '', t).strip()
    t = re.sub(r'\s+', ' ', t)
    return t or None
    """Trim, strip wrapping parens, drop leading/trailing dashes/colons."""
    if not text:
        return None
    t = text.strip().strip('()').strip()
    t = re.sub(r'^[\-–—:]\s*', '', t).strip()
    t = re.sub(r'[\-–—:]\s*$', '', t).strip()
    t = re.sub(r'\s+', ' ', t)
    return t or None

def format_level_alias(level, alias):
    """
    Recombine level + alias for display.
      ('6',  'Business Officer') → 'Level 6 (Business Officer)'
      ('6',  None)               → 'Level 6'
      (None, 'Business Officer') → 'Business Officer'
      (None, None)               → ''
    """
    level = (level or '').strip()
    alias = (alias or '').strip()
    level_is_numeric = bool(re.fullmatch(r'\d{1,2}(?:[/,\-]\d{1,2})*', level))
    if level and alias:
        prefix = f"Level {level}" if level_is_numeric else level
        return f"{prefix} ({alias})"
    if level:
        return f"Level {level}" if level_is_numeric else level
    return alias

def _short_preview(text, max_len=50):
    """Truncate text at a word boundary with '…' if longer than max_len."""
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', str(text)).strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    sp = cut.rfind(' ')
    if sp > max_len * 0.6:
        cut = cut[:sp]
    return cut.rstrip(' ,;:') + '…'

def _get_filtered_questions_interactive():
    """
    Show the filter menu, let the user set filters, and return the filtered questions.
    Returns: (filtered_questions, cancelled)
    - filtered_questions: list of question dicts matching the filters, or [] if none
    - cancelled: True if user chose 0 to cancel
    """
    from .question_converter.db_handler import get_questions

    filters = {
        'date': '',
        'institution': '',
        'level': '',
        'paper': '',
        'group': '',
        'subject': '',
        'chapter': '',
        'type': ''
    }

    display_labels = {
        'date': 'Question Date',
        'institution': 'Institution',
        'level': 'Level',
        'paper': 'Paper',
        'group': 'Group',
        'subject': 'Subject',
        'chapter': 'Chapter',
        'type': 'Type'
    }

    def show_filters():
        print("\n" + "─" * 60)
        print_colored("  CURRENT FILTERS", COLORS.YELLOW, bold=True)
        print("─" * 60)
        for i, (key, value) in enumerate(filters.items(), 1):
            display = value if value else color_text("(not set)", COLORS.RED)
            label = display_labels.get(key, key.replace('_', ' ').title())
            print(f"  {i}. {label:15}: {display}")
        print("─" * 60)

    all_questions = get_questions()
    filtered = all_questions

    while True:
        show_filters()

        # Apply filters (substring for text, exact for date/type)
        filtered = all_questions
        for key, value in filters.items():
            if not value:
                continue
            if key == 'type':
                filtered = [q for q in filtered
                            if (q.get('type') or '').lower() == value.lower()]
            elif key == 'date':
                filtered = [q for q in filtered
                            if (q.get('date') or '') == value]
            elif key == 'paper':
                # Exact match — 'paper_i' must not match 'paper_ii'
                filtered = [q for q in filtered
                            if (q.get('paper') or '').lower() == value.lower()]
            elif key == 'question_number':
                # Family match: '1' → 1, 01, 1a, 1b (never 10, 11)
                want = canonical_qno(value)
                if want is not None:
                    def _in_family(qno):
                        c = canonical_qno(qno) or ''
                        if not c.startswith(want):
                            return False
                        tail = c[len(want):]
                        return (not tail) or (not tail[0].isdigit())
                    filtered = [q for q in filtered
                                if _in_family(q.get('question_no'))]
            else:
                # Text fields remain substring matches (subject, institution, etc.)
                filtered = [q for q in filtered
                            if value.lower() in (q.get(key) or '').lower()]

        print_colored(f"[i] {len(filtered)} questions match current filters.", COLORS.BLUE)

        # Show preview of matches
        if filtered:
            print(f"\n  {color_text('Preview (first 5):', COLORS.CYAN)}")
            for q in filtered[:5]:
                qid = q.get('id', '?')
                date = q.get('date', '')
                inst = q.get('institution', '')[:25]
                subj = q.get('subject', '')[:25]
                paper = q.get('paper', '')[:15]
                level = q.get('level', '')[:12]
                qno = q.get('question_no', '')
                print(f"  [{date}] {qid} | {inst} | {subj} | {paper} | {level} | Q{qno}")
            if len(filtered) > 5:
                print(f"  ... and {len(filtered) - 5} more")

        print("\n  " + color_text("OPTIONS:", COLORS.WHITE, bold=True))
        print("  1-8. Edit filter (by number)")
        print("  9.  " + color_text("Execute with current filters", COLORS.GREEN, bold=True))
        print("  0.  " + color_text("Cancel", COLORS.RED))
        print("  c.  " + color_text("Clear all filters", COLORS.YELLOW))
        print("─" * 60)

        choice = input(color_text("Choose an option: ", COLORS.MAGENTA)).strip().lower()

        if choice == '9':
            return filtered, False

        elif choice == '0':
            return [], True

        elif choice == 'c':
            for key in filters:
                filters[key] = ''
            print_colored("[✓] All filters cleared.", COLORS.GREEN)
            continue

        elif choice.isdigit() and 1 <= int(choice) <= 8:
            idx = int(choice) - 1
            key = list(filters.keys())[idx]
            current = filters[key]
            label = display_labels.get(key, key.replace('_', ' ').title())
            new_val = input(color_text(f"New value for {label} [{current}]: ", COLORS.MAGENTA)).strip()
            if new_val:
                filters[key] = new_val
                print_colored(f"[✓] {label} set to: {new_val}", COLORS.GREEN)
            else:
                print_colored("[i] No change.", COLORS.YELLOW)
            continue

        else:
            print_colored("[!] Invalid choice.", COLORS.RED)
            continue

def add_question(date, institution, subject, paper, group, marks, chapter,
                 question_number, nepali, english, level, notes=None,
                 force=False, options=None, pairs=None, hints=None,
                 general_feedback=None, fraction_correct=100, fraction_wrong=-20,
                 shuffle_answers=True, show_num_correct=False,
                 correct_feedback=None, partially_correct_feedback=None,
                 incorrect_feedback=None,
                 response_lines=15, attachments=0,
                 filetypes='.doc,.docx,.pdf,.png,.jpg,.jpeg',
                 maxbytes=2097152, grader_info=None,
                 syllabus_code=None, q_type='essay',
                 feedback_true=None, feedback_false=None,
                 penalty=0, exam_type='open', alias=None):
    # Convert empty strings to None for nullable fields
    if paper == '':
        paper = None
    if group == '':
        group = None
    if notes == '':
        notes = None

    # Normalise the question number centrally so every caller behaves the same
    question_number = normalize_question_number(question_number)

    # Auto-split a combined level string into level + alias.
    # If the caller already passed 'alias' explicitly, trust that and only
    # normalise the level. Otherwise split whatever's in 'level'.
    if alias is None and level:
        level, alias = split_level_and_alias(level)

    # Check duplicate
    if not force:
        existing = check_duplicate(date, institution, level, paper, group, question_number)
        if existing:
            print_colored(f"[!] Duplicate found! Question already exists with ID: {existing}", COLORS.YELLOW)
            overwrite = input(color_text("Overwrite existing question? (y/n): ", COLORS.MAGENTA)).strip().lower()
            if overwrite == 'y':
                # Update existing
                updates = {
                    'subject': subject,
                    'paper': paper,
                    'group': group,
                    'marks': marks,
                    'chapter': chapter,
                    'nepali_transcription': nepali,
                    'english_transcription': english,
                    'notes': notes,
                    'general_feedback': general_feedback,
                    'fraction_correct': fraction_correct,
                    'fraction_wrong': fraction_wrong,
                    'shuffle_answers': shuffle_answers,
                    'show_num_correct': show_num_correct,
                    'correct_feedback': correct_feedback,
                    'partially_correct_feedback': partially_correct_feedback,
                    'incorrect_feedback': incorrect_feedback,
                    'response_lines': response_lines,
                    'attachments': attachments,
                    'filetypes': filetypes,
                    'maxbytes': maxbytes,
                    'grader_info': grader_info,
                    'type': q_type,
                    'feedback_true': feedback_true,
                    'feedback_false': feedback_false,
                    'penalty': penalty,
                }
                # Remove None values
                updates = {k: v for k, v in updates.items() if v is not None}
                if update_question(existing, **updates, options=options, pairs=pairs, hints=hints):
                    print_colored(f"[✓] Question {existing} updated.", COLORS.GREEN)
                    return existing
                else:
                    print_colored("[!] Update failed.", COLORS.RED)
                    return None
            else:
                print_colored("[i] Keeping existing question. No changes made.", COLORS.YELLOW)
                return existing

    # Insert new question
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        INSERT INTO questions
        (question_date, institution, subject, paper, `group`, marks, chapter,
         question_number, nepali_transcription, english_transcription, level, notes,
         general_feedback, fraction_correct, fraction_wrong, shuffle_answers,
         show_num_correct, correct_feedback, partially_correct_feedback,
         incorrect_feedback, response_lines, attachments, filetypes, maxbytes,
         grader_info, type, syllabus_code,
         penalty, feedback_true, feedback_false, exam_type, alias)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s)
    """, (date, institution, subject, paper, group, marks, chapter,
          question_number, nepali, english, level, notes,
          general_feedback, fraction_correct, fraction_wrong,
          shuffle_answers, show_num_correct,
          correct_feedback, partially_correct_feedback, incorrect_feedback,
          response_lines, attachments, filetypes, maxbytes, grader_info, q_type, syllabus_code,
          penalty, feedback_true, feedback_false, exam_type or 'open', alias))
    conn.commit()
    qid = cursor.lastrowid

    # Insert options
    if options:
        for idx, opt in enumerate(options):
            # Derive fraction from 'correct' if not explicitly provided
            if 'fraction' in opt and opt['fraction'] is not None:
                fraction = opt['fraction']
            else:
                fraction = fraction_correct if opt.get('correct', False) else fraction_wrong
            cursor.execute("""
                INSERT INTO question_options (question_id, text, fraction, feedback, display_order)
                VALUES (%s, %s, %s, %s, %s)
            """, (qid, opt['text'], fraction, opt.get('feedback', ''), idx))

    # Insert matching pairs
    if pairs:
        for idx, pair in enumerate(pairs):
            cursor.execute("""
                INSERT INTO question_matching_pairs (question_id, subquestion, answer, display_order)
                VALUES (%s, %s, %s, %s)
            """, (qid, pair['subquestion'], pair['answer'], idx))

    # Insert hints
    if hints:
        for idx, hint in enumerate(hints, 1):
            cursor.execute("""
                INSERT INTO question_hints (question_id, hint_text, clear_incorrect, show_num_correct, hint_number)
                VALUES (%s, %s, %s, %s, %s)
            """, (qid, hint['text'], hint.get('clear_incorrect', False),
                  hint.get('show_num_correct', False), idx))

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Question added with ID: {qid}", COLORS.GREEN)
    return qid

def get_question_by_id(qid):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM questions WHERE id = %s", (qid,))
    q = cursor.fetchone()
    if q:
        cursor.execute("SELECT * FROM question_options WHERE question_id = %s ORDER BY display_order", (qid,))
        opts = cursor.fetchall()
        # Derive 'correct' from fraction (> 0 means correct — Moodle convention)
        for opt in opts:
            try:
                opt['correct'] = float(opt.get('fraction') or 0) > 0
            except (TypeError, ValueError):
                opt['correct'] = False
        q['options'] = opts

        cursor.execute("SELECT * FROM question_matching_pairs WHERE question_id = %s ORDER BY display_order", (qid,))
        q['pairs'] = cursor.fetchall()

        cursor.execute("SELECT * FROM question_hints WHERE question_id = %s ORDER BY hint_number", (qid,))
        q['hints'] = cursor.fetchall()
    cursor.close()
    conn.close()
    return q

def get_questions_by_criteria(date=None, institution=None, level=None, alias=None, paper=None, group=None, subject=None, question_number=None, chapter=None, syllabus_code=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    conditions = []
    params = []

    if date:
        conditions.append("question_date = %s")
        params.append(date)
    if institution:
        conditions.append("institution LIKE %s")
        params.append(f"{institution}%")
    if level:
        conditions.append("level LIKE %s")
        params.append(f"{level}%")
    if alias:
        conditions.append("alias LIKE %s")
        params.append(f"%{alias}%")
    if paper:
        # Paper is a controlled vocabulary (pretest / paper_i / paper_ii / paper_iii).
        # Exact match — otherwise 'paper_i' also matches 'paper_ii'.
        conditions.append("paper = %s")
        params.append(paper)
    if group:
        conditions.append("`group` LIKE %s")
        params.append(f"{group}%")
    if subject:
        conditions.append("subject LIKE %s")
        params.append(f"{subject}%")
    if question_number:
        # Normalise to two-digit form so '1' and '01' both work.
        qn = str(question_number).strip()
        if qn.isdigit():
            qn = qn.zfill(2)
        # Exact match so '1' doesn't also match '10'..'19'.
        conditions.append("question_number = %s")
        params.append(qn)
    if chapter:
        conditions.append("LOWER(chapter) LIKE LOWER(%s)")
        params.append(f"%{chapter}%")
    if syllabus_code:
        # Rough pre-filter in SQL (fast), then exact boundary check in Python.
        conditions.append("syllabus_code LIKE %s")
        params.append(f"%{syllabus_code}%")

    sql = f"SELECT * FROM {TABLE_NAME}"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += (" ORDER BY question_date DESC, institution, level, `group`, subject, "
            # numeric prefix first, then the rest of the string
            "CAST(question_number AS UNSIGNED), question_number")
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # ---- Post-filter: syllabus_code must match as a whole segment ----
    # Prevents '1.5' from matching '1.15', '11.5', '1.50', etc.
    if syllabus_code:
        pattern = re.compile(
            r'(?<![0-9])' + re.escape(syllabus_code.strip()) + r'(?![0-9])'
        )
        rows = [r for r in rows
                if pattern.search(r.get('syllabus_code') or '')]

    return rows

def get_all_questions(sort_by='question_date', order='DESC', search=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    if search:
        sql = """
            SELECT *, MATCH(subject, institution, paper, `group`, chapter,
                            nepali_transcription, english_transcription, notes)
                   AGAINST (%s IN NATURAL LANGUAGE MODE) AS relevance
            FROM questions
            WHERE MATCH(subject, institution, paper, `group`, chapter,
                        nepali_transcription, english_transcription, notes)
                  AGAINST (%s IN NATURAL LANGUAGE MODE)
            ORDER BY relevance DESC
        """
        cursor.execute(sql, (search, search))
    else:
        if sort_by == 'question_number':
            cursor.execute(
                f"SELECT * FROM questions "
                f"ORDER BY CAST(question_number AS UNSIGNED) {order}, question_number {order}"
            )
        else:
            cursor.execute(f"SELECT * FROM questions ORDER BY {sort_by} {order}")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def search_questions_all_fields(search_term):
    """
    Return question rows (full data) that match search_term in main table
    or in options/pairs.
    This is the same function used by the web interface.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    like = f"%{search_term}%"

    # Search main table
    sql_main = """
        SELECT id FROM questions
        WHERE subject LIKE %s OR institution LIKE %s OR chapter LIKE %s
           OR nepali_transcription LIKE %s OR english_transcription LIKE %s
           OR notes LIKE %s
    """
    cursor.execute(sql_main, (like, like, like, like, like, like))
    main_ids = [row['id'] for row in cursor.fetchall()]

    # Search options
    sql_options = """
        SELECT DISTINCT question_id FROM question_options
        WHERE text LIKE %s
    """
    cursor.execute(sql_options, (like,))
    option_ids = [row['question_id'] for row in cursor.fetchall()]

    # Search matching pairs (subquestion and answer)
    sql_pairs = """
        SELECT DISTINCT question_id FROM question_matching_pairs
        WHERE subquestion LIKE %s OR answer LIKE %s
    """
    cursor.execute(sql_pairs, (like, like))
    pair_ids = [row['question_id'] for row in cursor.fetchall()]

    # Union all IDs
    all_ids = set(main_ids + option_ids + pair_ids)

    cursor.close()
    conn.close()

    if not all_ids:
        return []

    # Fetch full question rows
    placeholders = ','.join(['%s'] * len(all_ids))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM questions WHERE id IN ({placeholders})", list(all_ids))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def update_question(qid, **kwargs):
    options = kwargs.pop('options', None)
    pairs = kwargs.pop('pairs', None)
    hints = kwargs.pop('hints', None)

    fields = []
    values = []
    for key, val in kwargs.items():
        if val is not None:
            if key == 'group':
                fields.append("`group` = %s")
            else:
                fields.append(f"{key} = %s")
            values.append(val)

    if not fields:
        return 'no_fields'

    values.append(qid)
    sql = f"UPDATE questions SET {', '.join(fields)} WHERE id = %s"

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, values)
        conn.commit()
        affected = cursor.rowcount

        if options is not None or pairs is not None or hints is not None:
            if options is not None:
                cursor.execute("DELETE FROM question_options WHERE question_id = %s", (qid,))
                # Pull the question-level fractions (may not be in kwargs)
                q_frac_correct = kwargs.get('fraction_correct', 100)
                q_frac_wrong = kwargs.get('fraction_wrong', -20)
                for idx, opt in enumerate(options):
                    if 'fraction' in opt and opt['fraction'] is not None:
                        fraction = opt['fraction']
                    else:
                        fraction = q_frac_correct if opt.get('correct', False) else q_frac_wrong
                    cursor.execute("""
                        INSERT INTO question_options (question_id, text, fraction, feedback, display_order)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (qid, opt['text'], fraction, opt.get('feedback', ''), idx))
            if pairs is not None:
                cursor.execute("DELETE FROM question_matching_pairs WHERE question_id = %s", (qid,))
                for idx, pair in enumerate(pairs):
                    cursor.execute("""
                        INSERT INTO question_matching_pairs (question_id, subquestion, answer, display_order)
                        VALUES (%s, %s, %s, %s)
                    """, (qid, pair['subquestion'], pair['answer'], idx))
            if hints is not None:
                cursor.execute("DELETE FROM question_hints WHERE question_id = %s", (qid,))
                for idx, hint in enumerate(hints, 1):
                    cursor.execute("""
                        INSERT INTO question_hints (question_id, hint_text, clear_incorrect, show_num_correct, hint_number)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (qid, hint['text'], hint.get('clear_incorrect', False),
                          hint.get('show_num_correct', False), idx))
            conn.commit()

        cursor.close()
        conn.close()
        return 'updated' if affected > 0 else 'no_change'
    except Exception as e:
        cursor.close()
        conn.close()
        return f'error: {e}'

def delete_question(qid):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id = %s", (qid,))
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    return affected > 0

def check_duplicate(date, institution, level, paper, group, question_number, exclude_id=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conditions = []
        params = []

        def add_condition(field, value):
            if value is None:
                conditions.append(f"{field} IS NULL")
            else:
                conditions.append(f"{field} = %s")
                params.append(value)

        # Paper, group, level, date, institution — exact DB values are fine
        add_condition("question_date", date)
        add_condition("institution", institution)
        add_condition("level", level)
        add_condition("paper", paper)
        add_condition("`group`", group)

        # Question number — compare canonical forms so '1' and '01' collide
        want = canonical_qno(question_number)
        if want is None:
            conditions.append("(question_number IS NULL OR question_number = '')")
        else:
            # Fetch candidates with the same numeric prefix, then filter in Python
            conditions.append("question_number IS NOT NULL AND question_number != ''")
            # We'll do the canonical comparison after fetching.

        sql = "SELECT id, question_number FROM questions WHERE " + " AND ".join(conditions)
        if exclude_id:
            sql += " AND id != %s"
            params.append(exclude_id)

        cursor.execute(sql, params)
        for row in cursor.fetchall():
            if canonical_qno(row['question_number']) == want:
                return row['id']
        return None
    finally:
        cursor.close()
        conn.close()

# ---------- Display helpers ----------
def _display_single_question(q):
    qid = q.get('id', '?')
    qno = normalize_question_number(q.get('question_number'))
    qtype = q.get('type', 'essay')

    print()
    print_colored("  " + _title_rule(f"📄 QUESTION DETAILS   ID: {qid}"), COLORS.CYAN)

    # ---------- Institution / Level / Date ----------
    inst = q.get('institution') or '(unknown institution)'
    level = q.get('level') or ''
    date_str = q.get('question_date') or ''
    group = q.get('group') or ''
    subject = q.get('subject') or ''

    print(f"  {'Institution':<14}: {color_text(inst, COLORS.BLUE, bold=True)}")
    if level or q.get('alias'):
        print(f"  {'Level':<14}: {format_level_alias(level, q.get('alias'))}")
    if date_str:
        print(f"  {'Date':<14}: {date_str}")
    if group:
        print(f"  {'Group':<14}: {group}")
    if subject:
        print(f"  {'Subject':<14}: {subject}")

    exam_type = q.get('exam_type') or 'open'
    exam_label = EXAM_TYPE_LABELS.get(exam_type, exam_type)
    print(f"  {'Exam type':<14}: {color_text(exam_label, COLORS.YELLOW)}")

    # ---------- Syllabus context ----------
    info = resolve_question_syllabus(q)
    if info['paper_display'] or info['subject_name'] or info['chapter_name'] or info['code_display']:
        print()
        print_colored("  📖  Syllabus Link", COLORS.CYAN, bold=True)
        print("  " + "─" * (_QB_WIDTH - 4))
        if info['paper_display']:
            print(f"     {'Paper':<10}: {info['paper_display']}")
        if info['subject_name']:
            code = info['subject_code'] or ''
            print(f"     {'Subject':<10}: {code} — {info['subject_name']}")
        elif info['subject_code']:
            print(f"     {'Subject':<10}: {info['subject_code']}  (name not in syllabus)")
        if info['chapter_name']:
            code = info['chapter_code'] or ''
            print(f"     {'Chapter':<10}: {code} — {info['chapter_name']}")
        if info['code_display']:
            print(f"     {'Code':<10}: {info['code_display']}   {color_text('(' + info['reason'] + ')', COLORS.YELLOW)}")
        if not (info['subject_name'] or info['chapter_name']):
            print_colored("     [i] No matching subject/chapter found in your syllabus.", COLORS.YELLOW)

    # ---------- Cross-linked lectures ----------
    if info['paper_key'] and info['subject_code'] and info['chapter_code']:
        lectures = find_lectures_for_chapter(
            info['paper_key'], info['subject_code'], info['chapter_code']
        )
        if lectures:
            print()
            print_colored(
                f"  📼  Lectures in this chapter  ({len(lectures)})",
                COLORS.CYAN, bold=True
            )
            print("  " + "─" * (_QB_WIDTH - 4))
            for lec in lectures:
                sid = lec.get('syllabus_id') or ''
                date_str = lec.get('nepali_date') or ''
                lecturer = (lec.get('lecturer') or '')[:22]
                title = (lec.get('chapter') or lec.get('subject') or '')[:36]
                line = f"     {sid:<14}  {date_str:<12}  {lecturer:<22}  {title}"
                print(line)

    # ---------- Question text ----------
    nepali = html_to_terminal(q.get('nepali_transcription') or '').strip()
    english = html_to_terminal(q.get('english_transcription') or '').strip()
    marks = q.get('marks')
    notes = q.get('notes')

    print()
    print_colored("  📝  Question", COLORS.CYAN, bold=True)
    print("  " + "─" * (_QB_WIDTH - 4))

    line = f"     {color_text(f'Q.No. {qno}.', COLORS.CYAN, bold=True)}"
    if marks and str(marks).isdigit():
        line += f"  {color_text(f'[{marks} marks]', COLORS.YELLOW)}"
    line += f"  {color_text(f'Type: {qtype}', COLORS.BLUE)}"
    print(line)

    if nepali and english and nepali.strip().lower() == english.strip().lower():
        # Identical → show once
        print(f"\n     {nepali}")
    else:
        if nepali:
            print(f"\n     {nepali}")
        if english:
            prefix = "     " if not nepali else "     "
            print(f"{prefix}{color_text('(' + english + ')', COLORS.WHITE) if nepali else english}")

    if notes:
        print(f"\n     {color_text('📝 Note:', COLORS.YELLOW)} {notes}")

    # ---------- Type-specific details ----------
    if qtype == 'multichoice':
        options = q.get('options', [])
        if options:
            print()
            print_colored("  🔘  Options", COLORS.CYAN, bold=True)
            print("  " + "─" * (_QB_WIDTH - 4))
            for idx, opt in enumerate(options):
                letter = chr(ord('A') + idx)
                mark = color_text("✓", COLORS.GREEN, bold=True) if opt.get('correct') else " "
                text = opt.get('text', '')
                print(f"     {mark}  {letter}. {text}")
        fc = q.get('fraction_correct')
        fw = q.get('fraction_wrong')
        if fc is not None or fw is not None:
            print(f"     {color_text('Scoring:', COLORS.WHITE)} correct {fc or 100}% · wrong {fw if fw is not None else -20}%")

    elif qtype == 'truefalse':
        options = q.get('options', [])
        print()
        print_colored("  ✅  Correct answer", COLORS.CYAN, bold=True)
        print("  " + "─" * (_QB_WIDTH - 4))
        for opt in options:
            if opt.get('correct'):
                print(f"     {color_text('✓', COLORS.GREEN, bold=True)}  {opt.get('text', '')}")
                break
        if q.get('feedback_true'):
            print(f"     • If True : {html_to_terminal(q['feedback_true'])}")
        if q.get('feedback_false'):
            print(f"     • If False: {html_to_terminal(q['feedback_false'])}")

    elif qtype == 'matching':
        pairs = q.get('pairs', [])
        if pairs:
            print()
            print_colored("  🔗  Matching pairs", COLORS.CYAN, bold=True)
            print("  " + "─" * (_QB_WIDTH - 4))
            for pair in pairs:
                sub = pair.get('subquestion', '')
                ans = pair.get('answer', '')
                print(f"     {sub}  {color_text('↔', COLORS.CYAN)}  {ans}")
        hints = q.get('hints', [])
        if hints:
            print()
            print_colored("  💡  Hints", COLORS.CYAN, bold=True)
            print("  " + "─" * (_QB_WIDTH - 4))
            for i, h in enumerate(hints, 1):
                extra = []
                if h.get('clear_incorrect'): extra.append("clears incorrect")
                if h.get('show_num_correct'): extra.append("shows count")
                suffix = f"  ({', '.join(extra)})" if extra else ""
                print(f"     Hint {i}: {h.get('text', '')}{suffix}")

    else:  # essay
        print()
        print_colored("  📄  Essay settings", COLORS.CYAN, bold=True)
        print("  " + "─" * (_QB_WIDTH - 4))
        print(f"     Response lines : {q.get('response_lines', 15)}")
        print(f"     Attachments    : {q.get('attachments', 0)}")
        if q.get('filetypes'):
            print(f"     File types     : {q['filetypes']}")
        if q.get('grader_info'):
            print(f"     Grader notes   : {html_to_terminal(q['grader_info'])}")

    # ---------- Answer / explanation ----------
    answer_lines = []
    if qtype == 'multichoice':
        correct = next((o.get('text', '') for o in q.get('options', []) if o.get('correct')), None)
        if correct:
            answer_lines.append(f"✅ Correct option: {correct}")
    elif qtype == 'truefalse':
        correct = next((o.get('text', '') for o in q.get('options', []) if o.get('correct')), None)
        if correct:
            answer_lines.append(f"✅ Correct answer: {correct}")

    if q.get('general_feedback'):
        answer_lines.append(f"💡 Explanation: {html_to_terminal(q['general_feedback'])}")

    if answer_lines:
        print()
        print_colored("  📖  Answer & Explanation", COLORS.GREEN, bold=True)
        print("  " + "─" * (_QB_WIDTH - 4))
        for a in answer_lines:
            print(f"     {a}")

    print()
    print_colored("  " + _rule(), COLORS.CYAN)

def _display_paper(questions, show_answers=False):
    if not questions:
        print_colored("[i] No questions found.", COLORS.YELLOW)
        return

    first = questions[0]
    inst = first.get('institution') or '(unknown institution)'
    level = first.get('level') or ''
    alias = first.get('alias') or ''
    date_str = first.get('question_date') or ''

    print()
    print_colored("  " + _title_rule("📄 EXAM PAPER"), COLORS.CYAN)
    print()
    print(f"     {color_text(inst, COLORS.BLUE, bold=True)}")
    combined_level = format_level_alias(level, alias)
    if combined_level:
        print(f"     {combined_level}")
    if date_str:
        print(f"     {color_text(date_str, COLORS.MAGENTA)}")
    print_colored("  " + _rule(), COLORS.CYAN)

    # Group: subject → chapter → questions  (fall back to group → subject)
    from collections import defaultdict
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for q in questions:
        info = resolve_question_syllabus(q)
        subj = info['subject_name'] or q.get('subject') or 'Uncategorised'
        subj_code = info['subject_code'] or ''
        chap = info['chapter_name'] or q.get('chapter') or 'General'
        chap_code = info['chapter_code'] or ''
        key_subj = f"{subj_code} — {subj}" if subj_code else subj
        key_chap = f"{chap_code} — {chap}" if chap_code else chap
        grouped[key_subj][key_chap][
            (q.get('group') or 'General')] = True   # dummy — just to track group
        grouped[key_subj][key_chap][q['id']] = q     # hold the question itself

    # Flatten: grouped[subject][chapter] = list of q
    flat = {}
    for subj, chapters in grouped.items():
        flat[subj] = {}
        for chap, entries in chapters.items():
            qs = [v for v in entries.values() if isinstance(v, dict)]
            flat[subj][chap] = sorted(qs, key=lambda x: (x.get('question_number') or ''))

    # Render
    for subj_label in sorted(flat):
        print()
        print_colored(f"  📘  {subj_label}", COLORS.CYAN, bold=True)
        for chap_label in sorted(flat[subj_label]):
            qs = flat[subj_label][chap_label]
            print()
            print(f"     {color_text('📗 ' + chap_label, COLORS.GREEN)}  "
                  f"{color_text(f'({len(qs)} question' + ('s' if len(qs) != 1 else '') + ')', COLORS.WHITE)}")
            for q in qs:
                q_no = normalize_question_number(q.get('question_number'))
                marks = q.get('marks')
                qtype = q.get('type', 'essay')
                line = f"        {color_text(f'Q.No. {q_no}.', COLORS.CYAN, bold=True)}"
                if marks and str(marks).isdigit():
                    line += f"  {color_text(f'[{marks} marks]', COLORS.YELLOW)}"
                line += f"  {color_text(f'[{qtype}]', COLORS.BLUE)}"
                print(line)

                nep = html_to_terminal(q.get('nepali_transcription') or '').strip()
                eng = html_to_terminal(q.get('english_transcription') or '').strip()
                if nep and eng and nep.lower() == eng.lower():
                    print(f"           {nep}")
                else:
                    if nep:
                        print(f"           {nep}")
                    if eng:
                        print(f"           {color_text('(' + eng + ')', COLORS.WHITE) if nep else eng}")
                if q.get('notes'):
                    print(f"           {color_text('Note:', COLORS.YELLOW)} {q['notes']}")

                if show_answers:
                    if qtype in ('multichoice', 'truefalse'):
                        for opt in q.get('options', []):
                            marker = color_text(" ✓", COLORS.GREEN, bold=True) if opt.get('correct') else ""
                            print(f"              - {opt.get('text', '')}{marker}")
                    elif qtype == 'matching':
                        for pair in q.get('pairs', []):
                            print(f"              {pair.get('subquestion','')}  "
                                  f"{color_text('↔', COLORS.CYAN)}  {pair.get('answer','')}")
                    if q.get('general_feedback'):
                        print(f"              {color_text('💡', COLORS.GREEN)} {html_to_terminal(q['general_feedback'])}")
                    if qtype == 'essay' and q.get('grader_info'):
                        print(f"              {color_text('📝 Grader:', COLORS.GREEN)} {html_to_terminal(q['grader_info'])}")

    print()
    print_colored("  " + _rule(), COLORS.CYAN)

# ---------- Quick parser ----------
def parse_quick_input(text):
    parts = text.strip().split()
    if len(parts) < 3:
        return None, None, None, None

    date = parts[0]
    question_no = None
    if len(parts) >= 4:
        last = parts[-1]
        if last.isdigit() or (last.startswith('Q') and last[1:].isdigit()):
            question_no = last
            parts = parts[:-1]

    if len(parts) == 2:
        institution = parts[1]
        level = ''
    elif len(parts) >= 3:
        institution = parts[1]
        level = ' '.join(parts[2:])
    else:
        institution = ''
        level = ''

    return date, institution, level, question_no

def quick_lookup_interactive():
    print("\n" + "═" * 50)
    print_colored("  QUICK LOOKUP", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Enter a line in the format:")
    print("  date institution level [question_no]")
    print("Examples:")
    print("  2081-01-25 NRB Officer         -> shows whole paper")
    print("  2081-01-25 NRB Officer 12      -> shows question 12 only")
    print("(You can also just type a keyword for a full-text search.)")
    print("Type '0' or 'exit' to return to the Question Bank menu.")
    print("═" * 50)

    current_results = None
    current_query = None

    while True:
        if current_results is None:
            raw = input(color_text("> ", COLORS.MAGENTA)).strip()
        else:
            raw = input(color_text(f"({len(current_results)} results) > ", COLORS.MAGENTA)).strip()

        if not raw:
            continue

        if raw.lower() in ('0', 'exit', 'quit'):
            print_colored("Returning to Question Bank menu.", COLORS.YELLOW)
            break

        if raw.lower() in ('b', 'back'):
            current_results = None
            current_query = None
            continue

        if current_results is not None and raw.isdigit():
            qid = int(raw)
            q = next((r for r in current_results if r['id'] == qid), None)
            if q:
                # Fetch full question with options/pairs/hints
                full_q = get_question_by_id(qid)
                _display_single_question(full_q)
                print()
                continue
            else:
                print_colored("[!] ID not found in current results.", COLORS.YELLOW)
                continue

        # Parse and search
        date, inst, level, q_no = parse_quick_input(raw)

        if date and inst:
            if q_no:
                results = get_questions_by_criteria(date=date, institution=inst, level=level, question_number=q_no)
                if not results:
                    print_colored("[i] No matching question found.", COLORS.YELLOW)
                    continue
                elif len(results) == 1:
                    full_q = get_question_by_id(results[0]['id'])
                    _display_single_question(full_q)
                    print()
                    continue
                else:
                    print_colored(f"[i] Found {len(results)} questions. Showing all:", COLORS.BLUE)
                    _display_paper(results)
                    current_results = None
                    continue
            else:
                results = get_questions_by_criteria(date=date, institution=inst, level=level)
                if not results:
                    print_colored("[i] No questions found for this paper.", COLORS.YELLOW)
                    continue
                else:
                    show = input(color_text("Include answers? (y/n, default n): ",
                                            COLORS.MAGENTA)).strip().lower() == 'y'
                    _display_paper(results, show_answers=show)
                    current_results = None
                    continue

        # ---- Full-text search using the enhanced function ----
        results = search_questions_all_fields(raw)
        if not results:
            # Try searching by chapter (for syllabus codes like P1-B4.1)
            results = search_questions_by_chapter(raw)
            if not results:
                # Try searching by syllabus_code
                results = get_questions_by_criteria(syllabus_code=raw)
                if not results:
                    print_colored("[i] No matches.", COLORS.YELLOW)
                    current_results = None
                    current_query = None
                    continue

        current_results = results
        current_query = raw

        # Display results with numbering
        print(f"\n--- SEARCH RESULTS ({len(results)} matches) ---")
        for i, r in enumerate(results, 1):
            # Preview: use Nepali or English
            preview = _short_preview(
                r.get('nepali_transcription') or r.get('english_transcription') or '', 45
            )
            print(f"  {i:2}. [{r['id']:3}] | {r['question_date']} | {r['institution'][:20]:20} | {r['subject'][:25]:25} | {r['level'][:12]:12} | Q{r['question_number']} | {r.get('type', 'essay'):10} | {preview}")

        print("\n  Options:")
        print("  • Enter ID number (e.g., 29) to view details")
        print("  • Type 'b' or 'back' to clear this search")
        print("  • Type '0' or 'exit' to return to menu")
        print("  • Type a new search to start fresh")

def find_lectures_for_chapter(paper_key, subj_code, chap_code):
    """
    Return list of youtube_lectures records matching
    (paper_key, subj_code, chap_code) after parsing syllabus_id.
    """
    from .db import get_connection, TABLE_NAME
    from .file_manager import parse_syllabus_id
    if not (paper_key and subj_code and chap_code):
        return []
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT id, video_id, mirror_video_id, video_title, syllabus_id,
               subject, chapter, lecturer, nepali_date, time
        FROM {TABLE_NAME}
        WHERE paper = %s AND syllabus_id IS NOT NULL
        ORDER BY syllabus_id
    """, (paper_key,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    matched = []
    for r in rows:
        s, c, _l = parse_syllabus_id(r.get('syllabus_id'))
        if s == subj_code and c == chap_code:
            matched.append(r)
    return matched


def find_questions_for_chapter(paper_key, subj_code, chap_code):
    """
    Return list of question rows matching a chapter, resolved via
    resolve_question_syllabus().
    """
    from .db import get_connection
    if not (paper_key and subj_code and chap_code):
        return []
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM questions")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    out = []
    for q in rows:
        info = resolve_question_syllabus(q)
        if (info['paper_key'] == paper_key
                and info['subject_code'] == subj_code
                and info['chapter_code'] == chap_code):
            out.append(q)
    return out

def browse_by_syllabus_interactive():
    """
    Paper → Subject → Chapter → Questions drill-down.
    Question counts come from (paper, subject_code, chapter_code) parsed
    from each question's syllabus_code / chapter field.
    """
    from .file_manager import _papers
    from . import syllabus_config as SC

    while True:
        print()
        print_colored("  📖  BROWSE BY SYLLABUS", COLORS.CYAN, bold=True)
        print_colored("  " + _rule(), COLORS.CYAN)

        # --- Load all questions once ---
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM questions")
        all_questions = cursor.fetchall()
        cursor.close(); conn.close()

        # --- Build indexes: (paper, subj, chap) -> [q...], (paper, subj) -> [q...] ---
        from collections import defaultdict
        by_triple = defaultdict(list)
        by_pair = defaultdict(list)
        by_paper = defaultdict(list)

        for q in all_questions:
            info = resolve_question_syllabus(q)
            pk = info['paper_key']
            if not pk:
                continue
            by_paper[pk].append(q)
            subj = info['subject_code']
            chap = info['chapter_code']
            if subj:
                by_pair[(pk, subj)].append(q)
                if chap:
                    by_triple[(pk, subj, chap)].append(q)

        # ==================================================
        # LEVEL 1: Paper selection
        # ================================================
        papers = list(_papers().values())
        if not papers:
            print_colored("[i] No papers configured.", COLORS.YELLOW)
            input("\nPress Enter to continue...")
            return

        print()
        print("  Papers:")
        for i, p in enumerate(papers, 1):
            pk = p['paper_key']
            count = len(by_paper.get(pk, []))
            n_subj = len(SC.get_subjects(paper_key=pk, active_only=True))
            line = f"    {i:2}. {p['display_name']}"
            pad = 52 - len(line) if len(line) < 52 else 4
            line += " " * pad + f"{n_subj:>3} subj · {count:>4} Q"
            print(line)
        print("     0. Back")

        pi = input(color_text("\n  Choose paper: ", COLORS.MAGENTA)).strip()
        if pi == '0' or not pi:
            return
        if not pi.isdigit() or not (1 <= int(pi) <= len(papers)):
            print_colored("[!] Invalid choice.", COLORS.RED)
            continue
        selected_paper = papers[int(pi) - 1]
        paper_key = selected_paper['paper_key']
        paper_display = selected_paper['display_name']

        # ==================================================
        # LEVEL 2: Subject selection
        # ==================================================
        back_to_papers = False
        while not back_to_papers:
            print()
            print_colored(f"  📘  {paper_display}", COLORS.CYAN, bold=True)
            print_colored("  " + _rule(), COLORS.CYAN)

            subjects = SC.get_subjects(paper_key=paper_key, active_only=True)
            if not subjects:
                print_colored("[i] No subjects in this paper.", COLORS.YELLOW)
                input("\nPress Enter to continue...")
                break

            print()
            print("  Subjects:")
            for i, s in enumerate(subjects, 1):
                code = str(s.get('chapter') or '').zfill(2)
                count = len(by_pair.get((paper_key, code), []))
                line = f"    {i:2}. {code} — {s['name']}"
                pad = 56 - len(line) if len(line) < 56 else 4
                line += " " * pad + f"{count:>4} Q"
                print(line)
            print("     0. Back to papers")

            si = input(color_text("\n  Choose subject: ", COLORS.MAGENTA)).strip()
            if si == '0' or not si:
                break
            if not si.isdigit() or not (1 <= int(si) <= len(subjects)):
                print_colored("[!] Invalid choice.", COLORS.RED)
                continue

            selected_subject = subjects[int(si) - 1]
            subj_code = str(selected_subject.get('chapter') or '').zfill(2)
            subj_name = selected_subject['name']

            # ==================================================
            # LEVEL 3: Chapter selection
            # ==================================================
            back_to_subjects = False
            while not back_to_subjects:
                print()
                print_colored(f"  📗  {paper_display}  ›  {subj_code} {subj_name}", COLORS.CYAN, bold=True)
                print_colored("  " + _rule(), COLORS.CYAN)

                chapters = SC.get_chapters(subject_id=selected_subject['id'], active_only=True)
                if not chapters:
                    print_colored("[i] No chapters in this subject.", COLORS.YELLOW)
                    input("\nPress Enter to continue...")
                    break

                print()
                print("  Chapters:")
                for i, c in enumerate(chapters, 1):
                    cc = str(c.get('chapter_code') or '').zfill(2)
                    count = len(by_triple.get((paper_key, subj_code, cc), []))
                    line = f"    {i:2}. {cc} — {c['name']}"
                    pad = 56 - len(line) if len(line) < 56 else 4
                    line += " " * pad + f"{count:>4} Q"
                    print(line)
                print("     0. Back to subjects")

                ci = input(color_text("\n  Choose chapter: ", COLORS.MAGENTA)).strip()
                if ci == '0' or not ci:
                    break
                if not ci.isdigit() or not (1 <= int(ci) <= len(chapters)):
                    print_colored("[!] Invalid choice.", COLORS.RED)
                    continue

                selected_chapter = chapters[int(ci) - 1]
                chap_code = str(selected_chapter.get('chapter_code') or '').zfill(2)
                chap_name = selected_chapter['name']

                # ==================================================
                # LEVEL 4: Question list (stays here after viewing)
                # ==================================================
                qs = by_triple.get((paper_key, subj_code, chap_code), [])
                qs_sorted = sorted(
                    qs,
                    key=lambda x: (x.get('question_date') or '',
                                   x.get('question_number') or '')
                )

                while True:
                    print()
                    print_colored(
                        f"  📄  {paper_display}  ›  {subj_code} {subj_name}  ›  "
                        f"{chap_code} {chap_name}",
                        COLORS.CYAN, bold=True
                    )
                    print_colored("  " + _rule(), COLORS.CYAN)

                    if not qs_sorted:
                        print_colored("  [i] No questions in this chapter yet.", COLORS.YELLOW)
                    else:
                        print(f"\n  {len(qs_sorted)} question(s):")
                        print(f"  {'ID':>5}  {'Date':<10}  {'Qno':<4}  "
                              f"{'Type':<12}  Preview")
                        print("  " + "─" * 70)
                        for q in qs_sorted:
                            qno = (q.get('question_number') or '')[:4]
                            qtype = (q.get('type') or 'essay')[:12]
                            preview = _short_preview(
                                q.get('nepali_transcription')
                                or q.get('english_transcription')
                                or '',
                                40
                            )
                            print(f"  {q['id']:>5}  "
                                  f"{(q.get('question_date') or ''):<10}  "
                                  f"{qno:<4}  {qtype:<12}  {preview}")

                    print()
                    print_colored("  Options:", COLORS.WHITE, bold=True)
                    if qs_sorted:
                        print("    <ID>     view that question (stay on this list)")
                    print("    b        back to chapter list")
                    print("    0        back to subject list")
                    print("    q        back to paper list / exit")

                    cmd = input(color_text("  > ", COLORS.MAGENTA)).strip().lower()

                    if cmd == 'q':
                        return  # full exit from browse

                    if cmd in ('', 'b', 'back'):
                        # Exit question list → back to chapter menu
                        break

                    if cmd == '0':
                        # Exit question list AND chapter menu → back to subject menu
                        back_to_subjects = True
                        break

                    if cmd.isdigit():
                        q = get_question_by_id(int(cmd))
                        if q:
                            _display_single_question(q)
                            input("\nPress Enter to continue...")
                            continue
                        else:
                            print_colored(f"[!] Question {cmd} not found.", COLORS.RED)
                            input("\nPress Enter to continue...")
                            continue

                    print_colored(
                        "[!] Enter a numeric ID, 'b' for chapters, "
                        "'0' for subjects, or 'q' to exit.",
                        COLORS.RED
                    )

                if back_to_subjects:
                    continue
                else:
                    continue

def import_export_submenu():
    while True:
        print("\n" + "─" * 40)
        print_colored("  IMPORT / EXPORT", COLORS.CYAN, bold=True)
        print("─" * 40)
        print("  1. Export to CSV")
        print("  2. Export to JSON")
        print("  3. Export to TXT")
        print("  4. Import from CSV")
        print("  5. Import from JSON")
        print("  6. Import from TXT")
        print("  0. Return to Question Bank menu")
        print("─" * 40)

        choice = input(color_text("Choose an option (0-6): ", COLORS.MAGENTA)).strip()

        if choice == '1':
            export_questions_csv()
        elif choice == '2':
            export_questions_json()
        elif choice == '3':
            export_questions_txt()
        elif choice == '4':
            import_questions_csv()
        elif choice == '5':
            import_questions_json()
        elif choice == '6':
            import_questions_txt()
        elif choice == '0':
            print_colored("Returning to Question Bank menu.", COLORS.YELLOW)
            break
        else:
            print_colored("[!] Invalid option.", COLORS.RED)

# Question bank menu
def unified_question_menu():
    global _last_filtered_questions

    while True:
        print()
        print_colored("  📚  QUESTION BANK", COLORS.CYAN, bold=True)
        print_colored("  " + _rule(), COLORS.CYAN)
        print()

        print(_section_header("📖  BROWSE"))
        print("      1. All questions          paginated, sortable list")
        print("      2. Quick lookup           by date / institution / level")
        print("      3. Whole paper view       grouped by section")
        print("      4. " + color_text("Browse by syllabus", COLORS.GREEN) + "     paper → subject → chapter")
        print("      5. Advanced search        multi-field filters")
        print()

        print(_section_header("✏️   EDIT"))
        print("      6. Add a question")
        print("      7. Update a question")
        print("      8. Delete a question")
        print()

        print(_section_header("🛠️   TOOLS"))
        print("      9. Statistics")
        print("     10. Find duplicates")
        print("     11. Bulk rename a field")
        print()

        print(_section_header("📥  IMPORT  /  📤  EXPORT"))
        print("     12. Import questions   (TXT / CSV / JSON / XML)")
        print("     13. Export questions   (TXT / CSV / JSON / XML / HTML / Exam)")
        print("     14. Convert file to file  (no DB)")
        print()

        print_colored("      0. Back to main menu", COLORS.WHITE)
        print_colored("  " + _rule(), COLORS.CYAN)

        choice = input(color_text("\n  Choose: ", COLORS.MAGENTA)).strip().lower()

        if choice == '1':
            view_all_questions_interactive()
        elif choice == '2':
            quick_lookup_interactive()
        elif choice == '3':
            view_whole_paper_interactive()
        elif choice == '4':
            browse_by_syllabus_interactive()
        elif choice == '5':
            advanced_search_interactive()
        elif choice == '6':
            add_question_interactive()
        elif choice == '7':
            update_question_interactive()
        elif choice == '8':
            delete_question_interactive()
        elif choice == '9':
            question_statistics_interactive()
        elif choice == '10':
            find_duplicates_interactive()
        elif choice == '11':
            bulk_rename_interactive()
        elif choice == '12':
            question_import_menu()
        elif choice == '13':
            question_export_menu()
        elif choice == '14':
            question_convert_menu()
        elif choice == '0':
            break
        else:
            print_colored("[!] Invalid option.", COLORS.RED)


# ---------- Submenus for import / export / convert ----------

def question_import_menu():
    """Import submenu (previously letters a-e)."""
    while True:
        print()
        print_colored("  📥  IMPORT QUESTIONS", COLORS.CYAN, bold=True)
        print_colored("  " + _rule(), COLORS.CYAN)
        print("      1. From TXT   (human-readable)")
        print("      2. From CSV   (full backup, all columns)")
        print("      3. From JSON  (full backup, all columns)")
        print("      4. From XML   (Moodle format)")
        print("      5. Advanced import with filters (--questions ...)")
        print_colored("      0. Back", COLORS.WHITE)
        choice = input(color_text("\n  Choose: ", COLORS.MAGENTA)).strip()

        if choice == '0':
            return

        if choice in ('1', '3', '4'):
            from .question_converter import import_from_file
            from .question_converter.exceptions import ConverterError
            label, fmt = {
                '1': ("TXT", 'txt'),
                '3': ("JSON", 'json'),
                '4': ("XML", 'xml'),
            }[choice]
            filepath = input(color_text(f"{label} file path: ", COLORS.MAGENTA)).strip()
            if not filepath:
                continue
            source = input(color_text("Source name (optional): ", COLORS.MAGENTA)).strip() or None

            print("\nHow to handle duplicates?")
            print("  1. Skip duplicates (keep existing)")
            print("  2. Overwrite existing")
            dup = input(color_text("Choose (1-2): ", COLORS.MAGENTA)).strip()
            if dup not in ('1', '2'):
                print_colored("[!] Invalid choice.", COLORS.RED)
                continue

            force = (dup == '2')
            args = SimpleNamespace(verbose=True, bypass_duplicate=force,
                                   bypass_option=False, questions=None)
            try:
                count, errors = import_from_file(filepath, fmt, source=source, args=args)
                if count == 0 and not errors:
                    print_colored("[i] No questions were imported.", COLORS.YELLOW)
                else:
                    print_colored(f"[✓] Imported {count} questions.", COLORS.GREEN)
                    for e in (errors or [])[:5]:
                        print(f"  {e}")
            except ConverterError as e:
                print_colored(f"[!] {e}", COLORS.RED)

        elif choice == '2':
            import_questions_csv()

        elif choice == '5':
            from .question_converter.converter_main import parser
            from .question_converter import import_from_file
            from .question_converter.exceptions import ConverterError, DuplicateQuestionError, ParseError
            import shlex, os as _os

            print("\nExample: -i input.txt --questions 1,5,10 --bypass-duplicate")
            args_str = input(color_text("Arguments: ", COLORS.MAGENTA)).strip()
            if not args_str:
                continue
            try:
                argv = shlex.split(args_str)
                parsed = parser.parse_args(argv)
                input_file = parsed.input
                if not _os.path.exists(input_file):
                    print_colored(f"[!] File not found: {input_file}", COLORS.RED)
                    continue
                ext = _os.path.splitext(input_file)[1].lower().lstrip('.')
                fmt = {'txt': 'txt', 'text': 'txt', 'xml': 'xml', 'json': 'json'}.get(ext)
                if not fmt:
                    print_colored(f"[!] Unsupported extension: .{ext}", COLORS.RED)
                    continue
                source = input(color_text("Source name (optional): ", COLORS.MAGENTA)).strip() or None
                iargs = SimpleNamespace(verbose=parsed.verbose,
                                        bypass_duplicate=parsed.bypass_duplicate,
                                        bypass_option=parsed.bypass_option,
                                        questions=parsed.questions)
                count, errors = import_from_file(input_file, fmt, source=source, args=iargs)
                print_colored(f"[✓] Imported {count} questions.", COLORS.GREEN)
                for e in (errors or [])[:5]:
                    print(f"  {e}")
            except SystemExit:
                print_colored("[!] Invalid arguments.", COLORS.RED)
            except (ConverterError, ParseError, DuplicateQuestionError) as e:
                print_colored(f"[!] {e}", COLORS.RED)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)

        else:
            print_colored("[!] Invalid option.", COLORS.RED)


def question_export_menu():
    """Export submenu (previously letters f-l)."""
    while True:
        print()
        print_colored("  📤  EXPORT QUESTIONS", COLORS.CYAN, bold=True)
        print_colored("  " + _rule(), COLORS.CYAN)
        print("      1. To TXT      (human-readable)")
        print("      2. To CSV      (full backup)")
        print("      3. To JSON     (full backup)")
        print("      4. To XML      (Moodle)")
        print("      5. To HTML     (web view)")
        print("      6. To Exam HTML (interactive, timed)")
        print("      7. Advanced export with filters")
        print_colored("      0. Back", COLORS.WHITE)
        choice = input(color_text("\n  Choose: ", COLORS.MAGENTA)).strip()

        if choice == '0':
            return

        if choice == '1':
            from .question_converter import export_to_file
            from .question_converter.db_handler import get_questions as get_qs
            qs = get_qs()
            if not qs:
                print_colored("[i] No questions to export.", COLORS.YELLOW)
                continue
            default = f"questions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            outfile = input(color_text(f"Output (default: {default}): ", COLORS.MAGENTA)).strip() or default
            try:
                export_to_file(qs, outfile, 'txt', args=SimpleNamespace(verbose=True))
                print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)

        elif choice == '2':
            export_questions_csv()
        elif choice == '3':
            from .question_converter import export_to_file
            from .question_converter.db_handler import get_questions as get_qs
            qs = get_qs()
            if not qs:
                print_colored("[i] No questions to export.", COLORS.YELLOW); continue
            default = f"questions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            outfile = input(color_text(f"Output (default: {default}): ", COLORS.MAGENTA)).strip() or default
            try:
                export_to_file(qs, outfile, 'json', args=SimpleNamespace(verbose=True))
                print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)
        elif choice == '4':
            from .question_converter import export_to_file
            from .question_converter.db_handler import get_questions as get_qs
            qs = get_qs()
            if not qs:
                print_colored("[i] No questions to export.", COLORS.YELLOW); continue
            default = f"questions_export_moodle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
            outfile = input(color_text(f"Output (default: {default}): ", COLORS.MAGENTA)).strip() or default
            try:
                export_to_file(qs, outfile, 'xml', args=SimpleNamespace(verbose=True))
                print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)
        elif choice == '5':
            from .question_converter import export_to_file
            from .question_converter.db_handler import get_questions as get_qs
            qs = get_qs()
            if not qs:
                print_colored("[i] No questions to export.", COLORS.YELLOW); continue
            default = f"questions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            outfile = input(color_text(f"Output (default: {default}): ", COLORS.MAGENTA)).strip() or default
            try:
                export_to_file(qs, outfile, 'html', args=SimpleNamespace(verbose=True))
                print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)
        elif choice == '6':
            filtered, cancelled = _get_filtered_questions_interactive()
            if cancelled or not filtered:
                continue
            global _last_filtered_questions
            _last_filtered_questions = filtered
            from .question_converter.exam_output import create_exam_html
            default = f"exam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            outfile = input(color_text(f"Output (default: {default}): ", COLORS.MAGENTA)).strip() or default
            t = input(color_text("Time limit in minutes (default 90): ", COLORS.MAGENTA)).strip()
            time_min = int(t) if t.isdigit() else 90
            create_exam_html(filtered, outfile, verbose=True, time_minutes=time_min, pass_marks=45)
            print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)
        elif choice == '7':
            filtered, cancelled = _get_filtered_questions_interactive()
            if cancelled or not filtered:
                continue
            _last_filtered_questions = filtered
            fmt = input(color_text("Format (xml / json / html / txt): ", COLORS.MAGENTA)).strip()
            if not fmt:
                continue
            default = f"questions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
            outfile = input(color_text(f"Output (default: {default}): ", COLORS.MAGENTA)).strip() or default
            try:
                from .question_converter import export_to_file
                export_to_file(filtered, outfile, fmt, args=SimpleNamespace(verbose=True))
                print_colored(f"[✓] Exported {len(filtered)} questions to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)
        else:
            print_colored("[!] Invalid option.", COLORS.RED)


def question_convert_menu():
    """File-to-file converter (no DB) — previously option 'm'."""
    from .question_converter.converter_main import parser, run_conversion
    import shlex

    print("\n[File → File converter — no DB writes]")
    print("💡 Enclose paths with spaces in quotes: -i \"my file.txt\"")
    args_str = input(color_text("Arguments (e.g. -i input.txt -o output.xml --shuffle): ", COLORS.MAGENTA)).strip()
    if not args_str:
        return
    try:
        argv = shlex.split(args_str)
        parsed = parser.parse_args(argv)
        run_conversion(parsed)
    except SystemExit:
        print_colored("💡 If your path has spaces, wrap it in quotes.", COLORS.YELLOW)
    except Exception as e:
        print_colored(f"[!] {e}", COLORS.RED)

# ---------- Interactive functions ----------

def _prompt_field(prompt, default=None):
    val = input(color_text(prompt, COLORS.MAGENTA)).strip()
    return val if val else default

def add_question_interactive():
    print("\n" + "═" * 50)
    print_colored("  ADD NEW QUESTION", COLORS.CYAN, bold=True)
    print("═" * 50)

    # ---- Question type first ----
    print("\nQuestion type:")
    print("  1. Essay (long answer) — default")
    print("  2. Multichoice (MCQ)")
    print("  3. True/False")
    print("  4. Matching")
    t = input(color_text("Choose type (1-4, default 1): ", COLORS.MAGENTA)).strip() or '1'
    q_type = {'1':'essay', '2':'multichoice', '3':'truefalse', '4':'matching'}.get(t, 'essay')

    # ---- Common metadata ----
    date = _prompt_field("Date (YYYY-MM-DD, Enter for today): ")
    if not date:
        date = datetime.today().strftime('%Y-%m-%d')
    institution = _prompt_field("Institution: ")

    # --- Exam type ---
    print("\n  Exam type:")
    for i, (key, label) in enumerate(EXAM_TYPES, 1):
        default_marker = " (default)" if key == 'open' else ""
        print(f"    {i}. {label}{default_marker}")
    et_choice = input(color_text("  Choose (1-4, Enter for Open): ", COLORS.MAGENTA)).strip()
    if et_choice.isdigit() and 1 <= int(et_choice) <= len(EXAM_TYPES):
        exam_type = EXAM_TYPES[int(et_choice) - 1][0]
    else:
        exam_type = 'open'
    subject     = _prompt_field("Subject: ")
    paper       = _prompt_field("Paper: ")
    group       = _prompt_field("Group: ")

    marks = None
    while True:
        raw = input(color_text("Marks (numeric, Enter to skip): ", COLORS.MAGENTA)).strip()
        if not raw:
            break
        if raw.isdigit():
            marks = int(raw); break
        print_colored("[!] Marks must be a number.", COLORS.YELLOW)

    chapter    = _prompt_field("Chapter: ")
    q_num      = _prompt_field("Question Number: ")
    nepali     = _prompt_field("Nepali Transcription: ")
    english    = _prompt_field("English Transcription: ")
    raw_level  = _prompt_field("Level (e.g. '6' or 'Level 6 (Business Officer)'): ")
    level, level_alias = split_level_and_alias(raw_level)
    notes      = input(color_text("Notes (optional): ", COLORS.MAGENTA)).strip() or None
    gf         = input(color_text("General Feedback / Explanation (optional): ", COLORS.MAGENTA)).strip() or None

    options = pairs = hints = None
    feedback_true = feedback_false = None
    grader_info = None

    # ---- Type-specific input ----
    if q_type == 'multichoice':
        options = _prompt_mcq_options()
        if not options or len(options) < 2:
            print_colored("[!] Need at least 2 options.", COLORS.RED); return
        correct_count = sum(1 for o in options if o['correct'])
        if correct_count != 1:
            print_colored(f"[!] Exactly 1 correct option required (you marked {correct_count}).", COLORS.RED); return

    elif q_type == 'truefalse':
        c = input(color_text("Correct answer (t/f, default t): ", COLORS.MAGENTA)).strip().lower()
        is_true = (c != 'f')
        options = [
            {'text': 'True',  'correct':  is_true, 'fraction': 100 if is_true else -20},
            {'text': 'False', 'correct': not is_true, 'fraction': -20 if is_true else 100},
        ]
        feedback_true  = input(color_text("Feedback if True (optional): ",  COLORS.MAGENTA)).strip() or None
        feedback_false = input(color_text("Feedback if False (optional): ", COLORS.MAGENTA)).strip() or None

    elif q_type == 'matching':
        pairs = _prompt_matching_pairs()
        if not pairs or len(pairs) < 2:
            print_colored("[!] Need at least 2 matching pairs.", COLORS.RED); return

    else:  # essay
        grader_info = input(color_text("Grader Information (optional): ", COLORS.MAGENTA)).strip() or None

    force = input(color_text("Force add even if duplicate? (y/n, default n): ", COLORS.MAGENTA)).strip().lower() == 'y'

    qid = add_question(
        date, institution, subject, paper, group, marks,
        chapter, q_num, nepali, english, level, notes,
        force=force,
        options=options, pairs=pairs, hints=hints,
        general_feedback=gf,
        feedback_true=feedback_true, feedback_false=feedback_false,
        grader_info=grader_info,
        q_type=q_type,
        exam_type=exam_type,
        alias=level_alias,
    )
    if qid:
        print_colored(f"[✓] Question processed with ID: {qid}", COLORS.GREEN)


def _prompt_mcq_options():
    print("\n  Enter options one per line. Mark the correct one with '*' at the end.")
    print("  Examples:  Kathmandu *  /  Pokhara")
    print("  Empty line when done (at least 2).")
    opts = []
    while True:
        raw = input(color_text(f"  Option {len(opts)+1}: ", COLORS.MAGENTA)).strip()
        if not raw:
            break
        correct = raw.endswith('*')
        text = raw.rstrip('*').strip()
        if text:
            opts.append({'text': text, 'correct': correct})
    return opts


def _prompt_matching_pairs():
    print("\n  Enter pairs: subquestion, then its answer. Empty subquestion ends.")
    print("  Need at least 2 pairs.")
    pairs = []
    while True:
        sub = input(color_text(f"  Subquestion {len(pairs)+1}: ", COLORS.MAGENTA)).strip()
        if not sub:
            break
        ans = input(color_text(f"    Answer for '{sub}': ", COLORS.MAGENTA)).strip()
        if not ans:
            print_colored("  Answer empty — pair skipped.", COLORS.YELLOW); continue
        pairs.append({'subquestion': sub, 'answer': ans})
    return pairs

def view_all_questions_interactive():
    print("\nSort by:")
    print("  1. Date (default)   2. Subject   3. Institution")
    print("  4. Paper            5. Level     6. Type")
    sort_choice = input(color_text("Choose (1-6, default 1): ", COLORS.MAGENTA)).strip()
    sort_map = {
        '1': ('question_date', 'Date'),
        '2': ('subject', 'Subject'),
        '3': ('institution', 'Institution'),
        '4': ('paper', 'Paper'),
        '5': ('level', 'Level'),
        '6': ('type', 'Type'),
    }
    col, display_name = sort_map.get(sort_choice, ('question_date', 'Date'))

    order = input(color_text("Order (a=asc, d=desc, default d): ", COLORS.MAGENTA)).strip().lower()
    order_sql = 'ASC' if order == 'a' else 'DESC'

    # Optional type filter before we fetch
    t_filter = input(color_text("Type filter (essay/multichoice/truefalse/matching, Enter=all): ",
                                COLORS.MAGENTA)).strip().lower()
    rows = get_all_questions(sort_by=col, order=order_sql)
    if t_filter:
        rows = [r for r in rows if (r.get('type') or 'essay').lower() == t_filter]
    if not rows:
        print_colored("[i] No questions found.", COLORS.YELLOW)
        return

    PAGE_SIZE = 20
    total = len(rows)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = 1

    def _print_page(page_items, page_num):
        print(f"\n--- PAGE {page_num}/{pages} — {total} question(s) "
              f"(sorted by {color_text(display_name, COLORS.CYAN, bold=True)}) ---")
        print(f"  {'ID':>5} | {'Date':<10} | {'Institution':<20} | {'Subject':<22} | "
              f"{'Paper':<10} | {'Level':<10} | Qno | Type        | Preview")
        print("  " + "─" * 140)
        for r in page_items:
            qno = r.get('question_number', '') or ''
            qtype = (r.get('type') or 'essay')
            preview = _short_preview(
                r.get('nepali_transcription') or r.get('english_transcription') or '', 45
            )
            print(f"  {r['id']:>5} | "
                  f"{(r.get('question_date') or ''):<10} | "
                  f"{(r.get('institution') or '')[:20]:<20} | "
                  f"{(r.get('subject') or '')[:22]:<22} | "
                  f"{(r.get('paper') or '')[:10]:<10} | "
                  f"{(r.get('level') or '')[:10]:<10} | "
                  f"{qno:>3} | {qtype:<11} | {preview}")

    while True:
        start = (page - 1) * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        _print_page(rows[start:end], page)

        print("\n  [n]ext  [p]rev  [g]oto <page>  [i]d <ID> to view  [Enter] exit")
        cmd = input(color_text("> ", COLORS.MAGENTA)).strip().lower()

        if cmd in ('', 'q', 'exit'):
            return
        elif cmd == 'n':
            if page < pages:
                page += 1
            else:
                print_colored("Already on last page.", COLORS.YELLOW)
        elif cmd == 'p':
            if page > 1:
                page -= 1
            else:
                print_colored("Already on first page.", COLORS.YELLOW)
        elif cmd.startswith('g '):
            try:
                p = int(cmd.split()[1])
                if 1 <= p <= pages:
                    page = p
                else:
                    print_colored(f"[!] Page must be 1–{pages}.", COLORS.RED)
            except Exception:
                print_colored("[!] Usage: g <page>", COLORS.RED)
        elif cmd.startswith('i '):
            try:
                qid = int(cmd.split()[1])
                q = get_question_by_id(qid)
                if q:
                    _display_single_question(q)
                else:
                    print_colored(f"[!] Question ID {qid} not found.", COLORS.RED)
            except Exception:
                print_colored("[!] Usage: i <ID>", COLORS.RED)
        else:
            print_colored("[!] Unknown command.", COLORS.RED)

def view_whole_paper_interactive():
    print("\n" + "═" * 50)
    print_colored("  VIEW WHOLE PAPER (INTERACTIVE)", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Enter the paper details. At least one field is required.\n")

    date = _prompt_field("Date (YYYY-MM-DD): ")
    institution = _prompt_field("Institution (keyword): ")
    level = _prompt_field("Level (keyword): ")
    paper = _prompt_field("Paper (optional): ")

    if not any([date, institution, level, paper]):
        print_colored("[!] You must provide at least one search criterion.", COLORS.RED)
        return

    results = get_questions_by_criteria(date=date, institution=institution,
                                        level=level, paper=paper)
    if not results:
        print_colored("[i] No questions found.", COLORS.YELLOW)
        return

    show = input(color_text("Include options / correct answers / explanations? (y/n, default n): ",
                            COLORS.MAGENTA)).strip().lower() == 'y'
    _display_paper(results, show_answers=show)

def advanced_search_interactive():
    print("\n" + "═" * 50)
    print_colored("  ADVANCED SEARCH", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Set search criteria by choosing a field number, then enter the value.")
    print("Leave value blank to clear that criterion.")
    print("After setting criteria, choose '9. Search' to run the search.\n")

    fields = ['id', 'date', 'institution', 'level', 'alias', 'paper', 'group', 'subject',
            'question_number', 'chapter', 'syllabus_code', 'type', 'exam_type']
    display_names = {
        'id':              'question ID',
        'date':            'question_date',
        'institution':     'institution',
        'level': 'level',
        'alias': 'alias (role)',
        'paper':           'paper',
        'group':           'group',
        'subject':         'subject',
        'question_number': 'question_number',
        'chapter':         'chapter',
        'syllabus_code':   'syllabus_code',
        'type':            'type',
        'exam_type':       'exam type',
    }
    criteria = {f: '' for f in fields}

    while True:
        print("─" * 50)
        print_colored("  CURRENT CRITERIA", COLORS.YELLOW, bold=True)
        for i, field in enumerate(fields, 1):
            display_name = display_names[field]
            val = criteria[field]
            if not val:
                display = color_text("(not set)", COLORS.RED)
            else:
                display_val = str(val)
                if len(display_val) > 30:
                    display_val = display_val[:27] + "..."
                display = color_text(display_val, COLORS.GREEN)
            print(f"  {i:2}. {display_name:18}: {display}")
        print("─" * 50)
        print("  90. " + color_text("Search with current criteria", COLORS.CYAN, bold=True))
        print("  0. " + color_text("Return to Question Bank menu", COLORS.YELLOW))
        choice = input(color_text(f"\nChoose a field to edit (1-{len(fields)}), 90 to search, or 0 to return: ", COLORS.MAGENTA)).strip()

        if choice == '90':
            kwargs = {}
            for field in fields:
                val = criteria[field].strip()
                if val:
                    kwargs[field] = val

            # ---- Direct ID lookup takes precedence ----
            # If the user typed a question ID, jump straight to that question
            # and skip the rest of the filtering pipeline.
            if 'id' in kwargs:
                id_val = kwargs.pop('id')
                if id_val.isdigit():
                    q = get_question_by_id(int(id_val))
                    if q:
                        _display_single_question(q)
                    else:
                        print_colored(f"[!] Question ID {id_val} not found.", COLORS.RED)
                    continue
                # Non-numeric → silently ignore, fall through to normal filters

            # Family mode is always on — '1' matches 1, 01, 1a, 1b, 1(a), 1.5
            family_mode = True

            # Don't pass question_number to SQL — we filter it in Python below
            # so that '1' can match '1a', '1b', etc. when in family mode.
            sql_kwargs = {k: v for k, v in kwargs.items()
                          if k not in ('type', 'question_number', 'exam_type')}
            results = get_questions_by_criteria(**sql_kwargs)

            # ─── BLOCK 2: apply the question_number filter in Python ───
            if 'question_number' in kwargs:
                want = canonical_qno(kwargs['question_number'])
                if want is None:
                    # User typed something that canonicalised to nothing (e.g. just 'Q').
                    # Nothing to match — skip question_number filtering entirely.
                    pass
                else:
                    def _in_family(qno):
                        c = canonical_qno(qno) or ''
                        if not c.startswith(want):
                            return False
                        tail = c[len(want):]
                        return (not tail) or (not tail[0].isdigit())

                    if family_mode:
                        results = [q for q in results if _in_family(q.get('question_number'))]
                    else:
                        results = [q for q in results
                                   if canonical_qno(q.get('question_number')) == want]

            # Type filter
            if 'type' in kwargs:
                results = [q for q in results if q.get('type', '').lower() == kwargs['type'].lower()]

            # Exam-type filter
            if 'exam_type' in kwargs:
                wanted = kwargs['exam_type'].strip().lower()
                results = [q for q in results
                           if (q.get('exam_type') or 'open').lower() == wanted]

            if not results:
                print_colored("[i] No matches found.", COLORS.YELLOW)
                continue

            if len(results) == 1:
                full_q = get_question_by_id(results[0]['id'])
                _display_single_question(full_q)
            else:
                print(f"\n--- SEARCH RESULTS ({len(results)} matches) ---")
                for r in results:
                    preview = _short_preview(
                        r.get('nepali_transcription') or r.get('english_transcription') or '', 55
                    )
                    print(f"  {r['id']:3} | {r['question_date']} | {r['institution'][:20]:20} | {r['subject'][:20]:20} | {r['chapter'][:15]:15} | Q{r['question_number']} | {r.get('type', 'essay'):10}")
                    print(f"      {preview}")
                print(f"  Total: {len(results)} matches.")
                while True:
                    choice_id = input(color_text(
                        "\nEnter ID to view (Enter/b/q = back to search): ",
                        COLORS.MAGENTA)).strip().lower()
                    if choice_id in ('', 'b', 'back', 'q', 'quit'):
                        break
                    if not choice_id.isdigit():
                        print_colored("[!] Enter a numeric ID, or press Enter to return.", COLORS.RED)
                        continue
                    if int(choice_id) == 0:
                        break
                    q = get_question_by_id(int(choice_id))
                    if q:
                        _display_single_question(q)
                    else:
                        print_colored(f"[!] ID {choice_id} not found.", COLORS.RED)
            continue

        elif choice == '0':
            break

        elif choice.isdigit() and 1 <= int(choice) <= len(fields):
            idx = int(choice) - 1
            field = fields[idx]
            current = criteria[field]
            display_name = display_names[field]
            new_val = input(color_text(f"Value for {display_name} [{current}]: ", COLORS.MAGENTA)).strip()
            criteria[field] = new_val
            print_colored(f"[✓] {display_name} set to: {new_val if new_val else '(cleared)'}", COLORS.GREEN)
            continue
        else:
            print_colored("[!] Invalid option.", COLORS.RED)

def update_question_interactive():
    qid = input(color_text("Enter question ID to update: ", COLORS.MAGENTA)).strip()
    if not qid or not qid.isdigit():
        print_colored("[!] Invalid ID.", COLORS.RED)
        return

    row = get_question_by_id(int(qid))
    if not row:
        print_colored("[!] Question not found.", COLORS.RED)
        return

    fields = [
        'question_date', 'institution', 'subject', 'paper', 'group',
        'marks', 'chapter', 'question_number',
        'syllabus_code',
        'nepali_transcription', 'english_transcription', 'level', 'alias', 'notes', 'type',
        'exam_type',
        'options',   # special: opens the interactive editor for MCQ/TF/Matching
    ]
    updates = {}

    while True:
        print("\n" + "═" * 50)
        print_colored("  UPDATE QUESTION", COLORS.CYAN, bold=True)
        print("═" * 50)

        for i, field in enumerate(fields, 1):
            val = row.get(field)
            if val is None or val == '':
                display_val = "None"
            else:
                display_val = str(val)
                if len(display_val) > 60:
                    display_val = display_val[:57] + "..."
            print(f"  {i:2}. {field:22}: {display_val}")

        print("\n" + "─" * 50)
        print("  Enter the number of the field to edit, or 0 to save and exit.")
        print("  0. " + color_text("Save changes and exit", COLORS.GREEN))
        print("─" * 50)

        choice = input(color_text("Choose field (0-13): ", COLORS.MAGENTA)).strip()

        if choice == '0':
            if not updates:
                print_colored("[i] No changes made.", COLORS.YELLOW)
                return

            status = update_question(int(qid), **updates)
            if status == 'updated':
                print_colored("[✓] Question updated successfully.", COLORS.GREEN)
            elif status == 'no_change':
                print_colored("[i] No changes were made (values already the same).", COLORS.YELLOW)
            elif status.startswith('error'):
                print_colored(f"[!] Update failed: {status}", COLORS.RED)
            else:
                print_colored(f"[!] Unexpected status: {status}", COLORS.RED)
            return

        if not choice.isdigit():
            print_colored("[!] Please enter a number.", COLORS.RED)
            continue

        idx = int(choice)
        if idx < 1 or idx > len(fields):
            print_colored(f"[!] Please enter a number between 1 and {len(fields)}.", COLORS.RED)
            continue

        field = fields[idx - 1]
        current = row.get(field, '')

        # ---- Special: exam_type ----
        if field == 'exam_type':
            print("\n  Exam type:")
            for i, (key, label) in enumerate(EXAM_TYPES, 1):
                cur = " ← current" if key == (row.get('exam_type') or 'open') else ""
                print(f"    {i}. {label}{cur}")
            et = input(color_text(f"  Choose (1-{len(EXAM_TYPES)}, Enter to keep): ", COLORS.MAGENTA)).strip()
            if et.isdigit() and 1 <= int(et) <= len(EXAM_TYPES):
                updates['exam_type'] = EXAM_TYPES[int(et) - 1][0]
                row['exam_type'] = updates['exam_type']
                print_colored(f"[✓] Exam type set to {EXAM_TYPE_LABELS[updates['exam_type']]}.", COLORS.GREEN)
            else:
                print_colored("[i] No change.", COLORS.YELLOW)
            continue

        # ---- Special: options / pairs / hints ----
        if field == 'options':
            q_full = get_question_by_id(int(qid))
            q_type = q_full.get('type', 'essay')
            if q_type == 'multichoice':
                print("\n  Current options:")
                for i, o in enumerate(q_full.get('options', []), 1):
                    marker = "✓" if o.get('correct') else " "
                    print(f"    {i}. [{marker}] {o['text']}")
                print("\n  Enter new options (one per line, '*' = correct). Empty line when done.")
                print("  Or press Enter immediately to keep existing.")
                new_options = _prompt_mcq_options()
                if new_options:
                    correct_n = sum(1 for o in new_options if o['correct'])
                    if correct_n != 1:
                        print_colored(f"[!] Need exactly 1 correct (got {correct_n}). Keeping existing.", COLORS.RED)
                    else:
                        updates['options'] = new_options
                        print_colored(f"[✓] {len(new_options)} new option(s) staged.", COLORS.GREEN)
                else:
                    print_colored("[i] No change to options.", COLORS.YELLOW)
            elif q_type == 'truefalse':
                print("\n  Current:")
                for o in q_full.get('options', []):
                    print(f"    [{'✓' if o.get('correct') else ' '}] {o['text']}")
                c = input(color_text("Change correct answer to (t/f, Enter to keep): ", COLORS.MAGENTA)).strip().lower()
                if c in ('t', 'f'):
                    is_true = (c == 't')
                    updates['options'] = [
                        {'text': 'True',  'correct':  is_true, 'fraction': 100 if is_true else -20},
                        {'text': 'False', 'correct': not is_true, 'fraction': -20 if is_true else 100},
                    ]
                    print_colored(f"[✓] Correct answer set to {c.upper()}.", COLORS.GREEN)
            elif q_type == 'matching':
                print("\n  Current pairs:")
                for p in q_full.get('pairs', []):
                    print(f"    {p['subquestion']}  ↔  {p['answer']}")
                if input(color_text("Replace all pairs? (y/n): ", COLORS.MAGENTA)).strip().lower() == 'y':
                    new_pairs = _prompt_matching_pairs()
                    if new_pairs and len(new_pairs) >= 2:
                        updates['pairs'] = new_pairs
                        print_colored(f"[✓] {len(new_pairs)} pair(s) staged.", COLORS.GREEN)
                    else:
                        print_colored("[i] Not enough pairs — keeping existing.", COLORS.YELLOW)
            else:
                print_colored("[i] Essay questions have no options/pairs.", COLORS.YELLOW)
            continue

        # ---- Special: alias (role/designation) ----
        if field == 'alias':
            current = row.get('alias') or ''
            print(f"\nCurrent alias: {color_text(current or '(empty)', COLORS.BLUE)}")
            raw = input(color_text("New alias (or 'clear' to blank): ", COLORS.MAGENTA)).strip()
            if raw == '':
                print_colored("[i] Skipped.", COLORS.YELLOW)
                continue
            if raw.lower() in ('clear', 'null', 'none'):
                updates['alias'] = None
                row['alias'] = None
                print_colored("[✓] Alias will be cleared.", COLORS.GREEN)
            else:
                updates['alias'] = raw
                row['alias'] = raw
                print_colored(f"[✓] Alias will be updated to: {raw}", COLORS.GREEN)
            continue


        # ---- Special: syllabus_code ----
        if field == 'syllabus_code':
            raw = input(color_text("New syllabus code (e.g. 06.03, or 'clear' to blank it): ",
                                COLORS.MAGENTA)).strip()

            if raw.lower() == 'clear':
                updates['syllabus_code'] = None
                row['syllabus_code'] = None
                print_colored("[✓] syllabus_code will be cleared.", COLORS.GREEN)
                continue

            if not re.match(r'^\d{2}\.\d{2}$', raw):
                print_colored("[!] Must be two-digit.two-digit, e.g. '06.03'.", COLORS.RED)
                continue

            updates['syllabus_code'] = raw
            row['syllabus_code'] = raw
            print_colored(f"[✓] syllabus_code will be updated to {raw}", COLORS.GREEN)

            # ---- keep the chapter description in sync ----
            old_chapter = row.get('chapter') or ''
            new_chapter = re.sub(r'\([^)]*\)\s*$', f'({raw})', old_chapter)
            if new_chapter != old_chapter:
                updates['chapter'] = new_chapter
                row['chapter'] = new_chapter
                print_colored(f"[✓] chapter description updated to match.", COLORS.GREEN)

            continue

        print(f"\nCurrent value: {color_text(current if current != '' else '(empty)', COLORS.BLUE)}")
        prompt = color_text(f"New value (press Enter to skip, or type 'clear' to empty): ", COLORS.MAGENTA)
        raw = input(prompt).strip()

        if raw == '':
            print_colored("[i] Skipped (no change).", COLORS.YELLOW)
            continue

        if raw.lower() in ('clear', 'null', 'none'):
            if field == 'marks':
                updates[field] = None
                row[field] = None
                print_colored("[✓] Marks will be cleared (set to NULL).", COLORS.GREEN)
            else:
                updates[field] = ''   # empty string
                row[field] = ''
                print_colored("[✓] Field will be cleared (set to empty string).", COLORS.GREEN)
            continue

        if field == 'level':
            # Auto-split if user typed 'Level 6 (Business Officer)' or similar
            new_level, new_alias = split_level_and_alias(raw)
            updates['level'] = new_level
            row['level'] = new_level
            if new_alias:
                updates['alias'] = new_alias
                row['alias'] = new_alias
                print_colored(f"[✓] Split → level='{new_level}', alias='{new_alias}'", COLORS.GREEN)
            else:
                print_colored(f"[✓] Level set to '{new_level}'", COLORS.GREEN)
            continue

        if field == 'marks':
            if raw.isdigit():
                updates[field] = int(raw)
                row[field] = int(raw)
                print_colored(f"[✓] Marks will be updated to {raw}", COLORS.GREEN)
            else:
                print_colored("[!] Marks must be a number. Keeping current value.", COLORS.YELLOW)
        else:
            updates[field] = raw
            row[field] = raw
            print_colored(f"[✓] {field} will be updated to: {raw}", COLORS.GREEN)

def delete_question_interactive():
    qid = input(color_text("Enter question ID to delete: ", COLORS.MAGENTA)).strip()
    if not qid or not qid.isdigit():
        print_colored("[!] Invalid ID.", COLORS.RED)
        return
    row = get_question_by_id(int(qid))
    if not row:
        print_colored("[!] Question not found.", COLORS.RED)
        return
    print(f"Question: {row['subject']} - {row['question_number']} ({row['institution']})")
    confirm = input(color_text("Delete this question? (y/n): ", COLORS.RED)).strip().lower()
    if confirm == 'y':
        if delete_question(int(qid)):
            print_colored("[✓] Question deleted.", COLORS.GREEN)
        else:
            print_colored("[!] Deletion failed.", COLORS.RED)
    else:
        print_colored("Cancelled.", COLORS.YELLOW)

def _json_safe_default(o):
    """Fallback encoder for json.dumps: handles Decimal and date/datetime."""
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

# ---------- Export / Import (CSV) ----------
def export_questions_csv():
    print("\n" + "═" * 50)
    print_colored("  EXPORT QUESTIONS TO CSV (FULL)", COLORS.CYAN, bold=True)
    print("═" * 50)

    print_colored("[i] Fetching questions from database...", COLORS.BLUE)
    rows = get_all_questions()
    if not rows:
        print_colored("[i] No questions to export.", COLORS.YELLOW)
        return

    filename = input(color_text("Enter CSV filename (default: questions_export_full.csv): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "questions_export_full.csv"
    if not filename.endswith('.csv'):
        filename += '.csv'

    import json
    from decimal import Decimal
    from datetime import date, datetime

    export_fields = [
        'id',
        'question_date', 'institution', 'level', 'paper', 'group',
        'subject', 'chapter', 'question_number', 'marks',
        'nepali_transcription', 'english_transcription', 'notes',
        'source', 'type', 'exam_type',
        'general_feedback', 'fraction_correct', 'fraction_wrong',
        'syllabus_code',
        'shuffle_answers', 'show_num_correct',
        'correct_feedback', 'partially_correct_feedback', 'incorrect_feedback',
        'response_lines', 'attachments', 'filetypes', 'maxbytes',
        'grader_info',
        'penalty',
        'feedback_true', 'feedback_false'
    ]

    data = []
    conn = get_connection()
    total = len(rows)
    print_colored(f"[i] Exporting {total} questions to {filename}…", COLORS.BLUE)
    import time
    _start = time.time()

    for idx, row in enumerate(rows, 1):
        qid = row['id']
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM question_options WHERE question_id = %s ORDER BY display_order", (qid,))
        options = cursor.fetchall()
        cursor.execute("SELECT * FROM question_matching_pairs WHERE question_id = %s ORDER BY display_order", (qid,))
        pairs = cursor.fetchall()
        cursor.execute("SELECT * FROM question_hints WHERE question_id = %s ORDER BY hint_number", (qid,))
        hints = cursor.fetchall()
        cursor.close()

        out_row = {}
        for f in export_fields:
            val = row.get(f)
            if isinstance(val, (datetime, date)):
                val = str(val)
            if isinstance(val, Decimal):
                val = int(val) if val % 1 == 0 else float(val)
            out_row[f] = val

        out_row['options_json'] = json.dumps(options, ensure_ascii=False,
                                             default=_json_safe_default) if options else None
        out_row['pairs_json']   = json.dumps(pairs, ensure_ascii=False,
                                             default=_json_safe_default) if pairs else None
        out_row['hints_json']   = json.dumps(hints, ensure_ascii=False,
                                             default=_json_safe_default) if hints else None

        data.append(out_row)

    conn.close()

    fieldnames = export_fields + ['options_json', 'pairs_json', 'hints_json']
    print_colored(f"[i] Writing CSV file: {filename}...", COLORS.BLUE)
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        elapsed = time.time() - _start
        size_kb = os.path.getsize(filename) / 1024
        print_colored(f"[✓] Exported {len(data)} questions to {filename} "
                      f"({size_kb:.1f} KB, {elapsed:.2f}s)", COLORS.GREEN)
        print_colored("[i] Options, pairs, hints are saved as JSON strings in separate columns.", COLORS.YELLOW)
        print_colored("[i] To re-import this CSV, use the enhanced import function (option b).", COLORS.YELLOW)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_questions_csv():
    print("\n" + "═" * 50)
    print_colored("  IMPORT QUESTIONS FROM CSV (FULL)", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Expects a CSV with all scalar columns + options_json, pairs_json, hints_json.\n")

    filename = input(color_text("Enter CSV filename: ", COLORS.MAGENTA)).strip()
    if not filename or not os.path.exists(filename):
        print_colored("[!] File not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        print_colored(f"[!] Failed to read CSV: {e}", COLORS.RED)
        return

    if not rows:
        print_colored("[i] No data found.", COLORS.YELLOW)
        return

    # Normalise rows
    for row in rows:
        row.pop('id', None)
        for field in ['paper', 'group', 'chapter', 'notes', 'source']:
            if field in row and row[field] == '':
                row[field] = None

        if row.get('marks'):
            try:
                row['marks'] = int(row['marks'])
            except ValueError:
                row['marks'] = None
        if row.get('grade'):
            try:
                row['grade'] = float(row['grade'])
            except ValueError:
                row['grade'] = 1

        for json_col in ['options_json', 'pairs_json', 'hints_json']:
            if row.get(json_col):
                try:
                    row[json_col] = json.loads(row[json_col])
                except json.JSONDecodeError:
                    row[json_col] = None
            else:
                row[json_col] = None

        if 'question_number' in row:
            row['question_no'] = row['question_number']
        if 'response_lines' in row:
            row['lines'] = row['response_lines']

    from .question_converter.db_handler import insert_question
    from .question_converter.exceptions import DuplicateQuestionError

    print(f"\n[i] Found {len(rows)} questions in the CSV file.")
    print("How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Overwrite existing (by duplicate key)")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    skipped = 0
    errors = []

    total = len(rows)
    for idx, row in enumerate(rows, 1):
        if idx % 5 == 0 or idx == total:
            qno = row.get('question_no', '?')
            print(f"{COLORS.CYAN}  [{idx}/{total}] Processing Q{qno}...{COLORS.RESET}")

        q_dict = {
            'question_date': row.get('question_date'),
            'institution': row.get('institution'),
            'level': row.get('level'),
            'paper': row.get('paper'),
            'group': row.get('group'),
            'subject': row.get('subject'),
            'chapter': row.get('chapter'),
            'question_no': row.get('question_no'),
            'marks': row.get('marks'),
            'nepali_transcription': row.get('nepali_transcription'),
            'english_transcription': row.get('english_transcription'),
            'notes': row.get('notes'),
            'source': row.get('source'),
            'type': row.get('type', 'essay'),
            'grade': row.get('grade', 1),
            'lines': row.get('lines', 15),
            'penalty': row.get('penalty', 0),
            'general_feedback': row.get('general_feedback'),
            'fraction_correct': row.get('fraction_correct', 100),
            'fraction_wrong': row.get('fraction_wrong', -20),
            'shuffle_answers': row.get('shuffle_answers', True),
            'show_num_correct': row.get('show_num_correct', False),
            'correct_feedback': row.get('correct_feedback'),
            'partially_correct_feedback': row.get('partially_correct_feedback'),
            'incorrect_feedback': row.get('incorrect_feedback'),
            'attachments': row.get('attachments', 0),
            'filetypes': row.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg'),
            'maxbytes': row.get('maxbytes', 2097152),
            'grader_info': row.get('grader_info'),
            'penalty': row.get('penalty', 0),
            'feedback_true': row.get('feedback_true'),
            'feedback_false': row.get('feedback_false'),
            'exam_type': row.get('exam_type') or 'open',
            'options': row.get('options_json'),
            'pairs': row.get('pairs_json'),
            'hints': row.get('hints_json'),
        }
        q_dict = {k: v for k, v in q_dict.items() if v is not None}

        try:
            if choice == '1':
                insert_question(q_dict, source=row.get('source'), force=False)
                added += 1
            elif choice == '2':
                insert_question(q_dict, source=row.get('source'), force=True)
                updated += 1
            else:
                insert_question(q_dict, source=row.get('source'), force=False)
                added += 1
        except DuplicateQuestionError as e:
            if choice == '1':
                skipped += 1
            elif choice == '3':
                print_colored(f"\n[!] Duplicate found. Aborting: {e}", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
            else:
                skipped += 1
        except Exception as e:
            errors.append(str(e))

    conn.commit()
    cursor.close()
    conn.close()

    print("\n" + "═" * 50)
    print_colored("  IMPORT COMPLETE", COLORS.CYAN, bold=True)
    print(f"  {COLORS.GREEN}✅ Added   : {added}{COLORS.RESET}")
    print(f"  {COLORS.BLUE}🔄 Updated : {updated}{COLORS.RESET}")
    print(f"  {COLORS.YELLOW}⏭️ Skipped : {skipped}{COLORS.RESET}")
    if errors:
        print(f"  {COLORS.RED}❌ Errors  : {len(errors)}{COLORS.RESET}")
    print("═" * 50)

def export_questions_txt():
    print("\n" + "═" * 50)
    print_colored("  📤 EXPORT TO TXT", COLORS.CYAN, bold=True)
    print("═" * 50)

    rows = get_all_questions()
    if not rows:
        print_colored("[i] No questions to export.", COLORS.YELLOW)
        return

    filename = input(color_text("Enter TXT filename (default: questions_export.txt): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "questions_export.txt"
    if not filename.endswith('.txt'):
        filename += '.txt'

    field_order = [
        'question_date', 'institution', 'level', 'paper', 'group',
        'subject', 'chapter', 'marks', 'notes', 'source'
    ]
    labels = {
        'question_date': 'Date',
        'institution': 'Institution',
        'level': 'Level',
        'paper': 'Paper',
        'group': 'Group',
        'subject': 'Subject',
        'chapter': 'Chapter',
        'marks': 'Marks',
        'notes': 'Notes',
        'source': 'Source'
    }

    total = len(rows)
    import time
    start_time = time.time()

    print_colored(f"\n📤 Exporting {total} questions to {filename}...", COLORS.CYAN)

    type_counts = {}
    exported = 0
    skipped = 0

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# Exported Question Bank (with IDs)\n")
            f.write(f"# Total: {total} questions\n")
            f.write("# Each block is separated by '---'\n")
            f.write("# The 'Question No.' line must come first in each block.\n\n")

            for idx, row in enumerate(rows, 1):
                q = get_question_by_id(row['id'])
                if not q:
                    print_colored(f"[!] Skipping question {row['id']} (not found)", COLORS.YELLOW)
                    skipped += 1
                    continue

                q_type = q.get('type', 'essay')
                type_counts[q_type] = type_counts.get(q_type, 0) + 1

                f.write("---\n")

                qno = q.get('question_number', '')
                q_text = q.get('nepali_transcription') or q.get('english_transcription') or ''
                if qno:
                    f.write(f"Question No. {qno}: {q_text}\n")
                else:
                    f.write(f"Question: {q_text}\n")

                if q.get('id'):
                    f.write(f"ID: {q['id']}\n")

                for key in field_order:
                    val = q.get(key)
                    if val is not None and val != '':
                        if key == 'marks' and val:
                            val = str(val)
                        elif isinstance(val, (date, datetime)):
                            val = str(val)
                        f.write(f"{labels.get(key, key)}: {val}\n")
                if q.get('syllabus_code'):
                    f.write(f"Syllabus Code: {q['syllabus_code']}\n")
                # Only write Exam Type when it differs from the default
                et = (q.get('exam_type') or 'open').lower()
                if et != 'open':
                    nice = {
                        'internal': 'Internal',
                        'promotional': 'Promotional',
                        'other': 'Other',
                    }.get(et, et.capitalize())
                    f.write(f"Exam Type: {nice}\n")

                nep = q.get('nepali_transcription', '').strip()
                eng = q.get('english_transcription', '').strip()
                if nep:
                    f.write(f"Nepali: {nep}\n")
                if eng:
                    f.write(f"English: {eng}\n")

                f.write(f"Type: {q_type}\n")

                if q_type == "multichoice":
                    for opt in q.get('options', []):
                        marker = " *" if opt.get('correct', False) else ""
                        f.write(f"Option: {opt.get('text', '')}{marker}\n")
                    if q.get('grade', 1) != 1:
                        f.write(f"Grade: {q.get('grade', 1)}\n")
                    if q.get('penalty', 0) != 0:
                        f.write(f"Penalty: {q.get('penalty', 0)}\n")
                    if q.get('fraction_correct', 100) != 100 or q.get('fraction_wrong', -20) != -20:
                        f.write(f"Fraction: {q.get('fraction_correct', 100)} {q.get('fraction_wrong', -20)}\n")

                elif q_type == "truefalse":
                    for opt in q.get('options', []):
                        if opt.get('correct', False):
                            f.write(f"Correct: {opt.get('text', '').lower()}\n")
                            break
                    if q.get('grade', 1) != 1:
                        f.write(f"Grade: {q.get('grade', 1)}\n")
                    if q.get('penalty', 0) != 0:
                        f.write(f"Penalty: {q.get('penalty', 0)}\n")
                    if q.get('feedback_true'):
                        f.write(f"Feedback True: {q.get('feedback_true')}\n")
                    if q.get('feedback_false'):
                        f.write(f"Feedback False: {q.get('feedback_false')}\n")
                    if q.get('fraction_correct', 100) != 100 or q.get('fraction_wrong', -20) != -20:
                        f.write(f"Fraction: {q.get('fraction_correct', 100)} {q.get('fraction_wrong', -20)}\n")

                elif q_type == "matching":
                    for pair in q.get('pairs', []):
                        f.write(f"Subquestion: {pair.get('subquestion', '')}\n")
                        f.write(f"Answer: {pair.get('answer', '')}\n")
                    if q.get('grade', 1) != 1:
                        f.write(f"Grade: {q.get('grade', 1)}\n")
                    if q.get('penalty', 0) != 0:
                        f.write(f"Penalty: {q.get('penalty', 0)}\n")
                    if q.get('shuffle_answers', True) is False:
                        f.write("Shuffle Answers: false\n")
                    if q.get('show_num_correct', False):
                        f.write("Show Number Correct: true\n")
                    if q.get('correct_feedback') and q.get('correct_feedback') != "Your answer is correct.":
                        f.write(f"Correct Feedback: {q.get('correct_feedback')}\n")
                    if q.get('partially_correct_feedback') and q.get('partially_correct_feedback') != "Your answer is partially correct.":
                        f.write(f"Partially Correct Feedback: {q.get('partially_correct_feedback')}\n")
                    if q.get('incorrect_feedback') and q.get('incorrect_feedback') != "Your answer is incorrect.":
                        f.write(f"Incorrect Feedback: {q.get('incorrect_feedback')}\n")
                    for hint in q.get('hints', []):
                        f.write(f"Hint: {hint.get('text', '')}\n")
                        if hint.get('clear_incorrect', False):
                            f.write("Hint Clear Incorrect: true\n")
                        if hint.get('show_num_correct', False):
                            f.write("Hint Show Number Correct: true\n")

                else:  # essay
                    if q.get('grade', 1) != 1:
                        f.write(f"Grade: {q.get('grade', 1)}\n")
                    if q.get('lines', 15) != 15:
                        f.write(f"Lines: {q.get('lines', 15)}\n")
                    if q.get('attachments', 0) > 0:
                        f.write(f"Attachments: {q.get('attachments')}\n")
                        f.write(f"FileTypes: {q.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg')}\n")
                        max_mb = q.get('maxbytes', 2 * 1024 * 1024) / (1024 * 1024)
                        f.write(f"MaxFileSizeMB: {max_mb:.0f}\n")
                    if q.get('grader_info'):
                        f.write(f"Grader Information: {q.get('grader_info')}\n")

                # ---- Common to ALL question types ----
                if q.get('feedback_true'):
                    f.write(f"Feedback True: {q['feedback_true']}\n")
                if q.get('feedback_false'):
                    f.write(f"Feedback False: {q['feedback_false']}\n")
                if q.get('general_feedback'):
                    f.write(f"General Feedback: {q.get('general_feedback')}\n")

                f.write("\n")
                exported += 1

            f.write("---\n")

    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)
        return

    elapsed = time.time() - start_time
    file_size = os.path.getsize(filename) / 1024

    print("\n" + "═" * 60)
    print_colored("  📤 EXPORT SUMMARY", COLORS.CYAN, bold=True)
    print("═" * 60)
    print(f"  📁 Output file: {filename}")
    print(f"  📊 Questions  : {exported} (skipped: {skipped})")
    print(f"  🏷️  Format     : TXT")
    print(f"  💾 File size  : {file_size:.2f} KB")
    print(f"  ⏱️  Time       : {elapsed:.2f}s")
    if type_counts:
        print(f"  📈 Types      : {', '.join(f'{k}: {v}' for k, v in type_counts.items())}")
    print("═" * 60)

def import_questions_txt():
    print("\n" + "═" * 50)
    print_colored("  IMPORT FROM TEXT FILE (Smart)", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Supports both full (all fields repeated) and context‑aware formats.")
    print("Context lines (Date, Institution, Level, Paper, Group, etc.)")
    print("apply to all following question blocks until changed.\n")

    filename = input(color_text("Enter Text filename (e.g., questions.txt): ", COLORS.MAGENTA)).strip()
    if not filename or not os.path.exists(filename):
        print_colored("[!] File not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print_colored(f"[!] Failed to read file: {e}", COLORS.RED)
        return

    raw_blocks = re.split(r'\n---+\s*\n', content)
    raw_blocks = [b.strip() for b in raw_blocks if b.strip()]

    if not raw_blocks:
        print_colored("[i] No blocks found.", COLORS.YELLOW)
        return

    context = {}
    questions = []
    for block in raw_blocks:
        lines = block.split('\n')
        block_data = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' not in line:
                continue
            key, val = line.split(':', 1)
            key = key.strip().lower().replace(' ', '_')
            val = val.strip()
            if key == 'marks' and val.isdigit():
                val = int(val)
            if key == 'question_number':
                val = normalize_question_number(val)
            block_data[key] = val

        if 'question_number' not in block_data:
            context.update(block_data)
            continue

        merged = context.copy()
        merged.update(block_data)

        required = ('date', 'institution', 'level', 'question_number')
        missing = [r for r in required if r not in merged]
        if missing:
            print_colored(f"[!] Skipping block: missing {', '.join(missing)}", COLORS.YELLOW)
            continue

        db_q = {
            'question_date': merged.get('date'),
            'institution': merged.get('institution'),
            'level': merged.get('level'),
            'subject': merged.get('subject'),
            'paper': merged.get('paper'),
            'group': merged.get('group'),
            'marks': merged.get('marks'),
            'chapter': merged.get('chapter'),
            'question_number': merged.get('question_number'),
            'nepali_transcription': merged.get('nepali'),
            'english_transcription': merged.get('english'),
            'notes': merged.get('notes') or merged.get('note'),
            'feedback_true': merged.get('feedback_true'),
            'feedback_false': merged.get('feedback_false')
        }
        questions.append(db_q)

    if not questions:
        print_colored("[i] No valid question blocks found.", COLORS.YELLOW)
        return

    print(f"\n[i] Found {len(questions)} valid question(s) in the text file.")
    print("How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Overwrite existing records (update all fields)")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    no_change = 0
    skipped = 0

    total = len(questions)
    for idx, q in enumerate(questions, 1):
        date = q.get('question_date')
        institution = q.get('institution')
        level = q.get('level')
        paper = q.get('paper')
        group = q.get('group')
        question_number = q.get('question_number')

        dup_id = check_duplicate(date, institution, level, paper, group, question_number)

        if dup_id:
            if choice == '1':
                skipped += 1
                print(f"  [{idx}/{total}] Skipped Q{question_number} (ID: {dup_id})     ")
                continue
            elif choice == '2':
                updates = {k: v for k, v in q.items() if v is not None and k != 'question_date'}
                if not updates:
                    print(f"  [{idx}/{total}] Q{question_number} – no fields to update, skipping.")
                    skipped += 1
                    continue

                status = update_question(dup_id, **updates)
                if status == 'updated':
                    updated += 1
                    print(f"  [{idx}/{total}] Updated Q{question_number} (ID: {dup_id})     ")
                elif status == 'no_change':
                    no_change += 1
                    print(f"  [{idx}/{total}] Q{question_number} already up-to-date.")
                else:
                    print_colored(f"  [{idx}/{total}] Error updating Q{question_number}: {status}", COLORS.RED)
                    skipped += 1
                continue
            else:
                print_colored(f"\n[!] Duplicate found for question {question_number} (ID: {dup_id}). Aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
            fields = [k for k, v in q.items() if v is not None]
            values = [v for v in q.values() if v is not None]
            escaped_fields = [f"`{f}`" if f == 'group' else f for f in fields]
            placeholders = ','.join(['%s'] * len(fields))
            sql = f"INSERT INTO {TABLE_NAME} ({', '.join(escaped_fields)}) VALUES ({placeholders})"
            try:
                cursor.execute(sql, values)
                new_id = cursor.lastrowid
                added += 1
                print(f"  [{idx}/{total}] Added Q{question_number} (ID: {new_id})     ")
            except Exception as e:
                print_colored(f"  [{idx}/{total}] Failed to insert Q{question_number}: {e}", COLORS.RED)
                skipped += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\n[✓] Import complete: {added} added, {updated} updated, {no_change} unchanged, {skipped} skipped.")

def export_questions_json():
    print("\n" + "═" * 50)
    print_colored("  EXPORT QUESTIONS TO JSON", COLORS.CYAN, bold=True)
    print("═" * 50)

    rows = get_all_questions()
    if not rows:
        print_colored("[i] No questions to export.", COLORS.YELLOW)
        return

    filename = input(color_text("Enter JSON filename (default: questions_export.json): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "questions_export.json"
    if not filename.endswith('.json'):
        filename += '.json'

    total = len(rows)
    print_colored(f"[i] Exporting {total} questions to {filename}…", COLORS.BLUE)
    import time
    _start = time.time()

    export_data = []
    for idx, row in enumerate(rows, 1):
        clean_row = row.copy()
        clean_row.pop('created_at', None)
        clean_row.pop('updated_at', None)
        if 'question_date' in clean_row and clean_row['question_date']:
            if hasattr(clean_row['question_date'], 'isoformat'):
                clean_row['question_date'] = clean_row['question_date'].isoformat()
            else:
                clean_row['question_date'] = str(clean_row['question_date'])
        for key, value in clean_row.items():
            if isinstance(value, Decimal):
                clean_row[key] = int(value) if value % 1 == 0 else float(value)
        export_data.append(sanitize_for_json(clean_row))

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        file_size = os.path.getsize(filename) / 1024
        elapsed = time.time() - _start
        print_colored(f"[✓] Exported {len(export_data)} questions to {filename} "
                      f"({file_size:.1f} KB, {elapsed:.2f}s)", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_questions_json():
    from .question_converter.constants import C
    print("\n" + "═" * 50)
    print_colored("  IMPORT QUESTIONS FROM JSON", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("The JSON file should be an array of question objects.")
    print("Each object can have keys matching the database columns (except 'id', 'created_at', 'updated_at').")
    print("If a duplicate is found (same date, institution, level, paper, group, question_number), you can skip, overwrite, or abort.\n")

    filename = input(color_text("Enter JSON filename: ", COLORS.MAGENTA)).strip()
    if not filename or not os.path.exists(filename):
        print_colored("[!] File not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            rows = json.load(f)
    except Exception as e:
        print_colored(f"[!] Failed to read JSON: {e}", COLORS.RED)
        return

    if not isinstance(rows, list):
        print_colored("[!] JSON must be an array of objects.", COLORS.RED)
        return
    if not rows:
        print_colored("[i] No data found.", COLORS.YELLOW)
        return

    for obj in rows:
        obj.pop('id', None)
        if 'question_number' in obj and obj['question_number']:
            obj['question_number'] = normalize_question_number(obj['question_number'])
        for field in ['paper', 'group', 'chapter', 'notes']:
            if field in obj and obj[field] == '':
                obj[field] = None

    print(f"\n[i] Found {len(rows)} questions in the JSON file.")
    print("How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Overwrite existing (by duplicate key)")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    no_change = 0
    skipped = 0

    fields = ['question_date', 'institution', 'subject', 'paper', 'group',
            'marks', 'chapter', 'question_number', 'nepali_transcription',
            'english_transcription', 'level', 'notes',
            'feedback_true', 'feedback_false', 'exam_type']
    escaped_fields = [f"`{f}`" if f == 'group' else f for f in fields]

    total = len(rows)
    for idx, obj in enumerate(rows, 1):
        date = obj.get('question_date')
        institution = obj.get('institution')
        level = obj.get('level')
        paper = obj.get('paper')
        group = obj.get('group')
        question_number = obj.get('question_number')

        dup_id = None
        if date and institution and level and paper is not None and group is not None and question_number:
            dup_id = check_duplicate(date, institution, level, paper, group, question_number)

        if dup_id:
            if choice == '1':
                skipped += 1
                print(f"  [{idx}/{total}] Skipped Q{question_number} (ID: {dup_id})     ")
                continue
            elif choice == '2':
                updates = {}
                for f in fields:
                    val = obj.get(f)
                    if val is not None:
                        updates[f] = val
                if not updates:
                    print(f"  [{idx}/{total}] Q{question_number} (ID: {dup_id}) – no fields to update, skipping.")
                    skipped += 1
                    continue

                status = update_question(dup_id, **updates)
                if status == 'updated':
                    updated += 1
                    print(f"  [{idx}/{total}] Updated Q{question_number} (ID: {dup_id})     ")
                elif status == 'no_change':
                    no_change += 1
                    print(f"  [{idx}/{total}] Q{question_number} (ID: {dup_id}) already up-to-date.")
                else:
                    print_colored(f"  [{idx}/{total}] Error updating Q{question_number}: {status}", COLORS.RED)
                    skipped += 1
                continue
            else:
                print_colored(f"\n[!] Duplicate found for question {question_number} (ID: {dup_id}). Aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
            placeholders = ','.join(['%s'] * len(fields))
            cols = ','.join(escaped_fields)
            values = [obj.get(f) for f in fields]
            values = [v if v is not None else None for v in values]
            try:
                cursor.execute(f"INSERT INTO {TABLE_NAME} ({cols}) VALUES ({placeholders})", values)
                new_id = cursor.lastrowid
                added += 1
                print(f"  [{idx}/{total}] Added Q{question_number} (ID: {new_id})     ")
            except Exception as e:
                print_colored(f"  [{idx}/{total}] Failed to insert Q{question_number}: {e}", COLORS.RED)
                skipped += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\n[✓] Import complete: {added} added, {updated} updated, {no_change} unchanged, {skipped} skipped.")

# ---------- Chapter browsing ----------
def get_distinct_chapters():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT chapter FROM {TABLE_NAME} WHERE chapter IS NOT NULL AND chapter != '' ORDER BY chapter")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [row[0] for row in rows]

def get_distinct_values(column, search_term, limit=10):
    conn = get_connection()
    cursor = conn.cursor()
    sql = f"SELECT DISTINCT {column} FROM {TABLE_NAME} WHERE {column} LIKE %s ORDER BY {column} LIMIT %s"
    cursor.execute(sql, (f"{search_term}%", limit))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    result = []
    for row in rows:
        val = row[0]
        if val is None:
            continue
        if column == 'question_date' and isinstance(val, (date, datetime)):
            val = val.strftime('%Y-%m-%d')
        else:
            val = str(val)
        result.append(val)
    return result

def get_questions_by_chapter(chapter_code):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE chapter LIKE %s
        ORDER BY question_number
    """, (f"%{chapter_code}%",))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_distinct_chapters_like(search_term):
    conn = get_connection()
    cursor = conn.cursor()
    like = f"%{search_term}%"
    cursor.execute(
        "SELECT DISTINCT chapter FROM questions WHERE chapter LIKE %s ORDER BY chapter LIMIT 10",
        (like,)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [row[0] for row in rows]

def find_duplicates_interactive():
    print("\n" + "═" * 60)
    print_colored("  FIND DUPLICATE QUESTIONS", COLORS.CYAN, bold=True)
    print("═" * 60)
    print("  Groups by (date, institution, level, paper, group, number).")
    print("  Any group with more than one row is a duplicate cluster.\n")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT question_date, institution, level, paper, `group`, question_number,
               COUNT(*) AS n, GROUP_CONCAT(id ORDER BY id) AS ids
        FROM questions
        GROUP BY question_date, institution, level, paper, `group`, question_number
        HAVING n > 1
        ORDER BY n DESC, question_date DESC
    """)
    groups = cursor.fetchall()
    cursor.close(); conn.close()

    if not groups:
        print_colored("[✓] No duplicate clusters found.", COLORS.GREEN); return

    print_colored(f"[!] {len(groups)} duplicate cluster(s):\n", COLORS.YELLOW)
    for g in groups:
        ids = g['ids'].split(',')
        print(f"  {g['question_date']} | {g['institution']} | {g['level']} "
              f"| {g['paper'] or '-'} | {g['group'] or '-'} | Q{g['question_number']} "
              f"→ {g['n']} copies  (IDs: {', '.join(ids)})")

    pick = input(color_text("\nEnter IDs to view (comma-separated) or Enter to skip: ", COLORS.MAGENTA)).strip()
    if pick:
        for qid in [x.strip() for x in pick.split(',') if x.strip().isdigit()]:
            q = get_question_by_id(int(qid))
            if q:
                _display_single_question(q); print()


def question_statistics_interactive():
    print("\n" + "═" * 60)
    print_colored("  📊 QUESTION BANK STATISTICS", COLORS.CYAN, bold=True)
    print("═" * 60)

    conn = get_connection(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) AS n FROM questions")
    total = cursor.fetchone()['n']
    cursor.execute("SELECT COALESCE(type,'essay') AS type, COUNT(*) AS n FROM questions GROUP BY type ORDER BY n DESC")
    by_type = cursor.fetchall()
    cursor.execute("SELECT institution, COUNT(*) AS n FROM questions WHERE institution IS NOT NULL AND institution != '' GROUP BY institution ORDER BY n DESC LIMIT 10")
    by_inst = cursor.fetchall()
    cursor.execute("SELECT subject, COUNT(*) AS n FROM questions WHERE subject IS NOT NULL AND subject != '' GROUP BY subject ORDER BY n DESC LIMIT 10")
    by_subj = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) AS n FROM questions WHERE source IS NULL OR source = ''")
    no_source = cursor.fetchone()['n']
    cursor.execute("SELECT COUNT(*) AS n FROM questions WHERE general_feedback IS NULL OR general_feedback = ''")
    no_fb = cursor.fetchone()['n']
    cursor.close(); conn.close()

    print(f"\n  Total questions     : {color_text(str(total), COLORS.GREEN, bold=True)}")
    print(f"  Missing source tag  : {no_source}")
    print(f"  Missing explanation : {no_fb}")
    print(f"\n  By type:")
    for r in by_type: print(f"    {r['type']:<12}: {r['n']}")
    print(f"\n  Top institutions:")
    for r in by_inst: print(f"    {(r['institution'] or '')[:40]:<40}: {r['n']}")
    print(f"\n  Top subjects:")
    for r in by_subj: print(f"    {(r['subject'] or '')[:40]:<40}: {r['n']}")


def bulk_rename_interactive():
    """Bulk-rename a field across matching questions."""

    # (display label, db column, kind)
    # kind: 'text' | 'number' | 'exam_type' | 'q_type'
    FIELDS = [
        ('institution',    'institution',   'text'),
        ('subject',        'subject',       'text'),
        ('paper',          'paper',         'text'),
        ('level',          'level',         'text'),
        ('group',          'group',         'text'),
        ('source',         'source',        'text'),
        ('exam_type',      'exam_type',     'exam_type'),
        ('marks',          'marks',         'number'),
        ('chapter',        'chapter',       'text'),
        ('syllabus_code',  'syllabus_code', 'text'),
        ('type',           'type',          'q_type'),
        ('question_date',  'question_date', 'text'),
    ]

    print()
    print_colored("  BULK RENAME FIELD", COLORS.CYAN, bold=True)
    print_colored("  " + "─" * 56, COLORS.CYAN)
    for i, (label, _col, kind) in enumerate(FIELDS, 1):
        hint = {
            'exam_type': ' (menu)',
            'q_type':    ' (menu)',
            'number':    ' (numeric)',
        }.get(kind, '')
        print(f"   {i:>2}. {label}{hint}")
    print("     0. Cancel")

    raw = input(color_text(f"\nChoose field (0-{len(FIELDS)}): ", COLORS.MAGENTA)).strip()
    if not raw.isdigit():
        return
    idx = int(raw)
    if idx == 0:
        return
    if not (1 <= idx <= len(FIELDS)):
        print_colored("[!] Invalid choice.", COLORS.RED)
        return

    label, column, kind = FIELDS[idx - 1]

    # Backtick reserved words
    col_expr = f"`{column}`" if column in ('group', 'type') else column

    # ---------- Show top existing values ----------
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(f"""
            SELECT {col_expr} AS v, COUNT(*) AS n
            FROM questions
            GROUP BY {col_expr}
            ORDER BY n DESC
            LIMIT 20
        """)
        distinct_rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if distinct_rows:
        print()
        print_colored(f"  Existing values of '{label}' (top 20):", COLORS.YELLOW)
        for i, r in enumerate(distinct_rows, 1):
            v = r['v'] if r['v'] is not None else '(null)'
            v_str = str(v)
            if len(v_str) > 48:
                v_str = v_str[:45] + '...'
            print(f"   {i:>2}. {v_str:<50}  {r['n']:>5} rows")
        print_colored("       (or type any value manually)", COLORS.WHITE)

    # ---------- Old value ----------
    print()
    print_colored("  Old value:", COLORS.WHITE)
    print("    • Type a number from the list above to pick that value")
    print("    • Type 'clear' to match NULL rows")
    print("    • Or type any value manually (exact match)")
    old_raw = input(color_text(f"  Old {label}: ", COLORS.MAGENTA)).strip()

    if old_raw == '':
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    if old_raw.isdigit() and distinct_rows and 1 <= int(old_raw) <= len(distinct_rows):
        old = distinct_rows[int(old_raw) - 1]['v']
    elif old_raw.lower() == 'clear':
        old = None
    else:
        old = old_raw

    # ---------- New value ----------
    print()
    if kind == 'exam_type':
        print_colored("  New exam type:", COLORS.WHITE)
        for i, (k, lbl) in enumerate(EXAM_TYPES, 1):
            print(f"   {i:>2}. {lbl}")
        et = input(color_text("  Choose (1-4): ", COLORS.MAGENTA)).strip()
        if not et.isdigit() or not (1 <= int(et) <= len(EXAM_TYPES)):
            print_colored("[!] Invalid.", COLORS.RED)
            return
        new = EXAM_TYPES[int(et) - 1][0]

    elif kind == 'q_type':
        opts = ['essay', 'multichoice', 'truefalse', 'matching']
        print_colored("  New type:", COLORS.WHITE)
        for i, t in enumerate(opts, 1):
            print(f"   {i:>2}. {t}")
        t = input(color_text("  Choose (1-4): ", COLORS.MAGENTA)).strip()
        if not t.isdigit() or not (1 <= int(t) <= 4):
            print_colored("[!] Invalid.", COLORS.RED)
            return
        new = opts[int(t) - 1]

    elif kind == 'number':
        n = input(color_text(f"  New {label} (number, or 'clear' for NULL): ", COLORS.MAGENTA)).strip()
        if n == '':
            print_colored("Cancelled.", COLORS.YELLOW)
            return
        if n.lower() == 'clear':
            new = None
        elif n.isdigit():
            new = int(n)
        else:
            print_colored("[!] Must be a number.", COLORS.RED)
            return

    else:  # text
        n = input(color_text(f"  New {label} (or 'clear' for NULL): ", COLORS.MAGENTA)).strip()
        if n == '':
            print_colored("Cancelled.", COLORS.YELLOW)
            return
        new = None if n.lower() == 'clear' else n

    # ---------- Confirm ----------
    # Count matching rows BEFORE update
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if old is None:
            cursor.execute(f"SELECT COUNT(*) FROM questions WHERE {col_expr} IS NULL")
        else:
            cursor.execute(f"SELECT COUNT(*) FROM questions WHERE {col_expr} = %s", (old,))
        match_count = cursor.fetchone()[0]
    finally:
        cursor.close()
        conn.close()

    print()
    print_colored("  Summary", COLORS.YELLOW, bold=True)
    print_colored("  " + "─" * 56, COLORS.YELLOW)
    print(f"   Field        : {label}")
    print(f"   Old value    : {old if old is not None else '(NULL)'}")
    print(f"   New value    : {new if new is not None else '(NULL)'}")
    print(f"   Rows matched : {match_count}")

    if match_count == 0:
        print_colored("\n  [i] No rows match. Nothing to do.", COLORS.YELLOW)
        return

    confirm = input(color_text("\n  Apply rename? (y/n): ", COLORS.MAGENTA)).strip().lower()
    if confirm != 'y':
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    # ---------- Execute ----------
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if old is None and new is None:
            print_colored("[i] Old and new are both NULL — nothing to do.", COLORS.YELLOW)
            return
        elif old is None:
            cursor.execute(f"UPDATE questions SET {col_expr} = %s WHERE {col_expr} IS NULL", (new,))
        elif new is None:
            cursor.execute(f"UPDATE questions SET {col_expr} = NULL WHERE {col_expr} = %s", (old,))
        else:
            cursor.execute(f"UPDATE questions SET {col_expr} = %s WHERE {col_expr} = %s", (new, old))
        conn.commit()
        updated = cursor.rowcount
        print_colored(f"\n[✓] Updated {updated} row(s).", COLORS.GREEN)
    except Exception as e:
        conn.rollback()
        print_colored(f"\n[!] Failed: {e}", COLORS.RED)
    finally:
        cursor.close()
        conn.close()
