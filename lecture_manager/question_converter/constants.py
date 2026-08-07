# File Constants.py

# Valid question types list
VALID_QUESTION_TYPES = ["multichoice", "essay", "truefalse", "matching"]

# -------------------- COLORS --------------------
class C:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"

# Separator line
SEPARATOR = f"{C.MAGENTA}{C.BOLD}══════════════════════════════════════════════════════════════{C.RESET}"

HELP_TEXT_FORMAT = f"""
{C.CYAN}{C.BOLD}📄 TEXT INPUT/OUTPUT FORMAT:{C.RESET}

{C.GREEN}Basic Text Format:{C.RESET}
  • One question per section, separated by blank lines
  • Question can start with "Question:" or "Question No. X:"
  • Each field on a new line with colon separator
  • Comments start with #, //, /*, ---, or ***

{C.GREEN}Supported Question Types in Text Format:{C.RESET}
  • multichoice: Multiple choice questions (exactly 4 options)
  • essay: Essay/long answer questions
  • truefalse: True/False questions
  • matching: Matching questions (pairs of subquestions/answers)

{C.GREEN}📚 PASSAGE FEATURE (NEW):{C.RESET}
  • Define a passage once, reuse in many questions
  • Passage definition: [passage:identifier] on its own line
  • Reference in question: (passage:identifier) after the question number
  • Example:
    [passage:1]
    This is a reading passage about Nepal.
    It has multiple lines.

    Question No. 1 (passage:1): What is the capital of Nepal?
    Type: multichoice
    Option: Kathmandu *
    ...
  • Output: The passage is automatically inserted before the question text.
  • Perfect for reading comprehension questions – each question carries its own passage even after shuffling.

{C.GREEN}Text → Other Formats:{C.RESET}
  • {C.GREEN}Text → XML{C.RESET}: Creates Moodle-compatible XML
  • {C.GREEN}Text → JSON{C.RESET}: Creates structured JSON for APIs
  • {C.GREEN}Text → HTML{C.RESET}: Creates web-friendly HTML page
  • {C.GREEN}Text → Text{C.RESET}: Creates cleaned/reformatted text

{C.GREEN}Other → Text Format:{C.RESET}
  • {C.GREEN}XML → Text{C.RESET}: Extracts questions from Moodle XML
  • {C.GREEN}JSON → Text{C.RESET}: Converts JSON back to text format
  • {C.GREEN}HTML → Text{C.RESET}: Extracts text from HTML export

{C.YELLOW}💡 TIP:{C.RESET} Use text format for easy editing, then convert to XML for Moodle import
{C.YELLOW}💡 TIP:{C.RESET} Use JSON format for API integration or programmatic access
{C.YELLOW}💡 TIP:{C.RESET} Use HTML format for web viewing or printing
"""

# -------------------- HELP SECTIONS --------------------
HELP_HEADER = f"""
{C.MAGENTA}{C.BOLD}╔══════════════════════════════════════════════════════════════╗{C.RESET}
{C.MAGENTA}{C.BOLD}║                 FORMATTING HELP GUIDE                        ║{C.RESET}
{C.MAGENTA}{C.BOLD}╚══════════════════════════════════════════════════════════════╝{C.RESET}
"""

