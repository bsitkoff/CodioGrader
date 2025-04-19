#!/usr/bin/env python3
"""
codio‑grader  v1.0  (2025‑04‑19)

• Primary model  : gpt‑4.1‑nano‑2025‑04‑14   (≈ $0.00013/run @ 330 tokens)
• Fallback chain : gpt‑4o‑mini  ➜  gpt‑3.5‑turbo

Environment vars expected
-------------------------
# Required - at least one of these must be set:
OPENAI_API_KEY               legacy/fallback API key
CODIO_DIRECT_OPENAI_KEY     direct API access (preferred when available)
CODIO_DIRECT_OPENAI_BASE    base URL for direct API (optional)

CODIO_AUTOGRADE_ENV         set by Codio   (absent when you test locally)

# The following are optional.  If absent, Notion calls are skipped.
NOTION_API_KEY
NOTION_GRADES_DATABASE_ID
NOTION_STUDENTS_DATABASE_ID
"""

import os, sys, json, time, textwrap, pathlib, requests
from datetime import datetime
from time import perf_counter
from openai import OpenAI

# ------------------------------------------------------------
# Minimal logger – write to stderr only when DEBUG env var is true
# ------------------------------------------------------------
DEBUG = os.getenv("DEBUG", "0") not in ("0", "", "false", "False")

def log(msg: str):
    if DEBUG:
        print(f"[DEBUG] {msg}", file=sys.stderr)

#!/usr/bin/env python3
"""
codio‑grader  v1.0  (2025‑04‑19)

• Primary model  : gpt‑4.1‑nano‑2025‑04‑14   (≈ $0.00013/run @ 330 tokens)
• Fallback chain : gpt‑4o‑mini  ➜  gpt‑3.5‑turbo

Environment vars expected
-------------------------
# Required - at least one of these must be set:
OPENAI_API_KEY               legacy/fallback API key
CODIO_DIRECT_OPENAI_KEY     direct API access (preferred when available)
CODIO_DIRECT_OPENAI_BASE    base URL for direct API (optional)

CODIO_AUTOGRADE_ENV         set by Codio   (absent when you test locally)

# The following are optional.  If absent, Notion calls are skipped.
NOTION_API_KEY
NOTION_GRADES_DATABASE_ID
NOTION_STUDENTS_DATABASE_ID
"""

import os, sys, json, time, textwrap, pathlib, requests
from datetime import datetime
from time import perf_counter
from openai import OpenAI

# ------------------------------------------------------------
# OpenAI client configuration
# ------------------------------------------------------------
def create_openai_clients():
    """Create OpenAI clients for both direct and fallback configurations.
    Returns a dictionary with 'direct' and 'fallback' clients."""
    clients = {}
    
    # Try to create direct client first
    direct_key = os.getenv("CODIO_DIRECT_OPENAI_KEY")
    direct_base = os.getenv("CODIO_DIRECT_OPENAI_BASE", "https://api.openai.com/v1")
    
    if direct_key:
        log(f"Configuring direct OpenAI client with base URL: {direct_base}")
        try:
            clients["direct"] = OpenAI(
                api_key=direct_key,
                base_url=direct_base
            )
            log("Direct OpenAI client created successfully")
        except Exception as e:
            log(f"Failed to create direct client: {e}")
    else:
        log("No direct OpenAI configuration found (CODIO_DIRECT_OPENAI_KEY not set)")
    
    # Create fallback client if fallback key exists
    fallback_key = os.getenv("OPENAI_API_KEY")
    if fallback_key:
        log("Creating fallback OpenAI client with default configuration")
        clients["fallback"] = OpenAI()
    else:
        log("No fallback configuration found (OPENAI_API_KEY not set)")
    
    if not clients:
        raise RuntimeError("No valid OpenAI configuration found. Set either CODIO_DIRECT_OPENAI_KEY or OPENAI_API_KEY")
    
    return clients

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
# Environment variable loader (from load_env.py)
# ------------------------------------------------------------
def load_env_vars(env_path=".env", verbose=False):
    """Load environment variables from a .env file"""
    p = pathlib.Path(env_path)
    if not p.exists():
        if verbose:
            print(f"[load_env] {env_path} not found – skipping.", file=sys.stderr)
        raise FileNotFoundError(f"Environment file not found: {env_path}")
    
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
    
    if verbose:
        print(f"[load_env] variables from {env_path} loaded.")

