# lecture_manager/instapaper.py

import re
import time
import requests
import readline
from readability import Document
import html2text
from .db import get_connection
from .utils import print_colored, COLORS, color_text

import requests
from requests.auth import HTTPBasicAuth
resp = requests.get(
    'https://www.instapaper.com/api/authenticate',
    auth=HTTPBasicAuth('your_username', 'your_password')
)
print(resp.status_code)  # Should be 200 if credentials are valid

TABLE_NAME = "instapaper_credentials"
ARTICLE_TABLE = "instapaper_articles"

# ----- Database helpers -----
def get_credentials():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def save_credentials(consumer_key, consumer_secret, username, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        REPLACE INTO {TABLE_NAME} (id, consumer_key, consumer_secret, username, password)
        VALUES (1, %s, %s, %s, %s)
    """, (consumer_key, consumer_secret, username, password))
    conn.commit()
    cursor.close()
    conn.close()

# ----- OAuth / xAuth -----
def get_instapaper_access_token():
    """Perform xAuth OAuth and return (access_token, access_secret)."""
    from requests_oauthlib import OAuth1Session
    creds = get_credentials()
    if not creds:
        return None, None

    # If we already have tokens, return them
    if creds.get('oauth_token') and creds.get('oauth_secret'):
        return creds['oauth_token'], creds['oauth_secret']

    # Otherwise, exchange username/password for tokens
    session = OAuth1Session(creds['consumer_key'], creds['consumer_secret'])
    data = {
        "x_auth_username": creds['username'],
        "x_auth_password": creds['password'],
        "x_auth_mode": "client_auth"
    }
    resp = session.post("https://www.instapaper.com/api/1/oauth/access_token", data=data)
    if resp.status_code != 200:
        print_colored(f"[!] xAuth failed: {resp.text}", COLORS.RED)
        return None, None
    token_data = dict(pair.split('=') for pair in resp.text.split('&'))
    oauth_token = token_data['oauth_token']
    oauth_secret = token_data['oauth_secret']

    # Store tokens in DB for future use
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE instapaper_credentials
        SET oauth_token = %s, oauth_secret = %s
        WHERE id = 1
    """, (oauth_token, oauth_secret))
    conn.commit()
    cursor.close()
    conn.close()
    return oauth_token, oauth_secret

# ----- Article fetching and storage -----
def fetch_article_text(url):
    """Extract clean article text using readability-lxml with proper headers."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    # Create a session with retry logic
    session = requests.Session()
    session.headers.update(headers)

    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()

        # If we get here, the request was successful
        doc = Document(resp.text)
        title = doc.title() or "Untitled"
        content = doc.summary()

        return {
            'title': title,
            'author': '',
            'text': content,
            'summary': '',
            'top_image': '',
            'publish_date': None
        }
    except requests.exceptions.Timeout:
        print_colored(f"[!] Timeout fetching {url}", COLORS.YELLOW)
        return None
    except requests.exceptions.RequestException as e:
        print_colored(f"[!] Failed to fetch article: {e}", COLORS.RED)
        return None

def store_article_locally(url, title, author, content):
    import hashlib
    bookmark_id = hashlib.md5(url.encode()).hexdigest()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO instapaper_articles (bookmark_id, url, title, author, content)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            title = VALUES(title),
            author = VALUES(author),
            content = VALUES(content),
            updated_at = NOW()
    """, (bookmark_id, url, title, author, content))
    conn.commit()
    cursor.close()
    conn.close()

# ----- Main save function (Simple API + local storage) -----
def add_to_instapaper(url, title=None, tags=None):
    creds = get_credentials()
    if not creds:
        return False, "No credentials found. Run setup first."

    # ----- Test credentials first (optional) -----
    test_resp = requests.get(
        "https://www.instapaper.com/api/authenticate",
        auth=HTTPBasicAuth(creds['username'], creds['password'])
    )
    if test_resp.status_code != 200:
        return False, "❌ Invalid Instapaper username/password. Please check credentials."

    # ----- Save to Instapaper (Simple API) -----
    endpoint = "https://www.instapaper.com/api/add"
    data = {"url": url}
    if title:
        data["title"] = title
    if tags:
        data["tags"] = tags

    try:
        resp = requests.post(
            endpoint,
            data=data,
            auth=HTTPBasicAuth(creds['username'], creds['password']),
            timeout=10
        )
        if resp.status_code == 201:
            # Saved to Instapaper – now fetch and store locally
            article_data = fetch_article_text(url)
            if article_data:
                store_article_locally(url, article_data['title'], article_data['author'], article_data['text'])
                return True, "✅ Saved to Instapaper and stored offline."
            else:
                return True, "✅ Saved to Instapaper (but content could not be fetched)."
        elif resp.status_code == 403:
            return False, "❌ Forbidden: check your username/password or app permissions."
        else:
            return False, f"❌ Instapaper error {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, f"Connection error: {e}"

