# File utils.py (unchanged, except clear_screen kept but not used)

import re
import sys
import os
import hashlib
from bs4 import BeautifulSoup, NavigableString, Tag
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

# ---------- HTML → terminal rendering ----------

def _wrap_inline(node, ctx, open_code, close_code):
    """Wrap the rendered children of an inline tag with ANSI codes."""
    inner = ''.join(_walk_html(c, ctx) for c in node.children)
    if not inner.strip():
        return inner
    return f"{open_code}{inner}{close_code}"


def _walk_html(node, ctx):
    """Recursively render an HTML node to terminal text."""
    S = ctx['S']

    if isinstance(node, NavigableString):
        raw = str(node).replace('\xa0', ' ')
        if ctx.get('in_pre'):
            return raw
        return re.sub(r'[ \t\r\n]+', ' ', raw)

    if not isinstance(node, Tag):
        return ""

    name = node.name.lower()

    # Tags with no display value
    if name in ('script', 'style', 'noscript', 'head', 'meta', 'link', 'title'):
        return ""

    # -------- Inline --------
    if name in ('b', 'strong'):
        return _wrap_inline(node, ctx, S['bold'], S['reset'])
    if name in ('i', 'em'):
        return _wrap_inline(node, ctx, S['italic'], S['reset'])
    if name == 'u':
        return _wrap_inline(node, ctx, S['underline'], S['reset'])
    if name in ('s', 'strike', 'del'):
        return _wrap_inline(node, ctx, S['strike'], S['reset'])
    if name == 'code':
        return _wrap_inline(node, ctx, S['code'], S['reset'])

    if name == 'br':
        return "\n"
    if name == 'hr':
        return "\n" + S['hr'] + "\n"
    if name == 'img':
        alt = (node.get('alt') or '').strip()
        return f"[Image: {alt}]" if alt else "[Image]"
    if name == 'a':
        inner = ''.join(_walk_html(c, ctx) for c in node.children).strip()
        href = (node.get('href') or '').strip()
        if href and inner and href != inner and not href.startswith('#'):
            return f"{inner} ({S['link']}{href}{S['reset']})"
        if not inner and href:
            return f"{S['link']}{href}{S['reset']}"
        return inner

    # -------- Headings --------
    if name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
        inner = ''.join(_walk_html(c, ctx) for c in node.children).strip()
        if not inner:
            return ""
        style = S.get(name, S['bold'])
        return f"\n{style}{inner}{S['reset']}\n"

    # -------- Paragraph --------
    if name == 'p':
        inner = ''.join(_walk_html(c, ctx) for c in node.children).strip()
        return inner + "\n\n" if inner else ""

    # -------- Blockquote --------
    if name == 'blockquote':
        inner = ''.join(_walk_html(c, ctx) for c in node.children).strip()
        if not inner:
            return ""
        bar = S['quote_bar']
        lines = inner.split('\n')
        body = "\n".join((bar + ln) if ln.strip() else bar.rstrip() for ln in lines)
        return "\n" + body + "\n\n"

    # -------- Lists --------
    if name in ('ul', 'ol'):
        ctx['list_stack'].append(name)
        ctx['ol_counters'].append(0)
        try:
            pieces = []
            for child in node.children:
                if isinstance(child, Tag) and child.name == 'li':
                    pieces.append(_walk_html(child, ctx))
        finally:
            ctx['list_stack'].pop()
            ctx['ol_counters'].pop()
        joined = "".join(pieces)
        if not ctx['list_stack']:
            joined += "\n"
        return joined

    if name == 'li':
        direct_chunks, nested_chunks = [], []
        for c in node.children:
            if isinstance(c, Tag) and c.name in ('ul', 'ol'):
                nested_chunks.append(c)
            else:
                direct_chunks.append(_walk_html(c, ctx))
        direct = "".join(direct_chunks).strip()

        depth = max(0, len(ctx['list_stack']) - 1)
        indent = "   " * depth
        if ctx['list_stack'] and ctx['list_stack'][-1] == 'ol':
            ctx['ol_counters'][-1] += 1
            bullet = f"{ctx['ol_counters'][-1]}."
        else:
            bullet = "•"
        marker = f"{S['bold']}{bullet}{S['reset']}" if S['bold'] else bullet
        result = f"{indent}{marker} {direct}\n"
        for n in nested_chunks:
            result += _walk_html(n, ctx)
        return result

    # -------- Definition lists --------
    if name == 'dt':
        inner = ''.join(_walk_html(c, ctx) for c in node.children).strip()
        if not inner:
            return ""
        return f"\n{S['bold']}{inner}{S['reset']}\n"

    if name == 'dd':
        inner = ''.join(_walk_html(c, ctx) for c in node.children).strip()
        if not inner:
            return ""
        lines = inner.split('\n')
        return "\n".join(("    " + ln) if ln else ln for ln in lines) + "\n"

    # -------- Pre --------
    if name == 'pre':
        ctx['in_pre'] = True
        try:
            inner = ''.join(_walk_html(c, ctx) for c in node.children)
        finally:
            ctx['in_pre'] = False
        return "\n" + inner.rstrip() + "\n"

    # -------- Table --------
    if name == 'table':
        return "\n" + _render_html_table(node, use_color=ctx.get('use_color', False)) + "\n"

    # -------- Inline / block containers --------
    INLINE_CONTAINERS = {
        'span', 'font', 'small', 'sup', 'sub', 'abbr', 'cite', 'q',
        'mark', 'time', 'label', 'bdi', 'bdo', 'var', 'samp', 'kbd',
        'ruby', 'rt', 'rp',
    }
    BLOCK_CONTAINERS = {
        'div', 'section', 'article', 'main', 'aside', 'header',
        'footer', 'nav', 'figure', 'figcaption', 'details', 'summary',
        'fieldset', 'form', 'address',
    }
    TABLE_PARTS = {'thead', 'tbody', 'tfoot', 'tr'}

    if name in INLINE_CONTAINERS:
        return ''.join(_walk_html(c, ctx) for c in node.children)

    if name in BLOCK_CONTAINERS:
        inner = ''.join(_walk_html(c, ctx) for c in node.children).strip()
        return (inner + "\n") if inner else ""

    if name in TABLE_PARTS:
        return ''.join(_walk_html(c, ctx) for c in node.children)

    # Fallback: recurse into children
    return ''.join(_walk_html(c, ctx) for c in node.children)


