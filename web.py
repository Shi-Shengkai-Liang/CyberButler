from flask import Flask, jsonify, request, render_template_string, session, redirect
from functools import wraps
import json
import os
import subprocess

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "cyberbutler-secret-change-me")
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "cyberbutler2026")
DATA_FILE = os.environ.get("DATA_FILE", os.path.join(os.path.dirname(__file__), "tasks.json"))
SCAN_SCRIPT = os.path.join(os.path.dirname(__file__), "scan_to_json.py")

def load_tasks():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE) as f:
        return json.load(f)

def save_tasks(tasks):
    with open(DATA_FILE, "w") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CyberButler</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, sans-serif; background: #f5f5f5; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
.card { background: white; border-radius: 16px; padding: 2rem; width: 320px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
h1 { font-size: 20px; font-weight: 600; margin-bottom: 8px; color: #1a73e8; }
p { font-size: 13px; color: #888; margin-bottom: 1.5rem; }
input { width: 100%; padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; font-size: 15px; margin-bottom: 1rem; }
button { width: 100%; padding: 11px; background: #1a73e8; color: white; border: none; border-radius: 8px; font-size: 15px; cursor: pointer; }
.error { color: #d93025; font-size: 13px; margin-bottom: 1rem; }
</style>
</head>
<body>
<div class="card">
  <h1>CyberButler</h1>
  <p>请输入密码访问作业列表</p>
  {% if error %}<div class="error">密码错误，请重试</div>{% endif %}
  <form method="post">
    <input type="password" name="password" placeholder="密码" autofocus>
    <button type="submit">登录</button>
  </form>
</div>
</body>
</html>
"""

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CyberButler</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, sans-serif; background: #f5f5f5; color: #333; }
.header { background: #1a73e8; color: white; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 10; }
.header h1 { font-size: 18px; font-weight: 500; }
.header-btns { display: flex; gap: 8px; }
.refresh-btn { background: rgba(255,255,255,0.2); border: none; color: white; padding: 8px 16px; border-radius: 20px; font-size: 14px; cursor: pointer; }
.refresh-btn:active { background: rgba(255,255,255,0.3); }
.course-filters { display: flex; gap: 6px; flex-wrap: wrap; margin: 12px; }
.cf { padding: 6px 12px; font-size: 12px; border-radius: 20px; border: 1px solid #ddd; cursor: pointer; background: white; color: #666; }
.cf.active { background: #1a73e8; color: white; border-color: #1a73e8; }
.stats { background: white; margin: 12px; border-radius: 12px; padding: 14px 16px; display: flex; gap: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.stat { text-align: center; flex: 1; }
.stat-num { font-size: 24px; font-weight: 600; color: #1a73e8; }
.stat-label { font-size: 11px; color: #888; margin-top: 2px; }
.section { margin: 12px; }
.section-title { font-size: 12px; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; padding-left: 4px; }
.task { background: white; border-radius: 12px; padding: 14px 16px; margin-bottom: 8px; display: flex; align-items: flex-start; gap: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); cursor: pointer; }
.task.done { opacity: 0.4; }
.task.done .task-title { text-decoration: line-through; }
.check { width: 22px; height: 22px; border-radius: 50%; border: 2px solid #ddd; flex-shrink: 0; margin-top: 2px; display: flex; align-items: center; justify-content: center; }
.task.done .check { background: #34a853; border-color: #34a853; color: white; font-size: 12px; }
.task-info { flex: 1; }
.task-title { font-size: 15px; font-weight: 500; margin-bottom: 4px; }
.task-meta { font-size: 12px; color: #888; display: flex; gap: 8px; flex-wrap: wrap; }
.badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.badge-assign { background: #e8f0fe; color: #1a73e8; }
.badge-quiz { background: #fce8e6; color: #d93025; }
.badge-exam { background: #fef3e2; color: #f09300; }
.badge-other { background: #f1f3f4; color: #666; }
.due-urgent { color: #d93025; font-weight: 600; }
.due-soon { color: #f09300; font-weight: 500; }
.due-normal { color: #666; }
.no-deadline { color: #999; font-style: italic; }
.source-tag { font-size: 11px; color: #aaa; }
.empty { text-align: center; padding: 40px 20px; color: #999; font-size: 14px; }
.scanning { text-align: center; padding: 20px; color: #1a73e8; font-size: 14px; }
</style>
</head>
<body>
<div class="header">
  <h1>CyberButler</h1>
  <div class="header-btns">
    <button class="refresh-btn" onclick="triggerScan()">Refresh</button>
    <button class="refresh-btn" onclick="location.href='/logout'">Logout</button>
  </div>
</div>
<div class="course-filters" id="course-filters"></div>
<div id="app"></div>
<script>
let tasks = [];
let activeCourse = "all";

function buildCourseFilters() {
  const courses = ["all", ...new Set(tasks.map(t => t.course).filter(Boolean))];
  const container = document.getElementById("course-filters");
  container.innerHTML = courses.map(c =>
    `<button class="cf ${activeCourse === c ? "active" : ""}" onclick="setCourse('${c.replace(/'/g, "\\'")}')">${c === "all" ? "All" : c}</button>`
  ).join("");
}

function setCourse(c) {
  activeCourse = c;
  buildCourseFilters();
  render();
}

async function load() {
  const r = await fetch('/api/tasks');
  tasks = await r.json();
  buildCourseFilters();
  render();
}

async function triggerScan() {
  document.getElementById('app').innerHTML = '<div class="scanning">Scanning Moodle & Gradescope...</div>';
  await fetch('/api/scan', {method: 'POST'});
  await load();
}

async function toggleTask(idx) {
  await fetch('/api/toggle/' + idx, {method: 'POST'});
  await load();
}

function dueClass(due_ts) {
  if (!due_ts || due_ts > 9000000000) return 'no-deadline';
  const diff = due_ts * 1000 - Date.now();
  if (diff < 0) return 'due-urgent';
  if (diff < 86400000) return 'due-urgent';
  if (diff < 259200000) return 'due-soon';
  return 'due-normal';
}

function render() {
  const now = Date.now();
  const filtered = activeCourse === "all" ? tasks : tasks.filter(t => t.course === activeCourse);
  const pending = filtered.filter(t => !t.done);
  const done = filtered.filter(t => t.done);
  const urgent = pending.filter(t => t.due_ts && t.due_ts < 9000000000 && (t.due_ts * 1000 - now) < 86400000);
  const upcoming = pending.filter(t => t.due_ts && t.due_ts < 9000000000 && (t.due_ts * 1000 - now) >= 86400000);
  const noDue = pending.filter(t => !t.due_ts || t.due_ts >= 9000000000);

  let html = '';
  html += '<div class="stats">';
  html += `<div class="stat"><div class="stat-num">${pending.length}</div><div class="stat-label">Pending</div></div>`;
  html += `<div class="stat"><div class="stat-num" style="color:#d93025">${urgent.length}</div><div class="stat-label">Urgent</div></div>`;
  html += `<div class="stat"><div class="stat-num" style="color:#34a853">${done.length}</div><div class="stat-label">Done</div></div>`;
  html += '</div>';

  function renderTask(t, idx) {
    const badge = 'badge-' + (t.type || 'other');
    const dc = dueClass(t.due_ts);
    const dueText = t.due || 'No deadline';
    const showSource = t.source && (t.source.startsWith('page:') || t.source.startsWith('file:') || t.source.startsWith('label:'));
    return `<div class="task ${t.done ? 'done' : ''}" onclick="toggleTask(${idx})">
      <div class="check">${t.done ? '✓' : ''}</div>
      <div class="task-info">
        <div class="task-title">${t.title}</div>
        <div class="task-meta">
          <span class="badge ${badge}">${t.type || 'other'}</span>
          <span>${t.course || ''}</span>
          <span class="${dc}">${dueText}</span>
        </div>
        ${showSource ? `<div class="source-tag">from ${t.source}</div>` : ''}
      </div>
    </div>`;
  }

  if (urgent.length > 0) {
    html += '<div class="section"><div class="section-title">Due soon</div>';
    urgent.forEach(t => { html += renderTask(t, tasks.indexOf(t)); });
    html += '</div>';
  }
  if (upcoming.length > 0) {
    html += '<div class="section"><div class="section-title">Upcoming</div>';
    upcoming.forEach(t => { html += renderTask(t, tasks.indexOf(t)); });
    html += '</div>';
  }
  if (noDue.length > 0) {
    html += '<div class="section"><div class="section-title">No deadline set</div>';
    noDue.forEach(t => { html += renderTask(t, tasks.indexOf(t)); });
    html += '</div>';
  }
  if (done.length > 0) {
    html += '<div class="section"><div class="section-title">Completed</div>';
    done.forEach(t => { html += renderTask(t, tasks.indexOf(t)); });
    html += '</div>';
  }
  if (tasks.length === 0) {
    html += '<div class="empty">No tasks found.<br>Tap Refresh to scan.</div>';
  }

  document.getElementById('app').innerHTML = html;
}

load();
</script>
</body>
</html>
"""

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == WEB_PASSWORD:
            session["logged_in"] = True
            return redirect("/")
        return render_template_string(LOGIN_HTML, error=True)
    return render_template_string(LOGIN_HTML, error=False)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
@login_required
def index():
    return render_template_string(HTML)

@app.route("/api/tasks")
@login_required
def get_tasks():
    return jsonify(load_tasks())

@app.route("/api/toggle/<int:idx>", methods=["POST"])
@login_required
def toggle(idx):
    tasks = load_tasks()
    if 0 <= idx < len(tasks):
        tasks[idx]["done"] = not tasks[idx].get("done", False)
        save_tasks(tasks)
    return jsonify({"ok": True})

@app.route("/api/scan", methods=["POST"])
@login_required
def scan():
    subprocess.Popen(["python3", SCAN_SCRIPT])
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
