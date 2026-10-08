# facebook.py

import os
import subprocess
import shutil
import yt_dlp
from datetime import datetime
import re
import hashlib
from .utils import sanitize_filename, print_colored, color_text, COLORS, compute_md5
from .youtube import _ensure_cookie_file
from .file_manager import ROOT_DIR
from .facebook_manager import (
    add_facebook_entry,
    get_facebook_entry_by_url,
    get_facebook_file_path,
    get_facebook_entry_by_id,
    delete_facebook_entry_with_file
)

DOWNLOAD_DIR = './downloads'
PHOTO_BASE_DIR = os.path.join(DOWNLOAD_DIR, 'facebook_photos')

# Organised directories
FACEBOOK_VIDEO_DIR = os.path.join(ROOT_DIR, 'facebook', 'videos')
FACEBOOK_PHOTO_DIR = os.path.join(ROOT_DIR, 'facebook', 'photos')

def _parse_netscape_cookies(path):
    """Parse a Netscape cookie file into a requests-compatible dict."""
    cookies = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) >= 7:
                    domain = parts[0]
                    name = parts[5]
                    value = parts[6]
                    if 'facebook.com' in domain:
                        cookies[name] = value
    except Exception:
        pass
    return cookies

# ---------------------------------------------------------------------------
#  Facebook title / uploader extraction helpers
# ---------------------------------------------------------------------------

# Titles like these carry no information — reject them.
_FB_GENERIC_TITLES = {
    'facebook', 'watch', 'video', 'photo', 'reel', 'live', 'album',
    'photos', 'videos', 'facebook video', 'facebook watch',
    'facebook photo', 'facebook reel', 'facebook album',
    'video | facebook', 'photo | facebook', 'reel | facebook',
    'photos | facebook', 'watch | facebook',
}

# Path segments that are structural, not page names.
_FB_URL_SLUG_IGNORE = {
    'share', 'photo', 'photos', 'watch', 'reel', 'reels', 'videos',
    'posts', 'permalink', 'story', 'login', 'signup', 'p', 'groups',
    'profile.php', 'media', 'permalink.php', 'photo.php', 'video.php',
    'v', 'www', 'm', 'business', 'pg', 'pages', 'people',
}


def _clean_facebook_title(raw, uploader=None):
    """
    Turn a raw og:title (or yt-dlp title) into something usable, or None.

    - Strips Facebook's trailing fluff (" | Facebook", " - Facebook", …).
    - Rejects generic noise ("Facebook", "Video", "Photo", …).
    - Rejects the title if it's identical to the uploader name.
    - Rejects titles that are just a bare filename (e.g. "1234_5678.jpg").
    - Strips "Photo by X" / "Video by X" prefixes when the uploader is known.
    """
    if not raw:
        return None
    t = str(raw).strip()

    # Strip trailing " | Facebook" style suffixes (case-insensitive)
    for suffix in (
        ' | facebook', ' - facebook', ' – facebook', ' — facebook',
        ' | facebook watch', ' - facebook watch', ' | watch',
        ' on facebook', ' | meta',
    ):
        if t.lower().endswith(suffix):
            t = t[:-len(suffix)].rstrip()

    # Reject generic titles
    if t.lower().strip(' |') in _FB_GENERIC_TITLES:
        return None

    # Reject if the title equals the uploader name
    if uploader and t.lower() == str(uploader).lower():
        return None

    # Reject bare filenames: "1234_5678.jpg", "abc-123.png", etc.
    if re.match(r'^[\w\-]+\.(jpg|jpeg|png|gif|webp|mp4|webm|mov|avi)$',
                t, re.IGNORECASE):
        return None

    # Strip "<Kind> by <uploader>" prefixes
    if uploader:
        u = re.escape(str(uploader))
        for pat in (
            rf'^(?:Photo|Video|Reel|Live|Post)\s+by\s+{u}\b[\s:\-–—|]*',
        ):
            t = re.sub(pat, '', t, flags=re.IGNORECASE)

    t = t.strip(' -–—:|')
    if len(t) < 3:
        return None
    if len(t) > 200:
        t = t[:197].rsplit(' ', 1)[0] + '…'
    return t