HELP_VALID_TYPES = f"""
{C.CYAN}{C.BOLD}📋 VALID QUESTION TYPES:{C.RESET}
   {C.GREEN}• multichoice{C.RESET} - Multiple choice questions (exactly 4 options, 1 correct)
   {C.GREEN}• essay{C.RESET}       - Essay questions (long answer, text response)
   {C.GREEN}• truefalse{C.RESET}   - True/False questions (only True/False options)
   {C.GREEN}• matching{C.RESET}    - Matching questions (pairs of subquestions and answers)

{C.CYAN}{C.BOLD}✨ MARKING CORRECT ANSWERS:{C.RESET}
   {C.GREEN}*, [Correct], [correct], [OK], [ok], [Right], [right]{C.RESET}
   {C.YELLOW}Note:{C.RESET} Markers must be {C.RED}OUTSIDE{C.RESET} LaTeX math blocks

{C.CYAN}{C.BOLD}📐 LaTeX MATH BLOCKS (ignored for marker detection):{C.RESET}
   {C.GREEN}\\( ... \\){C.RESET}
   {C.GREEN}\\[ ... \\]{C.RESET}
   {C.GREEN}$ ... ${C.RESET}
   {C.GREEN}$$ ... $${C.RESET}

{C.CYAN}{C.BOLD}⚙️  MCQ REQUIREMENTS:{C.RESET}
   • {C.GREEN}Exactly 4 options{C.RESET} (unless using --bypass-option)
   • {C.GREEN}Exactly one correct option{C.RESET} required
   • {C.GREEN}No duplicate questions{C.RESET} (unless using --bypass-duplicate)

{C.CYAN}{C.BOLD}🎯 MATCHING REQUIREMENTS:{C.RESET}
   • {C.GREEN}Minimum 2 pairs{C.RESET} (subquestion + answer)
   • {C.GREEN}Unique subquestions{C.RESET} (no duplicates)
   • {C.GREEN}Answers can be duplicated{C.RESET} (same answer for different subquestions)

{C.CYAN}{C.BOLD}📝 QUESTION NUMBERING FORMATS:{C.RESET}
   • {C.GREEN}Question: <text>{C.RESET}
   • {C.GREEN}Question No. <number>: <text>{C.RESET}

{C.CYAN}{C.BOLD}🛠️  SUGGESTED FIXES FOR ERRORS:{C.RESET}
   • {C.YELLOW}No correct option:{C.RESET} Add exactly one correct marker outside math
   • {C.YELLOW}Multiple correct options:{C.RESET} Remove extra markers
   • {C.YELLOW}Less than 4 options:{C.RESET} Add options or use --bypass-option
   • {C.YELLOW}Duplicate questions:{C.RESET} Remove duplicate or use --bypass-duplicate
   • {C.YELLOW}Less than 2 matching pairs:{C.RESET} Add more subquestion/answer pairs
"""

# Add matching help section
HELP_MATCHING = f"""
{C.CYAN}{C.BOLD}🔗 MATCHING QUESTION BASIC FORMAT:{C.RESET}

{C.GREEN}Question:{C.RESET} Match the countries with their capitals.
{C.GREEN}Type:{C.RESET} matching
{C.GREEN}Shuffle Answers:{C.RESET} true  {C.YELLOW}# Default: true{C.RESET}
{C.GREEN}Show Number Correct:{C.RESET} false  {C.YELLOW}# Default: false (no cheating){C.RESET}
{C.GREEN}Subquestion:{C.RESET} France
{C.GREEN}Answer:{C.RESET} Paris
{C.GREEN}Subquestion:{C.RESET} Germany
{C.GREEN}Answer:{C.RESET} Berlin
{C.GREEN}Subquestion:{C.RESET} Italy
{C.GREEN}Answer:{C.RESET} Rome
{C.GREEN}Subquestion:{C.RESET} Spain
{C.GREEN}Answer:{C.RESET} Madrid

{C.YELLOW}# Optional parameters (use only when needed):{C.RESET}
{C.YELLOW}# Grade: 2{C.RESET}                # Default: {C.GREEN}1{C.RESET}
{C.YELLOW}# Penalty: 0.5{C.RESET}            # Default: {C.GREEN}0{C.RESET}
{C.YELLOW}# Correct Feedback: [text]{C.RESET} # Default: {C.GREEN}Your answer is correct.{C.RESET}
{C.YELLOW}# Partially Correct Feedback: [text]{C.RESET} # Default: {C.GREEN}Your answer is partially correct.{C.RESET}
{C.YELLOW}# Incorrect Feedback: [text]{C.RESET} # Default: {C.GREEN}Your answer is incorrect.{C.RESET}
{C.YELLOW}# General Feedback: [text]{C.RESET}
{C.YELLOW}# Hint 1: [text]{C.RESET}         # First hint text
{C.YELLOW}# Hint 1 Clear Incorrect: false{C.RESET}  # Default: false (no cheating)
{C.YELLOW}# Hint 1 Show Number Correct: false{C.RESET} # Default: false (no cheating)
{C.YELLOW}# Hint 2: [text]{C.RESET}         # Second hint text

{C.YELLOW}# Note:{C.RESET} Security defaults (no cheating/bias):
{C.YELLOW}# • Show Number Correct: false by default{C.RESET}
{C.YELLOW}# • Hint Clear Incorrect: false by default{C.RESET}
{C.YELLOW}# • Hint Show Number Correct: false by default{C.RESET}
"""

