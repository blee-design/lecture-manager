# File utils.py

import re
import os
import sys
from .constants import C
from .exceptions import (
    ConverterError, ParseError, ValidationError, IOError,
    InvalidFilterError,
)


# -------------------- LOGGING --------------------
def log(msg, level="INFO", verbose=False):
    if not verbose:
        return
    color = {
        "INIT": C.CYAN,
        "INFO": C.BLUE,
        "OK": C.GREEN,
        "WARN": C.YELLOW,
        "ERROR": C.RED,
        "SUMMARY": C.CYAN,
        "SUCCESS": C.MAGENTA + C.BOLD,
        "CONVERT": C.CYAN + C.BOLD
    }.get(level, "")
    print(f"{color}[{level}] {msg}{C.RESET}")


# -------------------- UTILITIES --------------------
CORRECT_PATTERNS = [r"\*", r"\[(correct|ok|right)\]"]

def strip_latex_blocks(text):
    """Only strip LaTeX blocks if the text actually contains LaTeX markers"""
    # Check if text contains any LaTeX markers before processing
    latex_markers = [r'\$\$', r'\$', r'\\\(', r'\\\[']

    has_latex = False
    for marker in latex_markers:
        if re.search(marker, text):
            has_latex = True
            break

    # Only process if LaTeX is actually present
    if not has_latex:
        return text

    # Original LaTeX pattern
    latex_pattern = r"(\$\$.*?\$\$|\$.*?\$|\\\(.*?\\\)|\\\[.*?\\\])"
    return re.sub(latex_pattern, lambda m: " " * len(m.group()), text, flags=re.DOTALL)



def is_correct_option(option_text, has_latex_in_question=False):
    """
    Determine if option is correct, with optional LaTeX processing

    Args:
        option_text: The option text to check
        has_latex_in_question: Whether the parent question contains LaTeX
                              (only process LaTeX if this is True)
    """
    # Only process LaTeX if the question contains LaTeX
    if has_latex_in_question:
        masked_text = strip_latex_blocks(option_text)
    else:
        masked_text = option_text  # Skip LaTeX processing entirely

    for pat in CORRECT_PATTERNS:
        if re.search(pat, masked_text, re.IGNORECASE):
            clean_text = re.sub(pat, "", option_text, flags=re.IGNORECASE).strip()
            return True, clean_text
    return False, option_text.strip()

def find_line_in_file(file_path, search_text):
    """Find the actual line number of text in the file"""
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            for i, line in enumerate(f, 1):
                # Clean line and remove BOM
                clean_line = line.replace('\ufeff', '').strip()
                # Look for the first 50 characters to match
                if search_text[:50] in clean_line:
                    return i
    except:
        pass
    return 1  # Default to line 1 if not found

def needs_latex_processing(question_text):
    """Check if a question contains LaTeX math blocks"""
    latex_patterns = [
        r'\$\$.*?\$\$',  # Display math
        r'\$.*?\$',      # Inline math
        r'\\\(.*?\\\)',  # Inline math
        r'\\\[.*?\\\]'   # Display math
    ]

    for pattern in latex_patterns:
        if re.search(pattern, question_text):
            return True
    return False

def validate_filter_pattern(filter_arg, max_question, strict=False):
    """
    Validate a filter pattern and return (include, exclude, errors, warnings).

    Supports:
        1,5,10           → include only these
        !5,!10           → include all except these
        1..10            → include range
        !1..10           → exclude range
        1..10,!5,!20..25 → include range minus these
        '..' or '...'    → both work as range operators

    strict=True → out-of-range numbers are errors (not warnings).
    """
    if not filter_arg or filter_arg.strip() == "":
        return set(), set(), [], []

    include = set()
    exclude = set()
    errors = []
    warnings = []

    filter_arg = filter_arg.strip()

    # Allow digits, commas, dots, spaces, and '!'
    _probe = filter_arg.replace('..', '').replace('...', '').replace('!', '')
    if not re.match(r'^[\d\s,.]+$', _probe):
        errors.append("Pattern contains invalid characters. "
                      "Only numbers, commas, '..' or '...', and '!' are allowed.")
        return include, exclude, errors, warnings

    parts = [p.strip() for p in filter_arg.split(',') if p.strip()]

    for part in parts:
        negate = part.startswith('!')
        if negate:
            part = part[1:].strip()
            if not part:
                continue
        target = exclude if negate else include

        # Normalise '...' → '..' for uniform parsing
        part_norm = part.replace('...', '..')

        if '..' in part_norm:
            if part_norm.count('..') > 1:
                errors.append(f"Multiple '..' in '{part}' — use one per range")
                continue

            range_parts = part_norm.split('..')
            if len(range_parts) != 2:
                errors.append(f"Invalid range format in '{part}'")
                continue

            start_str, end_str = range_parts[0].strip(), range_parts[1].strip()
            if not start_str.isdigit() or not end_str.isdigit():
                errors.append(f"Non-numeric values in range '{part}'")
                continue

            start, end = int(start_str), int(end_str)
            if start <= 0 or end <= 0:
                errors.append(f"Range bounds in '{part}' must be positive")
                continue
            if start > end:
                start, end = end, start
                warnings.append(f"Range '{part}' was reversed → {start}..{end}")

            if start > max_question:
                if strict:
                    errors.append(f"Range start {start} exceeds max {max_question}")
                else:
                    warnings.append(f"Range start {start} exceeds max {max_question}")
                continue
            if end > max_question:
                if strict:
                    errors.append(f"Range end {end} exceeds max {max_question}")
                else:
                    warnings.append(f"Range end {end} exceeds max {max_question}")
                end = max_question

            for num in range(start, end + 1):
                if 1 <= num <= max_question:
                    target.add(num)

        else:
            if not part.isdigit():
                errors.append(f"Invalid number '{part}' — must be positive integer")
                continue
            num = int(part)
            if num <= 0:
                errors.append(f"Invalid question number '{num}'")
                continue
            if num > max_question:
                if strict:
                    errors.append(f"Question {num} not found (max: {max_question})")
                else:
                    warnings.append(f"Question {num} not found (max: {max_question})")
                continue
            target.add(num)

    return include, exclude, errors, warnings

