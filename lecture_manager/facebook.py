# facebook.py

import os
import subprocess
import shutil
import yt_dlp
from datetime import datetime
import re
from .utils import sanitize_filename, print_colored, color_text, COLORS, compute_md5
from .youtube import _ensure_cookie_file
from .file_manager import ROOT_DIR

DOWNLOAD_DIR = './downloads'
PHOTO_BASE_DIR = os.path.join(DOWNLOAD_DIR, 'facebook_photos')

# Organised directories
FACEBOOK_VIDEO_DIR = os.path.join(ROOT_DIR, 'facebook', 'videos')
FACEBOOK_PHOTO_DIR = os.path.join(ROOT_DIR, 'facebook', 'photos')

def _extract_facebook_title(info):
    if not info or not isinstance(info, dict):
        return None
    title = info.get('title', '').strip()
    generic = ['video', 'facebook video', 'reel', 'photo', '']
    if title.lower() not in generic:
        return title
    desc = info.get('description', '').strip()
    if desc:
        lines = desc.split('\n')
        first = lines[0].strip()
        if first:
            return first[:200]
    uploader = info.get('uploader', '').strip()
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
    """Heuristic to detect if a Facebook link is for a video/Reel."""
    video_patterns = [
        '/watch',
        '/reel/',
        '/share/r/',
        '/share/v/',      # <-- Add this line
        '/videos/',
        '/video/',
    ]
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in video_patterns)

