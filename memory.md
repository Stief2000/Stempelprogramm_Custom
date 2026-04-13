# Project Memory

## Zweck

Dieses Projekt ist ein Python-basiertes Stempel- und Zeiterfassungssystem mit Tkinter-Oberflaeche, SQLite-Datenbank, PDF-Berichten und Druckfunktion.

## Aktueller Stand

- Die urspruengliche funktionierende Version liegt in `Arbeitsstunden_Werkstatt_Brixen_NEWNEW.py`.
- Die modernisierte und visuell ueberarbeitete Version liegt in `Arbeitsstunden_Werkstatt_Brixen_REDESIGN.py`.
- Die Redesign-Version soll funktional gleich bleiben, aber optisch moderner und allgemeiner einsetzbar sein.

## Wichtige Entscheidungen

- Die Originaldatei wurde nicht ueberschrieben.
- Neue GUI-Arbeiten passieren in separaten Dateien.
- Die aktuelle Designrichtung ist blau-grau, technisch und etwas industrieller.
- Sichtbare Begriffe wurden verallgemeinert, damit die Anwendung auch ausserhalb der Werkstatt einsetzbar ist.

## Wichtige Dateien

- `Arbeitsstunden_Werkstatt_Brixen_REDESIGN.py`
  Aktuelle Hauptdatei fuer die neue Oberflaeche.
- `Arbeitsstunden_Werkstatt_Brixen_NEWNEW.py`
  Referenz fuer die bestehende Logik und das bisherige Verhalten.
- `time_entries.db`
  SQLite-Datenbank mit den Zeiteintraegen.
- `requirements.txt`
  Python-Abhaengigkeiten.
- `.gitignore`
  Schliesst Build-Artefakte und temporaere Dateien aus.
- `README.md`
  Kurzbeschreibung und Setup.

## Abhaengigkeiten

- `tkcalendar==1.6.1`
- `reportlab==4.4.0`
- `pywin32==310`

## GitHub

- Repository: `https://github.com/Stief2000/Stempelprogramm_Custom`
- Standard-Branch: `main`

## Start auf neuem PC

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python Arbeitsstunden_Werkstatt_Brixen_REDESIGN.py
```

## Hinweise fuer spaetere Arbeit

- Bei weiteren GUI-Anpassungen soll die bestehende Funktionalitaet erhalten bleiben.
- Vor groesseren UI-Aenderungen immer die Redesign-Datei statt der Altdatei erweitern.
- Falls spaeter ein produktiver Rollout geplant ist, kann man die Logik noch staerker von der GUI trennen.
