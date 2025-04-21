#!/usr/bin/env python3
import os
import sys
import json
import argparse
from datetime import datetime
import requests
import re
import subprocess
from typing import Dict, List, Any, Tuple

class AutoGrader:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.openai_key = os.getenv('OPENAI_API_KEY')
        self.notion_key = os.getenv('NOTION_API_KEY')
        self.notion_grades_db = os.getenv('NOTION_GRADES_DATABASE_ID')
        self.notion_students_db = os.getenv('NOTION_STUDENTS_DATABASE_ID')
        self.debug = os.getenv('DEBUG', '0') == '1'
        self.codio_env = self._parse_codio_env()

    def _parse_codio_env(self) -> Dict:
        """Parse Codio environment variables if available"""
        codio_env_json = os.getenv('CODIO_AUTOGRADE_ENV')
        if not codio_env_json:
            self.log("Not running in Codio environment")
            return {}
        
        try:
            return json.loads(codio_env_json)
        except Exception as e:
            self.log(f"Failed to parse CODIO_AUTOGRADE_ENV: {str(e)}")
            return {}

    def _load_config(self, path: str) -> Dict:
        with open(path, 'r') as f:
            return json.load(f)

    def log(self, message: str) -> None:
        """Debug logging"""
        if self.debug:
            print(f"[DEBUG] {message}", file=sys.stderr)

    def _check_environment(self) -> None:
        """Verify all required environment variables are set"""
        required_vars = {
            'OPENAI_API_KEY': self.openai_key,
        }
        
        # Only require Notion variables if Notion is enabled
        if self.config.get('notion', {}).get('enabled', False):
            required_vars.update({
                'NOTION_API_KEY': self.notion_key,
                'NOTION_GRADES_DATABASE_ID': self.notion_grades_db,
                'NOTION_STUDENTS_DATABASE_ID': self.notion_students_db
            })
            
        missing = [k for k, v in required_vars.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    def _read_student_file(self, path: str) -> str:
        """Read a student's submission file"""
        try:
            with open(path, 'r') as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Failed to read student file {path}: {str(e)}")

    def _evaluate_criterion(self, criterion: Dict, code: str) -> Dict:
        """Evaluate a single criterion"""
        score = 0
        feedback = ""
        
        self.log(f"Evaluating criterion: {criterion['description']}")
        
        if criterion['type'] == 'ai_review':
            score, feedback = self._ai_review(criterion, code)
        elif criterion['type'] in ['python_syntax', 'microbit_blocks', 'scratch_blocks']:
            score, feedback = self._check_syntax(criterion, code)
        elif criterion['type'] == 'output_match':
            score, feedback = self._check_output(criterion, code)
        else:
            feedback = f"Unknown criterion type: {criterion['type']}"
        
        # Cap score at maximum points for this criterion
        score = min(score, criterion['points'])
        
        return {
            'score': score,
            'feedback': feedback,
            'max_points': criterion['points']
        }

    def _ai_review(self, criterion: Dict, code: str) -> Tuple[float, str]:
        """Get AI review for code"""
        try:
            system_prompt = criterion.get('system_prompt', 'You are a teacher evaluating student code.')
            self.log(f"AI Review with prompt: {system_prompt[:50]}...")
            
            # Check if we're using a Codio BricksLLM proxy
            openai_base_url = os.getenv('OPENAI_BASE_URL')
            
            headers = {
                'Authorization': f'Bearer {self.openai_key}',
                'Content-Type': 'application/json'
            }
            
            api_url = f"{openai_base_url}/chat/completions" if openai_base_url else "https://api.openai.com/v1/chat/completions"
            
            response = requests.post(
                api_url,
                headers=headers,
                json={
                    'model': 'gpt-4',  # Adjust based on availability
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': code}
                    ]
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")
                
            result = response.json()
            feedback = result['choices'][0]['message']['content']
            
            # Extract score from feedback if it starts with a number (as per system prompt)
            try:
                score_match = re.match(r'^\s*(\d+(\.\d+)?)', feedback)
                if score_match:
                    score = float(score_match.group(1))
                    # Remove the score from the feedback
                    feedback = feedback[score_match.end():].strip()
                else:
                    score = 0
            except:
                score = 0
                
            return score, feedback
            
        except Exception as e:
            self.log(f"AI review failed: {str(e)}")
            return 0, f"AI review failed: {str(e)}"

    def _check_syntax(self, criterion: Dict, code: str) -> Tuple[float, str]:
        """Check code syntax based on criterion type"""
        try:
            if criterion['type'] == 'python_syntax':
                # Check Python syntax
                return self._check_python_syntax(criterion, code)
            elif criterion['type'] == 'microbit_blocks':
                # For microbit, we can check for specific imports or patterns
                return self._check_microbit_syntax(criterion, code)
            elif criterion['type'] == 'scratch_blocks':
                # For scratch, we would need a different approach
                return 0, "Scratch syntax checking not implemented"
            else:
                return 0, f"Unknown syntax check type: {criterion['type']}"
        except Exception as e:
            self.log(f"Syntax check failed: {str(e)}")
            return 0, f"Syntax check failed: {str(e)}"

    def _check_python_syntax(self, criterion: Dict, code: str) -> Tuple[float, str]:
        """Check Python syntax and required elements"""
        # First, check if the code compiles
        try:
            compile(code, '<string>', 'exec')
        except Exception as e:
            return 0, f"Syntax error: {str(e)}"
            
        # Check for required elements
        required_elements = criterion.get('required_elements', [])
        found_elements = []
        missing_elements = []
        
        for element in required_elements:
            if element == 'function_definition':
                if re.search(r'def\s+\w+\s*\(', code):
                    found_elements.append(element)
                else:
                    missing_elements.append(element)
            elif element == 'while_loop':
                if re.search(r'while\s+.+:', code):
                    found_elements.append(element)
                else:
                    missing_elements.append(element)
            elif element == 'for_loop':
                if re.search(r'for\s+.+\s+in\s+.+:', code):
                    found_elements.append(element)
                else:
                    missing_elements.append(element)
            elif element == 'if_statement':
                if re.search(r'if\s+.+:', code):
                    found_elements.append(element)
                else:
                    missing_elements.append(element)
            # Add more element checks as needed
        
        # Calculate score based on found elements
        if not required_elements:
            score = criterion['points']  # Full points if no specific elements required
        else:
            score = (len(found_elements) / len(required_elements)) * criterion['points']
        
        # Generate feedback
        if missing_elements:
            feedback = f"Missing required elements: {', '.join(missing_elements)}"
        else:
            feedback = "All required elements found"
            
        return score, feedback

    def _check_microbit_syntax(self, criterion: Dict, code: str) -> Tuple[float, str]:
        """Check Microbit-specific code patterns"""
        required_elements = criterion.get('required_elements', [])
        found_elements = []
        missing_elements = []
        
        # Check for microbit-specific imports and functions
        if 'microbit_import' in required_elements:
            if re.search(r'from\s+microbit\s+import', code):
                found_elements.append('microbit_import')
            else:
                missing_elements.append('microbit_import')
                
        if 'display_image' in required_elements:
            if re.search(r'display\.(show|scroll|get_pixel|set_pixel)', code):
                found_elements.append('display_image')
            else:
                missing_elements.append('display_image')
                
        if 'button_input' in required_elements:
            if re.search(r'button_(a|b)\.(was_pressed|is_pressed|get_presses)', code):
                found_elements.append('button_input')
            else:
                missing_elements.append('button_input')
                
        # Calculate score based on found elements
        if not required_elements:
            score = criterion['points']  # Full points if no specific elements required
        else:
            score = (len(found_elements) / len(required_elements)) * criterion['points']
        
        # Generate feedback
        if missing_elements:
            feedback = f"Missing required Microbit elements: {', '.join(missing_elements)}"
        else:
            feedback = "All required Microbit elements found"
            
        return score, feedback

    def _check_output(self, criterion: Dict, code: str) -> Tuple[float, str]:
        """Check if code produces expected output"""
        try:
            # Create a temporary file to run the code
            with open('temp_code.py', 'w') as f:
                f.write(code)
            
            # Run the code and capture output
            result = subprocess.run(
                ['python3', 'temp_code.py'], 
                capture_output=True, 
                text=True, 
                timeout=5  # 5 second timeout
            )
            
            # Clean up temp file
            os.remove('temp_code.py')
            
            actual_output = result.stdout.strip()
            expected_output = criterion.get('expected', '').strip()
            
            # Check for exact match
            if actual_output == expected_output:
                return criterion['points'], "Output matches expected result"
            
            # Check for partial credit if enabled
            if criterion.get('partial_credit', False):
                # Simple partial credit based on string similarity
                max_len = max(len(actual_output), len(expected_output))
                if max_len == 0:
                    similarity = 0
                else:
                    # Calculate Levenshtein distance (simplified approach)
                    similarity = 1 - (abs(len(actual_output) - len(expected_output)) / max_len)
                    
                    # Additional factors to consider
                    if expected_output in actual_output:
                        similarity = max(similarity, 0.8)  # At least 80% if expected output is contained
                        
                    # Check for word-level similarity
                    expected_words = set(expected_output.split())
                    actual_words = set(actual_output.split())
                    if expected_words and actual_words:
                        common_words = expected_words.intersection(actual_words)
                        word_similarity = len(common_words) / len(expected_words)
                        similarity = max(similarity, word_similarity)
                
                score = similarity * criterion['points']
                feedback = f"Output partially matches. Expected: '{expected_output}', Got: '{actual_output}'"
                return score, feedback
            
            return 0, f"Output does not match. Expected: '{expected_output}', Got: '{actual_output}'"
            
        except subprocess.TimeoutExpired:
            return 0, "Code execution timed out"
        except Exception as e:
            self.log(f"Output check failed: {str(e)}")
            return 0, f"Failed to check output: {str(e)}"

    def _post_to_notion(self, results: Dict) -> None:
        """Post results to Notion database"""
        try:
            if not all([self.notion_key, self.notion_grades_db, self.notion_students_db]):
                self.log("Skipping Notion post: missing credentials")
                return
                
            headers = {
                'Authorization': f'Bearer {self.notion_key}',
                'Content-Type': 'application/json',
                'Notion-Version': '2022-06-28'
            }
            
            # Get student email from Codio environment
            student_email = "unknown@example.com"
            if self.codio_env and 'student' in self.codio_env:
                student_email = self.codio_env.get('student', {}).get('email', student_email)
            
            # Get grade topic ID from config
            grade_topic_id = self.config.get('notion', {}).get('grade_topic_id', '')
            
            # Find student page in Notion
            student_page_id = self._find_student_in_notion(student_email)
            if not student_page_id:
                self.log(f"Student not found in Notion: {student_email}")
                return
            
            # Format properties according to config
            properties = {
                "Name": {"title": [{"text": {"content": self.config['assignment']['name']}}]},
                "Student": {"relation": [{"id": student_page_id}]},
                "Date": {"date": {"start": datetime.utcnow().isoformat()}},
                "Total": {"number": self.config['assignment']['points_possible']},
                "Score": {"number": results['total_score']},
                "Grade Topic": {"relation": [{"id": grade_topic_id}]}
            }
            
            # Add configurable properties if specified
            if 'properties' in self.config.get('notion', {}):
                for key, template in self.config['notion']['properties'].items():
                    if key in ["Name", "Student", "Date", "Total", "Score", "Grade Topic"]:
                        continue  # Skip built-in properties
                        
                    value = template
                    value = value

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

# Log Notion configuration if debug enabled
if DEBUG:
    log(f"Notion API Key: {NOTION_API_KEY[:5]}...{NOTION_API_KEY[-5:]}")
    log(f"Notion Grades DB: {NOTION_GRADES_DATABASE_ID}")
    log(f"Notion Students DB: {NOTION_STUDENTS_DATABASE_ID}")

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
        
    log(f"Notion credentials validated - proceeding with student lookup for {student_email}")

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
        log(f"Student not found in Notion database: {student_email}")
        return
        
    log(f"Found student in Notion: {student_email} with ID: {student_page_id[:8]}...")

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
    
    log(f"Creating Notion grade entry for {assignment_title} with score: {score}")
    response = requests.post("https://api.notion.com/v1/pages",
                  headers=headers, json=payload)
    
    if response.status_code == 200:
        log(f"Successfully created Notion grade entry")
    else:
        log(f"Notion API response: {response.status_code} - {response.text[:100]}...")
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
        # Prepend the appropriate emoji based on pass/fail
        feedback = "✅ " + feedback if passed else "❓ " + feedback
        
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