HELP_TRUEFALSE = f"""
{C.CYAN}{C.BOLD}✅ TRUE/FALSE BASIC FORMAT:{C.RESET}

{C.GREEN}Question:{C.RESET} Water boils at 100°C at sea level.
{C.GREEN}Type:{C.RESET} truefalse
{C.GREEN}Correct:{C.RESET} true
{C.GREEN}Grade:{C.RESET} 1
{C.GREEN}Penalty:{C.RESET} 0.33
{C.GREEN}General Feedback:{C.RESET} Water boils at 100°C (212°F) at standard atmospheric pressure at sea level.
{C.GREEN}Feedback True:{C.RESET} Correct! Water does boil at 100°C at sea level.
{C.GREEN}Feedback False:{C.RESET} Incorrect. Water boils at 100°C, not at a different temperature.

{C.YELLOW}# Alternative format with options:{C.RESET}
{C.GREEN}Question:{C.RESET} The Earth is flat.
{C.GREEN}Type:{C.RESET} truefalse
{C.GREEN}Option:{C.RESET} true
{C.GREEN}Option:{C.RESET} false *
{C.GREEN}Grade:{C.RESET} 2
"""

HELP_MULTICHOICE = f"""
{C.CYAN}{C.BOLD}📋 MCQ (MULTIPLE CHOICE) BASIC FORMAT:{C.RESET}

{C.GREEN}Question:{C.RESET} What is the capital of Nepal?
{C.GREEN}Option:{C.RESET} Kathmandu {C.RED}*{C.RESET}
{C.GREEN}Option:{C.RESET} Pokhara
{C.GREEN}Option:{C.RESET} Biratnagar
{C.GREEN}Option:{C.RESET} Nepalgunj

{C.YELLOW}# Optional parameters (use only when needed):{C.RESET}
{C.YELLOW}# Grade: 2{C.RESET}                # Default: {C.GREEN}1{C.RESET}
{C.YELLOW}# Penalty: 0.5{C.RESET}            # Default: {C.GREEN}0{C.RESET}
{C.YELLOW}# General Feedback: [text]{C.RESET}
"""

HELP_ESSAY = f"""
{C.CYAN}{C.BOLD}📝 ESSAY BASIC FORMAT:{C.RESET}

{C.GREEN}Question:{C.RESET} Explain the concept of opportunity cost.
{C.GREEN}Type:{C.RESET} essay

{C.YELLOW}# Optional parameters (use only when needed):{C.RESET}
{C.YELLOW}# Grade: 10{C.RESET}               # Default: {C.GREEN}1{C.RESET}
{C.YELLOW}# Lines: 12{C.RESET}               # Default: {C.GREEN}15{C.RESET}
{C.YELLOW}# Attachments: 1{C.RESET}          # Default: {C.GREEN}0{C.RESET}
{C.YELLOW}# FileTypes: .pdf,.docx{C.RESET}   # Default: {C.GREEN}.doc,.docx,.pdf,.png,.jpg,.jpeg{C.RESET}
{C.YELLOW}# MaxFileSizeMB: 5{C.RESET}        # Default: {C.GREEN}2{C.RESET}
{C.YELLOW}# General Feedback: [text]{C.RESET}
{C.YELLOW}# Grader Information: [text]{C.RESET}
"""

