# pomodoro.py – Enhanced UI with modern design (fully working)

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta
import calendar
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
from datetime import datetime
from .db import get_connection

# ====================== STYLE CONFIGURATION ======================
def configure_styles():
    style = ttk.Style()
    style.theme_use('clam')
    bg_dark = "#1e2a3a"
    bg_medium = "#2c3e50"
    bg_light = "#34495e"
    accent = "#3498db"
    accent_light = "#5dade2"
    fg = "#ecf0f1"
    style.configure('.', background=bg_medium, foreground=fg, fieldbackground=bg_light)
    style.configure('TFrame', background=bg_medium)
    style.configure('TLabel', background=bg_medium, foreground=fg)
    style.configure('TLabelframe', background=bg_medium, foreground=fg, bordercolor=accent)
    style.configure('TLabelframe.Label', background=bg_medium, foreground=fg)
    style.configure('TButton', background=accent, foreground='white', bordercolor=accent, focuscolor='none', borderwidth=0)
    style.map('TButton', background=[('active', accent_light)])
    style.configure('TEntry', fieldbackground=bg_light, foreground=fg, insertcolor=fg)
    style.theme_use('clam')
    style.configure('TCombobox',
                    fieldbackground='#34495e',   # dark entry background
                    foreground='white',          # white text
                    background='#2c3e50',        # dropdown background
                    arrowcolor='white')          # arrow visible
    style.map('TCombobox',
            fieldbackground=[('readonly', '#34495e')])
    # Fix dropdown listbox (popup)
    style.configure('TCombobox.listbox',
                    background='#2c3e50',
                    foreground='white',
                    selectbackground='#3498db',
                    selectforeground='white')
    style.configure('TCombobox.listbox', background='#2c3e50', foreground='white', selectbackground='#3498db')
    style.configure('TProgressbar', background=accent, troughcolor=bg_light, bordercolor=bg_light)
    style.configure('Vertical.TScrollbar', background=bg_light, troughcolor=bg_medium)

class PomodoroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🍅 Pomodoro Study Timer")
        self.root.geometry("1000x780")
        self.root.minsize(850, 680)
        self.root.configure(bg="#1e2a3a")
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
        self.cycles_completed = 0
        self._after_id = None
        self.task_var = tk.StringVar()

        self.sound_func = self._beep

        self.build_ui()
        self.restore_state_if_any()
        self.update_display()
        self.refresh_task_list()
        self.refresh_log()
        self.update_progress()
        self.update_task_combo()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.schedule_state_save()

    # ---------- UI Construction ----------
    def build_ui(self):
        main = ttk.Frame(self.root, padding="10")
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        # ----- LEFT COLUMN -----
        left = ttk.Frame(main, padding="5")
        left.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        left.rowconfigure(0, weight=1)   # timer
        left.rowconfigure(1, weight=0)   # subject
        left.rowconfigure(2, weight=0)   # task combo
        left.rowconfigure(3, weight=2)   # notes
        left.columnconfigure(0, weight=1)

        # -- Timer Frame --
        timer_frame = ttk.LabelFrame(left, text="⏱️ Timer", padding="15")
        timer_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        timer_frame.columnconfigure(0, weight=1)

        self.time_label = ttk.Label(timer_frame, font=("Helvetica", 56, "bold"), foreground="#3498db")
        self.time_label.grid(row=0, column=0, pady=10)

        self.progress_bar = ttk.Progressbar(timer_frame, orient=tk.HORIZONTAL, length=300, mode='determinate')
        self.progress_bar.grid(row=1, column=0, pady=5, sticky=tk.W+tk.E)

        self.phase_label = ttk.Label(timer_frame, font=("Helvetica", 14), foreground="#ecf0f1")
        self.phase_label.grid(row=2, column=0, pady=5)

        ctrl_frame = ttk.Frame(timer_frame)
        ctrl_frame.grid(row=3, column=0, pady=10)
        self.start_btn = ttk.Button(ctrl_frame, text="▶ Start", command=self.start_timer)
        self.start_btn.grid(row=0, column=0, padx=5)
        self.pause_btn = ttk.Button(ctrl_frame, text="⏸ Pause", command=self.pause_timer, state=tk.DISABLED)
        self.pause_btn.grid(row=0, column=1, padx=5)
        self.reset_btn = ttk.Button(ctrl_frame, text="⟳ Reset", command=self.reset_timer)
        self.reset_btn.grid(row=0, column=2, padx=5)

        progress_frame = ttk.Frame(timer_frame)
        progress_frame.grid(row=4, column=0, pady=5, sticky=tk.W+tk.E)
        self.progress_label = ttk.Label(progress_frame, text="Today: 0 / 12 Pomodoros")
        self.progress_label.pack(side=tk.LEFT, padx=5)
        self.daily_bar = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, length=200, mode='determinate', maximum=self.config["daily_goal"])
        self.daily_bar.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        ttk.Button(progress_frame, text="📊 Summary", command=self.show_today_summary).pack(side=tk.LEFT, padx=5)
        ttk.Button(progress_frame, text="📈 Analytics", command=self.show_overall_stats).pack(side=tk.LEFT, padx=5)

        # -- Subject --
        subject_frame = ttk.LabelFrame(left, text="📌 Subject", padding="10")
        subject_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        self.subject_entry = ttk.Entry(subject_frame, font=("Helvetica", 11))
        self.subject_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        subject_frame.columnconfigure(0, weight=1)

        # -- Task Selection (combo) --
        task_select_frame = ttk.LabelFrame(left, text="🎯 Current Task", padding="10")
        task_select_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        task_select_frame.columnconfigure(0, weight=1)

        self.task_combo = ttk.Combobox(task_select_frame, textvariable=self.task_var, state="readonly", width=50)
        # Force dropdown listbox colors
        self.root.option_add('*TCombobox*Listbox.background', '#2c3e50')
        self.root.option_add('*TCombobox*Listbox.foreground', 'white')
        self.task_combo['foreground'] = 'white'
        self.task_combo['background'] = '#34495e'
        self.task_combo.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)


        # -- Notes --
        notes_frame = ttk.LabelFrame(left, text="📝 Notes for this session", padding="10")
        notes_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        notes_frame.columnconfigure(0, weight=1)
        notes_frame.rowconfigure(0, weight=1)
        self.notes_text = scrolledtext.ScrolledText(notes_frame, height=4, wrap=tk.WORD, bg="#2c3e50", fg="#ecf0f1", insertbackground="#ecf0f1")
        self.notes_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # ----- RIGHT COLUMN -----
        right = ttk.Frame(main, padding="5")
        right.grid(row=0, column=1, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        # -- Settings --
        settings_frame = ttk.LabelFrame(right, text="⚙️ Settings", padding="10")
        settings_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        settings_frame.columnconfigure(0, weight=1)

        row = 0
        ttk.Label(settings_frame, text="Work (min):").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.work_var = tk.StringVar(value=str(self.config["work_min"]))
        ttk.Entry(settings_frame, textvariable=self.work_var, width=6).grid(row=row, column=1, sticky=tk.W, pady=2)
        row += 1
        ttk.Label(settings_frame, text="Short break (min):").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.short_var = tk.StringVar(value=str(self.config["short_break_min"]))
        ttk.Entry(settings_frame, textvariable=self.short_var, width=6).grid(row=row, column=1, sticky=tk.W, pady=2)
        row += 1
        ttk.Label(settings_frame, text="Long break (min):").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.long_var = tk.StringVar(value=str(self.config["long_break_min"]))
        ttk.Entry(settings_frame, textvariable=self.long_var, width=6).grid(row=row, column=1, sticky=tk.W, pady=2)
        row += 1
        ttk.Label(settings_frame, text="Cycles before long:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.cycles_var = tk.StringVar(value=str(self.config["cycles_before_long"]))
        ttk.Entry(settings_frame, textvariable=self.cycles_var, width=6).grid(row=row, column=1, sticky=tk.W, pady=2)
        row += 1
        ttk.Label(settings_frame, text="Daily goal:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.goal_var = tk.StringVar(value=str(self.config["daily_goal"]))
        ttk.Entry(settings_frame, textvariable=self.goal_var, width=6).grid(row=row, column=1, sticky=tk.W, pady=2)
        row += 1
        ttk.Button(settings_frame, text="💾 Save Settings", command=self.save_settings).grid(row=row, column=0, columnspan=2, pady=10)

        # -- Task List --
        tasks_frame = ttk.LabelFrame(right, text="📋 Task List", padding="10")
        tasks_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        tasks_frame.columnconfigure(0, weight=1)
        tasks_frame.rowconfigure(1, weight=1)

        add_frame = ttk.Frame(tasks_frame)
        add_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        self.task_entry = ttk.Entry(add_frame, width=20)
        self.task_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ttk.Button(add_frame, text="➕ Add", command=self.add_task).pack(side=tk.LEFT, padx=2)
        ttk.Button(add_frame, text="📋 Bulk", command=self.bulk_add_tasks).pack(side=tk.LEFT, padx=2)

        priority_frame = ttk.Frame(tasks_frame)
        priority_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=2)
        ttk.Label(priority_frame, text="Priority:").pack(side=tk.LEFT, padx=(0,5))
        self.priority_var = tk.StringVar(value="3")
        ttk.Spinbox(priority_frame, from_=0, to=9, textvariable=self.priority_var, width=5).pack(side=tk.LEFT, padx=(0,10))
        ttk.Label(priority_frame, text="(1=highest, 9=high, 0=lowest)", font=("Helvetica", 8)).pack(side=tk.LEFT)

        listbox_frame = ttk.Frame(tasks_frame)
        listbox_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        listbox_frame.columnconfigure(0, weight=1)
        listbox_frame.rowconfigure(0, weight=1)

        self.task_listbox = tk.Listbox(listbox_frame, height=8, bg="#2c3e50", fg="#ecf0f1", selectbackground="#3498db", selectforeground="white")
        self.task_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar2 = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.task_listbox.yview)
        scrollbar2.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.task_listbox.config(yscrollcommand=scrollbar2.set)
        self.task_listbox.bind('<<ListboxSelect>>', self.on_task_select)

        task_btn_frame = ttk.Frame(tasks_frame)
        task_btn_frame.grid(row=3, column=0, pady=5, sticky=tk.W)
        ttk.Button(task_btn_frame, text="🗑 Remove", command=self.remove_task).pack(side=tk.LEFT, padx=2)
        ttk.Button(task_btn_frame, text="✅ Toggle Done", command=self.toggle_complete).pack(side=tk.LEFT, padx=2)
        ttk.Button(task_btn_frame, text="🔢 Set Priority", command=self.set_priority).pack(side=tk.LEFT, padx=2)
        ttk.Button(task_btn_frame, text="🗑 Clear All", command=self.clear_all_tasks).pack(side=tk.LEFT, padx=2)
        self.show_completed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(task_btn_frame, text="Show completed", variable=self.show_completed_var, command=self.refresh_task_list).pack(side=tk.LEFT, padx=10)

        # -- Study Log --
        log_frame = ttk.LabelFrame(right, text="📜 Study Log", padding="10")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED, bg="#2c3e50", fg="#ecf0f1")
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    # ---------- TASK MANAGEMENT (unchanged from original) ----------
    def load_tasks(self):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, task_text, priority, completed FROM pomodoro_tasks ORDER BY "
                       "CASE priority WHEN 1 THEN 0 WHEN 0 THEN 2 ELSE 1 END, priority")
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
        confirm = messagebox.askyesno("Remove Task", "Delete this task?")
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

    def on_task_select(self, event):
        selection = self.task_listbox.curselection()
        if selection:
            index = selection[0]
            task_id = self.task_listbox_task_ids[index]
            task = next((t for t in self.tasks if t['id'] == task_id), None)
            if task and not task['completed']:
                label = f"[P{task['priority']}] {task['task_text']}"
                self.task_var.set(label)

    def show_context_menu(self, event):
        index = self.task_listbox.nearest(event.y)
        if index != -1:
            self.task_listbox.selection_clear(0, tk.END)
            self.task_listbox.selection_set(index)
            self.task_listbox.activate(index)
            self.task_menu.post(event.x_root, event.y_root)

    def get_current_task_id(self):
        label = self.task_var.get()
        if label and label in self.combo_label_to_id:
            return self.combo_label_to_id[label]
        return None

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
            }
        return {"work_min":25, "short_break_min":5, "long_break_min":15,
                "cycles_before_long":4, "daily_goal":12}

    def save_config(self, config):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE pomodoro_settings
            SET work_min=%s, short_break_min=%s, long_break_min=%s,
                cycles_before_long=%s, daily_goal=%s
            WHERE id=1
        """, (config["work_min"], config["short_break_min"],
              config["long_break_min"], config["cycles_before_long"],
              config["daily_goal"]))
        conn.commit()
        cursor.close()
        conn.close()

    def load_log(self):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT l.id, l.timestamp, l.phase, l.duration_min, l.subject, l.notes, l.task_id,
                   t.task_text
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
                "timestamp": row["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                "phase": row["phase"],
                "duration_min": row["duration_min"],
                "subject": row.get("subject", ""),
                "notes": row["notes"],
                "task_id": row.get("task_id"),
                "task_name": row.get("task_text", "") if row.get("task_text") else None,
            })
        return log

    def add_log_entry(self, entry):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pomodoro_log (timestamp, phase, duration_min, subject, notes, task_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (entry["timestamp"], entry["phase"], entry["duration_min"],
              entry.get("subject"), entry.get("notes"), entry.get("task_id")))
        conn.commit()
        cursor.close()
        conn.close()

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

    # ---------- TODAY SUMMARY ----------
    def get_today_summary(self):
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

    def show_today_summary(self):
        rows = self.get_today_summary()
        if not rows:
            messagebox.showinfo("Today's Summary", "No study sessions logged today yet.")
            return

        summary_win = tk.Toplevel(self.root)
        summary_win.title("Today's Study Summary")
        summary_win.geometry("500x350")
        summary_win.resizable(False, False)

        ttk.Label(summary_win, text=f"Summary for {datetime.now().strftime('%Y-%m-%d')}",
                  font=("Helvetica", 14, "bold")).pack(pady=10)

        frame = ttk.Frame(summary_win, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        columns = ("Task", "Time (min)", "Sessions")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        tree.heading("Task", text="Task")
        tree.heading("Time (min)", text="Time (min)")
        tree.heading("Sessions", text="Sessions")
        tree.column("Task", width=250)
        tree.column("Time (min)", width=100, anchor=tk.CENTER)
        tree.column("Sessions", width=80, anchor=tk.CENTER)

        total_time = 0
        total_sessions = 0
        for task, minutes, sessions in rows:
            tree.insert("", tk.END, values=(task, minutes, sessions))
            total_time += minutes
            total_sessions += sessions

        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        total_hours = total_time // 60
        total_mins = total_time % 60
        footer = f"Total: {total_hours}h {total_mins}m  |  Sessions: {total_sessions}"
        ttk.Label(summary_win, text=footer, font=("Helvetica", 10, "bold")).pack(pady=10)

        ttk.Button(summary_win, text="Close", command=summary_win.destroy).pack(pady=5)

    # ---------- TIMER ----------
    def start_timer(self):
        if self.timer_running and not self.paused:
            return
        if self.paused:
            self.paused = False
            self.pause_btn.config(text="Pause")
            self.start_btn.config(state=tk.DISABLED)
            self.timer_running = True
            self.update_timer()
            self.save_state()
            return

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
        if not self.timer_running or self.paused:
            return
        if self.remaining_seconds <= 0:
            self.timer_complete()
            return
        self.remaining_seconds -= 1
        self.update_display()
        self.root.after(1000, self.update_timer)

    def pause_timer(self):
        if self.timer_running and not self.paused:
            self.paused = True
            self.pause_btn.config(text="Resume")
            self.start_btn.config(state=tk.NORMAL)
            self.save_state()
        elif self.paused:
            pass

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
        self.sound_func()

        completed_phase = self.current_phase

        if completed_phase == "work":
            self.cycles_completed += 1
            self.today_count += 1
            self.log_session()
            self.log = self.load_log()
            self.refresh_log()
            self.update_progress()

            if self.cycles_completed % self.config["cycles_before_long"] == 0:
                self.current_phase = "long_break"
                self.phase_label.config(text="Long Break")
                self.remaining_seconds = self.config["long_break_min"] * 60
            else:
                self.current_phase = "short_break"
                self.phase_label.config(text="Short Break")
                self.remaining_seconds = self.config["short_break_min"] * 60
        else:
            self.current_phase = "work"
            self.phase_label.config(text="Work")
            self.remaining_seconds = self.config["work_min"] * 60

        self.update_display()
        self.save_state()
        messagebox.showinfo("Pomodoro", f"{completed_phase.capitalize()} phase completed!")

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

    def log_session(self):
        subject = self.subject_entry.get().strip()
        notes = self.notes_text.get("1.0", tk.END).strip()
        task_id = self.get_current_task_id()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "phase": "work",
            "duration_min": self.config["work_min"],
            "subject": subject,
            "notes": notes,
            "task_id": task_id
        }
        self.add_log_entry(entry)

    def update_progress(self):
        goal = self.config["daily_goal"]
        self.progress_label.config(text=f"Today: {self.today_count} / {goal} Pomodoros")
        self.daily_bar['maximum'] = goal
        self.daily_bar['value'] = self.today_count

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
        for entry in reversed(self.log[-50:]):
            line = f"{entry['timestamp']} - {entry['duration_min']} min"
            if entry.get('task_name'):
                line += f" [Task: {entry['task_name']}]"
            elif entry.get('subject'):
                line += f" [{entry['subject']}]"
            self.log_text.insert(tk.END, line + "\n")
            if entry['notes']:
                self.log_text.insert(tk.END, f"  Notes: {entry['notes']}\n")
            self.log_text.insert(tk.END, "-" * 40 + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def _beep(self):
        try:
            import winsound
            winsound.Beep(1000, 500)
        except:
            print('\a')

    # ---------- STATE PERSISTENCE ----------
    def save_state(self):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                REPLACE INTO pomodoro_state
                (id, current_phase, remaining_seconds, notes, subject, cycles_completed, updated_at)
                VALUES (1, %s, %s, %s, %s, %s, NOW())
            """, (
                self.current_phase,
                self.remaining_seconds,
                self.notes_text.get("1.0", tk.END).strip(),
                self.subject_entry.get().strip(),
                self.cycles_completed
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
            self.current_phase = state['current_phase']
            self.remaining_seconds = state['remaining_seconds']
            self.cycles_completed = state['cycles_completed']
            self.subject_entry.delete(0, tk.END)
            self.subject_entry.insert(0, state.get('subject', ''))
            self.notes_text.delete("1.0", tk.END)
            self.notes_text.insert("1.0", state.get('notes', ''))
            self.phase_label.config(text=self.current_phase.capitalize())
            self.update_display()

            self.paused = True
            self.timer_running = False
            self.start_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.NORMAL, text="Resume")

            messagebox.showinfo("Restored", "Session restored. Click Start to resume.")
        else:
            self.clear_state()

    def schedule_state_save(self):
        if self.timer_running or self.paused:
            self.save_state()
        if hasattr(self, 'root') and self.root.winfo_exists():
            self._after_id = self.root.after(5000, self.schedule_state_save)

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
                COALESCE(subject, 'Uncategorized') as subject,
                SUM(duration_min) as total_min,
                COUNT(*) as sessions
            FROM pomodoro_log
            WHERE phase = 'work'
            GROUP BY subject
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
        hours = [f"{row['hour']}:00" for row in hourly_data]
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

        cursor.close()
        conn.close()

        stats_win = tk.Toplevel(self.root)
        stats_win.title("📊 Overall Study Analytics")
        stats_win.geometry("1000x700")

        notebook = ttk.Notebook(stats_win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

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

        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text="📈 30-Day Trend")
        if dates:
            fig1, ax1 = plt.subplots(figsize=(10, 4))
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

        tab3 = ttk.Frame(notebook)
        notebook.add(tab3, text="🧠 Subject Breakdown")
        if subjects:
            fig2, ax2 = plt.subplots(figsize=(6, 6))
            ax2.pie(subject_mins, labels=subjects, autopct='%1.1f%%', startangle=90)
            ax2.axis('equal')
            ax2.set_title('Total Study Time by Subject')
            canvas2 = FigureCanvasTkAgg(fig2, master=tab3)
            canvas2.draw()
            canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            ttk.Label(tab3, text="No subject data available.").pack(pady=50)

        tab4 = ttk.Frame(notebook)
        notebook.add(tab4, text="📋 Top Tasks")
        if tasks:
            fig3, ax3 = plt.subplots(figsize=(8, 4))
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
        if hours:
            fig4, ax4 = plt.subplots(figsize=(10, 4))
            ax4.bar(hours, hourly_sessions, color='#FF9800')
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
        if hourly_sessions:
            max_idx = hourly_sessions.index(max(hourly_sessions))
            best_hour = hours[max_idx]
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
        try:
            if hasattr(self, '_after_id') and self._after_id:
                self.root.after_cancel(self._after_id)
        except Exception:
            pass

        try:
            if self.remaining_seconds > 0:
                self.save_state()
            else:
                self.clear_state()
        except Exception as e:
            print(f"[Pomodoro] State save error: {e}")

        try:
            self.save_config(self.config)
        except Exception as e:
            print(f"[Pomodoro] Config save error: {e}")

        try:
            self.save_tasks(self.tasks)
        except Exception as e:
            print(f"[Pomodoro] Tasks save error: {e}")

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
