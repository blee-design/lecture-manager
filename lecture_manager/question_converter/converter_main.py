#!/usr/bin/env python3
import sys
import argparse

from .constants import (
    C, HELP_FORMAT_TEXT, PROGRAM_BANNER, SEPARATOR,
    HELP_HEADER, HELP_VALID_TYPES, HELP_TRUEFALSE,
    HELP_MULTICHOICE, HELP_ESSAY, HELP_MATCHING,
    HELP_TEXT_FORMAT, HELP_ADVANCED_EXAMPLES, HELP_CONVERSION, HELP_TIPS,
    HELP_PASSAGE, HELP_GROUP
)
from .converter_core import run_conversion

# ======================== PARSER (global) ========================
parser = argparse.ArgumentParser(
    description=f"{C.CYAN}{C.BOLD}Multi-format question converter{C.RESET}",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=f"""
{C.YELLOW}{C.BOLD}Security Notes:{C.RESET}
  {C.GREEN}• Matching questions:{C.RESET} Defaults prevent cheating
  {C.GREEN}  - Show Number Correct: false{C.RESET} (no count shown)
  {C.GREEN}  - Hint options: false by default{C.RESET} (no clearing/showing count)
  {C.GREEN}• Use defaults for exams{C.RESET} (secure, no bias)
  {C.GREEN}• Change only for practice{C.RESET} (set to true for hints/feedback)

{C.YELLOW}{C.BOLD}Examples:{C.RESET}
  {C.GREEN}# Basic conversions (defaults to txt → xml){C.RESET}
  python3 converter.py -i questions.txt -o output.xml

  {C.GREEN}# Matching question with secure defaults{C.RESET}
  Question: Match the capitals
  Type: matching
  Subquestion: France
  Answer: Paris
  Subquestion: Germany
  Answer: Berlin

  {C.GREEN}# Matching question with hints (for practice){C.RESET}
  Question: Match the capitals
  Type: matching
  Subquestion: France
  Answer: Paris
  Subquestion: Germany
  Answer: Berlin
  Show Number Correct: true
  Hint 1: France's capital starts with P
  Hint 1 Clear Incorrect: true
  Hint 1 Show Number Correct: true

{C.YELLOW}{C.BOLD}Shuffling Questions:{C.RESET}
  {C.GREEN}• Use -s or --shuffle to randomize question order{C.RESET}
  {C.GREEN}• Questions are renumbered sequentially after shuffling{C.RESET}
  {C.GREEN}• Can be combined with --questions filter{C.RESET}

{C.YELLOW}{C.BOLD}Supported conversions:{C.RESET}
  {C.GREEN}txt → xml, json, html{C.RESET}
  {C.GREEN}json → xml, txt, html{C.RESET}
  {C.GREEN}xml → txt, json, html{C.RESET}
    """
)

# Core arguments
parser.add_argument("-i", "--input", default="questions.txt",
                   help=f"{C.GREEN}Input file path (default: questions.txt){C.RESET}")

parser.add_argument("-o", "--output",
                   help=f"{C.GREEN}Output file path (auto-detected from format if not specified){C.RESET}")

# Exam mode options
parser.add_argument("-e", "--exam", action="store_true",
                   help=f"{C.GREEN}Enable interactive exam mode (one question at a time, timer, certificate){C.RESET}")
parser.add_argument("--time", type=str, default="90",
                   help=f"{C.GREEN}Exam time limit. Examples: 90 (minutes), 1h (1 hour), 90m, 120s (seconds). Default: 90m.{C.RESET}")

parser.add_argument("-f", "--format",
                   choices=["xml", "json", "html", "txt", "exam"],
                   help=f"{C.GREEN}Output format: xml, json, html, txt, or exam (exam mode). .exam extension also triggers exam mode.{C.RESET}")

# Question filtering
parser.add_argument("-q", "--questions",
                   help=f"{C.GREEN}Filter questions: comma-separated (5,10,20) or range (90..100){C.RESET}")

# Question shuffling
parser.add_argument("-s", "--shuffle", action="store_true",
                   help=f"{C.GREEN}Shuffle all questions randomly{C.RESET}")

# Existing bypass arguments
parser.add_argument("--bypass-option", action="store_true",
                   help=f"{C.YELLOW}Auto-fill missing options for MCQs{C.RESET}")
parser.add_argument("--bypass-duplicate", action="store_true",
                   help=f"{C.YELLOW}Allow duplicate questions{C.RESET}")

