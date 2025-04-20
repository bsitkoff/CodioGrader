#!/usr/bin/env python3
"""
codio‑grader  v1.0  (2025‑04‑20) - Simplified Version with Notion

• Primary model: gpt-4.1-nano-2025-04-14
• Uses chat completions API for reliable grading

Environment vars expected
-------------------------
# Codio sets these automatically:
OPENAI_API_KEY             - API key for OpenAI
OPENAI_BASE_URL            - Base URL for OpenAI API

CODIO_AUTOGRADE_ENV        - set by Codio (absent when testing locally)
DEBUG                      - optional, set to "1" to enable debug logging

# The following are optional. If absent, Notion calls are skipped.
NOTION_API_KEY
NOTION_GRADES_DATABASE_ID
NOTION_STUDENTS_DATABASE_ID
"""

import os, sys, json, textwrap, pathlib, requests
from datetime import datetime
from time import perf_counter
from openai import OpenAI

# ------------------------------------------------------------
# Notion configuration
# Hardcoded for Codio autograding environment, but can be overridden
# by environment variables if needed. These values are secure as:
# 1. They're only in the .guides/secure directory (students can't access)
# 2. The GitHub repository is private
# ------------------------------------------------------------
NOTION_CONFIG = {
    "API_KEY": "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",
    "GRADES_DB": "19c2fa9286478146942df2be3193a18d",
    "STUDENTS_DB": "19c2fa9286478121a858f58796de39a9"
}

# Allow environment variable override if needed
NOTION_API_KEY = os.getenv("NOTION_API_KEY", NOTION_CONFIG["API_KEY"])
NOTION_GRADES_DATABASE_ID = os.getenv("NOTION_GRADES_DATABASE_ID", NOTION_CONFIG["GRADES_DB"])
NOTION_STUDENTS_DATABASE_ID = os.getenv("NOTION_STUDENTS_DATABASE_ID", NOTION_CONFIG["STUDENTS_DB"])

# ------------------------------------------------------------
# Minimal logger – write to stderr only when DEBUG env var is true
# ------------------------------------------------------------
DEBUG = os.getenv("DEBUG", "0") not in ("0", "", "false", "False")

def log(msg: str):
    if DEBUG:
        print(f"[DEBUG] {msg}", file=sys.stderr)

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
# OpenAI API handling - simplified to use completions
# ------------------------------------------------------------
# Initialize the OpenAI client with default settings
# Note: Codio sets OPENAI_API_KEY and OPENAI_BASE_URL automatically
openai_client = OpenAI()
DEFAULT_MODEL = "gpt-4.1-nano-2025-04-14"

def call_openai(system_msg:str, user_msg:str, model:str=None) -> str:
    """Call OpenAI completions API and return the response text."""
    model = model or DEFAULT_MODEL
    log(f"Calling OpenAI API with model: {model}")
    
    try:
        # Using the OpenAI completions API
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.1
        )
        result = response.choices[0].message.content.strip()
        log(f"API response received: {result[:50]}...")
        return result
    except Exception as e:
        error_msg = str(e)
        log(f"OpenAI API call failed: {error_msg}")
        print(f"OpenAI API call failed: {error_msg}", file=sys.stderr)
        raise

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