def _extract_caption_from_description(desc):
    """
    Try to find the actual caption inside og:description.

    Facebook typically formats it as:
        "Photo by X on Facebook"                              ← no caption
        "Sunset at Pokhara — by Some Page on Facebook"        ← good caption
        "Album: Nepal 2081 · 12 photos · Facebook"            ← album blurb
    """
    if not desc:
        return None

    text = str(desc).strip()
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Strip common boilerplate prefixes/suffixes
        line = re.sub(r'^(?:Album|Photos?|Videos?)\s*[:\-–—]\s*',
                      '', line, flags=re.IGNORECASE)
        line = re.sub(r'\s*[·•]\s*\d+\s+photos?\s*',
                      '', line, flags=re.IGNORECASE)
        line = re.sub(r'\s*[·•]\s*Facebook\s*$',
                      '', line, flags=re.IGNORECASE)
        line = re.sub(r'\s+on\s+Facebook\.?\s*$',
                      '', line, flags=re.IGNORECASE)
        line = re.sub(r'\s*[—\-–]\s*by\s+.+?$', '', line)
        line = re.sub(r'^by\s+[^—\-–]+?\s*[—\-–]\s*', '', line,
                      flags=re.IGNORECASE)
        line = line.strip(' -–—:|')

        if len(line) < 5:
            continue
        if line.lower() in _FB_GENERIC_TITLES:
            continue

        if len(line) > 150:
            line = line[:147].rsplit(' ', 1)[0] + '…'
        return line

    return None


def _extract_uploader_from_url(url):
    """
    Best-effort page-name extraction from a Facebook URL.

    Handles:
      facebook.com/pages/<Name>/<id>       →  <Name>
      facebook.com/<slug>/photos/...       →  <slug>
      facebook.com/<slug>/videos/...       →  <slug>
      facebook.com/profile.php?id=...      →  None (no name in URL)
    """
    if not url:
        return None

    # facebook.com/pages/<Name>/<id>  — the most informative pattern
    m = re.search(r'facebook\.com/pages/([^/?#]+)', url, re.IGNORECASE)
    if m:
        name = m.group(1).replace('-', ' ').replace('_', ' ').replace('.', ' ')
        return ' '.join(name.split()).strip()

    # facebook.com/<slug>/...  — fallback
    m = re.search(r'facebook\.com/([^/?#]+)', url, re.IGNORECASE)
    if m:
        slug = m.group(1)
        if slug.lower() not in _FB_URL_SLUG_IGNORE:
            name = slug.replace('-', ' ').replace('_', ' ').replace('.', ' ')
            return ' '.join(name.split()).strip()

    return None


def _pick_photo_title(probe, uploader=None, custom_name=None):
    """
    Choose the best available title for a single Facebook photo.

    Priority:
      1. custom_name (user override)
      2. Cleaned og:title
      3. Real caption from og:description
      4. Uploader-based fallback ("Photo by X")
      5. Last resort: None (caller decides)
    """
    if custom_name:
        return custom_name

    if probe:
        t = _clean_facebook_title(probe.get('title'), uploader=uploader)
        if t:
            return t

        cap = _extract_caption_from_description(probe.get('description'))
        if cap:
            return cap

    if uploader and uploader.lower() not in ('unknown', 'facebook', ''):
        return f"Photo by {uploader}"

    return None


def _pick_album_title(probe, uploader=None, photo_count=None, custom_name=None):
    """
    Choose the best available title for a Facebook album.
    Same priority as photos, with photo count appended when known.
    """
    def _suffix(t):
        if not t:
            return t
        if photo_count and photo_count > 0:
            return f"{t} ({photo_count} photo" + ("s" if photo_count != 1 else "") + ")"
        return t

    if custom_name:
        return _suffix(custom_name)

    if probe:
        t = _clean_facebook_title(probe.get('title'), uploader=uploader)
        if t:
            return _suffix(t)

        cap = _extract_caption_from_description(probe.get('description'))
        if cap:
            return _suffix(cap)

    if uploader and uploader.lower() not in ('unknown', 'facebook', ''):
        return _suffix(f"Album by {uploader}")

    if photo_count and photo_count > 0:
        return f"Facebook Album ({photo_count} photo" + ("s" if photo_count != 1 else "") + ")"

    return "Facebook Album"