def _render_html_table(table, use_color=False):
    """
    Render an HTML <table> to terminal-friendly text using tabulate.

    Unlike the old version, this:
      • prefers <thead> / <th> for the header
      • only falls back to a heuristic when there's a strong signal
      • never blindly drops the first column — only an obvious row-number column
      • handles ragged rows
    """
    # ---- Header from <thead> ----
    header = []
    thead = table.find('thead')
    if thead:
        head_tr = thead.find('tr')
        if head_tr:
            header = [c.get_text(strip=True) for c in head_tr.find_all(['th', 'td'])]

    # ---- Body rows ----
    body_rows = []
    for tr in table.find_all('tr'):
        if thead and tr.find_parent('thead'):
            continue
        cells = tr.find_all(['td', 'th'])
        if not cells:
            continue
        body_rows.append([c.get_text(strip=True) for c in cells])

    # ---- Header from <th> in the first body row ----
    if not header and body_rows:
        first_tr = table.find('tr')
        if first_tr:
            first_cells = first_tr.find_all(['td', 'th'])
            if first_cells and all(c.name == 'th' for c in first_cells):
                header = body_rows.pop(0)

    # ---- Heuristic header (only when strong signal) ----
    if not header and len(body_rows) > 1:
        first = body_rows[0]
        looks_like_header = (
            all(c.strip() and len(c) < 40 and not re.search(r'\d', c) for c in first)
            if first else False
        )
        if looks_like_header:
            header = body_rows.pop(0)

    # ---- Drop a leading row-number column only when obvious ----
    if body_rows:
        first_col = [(r[0] if r else '') for r in body_rows]
        n_cols = max(len(r) for r in body_rows)
        is_row_num_col = (
            len(first_col) >= 2
            and n_cols > 1
            and all(re.fullmatch(r'\d{1,3}', (c or '').strip()) for c in first_col)
        )
        if is_row_num_col:
            body_rows = [r[1:] for r in body_rows]
            if header:
                h0 = (header[0] or '').strip()
                if not h0 or (len(h0) == 1 and h0.isalpha()):
                    header = header[1:]

    # ---- Drop an "A B C D" style header ----
    if header and len(header) > 1:
        if all((c or '').strip() and len(c.strip()) == 1 and c.strip().isalpha()
               for c in header):
            header = [c for c in header if c.strip() not in ('A', 'B', 'C', 'D')]

    if not body_rows and not header:
        return ""

    # ---- Normalize ragged rows ----
    n_cols = max([len(header)] + [len(r) for r in body_rows] + [0])
    if n_cols == 0:
        return ""
    header = list(header) + [''] * (n_cols - len(header))
    body_rows = [r + [''] * (n_cols - len(r)) for r in body_rows]

    # ---- Render ----
    try:
        if header and any(h.strip() for h in header):
            return tabulate(body_rows, headers=header, tablefmt='simple')
        return tabulate(body_rows, tablefmt='simple')
    except Exception:
        lines = []
        if header and any(h.strip() for h in header):
            lines.append(" | ".join(header))
            lines.append("-" * 40)
        for r in body_rows:
            lines.append(" | ".join(r))
        return "\n".join(lines)