# ------------------------------------------------------------
# Notion integration for tracking submissions
# ------------------------------------------------------------
def notion_log(student_email:str, assignment_title:str, score:int, feedback:str,
               topic_id:str):
    """
    Log grading results to Notion database if credentials are available.
    Silently skips logging if any required credentials are missing.
    """
    # Use the globally defined Notion credentials
    key   = NOTION_API_KEY
    db_gr = NOTION_GRADES_DATABASE_ID
    db_st = NOTION_STUDENTS_DATABASE_ID
    
    # Skip if any credentials are missing
    if not all([key, db_gr, db_st]):
        log("Notion logging skipped - missing credentials")
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
          local_override_email=None,
          override_model=None):
    """
    Main grading function that evaluates student code and provides feedback.
    
    Args:
        config_path: Path to the config JSON file
        local_override_email: Optional email override for local testing
        override_model: Optional model override for the OpenAI API
    """
    # Start timer for elapsed time tracking
    start_time = perf_counter()
    
    log(f"Starting grading process with config: {config_path}")
    
    # Load configuration and student code
    cfg = load_config(config_path)
    code = load_code(cfg["files"])
    prompt = cfg.get("assignment_prompt", "")
    assignment_title = cfg.get("assignment_title", "Codio Assignment")
    topic_id = cfg.get("grade_topic_id", "")
    
    log(f"Loaded assignment: {assignment_title}")
    log(f"Files to grade: {cfg['files']}")
    
    # Get prompts from config or use defaults
    default_system_prompt = """\
        You are an auto‑grader for student programming assignments.
        Respond ONLY with "yes" or "no" (lowercase) when asked if code
        meets the assignment requirements; no extra text.
    """
    default_eval_prompt = "Does this code meet the assignment requirements? Answer only 'yes' or 'no'."
    
    # Use prompts from config if available, otherwise use defaults
    system_msg = cfg.get("system_prompt", default_system_prompt)
    evaluation_prompt = cfg.get("evaluation_prompt", default_eval_prompt)
    
    user_msg = textwrap.dedent(f"""\
        ## Assignment instructions
        {prompt}

        ## Student submission
        {code}

        {evaluation_prompt}
    """)

    try:
        # Call OpenAI API for grading
        yn = call_openai(system_msg, user_msg, override_model).lower()
    except Exception as e:
        # Graceful failure path so students are not blocked
        error_msg = f"⚠️ Autograder API error: {e}"
        if in_codio():
            codio_send(0, error_msg)
        else:
            print("ERROR contacting OpenAI API:", e, file=sys.stderr)
            print("Make sure your API key has access to the models needed.")
        return

    # Process the yes/no response
    if yn.startswith("y"):
        passed = True
        grade_val = 100
    elif yn.startswith("n"):
        passed = False
        grade_val = 50
    else:
        # Unexpected response
        passed = False
        grade_val = 50
        unexpected_response = f"⚠️ Note: The grader received an unexpected response: '{yn}'. Expected 'yes' or 'no'."

    # Generate feedback
    if passed:
        default_pass_prompt = "You are a kind mentor. Give one upbeat sentence of praise."
        feedback_system_msg = cfg.get("feedback_prompt_pass", default_pass_prompt)
        feedback_user_msg = code
    else:
        default_fail_prompt = ("You are a kind mentor. In <=2 short sentences explain "
                  "why the code might not meet requirements. Keep it friendly for an 11‑yo.")
        feedback_system_msg = cfg.get("feedback_prompt_fail", default_fail_prompt)
        feedback_user_msg = code

    try:
        feedback = call_openai(feedback_system_msg, feedback_user_msg, override_model)
        
        # Append unexpected response warning if applicable
        if 'unexpected_response' in locals():
            feedback = f"{feedback}\n\n{unexpected_response}"
    except Exception as e:
        feedback = "Unable to generate detailed feedback. Please review your code."
        print(f"Error generating feedback: {e}", file=sys.stderr)

    # Deliver results
    if in_codio():
        ok = codio_send(grade_val, feedback)
        
        # Log to Notion if in Codio environment
        env = json.loads(os.getenv("CODIO_AUTOGRADE_ENV"))
        email = (local_override_email or
                env.get("student", {}).get("email", "unknown@nowhere"))
        try:
            log(f"Logging to Notion for student: {email}")
            notion_log(email, assignment_title, grade_val, feedback, topic_id)
        except Exception as e:
            # non-fatal
            print("Notion log failed:", e, file=sys.stderr)
            log(f"Notion logging failed: {str(e)}")
            
        sys.exit(0 if ok else 1)
    else:
        # Calculate elapsed time
        elapsed_time = perf_counter() - start_time
        
        # Local test mode
        print(json.dumps({
            "grade": grade_val,
            "feedback": feedback,
            "passed": passed,
            "elapsed_seconds": round(elapsed_time, 2)
        }, indent=2))
        
        # Print timing info to stderr
        print(f"Elapsed time: {elapsed_time:.2f} seconds", file=sys.stderr)

# ------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Run the Codio grader locally or inside Codio.")
    ap.add_argument("-c", "--config", default="autograde_config.json",
                   help="Path to autograde_config.json")
    ap.add_argument("--email", help="Override student e‑mail (local test)")
    ap.add_argument("--model", help="Override primary model (e.g., gpt-4o)")
    args = ap.parse_args()
    grade(args.config, local_override_email=args.email, override_model=args.model)

