import requests
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup

MOODLE_URL = "https://moodle.rose-hulman.edu"
MOODLE_TOKEN = os.environ.get("MOODLE_TOKEN", "")
MOODLE_USER_ID = os.environ.get("MOODLE_USER_ID", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "cyberbutler")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
AI_PROVIDER = os.environ.get("AI_PROVIDER", "anthropic")
GRADESCOPE_EMAIL = os.environ.get("GRADESCOPE_EMAIL", "")
GRADESCOPE_PASSWORD = os.environ.get("GRADESCOPE_PASSWORD", "")
DATA_FILE = os.environ.get("DATA_FILE", os.path.join(os.path.dirname(__file__), "tasks.json"))

GRADESCOPE_COURSES = {
    # 例: "1273436": "ME328 Material Engineering",
}

MANUAL_COURSES = {
    # 例: 122597: "MA223 Statistics",
}

def moodle(func, **params):
    r = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data={
        "wstoken": MOODLE_TOKEN,
        "wsfunction": func,
        "moodlewsrestformat": "json",
        **{k: str(v) for k, v in params.items()}
    })
    return r.json()

def get_current_courses():
    now = datetime.now()
    month, year = now.month, now.year
    if month >= 9:
        season, yr1, yr2 = "Fall", year, year+1
    elif month <= 2:
        season, yr1, yr2 = "Winter", year-1, year
    elif month <= 5:
        season, yr1, yr2 = "Spring", year-1, year
    else:
        season, yr1, yr2 = "Summer", year-1, year
    yr_dash = f"{yr1}-{yr2}"
    yr_short = f"{yr1}-{str(yr2)[2:]}"
    keywords = [
        f"{season} Quarter - {yr_dash}",
        f"{season} Quarter - {yr_short}",
        f"{season} {yr_dash}",
        f"{season} {yr_short}",
        f"({season} {yr_dash})",
        f"({season} {yr_short})",
    ]
    exclude = ["survey", "career", "advising", "enrollment", "polling",
               "resource", "alert", "diversity", "inclusion", "iprop",
               "access", "transition", "esl", "award", "final exam"]
    r = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data={
        "wstoken": MOODLE_TOKEN,
        "wsfunction": "core_enrol_get_users_courses",
        "moodlewsrestformat": "json",
        "userid": MOODLE_USER_ID
    })
    courses = {}
    for c in r.json():
        name = c["fullname"]
        if any(k.lower() in name.lower() for k in keywords):
            if not any(e in name.lower() for e in exclude):
                clean = name
                for suffix in [" Spring Quarter", " Fall Quarter", " Winter Quarter",
                                " Spring 20", " Fall 20", " Winter 20",
                                " (Spring", " (Fall", " (Winter"]:
                    if suffix in clean:
                        clean = clean[:clean.index(suffix)].strip()
                courses[c["id"]] = clean
    courses.update(MANUAL_COURSES)
    return courses

def download_file(url):
    r = requests.get(f"{url}&token={MOODLE_TOKEN}")
    return r.content

def extract_text_from_html(content):
    soup = BeautifulSoup(content, "html.parser")
    return soup.get_text(separator="\n", strip=True)

def extract_text_from_pdf(content):
    import pdfplumber, io
    text = ""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

def extract_text_from_docx(content):
    from docx import Document
    import io
    doc = Document(io.BytesIO(content))
    return "\n".join([p.text for p in doc.paragraphs])

def _parse_ai_response(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    if not text or text == "[]":
        return []
    arrays = re.findall(r'\[.*?\]', text, re.DOTALL)
    if arrays:
        all_items = []
        for arr in arrays:
            try:
                all_items.extend(json.loads(arr))
            except:
                pass
        return all_items
    return json.loads(text)

def _ai_anthropic(prompt):
    if not ANTHROPIC_KEY:
        return []
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return _parse_ai_response(msg.content[0].text)

def _ai_gemini(prompt):
    if not GEMINI_KEY:
        return []
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return _parse_ai_response(response.text)

def _ai_groq(prompt):
    if not GROQ_KEY:
        return []
    from groq import Groq
    client = Groq(api_key=GROQ_KEY)
    msg = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}]
    )
    return _parse_ai_response(msg.choices[0].message.content)