def _fast_probe(url, timeout=8):
    """
    Fast network probe using plain HTTP + Open Graph meta tags.
    Returns a dict:
      {
        'kind': 'video' | 'photo' | 'album' | 'unknown',
        'title': str | None,
        'uploader': str | None,
        'description': str | None,
        'og_video': str | None,
        'og_image': str | None,
      }
    or None if the probe failed entirely.
    """
    import re
    import html as _html

    try:
        import requests
    except ImportError:
        return None

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/131.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    cookies = {}
    if os.path.exists('cookies.txt'):
        cookies = _parse_netscape_cookies('cookies.txt')

    try:
        resp = requests.get(
            url, headers=headers, cookies=cookies,
            timeout=timeout, allow_redirects=True
        )
        if resp.status_code != 200:
            return None
        # Cap HTML size for speed — meta tags live in <head>
        html_text = resp.text[:500_000]
    except Exception:
        return None

    def _meta(prop):
        # property="og:title" content="..." (either order)
        for pat in (
            rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']*)["\']',
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']{re.escape(prop)}["\']',
        ):
            m = re.search(pat, html_text, re.I)
            if m:
                return _html.unescape(m.group(1)).strip()
        return None

    def _named_meta(name):
        for pat in (
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)["\']',
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']{re.escape(name)}["\']',
        ):
            m = re.search(pat, html_text, re.I)
            if m:
                return _html.unescape(m.group(1)).strip()
        return None

    og_type    = _meta('og:type') or ''
    og_video   = (_meta('og:video:url')
                  or _meta('og:video:secure_url')
                  or _meta('og:video'))
    og_image   = _meta('og:image') or _meta('og:image:url')
    og_title   = _meta('og:title') or _named_meta('title') or ''
    og_desc    = _meta('og:description') or _named_meta('description') or ''

    # Fallback to <title> if OG title missing
    if not og_title:
        m = re.search(r'<title[^>]*>([^<]+)</title>', html_text, re.I)
        if m:
            og_title = _html.unescape(m.group(1)).strip()

    # Strip Facebook suffix from titles
    for suffix in (' | Facebook', ' - Facebook', ' | Facebook Watch', ' | Watch'):
        if og_title.endswith(suffix):
            og_title = og_title[:-len(suffix)].strip()

    # ---- Classify ----
    url_lower = url.lower()
    kind = 'unknown'

    if og_video:
        kind = 'video'
    elif 'video' in og_type.lower():
        kind = 'video'
    elif any(p in url_lower for p in
             ('/reel/', '/videos/', '/watch', 'fb.watch', '/share/r/', '/share/v/')):
        kind = 'video'
    elif '/albums/' in url_lower or 'set=a.' in url_lower:
        kind = 'album'
    elif any(p in url_lower for p in ('/photos/', '/photo.php', 'photo/?fbid')):
        kind = 'photo'
    elif og_image and not og_video:
        kind = 'photo'

    # ---- Extract uploader ----
    uploader = _extract_uploader_from_url(url)

    # Fallback: og:title patterns ("Photo by X on Facebook", "X - Watch", …)
    if not uploader and og_title:
        for pat in (
            r'^(?:Post|Video|Photo|Reel|Live)\s+by\s+(.+?)(?:\s+on\s+Facebook)?$',
            r'^(.+?)\s*[-–—]\s*(?:Watch|Video|Reel|Photo|Album)',
        ):
            m = re.match(pat, og_title, re.I)
            if m:
                uploader = m.group(1).strip()
                break

    return {
        'kind': kind,
        'title': og_title or None,
        'uploader': uploader,
        'description': og_desc or None,
        'og_video': og_video,
        'og_image': og_image,
    }

def _get_facebook_metadata(url, timeout=10):
    """
    Return (uploader, title) for a Facebook URL.

    Flow:
      1. Fast HTTP + OG probe (1-2 seconds, no cookies needed for public content)
      2. yt-dlp fallback (only if probe yields nothing usable)
      3. gallery-dl fallback (last resort)
    """
    # ---- 1. Fast probe ----
    probe = _fast_probe(url, timeout=min(timeout, 8))
    if probe:
        title = probe.get('title')
        uploader = probe.get('uploader')
        if uploader and uploader.lower() not in ('unknown', 'facebook', ''):
            return uploader, title

    # ---- 2. yt-dlp fallback ----
    try:
        import yt_dlp
        _ensure_cookie_file()
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
            'socket_timeout': timeout,
        }
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                uploader = (info.get('uploader') or info.get('creator')
                            or info.get('channel') or info.get('uploader_id'))
                title = (info.get('title') or info.get('description')
                         or info.get('alt_title'))
                if uploader and uploader.lower() not in ('unknown', 'facebook', ''):
                    return uploader.strip(), title
    except Exception:
        pass

    # ---- 3. gallery-dl fallback ----
    try:
        import json, subprocess
        _ensure_cookie_file()
        cookie_file = 'cookies.txt' if os.path.exists('cookies.txt') else None
        cmd = ['gallery-dl', '-j']
        if cookie_file:
            cmd.extend(['--cookies', cookie_file])
        cmd.append(url)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            first = None
            if isinstance(data, list) and data:
                item = data[0]
                if isinstance(item, list) and len(item) >= 3:
                    first = item[2]
                elif isinstance(item, dict):
                    first = item
            if first:
                uploader = (first.get('uploader') or first.get('username')
                            or first.get('owner') or first.get('author'))
                title = (first.get('title') or first.get('caption')
                         or first.get('description'))
                if uploader and uploader.lower() not in ('unknown', 'facebook', ''):
                    return uploader.strip(), title
    except Exception:
        pass

    return None, None

