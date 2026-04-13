import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sqlite3
from datetime import datetime, timedelta
from dataclasses import dataclass
# Externe Bibliothek für Kalender-Widgets
from tkcalendar import DateEntry
import os
# ReportLab für PDF-Export
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.platypus import Spacer


# Admin-Konfiguration
ADMIN_PASSWORD = 'AdminBus'

DB_NAME = 'time_entries.db'
MECHANIC_CODES = {
    'Daniel': '01',
    'Hubert': '02',
    'Jonas': '03',
    'Alex': '04',
    'Jolly': '05',
}

@dataclass
class Entry:
    id: int
    kodex: str
    mechanic: str
    job_number: str
    start: datetime
    stop: datetime = None
    duration: timedelta = None

# -- Datenbankfunktionen --
def init_db() -> None:
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL;')
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS entries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kodex TEXT NOT NULL,
        mechanic TEXT NOT NULL,
        job_number TEXT NOT NULL,
        start TEXT NOT NULL,
        stop TEXT,
        duration REAL
    )
    ''')
    conn.commit()
    conn.close()

# Speichert Start der Erfassung
def save_start(mechanic: str, job_number: str) -> tuple[int, datetime]:
    start = datetime.now()
    kodex = MECHANIC_CODES.get(mechanic, '')
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL;')
    c = conn.cursor()
    c.execute(
        'INSERT INTO entries(kodex, mechanic, job_number, start) VALUES (?, ?, ?, ?)',
        (kodex, mechanic, job_number, start.isoformat())
    )
    entry_id = c.lastrowid
    conn.commit()
    conn.close()
    return entry_id, start

# Stoppt Erfassung, berechnet Dauer
def save_stop(entry_id: int) -> tuple[datetime, timedelta]:
    stop = datetime.now()
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL;')
    c = conn.cursor()
    c.execute('SELECT start FROM entries WHERE id = ?', (entry_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise ValueError("Eintrag nicht gefunden")
    start = datetime.fromisoformat(row[0])
    duration = stop - start
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL;')
    c = conn.cursor()
    c.execute(
        'UPDATE entries SET stop = ?, duration = ? WHERE id = ?',
        (stop.isoformat(), duration.total_seconds(), entry_id)
    )
    conn.commit()
    conn.close()
    return stop, duration

# Lädt aktive Einträge
def load_active_entries() -> list[Entry]:
    conn = sqlite3.connect(DB_NAME, timeout=30)
    c = conn.cursor()
    c.execute('SELECT id, kodex, mechanic, job_number, start FROM entries WHERE stop IS NULL')
    rows = c.fetchall()
    conn.close()
    return [Entry(
        id=r[0], kodex=r[1], mechanic=r[2], job_number=r[3],
        start=datetime.fromisoformat(r[4])
    ) for r in rows]

# Lädt abgeschlossene Einträge
def load_history_entries() -> list[Entry]:
    conn = sqlite3.connect(DB_NAME, timeout=30)
    c = conn.cursor()
    c.execute('SELECT id, kodex, mechanic, job_number, start, stop, duration FROM entries WHERE stop IS NOT NULL')
    rows = c.fetchall()
    conn.close()
    return [Entry(
        id=r[0], kodex=r[1], mechanic=r[2], job_number=r[3],
        start=datetime.fromisoformat(r[4]),
        stop=datetime.fromisoformat(r[5]),
        duration=timedelta(seconds=r[6]) if r[6] is not None else None
    ) for r in rows]

# Formatiert Dauer
def format_duration(td: timedelta) -> str:
    if td is None:
        return ''
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

# -- GUI --
class TimeTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stunden Tracker")
        self.state('zoomed')
        init_db()

        # Admin-Flag und Page-Ref
        self.is_admin = False
        self.page_report = None

        # Daten-Strukturen
        self.active_entries = {}
        self.buttons = {}
        self.filter_date     = tk.StringVar()
        self.filter_mechanic = tk.StringVar()
        self.filter_job      = tk.StringVar()


        # Order-Merker
        self.last_jobs: dict[str, str] = {}

        style = ttk.Style(self)
        # Definiere einen neuen Stil "Large.Treeview"
        style.configure("Large.Treeview",
                        font=("Arial", 18),     # größere Schrift
                        rowheight=30)           # höhere Zeilen
        style.configure("Large.Treeview.Heading",
                        font=("Arial", 14, "bold"))  # größere, fette Überschriften
        
        ############### Große Eingabefelder und Buttons
        style.configure("Large.TEntry",
                        font=("Arial", 14), padding=4)
        style.configure("Large.TCombobox",
                        font=("Arial", 14), padding=4)
        style.configure("Large.TButton",
                        font=("Arial", 14, "bold"), padding=6)

        style.configure("TotalTime.TLabel",
                background="yellow",
                foreground="black")  # Textfarbe ggf. schwarz


        # Notebook und Pages
        notebook = ttk.Notebook(self)
        notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        page_stamp = ttk.Frame(notebook)
        page_report = ttk.Frame(notebook)
        notebook.add(page_stamp, text="Stempeln")
        notebook.add(page_report, text="Berichte")
        notebook.pack(expand=True, fill='both')

        # Admin-Button oben rechts
        admin_btn = ttk.Button(self, text="Admin", command=self.toggle_admin)
        admin_btn.place(relx=0.98, rely=0.02, anchor='ne')
        admin_btn.lift()

        self.page_report = page_report
        self.build_stamp_page(page_stamp)
        self.build_report_page(page_report)

        # Filter zurücksetzen
        self.reset_filters()

    def toggle_admin(self):
        if not self.is_admin:
            pw = simpledialog.askstring("Admin Login", "Passwort:", show='*')
            if pw == ADMIN_PASSWORD:
                self.is_admin = True
                messagebox.showinfo("Admin", "Admin-Modus aktiviert.")
            else:
                messagebox.showerror("Admin", "Falsches Passwort.")
                return
        else:
            self.is_admin = False
            messagebox.showinfo("Admin", "Admin abgemeldet.")
        # Bericht-Seite neu zeichnen
        for w in self.page_report.winfo_children(): w.destroy()
        self.build_report_page(self.page_report)

    def on_tab_changed(self, event):
        if event.widget.tab(event.widget.select(), 'text') == 'Berichte':
            self.reset_filters()

    def build_stamp_page(self, frame):
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(padx=10, pady=10)

        # alle Mechaniker‐Buttons nebeneinander in Zeile 0
        for idx, mech in enumerate(MECHANIC_CODES):
            b = tk.Button(
                btn_frame,
                text=mech,
                width=25, height=3,
                font=('Arial',14,'bold'),
                bg='lightgray',
                command=lambda m=mech: self.on_mechanic_click(m)
            )
            b.grid(row=0, column=idx, padx=5, pady=5)
            self.buttons[mech] = b

        ttk.Label(frame, text="Aktive Einträge").pack(pady=(5,0))
        self.active_tree = ttk.Treeview(
            frame, style="Large.Treeview",
            columns=['ID','Kodex','Mechaniker','Auftrag','Start'],
            show='headings', height=10
        )
        widths = [60, 80, 120, 120, 180]
        for col, w in zip(self.active_tree['columns'], widths):
            self.active_tree.heading(col, text=col)
            self.active_tree.column(col, width=w)
        self.active_tree.pack(expand=True, fill='both', padx=10, pady=5)
        self.load_active()


    def on_mechanic_click(self, mechanic):
        if mechanic in self.active_entries:
            eid = self.active_entries.pop(mechanic)
            stop, dur = save_stop(eid)
            # messagebox.showinfo("Stopp", f"{mechanic} gestoppt: {format_duration(dur)}")
            self.buttons[mechanic].config(bg='lightgray')
        else:
            popup = tk.Toplevel(self); popup.title(f"Start {mechanic}")
            popup.geometry("300x150+750+300")
            label = ttk.Label(popup, text="Auftrag Nr.: ", font=('Arial',14))
            label.grid(row=0, column=1, padx=10, pady=10, sticky='w')
            ent = ttk.Entry(popup, font=('Arial',14))
            ent.grid(row=0, column=1, padx=10, pady=10, sticky='w')
            ent.insert(0, self.last_jobs.get(mechanic, ''))
            def ds():
                job=ent.get().strip()
                if not job: messagebox.showerror("Fehler","Auftragsnummer benötigt."); return
                eid,_=save_start(mechanic,job)
                self.active_entries[mechanic]=eid
                self.last_jobs[mechanic] = job
                self.buttons[mechanic].config(bg='lightgreen')
                popup.destroy(); self.load_active()
            start_btn = tk.Button(popup, text="Start", font = ('Arial', 14, 'bold'), width=15, height=2, command=ds)
            start_btn.grid(row=1, column=0, columnspan=2, pady=(0,15))
            popup.grab_set()
        self.load_active()

    def load_active(self):
        self.active_tree.delete(*self.active_tree.get_children())
        for e in load_active_entries():
            self.active_tree.insert('', 'end', values=(
                e.id, e.kodex, e.mechanic, e.job_number, e.start.strftime("%d-%m-%Y %H:%M")
            ))

    def build_report_page(self, frame):
        # Admin controls
        if self.is_admin:
            admin_frame = ttk.Frame(frame)
            admin_frame.pack(fill='x', padx=5, pady=5)
            ttk.Button(admin_frame, text="Datenbank leeren", command=self.clear_database).pack(side='left', padx=5)
            ttk.Button(admin_frame, text="Eintrag bearbeiten", command=self.edit_selected_entry).pack(side='left', padx=5)

        # Platzhalter für Gesamtzeit
        self.total_time_label = ttk.Label(
            frame,
            text="",
            style="TotalTime.TLabel",
            font=("Arial", 25, "bold"),
            anchor='e',
            justify='right'
        )
        self.total_time_label.pack(
            fill='x',        # dehnt das Label auf volle Breite
            padx=5,
            pady=(40,20)
        )

        # --- Filter-Zeile ---
        filt = ttk.Frame(frame)
        filt.pack(fill='x', padx=5, pady=(5,10))

        # Mechaniker-Auswahl
        ttk.Label(filt, text="Mechaniker:", font=("Arial", 14)).pack(side='left', padx=(20,4))
        ttk.Combobox(
            filt,
            textvariable=self.filter_mechanic,
            values=[''] + list(MECHANIC_CODES),
            state='readonly',
            width=12,
            style="Large.TCombobox"
        ).pack(side='left', padx=4)

        # Auftrag-Eingabe
        ttk.Label(filt, text="Auftrag:", font=("Arial", 14)).pack(side='left', padx=(20,4))
        ttk.Entry(
            filt,
            textvariable=self.filter_job,
            width=14,
            style="Large.TEntry"
        ).pack(side='left', padx=4)

        # Nur ein Datum-Feld
        ttk.Label(filt, text="Datum:", font=("Arial", 14)).pack(side='left', padx=(0,4))
        DateEntry(
            filt,
            textvariable=self.filter_date,    
            date_pattern='yyyy-mm-dd',
            font=("Arial", 14),
            width=12
        ).pack(side='left', padx=4)


        # Filter-Buttons
        ttk.Button(
            filt,
            text="Filter anwenden",
            command=self.apply_filters,
            style="Large.TButton"
        ).pack(side='left', padx=(20,4))
        ttk.Button(
            filt,
            text="Filter zurücksetzen",
            command=self.reset_filters,
            style="Large.TButton"
        ).pack(side='left')

        # Print button und Schnelldruck
        print_frame = ttk.Frame(frame)
        print_frame.pack(fill='x', padx=5, pady=(0,5))
        ttk.Button(print_frame, text="Drucken", command=self.print_history, style="Large.TButton").pack(side='right')
        ttk.Button(print_frame, text="Schnelldruck", command=self.quick_print, style="Large.TButton").pack(side='right', padx=(0,10))

        # History table (großer Stil)
        self.history_tree = ttk.Treeview(
            frame,
            style="Large.Treeview",
            columns=['ID','Kodex','Mechaniker','Auftrag','Start','Stop','Dauer'],
            show='headings',
            height=10
        )
        col_widths = [60, 80, 120, 120, 180, 180, 100]
        for col, w in zip(self.history_tree['columns'], col_widths):
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=w)
        self.history_tree.pack(expand=True, fill='both', padx=5, pady=5)

        # initialer Filter-Run
        self.apply_filters()


    def edit_selected_entry(self):
        sel=self.history_tree.selection()
        if not sel: messagebox.showerror("Fehler","Eintrag wählen"); return
        entry_id=self.history_tree.item(sel[0])['values'][0]
        conn=sqlite3.connect(DB_NAME);c=conn.cursor()
        c.execute('SELECT mechanic,job_number,start,stop FROM entries WHERE id=?',(entry_id,))
        mech,job,start_iso,stop_iso=c.fetchone();conn.close()
        popup=tk.Toplevel(self);popup.title(f"Bearbeite {entry_id}")
        ttk.Label(popup,text="Mechaniker:").grid(row=0,column=0);mech_ent=ttk.Entry(popup);mech_ent.grid(row=0,column=1);mech_ent.insert(0,mech)
        ttk.Label(popup,text="Auftrag:").grid(row=1,column=0);job_ent=ttk.Entry(popup);job_ent.grid(row=1,column=1);job_ent.insert(0,job)
        ttk.Label(popup,text="Start:").grid(row=2,column=0);start_ent=ttk.Entry(popup);start_ent.grid(row=2,column=1);start_ent.insert(0,start_iso.replace('T',' '))
        ttk.Label(popup,text="Stopp:").grid(row=3,column=0);stop_ent=ttk.Entry(popup);stop_ent.grid(row=3,column=1);stop_ent.insert(0,stop_iso.replace('T',' '))
        def save_edit():
            nm=mech_ent.get().strip();nj=job_ent.get().strip()
            ns=datetime.fromisoformat(start_ent.get().replace(' ','T'))
            ne=datetime.fromisoformat(stop_ent.get().replace(' ','T'))
            nd=(ne-ns).total_seconds()
            conn=sqlite3.connect(DB_NAME);c=conn.cursor()
            c.execute('UPDATE entries SET mechanic=?,job_number=?,start=?,stop=?,duration=? WHERE id=?',
                      (nm,nj,ns.isoformat(),ne.isoformat(),nd,entry_id))
            conn.commit();conn.close();popup.destroy();self.apply_filters();self.load_active()
        ttk.Button(popup,text="Speichern",command=save_edit).grid(row=4,column=0,columnspan=2,pady=10);popup.grab_set()

    def apply_filters(self):
        all_hist = load_history_entries()
        date = self.filter_date.get()       # dein einziges Datums-Feld
        mech = self.filter_mechanic.get()    # Mechaniker-Filter
        job  = self.filter_job.get()         # Auftrag-Filter

        # 2. Gesamtzeit nur dann anzeigen, wenn mind. 1 Filter aktiv ist
        if date or mech or job:
            # berechne Gesamtsekunden über alle bisherigen gefilterten Einträge
            total_secs = sum(e.duration.total_seconds()
                             for e in load_history_entries()
                             if (not date or e.start.date().isoformat()==date)
                             and (not mech or e.mechanic==mech)
                             and (not job  or e.job_number==job)
                             and e.duration)
            total_td = timedelta(seconds=int(total_secs))
            self.total_time_label.config(text=f"Gesamtzeit: {format_duration(total_td)}")
        else:
            # keine Filter → verstecke Label
            self.total_time_label.config(text="")

        filtered = []
        for e in all_hist:
            # wenn Datum gesetzt, dann muss e.start.exakt diesem Datum entsprechen
            if date and e.start.date().isoformat() != date:
                continue
            # Mechaniker-Filter
            if mech and e.mechanic != mech:
                continue
            # Auftrag-Filter (exakte Übereinstimmung)
            if job and e.job_number != job:
                continue
            filtered.append(e)

        filtered.reverse()

        # Treeview neu befüllen
        self.history_tree.delete(*self.history_tree.get_children())
        for e in filtered:
            self.history_tree.insert('', 'end', values=(
                e.id,
                e.kodex,
                e.mechanic,
                e.job_number,
                e.start.strftime("%d-%m-%Y %H:%M"),
                e.stop.strftime("%d-%m-%Y %H:%M"),
                format_duration(e.duration)
            ))


    def reset_filters(self):
        self.filter_date.set('')
        self.filter_mechanic.set('')
        self.filter_job.set('')
        self.apply_filters()

    def print_history(self):
        # 1. Filter anwenden wie in apply_filters
        all_hist = load_history_entries()
        date = self.filter_date.get()
        mech = self.filter_mechanic.get()
        job  = self.filter_job.get()

        filtered = []
        for e in all_hist:
            if date and e.start.date().isoformat() != date:
                continue
            if mech and e.mechanic != mech:
                continue
            if job and e.job_number != job:
                continue
            filtered.append(e)

        filtered.reverse()

        if not filtered:
            messagebox.showinfo("Drucken", "Keine Einträge zum Drucken gefunden.")
            return

        # 2. Gruppieren nach Auftrag
        grouped: dict[str, list[Entry]] = {}
        for e in filtered:
            grouped.setdefault(e.job_number, []).append(e)

        # 3. PDF vorbereiten
        filename = os.path.join(os.getcwd(), "bericht.pdf")
        doc = SimpleDocTemplate(filename, pagesize=A4)
        styles = getSampleStyleSheet()
        elements: list = []
        bold = ParagraphStyle("Bold", parent=styles["Normal"], fontName="Helvetica-Bold")

        # 4. Filter-Übersicht
        if date: elements.append(Paragraph(f"Datum: {date}", bold))
        if mech: elements.append(Paragraph(f"Mechaniker: {mech}", bold))
        if job:  elements.append(Paragraph(f"Auftrag: {job}", bold))

        # 5. Kopfzeile der Tabelle
        data = [["ID","Kodex","Mechaniker","Auftrag","Start","Stop","Dauer"]]

        # 6. Einträge + Subtotals
        for job_num, entries in grouped.items():
            #elements.append(Paragraph(f"Auftrag: {job_num}", bold))
            for e in entries:
                data.append([
                    str(e.id), e.kodex, e.mechanic, e.job_number,
                    e.start.strftime("%d-%m-%Y %H:%M"),
                    e.stop.strftime("%d-%m-%Y %H:%M"),
                    format_duration(e.duration)
                ])
            mech_sum: dict[str, float] = {}
            for e in entries:
                mech_sum.setdefault(e.mechanic, 0)
                if e.duration:
                    mech_sum[e.mechanic] += e.duration.total_seconds()
            if len(mech_sum) > 1:
                data.append(["","","","Subtotals","","",""])
                for m, secs in mech_sum.items():
                    td = timedelta(seconds=int(secs))
                    data.append(["","","", m, "","", format_duration(td)])
                data.append([""]*7)

        # 7. Gesamtzeit
        total_secs = sum(e.duration.total_seconds() for e in filtered if e.duration)
        total_td = timedelta(seconds=int(total_secs))
        data.append(["","","","Gesamt","","", format_duration(total_td)])

        # 8. Tabelle formatieren
        table = Table(data, repeatRows=1)
        tbl_style = TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTNAME",(3,len(data)-1),(3,len(data)-1),"Helvetica-Bold"),
            ("FONTNAME",(6,len(data)-1),(6,len(data)-1),"Helvetica-Bold"),
            ("GRID",(0,0),(-1,-1),0.5,colors.grey),
        ])
        table.setStyle(tbl_style)
        elements.append(table)

        # 9. PDF erzeugen und öffnen
        try:
            doc.build(elements)
            os.startfile(filename)
        except Exception as ex:
            messagebox.showerror("Drucken", f"Fehler beim Erstellen des Berichts: {ex}")


        def print_history(self):
            # … dein bestehender print_history-Code …
            try:
                doc.build(elements)
                os.startfile(filename)
            except Exception as ex:
                messagebox.showerror("Drucken", f"Fehler beim Erstellen des Berichts: {ex}")

    def quick_print(self):
        mech = self.filter_mechanic.get()

        # 1) Alle History-Einträge laden und nach Filter (Mechaniker + optional Datum) selektieren
        all_hist = load_history_entries()
        filtered = [
            e for e in all_hist
            if (not mech or e.mechanic == mech)
               and (not self.filter_date.get() or e.start.date().isoformat() == self.filter_date.get())
        ]
        if not filtered:
            messagebox.showinfo("Schnelldruck", "Keine Einträge zum Drucken gefunden.")
            return

        # 2) Neueste Einträge zuerst
        filtered.reverse()

        # 3) Gruppieren nach Auftrag (um später Subtotals pro Auftrag anzuzeigen)
        grouped: dict[str, list[Entry]] = {}
        for e in filtered:
            grouped.setdefault(e.job_number, []).append(e)

        # 4) PDF vorbereiten
        filename = os.path.join(os.getcwd(), "bericht.pdf")
        doc = SimpleDocTemplate(filename, pagesize=A4)
        styles = getSampleStyleSheet()
        elements: list = []
        bold = ParagraphStyle("Bold", parent=styles["Normal"], fontName="Helvetica-Bold")

        # **Nur Mechaniker im Header** (kein Datum, kein Auftrag)
        if mech:
            elements.append(Paragraph(f"Mechaniker: {mech}", bold))
        elements.append(Spacer(1, 12))

        # 5) Tabellenkopf
        data = [["ID", "Kodex", "Mechaniker", "Auftrag", "Start", "Stop", "Dauer"]]

        # 6) Einträge pro Auftrag + Subtotals
        for job_num, entries in grouped.items():
            for e in entries:
                data.append([
                    str(e.id),
                    e.kodex,
                    e.mechanic,
                    e.job_number,
                    e.start.strftime("%d-%m-%Y %H:%M"),
                    e.stop.strftime("%d-%m-%Y %H:%M"),
                    format_duration(e.duration)
                ])
            # Subtotals nur, wenn mehrere Mechaniker an demselben Auftrag arbeiten
            mech_sum: dict[str, float] = {}
            for e in entries:
                mech_sum.setdefault(e.mechanic, 0)
                if e.duration:
                    mech_sum[e.mechanic] += e.duration.total_seconds()
            if len(mech_sum) > 1:
                data.append(["", "", "", "Subtotals", "", "", ""])
                for m, secs in mech_sum.items():
                    td = timedelta(seconds=int(secs))
                    data.append(["", "", m, "", "", "", format_duration(td)])
                data.append([""] * 7)

        # 7) Gesamtzeit (alle gefilterten Einträge)
        total_secs = sum(e.duration.total_seconds() for e in filtered if e.duration)
        total_td = timedelta(seconds=int(total_secs))
        data.append(["", "", "", "Gesamt", "", "", format_duration(total_td)])

        # 8) Tabelle formatieren und in PDF aufnehmen
        table = Table(data, repeatRows=1)
        tbl_style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME",   (3, len(data) - 1), (3, len(data) - 1), "Helvetica-Bold"),
            ("FONTNAME",   (6, len(data) - 1), (6, len(data) - 1), "Helvetica-Bold"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ])
        table.setStyle(tbl_style)
        elements.append(table)

        # 9) PDF bauen und an Standard-Drucker senden
        doc.build(elements)
        try:
            os.startfile(filename, "print")
        except Exception as ex:
            messagebox.showerror("Schnelldruck", f"Fehler beim Schnell-Druck: {ex}")




    def clear_database(self):
        if not self.is_admin: return
        if messagebox.askyesno("Admin","Alle Einträge löschen? Dies ist unwiderruflich."):
            conn=sqlite3.connect(DB_NAME);conn.execute('DELETE FROM entries');conn.commit();conn.close()
            messagebox.showinfo("Admin","Datenbank geleert.")
            self.load_active();self.apply_filters()

if __name__=='__main__':
    app=TimeTrackerApp();app.mainloop()
