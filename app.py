from flask import Flask
import subprocess, json, os, html
from datetime import datetime, date

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

def get_week_type():
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
    today_date = datetime.now().strftime("%d.%m.%Y")
    today = date.today()
    week_type = get_week_type()

    PLAN = {
        (1, "Montag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
        (2, "Montag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
        (4, "Montag"): [{"s": "E", "r": "102", "t": "BOM"}],
        (5, "Montag"): [{"s": "Ph", "r": "329", "t": "SU"}],
        (8, "Montag"): [{"s": "D" if week_type == "U" else "M", "r": "", "t": ""}],
        (9, "Montag"): [{"s": "D" if week_type == "U" else "M", "r": "", "t": ""}],
        (1, "Dienstag"): [{"s": "F", "r": "104", "t": "HB"}],
        (2, "Dienstag"): [{"s": "F", "r": "104", "t": "HB"}],
        (3, "Dienstag"): [{"s": "Bio", "r": "310", "t": "LW"}],
        (4, "Dienstag"): [{"s": "Bio", "r": "310", "t": "LW"}],
        (5, "Dienstag"): [{"s": "Rev", "r": "137", "t": "PW"}],
        (6, "Dienstag"): [{"s": "Rev", "r": "137", "t": "PW"}],
        (7, "Dienstag"): [{"s": "Rev", "r": "137", "t": "PW"}],
        (1, "Mittwoch"): [{"s": "D", "r": "131", "t": "SI"}],
        (2, "Mittwoch"): [{"s": "D", "r": "131", "t": "SI"}],
        (3, "Mittwoch"): [{"s": "G", "r": "231", "t": "JK"}],
        (4, "Mittwoch"): [{"s": "G", "r": "134", "t": "JK"}],
        (5, "Mittwoch"): [{"s": "Ph", "r": "329", "t": "SU"}],
        (6, "Mittwoch"): [{"s": "Ph", "r": "329", "t": "SU"}],
        (8, "Mittwoch"): [{"s": "Spo", "r": "KS1", "t": "CV"}],
        (9, "Mittwoch"): [{"s": "Spo", "r": "KS1", "t": "CV"}],
        (1, "Donnerstag"): [{"s": "E", "r": "105", "t": "JK"}],
        (2, "Donnerstag"): [{"s": "E", "r": "102", "t": "BOM"}],
        (3, "Donnerstag"): [{"s": "M", "r": "134", "t": "SU"}],
        (4, "Donnerstag"): [{"s": "M", "r": "134", "t": "SU"}],
        (5, "Donnerstag"): [{"s": "Bio", "r": "310", "t": "LW"}],
        (6, "Donnerstag"): [{"s": "F", "r": "104", "t": "HB"}],
        (8, "Donnerstag"): [{"s": "DS", "r": "161", "t": "MJ"}],
        (9, "Donnerstag"): [{"s": "DS", "r": "161", "t": "MJ"}],
        (1, "Freitag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
        (2, "Freitag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
        (3, "Freitag"): [{"s": "M", "r": "134", "t": "SU"}],
        (4, "Freitag"): [{"s": "D", "r": "131", "t": "SI"}],
    }

    tasks_data = load("tasks") or {}
    subs_data = load("substitutions")
    tasks = tasks_data.get("tasks", []) if isinstance(tasks_data, dict) else []
    tasks = sorted(tasks, key=lambda t: t.get("date", ""))

    sub_days = parse_sub_days(subs_data)
    two = pick_two_days(sub_days, today)

    h = f"""
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
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
      body.dark .card {{ border: 1px solid rgba(255,255,255,0.2); background: #1a1a1a; }}
      body {{ font-family: system-ui, Arial; margin: 20px; }}
      table {{ border-collapse: collapse; width: 100%; min-width: 750px; }}
      th, td {{ border: 1px solid #555; padding: 8px; vertical-align: top; text-align: left; }}
      .subj {{ font-weight: bold; }}
      .small {{ font-size: 12px; }}
      .card {{ border-radius: 8px; padding: 10px; margin: 8px 0; border: 1px solid #ddd; background: white; }}
      .pill {{ display:inline-block; padding:2px 8px; border-radius:20px; font-size:12px; background:#333; color:#fff; }}
      .today {{ background:#22c55e !important; }}
    </style></head>
    <body class="dark">
    <button id="themeBtn" onclick="toggleTheme()">Light</button>
    <h1>Mein Schulportal</h1>
    <p>{today_date}: Diese Woche ist eine {week_type}-Woche.</p>
    <h2>Stundenplan</h2>
    <div style="overflow-x:auto"><table><tr><th>Stunde</th>
    """
    for d in DAYS:
        h += f"<th>{d}</th>"
    h += "</tr>"
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

    # Vertretungen: immer 2 Tage mit Datum
    h += "<h2>Vertretungen (auto, 2 Tage)</h2>"
    if not subs_data:
        h += "<p>Keine Vertretungsdaten. Login abgelaufen oder Wochenende. Aufgaben unten prüfen.</p>"
    elif not sub_days:
        h += f"<div class='card'><b>Format unbekannt.</b><br><span class='small'>Rohdaten:</span><pre>{esc(json.dumps(subs_data, indent=2, ensure_ascii=False)[:3000])}</pre></div>"
    else:
        # Übersicht aller gefundenen Daten zum Abgleich
        all_dates = ", ".join([x['date_str'] for x in sub_days])
        h += f"<p class='small'>Gefunden im Portal: {esc(all_dates)} | Heute: {esc(today_date)}</p>"
        for day in two:
            is_today = " today" if day["date"] == today else ""
            label = "Heute" if day["date"] == today else ("Vergangen / Letzter" if day["date"] < today else "Nächster")
            h += f"<div class='card'><span class='pill{is_today}'>{esc(label)} • {esc(day['date_str'])} • {esc(day['weekday'])}</span>"
            if day["infos"]:
                h += f"<div class='small'>Info: {esc(str(day['infos'])[:500])}</div>"
            if not day["entries"]:
                h += "<div>Nur Infos, keine Vertretungen.</div>"
            else:
                for e in day["entries"]:
                    if not isinstance(e, dict):
                        h += f"<div>• {esc(e)}</div>"
                        continue
                    # flexible Feldnamen
                    subj = e.get("subject") or e.get("fach") or e.get("Subject") or e.get("s") or ""
                    hour = e.get("hour") or e.get("stunde") or e.get("lesson") or ""
                    cls = e.get("class") or e.get("klasse") or ""
                    teacher = e.get("teacher") or e.get("lehrer") or e.get("verteter") or ""
                    room = e.get("room") or e.get("raum") or ""
                    typ = e.get("type") or e.get("art") or e.get("vertretungsart") or ""
                    text = e.get("text") or e.get("bemerkung") or e.get("info") or ""
                    h += f"<div style='margin-top:6px'>• <b>{esc(subj)} {esc(hour)} {esc(cls)}</b> <span class='small'>{esc(typ)} {esc(teacher)} {esc(room)} {esc(text)}</span></div>"
            h += "</div>"

    h += f"<h2>Aufgaben ({len(tasks)})</h2>"
    for t in tasks[:20]:
        h += f"<div class='card'><b>{esc(t.get('title',''))}</b> <span class='small'>{esc(t.get('date',''))} • {esc(t.get('subject_name',''))}</span></div>"

    h += """
    <script>
      function applyTheme(theme) {
        document.body.classList.remove('dark','light');
        document.body.classList.add(theme);
        document.getElementById('themeBtn').textContent = theme === 'dark' ? 'Light' : 'Dark';
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
