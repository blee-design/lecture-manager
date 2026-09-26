#!/usr/bin/env python3
"""
Convert old JSON question format (with options, pairs, hints) to the format
compatible with the current lecture-manager importer (v3.0.2+).

Handles: multichoice, matching, essay, truefalse.

What's new vs the old script:
  • Emits `question_no` (the importer expects it; `question_number` was silently ignored).
  • Emits `exam_type` (default: open).
  • For truefalse, emits `correct_answer` (the importer ignores options for TF).
  • Preserves `syllabus_code` and `notes` if present in the source.
  • Extracts a numeric syllabus code from `chapter` text like "… (04.02)".
  • Accepts `question_no` OR `question_number` from the source.

Usage:
    python convert_old_json.py old.json --output new.json
        [--date YYYY-MM-DD] [--institution STR] [--level STR] [--paper STR]
        [--exam-type open|internal|promotional|other]
        [--source STR]
        [--extract-subject]
        [--auto-detect] / [--no-auto-detect]
"""

import json
import os
import sys
import re
import argparse


# ============================================================
# Helpers
# ============================================================
_SYLLABUS_CODE_RE = re.compile(r'\b(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?(?:-\S+)?)\b')

# Detects a leading "Reading Passage <id>:<br>" prefix
_PASSAGE_PREFIX_RE = re.compile(
    r'^\s*Reading\s+Passage\s+([A-Za-z0-9_\-]+)\s*:\s*(?:<br\s*/?>\s*)?(.*)$',
    re.IGNORECASE | re.DOTALL,
)


def has_devanagari(text):
    """True if text contains Devanagari Unicode characters."""
    return bool(re.search(r'[\u0900-\u097F]', text))


def _classify_part(s):
    """Classify a text fragment as 'nep', 'eng', 'neutral', or 'empty'."""
    s = s.strip()
    if not s:
        return 'empty'
    dev = len(re.findall(r'[\u0900-\u097F]', s))
    lat = len(re.findall(r'[a-zA-Z]', s))
    total = dev + lat
    if total == 0:
        return 'neutral'
    if dev / total >= 0.5:
        return 'nep'
    if lat / total >= 0.5:
        return 'eng'
    return 'neutral'


def _smart_split_by_br(text):
    """
    Split text into (nepali, english) by finding the longest contiguous
    run of English-dominant parts when split by <br> or newline.

    This handles cases like:
        Nepali question<br>English translation<br>more Nepali data
    where a naive first-<br> split would put the Nepali data in the
    English field.
    """
    if '<br' in text:
        parts = re.split(r'<br\s*/?>', text)
        sep = '<br>'
    elif '\n' in text:
        parts = text.split('\n')
        sep = '\n'
    else:
        return None

    if len(parts) < 2:
        return None

    classes = [_classify_part(p) for p in parts]

    # Find the longest contiguous run of 'eng'
    best_start = best_end = -1
    cur_start = -1
    for i, c in enumerate(classes):
        if c == 'eng':
            if cur_start == -1:
                cur_start = i
        else:
            if cur_start != -1:
                if (i - cur_start) > (best_end - best_start):
                    best_start, best_end = cur_start, i
                cur_start = -1
    if cur_start != -1:
        if (len(classes) - cur_start) > (best_end - best_start):
            best_start, best_end = cur_start, len(classes)

    if best_start == -1:
        return None  # no English run found

    nepali_parts = parts[:best_start] + parts[best_end:]
    english_parts = parts[best_start:best_end]

    nep = sep.join(nepali_parts).strip()
    eng = sep.join(english_parts).strip()
    if not nep and not eng:
        return None
    return nep, eng


def extract_passage(text):
    """
    If `text` starts with 'Reading Passage <id>:<br>…', extract the
    passage and the question. Returns (identifier, passage, question).
    If no passage is detected, returns (None, None, text).

    The question is found by looking for:
      1. A trailing <p>…</p> block, or
      2. A </table> boundary, or
      3. The last <br> if the trailing part ends with '?'.
    """
    if not text:
        return None, None, text
    m = _PASSAGE_PREFIX_RE.match(text)
    if not m:
        return None, None, text

    identifier = m.group(1)
    rest = m.group(2).strip()
    if not rest:
        return identifier, '', ''

    # 1. Trailing <p>…</p>
    qm = re.search(r'<p>(.*?)</p>\s*$', rest, re.DOTALL | re.IGNORECASE)
    if qm:
        question = qm.group(1).strip()
        passage = rest[:qm.start()].strip()
        return identifier, passage, question

    # 2. Boundary at last </table>
    tm = re.search(r'</table>\s*(.*)$', rest, re.DOTALL | re.IGNORECASE)
    if tm and tm.group(1).strip():
        end = tm.start() + len('</table>')
        passage = rest[:end].strip()
        question = tm.group(1).strip()
        return identifier, passage, question

    # 3. Last <br> followed by a question mark
    parts = re.split(r'<br\s*/?>', rest)
    if len(parts) >= 2 and parts[-1].strip().endswith('?'):
        passage = '<br>'.join(parts[:-1]).strip()
        question = parts[-1].strip()
        return identifier, passage, question

    # Fallback: entire rest is the passage, no question text found
    return identifier, rest, ''


