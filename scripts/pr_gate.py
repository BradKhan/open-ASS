#!/usr/bin/env python3
"""CI PR risk declaration and sensitive-file escalation.

GitHub branch rulesets MUST independently enforce checks/review/merge rights.
A PR author can edit their PR body; this is a gate, not authorization.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RANK = {"fast": 0, "standard": 1, "critical": 2}
SENSITIVE = (".github/workflows/", ".github/CODEOWNERS", "config/", ".mcp.json",
             ".codex/", ".claude/agents/", ".githooks/",
             "AGENTS.md", "POLICY.md", "SECURITY.md",
             "integrations/skills.lock.json", "integrations/hermes-hooks.example.yaml",
             "scripts/pr_gate.py", "scripts/attest.py", "scripts/hermes_hook.py",
             "scripts/security_baseline.py", "scripts/verify.py",
             "scripts/skills.py", "scripts/mcp_server.py", "scripts/hook_gate.py",
             "scripts/agents.py", "scripts/context.py")
CODE = ("scripts/", "tests/", ".agents/", "contracts/", "context/", "integrations/",
        "src/", "app/", "server/", "worker/", "lib/", "packages/", "cmd/", "internal/",
        "api/", "web/", "frontend/", "backend/", "bin/", "crates/", "pkg/", "services/")
SOURCE_EXT = (".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".rs",
              ".go", ".java", ".kt", ".swift", ".c", ".cc", ".cpp", ".h",
              ".cs", ".rb", ".php", ".scala", ".sql", ".sh", ".bash", ".ps1")
MANIFESTS = {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
             "pyproject.toml", "requirements.txt", "requirements-dev.txt", "poetry.lock",
             "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "Gemfile",
             "Gemfile.lock", "pom.xml", "build.gradle", "Dockerfile",
             "docker-compose.yml", "Makefile", "justfile"}
DEPENDABOT_PIN = re.compile(
    r"^\s*uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([a-f0-9]{40})"
    r"\s+#\s*v[0-9][0-9A-Za-z.+-]*\s*$"
)
RISK = re.compile(r"(?im)^\s*Risk(?: class)?\s*:\s*(fast|standard|critical)\s*$")
ISSUE = re.compile(r"(?im)^\s*Issue\s*:\s*(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#([1-9][0-9]*)\s*$")


class GateError(ValueError):
    pass


def required_risk(paths):
    if not isinstance(paths, list) or not paths:
        raise GateError("cannot determine PR changes")
    minimum = "fast"
    for path in paths:
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
            raise GateError("unsafe PR path")
        if path.startswith(SENSITIVE) or re.search(r"(^|/)(auth|payment|permissions|secrets|credentials)(/|[._-])", path, re.I):
            return "critical"
        basename = path.rsplit("/", 1)[-1]
        if path.startswith(CODE) or basename in MANIFESTS or path.lower().endswith(SOURCE_EXT) \
                or path in ("AGENTS.md", "ARCHITECTURE.md", "justfile"):
            minimum = "standard"
        elif not (path.startswith(("docs/", ".github/ISSUE_TEMPLATE/"))
                  or path.lower().endswith((".md", ".markdown", ".rst", ".txt"))
                  or basename in ("LICENSE", "NOTICE", ".gitignore")):
            minimum = "standard"
    return minimum


def trusted_dependabot(pull, changed, diff_text):
    """Only accept a real GitHub Bot PR from this repository with one pinned Actions change.

    No approval or merge is implied. This path exists solely to avoid fictional
    issue/review declarations from unattended dependency update automation.
    """
    if not isinstance(pull, dict) or not isinstance(diff_text, str):
        return False
    user = pull.get("user") or {}
    head, base = pull.get("head") or {}, pull.get("base") or {}
    if (user.get("login") != "dependabot[bot]" or user.get("type") != "Bot"
        or not str(head.get("ref", "")).startswith("dependabot/github_actions/")
        or (head.get("repo") or {}).get("full_name") !=
           (base.get("repo") or {}).get("full_name")):
        return False
    if len(changed) != 1 or not re.fullmatch(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml", changed[0]):
        return False
    removed, added = [], []
    for line in diff_text.splitlines():
        if line.startswith(("---", "+++")) or line.startswith(("diff --git", "@@", "index ")):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    if len(removed) != 1 or len(added) != 1:
        return False
    old, new = DEPENDABOT_PIN.fullmatch(removed[0]), DEPENDABOT_PIN.fullmatch(added[0])
    return bool(old and new and old.group(1) == new.group(1)
                and old.group(2) != new.group(2))


def check(body, changed, initialized=False, security_command=None, automation=None):
    if not isinstance(body, str):
        raise GateError("missing PR body")
    required = required_risk(changed)
    if automation == "verified-dependabot-actions":
        if required != "critical":
            raise GateError("dependency automation cannot reduce risk classification")
        return {"issue": None, "declared": "critical", "minimum": required,
                "paths": len(changed), "automation": automation,
                "note": "Pinned dependency diff validated; no review, CI, or merge authority granted."}
    risks = RISK.findall(body)
    links = ISSUE.findall(body)
    if len(risks) != 1:
        raise GateError("PR must contain exactly one 'Risk: fast|standard|critical'")
    risk = risks[0].lower()
    if len(links) != 1 and (risk != "fast" or required != "fast" or len(links) > 1):
        raise GateError("standard and critical PRs require exactly one 'Issue: #number'")
    if RANK[risk] < RANK[required]:
        raise GateError("declared risk " + risk + " is below required " + required)
    if initialized and risk == "critical" and not security_command:
        raise GateError("critical application PR requires configured application security checks")
    if not re.search(r"(?im)^\s*Verification\s*:", body):
        raise GateError("PR needs a Verification: line with reproducible evidence")
    if risk == "critical" and not re.search(r"(?im)^\s*Security review\s*:", body):
        raise GateError("critical PR needs Security review: independent reviewer/evidence")
    return {"issue": int(links[0]) if links else None, "declared": risk, "minimum": required, "paths": len(changed),
            "note": "PR metadata validation is not independent approval."}


def git_changes(base, head):
    if not all(isinstance(s, str) and re.fullmatch("[a-f0-9]{40}", s) for s in (base, head)):
        raise GateError("invalid PR Git revisions")
    cmd = ["git", "diff", "--name-only", "-z", base + "..." + head]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True)
    if p.returncode:
        raise GateError("cannot determine PR changed files: " + p.stderr.decode(errors="replace")[:200])
    return [x.decode() for x in p.stdout.split(b"\x00") if x]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event", required=True, help="GitHub pull_request event JSON")
    a = p.parse_args()
    try:
        event = json.loads(Path(a.event).read_text())
        pull = event.get("pull_request")
        if not isinstance(pull, dict):
            raise GateError("not a pull_request event")
        changed = git_changes(pull["base"]["sha"], pull["head"]["sha"])
        config = json.loads((ROOT / "config/project.json").read_text())
        settings = config.get("verification", {})
        diff = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--unified=0",
             pull["base"]["sha"] + "..." + pull["head"]["sha"], "--", *changed],
            cwd=ROOT, capture_output=True, text=True, check=False)
        if diff.returncode:
            raise GateError("cannot inspect dependency diff")
        automation = ("verified-dependabot-actions" if trusted_dependabot(pull, changed, diff.stdout)
                      else None)
        if (pull.get("user") or {}).get("login") == "dependabot[bot]" and not automation:
            raise GateError("unrecognized bot change; explicit human review metadata required")
        result = check(pull.get("body"), changed,
                       config.get("initialized") is True,
                       settings.get("security_command"), automation)
        print(json.dumps(result, indent=2))
    except (GateError, OSError, KeyError, ValueError, TypeError) as exc:
        print("pr-gate: " + str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