# ----- Full API: fetch all bookmarks -----
def fetch_all_bookmarks(limit=500, offset=0):
    """Fetch all bookmarks from Instapaper using Full API."""
    oauth_token, oauth_secret = get_instapaper_access_token()
    if not oauth_token or not oauth_secret:
        return False, "OAuth tokens missing. Run xAuth first."

    creds = get_credentials()
    from requests_oauthlib import OAuth1Session
    session = OAuth1Session(
        creds['consumer_key'],
        creds['consumer_secret'],
        oauth_token,
        oauth_secret
    )

    params = {'limit': limit, 'offset': offset}
    resp = session.get("https://www.instapaper.com/api/1/bookmarks/list", params=params)
    if resp.status_code != 200:
        return False, f"API error: {resp.text}"

    bookmarks = resp.json()
    total = len(bookmarks)
    print_colored(f"[i] Found {total} bookmarks. Syncing...", COLORS.BLUE)
    for idx, bm in enumerate(bookmarks, 1):
        url = bm.get('url')
        if not url:
            continue
        print(f"  [{idx}/{total}] {bm.get('title', 'Untitled')[:50]}...", end="\r")
        article_data = fetch_article_text(url)
        if article_data:
            store_article_locally(
                url,
                article_data['title'] or bm.get('title', ''),
                article_data['author'],
                article_data['text']
            )
    print()
    return True, f"Synced {total} bookmarks to local database."

# ----- Local CRUD functions -----
def list_articles(limit=20):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, title, author, url, saved_at, updated_at
        FROM instapaper_articles
        ORDER BY saved_at DESC
        LIMIT %s
    """, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_article_by_id(article_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM instapaper_articles WHERE id = %s", (article_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def delete_article(article_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM instapaper_articles WHERE id = %s", (article_id,))
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    return affected > 0

def refresh_article(article_id):
    """Re‑fetch the article content and update the local DB."""
    article = get_article_by_id(article_id)
    if not article:
        return False, "Article not found."
    url = article['url']
    article_data = fetch_article_text(url)
    if not article_data:
        return False, "Failed to fetch new content."
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE instapaper_articles
        SET title = %s, author = %s, content = %s, updated_at = NOW()
        WHERE id = %s
    """, (article_data['title'], article_data['author'], article_data['text'], article_id))
    conn.commit()
    cursor.close()
    conn.close()
    return True, "Article refreshed."

# ----- Interactive functions -----
def _mask_string(s, show=4):
    if not s:
        return "(empty)"
    if len(s) <= show:
        return "*" * len(s)
    return s[:show] + "*" * (len(s) - show)

