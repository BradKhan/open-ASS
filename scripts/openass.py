#!/usr/bin/env python3
"""One entry point for Open ASS. Zero additional runtime dependencies."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {"verify": "verify.py", "init": "init_project.py",
           "context": "context.py", "agents": "agents.py", "skills": "skills.py",
           "pr-check": "pr_gate.py", "security": "security_baseline.py",
           "attest": "attest.py", "bootstrap": "project_setup.py", "role-sync": "role_sync.py", "task": "lifecycle.py", "harness": "harness.py", "quality": "product_quality.py", "evaluate": "adversarial_eval.py", "browser": "browser_probe.py", "readiness": "readiness.py", "run": "supervisor.py", "github-admin": "github_admin.py", "harness-check": "harness_compat.py", "live-smoke": "live_smoke.py", "dispatch": "dispatch.py", "activate": "activation.py", "bench": "eval_suite.py", "delegate": "delegation.py"}


def run(path, args=()):
    return subprocess.call([sys.executable, str(ROOT / "scripts" / path), *args], cwd=ROOT)


def hook(operation):
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git is required for local hooks")
    config = subprocess.run([git, "config", "--local", "--get", "core.hooksPath"],
                            cwd=ROOT, capture_output=True, text=True, check=False)
    existing = config.stdout.strip()
    if operation == "status":
        print("Git hooks: " + (existing or "not configured"))
        return 0
    if operation == "install":
        if existing and existing != ".githooks":
            raise RuntimeError("existing custom hooks directory; refusing to overwrite: " + existing)
        p = subprocess.run([git, "config", "--local", "core.hooksPath", ".githooks"], cwd=ROOT)
        if p.returncode:
            return p.returncode
        print("Enabled opt-in Git hooks (.githooks). CI remains authoritative.")
        return 0
    if existing != ".githooks":
        raise RuntimeError("Open ASS hooks are not enabled")
    return subprocess.call([git, "config", "--local", "--unset", "core.hooksPath"], cwd=ROOT)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=[*SCRIPTS, "doctor", "hooks", "mcp"])
    p.add_argument("rest", nargs=argparse.REMAINDER)
    args = p.parse_args()
    rest = args.rest
    try:
        if args.command in SCRIPTS:
            return run(SCRIPTS[args.command], rest)
        if args.command == "doctor":
            result = run("doctor.py")
            for name in ("agents.py", "skills.py", "context.py", "security_baseline.py"):
                result = max(result, run(name, ["check"] if name != "security_baseline.py" else []))
            result = max(result, hook("status"))
            return result
        if args.command == "hooks":
            if rest not in (["install"], ["status"], ["uninstall"]):
                raise RuntimeError("usage: openass.py hooks install|status|uninstall")
            return hook(rest[0])
        if args.command == "mcp" and rest == ["serve"]:
            return run("mcp_server.py")
        raise RuntimeError("usage: openass.py mcp serve")
    except RuntimeError as exc:
        print("openass: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
