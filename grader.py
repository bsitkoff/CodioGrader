#!/usr/bin/env python3
"""
codio‑grader  v1.0  (2025‑04‑19)

• Primary model  : gpt‑4.1‑nano‑2025‑04‑14   (≈ $0.00013/run @ 330 tokens)
• Fallback chain : gpt‑4o‑mini  ➜  gpt‑3.5‑turbo

Environment vars expected
-------------------------
OPENAI_API_KEY               required
CODIO_AUTOGRADE_ENV          set by Codio   (absent when you test locally)

# The following are optional.  If absent, Notion calls are skipped.
NOTION_API_KEY
NOTION_GRADES_DATABASE_ID
NOTION_STUDENTS_DATABASE_ID
"""

import os, sys, json, time, textwrap, pathlib, requests
from datetime import datetime

# ------------------------------------------------------------
# Configuration helpers
# ------------------------------------------------------------
def load_config(fname="autograde_config.json"):
    with open(fname, "r") as cf:
        return json.load(cf)

def load_code(file_list):
    buf = []
    for fn in file_list:
        p = pathlib.Path(fn)
        if not p.exists() or p.stat().st_size == 0:
            raise FileNotFoundError(f"Required file missing or empty: {fn}")
        buf.append(f"# === {fn} ===\n{p.read_text()}")
    return "\n\n".join(buf)

# ------------------------------------------------------------
# Thin wrapper around the new /responses endpoint
# ------------------------------------------------------------
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    print("OPENAI_API_KEY is not set; aborting.", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {OPENAI_KEY}",
    "Content-Type":  "application/json"
}
URL = "https://api.openai.com/v1/responses"

MODEL_CHAIN = [
    "gpt-4.1-nano-2025-04-14",
    "gpt-4o-mini",
    "gpt-3.5-turbo"
]

def call_openai(dev_msg:str, user_msg:str) -> str:
    """Try each model until one succeeds, return combined text output."""
    payload_template = {
        "instructions": dev_msg,
        # When we supply `instructions` the field is high‑priority.
        # Our actual prompt goes into `input`.
        "input": user_msg,
    }

    last_err = None
    for model in MODEL_CHAIN:
        payload = dict(payload_template, model=model)
        try:
            r = requests.post(URL, headers=HEADERS, json=payload, timeout=30)
            if r.status_code == 429:          # quota / rate limit
                last_err = r.text; time.sleep(2); continue
            r.raise_for_status()
            data = r.json()
            # SDKs expose `output_text`, but with bare HTTP call we need to
            # concatenate all text outputs ourselves:
            text_chunks = [
                c["text"]
                for item in data
                for c in item.get("content", [])
                if c.get("type") == "output_text"
            ]
            return "".join(text_chunks).strip()
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(f"All models failed: {last_err}")

# ------------------------------------------------------------
# Codio helpers (loaded lazily so local runs don't fail)
# ------------------------------------------------------------
def in_codio() -> bool:
    return bool(os.getenv("CODIO_AUTOGRADE_ENV"))

def codio_send(grade:int, feedback:str):
    # Import only when really in Codio
    sys.path.append("/usr/share/codio/assessments")
    from lib.grade import send_grade_v2, FORMAT_V2_MD
    return send_grade_v2(grade, feedback, FORMAT_V2_MD)

# OPTIONAL – Notion logging (works only if all IDs + key present)
def notion_log(student_email:str, assignment_title:str, score:int, feedback:str,
               topic_id:str):
    key   = os.getenv("NOTION_API_KEY")
    db_gr = os.getenv("NOTION_GRADES_DATABASE_ID")
    db_st = os.getenv("NOTION_STUDENTS_DATABASE_ID")
    if not all([key, db_gr, db_st]):          # silently skip if not configured
        return

    # resolve student page ID
    headers = {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    qurl = f"https://api.notion.com/v1/databases/{db_st}/query"
    student_page_id = None
    cursor = None
    while True:
        body = {"start_cursor": cursor} if cursor else {}
        resp = requests.post(qurl, headers=headers, json=body).json()
        for page in resp.get("results", []):
            if (page["properties"]
                    .get("Email", {})
                    .get("email", "")
                    .lower() == student_email.lower()):
                student_page_id = page["id"]; break
        if student_page_id or not resp.get("has_more"): break
        cursor = resp.get("next_cursor")
    if not student_page_id:           # don't crash grader on lookup failure
        return

    payload = {
        "parent": {"database_id": db_gr},
        "properties": {
            "Name":   {"title":  [{"text": {"content": assignment_title}}]},
            "Student":{"relation":[{"id": student_page_id}]},
            "Date":   {"date":   {"start": datetime.utcnow().isoformat()}},
            "Total":  {"number": 100},
            "Score":  {"number": score},
            "Notes":  {"rich_text":[{"text": {"content": feedback[:1900]}}]},
            "Grade Topic": {"relation":[{"id": topic_id}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages",
                  headers=headers, json=payload)

# ------------------------------------------------------------
# Main grading logic
# ------------------------------------------------------------
def grade(config_path="autograde_config.json",
          local_override_email=None):
    cfg      = load_config(config_path)
    code     = load_code(cfg["files"])
    prompt   = cfg.get("assignment_prompt", "")
    topic_id = cfg.get("grade_topic_id", "")
    assignment_title = cfg.get("assignment_title", "Codio Assignment")

    #########################################
    # Build developer / user messages
    #########################################
    dev_msg = textwrap.dedent("""\
        You are an auto‑grader for middle‑school Python assignments.
        Respond ONLY with “yes” or “no” (lowercase) when asked if code
        meets the assignment requirements; no extra text.
    """)

    user_msg = textwrap.dedent(f"""\
        ## Assignment instructions
        {prompt}

        ## Student submission
        {code}
    """)

    try:
        yn = call_openai(dev_msg, user_msg).lower()
    except Exception as e:
        # Graceful failure path so students are not blocked
        if in_codio():
            codio_send(0, f"⚠️ Autograder error: {e}")
        else:
            print("ERROR contacting OpenAI:", e, file=sys.stderr)
        return

    passed = yn.startswith("y")
    grade_val = 100 if passed else 50

    #########################################
    # follow‑up feedback
    #########################################
    if passed:
        fb_dev = "You are a kind mentor. Give one upbeat sentence of praise."
    else:
        fb_dev = ("You are a kind mentor. In <=2 short sentences explain "
                  "why the code might not run. Keep it friendly for an 11‑yo.")

    feedback = call_openai(fb_dev, code if not passed else "")

    # -------------------------------------
    # Deliver results
    # -------------------------------------
    if in_codio():
        ok = codio_send(grade_val, feedback)
        # attach Notion row if possible
        env = json.loads(os.getenv("CODIO_AUTOGRADE_ENV"))
        email = (local_override_email or
                 env.get("student", {}).get("email", "unknown@nowhere"))
        try:
            notion_log(email, assignment_title, grade_val, feedback, topic_id)
        except Exception as e:
            # non‑fatal
            print("Notion log failed:", e, file=sys.stderr)
        sys.exit(0 if ok else 1)
    else:
        # Local test mode
        print(json.dumps({
            "grade": grade_val,
            "feedback": feedback,
            "passed": passed
        }, indent=2))

# ------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Run the Codio grader locally or inside Codio.")
    ap.add_argument("-c", "--config", default="autograde_config.json",
                    help="Path to autograde_config.json")
    ap.add_argument("--email", help="Override student e‑mail (local test)")
    args = ap.parse_args()
    grade(args.config, local_override_email=args.email)
