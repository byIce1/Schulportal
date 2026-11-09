from flask import Flask
import subprocess
import json
import os
import html
from datetime import datetime
import requests  # Add this line
from bs4 import BeautifulSoup  # Add this line

app = Flask(__name__)

DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]

TIMES = {
    1: "07:50 - 08:35",
    2: "08:35 - 09:20",
    3: "09:40 - 10:25",
    4: "10:25 - 11:10",
    5: "11:30 - 12:15",
    6: "12:15 - 13:00",
    7: "13:10 - 13:55",
    8: "13:55 - 14:40",
    9: "14:40 - 15:25",
}

def load(command):
    try:
        result = subprocess.run(
            ["lanis", "--format", "json", command],
            capture_output=True, text=True, env=os.environ
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"load {command} failed: {e}")
        return None

def esc(x):
    return html.escape(str(x) if x is not None else "")

def fetch_vertretungsplan():
    """Fetch the Vertretungsplan from DSBmobile."""
    url = "https://dsbmobile.de/Default.aspx#/menu=0&item=0"  # Your provided link
    try:
        response = requests.get(url)

        if response.status_code != 200:
            print("Error fetching data")
            return []

        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find("table")  # Adjust the selector based on the actual structure

        vertretungsplan = []
        
        for row in table.find_all("tr")[1:]:  # Skip the header row
            cols = row.find_all("td")
            if len(cols) > 0:
                time_slot = cols[0].text.strip()  # Customize according to actual HTML tags
                subject = cols[1].text.strip()
                room = cols[2].text.strip()
                vertretungsplan.append({"time_slot": time_slot, "subject": subject, "room": room})
        
        return vertretungsplan
    except Exception as e:
        print(f"Error fetching vertretungsplan: {e}")
        return []

def get_week_type():
    """Determine if the current week is odd (U) or even (G)."""
    week_number = datetime.now().isocalendar()[1]
    return "U" if week_number % 2 != 0 else "G"


def parse_date_str(s):
    s = str(s).strip()
    # versucht YYYY-MM-DD, DD.MM.YYYY, YYYY/MM/DD
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except:
            pass
    return None

def parse_sub_days(subs_data):
    # Ziel: Liste von {"date": date, "date_str": "...", "entries": [...], "infos": [...]}
    if not subs_data:
        return []
    raw_days = []
    if isinstance(subs_data, list):
        # entweder Liste von Tagen oder Liste von einzelnen Vertretungen
        if subs_data and isinstance(subs_data[0], dict) and any(k in subs_data[0] for k in ("date","datum","day","tag","entries","eintraege")):
            # prüfen ob es Tages-Objekte sind
            if any("entries" in d or "eintraege" in d or "vertretungen" in d for d in subs_data):
                raw_days = subs_data
            else:
                # flache Eintragsliste -> nach Datum gruppieren
                grouped = {}
                for e in subs_data:
                    ds = e.get("date") or e.get("datum") or e.get("tag") or e.get("day") or ""
                    grouped.setdefault(str(ds), []).append(e)
                for ds, lst in grouped.items():
                    raw_days.append({"date": ds, "datum": ds, "entries": lst})
        else:
            raw_days = subs_data
    elif isinstance(subs_data, dict):
        for key in ("days","Dates","dates","substitutions","vertretungen","tage","data"):
            if key in subs_data and isinstance(subs_data[key], list):
                raw_days = subs_data[key]
                break
        if not raw_days:
            # evtl dict Datum -> Liste
            is_date_map = False
            for k, v in subs_data.items():
                if parse_date_str(k) and isinstance(v, (list, dict)):
                    is_date_map = True
                    break
            if is_date_map:
                for k, v in subs_data.items():
                    d = parse_date_str(k)
                    if d:
                        ent = v if isinstance(v, list) else v.get("entries", v.get("vertretungen", []))
                        raw_days.append({"date": k, "entries": ent})
            else:
                # einzelner Tag?
                if "entries" in subs_data or "vertretungen" in subs_data:
                    raw_days = [subs_data]

    out = []
    for d in raw_days:
        if not isinstance(d, dict):
            continue
        ds = d.get("date") or d.get("datum") or d.get("day") or d.get("tag") or d.get("Datum") or ""
        entries = d.get("entries") or d.get("eintraege") or d.get("vertretungen") or d.get("substitutions") or []
        infos = d.get("infos") or d.get("info") or d.get("informationen") or d.get("notes") or []
        if isinstance(entries, dict):
            entries = [entries]
        dt = parse_date_str(ds) if ds else None
        # fallback: Datum aus erstem Eintrag
        if not dt and entries:
            for e in entries:
                if isinstance(e, dict):
                    for k in ("date","datum","tag","day"):
                        if k in e:
                            dt = parse_date_str(e[k])
                            if dt:
                                ds = e[k]
                                break
                if dt:
                    break
        if not dt:
            continue
        out.append({"date": dt, "date_str": dt.strftime("%d.%m.%Y"), "weekday": dt.strftime("%A"), "entries": entries if isinstance(entries, list) else [], "infos": infos, "raw": d})
    # sortieren nach Datum
    out = sorted(out, key=lambda x: x["date"])
    # Duplikate pro Datum mergen
    merged = {}
    for x in out:
        if x["date"] not in merged:
            merged[x["date"]] = x
        else:
            merged[x["date"]]["entries"].extend(x["entries"])
    return sorted(merged.values(), key=lambda x: x["date"])