def _full_setup():
    """Prompt for all 4 credentials and save them."""
    print("\n" + "═" * 50)
    print_colored("  INSTAPAPER SETUP", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("We need your Instapaper app credentials and login.")
    print("Get Consumer Key/Secret from: https://www.instapaper.com/developers")
    print("═" * 50)

    consumer_key = input(color_text("Consumer Key: ", COLORS.MAGENTA)).strip()
    consumer_secret = input(color_text("Consumer Secret: ", COLORS.MAGENTA)).strip()
    username = input(color_text("Instapaper Username: ", COLORS.MAGENTA)).strip()
    password = input(color_text("Instapaper Password: ", COLORS.MAGENTA)).strip()

    if not all([consumer_key, consumer_secret, username, password]):
        print_colored("[!] All fields are required. Setup cancelled.", COLORS.RED)
        return False

    save_credentials(consumer_key, consumer_secret, username, password)
    print_colored("[✓] Instapaper credentials saved successfully.", COLORS.GREEN)
    return True

def edit_credentials_interactive():
    creds = get_credentials()
    if not creds:
        return _full_setup()

    updated = creds.copy()
    changed = False

    while True:
        print("\n" + "═" * 50)
        print_colored("  EDIT INSTAPAPER CREDENTIALS", COLORS.CYAN, bold=True)
        print("═" * 50)
        print(f"  1. Consumer Key    : {_mask_string(updated['consumer_key'], 6)}")
        print(f"  2. Consumer Secret : {_mask_string(updated['consumer_secret'], 4)}")
        print(f"  3. Username        : {_mask_string(updated['username'], 4)}")
        print(f"  4. Password        : {_mask_string(updated['password'], 2)}")
        print("  0. Save changes and exit")
        print("  c. Cancel and discard changes")
        print("═" * 50)

        choice = input(color_text("Choose a field (1-4), 0 to save, or c to cancel: ", COLORS.MAGENTA)).strip().lower()

        if choice == '0':
            if not changed:
                print_colored("[i] No changes made.", COLORS.YELLOW)
                return True
            save_credentials(
                updated['consumer_key'],
                updated['consumer_secret'],
                updated['username'],
                updated['password']
            )
            print_colored("[✓] Credentials updated and saved.", COLORS.GREEN)
            return True

        if choice == 'c':
            if changed:
                confirm = input(color_text("Discard changes? (y/n): ", COLORS.RED)).strip().lower()
                if confirm == 'y':
                    print_colored("[i] Changes discarded.", COLORS.YELLOW)
                    return True
                else:
                    continue
            else:
                print_colored("[i] No changes to discard.", COLORS.YELLOW)
                return True

        if choice not in ('1', '2', '3', '4'):
            print_colored("[!] Invalid choice.", COLORS.RED)
            continue

        field_map = {
            '1': 'consumer_key',
            '2': 'consumer_secret',
            '3': 'username',
            '4': 'password'
        }
        field = field_map[choice]
        current = updated.get(field, '')
        display_current = _mask_string(current, 4) if field in ('consumer_secret', 'password') else current

        new_val = input(color_text(f"New {field.replace('_', ' ').title()} [{display_current}]: ", COLORS.MAGENTA)).strip()
        if new_val:
            updated[field] = new_val
            changed = True
            print_colored(f"[✓] {field} updated (not saved yet).", COLORS.GREEN)
        else:
            print_colored("[i] No change made.", COLORS.YELLOW)

def save_lecture_question():
    print("\nWhat do you want to save to Instapaper?")
    print("  1. A YouTube lecture (by ID)")
    print("  2. A question (by ID)")
    print("  3. A custom URL (news article, blog, etc.)")
    sub = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if sub == '1':
        vid = input(color_text("Enter Video ID, Syllabus ID, or mirror ID: ", COLORS.MAGENTA)).strip()
        if not vid:
            return
        from .db import get_record_by_any_id
        rec = get_record_by_any_id(vid)
        if not rec:
            print_colored("[!] Record not found.", COLORS.RED)
            return
        url = f"https://youtu.be/{rec['video_id']}"
        title = rec.get('original_filename') or rec.get('video_title') or f"Lecture {rec['syllabus_id']}"
        tags = f"lecture,{rec.get('subject', '')}"
        ok, msg = add_to_instapaper(url, title=title, tags=tags)
        print_colored(msg, COLORS.GREEN if ok else COLORS.RED)
    elif sub == '2':
        qid = input(color_text("Enter question ID: ", COLORS.MAGENTA)).strip()
        if not qid or not qid.isdigit():
            print_colored("[!] Invalid ID.", COLORS.RED)
            return
        from .question_bank import get_question_by_id
        q = get_question_by_id(int(qid))
        if not q:
            print_colored("[!] Question not found.", COLORS.RED)
            return
        title = f"{q['institution']} {q['level']} Q{q['question_number']} – {q['subject']}"
        url = f"http://localhost:5000/question/{qid}"
        tags = f"question,{q['subject']}"
        ok, msg = add_to_instapaper(url, title=title, tags=tags)
        print_colored(msg, COLORS.GREEN if ok else COLORS.RED)
    elif sub == '3':
        url = input(color_text("Enter the full URL: ", COLORS.MAGENTA)).strip()
        if not url:
            print_colored("[!] URL cannot be empty.", COLORS.RED)
            return
        title = input(color_text("Optional title (press Enter to auto-detect): ", COLORS.MAGENTA)).strip()
        tags = input(color_text("Optional tags (comma‑separated, e.g. 'news,finance'): ", COLORS.MAGENTA)).strip()
        ok, msg = add_to_instapaper(url, title=title or None, tags=tags or None)
        print_colored(msg, COLORS.GREEN if ok else COLORS.RED)
    else:
        print_colored("[!] Invalid choice.", COLORS.RED)

def list_articles_interactive():
    articles = list_articles(limit=20)
    if not articles:
        print_colored("[i] No saved articles found.", COLORS.YELLOW)
        return
    print("\n" + "═" * 60)
    print_colored("  SAVED ARTICLES (latest 20)", COLORS.CYAN, bold=True)
    print("═" * 60)
    for art in articles:
        # Convert datetime to string safely
        saved_at_str = art['saved_at'].strftime('%Y-%m-%d') if art['saved_at'] else 'Unknown'
        title = art['title'] or 'Untitled'
        # Truncate title if too long
        if len(title) > 50:
            title = title[:47] + '...'
        print(f"  ID: {art['id']:3} | {title:70} | {saved_at_str}")
    print("═" * 60)

def read_article_interactive():
    article_id = input(color_text("Enter article ID to read: ", COLORS.MAGENTA)).strip()
    if not article_id or not article_id.isdigit():
        print_colored("[!] Invalid ID.", COLORS.RED)
        return
    article = get_article_by_id(int(article_id))
    if not article:
        print_colored("[!] Article not found.", COLORS.RED)
        return

    content = article['content']
    if not content:
        print_colored("[!] No content stored.", COLORS.YELLOW)
        return

    # Convert HTML to well-formatted plain text
    h = html2text.HTML2Text()
    h.body_width = 0        # Don't wrap lines
    h.ignore_links = False  # Show links in brackets
    plain_text = h.handle(content).strip()

    saved_at_str = article['saved_at'].strftime('%Y-%m-%d %H:%M') if article['saved_at'] else 'Unknown'

    print("\n" + "═" * 60)
    print_colored(f"  {article['title'] or 'Untitled'}", COLORS.CYAN, bold=True)
    print_colored(f"  By: {article['author'] or 'Unknown'}", COLORS.BLUE)
    print(f"  URL: {article['url']}")
    print(f"  Saved: {saved_at_str}")
    print("═" * 60)

    if len(plain_text) > 2000:
        use_less = input(color_text("Content is long. View with 'less'? (y/n): ", COLORS.MAGENTA)).strip().lower()
        if use_less == 'y':
            import subprocess, os
            pager = os.popen('less', 'w')
            pager.write(plain_text)
            pager.close()
        else:
            print(plain_text)
    else:
        print(plain_text)
    print("═" * 60)

def refresh_article_interactive():
    article_id = input(color_text("Enter article ID to refresh: ", COLORS.MAGENTA)).strip()
    if not article_id or not article_id.isdigit():
        print_colored("[!] Invalid ID.", COLORS.RED)
        return
    ok, msg = refresh_article(int(article_id))
    print_colored(msg, COLORS.GREEN if ok else COLORS.RED)

def delete_article_interactive():
    article_id = input(color_text("Enter article ID to delete: ", COLORS.MAGENTA)).strip()
    if not article_id or not article_id.isdigit():
        print_colored("[!] Invalid ID.", COLORS.RED)
        return
    confirm = input(color_text(f"Delete article {article_id}? (y/n): ", COLORS.RED)).strip().lower()
    if confirm == 'y':
        if delete_article(int(article_id)):
            print_colored("[✓] Article deleted.", COLORS.GREEN)
        else:
            print_colored("[!] Deletion failed (maybe not found).", COLORS.RED)

# ----- Main menu -----
def instapaper_menu():
    """Main interactive menu for Instapaper."""
    while True:
        creds = get_credentials()
        if not creds:
            print_colored("[i] No credentials found. Starting setup...", COLORS.YELLOW)
            if not _full_setup():
                return

        print("\n" + "═" * 50)
        print_colored("  INSTAPAPER MANAGER", COLORS.CYAN, bold=True)
        print("═" * 50)
        print("  1. Save a lecture/question")
        print("  2. List saved articles (offline)")
        print("  3. Read an article (by ID)")
        print("  4. Refresh/Update an article (re‑fetch content)")
        print("  5. Delete an article")
        print("  6. Edit credentials")
        print("  8. Sync all bookmarks from Instapaper (Full API)")
        print("  0. Cancel (return to main menu)")
        print("═" * 50)

        choice = input(color_text("Choose (0-8): ", COLORS.MAGENTA)).strip()

        if choice == '0':
            print_colored("[i] Returning to main menu.", COLORS.YELLOW)
            return
        elif choice == '1':
            save_lecture_question()
        elif choice == '2':
            list_articles_interactive()
        elif choice == '3':
            read_article_interactive()
        elif choice == '4':
            refresh_article_interactive()
        elif choice == '5':
            delete_article_interactive()
        elif choice == '6':
            edit_credentials_interactive()
        elif choice == '8':
            print_colored("[i] Fetching all bookmarks from Instapaper...", COLORS.BLUE)
            ok, msg = fetch_all_bookmarks()
            print_colored(msg, COLORS.GREEN if ok else COLORS.RED)
        else:
            print_colored("[!] Invalid choice.", COLORS.RED)

        input("\nPress Enter to continue...")

# Alias for backward compatibility
manage_credentials_interactive = instapaper_menu