def _extract_facebook_uploader_from_url(url):
    """Fallback: extract username from URL (for profile URLs)."""
    import re
    match = re.search(r'facebook\.com/([^/?]+)(?:/|$)', url)
    if match:
        username = match.group(1)
        # Ignore path segments like 'share', 'photo', etc.
        if username.lower() not in ('share', 'photo', 'watch', 'reel', 'videos', 'posts', 'permalink', 'story', 'login', 'signup'):
            return username.replace('.', ' ').title()
    return "Unknown"

def _download_album_with_db(url, uploader=None):
    """Explicit album download – just download and process."""
    import subprocess, tempfile
    
    _download_single_photo(url)

    _ensure_cookie_file()
    cookie_file = 'cookies.txt' if os.path.exists('cookies.txt') else None

    with tempfile.TemporaryDirectory() as tmpdir:
        print_colored("[⏳] Downloading album...", COLORS.BLUE)
        cmd = ['gallery-dl', '--directory', tmpdir]
        if cookie_file:
            cmd.extend(['--cookies', cookie_file])
        cmd.append(url)
        proc = subprocess.Popen(cmd, stdout=None, stderr=None)
        proc.wait()
        if proc.returncode != 0:
            print_colored(f"[!] Download failed with code {proc.returncode}", COLORS.RED)
            return
        _process_album_files(tmpdir, url, uploader, probe=probe)

def _extract_facebook_title(info):
    if not info or not isinstance(info, dict):
        return None

    uploader = (info.get('uploader') or info.get('channel') or
                info.get('creator') or '').strip() or None

    t = _clean_facebook_title(info.get('title'), uploader=uploader)
    if t:
        return t

    cap = _extract_caption_from_description(info.get('description'))
    if cap:
        return cap

    if uploader:
        return f"Video from {uploader}"
    return None