def split_nepali_english(text, auto_detect=True):
    """
    Split text into (nepali, english).

    Strategy, in order:
      1. If auto_detect is on, use language-aware <br> splitting —
         find the longest contiguous run of English-only parts.
         Handles cases like:
             Nepali question<br>English translation<br>more Nepali data
      2. Fall back to first <br> / newline split.
      3. Trailing parentheses: "Nepali (English)".
      4. Devanagari-presence heuristic (if auto_detect).
    """
    if not text:
        return "", ""

    # 1. Smart split (language-aware) — only when auto_detect is on
    if auto_detect:
        smart = _smart_split_by_br(text)
        if smart:
            return smart

    # 2. Traditional first-<br> split
    for sep in ('<br>', '<br/>', '<br />', '\n'):
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()

    # 3. Trailing parentheses
    m = re.search(r'^(.*?)\s*\(([^)]+)\)\s*$', text, re.DOTALL)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # 4. Devanagari heuristic
    if auto_detect:
        if not has_devanagari(text):
            return "", text
        if not re.search(r'[a-zA-Z]', text):
            return text, ""
        words = text.split()
        eng_words = []
        for w in reversed(words):
            if re.search(r'[a-zA-Z]', w) and not has_devanagari(w):
                eng_words.append(w)
            else:
                break
        if eng_words:
            eng = ' '.join(reversed(eng_words))
            nep = ' '.join(words[:-len(eng_words)])
            return nep.strip(), eng.strip()
        return text, ""

    return text, ""


def extract_subject_from_group(group):
    """Pull subject text from a group string like 'Physics (P1-B2.1)'."""
    if not group:
        return ""
    if '(' in group:
        return group.split('(', 1)[0].strip().rstrip(',')
    return group.strip()


def extract_syllabus_code(text):
    """Find a code like '04' or '04.02' or '04.02.01' or '04.02-1' inside text."""
    if not text:
        return ''
    m = _SYLLABUS_CODE_RE.search(str(text))
    return m.group(1) if m else ''


def pad_question_number(qno):
    """Return a 2-digit string for numeric input, else the raw trimmed string."""
    if qno is None:
        return '01'
    s = str(qno).strip()
    if s.isdigit():
        return s.zfill(2)
    return s


# ============================================================
# Field converters
# ============================================================
def convert_options(raw_options, q_type):
    """
    Normalise options to { text, fraction, feedback, correct } (all as the
    importer expects). Preserves fraction if the source provides it; otherwise
    derives it from `correct`.
    """
    out = []
    if not raw_options:
        return out
    for idx, opt in enumerate(raw_options):
        # Source might use: correct (bool), fraction (num), or both
        is_correct = opt.get('correct')
        fraction = opt.get('fraction')
        if fraction is None:
            fraction = 100.0 if is_correct else 0.0
        out.append({
            'text': opt.get('text', ''),
            'fraction': float(fraction),
            'feedback': opt.get('feedback', ''),
            'correct': bool(is_correct) if is_correct is not None else (float(fraction) > 0),
            'display_order': idx,
        })
    return out


def derive_tf_correct_answer(raw_options, fallback=True):
    """
    Given a TF question's options, decide the boolean correct_answer.
    """
    for opt in raw_options or []:
        text = (opt.get('text') or '').strip().lower()
        if opt.get('correct') or (opt.get('fraction') and float(opt.get('fraction')) > 0):
            if text == 'true':
                return True
            if text == 'false':
                return False
    return fallback


def convert_pairs(raw_pairs):
    """Return pairs in the { subquestion, answer } shape the importer expects."""
    out = []
    if not raw_pairs:
        return out
    for idx, pair in enumerate(raw_pairs):
        out.append({
            'subquestion': pair.get('subquestion', ''),
            'answer': pair.get('answer', ''),
            'display_order': idx,
        })
    return out


def convert_hints(raw_hints):
    """Return hints in the { text, clear_incorrect, show_num_correct } shape."""
    out = []
    if not raw_hints:
        return out
    for hint in raw_hints:
        out.append({
            'text': hint.get('text', ''),
            'clear_incorrect': bool(hint.get('clear_incorrect', False)),
            'show_num_correct': bool(hint.get('show_num_correct', False)),
        })
    return out