# Other arguments
parser.add_argument("-v", "--verbose", action="store_true",
                   help=f"{C.CYAN}Show detailed progress{C.RESET}")
parser.add_argument("--help-format", nargs='?', const="", default=None,
                   help=f"{C.MAGENTA}Show detailed formatting help (optionally specify question types: truefalse,multichoice,essay,passage,group){C.RESET}")

# -------------------- HELPER FUNCTION FOR FORMATTED HELP --------------------
def show_help_format(types=None):
    """Show formatting help, optionally filtered by question types or sections"""
    
    # Create a dictionary to map type names to their help sections
    type_sections = {
        'valid_types': HELP_VALID_TYPES,
        'truefalse': HELP_TRUEFALSE,
        'multichoice': HELP_MULTICHOICE,
        'essay': HELP_ESSAY,
        'matching': HELP_MATCHING,
        'text_format': HELP_TEXT_FORMAT,
        'advanced': HELP_ADVANCED_EXAMPLES,
        'conversion': HELP_CONVERSION,
        'tips': HELP_TIPS,
        'passage': HELP_PASSAGE,      # NEW
        'group': HELP_GROUP           # NEW
    }
    
    # Map user-friendly names to actual section names
    user_to_section = {
        'truefalse': 'truefalse',
        'multichoice': 'multichoice', 
        'essay': 'essay',
        'matching': 'matching',
        'text': 'text_format',
        'advanced': 'advanced',
        'conversion': 'conversion',
        'tips': 'tips',
        'passage': 'passage',         # NEW
        'group': 'group'              # NEW
    }
    
    # Start with the header
    help_text = HELP_HEADER
    
    if not types:
        # Show all sections (including passage and group)
        help_text += HELP_VALID_TYPES + SEPARATOR
        help_text += HELP_TRUEFALSE + SEPARATOR
        help_text += HELP_MULTICHOICE + SEPARATOR
        help_text += HELP_ESSAY + SEPARATOR
        help_text += HELP_MATCHING + SEPARATOR
        help_text += HELP_TEXT_FORMAT + SEPARATOR
        help_text += HELP_PASSAGE + SEPARATOR
        help_text += HELP_GROUP + SEPARATOR
        help_text += HELP_ADVANCED_EXAMPLES + SEPARATOR
        help_text += HELP_CONVERSION + SEPARATOR
        help_text += HELP_TIPS + SEPARATOR
    else:
        # Parse comma-separated types
        requested_types = [t.strip().lower() for t in types.split(',')]
        
        # Check if user requested 'all'
        if 'all' in requested_types:
            # Show all sections (including passage and group)
            help_text += HELP_VALID_TYPES + SEPARATOR
            help_text += HELP_TRUEFALSE + SEPARATOR
            help_text += HELP_MULTICHOICE + SEPARATOR
            help_text += HELP_ESSAY + SEPARATOR
            help_text += HELP_MATCHING + SEPARATOR
            help_text += HELP_TEXT_FORMAT + SEPARATOR
            help_text += HELP_PASSAGE + SEPARATOR
            help_text += HELP_GROUP + SEPARATOR
            help_text += HELP_ADVANCED_EXAMPLES + SEPARATOR
            help_text += HELP_CONVERSION + SEPARATOR
            help_text += HELP_TIPS + SEPARATOR
        else:
            # Always include valid types section unless user specifically excludes it
            if 'valid_types' not in requested_types and 'valid_types' not in user_to_section.values():
                help_text += HELP_VALID_TYPES + SEPARATOR
            
            # Show requested sections in logical order
            sections_to_show = []
            
            for req_type in requested_types:
                if req_type in user_to_section:
                    sections_to_show.append(user_to_section[req_type])
            
            # Define the order for sections (now includes passage and group)
            section_order = ['truefalse', 'multichoice', 'essay', 'matching', 'passage', 'group', 'text_format', 'advanced', 'conversion', 'tips']
            
            sections_added = 0
            
            for section in section_order:
                if section in sections_to_show:
                    help_text += type_sections[section] + SEPARATOR
                    sections_added += 1
            
            # If no specific sections were added, show error
            if sections_added == 0:
                # Check what was invalid
                invalid_types = []
                for req_type in requested_types:
                    if req_type not in user_to_section and req_type != 'valid_types':
                        invalid_types.append(req_type)
                
                if invalid_types:
                    print(f"{C.YELLOW}⚠️  Unknown help sections: {', '.join(invalid_types)}{C.RESET}")
                    print(f"{C.CYAN}Available help sections:{C.RESET}")
                    print(f"  {C.GREEN}• truefalse{C.RESET}   - True/False questions")
                    print(f"  {C.GREEN}• multichoice{C.RESET} - Multiple choice questions")
                    print(f"  {C.GREEN}• essay{C.RESET}       - Essay questions")
                    print(f"  {C.GREEN}• matching{C.RESET}    - Matching questions")
                    print(f"  {C.GREEN}• text{C.RESET}        - Text format guide")
                    print(f"  {C.GREEN}• passage{C.RESET}     - Reusable reading passages (NEW)")
                    print(f"  {C.GREEN}• group{C.RESET}       - Grouping questions together")
                    print(f"  {C.GREEN}• advanced{C.RESET}    - Advanced examples")
                    print(f"  {C.GREEN}• conversion{C.RESET}  - Conversion options")
                    print(f"  {C.GREEN}• tips{C.RESET}        - Tips and tricks")
                    print(f"  {C.GREEN}• all{C.RESET}         - Show all sections")
                    print(f"\n{C.YELLOW}Examples:{C.RESET}")
                    print(f"  {C.GREEN}--help-format essay{C.RESET}")
                    print(f"  {C.GREEN}--help-format essay,multichoice{C.RESET}")
                    print(f"  {C.GREEN}--help-format matching{C.RESET}")
                    print(f"  {C.GREEN}--help-format text{C.RESET}")
                    print(f"  {C.GREEN}--help-format passage{C.RESET}")
                    print(f"  {C.GREEN}--help-format group{C.RESET}")
                    print(f"  {C.GREEN}--help-format all{C.RESET}")
                    sys.exit(1)
            
            # Always add tips at the end if not already included
            if 'tips' not in sections_to_show and sections_added > 0:
                help_text += HELP_TIPS + SEPARATOR
    
    print(help_text)

    """Main CLI entry point - called from root converter.py"""
    # Display colorful banner
    print(PROGRAM_BANNER)

    parser = argparse.ArgumentParser(
        description=f"{C.CYAN}{C.BOLD}Multi-format question converter{C.RESET}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
    {C.YELLOW}{C.BOLD}Security Notes:{C.RESET}
    {C.GREEN}• Matching questions:{C.RESET} Defaults prevent cheating
    {C.GREEN}  - Show Number Correct: false{C.RESET} (no count shown)
    {C.GREEN}  - Hint options: false by default{C.RESET} (no clearing/showing count)
    {C.GREEN}• Use defaults for exams{C.RESET} (secure, no bias)
    {C.GREEN}• Change only for practice{C.RESET} (set to true for hints/feedback)

    {C.YELLOW}{C.BOLD}Examples:{C.RESET}
    {C.GREEN}# Basic conversions (defaults to txt → xml){C.RESET}
    python3 converter.py -i questions.txt -o output.xml

    {C.GREEN}# Matching question with secure defaults{C.RESET}
    Question: Match the capitals
    Type: matching
    Subquestion: France
    Answer: Paris
    Subquestion: Germany
    Answer: Berlin

    {C.GREEN}# Matching question with hints (for practice){C.RESET}
    Question: Match the capitals
    Type: matching
    Subquestion: France
    Answer: Paris
    Subquestion: Germany
    Answer: Berlin
    Show Number Correct: true
    Hint 1: France's capital starts with P
    Hint 1 Clear Incorrect: true
    Hint 1 Show Number Correct: true

    {C.YELLOW}{C.BOLD}Shuffling Questions:{C.RESET}
    {C.GREEN}• Use -s or --shuffle to randomize question order{C.RESET}
    {C.GREEN}• Questions are renumbered sequentially after shuffling{C.RESET}
    {C.GREEN}• Can be combined with --questions filter{C.RESET}

    {C.YELLOW}{C.BOLD}Supported conversions:{C.RESET}
    {C.GREEN}txt → xml, json, html{C.RESET}
    {C.GREEN}json → xml, txt, html{C.RESET}
    {C.GREEN}xml → txt, json, html{C.RESET}
        """
    )

# ======================== MAIN ========================
def main():
    """Main CLI entry point - called from root converter.py"""
    # Display colorful banner
    print(PROGRAM_BANNER)

    args = parser.parse_args()

    # Handle help-format with optional types
    if args.help_format is not None:
        if args.help_format == "":
            show_help_format()
        else:
            show_help_format(args.help_format)
        sys.exit(0)

    # Run the actual conversion
    run_conversion(args)

if __name__ == "__main__":
    main()
