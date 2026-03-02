# actions/dev_agent.py
# AI-powered development agent — plans, builds, and debugs full projects.
#
# Flow:
#   Describe project → Gemini plans file structure → Files written one by one
#   → VSCode opened → Entry point executed → Error? → Identify file → Fix → Retry
#   → Speaks only when done (success or failure)
#
# Models:
#   Planning : gemini-2.5-flash       (architecture, structure, debugging)
#   Writing  : gemini-2.5-flash-lite  (fast file generation)

import subprocess
import sys
import json
import re
import time
from pathlib import Path

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR           = get_base_dir()
API_CONFIG_PATH    = BASE_DIR / "config" / "api_keys.json"
PROJECTS_DIR       = Path.home() / "Desktop" / "JarvisProjects"
MAX_FIX_ATTEMPTS   = 4
MODEL_PLANNER      = "gemini-2.5-flash"
MODEL_WRITER       = "gemini-2.5-flash-lite"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_model(model_name: str):
    import google.generativeai as genai
    genai.configure(api_key=_get_api_key())
    return genai.GenerativeModel(model_name)


def _clean_code(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _clean_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _is_rate_limit(error: Exception) -> bool:
    return "429" in str(error) or "quota" in str(error).lower()


def _get_interpreter(path: Path) -> list[str] | None:
    return {
        ".py":  [sys.executable],
        ".js":  ["node"],
        ".ts":  ["ts-node"],
        ".sh":  ["bash"],
        ".ps1": ["powershell", "-File"],
        ".rb":  ["ruby"],
        ".php": ["php"],
    }.get(path.suffix.lower())


def _has_error(output: str) -> bool:
    if "timed out" in output.lower():
        return False
    signals = ["error", "exception", "traceback", "syntaxerror",
               "nameerror", "typeerror", "importerror", "stderr", "failed"]
    return any(s in output.lower() for s in signals)

def _identify_error_file(error_output: str, project_files: list[str]) -> str | None:
    """
    Try to find which file caused the error from traceback.
    Returns filename or None.
    """
    for line in error_output.splitlines():
        for f in project_files:
            if Path(f).name in line or f in line:
                return f
    return None

def _plan_project(description: str, language: str) -> dict:
    """
    Ask Gemini to plan the full project structure.

    Returns:
    {
        "project_name": "my_app",
        "entry_point": "main.py",
        "files": [
            {
                "path": "main.py",
                "description": "Entry point, starts the app"
            },
            {
                "path": "utils/helpers.py",
                "description": "Utility functions"
            }
        ],
        "run_command": "python main.py",
        "dependencies": ["requests", "flask"]
    }
    """
    model = _get_model(MODEL_PLANNER)

    prompt = f"""You are a senior software architect.
Plan the complete file structure for the following project.

Language: {language}
Description: {description}

Return ONLY a valid JSON object with this exact structure:
{{
  "project_name": "short_snake_case_name",
  "entry_point": "main.py",
  "files": [
    {{"path": "main.py", "description": "what this file does"}},
    {{"path": "utils/helpers.py", "description": "what this file does"}}
  ],
  "run_command": "python main.py",
  "dependencies": ["package1", "package2"]
}}

Rules:
- Keep it simple. Only include files that are truly necessary.
- No explanation, no markdown, no backticks. Pure JSON only.
- Entry point must be one of the files listed.
- Use relative paths only.

JSON:"""

    try:
        response = model.generate_content(prompt)
        raw = _clean_json(response.text)
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Planner returned invalid JSON: {e}\nRaw: {response.text[:300]}")


def _write_file(
    file_path: str,
    file_description: str,
    project_description: str,
    all_files: list[dict],
    language: str,
    project_dir: Path
) -> str:
    """Write one file. Returns the generated code."""
    model = _get_model(MODEL_WRITER)

    file_list = "\n".join(
        f"  - {f['path']}: {f['description']}" for f in all_files
    )

    prompt = f"""You are an expert {language} developer.
Write the code for ONE specific file in a larger project.

Project goal: {project_description}

All files in this project:
{file_list}

Now write ONLY the file: {file_path}
Purpose of this file: {file_description}

Rules:
- Output ONLY the code for this file. No explanation, no markdown, no backticks.
- Import from other project files using relative imports where needed.
- Add helpful inline comments.
- Handle errors properly.
- Use modern best practices.

Code for {file_path}:"""

    try:
        response = model.generate_content(prompt)
        code = _clean_code(response.text)

        # Save file
        full_path = project_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code, encoding="utf-8")

        print(f"[DevAgent] ✅ Written: {file_path}")
        return code

    except Exception as e:
        if _is_rate_limit(e):
            raise RateLimitError(str(e))
        raise


