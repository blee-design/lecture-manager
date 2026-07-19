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

def _get_facebook_metadata(url, timeout=10):
    """Get uploader and title using yt-dlp (primary) then gallery-dl."""
    # 1. Try yt-dlp (works for videos and many photo posts)
    try:
        import yt_dlp
        _ensure_cookie_file()
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
        }
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                uploader = (info.get('uploader') or info.get('creator') or
                            info.get('channel') or info.get('uploader_id'))
                title = info.get('title') or info.get('description') or info.get('alt_title')
                if uploader and uploader.lower() not in ('unknown', 'facebook', ''):
                    # Clean uploader
                    uploader = uploader.strip()
                    return uploader, title
    except Exception as e:
        # Silently fall through
        pass

    # 2. Fallback: gallery-dl -j
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
                uploader = first.get('uploader') or first.get('username') or first.get('owner') or first.get('author')
                title = first.get('title') or first.get('caption') or first.get('description')
                if uploader and uploader.lower() not in ('unknown', 'facebook', ''):
                    uploader = uploader.strip()
                    return uploader, title
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
        _process_album_files(tmpdir, url, uploader)

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
        '/share/v/',
        '/videos/',
        '/video/',
    ]
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in video_patterns)

def _download_video(url, custom_name=None, force=False):
    from .facebook_manager import add_facebook_entry, get_facebook_entry_by_url

    existing = get_facebook_entry_by_url(url)
    if existing and not force:
        print_colored(f"[i] URL already exists (ID: {existing['id']}). Skipping.", COLORS.YELLOW)
        return

    _ensure_cookie_file()
    cookie_opt = {'cookiefile': 'cookies.txt'} if os.path.exists('cookies.txt') else {'cookiesfrombrowser': ('edge',)}

    # Extract metadata
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

    if not title:
        title = "Facebook Video"
    if not uploader:
        uploader = "Unknown"
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
        **cookie_opt
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            print_colored(f"[⏳] Downloading Facebook video...", COLORS.BLUE)
            ydl.download([url])

        import glob
        pattern = os.path.join(DOWNLOAD_DIR, f"{temp_base}.*")
        matches = glob.glob(pattern)
        if not matches:
            print_colored("[!] Could not locate downloaded file.", COLORS.RED)
            return
        temp_path = matches[0]
        print_colored(f"[✓] Downloaded to {temp_path}", COLORS.GREEN)

        # Compute hash and move
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

        # Insert DB
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

    if _is_video_link(url):
        print_colored("[i] Detected as video/Reel link.", COLORS.BLUE)
        custom_name = input(color_text("Custom filename (optional, press Enter to auto-detect): ", COLORS.MAGENTA)).strip()
        _download_video(url, custom_name if custom_name else None)
    else:
        custom_name = input(color_text("Custom filename (optional, press Enter to auto-detect): ", COLORS.MAGENTA)).strip()
        _download_single_photo(url, custom_name if custom_name else None)

def _process_album_files(file_paths, url, uploader=None, title=None):
    from .facebook_manager import add_facebook_entry
    import shutil, os, hashlib

    if not file_paths:
        return

    if not uploader or uploader == "Unknown":
        uploader = _extract_facebook_uploader_from_url(url)

    if not title:
        title = f"Album from {uploader}" if uploader != "Unknown" else "Facebook Album"

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

def _download_single_photo(url, custom_name=None):
    from .facebook_manager import add_facebook_entry, get_facebook_entry_by_url
    import subprocess, tempfile, shutil, re

    existing = get_facebook_entry_by_url(url)
    if existing:
        print_colored(f"[i] URL already exists (ID: {existing['id']}). Skipping.", COLORS.YELLOW)
        return

    # Get metadata (uploader, title) with a 10‑second timeout
    uploader, title = _get_facebook_metadata(url, timeout=10)
    if not uploader or uploader == "Unknown":
        uploader = _extract_facebook_uploader_from_url(url)
    if not title:
        title = custom_name or "Facebook Photo"

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

        # Collect image files
        image_exts = ('.jpg','.jpeg','.png','.gif','.bmp','.webp')
        files = []
        for root, _, fnames in os.walk(tmpdir):
            for f in fnames:
                if f.lower().endswith(image_exts):
                    files.append(os.path.join(root, f))

        if not files:
            print_colored("[!] No photo file found.", COLORS.RED)
            return

        # If multiple → album
        if len(files) > 1:
            print_colored(f"[i] Detected {len(files)} photos – processing as album.", COLORS.YELLOW)
            _process_album_files(files, url, uploader, title)   # pass title
            return

        # Single photo
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
            original_filename=os.path.basename(downloaded_file),
            notes=None
        )
        if entry_id:
            print_colored(f"[✓] Facebook entry added (ID: {entry_id})", COLORS.GREEN)
        else:
            print_colored("[!] Database insertion failed, but file was saved.", COLORS.RED)
