from flask import Flask
import subprocess, json, os, html

app = Flask(__name__)

DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]

# Bell times taken from your screenshot
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

# Personal timetable from your screenshot.
PLAN = {
    (1, "Montag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
    (2, "Montag"): [{"s": "Wiwi", "r": "237", "t": "MC"}],
    (4, "Montag"): [{"s": "E", "r": "102", "t": "BOM"}],
    (5, "Montag"): [{"s": "Ph", "r": "329", "t": "SU"}],
    (8, "Montag"): [{"s": "D", "r": "132", "t": "SI", "badge": "U"}],
    (9, "Montag"): [{"s": "M", "r": "134", "t": "SU", "badge": "G"}],
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

def load(command):
    # Run lanis CLI for live tasks / substitutions only.
    result = subprocess.run(
        ["lanis", "--format", "json", command],
        capture_output=True, text=True, env=os.environ
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except:
        return None

def esc(x):
    return html.escape(str(x) if x is not None else "")

@app.route("/")
def index():
    # Load live tasks, sorted by date.
    tasks_data = load("tasks") or {}
    subs_data = load("substitutions")
    tasks = tasks_data.get("tasks", []) if isinstance(tasks_data, dict) else []
    tasks = sorted(tasks, key=lambda t: t.get("date", ""))

    # HTML with neutral dark theme, modified task outline color.
    h = """
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            /* Light theme styles */
            body.light { background: #f5f6fa; color: #222; }
            body.light table { background: white; }
            body.light th { background: #2f3b52; color: white; }
            body.light td.time { background: #eef1f6; }
            /* Dark theme styles */
            body.dark { background: #181c24; color: #e0e0e0; }
            body.dark table { background: #282c34; color: #e0e0e0; }
            body.dark th { background: #21252b; color: white; }
            body.dark th, body.dark td { border-color: #4b4e54; }
            body.dark td.time { background: #21252b; }
            body.dark .subj, body.dark .small { color: #e0e0e0; }
            body.dark .card { border: 1px solid rgba(255, 255, 255, 0.2); } /* Adjusted to darker */
            body.dark .celldiv { border-top: 1px solid rgba(255, 255, 255, 0.2); } /* Adjusted to darker */
            body { font-family: system-ui, Arial; margin: 20px; transition: background 0.2s; }
            table { border-collapse: collapse; width: 100%; min-width: 750px; }
            th, td { border: 1px solid #ddd; padding: 8px; vertical-align: top; text-align: left; }
            .subj { font-weight: bold; }
            .small { font-size: 12px; }
            .celldiv { margin-top: 4px; }
            .celldiv:first-child { margin-top: 0; }
            .badge-U { background: #22c55e; color: white; border-radius: 10px; padding: 0 6px; font-size: 11px; }
            .badge-G { background: #6b7280; color: white; border-radius: 10px; padding: 0 6px; font-size: 11px; }
            .card { border-radius: 8px; padding: 10px; margin: 8px 0; }
        </style>
    </head>
    <body class="dark">
        <button id="themeBtn" onclick="toggleTheme()">☀️ Light</button>
        <h1>Mein Schulportal</h1>
        <p>08.11.2026: Diese Woche ist eine U-Woche.</p>
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
                    badge = f" <span class='badge-{e['badge']}'>{e['badge']}</span>" if "badge" in e else ""
                    h += f"<div class='celldiv'><div class='subj'>{esc(e['s'])} {esc(e['r'])}{badge}</div><div class='small'>{esc(e['t'])}</div></div>"
                h += "</td>"
        h += "</tr>"
    h += "</table></div>"
    h += f"<h2>Aufgaben ({len(tasks)})</h2>"
    for t in tasks[:20]:
        h += f"<div class='card'><b>{esc(t.get('title',''))}</b> <span class='small'>{esc(t.get('date',''))} • {esc(t.get('subject_name',''))}</span></div>"
    
    h += "<h2>Vertretungen</h2>"
    if not subs_data:
        h += "<p>Keine Vertretungen - am Sonntag normal.</p>"
    else:
        h += f"<div class='card'><pre>{esc(json.dumps(subs_data, indent=2, ensure_ascii=False)[:4000])}</pre></div>"

    h += """
    <script>
      function applyTheme(theme) {
        document.body.classList.remove('dark', 'light');
        document.body.classList.add(theme);
        document.getElementById('themeBtn').textContent = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
        localStorage.setItem('theme', theme);
      }
      function toggleTheme() {
        const cur = document.body.classList.contains('dark') ? 'dark' : 'light';
        applyTheme(cur === 'dark' ? 'light' : 'dark');
      }
      // On load: use saved choice, otherwise dark.
      applyTheme(localStorage.getItem('theme') || 'dark');
    </script>
    </body>
    </html>
    """
    return h

if __name__ == "__main__":
    app.run(debug=True)
