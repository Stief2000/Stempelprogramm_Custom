import os
import sqlite3
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timedelta
from tkinter import messagebox, simpledialog, ttk

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from tkcalendar import DateEntry
import win32api


ADMIN_PASSWORD = "AdminBus"
DB_NAME = "time_entries.db"
MECHANIC_CODES = {
    "Daniel": "01",
    "Hubert": "02",
    "Jonas": "03",
    "Alex": "04",
    "Jolly": "05",
}


@dataclass
class Entry:
    id: int
    kodex: str
    mechanic: str
    job_number: str
    start: datetime
    stop: datetime | None = None
    duration: timedelta | None = None


def init_db() -> None:
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kodex TEXT NOT NULL,
                mechanic TEXT NOT NULL,
                job_number TEXT NOT NULL,
                start TEXT NOT NULL,
                stop TEXT,
                duration REAL
            )
            """
        )


def save_start(mechanic: str, job_number: str) -> tuple[int, datetime]:
    start = datetime.now()
    kodex = MECHANIC_CODES.get(mechanic, "")
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO entries(kodex, mechanic, job_number, start) VALUES (?, ?, ?, ?)",
            (kodex, mechanic, job_number, start.isoformat()),
        )
        entry_id = cursor.lastrowid
    return entry_id, start


def save_stop(entry_id: int) -> tuple[datetime, timedelta]:
    stop = datetime.now()
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()
        cursor.execute("SELECT start FROM entries WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Eintrag nicht gefunden")
        start = datetime.fromisoformat(row[0])
        duration = stop - start
        cursor.execute(
            "UPDATE entries SET stop = ?, duration = ? WHERE id = ?",
            (stop.isoformat(), duration.total_seconds(), entry_id),
        )
    return stop, duration


def load_active_entries() -> list[Entry]:
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, kodex, mechanic, job_number, start
            FROM entries
            WHERE stop IS NULL
            ORDER BY start
            """
        )
        rows = cursor.fetchall()
    return [
        Entry(
            id=row[0],
            kodex=row[1],
            mechanic=row[2],
            job_number=row[3],
            start=datetime.fromisoformat(row[4]),
        )
        for row in rows
    ]