# ============================================================
# Main conversion
# ============================================================
def convert_old_json(input_file, output_file, defaults,
                     extract_subject=False, source=None, auto_detect=True):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("Error: input JSON must be a list of question objects.")
        sys.exit(1)

    new_data = []
    type_counts = {'essay': 0, 'multichoice': 0, 'truefalse': 0, 'matching': 0, 'other': 0}
    tf_fixed = 0
    code_extracted = 0

    for item in data:
        # ---------- Question number (accept either key) ----------
        raw_qno = item.get('question_no')
        if raw_qno is None:
            raw_qno = item.get('question_number')
        question_no = pad_question_number(raw_qno)

        # ---------- Passage extraction (before text splitting) ----------
        raw_text = item.get('text', '') or ''
        passage_id_hint, passage_content, cleaned_text = extract_passage(raw_text)
        # If a passage was found, use the cleaned question text for splitting
        effective_text = cleaned_text if passage_id_hint else raw_text

        # ---------- Text ----------
        src_nep = (item.get('nepali_transcription') or '').strip()
        src_eng = (item.get('english_transcription') or '').strip()
        if src_nep or src_eng:
            nepali, english = src_nep, src_eng
        else:
            nepali, english = split_nepali_english(effective_text, auto_detect)

        # ---------- Type ----------
        qtype = (item.get('type') or 'essay').lower()
        if qtype not in ('essay', 'multichoice', 'truefalse', 'matching'):
            type_counts['other'] += 1
        else:
            type_counts[qtype] += 1

        # ---------- Fields per type ----------
        raw_options = item.get('options', []) or []
        options = []
        pairs = []
        hints = convert_hints(item.get('hints', []))
        correct_answer = None

        if qtype == 'multichoice':
            options = convert_options(raw_options, qtype)
        elif qtype == 'truefalse':
            # The importer ignores `options` for TF — it reads `correct_answer`.
            # Preserve options too (harmless), but always emit correct_answer.
            if 'correct_answer' in item and isinstance(item['correct_answer'], bool):
                correct_answer = item['correct_answer']
            else:
                correct_answer = derive_tf_correct_answer(raw_options, fallback=True)
                tf_fixed += 1
            options = convert_options(raw_options, qtype)
        elif qtype == 'matching':
            pairs = convert_pairs(item.get('pairs', []) or [])
        # essay: no options/pairs

        # ---------- Chapter / syllabus code ----------
        raw_chapter = item.get('chapter') or ''
        syllabus_code = (item.get('syllabus_code') or '').strip()
        if not syllabus_code and raw_chapter:
            extracted = extract_syllabus_code(raw_chapter)
            if extracted:
                syllabus_code = extracted
                code_extracted += 1

        # ---------- Subject ----------
        if extract_subject:
            subject = extract_subject_from_group(item.get('group') or '')
        else:
            subject = item.get('subject') or ''

        # ---------- Marks: prefer `marks`, fall back to `grade` ----------
        raw_marks = item.get('marks')
        if raw_marks is None:
            raw_marks = item.get('grade', 1)

        # ---------- exam_type ----------
        et = (item.get('exam_type') or defaults.get('exam_type') or 'open').lower()
        if et not in ('open', 'internal', 'promotional', 'other'):
            et = 'other'

        # ---------- Build the new question ----------
        new_q = {
            # --- Identity ---
            'question_no': question_no,
            # Also include the legacy key so older tools keep working
            'question_number': question_no,

            # --- Text ---
            'nepali_transcription': nepali,
            'english_transcription': english,

            # --- Type-specific payload ---
            'type': qtype,
            'options': options,
            'pairs': pairs,
            'hints': hints,

            # --- TF fix ---
            'correct_answer': correct_answer if qtype == 'truefalse' else None,

            # --- Feedback / grading ---
            'general_feedback': item.get('general_feedback', ''),
            'grader_info': item.get('grader_info', ''),
            'marks': raw_marks,
            'grade': 1,                              # Moodle defaultgrade; not used here
            'lines': item.get('lines', 15),
            'response_lines': item.get('lines', 15),
            'penalty': item.get('penalty', 0),
            'fraction_correct': item.get('fraction_correct', 100),
            'fraction_wrong': item.get('fraction_wrong', -20),
            'shuffle_answers': item.get('shuffle_answers', True),
            'show_num_correct': item.get('show_num_correct', False),
            'correct_feedback': item.get('correct_feedback', ''),
            'partially_correct_feedback': item.get('partially_correct_feedback', ''),
            'incorrect_feedback': item.get('incorrect_feedback', ''),
            'feedback_true': item.get('feedback_true', ''),
            'feedback_false': item.get('feedback_false', ''),

            # --- Attachment defaults (essay only, harmless otherwise) ---
            'attachments': item.get('attachments', 0),
            'filetypes': item.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg'),
            'maxbytes': item.get('maxbytes', 2097152),

            # --- Metadata ---
            'group': item.get('group') or '',
            'notes': item.get('notes') or '',
            'chapter': raw_chapter,
            'syllabus_code': syllabus_code,
            'source': item.get('source') or source or os.path.basename(input_file),
            'exam_type': et,

            # --- Defaults applied to every question ---
            'question_date': item.get('question_date') or defaults.get('date', ''),
            'institution': item.get('institution') or defaults.get('institution', ''),
            'level': item.get('level') or defaults.get('level', ''),
            'paper': item.get('paper') or defaults.get('paper', ''),
            'subject': subject,
        }

        # --- Passage link (only when a passage was extracted) ---
        if passage_content:
            new_q['_passage_text'] = passage_content

        # Drop None-only keys we don't want to persist
        if new_q['correct_answer'] is None:
            del new_q['correct_answer']

        new_data.append(new_q)

    # ---------- Write output ----------
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)

    # ---------- Report ----------
    n_passages = sum(1 for q in new_data if q.get('_passage_text'))
    unique_passages = len({q['_passage_text'] for q in new_data if q.get('_passage_text')})

    print(f"✅ Converted {len(new_data)} questions → {output_file}")
    print(f"   Types: essay={type_counts['essay']}  mcq={type_counts['multichoice']}  "
          f"tf={type_counts['truefalse']}  matching={type_counts['matching']}"
          + (f"  other={type_counts['other']}" if type_counts['other'] else ""))
    if tf_fixed:
        print(f"   ℹ️  Derived `correct_answer` for {tf_fixed} True/False question(s)")
    if code_extracted:
        print(f"   ℹ️  Extracted syllabus code from `chapter` text for {code_extracted} question(s)")
    if unique_passages:
        print(f"   ℹ️  Extracted {unique_passages} unique passage(s) linked to "
              f"{n_passages} question(s)")


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Convert old JSON question format to the current importer format."
    )
    parser.add_argument('input', help='Input JSON file (old format)')
    parser.add_argument('-o', '--output', help='Output JSON file (new format)')
    parser.add_argument('--date', help='Default question_date (YYYY-MM-DD)')
    parser.add_argument('--institution', help='Default institution')
    parser.add_argument('--level', help='Default level')
    parser.add_argument('--paper', help='Default paper (Paper I / Paper II / Paper III / Pretest)')
    parser.add_argument('--exam-type', dest='exam_type',
                        choices=['open', 'internal', 'promotional', 'other'],
                        default='open', help='Default exam type (default: open)')
    parser.add_argument('--extract-subject', action='store_true',
                        help='Extract subject text from the group field')
    parser.add_argument('--source', help='Source name (default: input filename)')
    parser.add_argument('--auto-detect', action='store_true', default=True,
                        help='Enable automatic Nepali/English detection (default)')
    parser.add_argument('--no-auto-detect', action='store_false', dest='auto_detect',
                        help='Disable automatic detection (only use <br> / parens splits)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found.")
        sys.exit(1)

    if args.output:
        output_file = args.output
    else:
        base, _ = os.path.splitext(args.input)
        output_file = f"{base}_converted.json"

    defaults = {}
    defaults['date']        = args.date        or input("Default Date (YYYY-MM-DD): ").strip()
    defaults['institution'] = args.institution or input("Default Institution: ").strip()
    defaults['level']       = args.level       or input("Default Level: ").strip()
    defaults['paper']       = args.paper       or input("Default Paper (Paper I / Paper II / Paper III / Pretest): ").strip()
    defaults['exam_type']   = args.exam_type

    print()
    print("Defaults to apply to ALL questions:")
    print(f"   Date        : {defaults['date']}")
    print(f"   Institution : {defaults['institution']}")
    print(f"   Level       : {defaults['level']}")
    print(f"   Paper       : {defaults['paper']}")
    print(f"   Exam type   : {defaults['exam_type']}")
    if args.extract_subject:
        print("   Subject     : extracted from 'group' field")
    else:
        print("   Subject     : left empty (update later)")
    print(f"   Auto-detect : {'ON' if args.auto_detect else 'OFF'}")

    if input("\nProceed? (y/n): ").strip().lower() != 'y':
        print("Aborted.")
        sys.exit(0)

    convert_old_json(
        args.input, output_file, defaults,
        extract_subject=args.extract_subject,
        source=args.source,
        auto_detect=args.auto_detect,
    )


if __name__ == "__main__":
    main()