def ai_call(prompt):
    if AI_PROVIDER == "gemini":
        return _ai_gemini(prompt)
    elif AI_PROVIDER == "groq":
        return _ai_groq(prompt)
    else:
        return _ai_anthropic(prompt)

def ai_extract_deadlines(text, source_name, course_name):
    if len(text.strip()) < 10:
        return []
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""Today is {today}. Course: {course_name}. Source: {source_name}.

Extract ALL assignments, quizzes (BQ = Battle Quiz = in-class quiz), exams, projects, homeworks and their deadlines.
Only include future items (after today).
Return JSON array only, no markdown, no other text:
[{{"title": "...", "due": "MM/DD or description", "type": "assign/quiz/exam/other", "notes": "..."}}]
If nothing found, return [].

Text:
{text[:6000]}"""
    try:
        return ai_call(prompt)
    except Exception as e:
        print(f"    AI error: {e}")
        return []

def notify(title, msg, priority="default"):
    try:
        requests.post(f"https://ntfy.sh/{NTFY_TOPIC}",
            data=msg.encode("utf-8"),
            headers={"Title": title.encode("utf-8"), "Priority": priority})
    except:
        pass

def ai_risk_analysis(tasks):
    pending = [t for t in tasks if not t.get("done")]
    if not pending:
        return
    now_ts = datetime.now().timestamp()
    task_list = []
    for t in pending:
        due_ts = t.get("due_ts", 9999999999)
        if due_ts < 9000000000:
            days_left = round((due_ts - now_ts) / 86400, 1)
            task_list.append(f"- [{t.get('type','?')}] {t.get('course','?')}: {t.get('title','?')} (due: {t.get('due','?')}, {days_left} days left, source: {t.get('source','?')})")
        else:
            task_list.append(f"- [{t.get('type','?')}] {t.get('course','?')}: {t.get('title','?')} (no deadline)")
    task_text = "\n".join(task_list[:50])
    today = datetime.now().strftime("%Y-%m-%d %A")
    prompt = f"""Today is {today}. Analyze this student task list for forgetting risk.

Tasks:
{task_text}

Identify up to 3 tasks with HIGH forgetting risk based on:
1. Tasks with no Moodle deadline (source: label/page/file) that students easily forget
2. Exams or quizzes coming up while many assignments are due around the same time
3. Tasks due after a break or long gap

For each high-risk task:
ALERT: [task name] - [one sentence reason]

