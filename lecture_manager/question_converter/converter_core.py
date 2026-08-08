# File converter_core.py

#!/usr/bin/env python3
"""Core conversion logic separated from CLI interface"""

import sys
import os
from .constants import C
from .utils import log, filter_questions, validate_filter_pattern
from .text_parser import parse_text_file
from .json_handler import json_to_questions, create_json_output
from .xml_handler import xml_to_questions, create_moodle_xml
from .html_output import create_html_output
from .text_output import create_text_output
from .exam_output import create_exam_html, parse_time_argument
from .exceptions import ConverterError, ParseError, ValidationError, IOError

# -------------------- SUCCESS MESSAGE --------------------
def print_success_message(questions, input_file, output_file, input_format, output_format, bypass_used, skipped_lines=0, verbose=False, shuffle_applied=False):
    """Print attractive success message at the end"""
    print("\n" + "="*70)
    print(f"{C.MAGENTA}{C.BOLD}✨ CONVERSION SUCCESSFULLY COMPLETED! ✨{C.RESET}")
    print("="*70)

    # Count question types and calculate total marks
    mcq_count = sum(1 for q in questions if q["type"] == "multichoice")
    essay_count = sum(1 for q in questions if q["type"] == "essay")
    truefalse_count = sum(1 for q in questions if q["type"] == "truefalse")
    matching_count = sum(1 for q in questions if q["type"] == "matching")
    total_marks = sum(q.get("grade", 1) for q in questions)

    print(f"{C.CYAN}📊 Conversion Summary:{C.RESET}")
    print(f"   • Input Format:  {input_format.upper()}")
    print(f"   • Output Format: {output_format.upper()}")
    print(f"   • Input File:    {input_file}")
    print(f"   • Output File:   {output_file}")
    print(f"   • Total Questions: {len(questions)}")
    print(f"   • Multiple Choice: {mcq_count}")
    print(f"   • Essay Questions: {essay_count}")
    print(f"   • True/False:      {truefalse_count}")
    print(f"   • Matching:        {matching_count}")
    print(f"   • Total Marks:     {total_marks}")
    
    # Show shuffling info
    if shuffle_applied:
        print(f"   • Questions Shuffled: Yes (all {len(questions)} questions)")
        changed_positions = 0
        position_map = []
        for q in questions:
            original_no = q.get("original_question_no", q.get("question_no", 0))
            current_no = q.get("question_no", 0)
            if original_no != current_no:
                changed_positions += 1
                position_map.append((original_no, current_no))
        if verbose:
            if changed_positions < len(questions):
                print(f"        - {changed_positions} questions changed position")
                print(f"        - {len(questions) - changed_positions} remained in same position (random chance)")
            if position_map and len(position_map) <= 10:
                print(f"\n{C.CYAN}Sample position changes:{C.RESET}")
                for original, current in position_map[:5]:
                    print(f"        Question {original} → Position {current}")
                if len(position_map) > 5:
                    print(f"        ... and {len(position_map) - 5} more changes")
    else:
        shuffled_count = 0
        for q in questions:
            original_no = q.get("original_question_no", q.get("question_no", 0))
            current_no = q.get("question_no", 0)
            if original_no != current_no:
                shuffled_count += 1
        if shuffled_count > 0:
            print(f"   • Questions Previously Shuffled: Yes ({shuffled_count} questions in different positions)")
    
    # Show detailed grading breakdown
    print(f"\n{C.CYAN}📝 Detailed Grading Breakdown:{C.RESET}")
    from collections import defaultdict
    mcq_grades = defaultdict(int)
    essay_grades = defaultdict(int)
    truefalse_grades = defaultdict(int)
    matching_grades = defaultdict(int)
    for q in questions:
        grade = q.get("grade", 1)
        q_type = q["type"]
        if q_type == "multichoice":
            mcq_grades[grade] += 1
        elif q_type == "essay":
            essay_grades[grade] += 1
        elif q_type == "truefalse":
            truefalse_grades[grade] += 1
        elif q_type == "matching":
            matching_grades[grade] += 1

    if mcq_grades:
        print(f"   • MCQ Questions ({mcq_count} total):")
        for grade, count in sorted(mcq_grades.items()):
            print(f"     - {count} question{'s' if count > 1 else ''} worth {grade} mark{'s' if grade != 1 else ''} each")
    if essay_grades:
        print(f"   • Essay Questions ({essay_count} total):")
        for grade, count in sorted(essay_grades.items()):
            print(f"     - {count} question{'s' if count > 1 else ''} worth {grade} mark{'s' if grade != 1 else ''} each")
    if truefalse_grades:
        print(f"   • True/False Questions ({truefalse_count} total):")
        for grade, count in sorted(truefalse_grades.items()):
            print(f"     - {count} question{'s' if count > 1 else ''} worth {grade} mark{'s' if grade != 1 else ''} each")
    if matching_grades:
        print(f"   • Matching Questions ({matching_count} total):")
        for grade, count in sorted(matching_grades.items()):
            print(f"     - {count} question{'s' if count > 1 else ''} worth {grade} mark{'s' if grade != 1 else ''} each")

    print(f"\n{C.CYAN}📈 Grade Distribution:{C.RESET}")
    all_grades = [q.get("grade", 1) for q in questions]
    if all_grades:
        unique_grades = sorted(set(all_grades))
        if len(unique_grades) == 1:
            print(f"   • All questions: {unique_grades[0]} mark{'s' if unique_grades[0] != 1 else ''} each")
        else:
            print(f"   • Lowest grade: {min(all_grades)} marks")
            print(f"   • Highest grade: {max(all_grades)} marks")
            print(f"   • Average grade: {sum(all_grades)/len(all_grades):.1f} marks")
            grade_counts = defaultdict(int)
            for grade in all_grades:
                grade_counts[grade] += 1
            print(f"   • Grade breakdown:")
            for grade in sorted(grade_counts.keys()):
                count = grade_counts[grade]
                percentage = (count / len(questions)) * 100
                print(f"     - {grade} marks: {count} question{'s' if count > 1 else ''} ({percentage:.1f}%)")

    if any(bypass_used.values()):
        print(f"\n{C.YELLOW}⚠️  Bypasses Applied:{C.RESET}")
        for k, lst in bypass_used.items():
            if lst:
                print(f"   • --bypass-{k}: Question(s) {', '.join(map(str, lst))}")

    try:
        size = os.path.getsize(output_file)
        if size < 1024:
            size_str = f"{size} bytes"
        elif size < 1024*1024:
            size_str = f"{size/1024:.1f} KB"
        else:
            size_str = f"{size/(1024*1024):.1f} MB"
        print(f"\n{C.GREEN}📁 Output Size: {size_str}{C.RESET}")
    except:
        pass
    
    if input_format == "txt" and skipped_lines > 0 and verbose:
        print(f"\n{C.YELLOW}ℹ️  Skipped lines: {skipped_lines}{C.RESET}")
        print(f"   • Comment lines (starting with #, //, /*, ---, ***)")
        print(f"   • Empty lines")
        print(f"   • Section headers and formatting lines")
        print(f"   • Questions filtered out by --questions option")
    
    print(f"\n{C.GREEN}✅ {output_format.upper()} file is ready for use!{C.RESET}")
    print("="*70 + "\n")