def load_history_entries() -> list[Entry]:
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, kodex, mechanic, job_number, start, stop, duration
            FROM entries
            WHERE stop IS NOT NULL
            ORDER BY start
            """
        )
        rows = cursor.fetchall()
    return [
        Entry(
            id=row[0],
            kodex=row[1],
            mechanic=row[2],
            job_number=row[3],
            start=datetime.fromisoformat(row[4]),
            stop=datetime.fromisoformat(row[5]),
            duration=timedelta(seconds=row[6]) if row[6] is not None else None,
        )
        for row in rows
    ]


def format_duration(td: timedelta | None) -> str:
    if td is None:
        return ""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class TimeTrackerApp(tk.Tk):
    BG = "#d8e0e8"
    SURFACE = "#f3f7fb"
    SURFACE_ALT = "#c6d1dc"
    SURFACE_STRONG = "#a7b7c7"
    TEXT = "#1c2733"
    MUTED = "#5d6c7b"
    BORDER = "#8899ab"
    ACCENT = "#2f6ea3"
    ACCENT_DARK = "#24557d"
    ACCENT_SOFT = "#d7e6f3"
    ACTIVE = "#2f7a86"
    ACTIVE_SOFT = "#d9eef1"
    WARNING_SOFT = "#e7eef6"
    PANEL_DARK = "#314252"
    PANEL_DARK_ALT = "#3d5366"
    PANEL_TEXT = "#eef4f9"

    APP_TITLE = "Arbeitszeiterfassung"
    APP_SUBTITLE = "Robuste Erfassung fuer Werkstatt, Montage, Lager und andere betriebliche Bereiche."
    TAB_CAPTURE = "Erfassung"
    TAB_REPORTS = "Auswertung"
    PERSON_LABEL = "Mitarbeiter"
    TASK_LABEL = "Vorgang"
    ACTIVE_AREA_LABEL = "Laufende Erfassungen"
    CODE_LABEL = "Code"

    def __init__(self) -> None:
        super().__init__()
        self.title(self.APP_TITLE)
        self.state("zoomed")
        self.configure(bg=self.BG)

        init_db()

        self.is_admin = False
        self.page_report: tk.Widget | None = None
        self.page_stamp: tk.Widget | None = None

        self.active_entries: dict[str, int] = {}
        self.active_entry_objects: dict[str, Entry] = {}
        self.buttons: dict[str, tk.Button] = {}
        self.mechanic_labels: dict[str, dict[str, tk.Label]] = {}

        self.filter_date = tk.StringVar()
        self.filter_mechanic = tk.StringVar()
        self.filter_job = tk.StringVar()
        self.total_time_var = tk.StringVar(value="")
        self.admin_status_var = tk.StringVar(value="Admin aus")
        self.active_summary_var = tk.StringVar(value="")

        self.last_jobs: dict[str, str] = {}

        self._configure_styles()
        self._prime_cached_state()
        self._build_shell()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("App.TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.SURFACE, relief="flat")
        style.configure("Section.TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI Semibold", 18))
        style.configure(
            "App.TNotebook",
            background=self.BG,
            borderwidth=0,
            tabmargins=(18, 0, 18, 0),
        )
        style.configure(
            "App.TNotebook.Tab",
            padding=(22, 10),
            font=("Bahnschrift SemiBold", 11),
            background=self.SURFACE_ALT,
            foreground=self.TEXT,
            borderwidth=0,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", self.SURFACE), ("active", self.ACCENT_SOFT)],
            foreground=[("selected", self.ACCENT_DARK)],
        )
        style.configure(
            "Accent.TButton",
            font=("Bahnschrift SemiBold", 11),
            padding=(14, 8),
            background=self.ACCENT,
            foreground="white",
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Accent.TButton",
            background=[("pressed", self.ACCENT_DARK), ("active", self.ACCENT_DARK)],
        )
        style.configure(
            "Secondary.TButton",
            font=("Bahnschrift SemiBold", 11),
            padding=(14, 8),
            background=self.SURFACE_ALT,
            foreground=self.TEXT,
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton",
            background=[("pressed", self.SURFACE_STRONG), ("active", self.SURFACE_STRONG)],
        )
        style.configure(
            "Report.Treeview",
            background="white",
            fieldbackground="white",
            foreground=self.TEXT,
            rowheight=34,
            font=("Segoe UI", 11),
            borderwidth=0,
        )
        style.configure(
            "Report.Treeview.Heading",
            background=self.SURFACE_STRONG,
            foreground=self.TEXT,
            font=("Bahnschrift SemiBold", 11),
            relief="flat",
            padding=(8, 8),
        )
        style.map(
            "Report.Treeview",
            background=[("selected", "#c8deef")],
            foreground=[("selected", self.TEXT)],
        )
        style.configure(
            "Filter.TCombobox",
            fieldbackground="white",
            background="white",
            foreground=self.TEXT,
            padding=6,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Filter.TEntry",
            fieldbackground="white",
            foreground=self.TEXT,
            padding=6,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Report.Vertical.TScrollbar",
            background=self.SURFACE_ALT,
            troughcolor=self.BG,
            bordercolor=self.BG,
            arrowcolor=self.TEXT,
        )

    def _build_shell(self) -> None:
        shell = tk.Frame(self, bg=self.BG)
        shell.pack(expand=True, fill="both", padx=18, pady=18)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=self.BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)

        title_block = tk.Frame(header, bg=self.BG)
        title_block.grid(row=0, column=0, sticky="w")
        tk.Label(
            title_block,
            text="BETRIEBSSYSTEM",
            bg=self.PANEL_DARK,
            fg=self.PANEL_TEXT,
            font=("Bahnschrift SemiBold", 9),
            padx=10,
            pady=4,
        ).pack(anchor="w", pady=(0, 8))
        tk.Label(
            title_block,
            text=self.APP_TITLE,
            bg=self.BG,
            fg=self.TEXT,
            font=("Bahnschrift SemiBold", 24),
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text=self.APP_SUBTITLE,
            bg=self.BG,
            fg=self.MUTED,
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(4, 0))

        admin_block = tk.Frame(header, bg=self.BG)
        admin_block.grid(row=0, column=1, sticky="e")
        self.admin_status_label = tk.Label(
            admin_block,
            textvariable=self.admin_status_var,
            bg=self.PANEL_DARK,
            fg=self.PANEL_TEXT,
            font=("Bahnschrift SemiBold", 10),
            padx=12,
            pady=8,
        )
        self.admin_status_label.pack(side="left", padx=(0, 10))
        self.admin_button = ttk.Button(admin_block, text="Admin", style="Accent.TButton", command=self.toggle_admin)
        self.admin_button.pack(side="left")

        self.notebook = ttk.Notebook(shell, style="App.TNotebook")
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self.page_stamp = tk.Frame(self.notebook, bg=self.BG)
        self.page_report = tk.Frame(self.notebook, bg=self.BG)
        self.notebook.add(self.page_stamp, text=self.TAB_CAPTURE)
        self.notebook.add(self.page_report, text=self.TAB_REPORTS)

        self.build_stamp_page(self.page_stamp)
        self.build_report_page(self.page_report)
        self.reset_filters()

    def _prime_cached_state(self) -> None:
        self._refresh_last_jobs()
        self._refresh_active_cache()

    def _refresh_last_jobs(self) -> None:
        self.last_jobs.clear()
        entries = load_history_entries() + load_active_entries()
        entries.sort(key=lambda entry: entry.start)
        for entry in entries:
            self.last_jobs[entry.mechanic] = entry.job_number

    def _refresh_active_cache(self) -> None:
        active_entries = load_active_entries()
        self.active_entries = {entry.mechanic: entry.id for entry in active_entries}
        self.active_entry_objects = {entry.mechanic: entry for entry in active_entries}

    def toggle_admin(self) -> None:
        if not self.is_admin:
            password = simpledialog.askstring("Admin Login", "Passwort:", show="*")
            if password == ADMIN_PASSWORD:
                self.is_admin = True
                messagebox.showinfo("Admin", "Admin-Modus aktiviert.")
            else:
                messagebox.showerror("Admin", "Falsches Passwort.")
                return
        else:
            self.is_admin = False
            messagebox.showinfo("Admin", "Admin abgemeldet.")

        self._update_admin_status()
        if self.page_report is not None:
            for widget in self.page_report.winfo_children():
                widget.destroy()
            self.build_report_page(self.page_report)

    def _update_admin_status(self) -> None:
        if self.is_admin:
            self.admin_status_var.set("Admin aktiv")
            self.admin_status_label.configure(bg=self.ACTIVE_SOFT, fg=self.ACTIVE)
            self.admin_button.configure(text="Admin beenden")
        else:
            self.admin_status_var.set("Admin aus")
            self.admin_status_label.configure(bg=self.PANEL_DARK, fg=self.PANEL_TEXT)
            self.admin_button.configure(text="Admin")

    def on_tab_changed(self, event: tk.Event) -> None:
        if event.widget.tab(event.widget.select(), "text") == self.TAB_REPORTS:
            self.reset_filters()

    def build_stamp_page(self, frame: tk.Frame) -> None:
        for widget in frame.winfo_children():
            widget.destroy()

        top_card = self._create_card(frame, padx=24, pady=22)
        top_card.pack(fill="x", pady=(0, 14))
        top_card.grid_columnconfigure(0, weight=1)
        top_card.grid_columnconfigure(1, weight=0)

        text_block = tk.Frame(top_card, bg=self.SURFACE)
        text_block.grid(row=0, column=0, sticky="w")
        tk.Label(
            text_block,
            text="Operative Zeiterfassung",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Bahnschrift SemiBold", 20),
        ).pack(anchor="w")
        tk.Label(
            text_block,
            text="Ein Klick startet oder stoppt die Zeit einer Person. Die Darstellung ist bewusst fuer unterschiedliche Einsatzbereiche gehalten.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(6, 0))

        summary_badge = tk.Label(
            top_card,
            textvariable=self.active_summary_var,
            bg=self.PANEL_DARK_ALT,
            fg=self.PANEL_TEXT,
            font=("Bahnschrift SemiBold", 11),
            padx=14,
            pady=10,
        )
        summary_badge.grid(row=0, column=1, sticky="e")

        cards_outer = self._create_card(frame, padx=18, pady=18)
        cards_outer.pack(fill="x", pady=(0, 14))
        tk.Label(
            cards_outer,
            text=self.PERSON_LABEL,
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Bahnschrift SemiBold", 16),
        ).pack(anchor="w")
        tk.Label(
            cards_outer,
            text="Gruene Karten sind aktiv. Beim Start wird der letzte verwendete Vorgang automatisch vorgeschlagen.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 14))

        cards_frame = tk.Frame(cards_outer, bg=self.SURFACE)
        cards_frame.pack(fill="x")
        for column in range(len(MECHANIC_CODES)):
            cards_frame.grid_columnconfigure(column, weight=1, uniform="mechanic")

        self.buttons.clear()
        self.mechanic_labels.clear()

        for column, mechanic in enumerate(MECHANIC_CODES):
            card = tk.Frame(
                cards_frame,
                bg="white",
                highlightthickness=1,
                highlightbackground=self.BORDER,
                padx=14,
                pady=14,
            )
            card.grid(row=0, column=column, sticky="nsew", padx=6, pady=6)

            tk.Label(
                card,
                text=mechanic,
                bg="white",
                fg=self.TEXT,
                font=("Bahnschrift SemiBold", 16),
            ).pack(anchor="w")
            tk.Label(
                card,
                text=f"{self.CODE_LABEL} {MECHANIC_CODES[mechanic]}",
                bg="white",
                fg=self.MUTED,
                font=("Segoe UI", 10),
            ).pack(anchor="w", pady=(2, 12))

            status_label = tk.Label(
                card,
                text="Bereit zum Start",
                bg="white",
                fg=self.TEXT,
                font=("Segoe UI Semibold", 11),
            )
            status_label.pack(anchor="w")

            job_label = tk.Label(
                card,
                text=f"Letzter {self.TASK_LABEL}: -",
                bg="white",
                fg=self.MUTED,
                font=("Segoe UI", 10),
            )
            job_label.pack(anchor="w", pady=(6, 14))

            action_button = tk.Button(
                card,
                text="Stempel starten",
                command=lambda mechanic_name=mechanic: self.on_mechanic_click(mechanic_name),
                font=("Segoe UI Semibold", 11),
                bg=self.ACCENT,
                fg="white",
                activebackground=self.ACCENT_DARK,
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=16,
                pady=10,
                cursor="hand2",
            )
            action_button.pack(fill="x")

            self.buttons[mechanic] = action_button
            self.mechanic_labels[mechanic] = {
                "card": card,
                "status": status_label,
                "job": job_label,
            }

        table_card = self._create_card(frame, padx=18, pady=18)
        table_card.pack(expand=True, fill="both")
        tk.Label(
            table_card,
            text=self.ACTIVE_AREA_LABEL,
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Bahnschrift SemiBold", 16),
        ).pack(anchor="w")
        tk.Label(
            table_card,
            text="Hier werden alle aktuell laufenden Erfassungen zentral angezeigt.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 12))

        table_frame = tk.Frame(table_card, bg=self.SURFACE)
        table_frame.pack(expand=True, fill="both")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.active_tree = ttk.Treeview(
            table_frame,
            style="Report.Treeview",
            columns=["ID", self.CODE_LABEL, self.PERSON_LABEL, self.TASK_LABEL, "Start"],
            show="headings",
            height=10,
        )
        for column, width, anchor in [
            ("ID", 70, "center"),
            (self.CODE_LABEL, 90, "center"),
            (self.PERSON_LABEL, 170, "w"),
            (self.TASK_LABEL, 170, "center"),
            ("Start", 190, "center"),
        ]:
            self.active_tree.heading(column, text=column)
            self.active_tree.column(column, width=width, anchor=anchor, stretch=True)
        self.active_tree.grid(row=0, column=0, sticky="nsew")

        active_scroll = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.active_tree.yview,
            style="Report.Vertical.TScrollbar",
        )
        active_scroll.grid(row=0, column=1, sticky="ns")
        self.active_tree.configure(yscrollcommand=active_scroll.set)

        action_row = tk.Frame(table_card, bg=self.SURFACE)
        action_row.pack(fill="x", pady=(14, 0))
        ttk.Button(
            action_row,
            text="Eintrag loeschen",
            command=self.delete_selected_active,
            style="Secondary.TButton",
        ).pack(side="right")

        self.refresh_stamp_section()

    def on_mechanic_click(self, mechanic: str) -> None:
        if mechanic in self.active_entries:
            entry_id = self.active_entries[mechanic]
            save_stop(entry_id)
            self.refresh_stamp_section()
            self.apply_filters()
            return
        self.open_start_popup(mechanic)

    def open_start_popup(self, mechanic: str) -> None:
        popup = tk.Toplevel(self)
        popup.title(f"Start {mechanic}")
        popup.configure(bg=self.SURFACE)
        popup.resizable(False, False)
        popup.transient(self)

        container = tk.Frame(popup, bg=self.SURFACE, padx=24, pady=22)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text=f"Erfassung starten fuer {mechanic}",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Bahnschrift SemiBold", 16),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(
            container,
            text=f"{self.CODE_LABEL} {MECHANIC_CODES.get(mechanic, '-')}",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 16))

        tk.Label(
            container,
            text=f"{self.TASK_LABEL} / Nummer",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Bahnschrift SemiBold", 11),
        ).grid(row=2, column=0, sticky="w", pady=(0, 6))

        job_entry = ttk.Entry(container, width=28, style="Filter.TEntry")
        job_entry.grid(row=3, column=0, columnspan=2, sticky="ew")
        job_entry.insert(0, self.last_jobs.get(mechanic, ""))
        job_entry.focus_set()
        job_entry.select_range(0, "end")

        hint_text = self.last_jobs.get(mechanic)
        tk.Label(
            container,
            text=f"Letzter {self.TASK_LABEL}: {hint_text}" if hint_text else "Noch kein frueherer Eintrag vorhanden.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 10),
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 18))

        def start_tracking() -> None:
            job_number = job_entry.get().strip()
            if not job_number:
                messagebox.showerror("Fehler", f"{self.TASK_LABEL} benoetigt.")
                return
            entry_id, _ = save_start(mechanic, job_number)
            self.last_jobs[mechanic] = job_number
            self.active_entries[mechanic] = entry_id
            self.refresh_stamp_section()
            popup.destroy()

        ttk.Button(container, text="Starten", command=start_tracking, style="Accent.TButton").grid(
            row=5, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(container, text="Abbrechen", command=popup.destroy, style="Secondary.TButton").grid(
            row=5, column=1, sticky="ew"
        )

        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)
        popup.bind("<Return>", lambda _event: start_tracking())
        popup.bind("<Escape>", lambda _event: popup.destroy())
        popup.grab_set()
        self._center_popup(popup, width=420, height=250)

    def refresh_stamp_section(self) -> None:
        self._refresh_last_jobs()
        self._refresh_active_cache()
        self._refresh_mechanic_cards()
        self._refresh_active_table()

    def _refresh_mechanic_cards(self) -> None:
        active_count = len(self.active_entries)
        self.active_summary_var.set(
            f"{active_count} laufende Buchungen" if active_count else "Keine laufende Buchung"
        )

        for mechanic in MECHANIC_CODES:
            widgets = self.mechanic_labels[mechanic]
            card = widgets["card"]
            status_label = widgets["status"]
            job_label = widgets["job"]
            button = self.buttons[mechanic]

            last_job = self.last_jobs.get(mechanic, "-")
            if mechanic in self.active_entry_objects:
                active_entry = self.active_entry_objects[mechanic]
                card.configure(bg=self.ACTIVE_SOFT, highlightbackground=self.ACTIVE)
                status_label.configure(
                    text=f"Aktiv seit {active_entry.start.strftime('%H:%M')}",
                    bg=self.ACTIVE_SOFT,
                    fg=self.ACTIVE,
                )
                job_label.configure(
                    text=f"{self.TASK_LABEL}: {active_entry.job_number}",
                    bg=self.ACTIVE_SOFT,
                    fg=self.TEXT,
                )
                button.configure(
                    text="Stempel stoppen",
                    bg=self.ACTIVE,
                    activebackground="#25634a",
                )
            else:
                card.configure(bg="white", highlightbackground=self.BORDER)
                status_label.configure(text="Bereit zum Start", bg="white", fg=self.TEXT)
                job_label.configure(text=f"Letzter {self.TASK_LABEL}: {last_job}", bg="white", fg=self.MUTED)
                button.configure(
                    text="Stempel starten",
                    bg=self.ACCENT,
                    activebackground=self.ACCENT_DARK,
                )

    def _refresh_active_table(self) -> None:
        self.active_tree.delete(*self.active_tree.get_children())
        for entry in load_active_entries():
            self.active_tree.insert(
                "",
                "end",
                values=(
                    entry.id,
                    entry.kodex,
                    entry.mechanic,
                    entry.job_number,
                    entry.start.strftime("%d-%m-%Y %H:%M"),
                ),
            )

    def build_report_page(self, frame: tk.Frame) -> None:
        for widget in frame.winfo_children():
            widget.destroy()

        header_card = self._create_card(frame, padx=24, pady=22)
        header_card.pack(fill="x", pady=(0, 14))
        header_card.grid_columnconfigure(0, weight=1)
        header_card.grid_columnconfigure(1, weight=0)

        text_block = tk.Frame(header_card, bg=self.SURFACE)
        text_block.grid(row=0, column=0, sticky="w")
        tk.Label(
            text_block,
            text="Analyse und Protokolle",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Bahnschrift SemiBold", 20),
        ).pack(anchor="w")
        tk.Label(
            text_block,
            text="Filtere die Historie, pruefe Gesamtzeiten und erstelle Ausdrucke fuer operative oder administrative Zwecke.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(6, 0))

        total_badge = tk.Label(
            header_card,
            textvariable=self.total_time_var,
            bg=self.PANEL_DARK_ALT,
            fg=self.PANEL_TEXT,
            font=("Bahnschrift SemiBold", 11),
            padx=14,
            pady=10,
        )
        total_badge.grid(row=0, column=1, sticky="e")

        if self.is_admin:
            admin_card = self._create_card(frame, padx=18, pady=16)
            admin_card.pack(fill="x", pady=(0, 14))
            tk.Label(
                admin_card,
                text="Admin-Werkzeuge",
                bg=self.SURFACE,
                fg=self.TEXT,
                font=("Bahnschrift SemiBold", 15),
            ).pack(anchor="w")
            tk.Label(
                admin_card,
                text="Diese Funktionen greifen direkt in die Daten ein und bleiben nur im Admin-Modus sichtbar.",
                bg=self.SURFACE,
                fg=self.MUTED,
                font=("Segoe UI", 10),
            ).pack(anchor="w", pady=(4, 12))

            button_row = tk.Frame(admin_card, bg=self.SURFACE)
            button_row.pack(fill="x")
            ttk.Button(
                button_row,
                text="Eintrag bearbeiten",
                command=self.edit_selected_entry,
                style="Secondary.TButton",
            ).pack(side="left", padx=(0, 10))
            ttk.Button(
                button_row,
                text="Datenbank leeren",
                command=self.clear_database,
                style="Accent.TButton",
            ).pack(side="left")

        filter_card = self._create_card(frame, padx=18, pady=18)
        filter_card.pack(fill="x", pady=(0, 14))
        tk.Label(
            filter_card,
            text="Filter",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Bahnschrift SemiBold", 16),
        ).grid(row=0, column=0, columnspan=6, sticky="w")
        tk.Label(
            filter_card,
            text="Die Gesamtzeit erscheint automatisch, sobald mindestens ein Filter aktiv ist.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(4, 14))

        tk.Label(filter_card, text=self.PERSON_LABEL, bg=self.SURFACE, fg=self.TEXT, font=("Bahnschrift SemiBold", 10)).grid(
            row=2, column=0, sticky="w"
        )
        tk.Label(filter_card, text=self.TASK_LABEL, bg=self.SURFACE, fg=self.TEXT, font=("Bahnschrift SemiBold", 10)).grid(
            row=2, column=1, sticky="w"
        )
        tk.Label(filter_card, text="Datum", bg=self.SURFACE, fg=self.TEXT, font=("Bahnschrift SemiBold", 10)).grid(
            row=2, column=2, sticky="w"
        )

        mechanic_box = ttk.Combobox(
            filter_card,
            textvariable=self.filter_mechanic,
            values=[""] + list(MECHANIC_CODES),
            state="readonly",
            width=16,
            style="Filter.TCombobox",
        )
        mechanic_box.grid(row=3, column=0, sticky="ew", padx=(0, 10), pady=(6, 0))

        job_entry = ttk.Entry(filter_card, textvariable=self.filter_job, width=16, style="Filter.TEntry")
        job_entry.grid(row=3, column=1, sticky="ew", padx=(0, 10), pady=(6, 0))

        self.report_date_entry = DateEntry(
            filter_card,
            textvariable=self.filter_date,
            date_pattern="yyyy-mm-dd",
            font=("Segoe UI", 11),
            width=12,
        )
        self.report_date_entry.grid(row=3, column=2, sticky="ew", padx=(0, 10), pady=(6, 0))

        ttk.Button(filter_card, text="Filter anwenden", command=self.apply_filters, style="Accent.TButton").grid(
            row=3, column=3, sticky="ew", padx=(4, 10), pady=(6, 0)
        )
        ttk.Button(filter_card, text="Filter zuruecksetzen", command=self.reset_filters, style="Secondary.TButton").grid(
            row=3, column=4, sticky="ew", pady=(6, 0)
        )

        filter_card.grid_columnconfigure(0, weight=1)
        filter_card.grid_columnconfigure(1, weight=1)
        filter_card.grid_columnconfigure(2, weight=1)
        filter_card.grid_columnconfigure(3, weight=0)
        filter_card.grid_columnconfigure(4, weight=0)

        table_card = self._create_card(frame, padx=18, pady=18)
        table_card.pack(expand=True, fill="both")
        title_row = tk.Frame(table_card, bg=self.SURFACE)
        title_row.pack(fill="x", pady=(0, 12))
        tk.Label(
            title_row,
            text="Historie",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Bahnschrift SemiBold", 16),
        ).pack(side="left")
        ttk.Button(title_row, text="Drucken", command=self.print_history, style="Secondary.TButton").pack(side="right")
        ttk.Button(title_row, text="Schnelldruck", command=self.quick_print, style="Accent.TButton").pack(
            side="right", padx=(0, 10)
        )

        tree_wrap = tk.Frame(table_card, bg=self.SURFACE)
        tree_wrap.pack(expand=True, fill="both")
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)

        self.history_tree = ttk.Treeview(
            tree_wrap,
            style="Report.Treeview",
            columns=["ID", self.CODE_LABEL, self.PERSON_LABEL, self.TASK_LABEL, "Start", "Stop", "Dauer"],
            show="headings",
            height=14,
        )
        for column, width, anchor in [
            ("ID", 70, "center"),
            (self.CODE_LABEL, 90, "center"),
            (self.PERSON_LABEL, 170, "w"),
            (self.TASK_LABEL, 140, "center"),
            ("Start", 190, "center"),
            ("Stop", 190, "center"),
            ("Dauer", 110, "center"),
        ]:
            self.history_tree.heading(column, text=column)
            self.history_tree.column(column, width=width, anchor=anchor, stretch=True)
        self.history_tree.grid(row=0, column=0, sticky="nsew")

        history_scroll = ttk.Scrollbar(
            tree_wrap,
            orient="vertical",
            command=self.history_tree.yview,
            style="Report.Vertical.TScrollbar",
        )
        history_scroll.grid(row=0, column=1, sticky="ns")
        self.history_tree.configure(yscrollcommand=history_scroll.set)

        self.apply_filters()

    def edit_selected_entry(self) -> None:
        selection = self.history_tree.selection()
        if not selection:
            messagebox.showerror("Fehler", "Eintrag waehlen.")
            return

        entry_id = self.history_tree.item(selection[0])["values"][0]
        with sqlite3.connect(DB_NAME, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mechanic, job_number, start, stop FROM entries WHERE id = ?", (entry_id,))
            row = cursor.fetchone()

        if not row:
            messagebox.showerror("Fehler", "Eintrag nicht gefunden.")
            return

        popup = tk.Toplevel(self)
        popup.title(f"Eintrag {entry_id} bearbeiten")
        popup.configure(bg=self.SURFACE)
        popup.resizable(False, False)
        popup.transient(self)

        container = tk.Frame(popup, bg=self.SURFACE, padx=24, pady=22)
        container.pack(fill="both", expand=True)

        fields = [
            (self.PERSON_LABEL, row[0]),
            (self.TASK_LABEL, row[1]),
            ("Start", row[2].replace("T", " ")),
            ("Stopp", row[3].replace("T", " ")),
        ]
        entries: list[ttk.Entry] = []
        for index, (label_text, value) in enumerate(fields):
            tk.Label(
                container,
                text=label_text,
                bg=self.SURFACE,
                fg=self.TEXT,
                font=("Bahnschrift SemiBold", 10),
            ).grid(row=index * 2, column=0, sticky="w", pady=(0 if index == 0 else 10, 4))
            field = ttk.Entry(container, width=28, style="Filter.TEntry")
            field.grid(row=index * 2 + 1, column=0, sticky="ew")
            field.insert(0, value)
            entries.append(field)

        def save_edit() -> None:
            try:
                mechanic = entries[0].get().strip()
                job_number = entries[1].get().strip()
                start = datetime.fromisoformat(entries[2].get().strip().replace(" ", "T"))
                stop = datetime.fromisoformat(entries[3].get().strip().replace(" ", "T"))
                duration = (stop - start).total_seconds()
            except ValueError:
                messagebox.showerror("Fehler", "Start und Stopp muessen ein gueltiges Datumsformat haben.")
                return

            with sqlite3.connect(DB_NAME, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE entries
                    SET mechanic = ?, job_number = ?, start = ?, stop = ?, duration = ?
                    WHERE id = ?
                    """,
                    (mechanic, job_number, start.isoformat(), stop.isoformat(), duration, entry_id),
                )
            popup.destroy()
            self.refresh_stamp_section()
            self.apply_filters()

        button_row = tk.Frame(container, bg=self.SURFACE)
        button_row.grid(row=8, column=0, sticky="ew", pady=(18, 0))
        ttk.Button(button_row, text="Speichern", command=save_edit, style="Accent.TButton").pack(side="left")
        ttk.Button(button_row, text="Abbrechen", command=popup.destroy, style="Secondary.TButton").pack(
            side="left", padx=(10, 0)
        )

        container.grid_columnconfigure(0, weight=1)
        popup.grab_set()
        self._center_popup(popup, width=430, height=360)

    def apply_filters(self) -> None:
        filtered_entries = self.get_filtered_history_entries()
        date = self.filter_date.get().strip()
        mechanic = self.filter_mechanic.get().strip()
        job_number = self.filter_job.get().strip()

        if date or mechanic or job_number:
            total_seconds = sum(
                entry.duration.total_seconds() for entry in filtered_entries if entry.duration is not None
            )
            total_td = timedelta(seconds=int(total_seconds))
            self.total_time_var.set(f"Gesamtzeit {format_duration(total_td)}")
        else:
            self.total_time_var.set("")

        self.history_tree.delete(*self.history_tree.get_children())
        for entry in reversed(filtered_entries):
            self.history_tree.insert(
                "",
                "end",
                values=(
                    entry.id,
                    entry.kodex,
                    entry.mechanic,
                    entry.job_number,
                    entry.start.strftime("%d-%m-%Y %H:%M"),
                    entry.stop.strftime("%d-%m-%Y %H:%M"),
                    format_duration(entry.duration),
                ),
            )

    def get_filtered_history_entries(self) -> list[Entry]:
        all_entries = load_history_entries()
        date = self.filter_date.get().strip()
        mechanic = self.filter_mechanic.get().strip()
        job_number = self.filter_job.get().strip()

        filtered: list[Entry] = []
        for entry in all_entries:
            if date and entry.start.date().isoformat() != date:
                continue
            if mechanic and entry.mechanic != mechanic:
                continue
            if job_number and entry.job_number != job_number:
                continue
            filtered.append(entry)
        return filtered

    def reset_filters(self) -> None:
        self.filter_date.set("")
        self.filter_mechanic.set("")
        self.filter_job.set("")
        if hasattr(self, "report_date_entry") and self.report_date_entry.winfo_exists():
            self.report_date_entry.delete(0, "end")
        self.apply_filters()

    def print_history(self) -> None:
        filtered_entries = self.get_filtered_history_entries()
        if not filtered_entries:
            messagebox.showinfo("Drucken", "Keine Eintraege zum Drucken gefunden.")
            return

        filename = self._build_report_pdf(
            filtered_entries,
            include_filter_header=True,
            mechanic_only_header=False,
        )
        try:
            os.startfile(filename)
        except Exception as exc:
            messagebox.showerror("Drucken", f"Fehler beim Oeffnen des Berichts: {exc}")

    def quick_print(self) -> None:
        mechanic = self.filter_mechanic.get().strip()
        date = self.filter_date.get().strip()
        all_history = load_history_entries()
        filtered_entries = [
            entry
            for entry in all_history
            if (not mechanic or entry.mechanic == mechanic)
            and (not date or entry.start.date().isoformat() == date)
        ]
        if not filtered_entries:
            messagebox.showinfo("Schnelldruck", "Keine Eintraege zum Drucken gefunden.")
            return

        filename = self._build_report_pdf(
            filtered_entries,
            include_filter_header=False,
            mechanic_only_header=True,
        )
        try:
            win32api.ShellExecute(0, "print", filename, None, ".", 0)
        except Exception as exc:
            messagebox.showerror("Schnelldruck", f"Fehler beim Schnell-Druck: {exc}")

    def _build_report_pdf(
        self,
        entries: list[Entry],
        *,
        include_filter_header: bool,
        mechanic_only_header: bool,
    ) -> str:
        entries = sorted(entries, key=lambda entry: entry.start)
        grouped: dict[str, list[Entry]] = {}
        for entry in entries:
            grouped.setdefault(entry.job_number, []).append(entry)

        filename = os.path.join(os.getcwd(), "bericht.pdf")
        document = SimpleDocTemplate(filename, pagesize=A4)
        styles = getSampleStyleSheet()
        bold = ParagraphStyle("Bold", parent=styles["Normal"], fontName="Helvetica-Bold")
        elements: list = []

        date = self.filter_date.get().strip()
        mechanic = self.filter_mechanic.get().strip()
        job_number = self.filter_job.get().strip()

        if include_filter_header:
            if date:
                elements.append(Paragraph(f"Datum: {date}", bold))
            if mechanic:
                elements.append(Paragraph(f"{self.PERSON_LABEL}: {mechanic}", bold))
            if job_number:
                elements.append(Paragraph(f"{self.TASK_LABEL}: {job_number}", bold))
        elif mechanic_only_header and mechanic:
            elements.append(Paragraph(f"{self.PERSON_LABEL}: {mechanic}", bold))

        if elements:
            elements.append(Spacer(1, 12))

        data = [["ID", self.CODE_LABEL, self.PERSON_LABEL, self.TASK_LABEL, "Start", "Stop", "Dauer"]]
        for entry in entries:
            data.append(
                [
                    str(entry.id),
                    entry.kodex,
                    entry.mechanic,
                    entry.job_number,
                    entry.start.strftime("%d-%m-%Y %H:%M"),
                    entry.stop.strftime("%d-%m-%Y %H:%M"),
                    format_duration(entry.duration),
                ]
            )

        for grouped_entries in grouped.values():
            mechanic_totals: dict[str, float] = {}
            for entry in grouped_entries:
                mechanic_totals.setdefault(entry.mechanic, 0.0)
                if entry.duration is not None:
                    mechanic_totals[entry.mechanic] += entry.duration.total_seconds()
            if len(mechanic_totals) > 1:
                data.append(["", "", "", "Subtotals", "", "", ""])
                for mechanic_name, seconds in mechanic_totals.items():
                    data.append(["", "", "", mechanic_name, "", "", format_duration(timedelta(seconds=int(seconds)))])
                data.append([""] * 7)

        total_seconds = sum(entry.duration.total_seconds() for entry in entries if entry.duration is not None)
        data.append(["", "", "", "Gesamt", "", "", format_duration(timedelta(seconds=int(total_seconds)))])

        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9cab5")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (3, len(data) - 1), (3, len(data) - 1), "Helvetica-Bold"),
                    ("FONTNAME", (6, len(data) - 1), (6, len(data) - 1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(table)
        document.build(elements)
        return filename

    def clear_database(self) -> None:
        if not self.is_admin:
            return
        if not messagebox.askyesno("Admin", "Alle Eintraege loeschen? Dies ist unwiderruflich."):
            return
        with sqlite3.connect(DB_NAME, timeout=30) as conn:
            conn.execute("DELETE FROM entries")
        messagebox.showinfo("Admin", "Datenbank geleert.")
        self.refresh_stamp_section()
        self.apply_filters()

    def delete_selected_active(self) -> None:
        selection = self.active_tree.selection()
        if not selection:
            messagebox.showerror("Fehler", "Bitte einen aktiven Eintrag auswaehlen.")
            return

        entry_id = self.active_tree.item(selection[0])["values"][0]
        if not messagebox.askyesno("Eintrag loeschen", f"Eintrag {entry_id} unwiderruflich loeschen?"):
            return

        with sqlite3.connect(DB_NAME, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

        self.refresh_stamp_section()

    def on_closing(self) -> None:
        if messagebox.askyesno("Beenden", "Bisch dor gonz sicher, dass du is Programm zuatian willsch?"):
            self.destroy()

    def _create_card(self, parent: tk.Widget, *, padx: int, pady: int) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=self.SURFACE,
            highlightthickness=1,
            highlightbackground=self.BORDER,
            padx=padx,
            pady=pady,
        )

    def _center_popup(self, popup: tk.Toplevel, *, width: int, height: int) -> None:
        self.update_idletasks()
        root_x = self.winfo_x()
        root_y = self.winfo_y()
        root_width = self.winfo_width()
        root_height = self.winfo_height()
        x = root_x + max((root_width - width) // 2, 0)
        y = root_y + max((root_height - height) // 2, 0)
        popup.geometry(f"{width}x{height}+{x}+{y}")


if __name__ == "__main__":
    app = TimeTrackerApp()
    app.mainloop()
