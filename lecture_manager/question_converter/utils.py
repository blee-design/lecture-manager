# File utils.py

import re
import os
import sys
from .constants import C
from .exceptions import ConverterError, ParseError, ValidationError, IOError


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

def validate_filter_pattern(filter_arg, max_question, strict=False):
    """Validate filter pattern and return parsed numbers with error messages
    If strict=True, out-of-range numbers are treated as errors (not warnings)"""
    if not filter_arg or filter_arg.strip() == "":
        return set(), [], []
    
    selected_numbers = set()
    errors = []
    warnings = []
    
    # Clean the filter argument
    filter_arg = filter_arg.strip()
    
    # Basic validation - only allow digits, commas, dots, and spaces
    if not re.match(r'^[\d\s,.]+$', filter_arg.replace('..', '')):
        errors.append(f"Pattern contains invalid characters. Only numbers, commas, and '..' are allowed.")
        return selected_numbers, errors, warnings
    
    parts = [p.strip() for p in filter_arg.split(',') if p.strip()]
    
    for part in parts:
        if '..' in part:
            # Check for multiple '..' in one part
            if part.count('..') > 1:
                errors.append(f"Multiple '..' in '{part}' - use only one '..' per range")
                continue
                
            range_parts = part.split('..')
            if len(range_parts) != 2:
                errors.append(f"Invalid range format in '{part}' - must be 'start..end'")
                continue
            
            start_str, end_str = range_parts[0].strip(), range_parts[1].strip()
            
            # Validate start and end are numbers
            if not start_str.isdigit() or not end_str.isdigit():
                errors.append(f"Non-numeric values in range '{part}'")
                continue
            
            start, end = int(start_str), int(end_str)
            
            # Validate range bounds
            if start <= 0:
                errors.append(f"Range start in '{part}' must be positive (got {start})")
                continue
            if end <= 0:
                errors.append(f"Range end in '{part}' must be positive (got {end})")
                continue
            
            # Check if range is reversed
            if start > end:
                # Auto-correct but warn
                start, end = end, start
                warnings.append(f"Range '{part}' was reversed, auto-corrected to {start}..{end}")
            
            # Check if range is within available questions - TREAT AS ERROR IN STRICT MODE
            if start > max_question:
                if strict:
                    errors.append(f"Range start {start} exceeds maximum available question {max_question}")
                else:
                    warnings.append(f"Range start {start} exceeds maximum available question {max_question}")
                    start = max_question + 1  # Make range empty
            elif end > max_question:
                if strict:
                    errors.append(f"Range end {end} exceeds maximum available question {max_question}")
                else:
                    warnings.append(f"Range end {end} exceeds maximum available question {max_question}")
                    end = max_question
            
            # Only add valid numbers if no errors in strict mode
            if not (strict and (start > max_question or end > max_question)):
                if start <= end:
                    for num in range(start, end + 1):
                        if 1 <= num <= max_question:
                            selected_numbers.add(num)
        else:
            # Handle individual number
            if not part.isdigit():
                errors.append(f"Invalid number '{part}' - must be a positive integer")
                continue
            
            num = int(part)
            
            if num <= 0:
                errors.append(f"Invalid question number '{num}' - must be positive")
                continue
            
            # Check if number exists - TREAT AS ERROR IN STRICT MODE
            if num > max_question:
                if strict:
                    errors.append(f"Question {num} not found (maximum available: {max_question})")
                else:
                    warnings.append(f"Question {num} not found (maximum available: {max_question})")
            else:
                selected_numbers.add(num)
    
    return selected_numbers, errors, warnings

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

def normalize_text(t):
    return re.sub(r"\s+", " ", t.strip().lower())

