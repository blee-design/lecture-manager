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
from .facebook_manager import add_facebook_entry, get_facebook_entry_by_url, get_facebook_file_path

DOWNLOAD_DIR = './downloads'
PHOTO_BASE_DIR = os.path.join(DOWNLOAD_DIR, 'facebook_photos')

# Organised directories
FACEBOOK_VIDEO_DIR = os.path.join(ROOT_DIR, 'facebook', 'videos')
FACEBOOK_PHOTO_DIR = os.path.join(ROOT_DIR, 'facebook', 'photos')

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
        '/share/v/',      # <-- Add this line
        '/videos/',
        '/video/',
    ]
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in video_patterns)

def _download_video(url, custom_name=None, force=False):
    from .facebook_manager import add_facebook_entry, get_facebook_entry_by_url

    # ---- Duplicate check ----
    existing = get_facebook_entry_by_url(url)
    if existing and not force:
        print_colored(f"[i] URL already exists in database (ID: {existing['id']}). Skipping download.", COLORS.YELLOW)
        return

    _ensure_cookie_file()
    cookie_opt = {'cookiefile': 'cookies.txt'} if os.path.exists('cookies.txt') else {'cookiesfrombrowser': ('edge',)}

    # ---- Step 1: Extract metadata (including ID) ----
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
                title = _extract_facebook_title(info)
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
    if not facebook_id:
        facebook_id = _extract_facebook_id(url)

    # ---- Step 2: Check if entry already exists and file is present ----
    if not force:
        existing = get_facebook_entry_by_id(facebook_id)
        if existing:
            file_path = get_facebook_file_path(existing)
            if file_path and os.path.exists(file_path):
                print_colored(f"[i] File already exists: {file_path}", COLORS.GREEN)
                # Optionally update metadata? Not needed.
                return   # <-- skip download

    # ---- Step 3: Download ----
    display_title = title
    original_name = custom_name if custom_name else display_title

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

def _process_album_files(file_paths, url, uploader):
    """Process a list of downloaded image files (hash, move, DB insert)."""
    from .facebook_manager import add_facebook_entry
    import shutil, os

    if not file_paths:
        return

    album_title = f"Album from {uploader}" if uploader != "Unknown" else "Facebook Album"
    target_dir = os.path.join(ROOT_DIR, 'facebook', 'photos')
    os.makedirs(target_dir, exist_ok=True)

    print_colored(f"[i] Processing {len(file_paths)} photos...", COLORS.BLUE)
    for idx, filepath in enumerate(file_paths, 1):
        print(f"  [{idx}/{len(file_paths)}] {os.path.basename(filepath)}", end="\r")
        file_hash = compute_md5(filepath)
        _, ext = os.path.splitext(filepath)
        new_name = f"{file_hash}{ext}"
        final_path = os.path.join(target_dir, new_name)
        if os.path.exists(final_path):
            os.remove(final_path)
        shutil.move(filepath, final_path)

        notes = f"Album from {url}"
        entry_id = add_facebook_entry(
            facebook_id=file_hash,
            entry_type='photo',
            title=album_title,
            uploader=uploader,
            url=url,
            file_hash=file_hash,
            original_filename=os.path.basename(filepath),
            notes=notes
        )
    print()  # newline after progress
    print_colored(f"[✓] Album processed: {len(file_paths)} photos added.", COLORS.GREEN)

def _download_single_photo(url, custom_name=None):
    from .facebook_manager import add_facebook_entry, get_facebook_entry_by_url
    import subprocess, tempfile, shutil, re

    # Duplicate check
    existing = get_facebook_entry_by_url(url)
    if existing:
        print_colored(f"[i] URL already exists in database (ID: {existing['id']}). Skipping download.", COLORS.YELLOW)
        return

    _ensure_cookie_file()
    cookie_file = 'cookies.txt' if os.path.exists('cookies.txt') else None

    # Extract uploader from URL
    uploader = "Unknown"
    match = re.search(r'facebook\.com/([^/]+)/', url)
    if match:
        uploader = match.group(1).replace('.', ' ').title()

    with tempfile.TemporaryDirectory() as tmpdir:
        print_colored("[⏳] Downloading photo(s)...", COLORS.BLUE)

        # Use short filename to avoid "File name too long"
        cmd = ['gallery-dl', '--config', 'gallery-dl.conf', '--directory', tmpdir]
        if cookie_file:
            cmd.extend(['--cookies', cookie_file])
        cmd.extend(['--filename', '{id}.{extension}'])   # <-- force short name
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
            _process_album_files(files, url, uploader)
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

        title = custom_name or "Facebook Photo"
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
