import subprocess
import sys
import os
from fastapi import APIRouter

router = APIRouter()

last_test_result = {
    "status": "NOT_RUN",
    "passed": 0,
    "failed": 0,
    "total": 0,
    "output": "",
    "timestamp": None,
}


@router.post("/tests/run")
def run_self_tests():
    """
    Run test_core.py and test_live_simulation.py and return PASS/FAIL breakdown.
    """
    global last_test_result
    output_lines = []
    passed = 0
    failed = 0

    scripts = ["test_core.py", "test_live_simulation.py"]
    for s in scripts:
        cmd = [sys.executable, s]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=".")
        output_lines.append(f"=== RUNNING {s} ===")
        output_lines.append(res.stdout)
        for line in res.stdout.splitlines():
            if "[PASS]" in line:
                passed += 1
            elif "[FAIL]" in line:
                failed += 1

    total = passed + failed
    status = "SUCCESS" if failed == 0 and total > 0 else ("FAILURE" if failed > 0 else "UNKNOWN")

    last_test_result = {
        "status": status,
        "passed": passed,
        "failed": failed,
        "total": total,
        "output": "\n".join(output_lines),
    }
    return last_test_result


@router.get("/tests/status")
def get_test_status():
    return last_test_result