def filter_questions(questions, filter_arg, verbose=False):
    """Filter questions based on selection criteria - with comprehensive error handling
    Throws error if questions are out of range"""
    if not filter_arg or filter_arg.strip() == "":
        log(f"No filter specified, using all {len(questions)} questions", "INFO", verbose)
        return questions

    # Get the maximum question number
    if not questions:
        print(f"{C.YELLOW}[WARNING] No questions to filter{C.RESET}")
        return questions
    
    max_question = max([q.get("question_no", 0) for q in questions])
    log(f"Parsing filter pattern: '{filter_arg}'", "INFO", verbose)
    log(f"Available questions: 1 to {max_question}", "INFO", verbose)

    # Use STRICT mode - out-of-range numbers are ERRORS
    selected_numbers, errors, warnings = validate_filter_pattern(filter_arg, max_question, strict=True)

    # Display errors if any - THESE ARE NOW FATAL
    if errors:
        raise InvalidFilterError("\n".join(errors))
        for error in errors:
            print(f"  • {error}")
        print(f"\n{C.YELLOW}Available questions: 1 to {max_question}{C.RESET}")
        print(f"{C.YELLOW}Examples of valid patterns:{C.RESET}")
        print(f"  {C.GREEN}-q 1,5,10{C.RESET}           # Individual questions")
        print(f"  {C.GREEN}-q 5..10{C.RESET}            # Range (inclusive)")
        print(f"  {C.GREEN}-q 1,5..10,15,20..25{C.RESET} # Mixed pattern")
        print(f"\n{C.YELLOW}Fix: Remove out-of-range numbers from your filter pattern.{C.RESET}")

    # If no valid numbers selected
    if not selected_numbers:
        print(f"{C.YELLOW}[WARNING] No valid question numbers selected, using all questions{C.RESET}")
        return questions

    # Display warnings if any (these are non-fatal like reversed ranges)
    if warnings and verbose:
        print(f"\n{C.YELLOW}[WARNING] Filter adjustments:{C.RESET}")
        for warning in warnings:
            print(f"  • {warning}")

    # Filter questions
    filtered = []
    for q in questions:
        q_no = q.get("question_no", 0)
        if q_no in selected_numbers:
            filtered.append(q)

    # Sort selected numbers for consistent display
    sorted_numbers = sorted(selected_numbers)
    
    # Show which numbers were actually found vs requested
    found_nums = [q.get("question_no", 0) for q in filtered]
    not_found = [n for n in selected_numbers if n not in found_nums]
    
    if not_found:
        print(f"{C.YELLOW}[WARNING] Some questions not found in input:{C.RESET}")
        print(f"  Missing: {sorted(not_found)}")
        print(f"  Available: 1 to {max_question}")

    # Summary
    log(f"\n{C.CYAN}Filter Summary:{C.RESET}", "SUMMARY", True)
    log(f"  Requested pattern: {filter_arg}", "INFO", True)
    log(f"  Parsed numbers: {sorted_numbers}", "INFO", verbose)
    log(f"  Found: {len(filtered)} of {len(selected_numbers)} requested questions", "INFO", True)
    
    if verbose and filtered:
        # Show which questions were selected
        print(f"\n{C.CYAN}Selected Questions:{C.RESET}")
        for q in filtered[:10]:  # Show first 10 only
            q_preview = q.get('text', '')[:50] + "..." if len(q.get('text', '')) > 50 else q.get('text', '')
            print(f"  Question {q.get('question_no', '?'):3d}: {q_preview}")
        if len(filtered) > 10:
            print(f"  ... and {len(filtered) - 10} more questions")

    # Re-number filtered questions sequentially
    for i, q in enumerate(filtered, 1):
        old_no = q.get("question_no", 0)
        # Store original number if not already stored
        if "original_question_no" not in q:
            q["original_question_no"] = old_no
        q["question_no"] = i
        if verbose and old_no != i:
            log(f"  Renumbered: Question {old_no} → {i}", "INFO", verbose)

    return filtered

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
    """Validate filter pattern and return parsed numbers with error messages
    If strict=True, out-of-range numbers are treated as errors (not warnings)"""
    if not filter_arg or filter_arg.strip() == "":
        return set(), [], []
    
    selected_numbers = set()
    errors = []
    warnings = []
    
    # Clean the filter argument
    filter_arg = filter_arg.strip()
    
    # Basic validation - only allow digits, commas, dots, and spaces
    if not re.match(r'^[\d\s,.]+$', filter_arg.replace('..', '')):
        errors.append(f"Pattern contains invalid characters. Only numbers, commas, and '..' are allowed.")
        return selected_numbers, errors, warnings
    
    parts = [p.strip() for p in filter_arg.split(',') if p.strip()]
    
    for part in parts:
        if '..' in part:
            # Check for multiple '..' in one part
            if part.count('..') > 1:
                errors.append(f"Multiple '..' in '{part}' - use only one '..' per range")
                continue
                
            range_parts = part.split('..')
            if len(range_parts) != 2:
                errors.append(f"Invalid range format in '{part}' - must be 'start..end'")
                continue
            
            start_str, end_str = range_parts[0].strip(), range_parts[1].strip()
            
            # Validate start and end are numbers
            if not start_str.isdigit() or not end_str.isdigit():
                errors.append(f"Non-numeric values in range '{part}'")
                continue
            
            start, end = int(start_str), int(end_str)
            
            # Validate range bounds
            if start <= 0:
                errors.append(f"Range start in '{part}' must be positive (got {start})")
                continue
            if end <= 0:
                errors.append(f"Range end in '{part}' must be positive (got {end})")
                continue
            
            # Check if range is reversed
            if start > end:
                # Auto-correct but warn
                start, end = end, start
                warnings.append(f"Range '{part}' was reversed, auto-corrected to {start}..{end}")
            
            # Check if range is within available questions - TREAT AS ERROR IN STRICT MODE
            if start > max_question:
                if strict:
                    errors.append(f"Range start {start} exceeds maximum available question {max_question}")
                else:
                    warnings.append(f"Range start {start} exceeds maximum available question {max_question}")
                    start = max_question + 1  # Make range empty
            elif end > max_question:
                if strict:
                    errors.append(f"Range end {end} exceeds maximum available question {max_question}")
                else:
                    warnings.append(f"Range end {end} exceeds maximum available question {max_question}")
                    end = max_question
            
            # Only add valid numbers if no errors in strict mode
            if not (strict and (start > max_question or end > max_question)):
                if start <= end:
                    for num in range(start, end + 1):
                        if 1 <= num <= max_question:
                            selected_numbers.add(num)
        else:
            # Handle individual number
            if not part.isdigit():
                errors.append(f"Invalid number '{part}' - must be a positive integer")
                continue
            
            num = int(part)
            
            if num <= 0:
                errors.append(f"Invalid question number '{num}' - must be positive")
                continue
            
            # Check if number exists - TREAT AS ERROR IN STRICT MODE
            if num > max_question:
                if strict:
                    errors.append(f"Question {num} not found (maximum available: {max_question})")
                else:
                    warnings.append(f"Question {num} not found (maximum available: {max_question})")
            else:
                selected_numbers.add(num)
    
    return selected_numbers, errors, warnings

