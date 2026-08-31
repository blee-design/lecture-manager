# lecture_manager/zoom_utils.py

import re
import urllib.parse

def extract_zoom_link(dirty_text: str) -> str:
    """
    Extract a clean Zoom meeting link from messy text.

    Supports:
      - Meeting number: mn=123456789 or id=123456789 or /j/123456789
      - Password: pwd=xxxxxx (URL-encoded or plain)
      - Also handles: zoom.us/j/123456789?pwd=xxxxxx

    Returns:
        Clean Zoom URL as a string, or an error message if not found.
    """
    if not dirty_text:
        return "No text provided."

    # Normalize: decode URL encoding in the whole text
    decoded = urllib.parse.unquote(dirty_text)

    # Pattern 1: zoom.us/j/... with optional pwd
    # Example: https://zoom.us/j/123456789?pwd=xyz
    match = re.search(r'(https?://zoom\.us/j/(\d+)(?:\?pwd=([^&\s]+))?)', decoded, re.IGNORECASE)
    if match:
        full_url = match.group(1)
        meeting_id = match.group(2)
        pwd = match.group(3)
        if pwd:
            # Ensure password is included in the clean link
            # Sometimes the full_url already contains it, but we can reconstruct.
            return f"https://zoom.us/j/{meeting_id}?pwd={pwd}"
        else:
            return f"https://zoom.us/j/{meeting_id}"

    # Pattern 2: meeting number and password separate
    # e.g., mn=123456789 or id=123456789
    mn_match = re.search(r'(?:mn|id)[:=](\d+)', decoded, re.IGNORECASE)
    if not mn_match:
        return "Could not find a valid Meeting Number (mn) in the text."

    meeting_id = mn_match.group(1)

    # Look for password: pwd=xxxxx (may be URL-encoded)
    pwd_match = re.search(r'pwd=([^&\s]+)', decoded, re.IGNORECASE)
    password = pwd_match.group(1) if pwd_match else None

    # Build the clean link
    clean_link = f"https://zoom.us/j/{meeting_id}"
    if password:
        clean_link += f"?pwd={password}"

    return clean_link


def interactive_zoom_extractor():
    """Interactive CLI function to extract Zoom link from user input."""
    print("\n" + "═" * 60)
    print("🔗 ZOOM MEETING LINK EXTRACTOR")
    print("═" * 60)
    print("Paste the messy Zoom text (meeting number, password, etc.)")
    print("and I'll extract a clean, clickable Zoom link.")
    print("Type 'exit' or press Ctrl+C to cancel.\n")

    while True:
        try:
            dirty = input("📋 Paste text (or 'exit'): ").strip()
        except KeyboardInterrupt:
            print("\nCancelled.")
            break
        if not dirty:
            continue
        if dirty.lower() in ('exit', 'quit', 'q'):
            break

        clean = extract_zoom_link(dirty)
        if clean.startswith("Could not"):
            print(f"❌ {clean}")
        else:
            print("\n✅ Your clean Zoom link:")
            print(f"   {clean}\n")
            # Ask if they want to copy to clipboard? Not easily in terminal, but we can show.
            print("(You can now copy the link above.)")
        print("-" * 60)
