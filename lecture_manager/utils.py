# File utils.py (unchanged, except clear_screen kept but not used)

import re
import sys
import os
import hashlib
from bs4 import BeautifulSoup
from tabulate import tabulate
import html2text
from decimal import Decimal
from .constants import DISPLAY_SEPARATOR

ROOT_DIR = os.path.expanduser("~/foxCloud/office/RootData")
TRASH_DIR = os.path.expanduser("~/.lecture_trash")


# ANSI color codes
class COLORS:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    WHITE = '\033[97m'
    RESET = '\033[0m'

# Map color names to codes for convenience
COLOR_MAP = {
    'header': COLORS.HEADER,
    'blue': COLORS.BLUE,
    'cyan': COLORS.CYAN,
    'green': COLORS.GREEN,
    'yellow': COLORS.YELLOW,
    'red': COLORS.RED,
    'magenta': COLORS.MAGENTA,
    'bold': COLORS.BOLD,
    'underline': COLORS.UNDERLINE,
    'white': COLORS.WHITE
}

def html_to_terminal(html_content):
    """
    Convert HTML (as stored from Moodle / LibreOffice / Word) into plain
    text suitable for terminal display, preserving line structure.

    Rules:
      - <br>            → newline
      - </p>, </div>    → newline (double between blocks)
      - </li>           → newline
      - <table>         → ASCII table (best effort)
      - Plain text      → returned as-is
    """
    if not html_content:
        return ""

    # Fast path: no tags → return as-is, preserving real newlines
    if not re.search(r'<\s*\w', html_content):
        return html_content

    soup = BeautifulSoup(html_content, 'html.parser')

    # ---- 1. Normalise tags that mean "newline" ----
    for br in soup.find_all('br'):
        br.replace_with('\n')

    # ---- 2. Handle tables before anything else (they need structure) ----
    table_markers = []
    for idx, table in enumerate(soup.find_all('table')):
        rows = []
        for tr in table.find_all('tr'):
            row = [cell.get_text(strip=True) for cell in tr.find_all(['td', 'th'])]
            if row:
                rows.append(row)
        if not rows:
            table.replace_with('')
            continue

        # Drop "A B C D" header row if present
        if len(rows) >= 2 and all(len(c) == 1 and c.isalpha() for c in rows[0] if c):
            rows = rows[1:]
        # Drop first (row-number) column
        rows = [[c for j, c in enumerate(r) if j != 0] for r in rows]
        if not rows:
            table.replace_with('')
            continue

        ascii_table = tabulate(rows[1:], headers=rows[0], tablefmt='simple')
        marker = f"\n____TABLE_{idx}____\n"
        table_markers.append((marker, ascii_table))
        table.replace_with(marker)

    # ---- 3. Block-level tags get a newline appended ----
    for block in soup.find_all(['p', 'div', 'li',
                                'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                                'blockquote', 'pre']):
        block.append('\n')

    # ---- 4. Now extract text with real newlines preserved ----
    plain_text = soup.get_text()

    # ---- 5. Reinstate tables ----
    for marker, ascii_table in table_markers:
        plain_text = plain_text.replace(marker, f"\n{ascii_table}\n")

    # ---- 6. Tidy up ----
    plain_text = plain_text.replace('\r\n', '\n').replace('\r', '\n')
    plain_text = re.sub(r'[ \t]+\n', '\n', plain_text)   # trailing spaces
    plain_text = re.sub(r'\n{3,}', '\n\n', plain_text)   # collapse 3+ blank lines
    return plain_text.strip()

# This function should be placed after ROOT_DIR is defined
def get_file_path_for_record(record):
    """
    Locate the video file for a given record.
    Uses hash_cache first, then falls back to target directory, then whole ROOT_DIR.
    """
    from .db import get_connection  # local import to avoid circular dependency
    import glob
    from .file_manager import get_target_path  # local import

    file_hash = record.get('file_hash')
    if file_hash:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT file_path FROM hash_cache WHERE file_hash = %s AND status = 'active'", (file_hash,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and os.path.exists(row['file_path']):
            return row['file_path']
        else:
            target_dir, _ = get_target_path(record, interactive=False)
            if target_dir and os.path.exists(target_dir):
                pattern = os.path.join(target_dir, file_hash + '.*')
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]
    # Fallback: search whole ROOT_DIR by video_id in filename
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(('.mp4','.mkv','.webm','.avi','.mov')):
                if record['video_id'] in f:
                    return os.path.join(root, f)
    return None

def normalize_syllabus_id(raw):
    """
    Convert syllabus ID to a standard format: XX.XX.XX (with optional -n suffix).
    Examples:
        '4.2.5'       -> '04.02.05'
        '04.02.05'    -> '04.02.05'
        '4.02.5-1'    -> '04.02.05-1'
        '04.2.05-2'   -> '04.02.05-2'
        '4.2'         -> '04.02'  (if only two parts)
        '4'           -> '04'
    """
    if not raw:
        return raw
    raw = raw.strip()
    # Split off optional suffix like -1, -2
    suffix = ''
    if '-' in raw:
        raw, suffix = raw.split('-', 1)
        suffix = '-' + suffix
    parts = raw.split('.')
    # Pad each part to 2 digits
    padded = []
    for p in parts:
        if p.isdigit():
            padded.append(p.zfill(2))
        else:
            padded.append(p)   # Keep non‑numeric as‑is (unlikely)
    return '.'.join(padded) + suffix

def color_text(text, color=None, bold=False):
    """
    Wrap text with ANSI color codes.
    color: string key from COLOR_MAP or a direct ANSI code.
    bold: boolean.
    """
    if not sys.stdout.isatty():
        return text
    if color is None:
        color = ''
    elif color in COLOR_MAP:
        color = COLOR_MAP[color]
    prefix = ''
    if bold:
        prefix += COLORS.BOLD
    if color:
        prefix += color
    suffix = COLORS.RESET
    return f"{prefix}{text}{suffix}"

def print_colored(text, color=None, bold=False):
    print(color_text(text, color, bold))

def sanitize_for_json(obj):
    """Convert Decimal to int/float, and convert date/datetime to isoformat."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if hasattr(obj, 'isoformat'):  # datetime/date
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    return obj

def normalize_syllabus_code(raw):
    """
    Convert a legacy syllabus code to the numeric XX.YY form the resolver
    expects. Leaves already-numeric codes untouched. Returns the input
    unchanged if nothing matches.

    Examples:
        'P1-B6.3'   → '06.03'
        'P2-A1.5'   → '01.05'
        'P3-C3.10'  → '03.10'
        '06.03'     → '06.03'   (already numeric, passes through)
        '4.2'       → '04.02'   (numeric but not padded)
        'garbage'   → 'garbage' (unknown, untouched)
    """
    if not raw:
        return raw
    s = str(raw).strip()

    # Legacy format: P{n}-{L}{S}.{C}  e.g. P1-B6.3
    m = re.match(r'^P\d+-([A-C])(\d+)\.(\d+)$', s, re.IGNORECASE)
    if m:
        subj = int(m.group(2))
        chap = int(m.group(3))
        return f"{subj:02d}.{chap:02d}"

    # Already numeric: XX.YY, X.Y, or X.YY — pad to 2+2
    m = re.match(r'^(\d{1,2})\.(\d{1,2})$', s)
    if m:
        return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}"

    # Three-part numeric (subject.chapter.part) — keep first two, pad
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{1,2})', s)
    if m:
        return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}"

    # Unknown format — return as-is
    return s

def sanitize_filename(text):
    text = re.sub(r'[\\/*?"<>]', '', text)
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    text = text.strip()
    return text

def clean_field(text):
    return text.strip() if text else ""

def get_display_title(record):
    if record.get('chapter'):
        return clean_field(record['chapter'])
    raw = record.get('video_title', '')
    if raw and '||' in raw:
        parts = [p.strip() for p in raw.split('||') if p.strip()]
        return parts[0] if parts else raw.strip()
    return clean_field(record.get('subject', ''))

def parse_lecture_title(title):
    if not title:
        return None

    parts = [p.strip() for p in title.split('||') if p.strip()]
    if not parts:
        return None

    # Patterns for date, time, and name indicators
    date_pattern = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
    time_pattern = re.compile(r'\b\d{1,2}:\d{2}\s*[AP]M\b', re.IGNORECASE)
    name_pattern = re.compile(r'\b(MRS?|MR|MS|SIR|MAM|PROF|DR)\b', re.IGNORECASE)

    # Find date and time positions
    date_idx = None
    time_idx = None
    for i, p in enumerate(parts):
        if date_pattern.search(p):
            date_idx = i
        if time_pattern.search(p):
            time_idx = i

    # If date or time missing, fallback to old 4‑part logic
    if date_idx is None or time_idx is None:
        if len(parts) == 4:
            return {
                'subject': parts[0],
                'lecturer': parts[1],
                'nepali_date': parts[2],
                'time': parts[3]
            }
        return None

    nepali_date = parts[date_idx]
    time_str = parts[time_idx]

    # Remove date and time from the list
    remaining = [p for j, p in enumerate(parts) if j not in (date_idx, time_idx)]
    if not remaining:
        return None

    # Try to find the lecturer: the part that contains a name title
    lecturer_idx = None
    for i, p in enumerate(remaining):
        if name_pattern.search(p):
            lecturer_idx = i
            break

    if lecturer_idx is not None:
        lecturer = remaining.pop(lecturer_idx)
    else:
        # If no title found, assume the last part before date/time is the lecturer
        lecturer = remaining.pop(-1)

    # The first remaining part becomes the subject
    subject = remaining[0] if remaining else ''

    return {
        'subject': subject,
        'lecturer': lecturer,
        'nepali_date': nepali_date,
        'time': time_str
    }

def clear_screen():
    """Clear the terminal screen (optional, not used automatically)."""
    os.system('cls' if os.name == 'nt' else 'clear')

def compute_md5(file_path, chunk_size=8192):
    """Compute MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def build_original_filename(record):
    """
    Build the original filename from record fields.
    Returns a string like: "syllabus || chapter || subject || lecturer || date || time"
    or None if all fields are empty.
    """
    parts = [
        record.get('syllabus_id', ''),
        record.get('chapter', ''),
        record.get('subject', ''),
        record.get('lecturer', ''),
        record.get('nepali_date', ''),
        record.get('time', '')
    ]
    # Filter empty parts
    parts = [str(p).strip() for p in parts if p and str(p).strip()]
    return DISPLAY_SEPARATOR.join(parts) if parts else None

def build_youtube_title(record, max_length=100):
    """
    Build a concise title for YouTube uploads (max 100 chars).
    Uses the same DISPLAY_SEPARATOR as local files.
    Includes: subject, lecturer, nepali_date, time.
    Drops: syllabus_id, chapter.
    """
    from .constants import DISPLAY_SEPARATOR

    parts = [
        record.get('subject', ''),
        record.get('lecturer', ''),
        record.get('nepali_date', ''),
        record.get('time', '')
    ]
    # Filter empty parts and strip whitespace
    parts = [str(p).strip() for p in parts if p and str(p).strip()]

    if not parts:
        # Fallback to video_id or syllabus_id
        fallback = record.get('video_id', '') or record.get('syllabus_id', '')
        return fallback[:max_length]

    # Join with the global diamond separator
    title = DISPLAY_SEPARATOR.join(parts)

    # Truncate to max_length (with ellipsis)
    if len(title) > max_length:
        title = title[:max_length - 3] + "..."

    return title
