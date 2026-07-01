import subprocess
import re
import sys

# Regex pattern to match sensitive API keys and tokens in git history
SECRET_PATTERNS = {
    "NVIDIA API Key": re.compile(r"nvapi-[a-zA-Z0-9_-]+"),
    "OpenAI API Key": re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),
    "Bearer Token": re.compile(r"Bearer\s+[a-zA-Z0-9\._-]+"),
}

def scan_git_history():
    print("Initializing Git History Security Scan...")
    try:
        # Fetch the full git patch history log
        result = subprocess.run(
            ["git", "log", "-p", "--all"],
            capture_output=True,
            text=True,
            check=True
        )
    except FileNotFoundError:
        print("WARNING: Git CLI is not installed or this is not a git repository. Skipping scan.")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"WARNING: Git log command failed: {e}. Skipping scan.")
        return 0

    log_data = result.stdout
    findings = []
    current_commit = "unknown"
    current_author = "unknown"

    # Analyze git output line-by-line
    for line in log_data.splitlines():
        if line.startswith("commit "):
            current_commit = line.split()[1]
        elif line.startswith("Author: "):
            current_author = line[8:].strip()
        
        # Check added lines in patches
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:].strip()
            for key_type, pattern in SECRET_PATTERNS.items():
                match = pattern.search(content)
                if match:
                    # Ignore placeholder matches to prevent false positives
                    matched_str = match.group(0)
                    if "your-key" in matched_str or "xxxx" in matched_str or "generate-strong" in matched_str:
                        continue
                    findings.append({
                        "commit": current_commit,
                        "author": current_author,
                        "type": key_type,
                        "leak": matched_str[:12] + "..."
                    })

    if findings:
        print("\n" + "=" * 50)
        print("CRITICAL SECURITY VULNERABILITY DETECTED!")
        print("Exposed secrets were found in git history:")
        print("=" * 50)
        for idx, f in enumerate(findings, 1):
            print(f"[{idx}] Commit: {f['commit']}")
            print(f"    Author: {f['author']}")
            print(f"    Type: {f['type']}")
            print(f"    Leaked Preview: {f['leak']}")
        print("\n" + "=" * 50)
        print("ACTION REQUIRED:")
        print("1. IMMEDIATELY rotate all exposed API credentials.")
        print("2. Use git-filter-repo or BFG Repo-Cleaner to permanently purge these secrets from git history.")
        print("=" * 50)
        return 1

    print("SUCCESS: No exposed secrets detected in Git history.")
    return 0

if __name__ == "__main__":
    sys.exit(scan_git_history())
