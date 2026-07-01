import subprocess
import json
import sys
import os

def parse_and_report(result) -> int:
    if result.returncode == 0:
        print("SUCCESS: No dependency vulnerabilities detected in requirements.txt.")
        return 0

    try:
        audit_data = json.loads(result.stdout)
    except Exception:
        print("Vulnerabilities detected. Raw pip-audit output:")
        print(result.stdout)
        print(result.stderr)
        return 1

    dependencies = audit_data.get("dependencies", [])
    vulnerable_count = 0
    
    print("\n" + "=" * 80)
    print(f"{'PACKAGE':<22} | {'VERSION':<10} | {'CVE ID':<15} | {'FIX VERSIONS':<20}")
    print("=" * 80)
    
    for dep in dependencies:
        vulns = dep.get("vulns", [])
        if vulns:
            vulnerable_count += len(vulns)
            name = dep.get("name")
            version = dep.get("version")
            for vuln in vulns:
                cve_id = vuln.get("id", "N/A")
                fix_versions = ", ".join(vuln.get("fix_versions", [])) or "None"
                print(f"{name:<22} | {version:<10} | {cve_id:<15} | {fix_versions:<20}")

    print("=" * 80)
    print(f"CRITICAL AUDIT REPORT: Found {vulnerable_count} dependency vulnerabilities.")
    print("Please upgrade the affected packages to the fixed versions.")
    print("=" * 80 + "\n")
    return 1

def audit_dependencies():
    print("Initializing Dependency Security Audit...")
    
    # 1. Try executing inside Docker container first
    try:
        check_container = subprocess.run(
            ["docker-compose", "ps", "rag-api"],
            capture_output=True,
            text=True
        )
        if "rag-api" in check_container.stdout and "Up" in check_container.stdout:
            print("Active rag-api container detected. Running pip-audit inside Docker...")
            
            # Ensure pip-audit is installed in the container
            subprocess.run(
                ["docker-compose", "exec", "-T", "-u", "root", "rag-api", "pip", "install", "pip-audit"],
                capture_output=True
            )
            
            # Execute audit inside the container
            result = subprocess.run(
                ["docker-compose", "exec", "-T", "-u", "appuser", "rag-api", "pip-audit", "-r", "requirements.txt", "--format", "json"],
                capture_output=True,
                text=True
            )
            return parse_and_report(result)
    except Exception as e:
        print(f"Docker execution check bypassed: {str(e)}. Falling back to local host scan.")

    # 2. Local fallback scan with --no-deps to prevent compiling native modules on Windows
    paths_to_try = [
        "pip-audit",
        os.path.join(os.environ.get("APPDATA", ""), r"Python\Python313\Scripts\pip-audit.exe"),
        os.path.join(os.environ.get("APPDATA", ""), r"Python\Python313\Scripts\pip-audit"),
        os.path.expanduser(r"~\AppData\Roaming\Python\Python313\Scripts\pip-audit.exe"),
        os.path.expanduser(r"~\AppData\Roaming\Python\Python313\Scripts\pip-audit")
    ]
    
    result = None
    for path in paths_to_try:
        try:
            result = subprocess.run(
                [path, "-r", "requirements.txt", "--no-deps", "--format", "json"],
                capture_output=True,
                text=True
            )
            break
        except FileNotFoundError:
            continue

    if result is None:
        print("ERROR: 'pip-audit' command is not installed or not found on search paths.")
        print("Please run 'pip install pip-audit' first.")
        return 1

    return parse_and_report(result)

if __name__ == "__main__":
    sys.exit(audit_dependencies())