def pick_two_days(days_sorted, today):
    # days_sorted: aufsteigend sortiert
    # Regel: erster Tag >= heute finden. Wenn == heute: heute + nächster. Wenn > heute: letzter davor + dieser.
    if not days_sorted:
        return []
    future_idx = None
    for i, d in enumerate(days_sorted):
        if d["date"] >= today:
            future_idx = i
            break
    if future_idx is None:
        # alles Vergangenheit -> letzte 2
        return days_sorted[-2:]
    if days_sorted[future_idx]["date"] == today:
        return days_sorted[future_idx:future_idx+2]
    else:
        # nächster liegt in Zukunft -> letzter davor + nächster
        if future_idx == 0:
            return days_sorted[0:2]
        return days_sorted[future_idx-1:future_idx+1]

@app.route("/")
def index():
    """Render the main page with the timetable."""
    today_date = datetime.now().strftime("%d.%m.%Y")  # Get today's date
    week_type = get_week_type()  # Determine the week type (odd/even)

    # Fetch tasks and substitutions
    tasks_data = load("tasks") or {}
    subs_data = load("substitutions")
    tasks = tasks_data.get("tasks", []) if isinstance(tasks_data, dict) else []
    tasks = sorted(tasks, key=lambda t: t.get("date", ""))

    # Define the timetable structure based on the current week
    PLAN = {
        # Monday
        (1, "Montag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
        (2, "Montag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
        (3, "Montag"): [],  # Frei
        (4, "Montag"): [{"s": "E", "r": "102", "t": "BOM"}],
        (5, "Montag"): [{"s": "Ph", "r": "329", "t": "SU"}],
        (6, "Montag"): [],  # Frei
        (8, "Montag"): [{"s": "D" if week_type == "U" else "M", "r": "", "t": ""}],  # 8th hour
        (9, "Montag"): [{"s": "D" if week_type == "U" else "M", "r": "", "t": ""}],  # 9th hour

        # Tuesday
        (1, "Dienstag"): [{"s": "F", "r": "104", "t": "HB"}],
        (2, "Dienstag"): [{"s": "F", "r": "104", "t": "HB"}],
        (3, "Dienstag"): [{"s": "Bio", "r": "310", "t": "LW"}],
        (4, "Dienstag"): [{"s": "Bio", "r": "310", "t": "LW"}],
        (5, "Dienstag"): [{"s": "Rev", "r": "137", "t": "PW"}],
        (6, "Dienstag"): [{"s": "Rev", "r": "137", "t": "PW"}],
        (7, "Dienstag"): [{"s": "Rev", "r": "137", "t": "PW"}],
        (8, "Dienstag"): [],  # Frei
        
        # Wednesday
        (1, "Mittwoch"): [{"s": "D", "r": "131", "t": "SI"}],
        (2, "Mittwoch"): [{"s": "D", "r": "131", "t": "SI"}],
        (3, "Mittwoch"): [{"s": "G", "r": "231", "t": "JK"}],
        (4, "Mittwoch"): [{"s": "G", "r": "134", "t": "JK"}],
        (5, "Mittwoch"): [{"s": "Ph", "r": "329", "t": "SU"}],
        (6, "Mittwoch"): [{"s": "Ph", "r": "329", "t": "SU"}],
        (7, "Mittwoch"): [],  # Frei
        (8, "Mittwoch"): [{"s": "Spo", "r": "KS1", "t": "CV"}],
        (9, "Mittwoch"): [{"s": "Spo", "r": "KS1", "t": "CV"}],

        # Thursday
        (1, "Donnerstag"): [{"s": "E", "r": "105", "t": "JK"}],
        (2, "Donnerstag"): [{"s": "E", "r": "102", "t": "BOM"}],
        (3, "Donnerstag"): [{"s": "M", "r": "134", "t": "SU"}],
        (4, "Donnerstag"): [{"s": "M", "r": "134", "t": "SU"}],
        (5, "Donnerstag"): [{"s": "Bio", "r": "310", "t": "LW"}],
        (6, "Donnerstag"): [{"s": "F", "r": "104", "t": "HB"}],
        (7, "Donnerstag"): [],  # Frei
        (8, "Donnerstag"): [{"s": "DS", "r": "161", "t": "MJ"}],
        (9, "Donnerstag"): [{"s": "DS", "r": "161", "t": "MJ"}],

        # Friday
        (1, "Freitag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
        (2, "Freitag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
        (3, "Freitag"): [{"s": "M", "r": "134", "t": "SU"}],
        (4, "Freitag"): [{"s": "D", "r": "131", "t": "SI"}],
    }

    # Build the HTML response for the main page
    h = f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body.light {{ background: #f5f6fa; color: #222; }}
            body.light table {{ background: white; }}
            body.light th {{ background: #2f3b52; color: white; }}
            body.light td.time {{ background: #eef1f6; }}
            body.dark {{ background: #121212; color: #e0e0e0; }}
            body.dark table {{ background: #1a1a1a; color: #e0e0e0; }}
            body.dark th {{ background: #21252b; color: white; }}
            body.dark th, body.dark td {{ border-color: #4b4e54; }}
            body.dark td.time {{ background: #1a1a1a; }}
            body.dark .subj, body.dark .small {{ color: #e0e0e0; }}
            body.dark .card {{ border: 1px solid rgba(255, 255, 255, 0.2); }}
            body.dark .celldiv {{ border-top: none; }}
            body {{ font-family: system-ui, Arial; margin: 20px; transition: background 0.2s; }}
            table {{ border-collapse: collapse; width: 100%; min-width: 750px; }}
            th, td {{ border: 1px solid #555; padding: 8px; vertical-align: top; text-align: left; }}
            .subj {{ font-weight: bold; }}
            .small {{ font-size: 12px; }}
            .card {{ border-radius: 8px; padding: 10px; margin: 8px 0; border: 1px solid #ddd; }}
        </style>
    </head>
    <body class="dark">
        <button id="themeBtn" onclick="toggleTheme()">☀️ Light</button>
        <h1>Mein Schulportal</h1>
        <p>{today_date}: Diese Woche ist eine {week_type}-Woche.</p>
        <h2>Stundenplan</h2>
        <div style="overflow-x:auto">
            <table>
                <tr><th>Stunde</th>
    """
    
    for d in DAYS:
        h += f"<th>{d}</th>"
    h += "</tr>"

    # Build rows 1-9
    for hn in range(1, 10):
        h += f"<tr><td class='time'>{hn}. Stunde<br>{TIMES[hn]}</td>"
        for d in DAYS:
            cell = PLAN.get((hn, d), [])
            if not cell:
                h += "<td></td>"
            else:
                h += "<td>"
                for e in cell:
                    h += f"<div><div class='subj'>{esc(e['s'])} {esc(e['r'])}</div><div class='small'>{esc(e['t'])}</div></div>"
                h += "</td>"
        h += "</tr>"
    
    h += "</table></div>"
    h += f"<h2>Aufgaben ({len(tasks)})</h2>"
    for t in tasks[:20]:
        h += f"<div class='card'><b>{esc(t.get('title',''))}</b> <span class='small'>{esc(t.get('date',''))} • {esc(t.get('subject_name',''))}</span></div>"

    h += "<h2>Vertretungen</h2>"
    if not subs_data:
        h += "<p>Keine Vertretungen.</p>"
    else:
        h += f"<div class='card'><pre>{esc(json.dumps(subs_data, indent=2, ensure_ascii=False)[:4000])}</pre></div>"

    h += """
    <script>
      function applyTheme(theme) {
        document.body.classList.remove('dark','light');
        document.body.classList.add(theme);
        document.getElementById('themeBtn').textContent = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
        localStorage.setItem('theme', theme);
      }
      function toggleTheme() {
        const cur = document.body.classList.contains('dark') ? 'dark' : 'light';
        applyTheme(cur === 'dark' ? 'light' : 'dark');
      }
      applyTheme(localStorage.getItem('theme') || 'dark');
    </script></body></html>
    """
    return h

if __name__ == "__main__":
    app.run(debug=True)