# ------------------------------------------------------------
# Wrapper around the OpenAI client responses API
# ------------------------------------------------------------
# Load environment variables from .env file
try:
    load_env_vars(verbose=False)
except FileNotFoundError:
    print("Warning: .env file not found. Make sure environment variables are set manually.", file=sys.stderr)

# Initialize the OpenAI clients
log("Initializing OpenAI clients...")
openai_clients = create_openai_clients()
log(f"Created clients with configurations: {list(openai_clients.keys())}")

MODEL_CHAIN = [
    "gpt-4.1-nano-2025-04-14",
    "gpt-4o-mini",
    "gpt-3.5-turbo"
]

def call_openai(dev_msg:str, user_msg:str, override_model:str=None) -> str:
    """Try each model until one succeeds, return text output.
    First tries direct OpenAI connection if available, then falls back to default."""
    last_err = None
    
    # Use override_model if provided, otherwise use the MODEL_CHAIN
    models_to_try = [override_model] + MODEL_CHAIN[1:] if override_model else MODEL_CHAIN
    
    # Try direct client first if available
    if "direct" in openai_clients:
        log("Attempting to use direct OpenAI client first")
        for model in models_to_try:
            try:
                log(f"Trying model {model} with direct client")
                response = openai_clients["direct"].responses.create(
                    model=model,
                    instructions=dev_msg,
                    input=[
                        {
                            "role": "user", 
                            "content": user_msg
                        }
                    ]
                )
                log("Direct client request successful")
                return response.output_text.strip()
            except Exception as e:
                last_err = f"Direct API failed: {str(e)}"
                log(f"Direct API - Model {model} failed: {str(e)}")
                continue
        log("All models failed with direct client, falling back to default")
    
    # Try fallback client if available
    if "fallback" in openai_clients:
        log("Attempting to use fallback OpenAI client")
        for model in models_to_try:
            try:
                log(f"Trying model {model} with fallback client")
                response = openai_clients["fallback"].responses.create(
                    model=model,
                    instructions=dev_msg,
                    input=[
                        {
                            "role": "user", 
                            "content": user_msg
                        }
                    ]
                )
                log("Fallback client request successful")
                return response.output_text.strip()
            except Exception as e:
                last_err = f"Fallback API failed: {str(e)}"
                log(f"Fallback API - Model {model} failed: {str(e)}")
                time.sleep(1)  # Brief pause before trying the next model
                continue
    
    raise RuntimeError(f"All API attempts failed: {last_err}")

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

# OPTIONAL – Notion logging (works only if all IDs + key present)
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
          local_override_email=None,
          override_model=None):
    cfg      = load_config(config_path)
    code     = load_code(cfg["files"])
    prompt   = cfg.get("assignment_prompt", "")
    topic_id = cfg.get("grade_topic_id", "")
    assignment_title = cfg.get("assignment_title", "Codio Assignment")
    
    # Start timer for elapsed time tracking
    start_time = perf_counter()

    #########################################
    # Build developer / user messages
    #########################################
    dev_msg = textwrap.dedent("""
        You are an auto‑grader for middle‑school Python assignments.
        Respond ONLY with "yes" or "no" (lowercase) when asked if code
        meets the assignment requirements; no extra text.
    """)

    user_msg = textwrap.dedent(f"""
        ## Assignment instructions
        {prompt}

        ## Student submission
        {code}
    """)

    try:
        yn = call_openai(dev_msg, user_msg, override_model).lower()
    except Exception as e:
        # Graceful failure path so students are not blocked
        error_msg = f"⚠️ Autograder API error: {e}"
        if in_codio():
            codio_send(0, error_msg)
        else:
            print("ERROR contacting OpenAI API:", e, file=sys.stderr)
            print("Make sure your API key has access to the models and responses API.")
        return

    # Check for unexpected responses (not yes/no)
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
        # Add the unexpected response to feedback
        unexpected_response = f"⚠️ Note: The grader received an unexpected response: '{yn}'. Expected 'yes' or 'no'."

    #########################################
    # follow‑up feedback
    #########################################
    if passed:
        fb_dev = "You are a kind mentor. Give one upbeat sentence of praise."
    else:
        fb_dev = ("You are a kind mentor. In <=2 short sentences explain "
                  "why the code might not run. Keep it friendly for an 11‑yo.")

    feedback = call_openai(fb_dev, code if not passed else "", override_model)
    
    # Append unexpected response warning if applicable
    if 'unexpected_response' in locals():
        feedback = f"{feedback}\n\n{unexpected_response}"

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