def _install_dependencies(dependencies: list[str], project_dir: Path) -> str:
    if not dependencies:
        return "No dependencies to install."

    print(f"[DevAgent] 📦 Installing: {dependencies}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + dependencies,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=120, cwd=str(project_dir)
        )
        if result.returncode == 0:
            return f"Installed: {', '.join(dependencies)}"
        return f"Install warning: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "Dependency install timed out."
    except Exception as e:
        return f"Install error: {e}"


def _open_vscode(project_dir: Path) -> bool:
    vscode_paths = [
        "code",
        r"C:\Users\{}\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd".format(
            Path.home().name
        ),
    ]
    for cmd in vscode_paths:
        try:
            subprocess.Popen(
                [cmd, str(project_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True  
            )
            time.sleep(2)
            print(f"[DevAgent] 💻 VSCode opened: {project_dir}")
            return True
        except Exception:
            continue
    print("[DevAgent] ⚠️ VSCode not found.")
    return False


def _run_project(run_command: str, project_dir: Path, timeout: int = 30) -> str:
    """Run the project entry point, return output."""
    print(f"[DevAgent] 🚀 Running: {run_command}")

    try:
        parts = run_command.split()
        if parts[0] == "python":
            parts[0] = sys.executable

        result = subprocess.run(
            parts,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(project_dir)
        )

        output = result.stdout.strip()
        error  = result.stderr.strip()

        parts_out = []
        if output: parts_out.append(f"Output:\n{output}")
        if error:  parts_out.append(f"Stderr:\n{error}")
        return "\n\n".join(parts_out) if parts_out else "Ran with no output."

    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s. (Long-running app may be working fine.)"
    except FileNotFoundError as e:
        return f"Command not found: {e}"
    except Exception as e:
        return f"Run error: {e}"

def _fix_file(
    file_path: str,
    current_code: str,
    error_output: str,
    project_description: str,
    all_files: list[dict],
    language: str,
    project_dir: Path
) -> str:
    """Ask Gemini to fix a specific file based on error output."""
    model = _get_model(MODEL_PLANNER)

    file_list = "\n".join(
        f"  - {f['path']}: {f['description']}" for f in all_files
    )

    prompt = f"""You are an expert {language} debugger.
Fix the file below. It caused an error when the project was run.

Project goal: {project_description}

All files in this project:
{file_list}

File to fix: {file_path}

Error output:
{error_output[:3000]}

Current code:
{current_code}

Return ONLY the fixed code — no explanation, no markdown, no backticks.

Fixed code:"""

    try:
        response = model.generate_content(prompt)
        fixed = _clean_code(response.text)

        full_path = project_dir / file_path
        full_path.write_text(fixed, encoding="utf-8")

        print(f"[DevAgent] 🔧 Fixed: {file_path}")
        return fixed

    except Exception as e:
        if _is_rate_limit(e):
            raise RateLimitError(str(e))
        raise

class RateLimitError(Exception):
    pass
def _build_project(
    description: str,
    language: str,
    project_name: str,
    timeout: int,
    speak=None,
    player=None
) -> str:
    """
    Full build loop:
    Plan → Write files → Install deps → Open VSCode → Run → Fix loop
    """

    def log(msg: str):
        print(f"[DevAgent] {msg}")
        if player:
            player.write_log(f"[DevAgent] {msg}")

    log("Planning project structure...")
    try:
        plan = _plan_project(description, language)
    except RateLimitError:
        msg = "You have reached the rate limit, sir. Please try again shortly."
        if speak: speak(msg)
        return msg
    except ValueError as e:
        msg = f"Planning failed: {e}"
        if speak: speak(msg)
        return msg

    proj_name = project_name or plan.get("project_name", "jarvis_project")
    proj_name = re.sub(r"[^\w\-]", "_", proj_name)
    project_dir = PROJECTS_DIR / proj_name
    project_dir.mkdir(parents=True, exist_ok=True)

    files       = plan.get("files", [])
    entry_point = plan.get("entry_point", "main.py")
    run_command = plan.get("run_command", f"python {entry_point}")
    dependencies = plan.get("dependencies", [])

    log(f"Project: {proj_name} | Files: {len(files)} | Entry: {entry_point}")

    file_codes: dict[str, str] = {}

    for file_info in files:
        file_path = file_info.get("path", "")
        file_desc = file_info.get("description", "")
        if not file_path:
            continue

        log(f"Writing {file_path}...")
        try:
            code = _write_file(
                file_path, file_desc, description,
                files, language, project_dir
            )
            file_codes[file_path] = code
        except RateLimitError:
            msg = "You have reached the rate limit, sir. Please try again shortly."
            if speak: speak(msg)
            return msg
        except Exception as e:
            log(f"Failed to write {file_path}: {e}")
            continue

    if not file_codes:
        msg = "I could not write any files for this project, sir."
        if speak: speak(msg)
        return msg

    if dependencies:
        log(f"Installing dependencies: {dependencies}")
        _install_dependencies(dependencies, project_dir)

    _open_vscode(project_dir)

    last_output = ""
    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        log(f"Running project (attempt {attempt}/{MAX_FIX_ATTEMPTS})...")

        last_output = _run_project(run_command, project_dir, timeout)
        log(f"Output: {last_output[:150]}")

        if not _has_error(last_output):
            msg = (
                f"Project '{proj_name}' is working, sir. "
                f"Built in {attempt} attempt{'s' if attempt > 1 else ''}. "
                f"Opened in VSCode at {project_dir}."
            )
            if speak: speak(msg)
            return f"{msg}\n\nOutput:\n{last_output}"

        if attempt == MAX_FIX_ATTEMPTS:
            break

        error_file = _identify_error_file(last_output, list(file_codes.keys()))
        if not error_file:
            error_file = entry_point

        log(f"Error in '{error_file}', fixing...")

        try:
            fixed = _fix_file(
                error_file,
                file_codes.get(error_file, ""),
                last_output,
                description,
                files,
                language,
                project_dir
            )
            file_codes[error_file] = fixed
        except RateLimitError:
            msg = "You have reached the rate limit, sir. Please try again shortly."
            if speak: speak(msg)
            return msg
        except Exception as e:
            log(f"Fix failed: {e}")

    msg = (
        f"I was unable to get '{proj_name}' working after {MAX_FIX_ATTEMPTS} attempts, sir. "
        f"The project is saved at {project_dir} — you can open it in VSCode and check manually."
    )
    if speak: speak(msg)
    return f"{msg}\n\nLast error:\n{last_output[:500]}"

def dev_agent(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None
) -> str:
    """
    Called from main.py.

    parameters:
        description  : What the project should do (required)
        language     : Programming language (default: python)
        project_name : Optional folder name (auto-generated if not given)
        timeout      : Run timeout in seconds (default: 30)
    """
    p            = parameters or {}
    description  = p.get("description", "").strip()
    language     = p.get("language", "python").strip()
    project_name = p.get("project_name", "").strip()
    timeout      = int(p.get("timeout", 30))

    if not description:
        return "Please describe the project you want me to build, sir."

    return _build_project(
        description  = description,
        language     = language,
        project_name = project_name,
        timeout      = timeout,
        speak        = speak,
        player       = player
    )