# lecture_manager/instapaper.py

import os
import re
import time
import requests
import html2text
from readability import Document
from requests_oauthlib import OAuth1Session

from .db import get_connection
from .utils import print_colored, COLORS, color_text

CRED_TABLE = "instapaper_credentials"
OAUTH_TABLE = "instapaper_oauth"
ARTICLE_TABLE = "instapaper_articles"

API_BASE = "https://www.instapaper.com/api/1"
AUTHORIZE_URL = "https://www.instapaper.com/authorize"
ACCESS_TOKEN_URL = f"{API_BASE}/oauth/access_token"

# ==========================================
#  AUTHENTICATION & API SESSIONS
# ==========================================

def get_oauth_tokens():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT oauth_token, oauth_secret FROM {OAUTH_TABLE} WHERE id = 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return (row['oauth_token'], row['oauth_secret']) if row else (None, None)

def save_oauth_tokens(oauth_token, oauth_secret):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"REPLACE INTO {OAUTH_TABLE} (id, oauth_token, oauth_secret) VALUES (1, %s, %s)", (oauth_token, oauth_secret))
    conn.commit()
    cursor.close()
    conn.close()

def get_credentials():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {CRED_TABLE} WHERE id = 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def save_credentials(consumer_key, consumer_secret):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"REPLACE INTO {CRED_TABLE} (id, consumer_key, consumer_secret) VALUES (1, %s, %s)", (consumer_key, consumer_secret))
    conn.commit()
    cursor.close()
    conn.close()

def _get_api_session():
    oauth_token, oauth_secret = get_oauth_tokens()
    if not oauth_token: return None
    creds = get_credentials()
    if not creds: return None
    return OAuth1Session(creds['consumer_key'], creds['consumer_secret'], oauth_token, oauth_secret)

def get_instapaper_access_token():
    oauth_token, oauth_secret = get_oauth_tokens()
    if oauth_token: return oauth_token, oauth_secret

    creds = get_credentials()
    if not creds:
        print_colored("[!] No Consumer Key/Secret found. Run option 6 first.", COLORS.RED)
        return None, None

    c_key, c_secret = creds['consumer_key'].strip(), creds['consumer_secret'].strip()
    print_colored("\n[!] OAuth tokens missing. Starting OAuth flow...", COLORS.YELLOW)

    oauth = OAuth1Session(c_key, client_secret=c_secret, callback_uri='oob')
    try:
        fetch_response = oauth.fetch_request_token(f"{API_BASE}/oauth/request_token")
        request_token = fetch_response.get('oauth_token')
        request_token_secret = fetch_response.get('oauth_token_secret')

        auth_url = f"{AUTHORIZE_URL}?oauth_token={request_token}"
        print("\n" + "="*60)
        print("1. Open this URL in your browser:\n" + color_text(auth_url, COLORS.GREEN, bold=True))
        print("2. Log in and click 'Authorize'.")
        print("3. Copy the PIN code Instapaper gives you.")
        print("="*60 + "\n")

        verifier = input(color_text("Enter the PIN code: ", COLORS.MAGENTA)).strip()
        if not verifier: return None, None

        oauth = OAuth1Session(c_key, client_secret=c_secret, resource_owner_key=request_token, resource_owner_secret=request_token_secret, verifier=verifier)
        tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)

        save_oauth_tokens(tokens.get('oauth_token'), tokens.get('oauth_token_secret'))
        print_colored("[✓] Authorization successful! Tokens saved.", COLORS.GREEN)
        return tokens.get('oauth_token'), tokens.get('oauth_token_secret')
    except Exception as e:
        print_colored(f"[!] OAuth failed: {e}", COLORS.RED)
        return None, None

# ==========================================
#  WEB SCRAPING & LOCAL DB
# ==========================================