def _download_video(url, custom_name=None):
    from .facebook_manager import add_facebook_entry

    _ensure_cookie_file()
    cookie_opt = {'cookiefile': 'cookies.txt'} if os.path.exists('cookies.txt') else {'cookiesfrombrowser': ('edge',)}

    # ---- Extract metadata (safe) ----
    title = None
    uploader = None
    description = None
    facebook_id = None

    try:
        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
            **cookie_opt
        }
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and isinstance(info, dict):
                title = _extract_facebook_title(info)   # our helper
                uploader = info.get('uploader', '').strip()
                description = info.get('description', '').strip()
                facebook_id = info.get('id') or _extract_facebook_id(url)
    except Exception as e:
        print_colored(f"[!] Could not fetch metadata: {e}", COLORS.YELLOW)

    # ---- Fallbacks ----
    if not title:
        title = "Facebook Video"
    if not uploader:
        uploader = "Unknown"

    # ---- Determine display title and original name ----
    display_title = title
    if custom_name:
        original_name = custom_name
    else:
        original_name = display_title

    # ---- Download with a temporary name ----
    import time
    temp_base = f"fb_temp_{int(time.time())}_{os.urandom(4).hex()}"
    temp_path_pattern = os.path.join(DOWNLOAD_DIR, f"{temp_base}.%(ext)s")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    ydl_opts_download = {
        'outtmpl': temp_path_pattern,
        'format': 'bestvideo+bestaudio/best',
        'quiet': False,
        'no_warnings': True,
        'ignoreerrors': True,
        **cookie_opt
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            print_colored(f"[⏳] Downloading Facebook video...", COLORS.BLUE)
            ydl.download([url])

        # Locate the downloaded file
        import glob
        pattern = os.path.join(DOWNLOAD_DIR, f"{temp_base}.*")
        matches = glob.glob(pattern)
        if not matches:
            print_colored("[!] Could not locate downloaded file.", COLORS.RED)
            return
        temp_path = matches[0]
        print_colored(f"[✓] Downloaded to {temp_path}", COLORS.GREEN)

        # ---- Compute hash and move ----
        file_hash = compute_md5(temp_path)
        _, ext = os.path.splitext(temp_path)
        if not ext:
            ext = '.mp4'
        new_filename = f"{file_hash}{ext}"
        os.makedirs(FACEBOOK_VIDEO_DIR, exist_ok=True)
        final_path = os.path.join(FACEBOOK_VIDEO_DIR, new_filename)

        if os.path.exists(final_path):
            os.remove(final_path)
        shutil.move(temp_path, final_path)
        print_colored(f"[✓] File stored at: {final_path}", COLORS.BLUE)

        # ---- Insert/update DB ----
        if not facebook_id:
            facebook_id = _extract_facebook_id(url)
        entry_id = add_facebook_entry(
            facebook_id=facebook_id,
            entry_type='video',
            title=display_title,
            uploader=uploader,
            url=url,
            file_hash=file_hash,
            original_filename=original_name,
            notes=None
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
        print_colored("[!] cookies.txt not found. Please run option 26 to refresh cookies.", COLORS.RED)
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
        '--config', config_file,
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
    """
    Main entry point for Facebook downloads (option 28).
    Auto-detects video, single photo, or album.
    """
    print("\n" + "═" * 50)
    print_colored("  DOWNLOAD FROM FACEBOOK", COLORS.CYAN, bold=True)
    print("═" * 50)

    url = input(color_text("Enter Facebook video, Reel, or photo album URL: ", COLORS.MAGENTA)).strip()
    if not url:
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    # 1. Check if it's a video link
    if _is_video_link(url):
        print_colored("[i] Detected as video/Reel link.", COLORS.BLUE)
        custom_name = input(color_text("Custom filename (optional, press Enter to auto-detect): ", COLORS.MAGENTA)).strip()
        _download_video(url, custom_name if custom_name else None)
        return

    # 2. Try to detect if it's an album using yt-dlp quick fetch
    try:
        import yt_dlp
        ydl_opts = {'quiet': True, 'extract_flat': True, 'ignoreerrors': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get('_type') == 'playlist':
                print_colored("[i] Detected as photo album/playlist.", COLORS.BLUE)
                _download_photos(url)
                return
    except Exception:
        pass  # fall through to single photo

    # 3. Assume single photo
    print_colored("[i] Detected as single photo link.", COLORS.BLUE)
    custom_name = input(color_text("Custom filename (optional, press Enter to auto-detect): ", COLORS.MAGENTA)).strip()
    _download_single_photo(url, custom_name if custom_name else None)

def _download_single_photo(url, custom_name=None):
    from .facebook_manager import add_facebook_entry

    _ensure_cookie_file()
    cookie_opt = {'cookiefile': 'cookies.txt'} if os.path.exists('cookies.txt') else {'cookiesfrombrowser': ('edge',)}

    # ---- Extract metadata (safe) ----
    title = None
    uploader = None
    facebook_id = None

    try:
        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
            **cookie_opt
        }
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and isinstance(info, dict):
                title = _extract_facebook_title(info)
                uploader = info.get('uploader', '').strip()
                facebook_id = info.get('id') or _extract_facebook_id(url)
    except Exception as e:
        print_colored(f"[!] Could not fetch metadata: {e}", COLORS.YELLOW)

    # ---- Fallbacks ----
    if not title:
        title = "Facebook Photo"
    if not uploader:
        uploader = "Unknown"

    display_title = title
    original_name = custom_name if custom_name else display_title

    # ---- Download with temporary name ----
    import time
    temp_base = f"fb_photo_temp_{int(time.time())}_{os.urandom(4).hex()}"
    temp_path_pattern = os.path.join(DOWNLOAD_DIR, f"{temp_base}.%(ext)s")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    ydl_opts_download = {
        'outtmpl': temp_path_pattern,
        'format': 'best',
        'quiet': False,
        'no_warnings': True,
        'ignoreerrors': True,
        **cookie_opt
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            ydl.download([url])
    except Exception as e:
        print_colored(f"[!] Download failed: {e}", COLORS.RED)
        return

    # Locate downloaded file
    import glob
    pattern = os.path.join(DOWNLOAD_DIR, f"{temp_base}.*")
    matches = glob.glob(pattern)
    if not matches:
        print_colored("[!] Could not locate downloaded file.", COLORS.RED)
        return
    temp_path = matches[0]

    # ---- Compute hash and move ----
    file_hash = compute_md5(temp_path)
    _, ext = os.path.splitext(temp_path)
    if not ext:
        ext = '.jpg'
    new_filename = f"{file_hash}{ext}"
    os.makedirs(FACEBOOK_PHOTO_DIR, exist_ok=True)
    final_path = os.path.join(FACEBOOK_PHOTO_DIR, new_filename)
    shutil.move(temp_path, final_path)
    print_colored(f"[✓] Photo stored at: {final_path}", COLORS.BLUE)

    # ---- Insert/update DB ----
    if not facebook_id:
        facebook_id = _extract_facebook_id(url)
    entry_id = add_facebook_entry(
        facebook_id=facebook_id,
        entry_type='photo',
        title=display_title,
        uploader=uploader,
        url=url,
        file_hash=file_hash,
        original_filename=original_name,
        notes=None
    )
    if entry_id:
        print_colored(f"[✓] Facebook entry added (ID: {entry_id})", COLORS.GREEN)
    else:
        print_colored("[!] Database insertion failed, but file was saved.", COLORS.RED)
