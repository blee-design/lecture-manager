# File: pomodoro.py

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime, timedelta
from .db import get_connection

class PomodoroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pomodoro Study Timer")
        self.root.geometry("780x700")
        self.root.minsize(600, 500)

        self.config = self.load_config()
        self.tasks = self.load_tasks()
        self.log = self.load_log()
        self.today_count = self.count_today_pomodoros()

        self.remaining_seconds = 0
        self.timer_running = False
        self.paused = False
        self.current_phase = "work"
        self.cycles_completed = 0

        self.sound_func = self._beep

        self.build_scrollable_ui()

        # ---- Restore saved state if any ----
        self.restore_state_if_any()

        self.update_display()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # ---- Periodic state save (every 5 seconds) ----
        self.schedule_state_save()

    # ---------- Scrollable UI with full mouse‑wheel support ----------
    def build_scrollable_ui(self):
        self.canvas = tk.Canvas(self.root, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.main_frame = ttk.Frame(self.canvas, padding="10")
        self.canvas.create_window((0, 0), window=self.main_frame, anchor=tk.NW)

        def configure_canvas(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.main_frame.bind("<Configure>", configure_canvas)

        def on_mousewheel(event):
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
            elif event.delta:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.root.bind("<MouseWheel>", on_mousewheel)
        self.root.bind("<Button-4>", on_mousewheel)
        self.root.bind("<Button-5>", on_mousewheel)

        self.build_ui(self.main_frame)

    def build_ui(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        timer_frame = ttk.LabelFrame(parent, text="Timer", padding="10")
        timer_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        self.time_label = ttk.Label(timer_frame, font=("Helvetica", 48), text="25:00")
        self.time_label.grid(row=0, column=0, columnspan=3, pady=10)

        self.phase_label = ttk.Label(timer_frame, font=("Helvetica", 14), text="Work")
        self.phase_label.grid(row=1, column=0, columnspan=3, pady=5)

        self.start_btn = ttk.Button(timer_frame, text="Start", command=self.start_timer)
        self.start_btn.grid(row=2, column=0, padx=5, pady=5)
        self.pause_btn = ttk.Button(timer_frame, text="Pause", command=self.pause_timer, state=tk.DISABLED)
        self.pause_btn.grid(row=2, column=1, padx=5, pady=5)
        self.reset_btn = ttk.Button(timer_frame, text="Reset", command=self.reset_timer)
        self.reset_btn.grid(row=2, column=2, padx=5, pady=5)

        progress_frame = ttk.Frame(timer_frame)
        progress_frame.grid(row=3, column=0, columnspan=3, pady=5, sticky=tk.W)
        self.progress_label = ttk.Label(progress_frame, text="Today: 0 Pomodoros")
        self.progress_label.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(progress_frame, text="📊 Today's Summary", command=self.show_today_summary).pack(side=tk.LEFT)

        settings_frame = ttk.LabelFrame(parent, text="Settings", padding="10")
        settings_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        ttk.Label(settings_frame, text="Work (min):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.work_var = tk.StringVar(value=str(self.config["work_min"]))
        ttk.Entry(settings_frame, textvariable=self.work_var, width=6).grid(row=0, column=1, sticky=tk.W, pady=2)

        ttk.Label(settings_frame, text="Short Break (min):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.short_var = tk.StringVar(value=str(self.config["short_break_min"]))
        ttk.Entry(settings_frame, textvariable=self.short_var, width=6).grid(row=1, column=1, sticky=tk.W, pady=2)

        ttk.Label(settings_frame, text="Long Break (min):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.long_var = tk.StringVar(value=str(self.config["long_break_min"]))
        ttk.Entry(settings_frame, textvariable=self.long_var, width=6).grid(row=2, column=1, sticky=tk.W, pady=2)

        ttk.Label(settings_frame, text="Cycles before long:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.cycles_var = tk.StringVar(value=str(self.config["cycles_before_long"]))
        ttk.Entry(settings_frame, textvariable=self.cycles_var, width=6).grid(row=3, column=1, sticky=tk.W, pady=2)

        ttk.Label(settings_frame, text="Daily goal (pomodoros):").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.goal_var = tk.StringVar(value=str(self.config["daily_goal"]))
        ttk.Entry(settings_frame, textvariable=self.goal_var, width=6).grid(row=4, column=1, sticky=tk.W, pady=2)

        ttk.Button(settings_frame, text="Save Settings", command=self.save_settings).grid(row=5, column=0, columnspan=2, pady=10)

        subject_frame = ttk.LabelFrame(parent, text="Subject / Topic", padding="5")
        subject_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.subject_entry = ttk.Entry(subject_frame)
        self.subject_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5)
        subject_frame.columnconfigure(0, weight=1)

        notes_frame = ttk.LabelFrame(parent, text="Notes for this session", padding="10")
        notes_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.notes_text = scrolledtext.ScrolledText(notes_frame, height=6, wrap=tk.WORD)
        self.notes_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        notes_frame.columnconfigure(0, weight=1)
        notes_frame.rowconfigure(0, weight=1)

        log_frame = ttk.LabelFrame(parent, text="Study Log", padding="10")
        log_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        tasks_frame = ttk.LabelFrame(parent, text="Task List (To-Do)", padding="10")
        tasks_frame.grid(row=3, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        task_entry_frame = ttk.Frame(tasks_frame)
        task_entry_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        self.task_entry = ttk.Entry(task_entry_frame)
        self.task_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0,5))
        ttk.Button(task_entry_frame, text="Add", command=self.add_task).grid(row=0, column=1)
        task_entry_frame.columnconfigure(0, weight=1)

        listbox_frame = ttk.Frame(tasks_frame)
        listbox_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        self.task_listbox = tk.Listbox(listbox_frame, height=6)
        self.task_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.task_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.task_listbox.config(yscrollcommand=scrollbar.set)

        ttk.Button(tasks_frame, text="Remove Selected", command=self.remove_task).grid(row=2, column=0, pady=5)

        tasks_frame.columnconfigure(0, weight=1)
        tasks_frame.rowconfigure(1, weight=1)

        self.refresh_task_list()
        self.refresh_log()
        self.update_progress()

    # ---------- State persistence ----------
    def save_state(self):
        """Save current session state to DB."""
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
        except Exception as e:
            # Silently ignore DB errors during save
            pass

    def clear_state(self):
        """Clear saved state (set remaining_seconds to 0)."""
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
        """Load saved state from DB. Returns dict or None."""
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM pomodoro_state WHERE id = 1")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row and row['remaining_seconds'] > 0:
                # Check if state is recent (within 2 hours)
                updated = row['updated_at']
                if updated and (datetime.now() - updated).total_seconds() < 7200:
                    return row
            return None
        except Exception:
            return None

    def restore_state_if_any(self):
        """Check for saved state and ask to resume."""
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
            # Restore all fields
            self.current_phase = state['current_phase']
            self.remaining_seconds = state['remaining_seconds']
            self.cycles_completed = state['cycles_completed']
            self.subject_entry.delete(0, tk.END)
            self.subject_entry.insert(0, state.get('subject', ''))
            self.notes_text.delete("1.0", tk.END)
            self.notes_text.insert("1.0", state.get('notes', ''))
            self.phase_label.config(text=self.current_phase.capitalize())
            self.update_display()

            # Set as paused so Start resumes from saved time
            self.paused = True
            self.timer_running = False
            self.start_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.NORMAL, text="Resume")

            messagebox.showinfo("Restored", "Session restored. Click Start to resume.")
        else:
            # Discard saved state
            self.clear_state()

    def schedule_state_save(self):
        """Save state every 5 seconds if timer is running or paused."""
        if self.timer_running or self.paused:
            self.save_state()
        self.root.after(5000, self.schedule_state_save)

    # ---------- Database helpers (unchanged) ----------
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

    def load_tasks(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT task_text FROM pomodoro_tasks ORDER BY created_at")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[0] for row in rows]

    def save_tasks(self, tasks):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pomodoro_tasks")
        for task in tasks:
            cursor.execute("INSERT INTO pomodoro_tasks (task_text) VALUES (%s)", (task,))
        conn.commit()
        cursor.close()
        conn.close()

    def load_log(self):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT timestamp, phase, duration_min, subject, notes
            FROM pomodoro_log
            ORDER BY id DESC
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
                "notes": row["notes"]
            })
        return log

    def add_log_entry(self, entry):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pomodoro_log (timestamp, phase, duration_min, subject, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, (entry["timestamp"], entry["phase"], entry["duration_min"],
              entry.get("subject"), entry.get("notes")))
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

    # ---------- Today's summary ----------
    def get_today_summary(self):
        today = datetime.now().date().isoformat()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(subject, 'Uncategorized') AS subject,
                SUM(duration_min) AS total_minutes,
                COUNT(*) AS sessions
            FROM pomodoro_log
            WHERE DATE(timestamp) = %s AND phase = 'work'
            GROUP BY subject
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
        summary_win.geometry("450x300")
        summary_win.resizable(False, False)

        ttk.Label(summary_win, text=f"Summary for {datetime.now().strftime('%Y-%m-%d')}",
                  font=("Helvetica", 14, "bold")).pack(pady=10)

        frame = ttk.Frame(summary_win, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        columns = ("Subject", "Time (min)", "Sessions")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        tree.heading("Subject", text="Subject")
        tree.heading("Time (min)", text="Time (min)")
        tree.heading("Sessions", text="Sessions")
        tree.column("Subject", width=200)
        tree.column("Time (min)", width=100, anchor=tk.CENTER)
        tree.column("Sessions", width=80, anchor=tk.CENTER)

        total_time = 0
        total_sessions = 0
        for subject, minutes, sessions in rows:
            tree.insert("", tk.END, values=(subject, minutes, sessions))
            total_time += minutes
            total_sessions += sessions

        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        total_hours = total_time // 60
        total_mins = total_time % 60
        footer = f"Total: {total_hours}h {total_mins}m  |  Sessions: {total_sessions}"
        ttk.Label(summary_win, text=footer, font=("Helvetica", 10, "bold")).pack(pady=10)

        ttk.Button(summary_win, text="Close", command=summary_win.destroy).pack(pady=5)

    # ---------- Timer logic (with state updates) ----------
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
        # Ask for confirmation before resetting
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

        if self.current_phase == "work":
            self.cycles_completed += 1
            self.today_count += 1
            self.log_session()
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
        # Clear state after a work session completes (so we don't restore old state)
        if self.current_phase == "work":
            self.clear_state()
        else:
            # For break, keep state so we can resume break if closed
            self.save_state()

        messagebox.showinfo("Pomodoro", f"{self.current_phase.capitalize()} phase completed!")

    def update_display(self):
        mins = self.remaining_seconds // 60
        secs = self.remaining_seconds % 60
        self.time_label.config(text=f"{mins:02d}:{secs:02d}")

    def log_session(self):
        subject = self.subject_entry.get().strip()
        notes = self.notes_text.get("1.0", tk.END).strip()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "phase": "work",
            "duration_min": self.config["work_min"],
            "subject": subject,
            "notes": notes
        }
        self.add_log_entry(entry)

    def update_progress(self):
        goal = self.config["daily_goal"]
        self.progress_label.config(text=f"Today: {self.today_count} / {goal} Pomodoros")

    # ---------- Settings ----------
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
            messagebox.showinfo("Settings", "Settings saved successfully!")
        except:
            messagebox.showerror("Error", "Please enter valid positive integers.")

    # ---------- Task list ----------
    def add_task(self):
        task = self.task_entry.get().strip()
        if task:
            self.tasks.append(task)
            self.save_tasks(self.tasks)
            self.refresh_task_list()
            self.task_entry.delete(0, tk.END)

    def remove_task(self):
        selected = self.task_listbox.curselection()
        if selected:
            index = selected[0]
            del self.tasks[index]
            self.save_tasks(self.tasks)
            self.refresh_task_list()

    def refresh_task_list(self):
        self.task_listbox.delete(0, tk.END)
        for task in self.tasks:
            self.task_listbox.insert(tk.END, task)

    def refresh_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        for entry in reversed(self.log[-50:]):
            line = f"{entry['timestamp']} - {entry['duration_min']} min"
            if entry.get('subject'):
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

    def on_close(self):
        # Save current state before closing (if timer is running or paused)
        if self.timer_running or self.paused:
            self.save_state()
        else:
            self.clear_state()
        self.save_config(self.config)
        self.save_tasks(self.tasks)
        self.root.destroy()

    def run(self):
        self.root.mainloop()

def main():
    root = tk.Tk()
    app = PomodoroApp(root)
    app.run()

if __name__ == "__main__":
    main()