def filter_questions(questions, filter_arg, verbose=False):
    """Filter questions based on selection criteria - with comprehensive error handling"""
    if not filter_arg or filter_arg.strip() == "":
        log(f"No filter specified, using all {len(questions)} questions", "INFO", verbose)
        return questions

    # Get the maximum question number
    if not questions:
        print(f"{C.YELLOW}[WARNING] No questions to filter{C.RESET}")
        return questions
    
    max_question = max([q.get("question_no", 0) for q in questions])
    log(f"Parsing filter pattern: '{filter_arg}'", "INFO", verbose)
    log(f"Available questions: 1 to {max_question}", "INFO", verbose)

    # Use the new validation function with strict mode
    selected_numbers, errors, warnings = validate_filter_pattern(filter_arg, max_question, strict=True)

    # Display errors if any
    if errors:
        raise InvalidFilterError("\n".join(errors))
        for error in errors:
            print(f"  • {error}")
        print(f"\n{C.YELLOW}Available questions: 1 to {max_question}{C.RESET}")
        print(f"{C.YELLOW}Examples of valid patterns:{C.RESET}")
        print(f"  {C.GREEN}-q 1,5,10{C.RESET}           # Individual questions")
        print(f"  {C.GREEN}-q 5..10{C.RESET}            # Range (inclusive)")
        print(f"  {C.GREEN}-q 1,5..10,15,20..25{C.RESET} # Mixed pattern")
        print(f"\n{C.YELLOW}Note:{C.RESET} Question numbers must exist in your input file.")
        # Don't exit, just return all questions as a safety measure
        return questions

    # If no valid numbers selected
    if not selected_numbers:
        print(f"{C.YELLOW}[WARNING] No valid question numbers selected, using all questions{C.RESET}")
        return questions

    # Display warnings if any
    if warnings and verbose:
        print(f"\n{C.YELLOW}[WARNING] Filter issues:{C.RESET}")
        for warning in warnings:
            print(f"  • {warning}")

    # Filter questions
    filtered = []
    for q in questions:
        q_no = q.get("question_no", 0)
        if q_no in selected_numbers:
            filtered.append(q)

    # Sort selected numbers for consistent display
    sorted_numbers = sorted(selected_numbers)
    
    # Show which numbers were actually found vs requested
    found_nums = [q.get("question_no", 0) for q in filtered]
    not_found = [n for n in selected_numbers if n not in found_nums]
    
    if not_found:
        print(f"{C.YELLOW}[WARNING] Some questions not found in input:{C.RESET}")
        print(f"  Missing: {sorted(not_found)}")
        print(f"  Available: 1 to {max_question}")

    # Summary
    log(f"\n{C.CYAN}Filter Summary:{C.RESET}", "SUMMARY", True)
    log(f"  Requested pattern: {filter_arg}", "INFO", True)
    log(f"  Parsed numbers: {sorted_numbers}", "INFO", verbose)
    log(f"  Found: {len(filtered)} of {len(selected_numbers)} requested questions", "INFO", True)
    
    if verbose and filtered:
        # Show which questions were selected
        print(f"\n{C.CYAN}Selected Questions:{C.RESET}")
        for q in filtered[:10]:  # Show first 10 only
            q_preview = q.get('text', '')[:50] + "..." if len(q.get('text', '')) > 50 else q.get('text', '')
            print(f"  Question {q.get('question_no', '?'):3d}: {q_preview}")
        if len(filtered) > 10:
            print(f"  ... and {len(filtered) - 10} more questions")

    # Re-number filtered questions sequentially
    for i, q in enumerate(filtered, 1):
        old_no = q.get("question_no", 0)
        q["question_no"] = i
        if verbose and old_no != i:
            log(f"  Renumbered: Question {old_no} → {i}", "INFO", verbose)

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