def fetch_article_text(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return None
        html = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', resp.text)
        try:
            doc = Document(html)
            return {'title': doc.title() or "Untitled", 'author': '', 'text': doc.summary()}
        except Exception:
            h = html2text.HTML2Text()
            h.body_width = 0
            return {'title': "Untitled", 'author': '', 'text': h.handle(html)}
    except Exception:
        return None

def store_article_locally(url, title, author, content, server_id=None, status='unread'):
    import hashlib
    bookmark_id = hashlib.md5(url.encode()).hexdigest()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO instapaper_articles (bookmark_id, server_id, url, title, author, content, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            server_id = COALESCE(VALUES(server_id), server_id),
            status = COALESCE(VALUES(status), status),
            title = COALESCE(VALUES(title), title),
            content = COALESCE(VALUES(content), content),
            updated_at = NOW()
    """, (bookmark_id, server_id, url, title, author, content, status))
    conn.commit()
    cursor.close()
    conn.close()

# ==========================================
#  SYNC & API ACTIONS
# ==========================================

def sync_all_bookmarks():
    session = _get_api_session()
    if not session:
        return False, "OAuth not configured. Run Option 6."

    print_colored("[i] Syncing with Instapaper server...", COLORS.BLUE)
    for folder in ['unread', 'archive']:
        offset = 0
        while True:
            try:
                resp = session.get(f"{API_BASE}/bookmarks/list", params={'limit': 250, 'offset': offset, 'folder_id': folder})
                bookmarks = resp.json()
                if not bookmarks: break

                for bm in bookmarks:
                    if bm.get('type') != 'bookmark': continue
                    url = bm.get('url')
                    server_id = bm.get('bookmark_id')

                    conn = get_connection()
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute("SELECT id, content FROM instapaper_articles WHERE url = %s", (url,))
                    existing = cursor.fetchone()
                    cursor.close(); conn.close()

                    if not existing or (folder == 'unread' and not existing['content']):
                        art = fetch_article_text(url)
                        if art:
                            store_article_locally(url, art['title'], art['author'], art['text'], server_id, folder)
                        else:
                            store_article_locally(url, bm.get('title', 'Untitled'), '', '', server_id, folder)
                    else:
                        store_article_locally(url, bm.get('title', 'Untitled'), existing.get('author',''), existing.get('content',''), server_id, folder)
                offset += 250
                time.sleep(0.5)
            except Exception as e:
                print_colored(f"\n[!] Sync error: {e}", COLORS.RED)
                break
    print_colored("[✓] Sync complete!", COLORS.GREEN)
    return True, "Synced"

def archive_article(article_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT server_id FROM instapaper_articles WHERE id = %s", (article_id,))
    row = cursor.fetchone()
    if not row: return False, "Article not found."
    cursor.execute("UPDATE instapaper_articles SET status = 'archive' WHERE id = %s", (article_id,))
    conn.commit()
    if row['server_id']:
        session = _get_api_session()
        if session: session.post(f"{API_BASE}/bookmarks/archive", data={'bookmark_id': row['server_id']})
    cursor.close(); conn.close()
    return True, "Article archived."

def delete_article(article_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT server_id FROM instapaper_articles WHERE id = %s", (article_id,))
    row = cursor.fetchone()
    if row and row['server_id']:
        session = _get_api_session()
        if session: session.post(f"{API_BASE}/bookmarks/delete", data={'bookmark_id': row['server_id']})
    cursor.execute("DELETE FROM instapaper_articles WHERE id = %s", (article_id,))
    conn.commit()
    cursor.close(); conn.close()
    return True, "Deleted everywhere."

def add_to_instapaper(url, title=None):
    session = _get_api_session()
    if not session: return False, "OAuth not configured."
    try:
        resp = session.post(f"{API_BASE}/bookmarks/add", data={'url': url, 'title': title or ''})
        if resp.status_code == 201:
            art = fetch_article_text(url)
            if art: store_article_locally(url, art['title'], '', art['text'])
            return True, "✅ Saved to server."
        return False, f"❌ Error: {resp.status_code}"
    except Exception as e:
        return False, f"Error: {e}"

# ==========================================
#  LOCAL DB & CLI READING
# ==========================================

def list_all_articles():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, title, url, saved_at, status FROM instapaper_articles ORDER BY saved_at DESC")
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows

def get_article_by_id(article_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM instapaper_articles WHERE id = %s", (article_id,))
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return row

def refresh_article(article_id):
    article = get_article_by_id(article_id)
    if not article: return False, "Article not found."
    art_data = fetch_article_text(article['url'])
    if not art_data: return False, "Failed to fetch new content."

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE instapaper_articles
        SET title = %s, author = %s, content = %s, updated_at = NOW()
        WHERE id = %s
    """, (art_data['title'], art_data['author'], art_data['text'], article_id))
    conn.commit()
    cursor.close(); conn.close()
    return True, "Article refreshed."

# ==========================================
#  CLI INTERACTIVE MENUS
# ==========================================

def _mask_string(s, show=4):
    if not s: return "(empty)"
    return s[:show] + "*" * (len(s) - show)

def _full_setup():
    print("\n" + "═" * 50)
    print_colored("  INSTAPAPER SETUP", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Get Consumer Key/Secret from: https://www.instapaper.com/developers")
    c_key = input(color_text("Consumer Key: ", COLORS.MAGENTA)).strip()
    c_secret = input(color_text("Consumer Secret: ", COLORS.MAGENTA)).strip()
    save_credentials(c_key, c_secret)
    print_colored("[✓] API Keys saved.", COLORS.GREEN)
    return True

def edit_credentials_interactive():
    creds = get_credentials()
    if not creds: return _full_setup()
    print("\n" + "═" * 50)
    print(f"Current Consumer Key: {_mask_string(creds.get('consumer_key'))}")
    new_key = input(color_text("New Consumer Key (Enter to keep): ", COLORS.MAGENTA)).strip()
    new_secret = input(color_text("New Consumer Secret (Enter to keep): ", COLORS.MAGENTA)).strip()
    if new_key: creds['consumer_key'] = new_key
    if new_secret: creds['consumer_secret'] = new_secret
    save_credentials(creds['consumer_key'], creds['consumer_secret'])
    print_colored("[✓] Credentials updated.", COLORS.GREEN)

def save_lecture_question():
    print("\nWhat do you want to save to Instapaper?")
    print("  1. A YouTube lecture (by ID)")
    print("  2. A question (by ID)")
    print("  3. A custom URL")
    sub = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()

    if sub == '1':
        vid = input(color_text("Enter Video ID: ", COLORS.MAGENTA)).strip()
        from .db import get_record_by_any_id
        rec = get_record_by_any_id(vid)
        if rec:
            ok, msg = add_to_instapaper(f"https://youtu.be/{rec['video_id']}", rec.get('original_filename'))
            print_colored(msg, COLORS.GREEN if ok else COLORS.RED)
    elif sub == '2':
        qid = input(color_text("Enter question ID: ", COLORS.MAGENTA)).strip()
        from .question_bank import get_question_by_id
        q = get_question_by_id(int(qid))
        if q:
            ok, msg = add_to_instapaper(f"http://localhost:5000/question/{qid}", f"Q{q['question_number']} {q['subject']}")
            print_colored(msg, COLORS.GREEN if ok else COLORS.RED)
    elif sub == '3':
        url = input(color_text("Enter the full URL: ", COLORS.MAGENTA)).strip()
        if url:
            ok, msg = add_to_instapaper(url)
            print_colored(msg, COLORS.GREEN if ok else COLORS.RED)

def list_articles_interactive():
    status_filter = input(color_text("\nFilter by status (u=unread, a=archived, Enter=all): ", COLORS.MAGENTA)).strip().lower()
    articles = list_all_articles()

    if status_filter == 'u':
        articles = [a for a in articles if a['status'] == 'unread']
    elif status_filter == 'a':
        articles = [a for a in articles if a['status'] == 'archive']

    if not articles:
        print_colored("[i] No articles found.", COLORS.YELLOW)
        return

    print("\n" + "═" * 75)
    print_colored(f"  ARTICLES ({len(articles)} shown)", COLORS.CYAN, bold=True)
    print("═" * 75)
    for art in articles:
        status_icon = "📖" if art['status'] == 'unread' else "📁"
        print(f"  {status_icon} ID: {art['id']:3} | {(art['title'] or 'Untitled')[:55]}")
    print("═" * 75)

def read_article_interactive():
    article_id = input(color_text("Enter article ID to read: ", COLORS.MAGENTA)).strip()
    if not article_id.isdigit(): return
    article = get_article_by_id(int(article_id))
    if not article or not article['content']:
        print_colored("[!] Article or offline content not found.", COLORS.RED); return

    h = html2text.HTML2Text()
    h.body_width = 0
    plain_text = h.handle(article['content']).strip()

    print("\n" + "═" * 60)
    print_colored(f"  {article['title'] or 'Untitled'}", COLORS.CYAN, bold=True)
    print("═" * 60)
    print(plain_text)
    print("═" * 60)

    if article['status'] == 'unread':
        ans = input(color_text("\nArchive this article on the server now? (y/n): ", COLORS.MAGENTA)).strip().lower()
        if ans == 'y':
            ok, msg = archive_article(article['id'])
            print_colored(msg, COLORS.GREEN if ok else COLORS.RED)

def refresh_article_interactive():
    article_id = input(color_text("Enter article ID to re-fetch text: ", COLORS.MAGENTA)).strip()
    if not article_id.isdigit(): return
    ok, msg = refresh_article(int(article_id))
    print_colored(msg, COLORS.GREEN if ok else COLORS.RED)

def delete_article_interactive():
    article_id = input(color_text("Enter article ID to DELETE (Local + Server): ", COLORS.MAGENTA)).strip()
    if not article_id.isdigit(): return
    confirm = input(color_text(f"Permanently delete article {article_id}? (y/n): ", COLORS.RED)).strip().lower()
    if confirm == 'y':
        ok, msg = delete_article(int(article_id))
        print_colored(msg, COLORS.GREEN if ok else COLORS.RED)

def instapaper_menu():
    while True:
        creds = get_credentials()
        if not creds:
            _full_setup()
            continue

        oauth_token, _ = get_oauth_tokens()
        auth_status = color_text("Connected", COLORS.GREEN) if oauth_token else color_text("Needs Auth", COLORS.RED)

        print("\n" + "═" * 50)
        print_colored("  📰 INSTAPAPER SYNC CLIENT", COLORS.CYAN, bold=True)
        print(f"  Server Status: {auth_status}")
        print("═" * 50)
        print("  1. 🔄 Sync with Server (Pull latest)")
        print("  2. 📖 List Articles")
        print("  3. 👁  Read Article (Offline)")
        print("  4. 📥 Save URL/Lecture to Server")
        print("  5. 🔄 Re-fetch Article Text")
        print("  6. 🗑  Delete Article (Local + Server)")
        print("  7. ⚙️  Edit API Credentials")
        print("  0. Return to main menu")
        print("═" * 50)

        choice = input(color_text("Choose (0-7): ", COLORS.MAGENTA)).strip()

        if choice == '0': return
        elif choice == '1': ok, msg = sync_all_bookmarks()
        elif choice == '2': list_articles_interactive()
        elif choice == '3': read_article_interactive()
        elif choice == '4': save_lecture_question()
        elif choice == '5': refresh_article_interactive()
        elif choice == '6': delete_article_interactive()
        elif choice == '7': edit_credentials_interactive()
        else: print_colored("[!] Invalid choice.", COLORS.RED)

        input("\nPress Enter to continue...")
