# Stempelprogramm Custom

Python-Anwendung zur Zeiterfassung mit Tkinter-Oberflaeche, SQLite-Datenbank, PDF-Berichten und Druckfunktion.

## Enthalten

- Mehrere Entwicklungsstaende als `.py`-Dateien
- PyInstaller-`.spec`-Dateien
- Neue Redesign-Variante in `Arbeitsstunden_Werkstatt_Brixen_REDESIGN.py`

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python Arbeitsstunden_Werkstatt_Brixen_REDESIGN.py
```

## Hinweis

Die Datei `time_entries.db` enthaelt die SQLite-Datenbank der Anwendung.
