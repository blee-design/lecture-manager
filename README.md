# 📚 Lecture Manager

**Unified media manager for YouTube lectures, Facebook content, offline article reading, question banking, and productivity tracking.**

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🌟 Features

### 📺 YouTube Lectures
- Add lectures via YouTube URL or video ID
- Auto‑detect title, lecturer, date, and time from the title
- Organise files into a structured folder tree (by paper, subject, chapter)
- Download videos in 720p (or lower) with metadata and thumbnails
- Local playback via embedded player (web UI) or external player (CLI)
- YouTube upload (unlisted) with automatic mirror ID linking
- Mirror management – link original videos to uploaded copies

### 📘 Facebook Content
- Download videos, reels, and photos from Facebook
- Auto‑detect uploader and title
- Organise files by type (video/photo) with MD5‑based filenames
- Full database tracking with export/import

### ❓ Question Bank (New!)
- Import/export questions in multiple formats: **TXT, CSV, JSON, XML (Moodle), HTML**
- Support for four question types: **essay, multichoice, truefalse, matching**
- **Context‑aware import** – set global defaults (date, institution, level, paper, group, subject) and reuse them across questions
- **Reading passage** feature – define once, reuse in many questions
- **Group** questions into exam sections
- Web UI for browsing, searching, and viewing whole papers
- Advanced search and filtering

### ⏱️ Pomodoro Timer (Enhanced!)
- Built‑in Tkinter GUI timer with study sessions, short/long breaks
- **Smart Syllabus Integration:** Auto-expands task codes (e.g., `P1-A1.1`) into full chapter names based on the active syllabus.
- **Context-Aware Filtering:** The task dropdown only shows chapters relevant to the selected subject.
- Task management with priority, completion, and bulk add
- Study logging with subjects, session types (study/revision/pretest/exam)
- Daily, weekly, and monthly progress tracking
- Badges and streak tracking to keep you motivated
- Detailed analytics with charts (matplotlib)

### 📰 Offline Article Reader (Instapaper Two-Way Sync!)
- Save articles, YouTube lectures, or questions to Instapaper
- **Two-Way Sync:** Pull unread and archived bookmarks from the server, and archive/delete them locally and remotely.
- Offline storage of full article content with local search
- Modern OAuth 1.0a authentication flow

### 🌐 Web Interface (Flask) (Redesigned!)
- Dashboard with library statistics and paper breakdown
- **Master-Detail Syllabus Explorer:** Clean sidebar tree with dynamic chapter loading.
- **Advanced Lectures View:** Sticky filter sidebar, grouped institution dropdowns, and clean 4-column table layout.
- Browse and manage YouTube and Facebook entries
- View questions, whole papers, and browse by chapter
- Import/export questions via the web UI
- Stream local video files directly in the browser

### 🛠️ CLI Tools
- Full terminal interface with colour‑coded menus
- Tally and sync database with actual files
- Duplicate detection and resolution
- Backup, restore, and trash management
- File compression (re‑encode to 480p H.264) to save space
- Share/restore files via a shared directory

### 🗄️ Database Backend
- MariaDB/MySQL with automatic schema creation and migration
- Unique constraints prevent duplicate questions and lecture records
- Transaction‑safe import/export operations

---

### 🔊 Sound / Beep

The Pomodoro timer uses a beep to signal session end. If you don't hear a sound:

- In Konsole, enable the audible bell in Settings → Notifications.
- Or install `beep`: `sudo apt install beep`
- On some systems, the `paplay` or `speaker-test` fallbacks will work without extra setup.


## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- MariaDB/MySQL server
- `ffmpeg` (for video processing)
- `deno` (optional, used by some internal tools)

### Installation

```bash
# Clone the repository
git clone https://github.com/blee-design/lecture-manager.git
cd lecture-manager

# Create a virtual environment and install the package
make setup
