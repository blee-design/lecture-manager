# pomodoro.py

import math
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta
import calendar
import tkinter as tk
import random
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
from datetime import datetime
import os
import re
from .db import get_connection
import signal
signal.signal(signal.SIGINT, signal.SIG_IGN)

print("🚀 LOADING POMODORO MODULE")

# Session types available in the Pomodoro dropdown.
# Add or remove freely — the DB stores whatever you pick.
# Stats and charts update automatically the moment a new type is logged.
SESSION_TYPES = [
    "study",
    "revision",
    "pretest",
    "exam",
    "quiz",
    "newspaper",
]

def load_quotes():
    """Load quotes from quotes.txt. Return empty list if file not found or empty."""
    quotes_file = os.path.join(os.path.dirname(__file__), '..', 'quotes.txt')
    try:
        with open(quotes_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            return lines
    except FileNotFoundError:
        print("[WARN] quotes.txt not found. No quotes available.")
        return []

QUOTES = load_quotes()


def _strip_number_prefix(name):
    """Remove a leading '1. ' / '01 - ' / '1) ' / '1:' style number
    from a subject name so the UI can re-number it per paper."""
    if not name:
        return ''
    return re.sub(r'^\s*\d+\s*[.)\-:]\s*', '', str(name)).strip()

# ====================== STYLE CONFIGURATION ======================
# ---- Modern palette (module-level so other functions can reuse) ----
PALETTE = {
    'bg':            '#0f1117',   # deep near-black
    'card':          '#1a1d28',   # card surface
    'card_hover':    '#232734',   # card hover / raised
    'border':        '#2a2e3d',   # subtle divider
    'text':          '#e8eaf0',   # primary text
    'text_muted':    '#8b92a5',   # secondary text
    'accent':        '#6366f1',   # indigo — primary action
    'accent_hover':  '#7c7ff2',
    'success':       '#10b981',
    'warning':       '#f59e0b',
    'danger':        '#ef4444',
    'info':          '#06b6d4',
}

def _strip_syllabus_tag(text):
    """Remove a leading '[XX] ' prefix used for display in the subject dropdown."""
    import re as _re
    return _re.sub(r'^\[[^\]]+\]\s*', '', (text or '')).strip()

def configure_styles():
    style = ttk.Style()
    style.theme_use('clam')

    bg      = PALETTE['bg']
    card    = PALETTE['card']
    border  = PALETTE['border']
    text    = PALETTE['text']
    muted   = PALETTE['text_muted']
    accent  = PALETTE['accent']
    acc_h   = PALETTE['accent_hover']

    # ---- Base ----
    style.configure('.', background=bg, foreground=text,
                    fieldbackground=card, borderwidth=0, focuscolor=bg)
    style.configure('TFrame',       background=bg)
    style.configure('TLabel',       background=bg, foreground=text)
    style.configure('Muted.TLabel', background=bg, foreground=muted)
    style.configure('Card.TFrame',  background=card)
    style.configure('Card.TLabel',  background=card, foreground=text)

    # ---- Borderless LabelFrame (kept for any leftover usage) ----
    style.configure('TLabelframe',
                    background=card, foreground=text,
                    bordercolor=card, borderwidth=0, relief='flat')
    style.configure('TLabelframe.Label',
                    background=card, foreground=muted,
                    font=('Helvetica Neue', 9))

    # ---- Buttons ----
    style.configure('TButton',
                    background=card, foreground=text,
                    bordercolor=border, focuscolor=bg,
                    borderwidth=0, relief='flat',
                    padding=(14, 8))
    style.map('TButton',
              background=[('active', PALETTE['card_hover']),
                          ('pressed', PALETTE['border'])],
              foreground=[('disabled', muted)])

    # Primary (accent) button — for ▶ Start / Save Log
    style.configure('Accent.TButton',
                    background=accent, foreground='white',
                    borderwidth=0, relief='flat', padding=(18, 10))
    style.map('Accent.TButton',
              background=[('active', acc_h), ('pressed', accent)])

    # Ghost button — for secondary controls
    style.configure('Ghost.TButton',
                    background=card, foreground=muted,
                    borderwidth=0, relief='flat', padding=(10, 6))
    style.map('Ghost.TButton',
              background=[('active', PALETTE['card_hover'])],
              foreground=[('active', text)])

    # ---- Inputs ----
    style.configure('TEntry',
                    fieldbackground=PALETTE['card_hover'],
                    foreground=text, insertcolor=text,
                    bordercolor=border, borderwidth=1, relief='flat',
                    padding=6)
    style.configure('TCombobox',
                    fieldbackground=PALETTE['card_hover'],
                    foreground=text, background=card,
                    arrowcolor=muted, bordercolor=border,
                    borderwidth=1, relief='flat', padding=6)
    style.map('TCombobox',
              fieldbackground=[('readonly', PALETTE['card_hover'])],
              bordercolor=[('focus', accent)])
    style.configure('TCombobox.listbox',
                    background=card, foreground=text,
                    selectbackground=accent, selectforeground='white',
                    borderwidth=0)

    # ---- Progressbar ----
    style.configure('TProgressbar',
                    background=accent, troughcolor=PALETTE['card_hover'],
                    bordercolor=card, borderwidth=0, thickness=6)

    # ---- Notebook (stats dialog) ----
    style.configure('TNotebook', background=bg, bordercolor=border,
                    borderwidth=0)
    style.configure('TNotebook.Tab',
                    background=card, foreground=muted,
                    padding=[14, 8], borderwidth=0)
    style.map('TNotebook.Tab',
              background=[('selected', PALETTE['card_hover'])],
              foreground=[('selected', text)])

    # ---- Scrollbar ----
    style.configure('Vertical.TScrollbar',
                    background=card, troughcolor=bg,
                    bordercolor=bg, arrowcolor=muted, borderwidth=0)
    style.map('Vertical.TScrollbar',
              background=[('active', PALETTE['card_hover'])])

    # ---- Treeview ----
    style.configure('Treeview',
                    background=card, foreground=text,
                    fieldbackground=card, bordercolor=border,
                    borderwidth=0, rowheight=28)
    style.configure('Treeview.Heading',
                    background=bg, foreground=muted,
                    borderwidth=0, relief='flat', padding=(8, 6))
    style.map('Treeview',
              background=[('selected', accent)],
              foreground=[('selected', 'white')])
    style.map('Treeview.Heading',
              background=[('active', PALETTE['card_hover'])],
              foreground=[('active', text)])

    # ---- Badge frames ----
    style.configure('Earned.TFrame', background=PALETTE['success'],
                    borderwidth=0, relief='flat')
    style.configure('Locked.TFrame', background=PALETTE['card_hover'],
                    borderwidth=0, relief='flat')

def make_card(parent, title, **grid_kw):
    """
    Borderless card surface with a subtle title row.
    Returns (card_frame, content_frame). Put child widgets inside content.
    """
    card = tk.Frame(parent, bg=PALETTE['card'], bd=0, highlightthickness=0)
    if grid_kw:
        card.grid(**grid_kw)

    tk.Label(card, text=title, bg=PALETTE['card'],
             fg=PALETTE['text_muted'],
             font=('Helvetica Neue', 10, 'bold'),
             anchor='w', padx=14, pady=8).pack(fill='x', pady=(8, 4))

    tk.Frame(card, bg=PALETTE['border'], height=1).pack(fill='x', padx=14)

    content = tk.Frame(card, bg=PALETTE['card'], padx=14, pady=12)
    content.pack(fill='both', expand=True)
    return card, content

# ====================== PIE CHART HELPER ======================
def _render_pie_chart(ax, data, labels, title):
    """
    Dark-themed donut chart with a side legend and a Hollywood-style
    hover effect: the slice under the cursor lifts, its outline brightens,
    and a small tooltip shows label + minutes + percentage.
    """
    # ---- Filter out zero/negative values ----
    pairs = [(str(lbl), val) for lbl, val in zip(labels, data) if val and val > 0]

    ax.set_facecolor('#2c3e50')
    ax.figure.patch.set_facecolor('#2c3e50')

    if not pairs:
        ax.text(0.5, 0.5, "No data", ha='center', va='center',
                color='#ecf0f1', fontsize=12)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title, color='#ecf0f1', fontsize=12, weight='bold', pad=10)
        return

    labels_clean, values = zip(*pairs)
    total = sum(values)
    pcts = [(v / total) * 100 for v in values]

    palette = [
        '#3498db', '#9b59b6', '#e67e22', '#16a085', '#e74c3c',
        '#f1c40f', '#2ecc71', '#1abc9c', '#e84393', '#d35400',
        '#8e44ad', '#2980b9', '#c0392b', '#27ae60', '#f39c12',
    ]
    colors = [palette[i % len(palette)] for i in range(len(values))]

    wedges, _texts, autotexts = ax.pie(
        values,
        labels=None,
        colors=colors,
        autopct=lambda p: f'{p:.1f}%',
        startangle=90,
        counterclock=False,
        pctdistance=0.79,
        wedgeprops=dict(width=0.40, edgecolor='#1e2a3a', linewidth=1.6),
        textprops=dict(color='white', fontsize=9, weight='bold'),
    )
    for t in autotexts:
        t.set_color('white')

    ax.text(0, 0, f"{int(total)}\nmin", ha='center', va='center',
            color='#ecf0f1', fontsize=13, weight='bold')

    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    legend_labels = [
        f"{labels_clean[i]}  —  {int(values[i])}m  ({pcts[i]:.1f}%)"
        for i in order
    ]
    legend_handles = [wedges[i] for i in order]
    ax.legend(legend_handles, legend_labels,
              loc='center left', bbox_to_anchor=(1.02, 0.5),
              fontsize=9, frameon=False, labelcolor='#ecf0f1')

    ax.set_title(title, color='#ecf0f1', fontsize=12, weight='bold', pad=15)
    ax.axis('equal')

    # =========================================================
    #  HOVER LAYER  —  "Hollywood" explode + tooltip
    # =========================================================
    original_transforms = [w.get_transform() for w in wedges]
    hover_state = {'idx': None}

    # Tooltip text object anchored at figure top-left
    tooltip = ax.figure.text(
        0.02, 0.97, '',
        ha='left', va='top',
        fontsize=10, color='#ecf0f1', weight='bold',
        bbox=dict(boxstyle='round,pad=0.45',
                  facecolor='#1e2a3a',
                  edgecolor='#3498db',
                  linewidth=1.2,
                  alpha=0.95),
        zorder=20,
    )
    tooltip.set_visible(False)

    def _restore(idx):
        wedges[idx].set_transform(original_transforms[idx])
        wedges[idx].set_linewidth(1.6)
        wedges[idx].set_edgecolor('#1e2a3a')

    def _highlight(idx):
        w = wedges[idx]
        theta_mid = math.radians((w.theta1 + w.theta2) / 2.0)
        offset = 0.09                       # ~9% of radius — the "lift"
        dx = offset * math.cos(theta_mid)
        dy = offset * math.sin(theta_mid)
        new_tr = mtransforms.Affine2D().translate(dx, dy) + original_transforms[idx]
        w.set_transform(new_tr)
        w.set_linewidth(2.4)
        w.set_edgecolor('white')

    def _wedge_at(event):
        # Test against original positions regardless of current explode state
        for i, w in enumerate(wedges):
            current = w.get_transform()
            w.set_transform(original_transforms[i])
            try:
                inside, _ = w.contains(event)
            except Exception:
                inside = False
            w.set_transform(current)
            if inside:
                return i
        return None

    def on_hover(event):
        if event.inaxes != ax:
            if hover_state['idx'] is not None:
                _restore(hover_state['idx'])
                hover_state['idx'] = None
                tooltip.set_visible(False)
                ax.figure.canvas.draw_idle()
            return

        new_idx = _wedge_at(event)
        if new_idx == hover_state['idx']:
            return

        if hover_state['idx'] is not None:
            _restore(hover_state['idx'])

        if new_idx is not None:
            _highlight(new_idx)
            label = labels_clean[new_idx]
            val = values[new_idx]
            pct = pcts[new_idx]
            tooltip.set_text(f"  {label}\n  {int(val)} min  •  {pct:.1f}%  ")
            tooltip.set_visible(True)
        else:
            tooltip.set_visible(False)

        hover_state['idx'] = new_idx
        ax.figure.canvas.draw_idle()

    def on_leave(_event):
        if hover_state['idx'] is not None:
            _restore(hover_state['idx'])
            hover_state['idx'] = None
        tooltip.set_visible(False)
        ax.figure.canvas.draw_idle()

    # Store refs on the axes so they survive until the figure is destroyed
    ax._hover_cids = (
        ax.figure.canvas.mpl_connect('motion_notify_event', on_hover),
        ax.figure.canvas.mpl_connect('figure_leave_event', on_leave),
    )
    ax._hover_tooltip = tooltip

class PomodoroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🍅 Pomodoro Study Timer")
        self.root.geometry("1000x780")
        self.root.minsize(850, 680)
        self.root.configure(bg="#0f1117")
        configure_styles()

        self.config = self.load_config()
        self.tasks = self.load_tasks()
        self.current_task_id = None

        self.log = self.load_log()
        self.today_count = self.count_today_pomodoros()

        self.remaining_seconds = 0
        self.timer_running = False
        self.paused = False
        self.current_phase = "work"

        # Set cycles_completed to today's count
        self.today_count = self.count_today_pomodoros()
        self.cycles_completed = self.today_count
        # Update the state table to reflect today's count (keeps DB in sync)
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE pomodoro_state SET cycles_completed = %s WHERE id = 1", (self.cycles_completed,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass
        # ------------------------------------------

        self._after_id = None
        self.task_var = tk.StringVar()
        self._subject_label_to_name = {}

        # pause tracking
        self.pauses = []
        self.pause_start_time = None

        self.edit_log_var = tk.BooleanVar(value=False)
        self.save_log_btn = None

        self.sound_func = self._beep

        self.build_ui()
        self.update_streak_display()
        self.restore_state_if_any()          # Restores phase, remaining time, subject, notes, cycles_completed
        self.update_display()
        self.refresh_task_list()
        self.refresh_log()
        self.update_progress()
        self.update_task_combo()

        self.schedule_state_save()

        # ---- NEW: midnight rollover detection ----
        self._today_date = datetime.now().date()
        self._rollover_after_id = None
        self._schedule_day_rollover_check()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # ----- AUTOMATIC BADGE REFRESH ON STARTUP -----
        self.root.after(1000, self.refresh_badges)

    def edit_task(self):
        """Edit the text of the selected task."""
        selection = self.task_listbox.curselection()
        if not selection:
            messagebox.showinfo("Info", "Select a task to edit.")
            return

        index = selection[0]
        task_id = self.task_listbox_task_ids[index]
        task = next((t for t in self.tasks if t['id'] == task_id), None)
        if not task:
            return

        current_text = task['task_text']
        new_text = simpledialog.askstring(
            "Edit Task",
            f"Edit task:\n\nCurrent: {current_text}",
            initialvalue=current_text
        )
        if new_text is None:          # user cancelled
            return
        new_text = new_text.strip()
        if not new_text:
            messagebox.showwarning("Empty", "Task text cannot be empty.")
            return

        # Update database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE pomodoro_tasks SET task_text = %s WHERE id = %s", (new_text, task_id))
        conn.commit()
        cursor.close()
        conn.close()

        # Refresh UI
        self.tasks = self.load_tasks()
        self.refresh_task_list()
        self.update_task_combo()
        messagebox.showinfo("Task Updated", "Task text updated successfully.")

    def export_log_csv(self):
        import csv
        from tkinter import filedialog
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not filename:
            return
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT timestamp, phase, duration_min, subject, session_type, notes,
                pause_count, pause_total_sec, task_id
            FROM pomodoro_log
            WHERE phase = 'work'
            ORDER BY timestamp
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        if not rows:
            messagebox.showinfo("No data", "No work sessions to export.")
            return
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        messagebox.showinfo("Export", f"Exported {len(rows)} sessions to {filename}")

    def check_and_award_badges(self):
        from .db import get_connection
        import random

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Total work sessions
        cursor.execute("SELECT COUNT(*) as total FROM pomodoro_log WHERE phase = 'work'")
        total_sessions = cursor.fetchone()['total']

        # Days with at least one session
        cursor.execute("SELECT COUNT(DISTINCT DATE(timestamp)) as days FROM pomodoro_log WHERE phase = 'work'")
        days_active = cursor.fetchone()['days']

        # Current streak (use your existing streak logic)
        streak = self.get_current_streak()

        # Early bird / Night owl
        cursor.execute("SELECT COUNT(*) as early FROM pomodoro_log WHERE phase='work' AND TIME(timestamp) < '08:00:00'")
        early_bird = cursor.fetchone()['early'] > 0
        cursor.execute("SELECT COUNT(*) as late FROM pomodoro_log WHERE phase='work' AND TIME(timestamp) > '22:00:00'")
        night_owl = cursor.fetchone()['late'] > 0

        # Subject specialist (≥5h on one subject)
        cursor.execute("""
            SELECT subject, SUM(duration_min) as total FROM pomodoro_log
            WHERE phase='work' AND subject IS NOT NULL AND subject != ''
            GROUP BY subject HAVING total >= 300 LIMIT 1
        """)
        specialist = cursor.fetchone() is not None

        # Balanced learner (3+ subjects this week)
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        cursor.execute("""
            SELECT COUNT(DISTINCT subject) as distinct_subjects
            FROM pomodoro_log
            WHERE phase='work' AND subject IS NOT NULL AND subject != ''
            AND timestamp >= %s
        """, (week_start,))
        distinct = cursor.fetchone()['distinct_subjects']
        balanced = distinct >= 3

        cursor.close()
        conn.close()

        # Determine which badges to award
        earned = []
        if total_sessions >= 1:
            earned.append('first_pomodoro')
        if total_sessions >= 10:
            earned.append('ten_sessions')
        if total_sessions >= 50:
            earned.append('fifty_sessions')
        if total_sessions >= 100:
            earned.append('hundred_sessions')
        if streak >= 5:
            earned.append('five_day_streak')
        if streak >= 10:
            earned.append('ten_day_streak')
        if early_bird:
            earned.append('early_bird')
        if night_owl:
            earned.append('night_owl')
        if specialist:
            earned.append('subject_specialist')
        if balanced:
            earned.append('balanced_learner')

        # Insert into user_badges if not already present
        conn = get_connection()
        cursor = conn.cursor()

        # ---- Inside check_and_award_badges ----
        newly_earned = []
        for b in earned:
            # Check if already earned
            cursor.execute("SELECT id FROM user_badges WHERE badge_name = %s", (b,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO user_badges (badge_name) VALUES (%s)", (b,))
                newly_earned.append(b)

        conn.commit()
        cursor.close()
        conn.close()

        # Show notification for new badges
        if newly_earned:
            # Fetch icons and descriptions
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            placeholders = ','.join(['%s'] * len(newly_earned))
            cursor.execute(f"SELECT badge_name, description, icon FROM pomodoro_badges WHERE badge_name IN ({placeholders})", newly_earned)
            badge_info = cursor.fetchall()
            cursor.close()
            conn.close()
            msg = "\n".join([f"{b['icon']} {b['badge_name'].replace('_',' ').title()} – {b['description']}" for b in badge_info])
            messagebox.showinfo("🏆 New Badge(s) Unlocked!", f"You earned:\n\n{msg}")

    def _create_scrollable_container(self):
        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container, bg="#0f1117", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill="y")

        self.scrollable_frame = ttk.Frame(self.canvas, padding="10")
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )

        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self._bind_mousewheel()
        return self.scrollable_frame

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)

    def _bind_mousewheel(self):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def build_ui(self):
        main = self._create_scrollable_container()
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # --- Settings StringVars (used by the settings dialog) ---
        self.work_var         = tk.StringVar(value=str(self.config["work_min"]))
        self.short_var        = tk.StringVar(value=str(self.config["short_break_min"]))
        self.long_var         = tk.StringVar(value=str(self.config["long_break_min"]))
        self.cycles_var       = tk.StringVar(value=str(self.config["cycles_before_long"]))
        self.goal_var         = tk.StringVar(value=str(self.config["daily_goal"]))
        self.weekly_goal_var  = tk.StringVar(value=str(self.config["weekly_goal_hours"]))
        self.monthly_goal_var = tk.StringVar(value=str(self.config["monthly_goal_hours"]))

        # ==============================================================
        # LEFT COLUMN: Timer · Session Type · Task · Notes
        # ==============================================================
        left = tk.Frame(main, bg=PALETTE['bg'])
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        left.rowconfigure(0, weight=0)
        left.rowconfigure(1, weight=0)
        left.rowconfigure(2, weight=0)
        left.rowconfigure(3, weight=1)
        left.columnconfigure(0, weight=1)

        # ---------- Timer card ----------
        _, tc = make_card(left, "⏱️  TIMER",
                          row=0, column=0, sticky='ew', pady=(0, 8))
        tc.columnconfigure(0, weight=1)

        self.time_label = tk.Label(tc, text="25:00",
                                   bg=PALETTE['card'], fg=PALETTE['accent'],
                                   font=('Helvetica Neue', 56, 'bold'))
        self.time_label.grid(row=0, column=0, pady=(4, 6))

        self.progress_bar = ttk.Progressbar(tc, orient='horizontal',
                                            length=300, mode='determinate')
        self.progress_bar.grid(row=1, column=0, pady=(0, 8), sticky='ew')

        self.phase_label = tk.Label(tc, text="Work",
                                    bg=PALETTE['card'], fg=PALETTE['text_muted'],
                                    font=('Helvetica Neue', 11))
        self.phase_label.grid(row=2, column=0, pady=(0, 8))

        ctrl = tk.Frame(tc, bg=PALETTE['card'])
        ctrl.grid(row=3, column=0, pady=(0, 8))
        self.start_btn = ttk.Button(ctrl, text="▶  Start",
                                    style='Accent.TButton',
                                    command=self.start_timer)
        self.start_btn.pack(side='left', padx=4)
        self.pause_btn = ttk.Button(ctrl, text="⏸  Pause",
                                    command=self.pause_timer,
                                    state='disabled')
        self.pause_btn.pack(side='left', padx=4)
        self.reset_btn = ttk.Button(ctrl, text="⟳  Reset",
                                    style='Ghost.TButton',
                                    command=self.reset_timer)
        self.reset_btn.pack(side='left', padx=4)
        ttk.Button(ctrl, text="⚙", width=3,
                   style='Ghost.TButton',
                   command=self.open_settings_dialog).pack(side='left', padx=4)

        # Daily progress row
        daily = tk.Frame(tc, bg=PALETTE['card'])
        daily.grid(row=4, column=0, sticky='ew', pady=(2, 2))
        self.progress_label = tk.Label(daily, text="Today: 0 / 12",
                                       bg=PALETTE['card'], fg=PALETTE['text'],
                                       font=('Helvetica Neue', 10))
        self.progress_label.pack(side='left', padx=(4, 8))
        self.daily_bar = ttk.Progressbar(daily, orient='horizontal',
                                         length=200, mode='determinate',
                                         maximum=self.config["daily_goal"])
        self.daily_bar.pack(side='left', padx=(0, 8), fill='x', expand=True)
        ttk.Button(daily, text="📊", style='Ghost.TButton',
                   command=self.show_today_summary).pack(side='left', padx=2)
        ttk.Button(daily, text="📈", style='Ghost.TButton',
                   command=self.show_overall_stats).pack(side='left', padx=2)

        # Inline stats strip (streak + week bar + month bar)
        stats = tk.Frame(tc, bg=PALETTE['card'])
        stats.grid(row=5, column=0, sticky='ew', pady=(6, 2))

        self.streak_label = tk.Label(stats, text="🔥 0-day",
                                     bg=PALETTE['card'],
                                     fg=PALETTE['warning'],
                                     font=('Helvetica Neue', 10, 'bold'))
        self.streak_label.pack(side='left', padx=(4, 14))

        tk.Label(stats, text="📅", bg=PALETTE['card'],
                 fg=PALETTE['text_muted']).pack(side='left')
        self.week_fill_lbl = tk.Label(stats, text="",
                                      fg=PALETTE['danger'], bg=PALETTE['card'],
                                      font=('DejaVu Sans Mono', 11, 'bold'))
        self.week_fill_lbl.pack(side='left', padx=(3, 0))
        self.week_empty_lbl = tk.Label(stats, text="",
                                       fg=PALETTE['border'], bg=PALETTE['card'],
                                       font=('DejaVu Sans Mono', 11, 'bold'))
        self.week_empty_lbl.pack(side='left')
        self.weekly_label = tk.Label(stats, text=" 0h/10h",
                                     bg=PALETTE['card'],
                                     fg=PALETTE['text_muted'],
                                     font=('Helvetica Neue', 10))
        self.weekly_label.pack(side='left', padx=(4, 14))

        tk.Label(stats, text="🗓️", bg=PALETTE['card'],
                 fg=PALETTE['text_muted']).pack(side='left')
        self.month_fill_lbl = tk.Label(stats, text="",
                                       fg=PALETTE['danger'], bg=PALETTE['card'],
                                       font=('DejaVu Sans Mono', 11, 'bold'))
        self.month_fill_lbl.pack(side='left', padx=(3, 0))
        self.month_empty_lbl = tk.Label(stats, text="",
                                        fg=PALETTE['border'], bg=PALETTE['card'],
                                        font=('DejaVu Sans Mono', 11, 'bold'))
        self.month_empty_lbl.pack(side='left')
        self.monthly_label = tk.Label(stats, text=" 0h/40h",
                                      bg=PALETTE['card'],
                                      fg=PALETTE['text_muted'],
                                      font=('Helvetica Neue', 10))
        self.monthly_label.pack(side='left', padx=(4, 4))

        # Hidden progress bars (kept for compatibility, occupy zero pixels)
        self.weekly_bar = ttk.Progressbar(left, mode='determinate')
        self.monthly_bar = ttk.Progressbar(left, mode='determinate')

        # ---------- Session Type ----------
        _, stc = make_card(left, "📌  SESSION TYPE",
                           row=1, column=0, sticky='ew', pady=(0, 8))
        stc.columnconfigure(0, weight=1)
        self.type_var = tk.StringVar(value="study")
        ttk.Combobox(stc, textvariable=self.type_var,
                     state='readonly', values=SESSION_TYPES
                     ).grid(row=0, column=0, sticky='ew')

        # ---------- Current Task ----------
        _, tkc = make_card(left, "🎯  CURRENT TASK",
                           row=2, column=0, sticky='ew', pady=(0, 8))
        tkc.columnconfigure(0, weight=1)
        self.task_combo = ttk.Combobox(tkc, textvariable=self.task_var,
                                       state='readonly', width=50)
        self.root.option_add('*TCombobox*Listbox.background', PALETTE['card'])
        self.root.option_add('*TCombobox*Listbox.foreground', PALETTE['text'])
        self.task_combo.grid(row=0, column=0, sticky='ew')
        self.task_combo.bind('<<ComboboxSelected>>', self.on_task_combo_select)

        # ---------- Notes ----------
        _, nc = make_card(left, "📝  NOTES FOR THIS SESSION",
                          row=3, column=0, sticky='nsew', pady=(0, 0))
        nc.columnconfigure(0, weight=1)
        nc.rowconfigure(0, weight=1)
        self.notes_text = scrolledtext.ScrolledText(
            nc, height=8, wrap='word',
            bg=PALETTE['card_hover'], fg=PALETTE['text'],
            insertbackground=PALETTE['text'],
            relief='flat', borderwidth=0, padx=8, pady=6)
        self.notes_text.grid(row=0, column=0, sticky='nsew')

        # ==============================================================
        # RIGHT COLUMN: Subject · Task List · Study Log
        # ==============================================================
        right = tk.Frame(main, bg=PALETTE['bg'])
        right.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        right.rowconfigure(0, weight=0)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        # ---------- Subject ----------
        _, sc = make_card(right, "📌  SUBJECT",
                          row=0, column=0, sticky='ew', pady=(0, 8))
        sc.columnconfigure(0, weight=1)

        tk.Label(sc, text="Syllabus", bg=PALETTE['card'],
                 fg=PALETTE['text_muted'], font=('Helvetica Neue', 9),
                 anchor='w').grid(row=0, column=0, sticky='ew', pady=(0, 2))
        self.syllabus_var = tk.StringVar()
        self.syllabus_combo = ttk.Combobox(sc, textvariable=self.syllabus_var,
                                           state='readonly')
        self.syllabus_combo.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.syllabus_combo.bind('<<ComboboxSelected>>',
                                 lambda e: self.on_syllabus_change())
        self._syllabus_map = {}

        tk.Label(sc, text="Subject", bg=PALETTE['card'],
                 fg=PALETTE['text_muted'], font=('Helvetica Neue', 9),
                 anchor='w').grid(row=2, column=0, sticky='ew', pady=(0, 2))
        self.subject_var = tk.StringVar()
        self.subject_combo = ttk.Combobox(sc, textvariable=self.subject_var,
                                          state='readonly')
        self.subject_combo.grid(row=3, column=0, sticky='ew')
        self.subject_combo.bind('<<ComboboxSelected>>',
                                self.on_subject_combo_select)

        self.load_syllabus_list()
        self.refresh_subject_list()

        # ---------- Task List ----------
        _, tlc = make_card(right, "📋  TASK LIST",
                           row=1, column=0, sticky='nsew', pady=(0, 8))
        tlc.columnconfigure(0, weight=1)
        tlc.rowconfigure(2, weight=1)

        add = tk.Frame(tlc, bg=PALETTE['card'])
        add.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        self.task_entry = ttk.Entry(add)
        self.task_entry.pack(side='left', fill='x', expand=True, padx=(0, 4))
        ttk.Button(add, text="➕", style='Ghost.TButton',
                   command=self.add_task).pack(side='left', padx=2)
        ttk.Button(add, text="📋", style='Ghost.TButton',
                   command=self.bulk_add_tasks).pack(side='left', padx=2)

        pri = tk.Frame(tlc, bg=PALETTE['card'])
        pri.grid(row=1, column=0, sticky='ew', pady=(0, 6))
        tk.Label(pri, text="Priority", bg=PALETTE['card'],
                 fg=PALETTE['text_muted'], font=('Helvetica Neue', 9)
                 ).pack(side='left', padx=(0, 6))
        self.priority_var = tk.StringVar(value="3")
        ttk.Spinbox(pri, from_=0, to=9, textvariable=self.priority_var,
                    width=4).pack(side='left', padx=(0, 6))
        tk.Label(pri, text="(1=high, 9=low, 0=lowest)",
                 bg=PALETTE['card'], fg=PALETTE['text_muted'],
                 font=('Helvetica Neue', 8)).pack(side='left')

        lb_wrap = tk.Frame(tlc, bg=PALETTE['card'])
        lb_wrap.grid(row=2, column=0, sticky='nsew', pady=(0, 6))
        lb_wrap.columnconfigure(0, weight=1)
        lb_wrap.rowconfigure(0, weight=1)

        self.task_listbox = tk.Listbox(
            lb_wrap, height=6,
            bg=PALETTE['card_hover'], fg=PALETTE['text'],
            selectbackground=PALETTE['accent'], selectforeground='white',
            relief='flat', borderwidth=0, highlightthickness=0,
            activestyle='none')
        self.task_listbox.grid(row=0, column=0, sticky='nsew')
        sb2 = ttk.Scrollbar(lb_wrap, orient='vertical',
                            command=self.task_listbox.yview)
        sb2.grid(row=0, column=1, sticky='ns')
        self.task_listbox.config(yscrollcommand=sb2.set)
        self.task_listbox.bind('<<ListboxSelect>>', self.on_task_select)
        self.task_listbox.bind('<Double-Button-1>', lambda e: self.edit_task())

        btns = tk.Frame(tlc, bg=PALETTE['card'])
        btns.grid(row=3, column=0, sticky='ew')
        for txt, cmd in [
            ("🗑", self.remove_task),
            ("✏️", self.edit_task),
            ("✅", self.toggle_complete),
            ("🔢", self.set_priority),
            ("🧹", self.clear_all_tasks),
        ]:
            ttk.Button(btns, text=txt, width=3, style='Ghost.TButton',
                       command=cmd).pack(side='left', padx=2)
        self.show_completed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btns, text="Show done",
                        variable=self.show_completed_var,
                        command=self.refresh_task_list).pack(side='right',
                                                             padx=4)

        # ---------- Study Log ----------
        _, lc = make_card(right, "📜  STUDY LOG",
                          row=2, column=0, sticky='nsew')
        lc.columnconfigure(0, weight=1)
        lc.rowconfigure(1, weight=1)

        head = tk.Frame(lc, bg=PALETTE['card'])
        head.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        self.edit_log_cb = ttk.Checkbutton(head, text="✏️ Edit",
                                           variable=self.edit_log_var,
                                           command=self.toggle_edit_mode)
        self.edit_log_cb.pack(side='right')

        self.log_text = scrolledtext.ScrolledText(
            lc, height=8, wrap='word', state='disabled',
            bg=PALETTE['card_hover'], fg=PALETTE['text'],
            relief='flat', borderwidth=0, padx=8, pady=6)
        self.log_text.grid(row=1, column=0, sticky='nsew')

        self.save_log_btn = ttk.Button(lc, text="💾  Save Log Changes",
                                       style='Accent.TButton',
                                       command=self.save_log_changes)
        self.save_log_btn.grid(row=2, column=0, sticky='e', pady=(6, 0))
        self.save_log_btn.grid_remove()

    # ---------- TASK MANAGEMENT (unchanged from original) ----------
    def load_tasks(self):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, task_text, priority, completed FROM pomodoro_tasks
            ORDER BY
                CASE priority WHEN 1 THEN 0 WHEN 0 THEN 2 ELSE 1 END,
                priority,
                task_text ASC   -- <-- added alphabetical sorting
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def save_tasks(self, tasks):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pomodoro_tasks")
        for task in tasks:
            cursor.execute("INSERT INTO pomodoro_tasks (id, task_text, priority, completed) VALUES (%s, %s, %s, %s)",
                           (task['id'], task['task_text'], task['priority'], task['completed']))
        conn.commit()
        cursor.close()
        conn.close()

    def add_task(self):
        text = self.task_entry.get().strip()
        if not text:
            return
        try:
            priority = int(self.priority_var.get())
            if priority < 0 or priority > 9:
                priority = 3
        except:
            priority = 3
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pomodoro_tasks (task_text, priority, completed) VALUES (%s, %s, 0)", (text, priority))
        conn.commit()
        cursor.close()
        conn.close()
        self.task_entry.delete(0, tk.END)
        self.tasks = self.load_tasks()
        self.refresh_task_list()
        self.update_task_combo()

    def bulk_add_tasks(self):
        bulk_win = tk.Toplevel(self.root)
        bulk_win.title("Bulk Add Tasks")
        bulk_win.geometry("400x350")
        bulk_win.resizable(True, True)
        bulk_win.configure(bg="#1e2a3a")

        ttk.Label(bulk_win, text="Enter one task per line:", font=("Helvetica", 10)).pack(pady=5)
        ttk.Label(bulk_win, text="Priority will be applied to all tasks.", font=("Helvetica", 9)).pack()

        text_area = scrolledtext.ScrolledText(bulk_win, height=10, wrap=tk.WORD)
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        bulk_priority_frame = ttk.Frame(bulk_win)
        bulk_priority_frame.pack(pady=5)
        ttk.Label(bulk_priority_frame, text="Priority for all:").pack(side=tk.LEFT, padx=5)
        bulk_priority_var = tk.StringVar(value="3")
        ttk.Spinbox(bulk_priority_frame, from_=0, to=9, textvariable=bulk_priority_var, width=5).pack(side=tk.LEFT, padx=5)
        ttk.Label(bulk_priority_frame, text="(1=Highest, 9=High, 0=Lowest)").pack(side=tk.LEFT, padx=5)

        def do_bulk_add():
            text = text_area.get("1.0", tk.END).strip()
            if not text:
                return
            try:
                priority = int(bulk_priority_var.get())
                if priority < 0 or priority > 9:
                    priority = 3
            except:
                priority = 3
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            if not lines:
                return
            conn = get_connection()
            cursor = conn.cursor()
            for line in lines:
                cursor.execute("INSERT INTO pomodoro_tasks (task_text, priority, completed) VALUES (%s, %s, 0)",
                               (line, priority))
            conn.commit()
            cursor.close()
            conn.close()
            self.tasks = self.load_tasks()
            self.refresh_task_list()
            self.update_task_combo()
            bulk_win.destroy()
            messagebox.showinfo("Bulk Add", f"Added {len(lines)} tasks.")

        btn_frame = ttk.Frame(bulk_win)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Add All", command=do_bulk_add).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=bulk_win.destroy).pack(side=tk.LEFT, padx=5)

    def remove_task(self):
        selection = self.task_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        task_id = self.task_listbox_task_ids[index]
        task = next((t for t in self.tasks if t['id'] == task_id), None)
        if not task:
            return

        # Check if this task has any log entries
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pomodoro_log WHERE task_id = %s", (task_id,))
        log_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        if log_count > 0:
            msg = (f"This task has {log_count} log entries.\n"
                "If you delete it, those sessions will become 'Uncategorized'.\n\n"
                "Do you want to reassign these logs to another task?")
            answer = messagebox.askyesnocancel("Task has history", msg)
            if answer is None:   # Cancel
                return
            if answer:           # Yes – reassign
                # Get list of other active tasks (excluding the one being deleted)
                other_tasks = [t for t in self.tasks if t['id'] != task_id and not t['completed']]
                if not other_tasks:
                    messagebox.showinfo("No other tasks", "There are no other active tasks. The logs will be set to NULL (Uncategorized).")
                    new_task_id = None
                else:
                    # Show a simple dialog to choose a task
                    task_names = [f"[P{t['priority']}] {t['task_text']}" for t in other_tasks]
                    import tkinter.simpledialog
                    choice = tkinter.simpledialog.askinteger(
                        "Reassign logs",
                        "Select a task to reassign the logs to:\n\n" +
                        "\n".join(f"{i+1}. {name}" for i, name in enumerate(task_names)) +
                        "\n\nEnter 0 to set logs to NULL (Uncategorized).",
                        minvalue=0, maxvalue=len(other_tasks)
                    )
                    if choice is None or choice == 0:
                        new_task_id = None
                    else:
                        new_task_id = other_tasks[choice-1]['id']

                # Update logs
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE pomodoro_log SET task_id = %s WHERE task_id = %s", (new_task_id, task_id))
                conn.commit()
                cursor.close()
                conn.close()
            else:   # No – delete anyway, leaving logs uncategorized
                pass  # fall through to deletion

        # Proceed with deletion
        confirm = messagebox.askyesno("Remove Task", "Delete this task permanently?")
        if not confirm:
            return

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pomodoro_tasks WHERE id = %s", (task_id,))
        conn.commit()
        cursor.close()
        conn.close()

        self.tasks = self.load_tasks()
        self.refresh_task_list()
        self.update_task_combo()

    def save_log_changes(self):
        """Parse the log text and update only changed entries."""
        content = self.log_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("No content", "The log is empty. Nothing to save.")
            return

        if not messagebox.askyesno("Save Log",
                                "This will update only the changed entries.\n"
                                "Entries without an ID (new ones) will be inserted.\n\n"
                                "Continue?"):
            return

        import re

        # Split by the separator line
        blocks = content.split("-" * 40 + "\n")
        updated = 0
        inserted = 0
        unchanged = 0
        errors = []

        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split('\n')
            if not lines:
                continue

            # First line: "[#87] 2024-01-01 10:00:00 - 25 min ..."
            first_line = lines[0].strip()

            # Extract log ID
            id_match = re.search(r'^\[#(\d+)\]', first_line)
            log_id = int(id_match.group(1)) if id_match else None

            # Extract timestamp and duration
            match = re.match(r'^(?:\[\#\d+\]\s*)?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (\d+) min', first_line)
            if not match:
                errors.append(f"Invalid format in block: {first_line[:50]}...")
                continue
            timestamp_str = match.group(1)
            duration = int(match.group(2))

            # Optional task, subject, session type
            task_name = None
            subject = None
            session_type = "study"

            task_match = re.search(r'\[Task:\s*(.*?)\]', first_line)
            if task_match:
                task_name = task_match.group(1).strip()

            subject_match = re.search(r'\[Subject:\s*(.*?)\]', first_line)
            if subject_match:
                subject = _strip_syllabus_tag(subject_match.group(1))

            type_match = re.search(r'\((\w+)\)', first_line)
            if type_match:
                session_type = type_match.group(1)

            # Validate against allowed ENUM values
            ALLOWED_SESSION_TYPES = {'study', 'revision', 'pretest', 'exam', 'quiz'}
            if session_type not in ALLOWED_SESSION_TYPES:
                session_type = 'study'

            # Notes
            notes_lines = []
            for line in lines[1:]:
                if line.strip().startswith("-" * 40):
                    break
                if line.strip().startswith("Notes:"):
                    notes_lines.append(line.strip()[6:].strip())
                elif notes_lines:
                    notes_lines.append(line.strip())
            notes = "\n".join(notes_lines) if notes_lines else None

            # Resolve task_id from task_name
            task_id = None
            if task_name:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM pomodoro_tasks WHERE task_text = %s", (task_name,))
                row = cursor.fetchone()
                if row:
                    task_id = row[0]
                else:
                    messagebox.showwarning("Task not found", f"Task '{task_name}' not found. It will be set to NULL.")
                cursor.close()
                conn.close()

            # Resolve subject_id from subject text (self-healing)
            subject_id = None
            resolved_subject_name = subject  # what we actually store
            if subject:
                conn = get_connection()
                cursor = conn.cursor(dictionary=True)

                # 1. Exact match
                cursor.execute(
                    "SELECT id, name FROM subjects WHERE name = %s",
                    (subject,)
                )
                row = cursor.fetchone()

                # 2. Normalized match — strip "N. " prefix, compare case-insensitively
                if not row:
                    import re as _re
                    def _norm(s):
                        return _re.sub(r'^\d+\.\s*', '', s or '').strip().lower()
                    target = _norm(subject)
                    cursor.execute(
                        "SELECT id, name FROM subjects WHERE active = 1"
                    )
                    for c in cursor.fetchall():
                        if _norm(c['name']) == target:
                            row = c
                            break

                if row:
                    subject_id = row['id']
                    resolved_subject_name = row['name']  # canonical spelling
                else:
                    messagebox.showwarning(
                        "Subject not found",
                        f"Subject '{subject}' not found. It will be set to NULL.\n\n"
                        f"Tip: add this subject to your syllabus, or rename "
                        f"the log entry manually."
                    )
                cursor.close()
                conn.close()

            # Now update or insert
            conn = get_connection()
            cursor = conn.cursor()
            if log_id:
                cursor.execute("SELECT id FROM pomodoro_log WHERE id = %s", (log_id,))
                if cursor.fetchone():
                    cursor.execute("""
                        UPDATE pomodoro_log
                        SET timestamp = %s, duration_min = %s, subject = %s, subject_id = %s,
                            notes = %s, task_id = %s, session_type = %s
                        WHERE id = %s
                    """, (timestamp_str, duration, resolved_subject_name, subject_id, notes, task_id, session_type, log_id))
                    if cursor.rowcount > 0:
                        updated += 1
                    else:
                        unchanged += 1
                else:
                    cursor.execute("""
                        INSERT INTO pomodoro_log (timestamp, phase, duration_min, subject, subject_id, notes, task_id, session_type)
                        VALUES (%s, 'work', %s, %s, %s, %s, %s, %s)
                    """, (timestamp_str, duration, subject, subject_id, notes, task_id, session_type))
                    inserted += 1
            else:
                cursor.execute("""
                    INSERT INTO pomodoro_log (timestamp, phase, duration_min, subject, subject_id, notes, task_id, session_type)
                    VALUES (%s, 'work', %s, %s, %s, %s, %s, %s)
                """, (timestamp_str, duration, subject, subject_id, notes, task_id, session_type))
                inserted += 1
            conn.commit()
            cursor.close()
            conn.close()

        # Show errors if any (indented correctly)
        if errors:
            messagebox.showerror("Errors", f"Encountered errors:\n" + "\n".join(errors[:5]))

        # Refresh log display
        self.log = self.load_log()
        self.refresh_log()
        # Turn off edit mode
        self.edit_log_var.set(False)
        self.toggle_edit_mode()

        # --- Natural language summary ---
        if updated == 0 and inserted == 0:
            msg = "No changes were made. Everything is already up to date."
        else:
            parts = []
            if updated > 0:
                parts.append(f"updated {updated} entr{'y' if updated == 1 else 'ies'}")
            if inserted > 0:
                parts.append(f"added {inserted} new entr{'y' if inserted == 1 else 'ies'}")
            msg = "Successfully " + " and ".join(parts) + "."

        messagebox.showinfo("Done", msg)

    def toggle_edit_mode(self):
        """Enable/disable editing of the study log."""
        if self.edit_log_var.get():
            # Enable editing
            self.log_text.config(state=tk.NORMAL)
            self.save_log_btn.grid()          # show save button
        else:
            # Disable editing and hide save button
            self.log_text.config(state=tk.DISABLED)
            self.save_log_btn.grid_remove()   # hide save button

    def toggle_complete(self):
        selection = self.task_listbox.curselection()
        if not selection:
            messagebox.showinfo("Info", "Select a task first.")
            return
        index = selection[0]
        task_id = self.task_listbox_task_ids[index]
        task = next((t for t in self.tasks if t['id'] == task_id), None)
        if not task:
            return
        new_status = 0 if task['completed'] else 1
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE pomodoro_tasks SET completed = %s WHERE id = %s", (new_status, task_id))
        conn.commit()
        cursor.close()
        conn.close()
        self.tasks = self.load_tasks()
        self.refresh_task_list()
        self.update_task_combo()
        status_text = "Un-completed" if new_status == 0 else "Completed"
        messagebox.showinfo("Task Updated", f"Task {status_text}!")

    def set_priority(self):
        selection = self.task_listbox.curselection()
        if not selection:
            messagebox.showinfo("Info", "Select a task first.")
            return
        index = selection[0]
        task_id = self.task_listbox_task_ids[index]
        task = next((t for t in self.tasks if t['id'] == task_id), None)
        if not task:
            return

        new_priority = simpledialog.askinteger(
            "Set Priority",
            f"Enter new priority (0-9) for:\n{task['task_text']}\n\n"
            "1 = Highest, 9 = High, 0 = Lowest\n"
            f"Current: {task['priority']}",
            minvalue=0, maxvalue=9,
            initialvalue=task['priority']
        )
        if new_priority is None:
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE pomodoro_tasks SET priority = %s WHERE id = %s", (new_priority, task_id))
        conn.commit()
        cursor.close()
        conn.close()
        self.tasks = self.load_tasks()
        self.refresh_task_list()
        self.update_task_combo()
        messagebox.showinfo("Priority Updated", f"Priority set to {new_priority}.")

    def clear_all_tasks(self):
        if not self.tasks:
            return
        confirm = messagebox.askyesno("Clear All", "Delete all tasks?")
        if not confirm:
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pomodoro_tasks")
        conn.commit()
        cursor.close()
        conn.close()
        self.tasks = self.load_tasks()
        self.refresh_task_list()
        self.update_task_combo()

    def refresh_task_list(self):
        self.task_listbox.delete(0, tk.END)
        self.task_listbox_task_ids = []
        show_completed = self.show_completed_var.get()
        for task in self.tasks:
            if not show_completed and task['completed']:
                continue
            priority = task['priority']
            if priority == 1:
                icon = '🔴'
            elif priority in (2, 3):
                icon = '🟧'
            elif priority in (4, 5, 6):
                icon = '🟨'
            elif priority in (7, 8, 9):
                icon = '🟩'
            else:
                icon = '⬜'
            label = f"[P{priority}] {icon} {task['task_text']}"
            if task['completed']:
                label += " ✓"
            self.task_listbox.insert(tk.END, label)
            self.task_listbox_task_ids.append(task['id'])
        self.update_task_combo()

    def refresh_subject_list(self):
        """
        Load subjects for the currently selected syllabus, grouped by
        paper. Each paper's subjects are re-numbered from 1 in the
        dropdown — independently of whatever number is baked into the
        stored name.
        """
        from collections import OrderedDict

        syllabus_key = self._syllabus_map.get(self.syllabus_var.get())

        if not syllabus_key:
            self.subject_combo['values'] = []
            self.subject_var.set('')
            self._subject_label_to_name = {}
            return

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                p.paper_key,
                p.display_name  AS paper_display,
                s.chapter       AS subject_code,
                s.name          AS subject_name
            FROM subjects s
            JOIN papers p   ON p.paper_key = s.paper
            JOIN syllabi sy ON sy.id       = p.syllabus_id
            WHERE s.active = 1
              AND sy.syllabus_key = %s
            ORDER BY p.display_order, p.display_name,
                     s.chapter, s.name
        """, (syllabus_key,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Group rows by paper, preserving query order
        by_paper = OrderedDict()
        for r in rows:
            by_paper.setdefault(r['paper_key'], {
                'display':  r['paper_display'],
                'subjects': [],
            })['subjects'].append(r)

        values = []
        label_to_name = {}

        for paper_key, bucket in by_paper.items():
            # Visual header — not a real subject
            header = f"── {bucket['display']} ──"
            values.append(header)

            for idx, subj in enumerate(bucket['subjects'], 1):
                bare = _strip_number_prefix(subj['subject_name'])
                label = f"   {idx:>2}. {bare}"
                values.append(label)
                label_to_name[label] = subj['subject_name']   # canonical DB name

        self.subject_combo['values'] = values
        self._subject_label_to_name = label_to_name

        # Auto-select the first real subject (skip the header row)
        first_real = next((v for v in values if not v.startswith('──')), None)
        self.subject_var.set(first_real or '')

    def load_syllabus_list(self):
        """Populate the syllabus dropdown with all active syllabi."""
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT syllabus_key, display_name, level
            FROM syllabi
            WHERE active = 1
            ORDER BY display_order, display_name
        """)
        syllabi = cursor.fetchall()
        cursor.close()
        conn.close()

        self._syllabus_map = {
            s['display_name']: s['syllabus_key'] for s in syllabi
        }
        values = [s['display_name'] for s in syllabi]
        self.syllabus_combo['values'] = values
        if values:
            self.syllabus_var.set(values[0])

    def on_syllabus_change(self):
        """Reload the subject list when the syllabus selection changes."""
        self.subject_var.set('')
        self.refresh_subject_list()

    def on_subject_combo_select(self, event=None):
        """
        If the user picks a paper header row, jump to that paper's first
        real subject. Otherwise do nothing.
        """
        label = self.subject_var.get()
        if not label or not label.startswith('──'):
            return
        values = list(self.subject_combo['values'])
        try:
            idx = values.index(label)
        except ValueError:
            return
        for v in values[idx + 1:]:
            if not v.startswith('──'):
                self.subject_var.set(v)
                return

    def update_task_combo(self):
        options = []
        for task in self.tasks:
            if task['completed']:
                continue
            priority = task['priority']
            label = f"[P{priority}] {task['task_text']}"
            options.append(label)
        self.task_combo['values'] = options
        if options and not self.task_var.get():
            self.task_var.set(options[0])
        elif not options:
            self.task_var.set("")
        self.combo_label_to_id = {}
        for task in self.tasks:
            if not task['completed']:
                label = f"[P{task['priority']}] {task['task_text']}"
                self.combo_label_to_id[label] = task['id']

    def _render_inline_bar(self, pct, fill_lbl, empty_lbl, width=10):
        """
        Update an inline Unicode block bar. The bar is `width` characters
        wide (each `█` = filled block, each `░` = empty block). The filled
        portion's colour shifts as progress increases:

            < 33%  red      — barely started
            < 66%  orange   — making progress
            < 100% blue     — nearly there
            >= 100% green   — goal reached
        """
        pct = max(0, min(100, float(pct)))
        filled = int(round(width * pct / 100.0))
        empty = width - filled

        if pct >= 100:
            color = "#2ecc71"   # green
        elif pct >= 66:
            color = "#3498db"   # blue
        elif pct >= 33:
            color = "#f39c12"   # orange
        else:
            color = "#e74c3c"   # red

        fill_lbl.config(text="█" * filled, fg=color)
        empty_lbl.config(text="░" * empty)

    def update_weekly_monthly_progress(self):
        now = datetime.now()
        # ---- Weekly: Sunday start ----
        # DAYOFWEEK: 1=Sunday, 2=Monday, ... 7=Saturday
        # Subtract (DAYOFWEEK(CURDATE()) - 1) days to get the most recent Sunday
        week_start_sql = "DATE_SUB(CURDATE(), INTERVAL (DAYOFWEEK(CURDATE()) - 1) DAY)"

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT SUM(duration_min)
            FROM pomodoro_log
            WHERE phase='work'
            AND DATE(timestamp) >= {week_start_sql}
        """)
        weekly = cursor.fetchone()[0] or 0

        # ---- Monthly: 1st of month ----
        month_start_sql = "DATE_FORMAT(CURDATE(), '%Y-%m-01')"
        cursor.execute(f"""
            SELECT SUM(duration_min)
            FROM pomodoro_log
            WHERE phase='work'
            AND DATE(timestamp) >= {month_start_sql}
        """)
        monthly = cursor.fetchone()[0] or 0
        cursor.close()
        conn.close()

        week_goal  = self.config.get('weekly_goal_hours', 10) * 60
        month_goal = self.config.get('monthly_goal_hours', 40) * 60

        # Keep the hidden bars in sync (harmless, useful for any external reader)
        self.weekly_bar['maximum'] = week_goal
        self.weekly_bar['value'] = min(weekly, week_goal)
        self.monthly_bar['maximum'] = month_goal
        self.monthly_bar['value'] = min(monthly, month_goal)

        # Percent complete
        weekly_f  = float(weekly  or 0)
        monthly_f = float(monthly or 0)
        week_pct  = (weekly_f  / week_goal  * 100.0) if week_goal  > 0 else 0.0
        month_pct = (monthly_f / month_goal * 100.0) if month_goal > 0 else 0.0

        # Refresh the inline block bars
        self._render_inline_bar(week_pct,
                                self.week_fill_lbl, self.week_empty_lbl)
        self._render_inline_bar(month_pct,
                                self.month_fill_lbl, self.month_empty_lbl)

        # Refresh the numeric text next to each bar
        wh, wm = divmod(int(weekly_f), 60)
        mh, mm = divmod(int(monthly_f), 60)
        self.weekly_label.config(
            text=f" {wh}h {wm}m/{week_goal//60}h")
        self.monthly_label.config(
            text=f" {mh}h {mm}m/{month_goal//60}h")

    def get_weekly_daily_totals(self):
        """Return a dict mapping weekday names to minutes studied for the current week (Sun-Sat)."""
        conn = get_connection()
        cursor = conn.cursor()
        # Group by day of week (0=Sunday, 1=Monday, ..., 6=Saturday)
        cursor.execute("""
            SELECT
                DAYOFWEEK(timestamp) - 1 AS dow,   -- 0=Sunday
                SUM(duration_min) AS total_min
            FROM pomodoro_log
            WHERE phase='work'
            AND DATE(timestamp) >= DATE_SUB(CURDATE(), INTERVAL (DAYOFWEEK(CURDATE()) - 1) DAY)
            GROUP BY dow
            ORDER BY dow
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        # Initialize all days with 0
        days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        totals = {day: 0 for day in days}
        for dow, total in rows:
            totals[days[dow]] = total or 0
        return totals

    def on_task_combo_select(self, event):
        label = self.task_var.get()
        print(f"[DEBUG] on_task_combo_select: label='{label}'")   # debug
        if not label:
            self.current_task_id = None
            return

        # Directly look up the task ID
        task_id = None
        if label in self.combo_label_to_id:
            task_id = self.combo_label_to_id[label]
            print(f"[DEBUG] Exact match found: task_id={task_id}")
        else:
            # Fuzzy match
            import re
            match = re.match(r'^\[P\d+\]\s*(.*)$', label)
            if match:
                task_text = match.group(1).strip()
                print(f"[DEBUG] Fuzzy matching task_text='{task_text}'")
                for lbl, tid in self.combo_label_to_id.items():
                    m = re.match(r'^\[P\d+\]\s*(.*)$', lbl)
                    if m and m.group(1).strip().lower() == task_text.lower():
                        task_id = tid
                        print(f"[DEBUG] Fuzzy match found: task_id={task_id}")
                        break

        if task_id is not None:
            self.current_task_id = task_id
            # Update priority spinbox
            task = next((t for t in self.tasks if t['id'] == task_id), None)
            if task:
                self.priority_var.set(str(task['priority']))
        else:
            self.current_task_id = None

    def on_task_select(self, event):
        selection = self.task_listbox.curselection()
        if selection:
            index = selection[0]
            task_id = self.task_listbox_task_ids[index]
            task = next((t for t in self.tasks if t['id'] == task_id), None)
            if task:
                # Update the priority spinbox to show the selected task's priority
                self.priority_var.set(str(task['priority']))
                if not task['completed']:
                    label = f"[P{task['priority']}] {task['task_text']}"
                    self.task_var.set(label)

    def show_context_menu(self, event):
        index = self.task_listbox.nearest(event.y)
        if index != -1:
            self.task_listbox.selection_clear(0, tk.END)
            self.task_listbox.selection_set(index)
            self.task_listbox.activate(index)
            self.task_menu.post(event.x_root, event.y_root)

    def get_week_stats(self):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                COALESCE(SUM(duration_min), 0) AS total_min,
                COUNT(*) AS sessions
            FROM pomodoro_log
            WHERE phase='work'
            AND DATE(timestamp) >= DATE_SUB(CURDATE(), INTERVAL (DAYOFWEEK(CURDATE()) - 1) DAY)
        """)
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row or {'total_min': 0, 'sessions': 0}

    def get_month_stats(self):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                COALESCE(SUM(duration_min), 0) AS total_min,
                COUNT(*) AS sessions
            FROM pomodoro_log
            WHERE phase='work'
            AND DATE(timestamp) >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
        """)
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row or {'total_min': 0, 'sessions': 0}

    def get_current_task_id(self):
        label = self.task_var.get()
        if not label:
            return None
        # Try exact match from combo_label_to_id
        if label in self.combo_label_to_id:
            return self.combo_label_to_id[label]
        # Fallback: fuzzy match (same as in log_session)
        import re
        match = re.match(r'^\[P\d+\]\s*(.*)$', label)
        if match:
            task_text = match.group(1).strip()
            for lbl, tid in self.combo_label_to_id.items():
                m = re.match(r'^\[P\d+\]\s*(.*)$', lbl)
                if m and m.group(1).strip().lower() == task_text.lower():
                    return tid
        return None

    def get_current_streak(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT DATE(timestamp) as date FROM pomodoro_log WHERE phase='work' ORDER BY date DESC")
        dates = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        if not dates:
            return 0
        streak = 0
        check = datetime.now().date()
        while check in dates:
            streak += 1
            check -= timedelta(days=1)
        return streak

    def update_streak_display(self):
        streak = self.get_current_streak()
        if streak == 0:
            self.streak_label.config(text="🔥 0-day")
        else:
            self.streak_label.config(text=f"🔥 {streak}-day")
    # ---------- DATABASE HELPERS ----------
    def load_config(self):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM pomodoro_settings WHERE id = 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            return {
                "work_min": row["work_min"],
                "short_break_min": row["short_break_min"],
                "long_break_min": row["long_break_min"],
                "cycles_before_long": row["cycles_before_long"],
                "daily_goal": row["daily_goal"],
                "weekly_goal_hours": row.get("weekly_goal_hours", 10),   # new
                "monthly_goal_hours": row.get("monthly_goal_hours", 40), # new
            }
        return {
            "work_min":25, "short_break_min":5, "long_break_min":15,
            "cycles_before_long":4, "daily_goal":12,
            "weekly_goal_hours":10, "monthly_goal_hours":40
        }

    def save_config(self, config):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE pomodoro_settings
            SET work_min=%s, short_break_min=%s, long_break_min=%s,
                cycles_before_long=%s, daily_goal=%s,
                weekly_goal_hours=%s, monthly_goal_hours=%s
            WHERE id=1
        """, (config["work_min"], config["short_break_min"],
            config["long_break_min"], config["cycles_before_long"],
            config["daily_goal"], config["weekly_goal_hours"],
            config["monthly_goal_hours"]))
        conn.commit()
        cursor.close()
        conn.close()

    def load_log(self):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT l.id, l.timestamp, l.phase, l.duration_min, l.subject, l.session_type,
                l.notes, l.task_id, t.task_text
            FROM pomodoro_log l
            LEFT JOIN pomodoro_tasks t ON l.task_id = t.id
            ORDER BY l.id DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        log = []
        for row in rows:
            log.append({
                "id": row["id"],
                "timestamp": row["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                "phase": row["phase"],
                "duration_min": row["duration_min"],
                "subject": row.get("subject", ""),
                "notes": row["notes"],
                "task_id": row.get("task_id"),
                "task_name": row.get("task_text", "") if row.get("task_text") else None,
                "session_type": row.get("session_type", "study")
            })
        return log

    def add_log_entry(self, entry):
        conn = get_connection()
        cursor = conn.cursor()
        subject_name = entry.get('subject')
        subject_id = None
        if subject_name:
            try:
                cur = conn.cursor()
                cur.execute("SELECT id FROM subjects WHERE name = %s", (subject_name,))
                row = cur.fetchone()
                if row:
                    subject_id = row[0]
                cur.close()
            except Exception:
                pass
        cursor.execute("""
            INSERT INTO pomodoro_log (timestamp, phase, duration_min, subject, subject_id, notes, task_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (entry["timestamp"], entry["phase"], entry["duration_min"],
            subject_name, subject_id, entry.get("notes"), entry.get("task_id")))
        conn.commit()
        cursor.close()
        conn.close()

    def log_session(self):
        """Fallback: log a work session without pause tracking."""
        subject_name = _strip_syllabus_tag(self.subject_var.get())
        subject_id = None
        if subject_name:
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM subjects WHERE name = %s", (subject_name,))
                row = cursor.fetchone()
                if row:
                    subject_id = row[0]
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"[DEBUG] Subject lookup error: {e}")

        # Get task ID from combobox
        label = self.task_var.get().strip()
        print(f"[DEBUG] log_session task label: '{label}'")
        task_id = None
        if label:
            # Try exact match from combo_label_to_id
            if label in self.combo_label_to_id:
                task_id = self.combo_label_to_id[label]
                print(f"[DEBUG] Exact match: {task_id}")
            else:
                # Fuzzy match
                import re
                match = re.match(r'^\[P\d+\]\s*(.*)$', label)
                if match:
                    task_text = match.group(1).strip()
                    print(f"[DEBUG] Fuzzy task_text: '{task_text}'")
                    for lbl, tid in self.combo_label_to_id.items():
                        m = re.match(r'^\[P\d+\]\s*(.*)$', lbl)
                        if m and m.group(1).strip().lower() == task_text.lower():
                            task_id = tid
                            print(f"[DEBUG] Fuzzy match: {task_id}")
                            break
                    # If still None, try direct DB lookup
                    if task_id is None:
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM pomodoro_tasks WHERE task_text = %s", (task_text,))
                        row = cursor.fetchone()
                        if row:
                            task_id = row[0]
                            print(f"[DEBUG] DB lookup found task_id={task_id}")
                        cursor.close()
                        conn.close()

        # If task_id remains None, we log without a task
        notes = self.notes_text.get("1.0", tk.END).strip()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pomodoro_log (timestamp, phase, duration_min, subject, subject_id, notes, task_id)
            VALUES (NOW(), 'work', %s, %s, %s, %s, %s)
        """, (self.config["work_min"], subject_name, subject_id, notes, task_id))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[DEBUG] Inserted log with task_id={task_id}")

    def count_today_pomodoros(self):
        today = datetime.now().date().isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM pomodoro_log
            WHERE DATE(timestamp) = %s AND phase = 'work'
        """, (today,))
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

    def get_today_summary(self):
        """Return task‑based summary for today."""
        today = datetime.now().date().isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(t.task_text, 'Uncategorized') AS task,
                SUM(l.duration_min) AS total_minutes,
                COUNT(*) AS sessions
            FROM pomodoro_log l
            LEFT JOIN pomodoro_tasks t ON l.task_id = t.id
            WHERE DATE(l.timestamp) = %s AND l.phase = 'work'
            GROUP BY task
            ORDER BY total_minutes DESC
        """, (today,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def get_today_summary_by_type(self):
        """Return session‑type summary for today."""
        today = datetime.now().date().isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                session_type,
                SUM(duration_min) AS total_minutes,
                COUNT(*) AS sessions
            FROM pomodoro_log
            WHERE DATE(timestamp) = %s AND phase = 'work'
            GROUP BY session_type
            ORDER BY total_minutes DESC
        """, (today,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def show_today_summary(self):
        # Task breakdown (existing)
        task_rows = self.get_today_summary()
        # Type breakdown (new)
        type_rows = self.get_today_summary_by_type()

        if not task_rows and not type_rows:
            messagebox.showinfo("Today's Summary", "No study sessions logged today yet.")
            return

        summary_win = tk.Toplevel(self.root)
        summary_win.title("Today's Study Summary")
        summary_win.geometry("700x500")
        summary_win.resizable(False, False)
        summary_win.configure(bg="#1e2a3a")

        ttk.Label(summary_win, text=f"Summary for {datetime.now().strftime('%Y-%m-%d')}",
                font=("Helvetica", 14, "bold")).pack(pady=10)

        # Notebook for two tabs
        notebook = ttk.Notebook(summary_win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ----- Tab 1: Tasks -----
        tab1 = ttk.Frame(notebook, padding="10")
        notebook.add(tab1, text="📋 By Task")

        if task_rows:
            columns = ("Task", "Time (min)", "Sessions")
            tree = ttk.Treeview(tab1, columns=columns, show="headings", height=10)
            tree.heading("Task", text="Task")
            tree.heading("Time (min)", text="Time (min)")
            tree.heading("Sessions", text="Sessions")
            tree.column("Task", width=250)
            tree.column("Time (min)", width=100, anchor=tk.CENTER)
            tree.column("Sessions", width=80, anchor=tk.CENTER)

            total_time = 0
            total_sessions = 0
            for task, minutes, sessions in task_rows:
                tree.insert("", tk.END, values=(task, minutes, sessions))
                total_time += minutes
                total_sessions += sessions
            tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            scrollbar = ttk.Scrollbar(tab1, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            total_hours = total_time // 60
            total_mins = total_time % 60
            footer = f"Total: {total_hours}h {total_mins}m  |  Sessions: {total_sessions}"
            ttk.Label(tab1, text=footer, font=("Helvetica", 10, "bold")).pack(pady=5)
        else:
            ttk.Label(tab1, text="No task data for today.").pack(pady=50)

        # ----- Tab 2: Session Types -----
        tab2 = ttk.Frame(notebook, padding="10")
        notebook.add(tab2, text="📊 By Session Type")

        if type_rows:
            columns = ("Type", "Time (min)", "Sessions")
            tree2 = ttk.Treeview(tab2, columns=columns, show="headings", height=10)
            tree2.heading("Type", text="Type")
            tree2.heading("Time (min)", text="Time (min)")
            tree2.heading("Sessions", text="Sessions")
            tree2.column("Type", width=150)
            tree2.column("Time (min)", width=100, anchor=tk.CENTER)
            tree2.column("Sessions", width=80, anchor=tk.CENTER)

            total_time2 = 0
            total_sessions2 = 0
            for stype, minutes, sessions in type_rows:
                display_type = stype if stype else "Unspecified"
                tree2.insert("", tk.END, values=(display_type, minutes, sessions))
                total_time2 += minutes
                total_sessions2 += sessions
            tree2.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            total_hours2 = total_time2 // 60
            total_mins2 = total_time2 % 60
            footer2 = f"Total: {total_hours2}h {total_mins2}m  |  Sessions: {total_sessions2}"
            ttk.Label(tab2, text=footer2, font=("Helvetica", 10, "bold")).pack(pady=5)
        else:
            ttk.Label(tab2, text="No session type data for today.").pack(pady=50)

        ttk.Button(summary_win, text="Close", command=summary_win.destroy).pack(pady=5)

    def start_timer(self):
        # ----- If resuming from pause -----
        if self.paused:
            self.paused = False
            self.pause_btn.config(text="Pause")
            self.start_btn.config(state=tk.DISABLED)
            self.timer_running = True
            self.update_timer()
            self.save_state()
            return

        # reset pause tracking for a fresh session
        self.pauses = []
        self.pause_start_time = None

        # ----- Set duration for the phase -----
        if self.current_phase == "work":
            minutes = self.config["work_min"]
        elif self.current_phase == "short_break":
            minutes = self.config["short_break_min"]
        else:
            minutes = self.config["long_break_min"]

        self.remaining_seconds = minutes * 60
        self.timer_running = True
        self.paused = False
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL, text="Pause")
        self.update_display()
        self.update_timer()
        self.save_state()

    def update_timer(self):
        if not self.root.winfo_exists():
            return
        if not self.timer_running or self.paused:
            return
        if self.remaining_seconds <= 0:
            self.timer_complete()
            return
        self.remaining_seconds -= 1
        self.update_display()
        # Store the after ID so we can cancel it later
        self._timer_after_id = self.root.after(1000, self.update_timer)

    def pause_timer(self):
        if self.timer_running and not self.paused:
            # Pausing
            self.paused = True
            self.pause_btn.config(text="Resume")
            self.start_btn.config(state=tk.NORMAL)
            self.pause_start_time = datetime.now()   # record pause start
            self.save_state()
        elif self.paused:
            # Resuming: record pause end and duration
            if self.pause_start_time:
                pause_end = datetime.now()
                duration = (pause_end - self.pause_start_time).total_seconds()
                self.pauses.append((self.pause_start_time, pause_end, duration))
                self.pause_start_time = None
            self.paused = False
            self.pause_btn.config(text="Pause")
            self.start_btn.config(state=tk.DISABLED)
            self.timer_running = True
            self.save_state()
            self.update_timer()

    def reset_timer(self):
        if self.timer_running or self.paused:
            confirm = messagebox.askyesno("Reset Timer",
                                        "Are you sure you want to reset?\n\n"
                                        "This will discard the current session progress.")
            if not confirm:
                return

        self.timer_running = False
        self.paused = False
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED, text="Pause")
        self.current_phase = "work"
        self.remaining_seconds = self.config["work_min"] * 60
        self.phase_label.config(text="Work")
        self.update_display()
        self.clear_state()

    def timer_complete(self):
        self.timer_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED, text="Pause")

        # Beep (ignore errors)
        try:
            self.sound_func()
        except Exception:
            pass

        completed_phase = self.current_phase
        print(f"[DEBUG] Timer complete. Phase: {completed_phase}")

        try:
            if completed_phase == "work":
                # ============================================================
                # 1. PERSIST FIRST — before any blocking modal.
                #    If the user closes the window (or walks away) before
                #    clicking OK on the notification, the session must already
                #    be in the DB.
                # ============================================================

                # Midnight rollover check (updates today_count from DB)
                self._check_day_rollover()

                # Insert the log row NOW
                self.log_work_session()

                # Refresh the on-screen log so it shows the new row immediately
                self.log = self.load_log()
                self.refresh_log()
                self.log_text.update_idletasks()

                # ============================================================
                # 2. NOW show the completion notification
                # ============================================================
                import random
                quote = random.choice(QUOTES) if QUOTES else "Great work!"
                session_type_shown = self.type_var.get().strip() or 'study'
                messagebox.showinfo(
                    "🎉 Session Complete!",
                    f"Great work!\n\n"
                    f"Type: {session_type_shown}   •   {self.config['work_min']} min\n\n"
                    f"{quote}"
                )

                # ============================================================
                # 3. Post-notification: badges, counters, phase switch
                # ============================================================
                try:
                    self.check_and_award_badges()
                except Exception as e:
                    print(f"[DEBUG] Badge error: {e}")

                self.cycles_completed += 1
                self.today_count += 1
                self.update_progress()

                # Which break next?
                if self.cycles_completed % self.config["cycles_before_long"] == 0:
                    self.current_phase = "long_break"
                    self.remaining_seconds = self.config["long_break_min"] * 60
                    self.phase_label.config(text="Long Break")
                else:
                    self.current_phase = "short_break"
                    self.remaining_seconds = self.config["short_break_min"] * 60
                    self.phase_label.config(text="Short Break")

                print(f"[DEBUG] New phase: {self.current_phase}")

            else:
                # Break complete – go back to work
                self.current_phase = "work"
                self.remaining_seconds = self.config["work_min"] * 60
                self.phase_label.config(text="Work")

            self.update_display()
            self.save_state()

            # Only show the "phase completed" popup for BREAKS.
            # For work sessions, the "Session Complete!" popup above already
            # told the user — showing a second dialog on top of it is redundant.
            if completed_phase != "work":
                messagebox.showinfo("Pomodoro", f"{completed_phase.capitalize()} phase completed!")

        except Exception as e:
            print(f"[ERROR] timer_complete() crashed: {e}")
            import traceback
            traceback.print_exc()
            self.current_phase = "work"
            self.remaining_seconds = self.config["work_min"] * 60
            self.phase_label.config(text="Work")
            self.update_display()
            self.save_state()
            messagebox.showerror("Error", f"Timer completion failed: {e}\nReset to work phase.")

    def log_work_session(self):
        """Insert a log entry for a completed work session."""
        label = self.subject_var.get()
        # Map the display label back to the canonical DB name
        subject_name = self._subject_label_to_name.get(label)
        if not subject_name:
            subject_name = _strip_number_prefix(
                _strip_syllabus_tag(label)
            )
        subject_id = None
        if subject_name:
            try:
                import re as _re
                conn = get_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "SELECT id, name FROM subjects WHERE name = %s",
                    (subject_name,)
                )
                row = cursor.fetchone()
                if not row:
                    def _norm(s):
                        return _re.sub(r'^\d+\.\s*', '', s or '').strip().lower()
                    target = _norm(subject_name)
                    cursor.execute(
                        "SELECT id, name FROM subjects WHERE active = 1"
                    )
                    for c in cursor.fetchall():
                        if _norm(c['name']) == target:
                            row = c
                            break
                if row:
                    subject_id = row['id']
                    subject_name = row['name']  # canonical
                cursor.close()
                conn.close()
            except Exception:
                pass

        # Get task ID
        label = self.task_var.get().strip()
        task_id = None
        if label:
            if label in self.combo_label_to_id:
                task_id = self.combo_label_to_id[label]
            else:
                import re
                match = re.match(r'^\[P\d+\]\s*(.*)$', label)
                if match:
                    task_text = match.group(1).strip()
                    for lbl, tid in self.combo_label_to_id.items():
                        m = re.match(r'^\[P\d+\]\s*(.*)$', lbl)
                        if m and m.group(1).strip().lower() == task_text.lower():
                            task_id = tid
                            break

        notes = self.notes_text.get("1.0", tk.END).strip()
        session_type = self.type_var.get().strip()   # e.g., "study", "revision", etc.

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pomodoro_log (timestamp, phase, duration_min, subject, subject_id, notes, task_id, session_type)
            VALUES (NOW(), 'work', %s, %s, %s, %s, %s, %s)
        """, (self.config["work_min"], subject_name, subject_id, notes, task_id, session_type))
        conn.commit()
        cursor.close()
        conn.close()

    def update_display(self):
        mins = self.remaining_seconds // 60
        secs = self.remaining_seconds % 60
        self.time_label.config(text=f"{mins:02d}:{secs:02d}")
        # Update progress bar
        total_seconds = 0
        if self.current_phase == "work":
            total_seconds = self.config["work_min"] * 60
        elif self.current_phase == "short_break":
            total_seconds = self.config["short_break_min"] * 60
        else:
            total_seconds = self.config["long_break_min"] * 60
        if total_seconds > 0:
            progress = ((total_seconds - self.remaining_seconds) / total_seconds) * 100
            self.progress_bar['value'] = progress

    def update_progress(self):
        self.update_streak_display()
        goal = self.config["daily_goal"]
        self.progress_label.config(text=f"Today: {self.today_count} / {goal} Pomodoros")
        self.daily_bar['maximum'] = goal
        self.daily_bar['value'] = self.today_count
        self.update_weekly_monthly_progress()

    def _check_day_rollover(self):
        """
        Detect when the calendar date has changed (midnight crossing).
        When it does, re-query the DB so 'Today' counters reset cleanly,
        without needing an app restart.
        Returns True if a rollover happened.
        """
        current_date = datetime.now().date()
        if getattr(self, '_today_date', None) == current_date:
            return False

        self._today_date = current_date

        # Recompute from the database (now points at the new day's data)
        new_today = self.count_today_pomodoros()
        self.today_count = new_today
        self.cycles_completed = new_today

        # Persist the new cycle count so state saves stay consistent
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pomodoro_state SET cycles_completed = %s WHERE id = 1",
                (new_today,)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass

        # Refresh the UI bars/labels
        self.update_progress()
        return True


    def _schedule_day_rollover_check(self):
        """Run the rollover check every 30 seconds, forever."""
        self._check_day_rollover()
        self._rollover_after_id = self.root.after(30_000, self._schedule_day_rollover_check)

    def open_settings_dialog(self):
        """Open Pomodoro settings in a modal dialog."""
        win = tk.Toplevel(self.root)
        win.title("⚙️ Pomodoro Settings")
        win.geometry("400x420")
        win.resizable(False, False)
        win.configure(bg="#1e2a3a")
        win.transient(self.root)
        win.grab_set()

        outer = ttk.LabelFrame(win, text="⚙️ Settings", padding="15")
        outer.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        outer.columnconfigure(1, weight=1)

        # Working copies of the values so Cancel is truly a cancel
        d_work   = tk.StringVar(value=str(self.config["work_min"]))
        d_short  = tk.StringVar(value=str(self.config["short_break_min"]))
        d_long   = tk.StringVar(value=str(self.config["long_break_min"]))
        d_cycles = tk.StringVar(value=str(self.config["cycles_before_long"]))
        d_goal   = tk.StringVar(value=str(self.config["daily_goal"]))
        d_weekly = tk.StringVar(value=str(self.config["weekly_goal_hours"]))
        d_month  = tk.StringVar(value=str(self.config["monthly_goal_hours"]))

        row = 0
        def _add(label, var):
            nonlocal row
            ttk.Label(outer, text=label).grid(row=row, column=0,
                                              sticky=tk.W, pady=4, padx=(0, 15))
            ttk.Entry(outer, textvariable=var, width=10).grid(
                row=row, column=1, sticky=tk.W, pady=4)
            row += 1

        _add("Work (min):", d_work)
        _add("Short break (min):", d_short)
        _add("Long break (min):", d_long)
        _add("Cycles before long:", d_cycles)
        _add("Daily goal:", d_goal)
        _add("Weekly goal (hours):", d_weekly)
        _add("Monthly goal (hours):", d_month)

        def save_and_close():
            try:
                work   = int(d_work.get())
                short  = int(d_short.get())
                long_  = int(d_long.get())
                cycles = int(d_cycles.get())
                goal   = int(d_goal.get())
                weekly = int(d_weekly.get())
                month  = int(d_month.get())
                if min(work, short, long_, cycles, goal, weekly, month) <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error",
                                     "Please enter valid positive integers.")
                return

            self.config.update({
                "work_min": work,
                "short_break_min": short,
                "long_break_min": long_,
                "cycles_before_long": cycles,
                "daily_goal": goal,
                "weekly_goal_hours": weekly,
                "monthly_goal_hours": month,
            })
            self.save_config(self.config)

            # Live-update anything the timer shows
            if not self.timer_running:
                self.remaining_seconds = work * 60
                self.update_display()
            self.daily_bar['maximum'] = goal
            self.daily_bar['value'] = self.today_count
            self.update_progress()

            messagebox.showinfo("Settings", "Settings saved successfully.")
            win.destroy()

        btn_frame = ttk.Frame(outer)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(20, 0))
        ttk.Button(btn_frame, text="💾 Save",
                   command=save_and_close).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel",
                   command=win.destroy).pack(side=tk.LEFT, padx=5)

    # ---------- SETTINGS ----------
    def save_settings(self):
        try:
            work = int(self.work_var.get())
            short = int(self.short_var.get())
            long_ = int(self.long_var.get())
            cycles = int(self.cycles_var.get())
            goal = int(self.goal_var.get())
            if work <= 0 or short <= 0 or long_ <= 0 or cycles <= 0 or goal <= 0:
                raise ValueError
            self.config.update({
                "work_min": work,
                "short_break_min": short,
                "long_break_min": long_,
                "cycles_before_long": cycles,
                "daily_goal": goal,
                "weekly_goal_hours": int(self.weekly_goal_var.get()),
                "monthly_goal_hours": int(self.monthly_goal_var.get()),
            })
            self.save_config(self.config)
            if not self.timer_running:
                self.remaining_seconds = work * 60
                self.update_display()
            self.daily_bar['maximum'] = goal
            self.daily_bar['value'] = self.today_count
            # ----- ADD THIS LINE -----
            self.update_progress()
            # ---------------------------
            messagebox.showinfo("Settings", "Settings saved successfully!")
        except:
            messagebox.showerror("Error", "Please enter valid positive integers.")

    def refresh_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)

        if not self.log:
            self.log_text.insert(tk.END, "No study sessions logged yet.")
        else:
            # for entry in reversed(self.log):        # all entries, newest first, no limit
            for entry in reversed(self.log[:50]):
                line = f"[#{entry['id']}] {entry['timestamp']} - {entry['duration_min']} min"
                if entry.get('task_name'):
                    line += f" [Task: {entry['task_name']}]"
                if entry.get('subject'):
                    line += f" [Subject: {entry['subject']}]"
                if entry.get('session_type'):
                    line += f" ({entry['session_type']})"
                self.log_text.insert(tk.END, line + "\n")
                if entry['notes']:
                    self.log_text.insert(tk.END, f"  Notes: {entry['notes']}\n")
                self.log_text.insert(tk.END, "-" * 40 + "\n")

        self.log_text.config(state=tk.NORMAL if self.edit_log_var.get() else tk.DISABLED)
        self.log_text.see(tk.END)
        self.log_text.update_idletasks()

    def _beep(self):
        """Cross‑platform beep – works on Windows, macOS, and Linux."""
        import sys, subprocess, os, platform, shutil, tempfile, wave, struct, math

        # ----- 1. Terminal bell (non‑blocking) -----
        try:
            sys.stdout.write('\a')
            sys.stdout.flush()
        except Exception:
            pass

        system = platform.system()

        # ----- 2. Windows: winsound -----
        if system == 'Windows':
            try:
                import winsound
                winsound.Beep(440, 300)
                return
            except Exception:
                pass
            try:
                winsound.MessageBeep()
                return
            except Exception:
                pass

        # ----- 3. macOS: afplay with system sounds -----
        if system == 'Darwin':
            sounds = [
                '/System/Library/Sounds/Glass.aiff',
                '/System/Library/Sounds/Ping.aiff',
                '/System/Library/Sounds/Bottle.aiff',
                '/System/Library/Sounds/Tink.aiff',
            ]
            for s in sounds:
                if os.path.exists(s) and shutil.which('afplay'):
                    try:
                        subprocess.run(['afplay', s], check=False, timeout=1,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return
                    except Exception:
                        continue
            # Fallback: use 'say' to produce a tone
            try:
                if shutil.which('say'):
                    subprocess.run(['say', 'beep'], check=False, timeout=1,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
            except Exception:
                pass

        # ----- 4. Linux / other Unix: try system sounds with mplayer/paplay -----
        # (This also runs on other Unices if they have the files)
        system_sounds = [
            '/usr/share/sounds/freedesktop/stereo/bell.oga',
            '/usr/share/sounds/alsa/Noise.wav',
            '/usr/share/sounds/gnome/default/alerts/glass.ogg',
            '/usr/share/sounds/ubuntu/stereo/bell.ogg',
        ]
        players = [
            ('mplayer', ['mplayer']),
            ('paplay', ['paplay']),
            ('play', ['play']),
            ('ffplay', ['ffplay', '-nodisp', '-autoexit']),
        ]
        for sound in system_sounds:
            if os.path.exists(sound):
                for name, base_cmd in players:
                    if shutil.which(name):
                        try:
                            subprocess.run(base_cmd + [sound], check=False, timeout=2,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            return
                        except Exception:
                            continue

        # ----- 5. Generate sine WAV and try common players (Linux / generic) -----
        try:
            freq, duration, sample_rate = 440, 0.3, 44100
            num_samples = int(sample_rate * duration)
            amplitude = 16000
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                wf = wave.open(tmp, 'wb')
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                for i in range(num_samples):
                    value = int(amplitude * math.sin(2 * math.pi * freq * i / sample_rate))
                    wf.writeframesraw(struct.pack('<h', value))
                wf.close()
                tmp_path = tmp.name

            for name, cmd in [
                ('mplayer', ['mplayer', tmp_path]),
                ('paplay', ['paplay', tmp_path]),
                ('aplay', ['aplay', tmp_path]),
                ('play', ['play', tmp_path]),
                ('ffplay', ['ffplay', '-nodisp', '-autoexit', tmp_path]),
            ]:
                if shutil.which(name):
                    try:
                        subprocess.run(cmd, check=False, timeout=2,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        os.unlink(tmp_path)
                        return
                    except Exception:
                        continue
            os.unlink(tmp_path)
        except Exception:
            pass

        # ----- 6. Tkinter bell (may not work on Wayland / some systems) -----
        try:
            self.root.bell()
        except Exception:
            pass

        # ----- 7. Visual fallback (flash window title + popup) -----
        try:
            original_title = self.root.title()
            self.root.title("🔔 TIME'S UP! 🔔")
            self.root.after(3000, lambda: self.root.title(original_title))
            popup = tk.Toplevel(self.root)
            popup.title("Pomodoro")
            popup.geometry("300x100")
            popup.resizable(False, False)
            popup.attributes('-topmost', True)
            ttk.Label(popup, text="⏰ Time's up!", font=("Helvetica", 18)).pack(pady=20)
            popup.after(3000, popup.destroy)
            popup.lift()
            popup.focus_force()
        except Exception:
            pass

        # ----- 8. Last resort: plain message box -----
        try:
            messagebox.showinfo("Pomodoro", "⏰ Time's up! (no sound available)")
        except Exception:
            pass

    # ---------- STATE PERSISTENCE ----------
    def _current_canonical_subject(self):
        """Return the DB-canonical subject name for the current selection."""
        label = self.subject_var.get()
        if not label or label.startswith('──'):
            return ''
        canonical = self._subject_label_to_name.get(label)
        if canonical:
            return canonical
        return _strip_number_prefix(_strip_syllabus_tag(label))

    def save_state(self):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            current_task_id = self.get_current_task_id()  # helper to get selected task ID
            cursor.execute("""
                REPLACE INTO pomodoro_state
                (id, current_phase, remaining_seconds, notes, subject, cycles_completed,
                session_type, task_id)   -- added two new columns
                VALUES (1, %s, %s, %s, %s, %s, %s, %s)
            """, (
                self.current_phase,
                self.remaining_seconds,
                self.notes_text.get("1.0", tk.END).strip(),
                self._current_canonical_subject(),
                self.cycles_completed,
                self.type_var.get().strip(),   # session_type
                current_task_id                # task_id (can be None)
            ))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass

    def clear_state(self):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pomodoro_state
                SET remaining_seconds = 0, updated_at = NOW()
                WHERE id = 1
            """)
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass

    def load_state(self):
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM pomodoro_state WHERE id = 1")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row and row['remaining_seconds'] > 0:
                updated = row['updated_at']
                if updated and (datetime.now() - updated).total_seconds() < 7200:
                    return row
            return None
        except Exception:
            return None

    def restore_state_if_any(self):
        state = self.load_state()
        if not state:
            return

        msg = (f"Resume previous session?\n\n"
            f"Phase: {state['current_phase'].capitalize()}\n"
            f"Remaining: {state['remaining_seconds']//60}m {state['remaining_seconds']%60}s\n"
            f"Subject: {state.get('subject', '') or '(none)'}\n"
            f"Cycles completed: {state['cycles_completed']}\n\n"
            f"Notes: {state.get('notes', '')[:100]}...")
        answer = messagebox.askyesno("Resume Session", msg)
        if answer:
            # Restore core state
            self.current_phase = state['current_phase']
            self.remaining_seconds = state['remaining_seconds']
            self.cycles_completed = state['cycles_completed']

            if state.get('subject'):
                canonical = state['subject'].strip()
                chosen = None
                # 1. Exact match via the label map
                for label, name in self._subject_label_to_name.items():
                    if name == canonical:
                        chosen = label
                        break
                # 2. Fallback: match by stripping the number prefix
                if not chosen:
                    bare = _strip_number_prefix(
                        _strip_syllabus_tag(canonical)
                    )
                    for label in self.subject_combo['values']:
                        if label.startswith('──'):
                            continue
                        if _strip_number_prefix(
                                _strip_syllabus_tag(label)) == bare:
                            chosen = label
                            break
                self.subject_var.set(chosen or canonical)
            else:
                self.subject_var.set('')

            # ---------- NEW: Restore session type ----------
            if state.get('session_type'):
                self.type_var.set(state['session_type'])
            else:
                self.type_var.set('study')  # default

            # ---------- NEW: Restore task ----------
            task_id = state.get('task_id')
            if task_id:
                # Find the task in self.tasks (which should be already loaded)
                task = next((t for t in self.tasks if t['id'] == task_id), None)
                if task:
                    label = f"[P{task['priority']}] {task['task_text']}"
                    # Ensure the combo has this label; if not, add it temporarily?
                    # Actually, the combo values are built from tasks, so it should exist.
                    self.task_var.set(label)
                    self.current_task_id = task_id
                else:
                    # Task may have been deleted; leave as default
                    self.current_task_id = None
            else:
                self.current_task_id = None

            # Restore notes
            self.notes_text.delete("1.0", tk.END)
            self.notes_text.insert("1.0", state.get('notes', ''))
            self.phase_label.config(text=self.current_phase.capitalize())
            self.update_display()

            # Set timer as paused (ready to resume when user clicks Start)
            self.paused = True
            self.timer_running = False
            self.start_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.NORMAL, text="Resume")

            messagebox.showinfo("Restored", "Session restored. Click Start to resume.")
        else:
            # User declines – clear old state and reset cycles to today's count
            self.clear_state()
            self.today_count = self.count_today_pomodoros()
            self.cycles_completed = self.today_count
            self.current_phase = "work"
            self.remaining_seconds = self.config["work_min"] * 60
            self.phase_label.config(text="Work")
            self.update_display()
            self.update_progress()

    def schedule_state_save(self):
        if self.timer_running or self.paused:
            self.save_state()
        if hasattr(self, 'root') and self.root.winfo_exists():
            self._after_id = self.root.after(5000, self.schedule_state_save)

    def refresh_badges(self):
        """Recalculate badges from current logs and remove those that no longer qualify."""
        from .db import get_connection
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get current totals
        cursor.execute("SELECT COUNT(*) as total FROM pomodoro_log WHERE phase = 'work'")
        total_sessions = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(DISTINCT DATE(timestamp)) as days FROM pomodoro_log WHERE phase = 'work'")
        days_active = cursor.fetchone()['days']

        # Streak
        streak = self.get_current_streak()

        cursor.execute("SELECT COUNT(*) as early FROM pomodoro_log WHERE phase='work' AND TIME(timestamp) < '08:00:00'")
        early_bird = cursor.fetchone()['early'] > 0
        cursor.execute("SELECT COUNT(*) as late FROM pomodoro_log WHERE phase='work' AND TIME(timestamp) > '22:00:00'")
        night_owl = cursor.fetchone()['late'] > 0

        cursor.execute("""
            SELECT subject, SUM(duration_min) as total FROM pomodoro_log
            WHERE phase='work' AND subject IS NOT NULL AND subject != ''
            GROUP BY subject HAVING total >= 300 LIMIT 1
        """)
        specialist = cursor.fetchone() is not None

        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        cursor.execute("""
            SELECT COUNT(DISTINCT subject) as distinct_subjects
            FROM pomodoro_log
            WHERE phase='work' AND subject IS NOT NULL AND subject != ''
            AND timestamp >= %s
        """, (week_start,))
        distinct = cursor.fetchone()['distinct_subjects']
        balanced = distinct >= 3

        # Determine which badges should be earned
        earned = []
        if total_sessions >= 1:     earned.append('first_pomodoro')
        if total_sessions >= 10:    earned.append('ten_sessions')
        if total_sessions >= 50:    earned.append('fifty_sessions')
        if total_sessions >= 100:   earned.append('hundred_sessions')
        if streak >= 5:             earned.append('five_day_streak')
        if streak >= 10:            earned.append('ten_day_streak')
        if early_bird:              earned.append('early_bird')
        if night_owl:               earned.append('night_owl')
        if specialist:              earned.append('subject_specialist')
        if balanced:                earned.append('balanced_learner')

        # Clear all user_badges and re-insert those that qualify
        cursor.execute("DELETE FROM user_badges")
        for b in earned:
            cursor.execute("INSERT INTO user_badges (badge_name) VALUES (%s)", (b,))
        conn.commit()
        cursor.close()
        conn.close()
        # messagebox.showinfo("Badges Refreshed", f"{len(earned)} badges currently active.")

    # ---------- OVERALL STATS ----------
    def show_overall_stats(self):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT DATE(timestamp) as date, SUM(duration_min) as total_min, COUNT(*) as sessions
            FROM pomodoro_log
            WHERE phase = 'work' AND timestamp >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY DATE(timestamp)
            ORDER BY date
        """)
        trend_data = cursor.fetchall()
        dates = [row['date'].strftime('%m-%d') for row in trend_data] if trend_data else []
        minutes = [float(row['total_min']) for row in trend_data] if trend_data else []

        cursor.execute("""
            SELECT
                l.subject AS subject,
                SUM(l.duration_min) AS total_min,
                COUNT(*) AS sessions
            FROM pomodoro_log l
            WHERE l.phase = 'work' AND l.subject IS NOT NULL AND l.subject != ''
            GROUP BY l.subject
            ORDER BY total_min DESC
        """)
        subject_data = cursor.fetchall()
        subjects = [row['subject'] for row in subject_data if row['total_min'] > 0]
        subject_mins = [float(row['total_min']) for row in subject_data if row['total_min'] is not None and float(row['total_min']) > 0]

        cursor.execute("""
            SELECT
                COALESCE(t.task_text, 'Uncategorized Task') as task_text,
                SUM(l.duration_min) as total_min
            FROM pomodoro_log l
            LEFT JOIN pomodoro_tasks t ON l.task_id = t.id
            WHERE l.phase = 'work'
            GROUP BY l.task_id
            ORDER BY total_min DESC
            LIMIT 5
        """)
        task_data = cursor.fetchall()
        tasks = [row['task_text'] for row in task_data if row['total_min'] > 0]
        task_mins = [float(row['total_min']) for row in task_data if row['total_min'] is not None and float(row['total_min']) > 0]

        cursor.execute("""
            SELECT HOUR(timestamp) as hour, COUNT(*) as sessions
            FROM pomodoro_log
            WHERE phase = 'work'
            GROUP BY HOUR(timestamp)
            ORDER BY hour
        """)
        hourly_data = cursor.fetchall()
        hour_labels = [f"{row['hour']}:00" for row in hourly_data]
        hourly_sessions = [row['sessions'] for row in hourly_data]

        cursor.execute("""
            SELECT DISTINCT DATE(timestamp) as date
            FROM pomodoro_log
            WHERE phase = 'work'
            ORDER BY date DESC
        """)
        days_list = [row['date'] for row in cursor.fetchall()]
        streak = 0
        if days_list:
            current = datetime.now().date()
            if current in days_list or (current - timedelta(days=1)) in days_list:
                streak = 1
                check_date = current - timedelta(days=1)
                while check_date in days_list:
                    streak += 1
                    check_date -= timedelta(days=1)
            else:
                streak = 0

        cursor.execute("""
            SELECT
                COUNT(*) as total_sessions,
                SUM(duration_min) as total_minutes,
                AVG(duration_min) as avg_session
            FROM pomodoro_log
            WHERE phase = 'work'
        """)
        totals = cursor.fetchone()
        if totals:
            totals = {
                'total_sessions': totals['total_sessions'] or 0,
                'total_minutes': totals['total_minutes'] or 0,
                'avg_session': totals['avg_session'] or 0
            }
        else:
            totals = {'total_sessions': 0, 'total_minutes': 0, 'avg_session': 0}

        cursor.close()
        conn.close()

        stats_win = tk.Toplevel(self.root)
        stats_win.title("📊 Overall Study Analytics")
        stats_win.geometry("1000x700")
        stats_win.configure(bg="#1e2a3a")

        # ---- NEW: Track figures and close them on window destroy ----
        figures = []

        def close_figures():
            for fig in figures:
                plt.close(fig)

        stats_win.bind('<Destroy>', lambda e: close_figures())

        notebook = ttk.Notebook(stats_win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        badge_tab = ttk.Frame(notebook)
        notebook.add(badge_tab, text="🏅 Badges")

        # Query badges
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.badge_name, b.description, b.icon, (u.id IS NOT NULL) as earned
            FROM pomodoro_badges b
            LEFT JOIN user_badges u ON b.badge_name = u.badge_name
            ORDER BY b.badge_name
        """)
        badge_rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Display as a grid
        badge_frame = ttk.Frame(badge_tab, padding="10")
        badge_frame.pack(fill=tk.BOTH, expand=True)
        row_count = 0
        col_count = 0
        for b in badge_rows:
            # Earned badges get a distinct style; locked ones stay muted
            style_name = 'Earned.TFrame' if b['earned'] else 'Locked.TFrame'

            frame = ttk.Frame(badge_frame, relief="solid", borderwidth=1, style=style_name)
            frame.grid(row=row_count, column=col_count, padx=5, pady=5, sticky="nsew")

            ttk.Label(frame, text=b['icon'], font=("Helvetica", 24)).pack(pady=2)
            ttk.Label(frame, text=b['badge_name'].replace('_', ' ').title(),
                        font=("Helvetica", 10, "bold")).pack()
            ttk.Label(frame, text=b['description'],
                        font=("Helvetica", 8), wraplength=120).pack(pady=2)

            col_count += 1
            if col_count >= 4:
                col_count = 0
                row_count += 1

        tab1 = ttk.Frame(notebook)
        notebook.add(tab1, text="🔥 Summary & Streak")

        summary_text = f"""
        🏆 CURRENT STUDY STREAK: {streak} days!
        {'🔥 Keep going! You are on fire!' if streak >= 5 else '💪 Consistency is key. Start a new streak today!'}

        📊 LIFETIME TOTALS:
        • Total Sessions : {totals['total_sessions'] if totals else 0}
        • Total Time     : {totals['total_minutes'] // 60}h {totals['total_minutes'] % 60}m
        • Avg Session    : {totals['avg_session']:.0f} minutes
        """

        ttk.Label(tab1, text=summary_text, font=("Helvetica", 12), justify=tk.LEFT).pack(anchor=tk.W, padx=20, pady=20)

        goal = self.config.get("daily_goal", 12)
        today_count = self.count_today_pomodoros()
        progress_pct = min(100, (today_count / goal) * 100)

        ttk.Label(tab1, text=f"🎯 Today's Progress: {today_count} / {goal} Pomodoros", font=("Helvetica", 11)).pack(anchor=tk.W, padx=20)
        progress_bar = ttk.Progressbar(tab1, length=400, mode='determinate', maximum=goal, value=today_count)
        progress_bar.pack(anchor=tk.W, padx=20, pady=10)
        ttk.Label(tab1, text=f"{progress_pct:.0f}% Complete", font=("Helvetica", 10)).pack(anchor=tk.W, padx=20)

        # ---- Week/Month tab with bar chart ----
        tab_week = ttk.Frame(notebook)
        notebook.add(tab_week, text="📅 Week/Month")

        # Fetch weekly daily data
        daily = self.get_weekly_daily_totals()
        week_days = list(daily.keys())
        week_minutes = list(daily.values())

        # Create a bar chart
        fig_week, ax_week = plt.subplots(figsize=(8, 4))
        figures.append(fig_week)
        ax_week.bar(week_days, week_minutes, color='#4CAF50')
        ax_week.set_title('Daily Study Time (Current Week)')
        ax_week.set_ylabel('Minutes')
        ax_week.set_xlabel('Day')
        # Add value labels on top of bars
        for i, v in enumerate(week_minutes):
            if v > 0:
                ax_week.text(i, v + 2, str(v), ha='center', fontsize=9)

        canvas_week = FigureCanvasTkAgg(fig_week, master=tab_week)
        canvas_week.draw()
        canvas_week.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Text summary (use week and month stats)
        week = self.get_week_stats()
        month = self.get_month_stats()

        week_total = week['total_min'] or 0
        month_total = month['total_min'] or 0

        week_h = week_total // 60
        week_m = week_total % 60
        week_goal_h = self.config.get('weekly_goal_hours', 10)
        week_pct = (week_total / (week_goal_h * 60)) * 100 if week_goal_h > 0 else 0

        month_h = month_total // 60
        month_m = month_total % 60
        month_goal_h = self.config.get('monthly_goal_hours', 40)
        month_pct = (month_total / (month_goal_h * 60)) * 100 if month_goal_h > 0 else 0

        summary = f"""
        📊 WEEK (Sun–Sat): {week_h}h {week_m}m  |  {week['sessions']} sessions  |  {week_pct:.1f}% of {week_goal_h}h goal
        📆 MONTH: {month_h}h {month_m}m  |  {month['sessions']} sessions  |  {month_pct:.1f}% of {month_goal_h}h goal
        """
        ttk.Label(tab_week, text=summary, font=("Helvetica", 10), justify=tk.LEFT).pack(anchor=tk.W, padx=20, pady=10)

        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text="📈 30-Day Trend")
        if dates:
            fig1, ax1 = plt.subplots(figsize=(10, 4))
            figures.append(fig1)
            ax1.bar(dates, minutes, color='#4CAF50')
            ax1.set_title('Daily Study Time (Last 30 Days)')
            ax1.set_ylabel('Minutes Studied')
            ax1.set_xlabel('Date')
            plt.xticks(rotation=45)
            canvas1 = FigureCanvasTkAgg(fig1, master=tab2)
            canvas1.draw()
            canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            ttk.Label(tab2, text="No data available for the last 30 days.").pack(pady=50)

        # ---- Monthly Breakdown tab ----
        tab_monthly = ttk.Frame(notebook)
        notebook.add(tab_monthly, text="📆 Monthly Breakdown")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                DATE_FORMAT(timestamp, '%Y-%m') AS month,
                SUM(duration_min) AS total_min,
                COUNT(*) AS sessions,
                COUNT(DISTINCT DATE(timestamp)) AS days_active
            FROM pomodoro_log
            WHERE phase = 'work'
            GROUP BY month
            ORDER BY month
        """)
        monthly_data = cursor.fetchall()
        cursor.close()
        conn.close()

        if monthly_data and any(row['total_min'] > 0 for row in monthly_data):
            # Prepare data for bar chart
            months = [row['month'] for row in monthly_data]
            total_hours = [row['total_min'] / 60 for row in monthly_data]

            fig_monthly, ax_monthly = plt.subplots(figsize=(10, 4))
            figures.append(fig_monthly)
            ax_monthly.bar(months, total_hours, color='#FFA500')
            ax_monthly.set_title('Total Study Time per Month')
            ax_monthly.set_ylabel('Hours')
            ax_monthly.set_xlabel('Month')
            plt.xticks(rotation=45)

            canvas_monthly = FigureCanvasTkAgg(fig_monthly, master=tab_monthly)
            canvas_monthly.draw()
            canvas_monthly.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # Summary table (text)
            summary_text = "📊 Monthly Summary:\n"
            for row in monthly_data:
                hours = row['total_min'] // 60
                mins = row['total_min'] % 60
                avg_per_day = row['total_min'] / row['days_active'] if row['days_active'] else 0
                summary_text += f"  {row['month']}: {hours}h {mins}m  |  {row['sessions']} sessions  |  {row['days_active']} days  |  avg {avg_per_day:.0f} min/day\n"
            ttk.Label(tab_monthly, text=summary_text, font=("Helvetica", 10), justify=tk.LEFT).pack(anchor=tk.W, padx=20, pady=10)
        else:
            ttk.Label(tab_monthly, text="No monthly data available yet.").pack(pady=50)

        tab3 = ttk.Frame(notebook)
        notebook.add(tab3, text="🧠 Subject Breakdown")
        if subjects:
            fig2, ax2 = plt.subplots(figsize=(9, 5.5))
            figures.append(fig2)
            _render_pie_chart(ax2, subject_mins, subjects,
                              title='Total Study Time by Subject')
            fig2.tight_layout()
            canvas2 = FigureCanvasTkAgg(fig2, master=tab3)
            canvas2.draw()
            canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            ttk.Label(tab3, text="No subject data available.").pack(pady=50)

        # ---- Session Type Distribution (new) ----
        tab_type = ttk.Frame(notebook)
        notebook.add(tab_type, text="📊 Session Types")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                session_type,
                SUM(duration_min) AS total_min
            FROM pomodoro_log
            WHERE phase = 'work'
            GROUP BY session_type
            ORDER BY total_min DESC
        """)
        type_data = cursor.fetchall()
        cursor.close()
        conn.close()

        if type_data:
            # Ensure every known session type appears, even with 0 minutes
            known_types = ["study", "revision", "pretest", "exam", "quiz"]
            got = {row['session_type'] for row in type_data}
            padded = list(type_data)
            for t in known_types:
                if t not in got:
                    padded.append({'session_type': t, 'total_min': 0})
            types = [(row['session_type'] or 'Unspecified') for row in padded]
            mins  = [float(row['total_min'] or 0) for row in padded]

            if mins:
                fig_type, ax_type = plt.subplots(figsize=(9, 5.5))
                figures.append(fig_type)
                _render_pie_chart(ax_type, mins, types,
                                  title='Total Study Time by Session Type')
                fig_type.tight_layout()
                canvas_type = FigureCanvasTkAgg(fig_type, master=tab_type)
                canvas_type.draw()
                canvas_type.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            else:
                ttk.Label(tab_type, text="No session type data available.").pack(pady=50)
        else:
            ttk.Label(tab_type, text="No session type data available.").pack(pady=50)

        tab4 = ttk.Frame(notebook)
        notebook.add(tab4, text="📋 Top Tasks")
        if tasks:
            fig3, ax3 = plt.subplots(figsize=(8, 4))
            figures.append(fig3)
            ax3.barh(tasks, task_mins, color='#2196F3')
            ax3.set_title('Top 5 Tasks (Time Spent)')
            ax3.set_xlabel('Minutes')
            canvas3 = FigureCanvasTkAgg(fig3, master=tab4)
            canvas3.draw()
            canvas3.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            ttk.Label(tab4, text="No task data available.").pack(pady=50)

        tab5 = ttk.Frame(notebook)
        notebook.add(tab5, text="⏰ Peak Hours")
        if hour_labels:
            fig4, ax4 = plt.subplots(figsize=(10, 4))
            figures.append(fig4)
            ax4.bar(hour_labels, hourly_sessions, color='#FF9800')
            ax4.set_title('Pomodoro Sessions by Hour of Day')
            ax4.set_ylabel('Number of Sessions')
            ax4.set_xlabel('Hour')
            plt.xticks(rotation=45)
            canvas4 = FigureCanvasTkAgg(fig4, master=tab5)
            canvas4.draw()
            canvas4.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            ttk.Label(tab5, text="No hourly data available.").pack(pady=50)

        tab6 = ttk.Frame(notebook)
        notebook.add(tab6, text="💡 Insights")

        insights = "📌 **DYNAMIC INSIGHTS BASED ON YOUR DATA**\n\n"
        if hourly_sessions and hour_labels:
            max_idx = int(hourly_sessions.index(max(hourly_sessions)))
            best_hour = hour_labels[max_idx]
            insights += f"🚀 Your peak productivity time is around **{best_hour}**.\n"
            insights += f"   Schedule your hardest subjects during this hour!\n\n"

        if subjects and subject_mins:
            top_subj = subjects[0]
            pct = (subject_mins[0] / sum(subject_mins)) * 100
            insights += f"📚 You spend {pct:.0f}% of your time on **{top_subj}**.\n"
            if pct < 50:
                insights += f"   You have a great balanced approach! Keep exploring other subjects.\n\n"
            else:
                insights += f"   Consider diversifying slightly if other subjects need attention.\n\n"

        if totals and totals['total_sessions'] > 20:
            avg = totals['total_minutes'] / totals['total_sessions']
            if avg > 25:
                insights += f"💪 Your average session is {avg:.0f} min. Excellent deep work!"
            else:
                insights += f"⏳ Your average session is {avg:.0f} min. Try extending them to 25-30 min for better flow."

        if streak >= 5:
            insights += f"\n🔥 **You are on a {streak}-day streak!** This is your prime time to build momentum. Don't break the chain!"
        elif streak == 0:
            insights += f"\n🔄 Start a new streak today! Just 1 Pomodoro is enough to get back on track."

        ttk.Label(tab6, text=insights, font=("Helvetica", 11), justify=tk.LEFT, wraplength=800).pack(anchor=tk.W, padx=20, pady=20)

    # ---------- ON CLOSE (with error handling) ----------
    def on_close(self):
        # 1. Stop the timer immediately
        self.timer_running = False
        self.paused = False

        # 2. Cancel the timer's after callback
        if hasattr(self, '_timer_after_id') and self._timer_after_id:
            try:
                self.root.after_cancel(self._timer_after_id)
            except Exception:
                pass
            self._timer_after_id = None

        # 3. Cancel the state‑save after callback
        if hasattr(self, '_after_id') and self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

        # 3b. Cancel the day-rollover after callback
        if getattr(self, '_rollover_after_id', None):
            try:
                self.root.after_cancel(self._rollover_after_id)
            except Exception:
                pass
            self._rollover_after_id = None

        # 4. Save state (if remaining time > 0)
        try:
            if self.remaining_seconds > 0:
                self.save_state()
            else:
                self.clear_state()
        except Exception as e:
            print(f"[Pomodoro] State save error: {e}")

        # 5. Save settings and tasks
        try:
            self.save_config(self.config)
        except Exception as e:
            print(f"[Pomodoro] Config save error: {e}")

        try:
            self.save_tasks(self.tasks)
        except Exception as e:
            print(f"[Pomodoro] Tasks save error: {e}")

        # 6. Destroy the window
        self.root.destroy()

    def run(self):
        self.root.mainloop()

# ---------- ENTRY POINT ----------
def main():
    root = tk.Tk()
    app = PomodoroApp(root)
    app.run()

if __name__ == "__main__":
    main()