If no high risk tasks, reply: NO ALERTS"""
    try:
        if AI_PROVIDER == "anthropic" and ANTHROPIC_KEY:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            result = msg.content[0].text.strip()
        elif AI_PROVIDER == "gemini" and GEMINI_KEY:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            result = model.generate_content(prompt).text.strip()
        elif AI_PROVIDER == "groq" and GROQ_KEY:
            from groq import Groq
            client = Groq(api_key=GROQ_KEY)
            msg = client.chat.completions.create(
                model="llama3-8b-8192",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            result = msg.choices[0].message.content.strip()
        else:
            return
        if result and result != "NO ALERTS":
            notify("Risk Alert: CyberButler", result, "high")
            print(f"  Risk analysis: alerts sent")
    except Exception as e:
        print(f"  Risk analysis error: {e}")

def scan_course(course_id, course_name):
    found = []
    contents = moodle("core_course_get_contents", courseid=course_id)
    if isinstance(contents, dict) and "exception" in contents:
        print(f"  Error: {contents.get('message')}")
        return []

    for section in contents:
        for mod in section.get("modules", []):
            modname = mod["modname"]
            name = mod["name"]

            if modname in ("assign", "quiz"):
                due_ts = None
                for d in mod.get("dates", []):
                    if d.get("dataid") in ("duedate", "timeclose"):
                        due_ts = d.get("timestamp")
                if due_ts:
                    due_str = datetime.fromtimestamp(due_ts).strftime("%m/%d %H:%M")
                    instance_id = mod.get("instance", 0)
                    already_done = False
                    if modname == "assign" and instance_id:
                        try:
                            sub = moodle("mod_assign_get_submission_status", assignid=instance_id)
                            state = sub.get("lastattempt", {}).get("submission", {}).get("status", "")
                            if state in ("submitted", "graded"):
                                already_done = True
                        except:
                            pass
                    if due_ts > datetime.now().timestamp() or already_done:
                        found.append({
                            "title": name,
                            "due": due_str,
                            "due_ts": due_ts,
                            "type": modname,
                            "source": "moodle_api",
                            "course": course_name,
                            "done": already_done
                        })
                elif not due_ts:
                    desc = mod.get("description", "")
                    desc_text = BeautifulSoup(desc, "html.parser").get_text() if desc else ""
                    combined = f"Title: {name}\nDescription: {desc_text}"
                    ai_items = ai_extract_deadlines(combined, f"assign:{name}", course_name)
                    if ai_items:
                        for item in ai_items:
                            item["source"] = "moodle_desc"
                            item["course"] = course_name
                            item["done"] = False
                            item.setdefault("due_ts", 7777777777)
                        found.extend(ai_items)
                        print(f"    [desc] {name}: found {len(ai_items)} items")
                    else:
                        found.append({
                            "title": name,
                            "due": "No deadline set",
                            "due_ts": 9999999999,
                            "type": modname,
                            "source": "moodle_api",
                            "course": course_name,
                            "done": False
                        })

            elif modname == "label":
                desc = mod.get("description", "")
                if desc and len(desc) > 100:
                    text = BeautifulSoup(desc, "html.parser").get_text(separator=" ", strip=True)
                    items = ai_extract_deadlines(text, f"label:{name}", course_name)
                    for item in items:
                        item["source"] = f"label:{name}"
                        item["course"] = course_name
                        item["done"] = False
                        item.setdefault("due_ts", 8888888888)
                    found.extend(items)
                    if items:
                        print(f"    [label] {name}: found {len(items)} items")

            elif modname == "page":
                for c in mod.get("contents", []):
                    if c.get("filename", "").endswith(".html"):
                        try:
                            content = download_file(c["fileurl"])
                            text = extract_text_from_html(content)
                            items = ai_extract_deadlines(text, name, course_name)
                            for item in items:
                                item["source"] = f"page:{name}"
                                item["course"] = course_name
                                item["done"] = False
                                item.setdefault("due_ts", 8888888888)
                            found.extend(items)
                            if items:
                                print(f"    [page] {name}: found {len(items)} items")
                        except Exception as e:
                            print(f"    [page] {name}: error {e}")

            elif modname == "resource":
                for c in mod.get("contents", []):
                    fname = c.get("filename", "").lower()
                    if any(k in fname for k in ["calendar", "schedule", "syllabus"]):
                        try:
                            content = download_file(c["fileurl"])
                            if fname.endswith(".pdf"):
                                text = extract_text_from_pdf(content)
                            elif fname.endswith(".docx"):
                                text = extract_text_from_docx(content)
                            else:
                                continue
                            items = ai_extract_deadlines(text, c["filename"], course_name)
                            for item in items:
                                item["source"] = f"file:{c['filename']}"
                                item["course"] = course_name
                                item["done"] = False
                                item.setdefault("due_ts", 8888888888)
                            found.extend(items)
                            if items:
                                print(f"    [file] {c['filename']}: found {len(items)} items")
                        except Exception as e:
                            print(f"    [file] {fname}: error {e}")
    return found

def scan_gradescope():
    found = []
    if not GRADESCOPE_EMAIL or not GRADESCOPE_PASSWORD:
        return found
    try:
        s = requests.Session()
        r = s.get("https://www.gradescope.com/login")
        soup = BeautifulSoup(r.text, "html.parser")
        token = soup.find("input", {"name": "authenticity_token"})["value"]
        s.post("https://www.gradescope.com/login", data={
            "utf8": "✓",
            "authenticity_token": token,
            "session[email]": GRADESCOPE_EMAIL,
            "session[password]": GRADESCOPE_PASSWORD,
            "session[remember_me]": "0",
            "commit": "Log In"
        })
        now_ts = datetime.now().timestamp()
        for cid, cname in GRADESCOPE_COURSES.items():
            r = s.get(f"https://www.gradescope.com/courses/{cid}")
            soup = BeautifulSoup(r.text, "html.parser")
            rows = soup.find_all("tr")
            for row in rows:
                th = row.find("th")
                tds = row.find_all("td")
                if not th or not tds:
                    continue
                name = th.text.strip()
                status = tds[0].text.strip()
                due_str = tds[3].text.strip() if len(tds) > 3 else ""
                if not due_str:
                    continue
                already_done = any(x in status for x in ["Submitted", "/ "])
                try:
                    due_dt = datetime.strptime(due_str, "%Y-%m-%d %H:%M:%S %z")
                    due_ts = int(due_dt.timestamp())
                except:
                    continue
                if due_ts < now_ts and not already_done:
                    continue
                due_display = datetime.fromtimestamp(due_ts).strftime("%m/%d %H:%M")
                found.append({
                    "title": name,
                    "due": due_display,
                    "due_ts": due_ts,
                    "type": "assign",
                    "source": "gradescope",
                    "course": cname,
                    "done": already_done
                })
        print(f"  Gradescope: {len(found)} items")
    except Exception as e:
        print(f"  Gradescope error: {e}")
    return found

def parse_due_ts(due_str):
    if not due_str or due_str in ("No deadline set", "TBD"):
        return 9999999999
    try:
        now = datetime.now()
        d = datetime.strptime(f"{due_str} {now.year}", "%m/%d %Y")
        if d < now:
            d = d.replace(year=now.year + 1)
        return int(d.timestamp())
    except:
        try:
            now = datetime.now()
            d = datetime.strptime(f"{due_str} {now.year}", "%m/%d %H:%M %Y")
            if d < now:
                d = d.replace(year=now.year + 1)
            return int(d.timestamp())
        except:
            return 8888888888

def merge_tasks(new_tasks, existing_tasks):
    existing_map = {}
    for t in existing_tasks:
        key = f"{t.get('course','')}:{t.get('title','')}"
        existing_map[key] = t
    merged = []
    for t in new_tasks:
        key = f"{t.get('course','')}:{t.get('title','')}"
        if key in existing_map:
            if not t.get("done"):
                t["done"] = existing_map[key].get("done", False)
        if not t.get("due_ts") or t["due_ts"] in (7777777777, 8888888888):
            t["due_ts"] = parse_due_ts(t.get("due", ""))
        merged.append(t)
    return merged

def main():
    print(f"CyberButler Scan: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    existing = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            existing = json.load(f)

    current_courses = get_current_courses()
    print(f"Courses: {list(current_courses.values())}")

    all_items = []
    for course_id, course_name in current_courses.items():
        items = scan_course(course_id, course_name)
        all_items.extend(items)
        print(f"  {course_name}: {len(items)} items")

    gs_items = scan_gradescope()
    all_items.extend(gs_items)

    merged = merge_tasks(all_items, existing)
    merged.sort(key=lambda x: x.get("due_ts", 9999999999))

    with open(DATA_FILE, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    now_ts = datetime.now().timestamp()
    urgent = [i for i in merged if not i.get("done") and
              isinstance(i.get("due_ts"), (int, float)) and
              i["due_ts"] - now_ts < 86400 and i["due_ts"] < 9000000000]
    if urgent:
        msg = "\n".join([f"[{i.get('type','?')}] {i['course']}: {i['title']} ({i['due']})" for i in urgent])
        notify(f"URGENT: {len(urgent)} due in 24h!", msg, "urgent")

    total = len([i for i in merged if not i.get("done")])
    notify(f"Scan done: {total} pending", f"Total {len(merged)} tasks")
    ai_risk_analysis(merged)
    print(f"Done. {len(merged)} tasks saved.")

if __name__ == "__main__":
    main()