def html_to_terminal(html_content, use_color=None):
    """
    Convert HTML (as stored from Moodle / LibreOffice / Word) into plain
    text suitable for terminal display, preserving structure.

    Preserves:
      • Headings       — proportionally weighted (bold + colour)
      • Paragraphs     — blank-line separation
      • Lists          — bullets / numbers, nested with indent
      • Tables         — header detection, box-drawing
      • Blockquotes    — indented with a vertical bar prefix
      • Horizontal rules
      • Pre / code     — whitespace kept verbatim
      • Inline styling — bold, italic, underline (ANSI)
      • Links          — "text (url)" when they differ

    ANSI colour is enabled automatically when stdout is a TTY, and can be
    forced with `use_color=True/False`. When disabled, the function returns
    clean plain text.
    """
    if not html_content:
        return ""

    # Fast path: no tags at all → return as-is
    if not re.search(r'<\s*\w', html_content):
        return html_content

    # Decide whether to emit ANSI codes
    if use_color is None:
        try:
            use_color = sys.stdout.isatty()
        except Exception:
            use_color = False

    # ANSI palette (empty strings when colour is off)
    if use_color:
        try:
            _cols = os.get_terminal_size().columns
        except Exception:
            _cols = 80
        hr_len = max(20, min(60, _cols - 8))
        S = {
            'bold':      "\033[1m",
            'italic':    "\033[3m",
            'underline': "\033[4m",
            'strike':    "\033[9m",
            'reset':     "\033[0m",
            'blue':      "\033[94m",
            'cyan':      "\033[96m",
            'green':     "\033[92m",
            'yellow':    "\033[93m",
            'magenta':   "\033[95m",
            'grey':      "\033[90m",
            'white':     "\033[97m",
            'h1':        "\033[1;96m",
            'h2':        "\033[1;94m",
            'h3':        "\033[1;92m",
            'h4':        "\033[1;93m",
            'h5':        "\033[1;95m",
            'h6':        "\033[1m",
            'code':      "\033[38;5;215m",
            'hr':        "\033[90m" + "─" * hr_len + "\033[0m",
            'quote_bar': "\033[96m│\033[0m ",
            'link':      "\033[4;94m",
        }
    else:
        S = {k: "" for k in (
            'bold', 'italic', 'underline', 'strike', 'reset',
            'blue', 'cyan', 'green', 'yellow', 'magenta', 'grey', 'white',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'code', 'link',
        )}
        S['hr'] = "─" * 50
        S['quote_bar'] = "│ "

    ctx = {
        'S': S,
        'use_color': use_color,
        'list_stack': [],
        'ol_counters': [],
        'in_pre': False,
    }

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        text = _walk_html(soup, ctx)
    except Exception:
        # Fallback: original-ish behaviour
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            for br in soup.find_all('br'):
                br.replace_with('\n')
            text = soup.get_text()
        except Exception:
            return html_content

    # ---- Tidy up ----
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+\n', '\n', text)    # trailing spaces on lines
    text = re.sub(r'\n{3,}', '\n\n', text)    # collapse 3+ blank lines
    return text.strip()

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