HELP_ADVANCED_EXAMPLES = f"""
{C.CYAN}{C.BOLD}🚀 ADVANCED EXAMPLES (Only when needed):{C.RESET}

{C.GREEN}Question:{C.RESET} Submit your project report.
{C.GREEN}Type:{C.RESET} essay
{C.GREEN}Grade:{C.RESET} 20
{C.GREEN}Lines:{C.RESET} 8
{C.GREEN}Attachments:{C.RESET} 1
{C.GREEN}FileTypes:{C.RESET} .pdf,.docx
{C.GREEN}MaxFileSizeMB:{C.RESET} 5
{C.GREEN}General Feedback:{C.RESET} Include cover and references.
{C.GREEN}Grader Information:{C.RESET} Evaluate based on clarity, structure, and references.

---

{C.GREEN}Question:{C.RESET} What is the derivative of \\( x^3 \\)?
{C.GREEN}Option:{C.RESET} \\( 3x^2 \\) {C.RED}*{C.RESET}
{C.GREEN}Option:{C.RESET} \\( x^2 \\)
{C.GREEN}Option:{C.RESET} \\( 3x \\)
{C.GREEN}Option:{C.RESET} \\( 4x^2 \\)
{C.GREEN}Grade:{C.RESET} 3
{C.GREEN}Penalty:{C.RESET} 0.33
{C.GREEN}General Feedback:{C.RESET} Use power rule: d/dx(x^n) = n*x^(n-1)
"""

HELP_PASSAGE = f"""
{C.CYAN}{C.BOLD}📚 READING PASSAGE FEATURE (NEW):{C.RESET}

{C.GREEN}Purpose:{C.RESET}
  Define a passage once and reuse it in multiple questions. Each question gets its own copy of the passage,
  so shuffling never separates the passage from its questions.

{C.GREEN}How to define a passage:{C.RESET}
  • Write {C.YELLOW}[passage:identifier]{C.RESET} on its own line (identifier can be number or word)
  • Then write the passage text (can span multiple lines, blank lines allowed)
  • Stop the passage when you encounter another {C.YELLOW}[passage:...]{C.RESET} or a {C.YELLOW}Question{C.RESET} line.

{C.GREEN}How to use a passage in a question:{C.RESET}
  • Add {C.YELLOW}(passage:identifier){C.RESET} right after the question number, before the colon.
  • The marker will be removed and replaced by the passage automatically.

{C.GREEN}Example:{C.RESET}
  [passage:1]
  This is a reading passage about Nepal.
  It has multiple lines.

  [passage:nepali]
  यो नेपालको बारेमा अनुच्छेद हो।

  Question No. 1 (passage:1): What is the capital of Nepal?
  Type: multichoice
  Option: Kathmandu *
  Option: Pokhara
  Option: Biratnagar
  Option: Nepalgunj

  Question No. 2 (passage:nepali): नेपालको राजधानी के हो?
  Type: multichoice
  Option: काठमाडौं *
  Option: पोखरा
  Option: विराटनगर
  Option: नेपालगन्ज

{C.GREEN}Output format (automatically generated):{C.RESET}
  Reading Passage 1:<br>This is a reading passage about Nepal.<br>It has multiple lines.<p>What is the capital of Nepal?</p>

{C.GREEN}Benefits:{C.RESET}
  • {C.YELLOW}Reusability{C.RESET} – same passage used in many questions
  • {C.YELLOW}Shuffle‑safe{C.RESET} – each question carries its own copy
  • {C.YELLOW}Clean input{C.RESET} – no duplication of long text
  • {C.YELLOW}Works in all output formats{C.RESET} (XML, HTML, JSON, TXT)
"""