def _extract_facebook_id(url):
    """Try to extract a stable ID from a Facebook URL."""
    patterns = [
        r'/watch\?v=([^&]+)',
        r'/reel/([^/?]+)',
        r'/videos/([^/?]+)',
        r'/photo\.php\?fbid=(\d+)',
        r'/permalink\.php\?story_fbid=(\d+)',
        r'/posts/(\d+)',
        r'fb\.watch/([^/?]+)',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    # fallback: use the last part of the URL
    return url.rstrip('/').split('/')[-1]

def _is_video_link(url):
    """
    Heuristic — returns True if the URL looks like a video/reel.
    Covers Facebook's many URL shapes.
    """
    if not url:
        return False
    u = url.lower()

    # ---- Definite video markers ----
    video_patterns = (
        '/watch/?v=', '/watch?v=', '/watch/',
        '/reel/', '/reels/',
        '/share/r/', '/share/v/',
        '/videos/', '/video/',
        'fb.watch/',
        'video_redirect/',
    )
    if any(p in u for p in video_patterns):
        return True

    # ---- Definite photo markers (short-circuit) ----
    photo_patterns = (
        '/photo.php', '/photo/?fbid', '/photos/',
        '/albums/', 'set=a.',
        '/share/p/',
    )
    if any(p in u for p in photo_patterns):
        return False

    # ---- Ambiguous: /posts/<id>, /permalink.php, /story.php ----
    # These can be either. Return False and let the fast probe decide.
    return False

def _download_video(url, custom_name=None, force=False, probe=None):
    from .facebook_manager import add_facebook_entry, get_facebook_entry_by_url

    existing = get_facebook_entry_by_url(url)
    if existing and not force:
        print_colored(f"[i] URL already exists (ID: {existing['id']}). Skipping.", COLORS.YELLOW)
        return

    _ensure_cookie_file()
    cookie_opt = ({'cookiefile': 'cookies.txt'} if os.path.exists('cookies.txt')
                  else {'cookiesfrombrowser': ('edge',)})

    # ---- Extract metadata: probe first, yt-dlp only as fallback ----
    title = None
    uploader = None
    facebook_id = None

    if probe:
        title = probe.get('title')
        uploader = probe.get('uploader')

    # Extract ID from URL even when probe succeeded
    facebook_id = _extract_facebook_id(url)

    # Metadata is now backfilled from the download's info dict (see below),
    # so the separate metadata-only yt-dlp pass is no longer needed.

    if not title:
        title = "Facebook Video"
    if not uploader:
        uploader = _extract_facebook_uploader_from_url(url) or "Unknown"
    if not facebook_id:
        facebook_id = _extract_facebook_id(url)

    display_title = title
    original_name = custom_name if custom_name else display_title

    import time
    temp_base = f"fb_temp_{int(time.time())}_{os.urandom(4).hex()}"
    temp_path_pattern = os.path.join(DOWNLOAD_DIR, f"{temp_base}.%(ext)s")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    ydl_opts_download = {
        'outtmpl': temp_path_pattern,
        'format': 'bestvideo+bestaudio/best',
        'verbose': True,
        'quiet': False,
        'no_warnings': True,
        'ignoreerrors': True,
        **cookie_opt,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            print_colored("[⏳] Downloading Facebook video...", COLORS.BLUE)
            # extract_info(download=True) returns the metadata dict AND
            # performs the download in a single extraction pass. The old
            # code called .download([url]) which internally re-extracts
            # everything a second time.
            _info = ydl.extract_info(url, download=True)

        # Backfill any metadata that the probe couldn't provide.
        if _info and isinstance(_info, dict):
            if not title:
                title = _extract_facebook_title(_info)
            if not uploader:
                uploader = (_info.get('uploader') or '').strip()
            if not facebook_id:
                facebook_id = _info.get('id') or _extract_facebook_id(url)
        if not title:
            title = "Facebook Video"
        if not uploader:
            uploader = _extract_facebook_uploader_from_url(url) or "Unknown"
        if not facebook_id:
            facebook_id = _extract_facebook_id(url)

        import glob
        pattern = os.path.join(DOWNLOAD_DIR, f"{temp_base}.*")
        matches = glob.glob(pattern)
        if not matches:
            print_colored("[!] Could not locate downloaded file.", COLORS.RED)
            return
        temp_path = matches[0]
        print_colored(f"[✓] Downloaded to {temp_path}", COLORS.GREEN)

        file_hash = compute_md5(temp_path)
        _, ext = os.path.splitext(temp_path)
        if not ext:
            ext = '.mp4'
        new_filename = f"{file_hash}{ext}"
        target_dir = os.path.join(ROOT_DIR, 'facebook', 'videos')
        os.makedirs(target_dir, exist_ok=True)
        final_path = os.path.join(target_dir, new_filename)

        if os.path.exists(final_path):
            os.remove(final_path)
        shutil.move(temp_path, final_path)
        print_colored(f"[✓] File stored at: {final_path}", COLORS.BLUE)

        entry_id = add_facebook_entry(
            facebook_id=facebook_id,
            entry_type='video',
            title=display_title,
            uploader=uploader,
            url=url,
            file_hash=file_hash,
            original_filename=original_name,
            notes=None,
        )
        if entry_id:
            print_colored(f"[✓] Facebook entry added (ID: {entry_id})", COLORS.GREEN)
        else:
            print_colored("[!] Database insertion failed, but file was saved.", COLORS.RED)

    except Exception as e:
        print_colored(f"[!] Download failed: {e}", COLORS.RED)

def _download_photos(url, output_dir=None):
    """
    Download all photos from a Facebook album/page/group using gallery-dl.
    This function remains unchanged – it does NOT add entries to the database.
    It's kept for quick photo album downloads.
    """
    # Ensure cookies.txt is fresh
    _ensure_cookie_file()

    cookie_file = 'cookies.txt'
    if not os.path.exists(cookie_file):
        print_colored("[!] cookies.txt not found. Please run option 23 to refresh cookies.", COLORS.RED)
        return

    # Default base directory
    if not output_dir:
        output_dir = PHOTO_BASE_DIR

    custom_dir = input(color_text(f"Output directory (default: {output_dir}): ", COLORS.MAGENTA)).strip()
    if custom_dir:
        output_dir = custom_dir

    os.makedirs(output_dir, exist_ok=True)

    # ---- Merge filename pattern into gallery-dl.conf ----
    config_file = 'gallery-dl.conf'
    config = {}

    # Load existing config if it exists
    if os.path.exists(config_file):
        try:
            import json
            with open(config_file, 'r') as f:
                config = json.load(f)
            print_colored(f"[i] Loaded existing config: {config_file}", COLORS.BLUE)
        except Exception as e:
            print_colored(f"[!] Could not parse existing config: {e}. Will create a new one.", COLORS.YELLOW)
            config = {}

    # Ensure extractor.facebook section exists
    if 'extractor' not in config:
        config['extractor'] = {}
    if 'facebook' not in config['extractor']:
        config['extractor']['facebook'] = {}

    # Set filename pattern (preserve other keys like sleep, retries)
    config['extractor']['facebook']['filename'] = "{uploader}_{date}_{caption}_{id}.{extension}"

    # Write back the config
    try:
        import json
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
        print_colored(f"[✓] Updated config with filename pattern: {config_file}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Failed to write config: {e}", COLORS.RED)
        return

    # Build gallery-dl command
    cmd = [
        'gallery-dl',
        '--cookies', cookie_file,
        '-v',
        '--config', config_file,
        '--verbose',
        '-d', output_dir,
        url
    ]

    print_colored(f"[⏳] Downloading photos from: {url}", COLORS.BLUE)
    print_colored(f"[i] Output folder: {output_dir}", COLORS.BLUE)
    print_colored("[i] Filename pattern: uploader_date_caption_id", COLORS.BLUE)
    print_colored("[i] Note: Photo albums are NOT tracked in the database.", COLORS.YELLOW)

    try:
        subprocess.run(cmd, check=True)
        print_colored(f"[✓] Photos downloaded to {output_dir}", COLORS.GREEN)
    except subprocess.CalledProcessError as e:
        print_colored(f"[!] Download failed: {e}", COLORS.RED)
    except FileNotFoundError:
        print_colored("[!] gallery-dl not found. Install with: pip install gallery-dl", COLORS.RED)

def download_facebook():
    print("\n" + "═" * 50)
    print_colored("  DOWNLOAD FROM FACEBOOK", COLORS.CYAN, bold=True)
    print("═" * 50)

    url = input(color_text("Enter Facebook video, Reel, photo, or album URL: ", COLORS.MAGENTA)).strip()
    if not url:
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    # ---- Fast probe (1-2 seconds) ----
    print_colored("[i] Detecting content type...", COLORS.BLUE)
    probe = _fast_probe(url, timeout=8)

    if probe:
        kind = probe.get('kind', 'unknown')
        title = probe.get('title')
        uploader = probe.get('uploader')
        if kind != 'unknown':
            print_colored(f"[✓] Detected: {kind.upper()}", COLORS.GREEN)
        if title:
            print(f"     Title    : {title[:80]}")
        if uploader:
            print(f"     Uploader : {uploader}")
    else:
        kind = 'unknown'
        print_colored("[i] Fast probe unavailable — falling back to URL heuristics.", COLORS.YELLOW)

    # ---- Decide route ----
    if kind == 'video':
        is_video = True
    elif kind == 'album':
        is_video = False
        is_album = True
    elif kind == 'photo':
        is_video = False
        is_album = False
    else:
        # Probe failed or ambiguous — use URL heuristic
        is_video = _is_video_link(url)
        is_album = ('/albums/' in url.lower()) or ('set=a.' in url.lower())

    # ---- Confirm with user (only in ambiguous case) ----
    if probe is None or kind == 'unknown':
        guess = 'video/Reel' if is_video else ('photo album' if is_album else 'photo')
        print_colored(f"[i] Guessing: {guess}", COLORS.YELLOW)
        override = input(color_text("Correct? (Enter=yes, 'v'=video, 'p'=photo, 'a'=album): ", COLORS.MAGENTA)).strip().lower()
        if override == 'v':
            is_video = True; is_album = False
        elif override == 'p':
            is_video = False; is_album = False
        elif override == 'a':
            is_video = False; is_album = True

    custom_name = input(color_text("Custom filename (optional, press Enter to auto-detect): ", COLORS.MAGENTA)).strip()

    # ---- Route ----
    if is_video:
        _download_video(url, custom_name if custom_name else None, probe=probe)
    elif is_album:
        _download_photos(url)
    else:
        _download_single_photo(url, custom_name if custom_name else None, probe=probe)

def _process_album_files(file_paths, url, uploader=None, title=None, probe=None):
    from .facebook_manager import add_facebook_entry
    import shutil, os, hashlib

    if not file_paths:
        return

    if not uploader or uploader == "Unknown":
        uploader = _extract_facebook_uploader_from_url(url)

    if not title:
        # Use the smart picker — og:title, then og:description caption,
        # then "Album by X", with photo count appended.
        title = _pick_album_title(probe, uploader=uploader,
                                  photo_count=len(file_paths))

    # Create a unique folder name from the URL
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    album_folder = os.path.join(ROOT_DIR, 'facebook', 'photos', url_hash)
    os.makedirs(album_folder, exist_ok=True)

    print_colored(f"[i] Processing {len(file_paths)} photos into album folder: {album_folder}", COLORS.BLUE)

    for idx, filepath in enumerate(file_paths, 1):
        print(f"  [{idx}/{len(file_paths)}] {os.path.basename(filepath)}", end="\r")
        file_hash = compute_md5(filepath)
        _, ext = os.path.splitext(filepath)
        new_name = f"{file_hash}{ext}"
        final_path = os.path.join(album_folder, new_name)

        # Remove if already exists (deduplicate)
        if os.path.exists(final_path):
            os.remove(final_path)
        shutil.move(filepath, final_path)

        # Store in DB with the same file_hash
        entry_id = add_facebook_entry(
            facebook_id=file_hash,          # unique per file
            entry_type='photo',
            title=title,
            uploader=uploader,
            url=url,
            file_hash=file_hash,
            original_filename=os.path.basename(filepath),
            notes=f"Album folder: {url_hash}"
        )
    print()  # newline after progress
    print_colored(f"[✓] Album processed: {len(file_paths)} photos added to {album_folder}.", COLORS.GREEN)

def _download_photo_direct(og_image_url, source_url, custom_name=None, probe=None, force=False):
    """
    Fast-path photo download: fetch og:image directly with requests.
    Returns True on success, False to signal "fall back to gallery-dl".
    """
    import requests, tempfile, shutil

    from .facebook_manager import add_facebook_entry, get_facebook_entry_by_url
    existing = get_facebook_entry_by_url(source_url)
    if existing and not force:
        print_colored(f"[i] URL already exists (ID: {existing['id']}). Skipping.", COLORS.YELLOW)
        return True   # nothing to do, treat as success

    uploader = (probe.get('uploader') if probe else None) \
               or _extract_facebook_uploader_from_url(source_url)
    title = (probe.get('title') if probe else None) or custom_name or "Facebook Photo"

    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/131.0.0.0 Safari/537.36'),
    }
    try:
        resp = requests.get(og_image_url, headers=headers, timeout=15, stream=True)
        if resp.status_code != 200:
            return False
        ctype = resp.headers.get('Content-Type', '').split(';')[0].strip().lower()
    except Exception:
        return False

    # Reject anything that isn't a real image (og:image occasionally points to
    # an HTML error page or a video thumbnail that we don't want as a photo).
    if not ctype.startswith('image/'):
        return False

    ext_map = {
        'image/jpeg': '.jpg', 'image/jpg': '.jpg',
        'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif',
    }
    ext = ext_map.get(ctype, '.jpg')

    # Write to temp, compute hash, move into place
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                tmp.write(chunk)
        tmp_path = tmp.name

    file_hash = compute_md5(tmp_path)
    target_dir = os.path.join(ROOT_DIR, 'facebook', 'photos')
    os.makedirs(target_dir, exist_ok=True)
    final_path = os.path.join(target_dir, f"{file_hash}{ext}")

    if os.path.exists(final_path):
        os.remove(final_path)
    shutil.move(tmp_path, final_path)
    print_colored(f"[✓] Photo stored: {final_path}", COLORS.GREEN)

    add_facebook_entry(
        facebook_id=file_hash,
        entry_type='photo',
        title=title,
        uploader=uploader,
        url=source_url,
        file_hash=file_hash,
        original_filename=custom_name or (probe.get('title') if probe else None)
                          or "Facebook Photo",
        notes=None,
    )
    return True

def _download_single_photo(url, custom_name=None, probe=None, force=False):
    from .facebook_manager import add_facebook_entry, get_facebook_entry_by_url
    import subprocess, tempfile, shutil, re

    existing = get_facebook_entry_by_url(url)
    if existing and not force:
        print_colored(f"[i] URL already exists (ID: {existing['id']}). Skipping.", COLORS.YELLOW)
        return

    # ---- Fast path: single photo with a known og:image ----
    # Facebook serves a direct image URL in og:image for every public photo
    # page. Fetching it with requests takes ~1s vs 5–15s for gallery-dl.
    # Only used when the probe is confident this is a single photo (not an
    # album, not ambiguous) and og:image is present.
    if probe and probe.get('kind') == 'photo' and probe.get('og_image'):
        print_colored("[⏳] Downloading photo directly (og:image)...", COLORS.BLUE)
        if _download_photo_direct(probe['og_image'], url, custom_name, probe, force):
            return
        print_colored("[i] Direct download failed — falling back to gallery-dl.",
                      COLORS.YELLOW)

    # ---- Metadata: probe first, fall back only if needed ----
    uploader = None
    title = None
    if probe:
        uploader = probe.get('uploader')
        title = probe.get('title')

    if not uploader or not title:
        print_colored("[i] Fetching metadata...", COLORS.BLUE)
        fb_uploader, fb_title = _get_facebook_metadata(url, timeout=10)
        uploader = uploader or fb_uploader
        title = title or fb_title

    if not uploader or uploader == "Unknown":
        uploader = _extract_facebook_uploader_from_url(url)
    if not title:
        title = _pick_photo_title(probe, uploader=uploader,
                                  custom_name=custom_name)
    if not title:
        # Absolute last resort — better than "Facebook Photo"
        title = "Facebook Photo"

    _ensure_cookie_file()
    cookie_file = 'cookies.txt' if os.path.exists('cookies.txt') else None

    with tempfile.TemporaryDirectory() as tmpdir:
        print_colored("[⏳] Downloading photo(s)...", COLORS.BLUE)
        cmd = ['gallery-dl', '-v', '--config', 'gallery-dl.conf', '--directory', tmpdir]
        if cookie_file:
            cmd.extend(['--cookies', cookie_file])
        cmd.extend(['--filename', '{id}.{extension}'])
        cmd.append(url)

        proc = subprocess.Popen(cmd, stdout=None, stderr=None)
        proc.wait()
        if proc.returncode != 0:
            print_colored(f"[!] Download failed with code {proc.returncode}", COLORS.RED)
            return

        image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
        files = []
        for root, _, fnames in os.walk(tmpdir):
            for f in fnames:
                if f.lower().endswith(image_exts):
                    files.append(os.path.join(root, f))

        if not files:
            print_colored("[!] No photo file found.", COLORS.RED)
            return

        if len(files) > 1:
            print_colored(f"[i] Detected {len(files)} photos – processing as album.", COLORS.YELLOW)
            _process_album_files(files, url, uploader, title, probe=probe)
            return

        downloaded_file = files[0]
        file_hash = compute_md5(downloaded_file)
        _, ext = os.path.splitext(downloaded_file)
        if not ext:
            ext = '.jpg'
        new_filename = f"{file_hash}{ext}"
        target_dir = os.path.join(ROOT_DIR, 'facebook', 'photos')
        os.makedirs(target_dir, exist_ok=True)
        final_path = os.path.join(target_dir, new_filename)
        if os.path.exists(final_path):
            os.remove(final_path)
        shutil.move(downloaded_file, final_path)
        print_colored(f"[✓] Photo stored: {final_path}", COLORS.GREEN)

        entry_id = add_facebook_entry(
            facebook_id=file_hash,
            entry_type='photo',
            title=title,
            uploader=uploader,
            url=url,
            file_hash=file_hash,
            original_filename=(custom_name or title or os.path.basename(downloaded_file)),
            notes=None,
        )
        if entry_id:
            print_colored(f"[✓] Facebook entry added (ID: {entry_id})", COLORS.GREEN)
        else:
            print_colored("[!] Database insertion failed, but file was saved.", COLORS.RED)
