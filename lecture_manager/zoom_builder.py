# File zoom_builder.py

import re
import urllib.parse
import readline

def extract_zoom_link(dirty_text):
    # Search for the meeting number (accepts 'mn=' or '?id=' formats)
    mn_match = re.search(r'(?:mn|id)[:=](\d+)', dirty_text)

    # Search for the password (stops extracting at the next '&' symbol or space)
    pwd_match = re.search(r'pwd=([^&\s]+)', dirty_text)

    if not mn_match:
        return "Could not find a valid Meeting Number (mn) in the text."

    meeting_id = mn_match.group(1)

    # Clean up the password if found (handles HTML URL encoding like %21 to !)
    password = urllib.parse.unquote(pwd_match.group(1)) if pwd_match else None

    # Construct the base working URL
    clean_link = f"https://zoom.us/j/{meeting_id}"

    # Attach password parameter if it exists
    if password:
        clean_link += f"?pwd={password}"

    return clean_link



# Run the function and print the result
# Instead of hardcoding the data, the script will ask you for it in the terminal
print("Paste your messy Zoom text here and press Enter:")
raw_data = input()

# Run the function and print the result
working_url = extract_zoom_link(raw_data)
print("\n👉 Your Working Zoom Link:")
print(working_url)