def normalize_text(t):
    return re.sub(r"\s+", " ", t.strip().lower())

def filter_questions(questions, filter_arg, verbose=False):
    """
    Filter questions by include/exclude pattern.

    A leading '!' excludes. Empty include set with non-empty exclude
    set means "all questions except these".
    """
    if not filter_arg or filter_arg.strip() == "":
        log(f"No filter specified, using all {len(questions)} questions",
            "INFO", verbose)
        return questions

    if not questions:
        print(f"{C.YELLOW}[WARNING] No questions to filter{C.RESET}")
        return questions

    max_question = max([q.get("question_no", 0) for q in questions])
    log(f"Parsing filter pattern: '{filter_arg}'", "INFO", verbose)
    log(f"Available questions: 1 to {max_question}", "INFO", verbose)

    include, exclude, errors, warnings = validate_filter_pattern(
        filter_arg, max_question, strict=True)

    if errors:
        print(f"\n{C.RED}Invalid filter pattern:{C.RESET}")
        for e in errors:
            print(f"  • {e}")
        print(f"\n{C.YELLOW}Available questions: 1 to {max_question}{C.RESET}")
        print(f"{C.YELLOW}Examples of valid patterns:{C.RESET}")
        print(f"  {C.GREEN}-q 1,5,10{C.RESET}             # include only these")
        print(f"  {C.GREEN}-q !5,!10{C.RESET}            # exclude these")
        print(f"  {C.GREEN}-q 1..10{C.RESET}             # include range")
        print(f"  {C.GREEN}-q 1..10,!5,!20..25{C.RESET}  # range minus exclusions")
        raise InvalidFilterError("\n".join(errors))

    if warnings and verbose:
        print(f"\n{C.YELLOW}[WARNING] Filter issues:{C.RESET}")
        for w in warnings:
            print(f"  • {w}")

    # Nothing to include or exclude → return as-is
    if not include and not exclude:
        print(f"{C.YELLOW}[WARNING] No valid selections — using all questions{C.RESET}")
        return questions

    # Apply inclusion then exclusion
    filtered = []
    for q in questions:
        q_no = q.get("question_no", 0)
        if include and q_no not in include:
            continue
        if q_no in exclude:
            continue
        filtered.append(q)

    # Summary
    mode = []
    if include: mode.append(f"include {len(include)}")
    if exclude: mode.append(f"exclude {len(exclude)}")
    log(f"\n{C.CYAN}Filter Summary:{C.RESET}", "SUMMARY", True)
    log(f"  Pattern: {filter_arg}", "INFO", True)
    log(f"  Mode   : {', '.join(mode) or 'none'}", "INFO", verbose)
    log(f"  Kept   : {len(filtered)} of {len(questions)}", "INFO", True)

    # Re-number
    for i, q in enumerate(filtered, 1):
        old_no = q.get("question_no", 0)
        q["question_no"] = i
        if verbose and old_no != i:
            log(f"  Renumbered: {old_no} → {i}", "INFO", verbose)

    return filtered

def format_passage_with_svg(passage_content):
    import re
    # Split into non-SVG and SVG parts
    parts = re.split(r'(<svg.*?</svg>)', passage_content, flags=re.DOTALL)
    formatted = []
    for part in parts:
        if part.startswith('<svg'):
            # keep SVG as-is
            formatted.append(part)
        else:
            # replace newlines with <br> for text parts
            formatted.append(part.replace('\n', '<br>'))
    return ''.join(formatted)

def format_passage_in_question(identifier, passage_content, question_text):
    """Format passage and question as: Reading Passage X:<br>passage<br><p>question</p>"""
    # Convert passage line breaks to <br>
    passage_with_br = passage_content.replace('\n', '<br>')
    # Build final string
    return f"Reading Passage {identifier}:<br>{passage_with_br}<p>{question_text}</p>"
