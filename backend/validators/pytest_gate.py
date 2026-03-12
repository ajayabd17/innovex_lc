import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


def _run_pytest(company_name: str, company_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run runtime pytest checks against generated payload.
    Returns a compact report and raises ValueError if checks fail.
    """
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    payload_path = out_dir / f"{company_name.replace(' ', '_')}_pytest_payload.json"
    payload_path.write_text(json.dumps(company_json, ensure_ascii=False), encoding="utf-8")

    env = os.environ.copy()
    env["GENERATED_PAYLOAD_PATH"] = str(payload_path.resolve())

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_runtime_generated_payload.py",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    report = {
        "passed": result.returncode == 0,
        "return_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "payload_path": str(payload_path),
    }

    return report


def run_pytest_verification(company_name: str, company_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run runtime pytest checks and raise if failed.
    """
    report = _run_pytest(company_name, company_json)
    if report["return_code"] != 0:
        msg = report["stdout"] or report["stderr"] or "Unknown pytest failure"
        raise ValueError(f"Pytest verification failed: {msg}")
    return report


def run_pytest_verification_report(company_name: str, company_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run runtime pytest checks and return report without raising.
    """
    return _run_pytest(company_name, company_json)


def extract_failed_fields_from_pytest_output(stdout: str, stderr: str) -> list[str]:
    """
    Best-effort field extraction from pytest/rule-engine failure text.
    Supports dict-like snippets containing 'field': 'x' or JSON-like "field":"x".
    """
    text = "\n".join([stdout or "", stderr or ""])
    fields = set()
    for pat in [
        r"""['"]field['"]\s*:\s*['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]""",
        r"""failed_conditions.*?['"]field['"]\s*:\s*['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]""",
    ]:
        for m in re.findall(pat, text, flags=re.DOTALL):
            fields.add(m)
    return sorted(fields)