# -------------------- CONVERSION LOGIC --------------------
def run_conversion(args):
    """Main conversion logic - separated from CLI parsing"""
    # Check input file
    if not os.path.exists(args.input):
        raise IOError(f"Input file not found: {args.input}")

    # ---------- DETECT EXAM MODE EARLY ----------
    # Store original format and exam flag before any modifications
    original_format = getattr(args, 'format', None)
    exam_mode_requested = False
    if original_format == "exam" or getattr(args, 'exam', False):
        exam_mode_requested = True
    # Also if output file ends with .mhtml (legacy) but we now use .exam.html
    if args.output and args.output.lower().endswith('.mhtml'):
        exam_mode_requested = True

    # ---------- INPUT FORMAT DETECTION ----------
    input_ext = os.path.splitext(args.input)[1].lower().lstrip('.')
    if input_ext in ['txt', 'text']:
        input_format = "txt"
    elif input_ext == 'json':
        input_format = "json"
    elif input_ext == 'xml':
        input_format = "xml"
    else:
        input_format = "txt"
        log(f"Unknown file extension '{input_ext}', assuming text format", "WARN", args.verbose)

    if input_format == "txt" and args.verbose:
        log("Note: Using UTF-8 with BOM handling for text files", "INFO", True)

    # ---------- OUTPUT FORMAT AUTO-DETECTION ----------
    if not args.format:
        if args.output:
            output_ext = os.path.splitext(args.output)[1].lower().lstrip('.')
            if output_ext == 'xml':
                args.format = "xml"
            elif output_ext == 'json':
                args.format = "json"
            elif output_ext == 'html':
                args.format = "html"
            elif output_ext == 'txt':
                args.format = "txt"
            else:
                if input_format == "txt":
                    args.format = "xml"
                else:
                    args.format = "txt"
        else:
            if input_format == "txt":
                args.format = "xml"
            elif input_format == "json":
                args.format = "txt"
            elif input_format == "xml":
                args.format = "txt"
            else:
                args.format = "xml"

    # If exam mode was requested, we internally use HTML format but will later generate exam HTML
    if exam_mode_requested:
        args.format = "html"

    # ---------- OUTPUT FILENAME ----------
    if not args.output:
        base_name = os.path.splitext(args.input)[0]
        if args.format == "xml":
            args.output = f"{base_name}_moodle.xml"
        elif args.format == "html":
            if exam_mode_requested:
                args.output = f"{base_name}.exam.html"
            else:
                args.output = f"{base_name}.html"
        else:
            args.output = f"{base_name}.{args.format}"
    else:
        # User provided output name; if exam mode, force .exam.html extension
        if exam_mode_requested and not args.output.endswith('.exam.html'):
            base, ext = os.path.splitext(args.output)
            args.output = base + '.exam.html'

    # ---------- LOGGING ----------
    log(f"Starting conversion: {input_format.upper()} → {'exam HTML' if exam_mode_requested else args.format.upper()}", "CONVERT", True)
    log(f"Input:  {args.input} ({input_format})", "INFO", args.verbose)
    log(f"Output: {args.output} ({'exam' if exam_mode_requested else args.format})", "INFO", args.verbose)
    if args.questions:
        log(f"Filter: {args.questions}", "INFO", args.verbose)
    if args.shuffle:
        log(f"Shuffle: Enabled - questions will be randomly ordered", "INFO", args.verbose)

    # ---------- LOAD QUESTIONS ----------
    questions = []
    bypass_used = {"duplicate": [], "option": []}
    skipped_lines = 0

    try:
        if input_format == "txt":
            questions, bypass_used, skipped_lines = parse_text_file(args.input, args)
        elif input_format == "json":
            questions = json_to_questions(args.input, args.verbose)
        elif input_format == "xml":
            questions = xml_to_questions(args.input, args.verbose)
        else:
            print(f"{C.RED}[ERROR] Unsupported input format: {input_format}{C.RESET}")
            sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise ParseError(f"Failed to parse input file: {e}")

    # ---------- FILTERING ----------
    original_count = len(questions)
    if args.questions:
        if args.verbose:
            print(f"\n{C.CYAN}{C.BOLD}=== FILTER PREVIEW ==={C.RESET}")
            max_q = max([q.get("question_no", 0) for q in questions]) if questions else 0
            selected, errors, warnings = validate_filter_pattern(args.questions, max_q, strict=True)
            if errors:
                print(f"\n{C.RED}[ERROR] Filter pattern has issues:{C.RESET}")
                for error in errors:
                    print(f"  • {error}")
                print(f"\n{C.YELLOW}Available questions: 1 to {max_q}{C.RESET}")
                print(f"{C.YELLOW}Cannot continue with invalid filter pattern.{C.RESET}")
                sys.exit(1)
            if warnings:
                print(f"\n{C.YELLOW}[WARNING] Filter adjustments:{C.RESET}")
                for warning in warnings:
                    print(f"  • {warning}")
            if selected:
                print(f"\n{C.GREEN}Filter Preview:{C.RESET}")
                print(f"  Will select: {sorted(selected)}")
                print(f"  Total questions to extract: {len(selected)}")
            else:
                print(f"\n{C.YELLOW}Warning: No valid questions selected with pattern{C.RESET}")
            print(f"{C.CYAN}{C.BOLD}======================{C.RESET}\n")
        questions = filter_questions(questions, args.questions, args.verbose)
        filtered_out = original_count - len(questions)
        log(f"Filtered out {filtered_out} questions, keeping {len(questions)}", "INFO", args.verbose)

    # ---------- SHUFFLING ----------
    shuffle_performed = False
    if args.shuffle and questions:
        import random
        log(f"Shuffling {len(questions)} questions randomly", "INFO", args.verbose)
        shuffle_performed = True
        shuffled_questions = questions.copy()
        random.shuffle(shuffled_questions)
        for q in shuffled_questions:
            if "original_question_no" not in q:
                q["original_question_no"] = q.get("question_no", 0)
        for i, q in enumerate(shuffled_questions, 1):
            old_no = q.get("question_no", i)
            q["question_no"] = i
            if args.verbose:
                text_preview = q.get('text', '')[:50] + "..." if len(q.get('text', '')) > 50 else q.get('text', '')
                log(f"  Question {old_no} → {i}: {text_preview}", "INFO", args.verbose)
        questions = shuffled_questions
        log(f"Questions shuffled and renumbered", "OK", args.verbose)

    # ---------- EXAM MODE SPECIFIC SETTINGS ----------
    exam_time_minutes = 90
    if exam_mode_requested:
        exam_time_minutes = parse_time_argument(args.time)
        log(f"Exam mode active: time limit = {exam_time_minutes} minute(s), pass mark = 45", "INFO", args.verbose)

    # ---------- CONVERT TO OUTPUT FORMAT ----------
    try:
        if args.format == "xml":
            create_moodle_xml(questions, args.output, args.verbose)
        elif args.format == "json":
            create_json_output(questions, args.output, args.verbose)
        elif args.format == "html":
            if exam_mode_requested:
                create_exam_html(questions, args.output, args.verbose,
                                 time_minutes=exam_time_minutes, pass_marks=45)
            else:
                create_html_output(questions, args.output, args.verbose, shuffle_applied=shuffle_performed)
        elif args.format == "txt":
            create_text_output(questions, args.output, args.verbose)
        else:
            print(f"{C.RED}[ERROR] Unsupported output format: {args.format}{C.RESET}")
            sys.exit(1)
    except Exception as e:
        print(f"{C.RED}[ERROR] Failed to create output file: {e}{C.RESET}")
        sys.exit(1)

    # ---------- SUCCESS MESSAGE ----------
    display_format = "exam HTML (.exam.html)" if exam_mode_requested else args.format
    print_success_message(questions, args.input, args.output, input_format,
                         display_format, bypass_used, skipped_lines, args.verbose, shuffle_performed)
