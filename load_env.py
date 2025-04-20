import os, pathlib

def load(env_path: str = ".env", verbose: bool = True):
    p = pathlib.Path(env_path)
    if not p.exists():
        if verbose:
            print(f"[load_env] {env_path} not found – skipping.")
        raise FileNotFoundError
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
    if verbose:
        print(f"[load_env] variables from {env_path} loaded.")