HELP_GROUP = f"""
{C.CYAN}{C.BOLD}👥 GROUP FEATURE:{C.RESET}

{C.GREEN}Purpose:{C.RESET}
  Group related questions together. Groups appear as headings in HTML output
  and are preserved in text/XML/JSON formats. When shuffling is enabled,
  groups are removed and each question stores its original group in metadata.

{C.GREEN}How to define a group:{C.RESET}
  • Write {C.YELLOW}[group: Group Name]{C.RESET} on its own line.
  • All following questions belong to that group until a new group is defined.
  • Group names can contain spaces, letters, numbers, and punctuation.

{C.GREEN}Example:{C.RESET}
  [group: Mathematics]
  Question No. 1: What is 2+2?
  Type: multichoice
  Option: 3
  Option: 4 *
  Option: 5

  [group: Physics]
  Question No. 2: What is the unit of force?
  Type: multichoice
  Option: Joule
  Option: Newton *
  Option: Watt

{C.GREEN}Output behaviour:{C.RESET}
  • {C.YELLOW}Without shuffle{C.RESET}   – Groups are shown as headings in HTML.
  • {C.YELLOW}With shuffle{C.RESET}      – Groups are stripped from the main display,
                           but each question's metadata shows its original group.
  • {C.YELLOW}Text/XML/JSON{C.RESET} – Groups are stored as a "group" field.

{C.GREEN}Advanced:{C.RESET}
  • Groups can be nested? No – groups are linear.
  • Empty groups are ignored.
  • Group markers themselves are never treated as questions.
"""

HELP_CONVERSION = f"""
{C.CYAN}{C.BOLD}🔄 MULTI-FORMAT CONVERSION:{C.RESET}

{C.GREEN}Supported conversions:{C.RESET}
  {C.YELLOW}txt → xml, json, html{C.RESET}
  {C.YELLOW}json → xml, txt, html{C.RESET}
  {C.YELLOW}xml → txt, json, html{C.RESET}

{C.GREEN}Question filtering:{C.RESET}
  {C.YELLOW}--questions 5,10,20,60{C.RESET}    (specific questions)
  {C.YELLOW}--questions 90..100{C.RESET}       (range of questions)
"""

HELP_TIPS = f"""
{C.YELLOW}💡 TIP:{C.RESET} Use {C.GREEN}--bypass-option{C.RESET} to allow less than 4 options
{C.YELLOW}💡 TIP:{C.RESET} Use {C.GREEN}--bypass-duplicate{C.RESET} to allow duplicate questions
{C.YELLOW}💡 TIP:{C.RESET} Use {C.GREEN}--verbose{C.RESET} to see detailed processing
{C.YELLOW}💡 TIP:{C.RESET} Use {C.GREEN}--help-format{C.RESET} to show this guide again
{C.YELLOW}💡 TIP:{C.RESET} Use {C.GREEN}[passage:...]{C.RESET} to define reusable reading passages (see the PASSAGE section)
"""

# Complete help text (for backward compatibility)
HELP_FORMAT_TEXT = f"""
{HELP_HEADER}
{HELP_VALID_TYPES}
{SEPARATOR}
{HELP_TRUEFALSE}
{SEPARATOR}
{HELP_MULTICHOICE}
{SEPARATOR}
{HELP_ESSAY}
{SEPARATOR}
{HELP_MATCHING}
{SEPARATOR}
{HELP_PASSAGE}
{SEPARATOR}
{HELP_GROUP}
{SEPARATOR}
{HELP_ADVANCED_EXAMPLES}
{SEPARATOR}
{HELP_CONVERSION}
{SEPARATOR}
{HELP_TIPS}
{SEPARATOR}
"""

# -------------------- BANNER FOR PROGRAM START --------------------
PROGRAM_BANNER = f"""
{C.MAGENTA}{C.BOLD}╔══════════════════════════════════════════════════════════════╗{C.RESET}
{C.MAGENTA}{C.BOLD}║        MULTI-FORMAT QUESTION CONVERTER v2.0                  ║{C.RESET}
{C.MAGENTA}{C.BOLD}║                 Created by: Udaya Raj Joshi                  ║{C.RESET}
{C.MAGENTA}{C.BOLD}╚══════════════════════════════════════════════════════════════╝{C.RESET}

{C.CYAN}Quick Start:{C.RESET}
  {C.GREEN}python3 converter.py -i questions.txt -o output.xml{C.RESET}
  {C.GREEN}python3 converter.py -i questions.txt -s -o shuffled.xml{C.RESET}

{C.CYAN}For detailed formatting help:{C.RESET}
  {C.GREEN}python3 converter.py --help-format{C.RESET}
  {C.GREEN}python3 converter.py --help-format essay{C.RESET}
  {C.GREEN}python3 converter.py --help-format essay,multichoice,passage{C.RESET}
"""