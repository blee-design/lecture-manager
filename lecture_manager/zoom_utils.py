# lecture_manager/zoom_utils.py

import re
import urllib.parse

def parse_zoom_invite(dirty_text: str) -> dict:
    """
    Extracts Zoom meeting details from messy text.
    Returns a dictionary with keys: url, meeting_id, passcode, domain.
    Returns an empty dictionary if no Zoom data is found.
    """
    if not dirty_text:
        return {}

    # Decode URL encoding just in case (e.g., %20 -> space)
    decoded = urllib.parse.unquote(dirty_text)

    result = {
        "url": None,
        "meeting_id": None,
        "passcode": None,
        "domain": "zoom.us"
    }

    # ---- 1. Find the Domain (default to zoom.us) ----
    domain_match = re.search(r'(?:https?://)?([a-zA-Z0-9.-]*zoom\.(?:us|com|cn|gov)[a-zA-Z0-9./-]*)', decoded, re.IGNORECASE)
    if domain_match:
        result["domain"] = domain_match.group(1).split('/')[0]

    # ---- 2. Extract Meeting ID ----
    # Look for standard formats: mn=123456789, Meeting ID: 123 456 7890, /j/123456789
    mn_patterns = [
        r'/j/(\d{9,11})',
        r'/w/(\d{9,11})',
        r'(?:Meeting ID|mn|id)[\s:=]*([0-9\s-]{9,15})'
    ]

    for pattern in mn_patterns:
        match = re.search(pattern, decoded, re.IGNORECASE)
        if match:
            # Strip spaces and hyphens
            raw_id = re.sub(r'[\s-]', '', match.group(1))
            if 9 <= len(raw_id) <= 11:
                result["meeting_id"] = raw_id
                break

    # ---- 3. Extract Passcode ----
    # Look for pwd=abc, Passcode: abc123
    pwd_patterns = [
        r'[?&]pwd=([a-zA-Z0-9._-]+)',
        r'(?:Passcode|Password|pwd)[\s:=]*([a-zA-Z0-9._-]+)'
    ]
    for pattern in pwd_patterns:
        match = re.search(pattern, decoded, re.IGNORECASE)
        if match:
            # Prevent matching "Passcode:" with empty space
            pwd = match.group(1).strip()
            if pwd and pwd.lower() not in ('required', 'none'):
                result["passcode"] = pwd
                break

    # ---- 4. Construct Clean URL ----
    if result["meeting_id"]:
        # Determine if it's a webinar or regular meeting based on the text
        path = "w" if "/w/" in decoded else "j"
        base_url = f"https://{result['domain']}/{path}/{result['meeting_id']}"
        if result["passcode"]:
            base_url += f"?pwd={result['passcode']}"
        result["url"] = base_url

    # Fallback: if no ID found, but a clean URL exists, try to use it
    elif "zoom.us" in decoded:
        url_match = re.search(r'(https?://[a-zA-Z0-9.-]*zoom\.(?:us|com|cn|gov)[a-zA-Z0-9./?=&_%-]+)', decoded)
        if url_match:
            result["url"] = url_match.group(1)

    return result


def extract_zoom_link(dirty_text: str) -> str:
    """Backward compatibility wrapper for the old function."""
    parsed = parse_zoom_invite(dirty_text)
    if parsed.get("url"):
        return parsed["url"]
    elif parsed.get("meeting_id"):
        return f"https://zoom.us/j/{parsed['meeting_id']}"
    else:
        return "Could not find a valid Zoom Meeting ID or Link."


def interactive_zoom_extractor():
    """Interactive CLI function to extract Zoom link from user input."""
    print("\n" + "═" * 60)
    print_colored("🔗 SMART ZOOM MEETING EXTRACTOR", COLORS.CYAN, bold=True)
    print("═" * 60)
    print("Paste the messy Zoom text (IDs with spaces, separate passwords, etc.)")
    print("and I'll build a clean, clickable Zoom link for you.")
    print("Type 'exit' or press Ctrl+C to cancel.\n")

    # Import here to avoid circular imports if utils imports zoom_utils
    from .utils import print_colored, COLORS, color_text

    while True:
        try:
            dirty = input("📋 Paste Zoom text (or 'exit'): ").strip()
        except KeyboardInterrupt:
            print("\nCancelled.")
            break
        if not dirty:
            continue
        if dirty.lower() in ('exit', 'quit', 'q'):
            break

        result = parse_zoom_invite(dirty)

        if not result.get("url"):
            print_colored("❌ Could not find a valid Zoom Meeting ID or Link in that text.", COLORS.RED)
        else:
            print("\n✅ Clean Zoom Link:")
            print(color_text(f"   {result['url']}", COLORS.GREEN, bold=True))

            # Show the breakdown so the user can verify
            print("\n   📋 Extracted Details:")
            if result.get("meeting_id"):
                print(f"      • Meeting ID : {result['meeting_id']}")
            if result.get("passcode"):
                print(f"      • Passcode   : {result['passcode']}")
            if result.get("domain") and result['domain'] != 'zoom.us':
                print(f"      • Domain     : {result['domain']}")

            print("\n   (You can now copy the link above.)")
        print("─" * 60)
