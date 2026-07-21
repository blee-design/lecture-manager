# File utils.py (unchanged, except clear_screen kept but not used)

import re
import sys
import os
import hashlib
from bs4 import BeautifulSoup
from tabulate import tabulate
import html2text

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
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, 'html.parser')

    # Process tables and replace with unique markers
    table_markers = []
    tables = soup.find_all('table')

    for idx, table in enumerate(tables):
        rows = []
        for tr in table.find_all('tr'):
            row = [cell.get_text(strip=True) for cell in tr.find_all(['td', 'th'])]
            if row:
                rows.append(row)
        if not rows:
            continue

        # Drop the first row if it's just column letters (A, B, C...)
        if len(rows) >= 2 and all(len(cell) == 1 and cell.isalpha() for cell in rows[0] if cell):
            rows = rows[1:]
        if not rows:
            continue

        # Drop the first column (row numbers)
        rows = [[cell for j, cell in enumerate(row) if j != 0] for row in rows]
        if not rows:
            continue

        ascii_table = tabulate(rows[1:], headers=rows[0], tablefmt='simple')
        # Use a marker that is unlikely to be modified
        marker = f"____TABLE_{idx}____"
        table_markers.append((marker, ascii_table))
        table.replace_with(marker)

    # Convert the rest of the HTML (non‑table) to plain text
    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_links = True
    h.ignore_emphasis = False
    h.ignore_images = True
    h.ignore_tables = True   # we already removed table tags
    plain_text = h.handle(str(soup))

    # Replace markers with ASCII tables
    for marker, ascii_table in table_markers:
        # The marker may have newlines around it; we'll replace exactly
        plain_text = plain_text.replace(marker, f"\n{ascii_table}\n")

    # Clean up excessive blank lines
    plain_text = re.sub(r'\n{3,}', '\n\n', plain_text)
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
    return " || ".join(parts) if parts else None
