#!/usr/bin/env python3
"""Provider-neutral delegation contracts over the existing Open ASS supervisor.

The contract is not an authorization token. Host sandbox permissions, an
existing lifecycle task, explicit execution consent and independent CI remain
authoritative. No new scheduler or model gateway is introduced here.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath

try:
    from scripts import agents, context, harness, lifecycle, supervisor
except ModuleNotFoundError:
    import agents
    import context
    import harness
    import lifecycle
    import supervisor

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "openass.delegation.v1"
ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 256_000


class DelegationError(ValueError):
    pass


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise DelegationError("invalid delegation fields")
    return value


def _integer(value, name, upper):
    if type(value) is not int or not 1 <= value <= upper:
        raise DelegationError("invalid " + name)
    return value


def _path(value):
    if not isinstance(value, str) or len(value) > 500 or not value or "\\" in value or "\x00" in value:
        raise DelegationError("invalid relative scope path")
    if value == ".":
        return value
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value or
            any(part in ("", ".", "..") for part in value.split("/"))):
        raise DelegationError("scope path escapes project")
    return value


def _scopes(value):
    if not isinstance(value, list) or not (1 <= len(value) <= 50):
        raise DelegationError("one to 50 scope paths required")
    result = [_path(v) for v in value]
    if len(set(result)) != len(result):
        raise DelegationError("duplicate scope paths")
    return result


def _contains(parent, child):
    return any(p == "." or child == p or child.startswith(p + "/") for p in parent)


def capabilities():
    """Static adapter support plus the observed executable location."""
    return [
        {"harness": name, "executable": shutil.which(binary),
         "request_modes": ["read-only", "workspace-write"],
         "durable_supervisor_modes": ["workspace-write"],
         "continuation": "not-implemented",
         "trust": "native host controls; runtime version not tested here"}
        for name, binary in sorted(harness.HARNESSES.items())
    ]


def validate(data):
    """Fail closed on unknown fields and authority/budget/scope escalation."""
    _fields(data, ("schema", "id", "parent", "child"))
    if data["schema"] != SCHEMA or not isinstance(data["id"], str) or not ID.fullmatch(data["id"]):
        raise DelegationError("unsupported delegation schema or ID")
    p = _fields(data["parent"], ("id", "permission", "providers", "scopes", "budget_cents",
                                "timeout_seconds", "max_depth"))
    c = _fields(data["child"], ("task_id", "harness", "role", "permission", "scopes",
                               "budget_cents", "timeout_seconds", "depth", "criteria", "context"))
    if not isinstance(p["id"], str) or not ID.fullmatch(p["id"]):
        raise DelegationError("invalid parent task ID")
    if not isinstance(c["task_id"], str) or not ID.fullmatch(c["task_id"]) or c["task_id"] == p["id"]:
        raise DelegationError("invalid child task ID")
    permissions = ("read-only", "workspace-write")
    if p["permission"] not in permissions or c["permission"] not in permissions:
        raise DelegationError("unknown permission mode")
    if p["permission"] == "read-only" and c["permission"] != "read-only":
        raise DelegationError("child attempts to elevate read-only authority")
    if not isinstance(p["providers"], list) or not p["providers"] or len(p["providers"]) > 20:
        raise DelegationError("provider allowlist required")
    if any(not isinstance(v, str) or v not in harness.HARNESSES for v in p["providers"]):
        raise DelegationError("unsupported provider in allowlist")
    if len(set(p["providers"])) != len(p["providers"]):
        raise DelegationError("duplicate provider")
    if c["harness"] not in p["providers"]:
        raise DelegationError("child provider is not authorized by parent")
    if not isinstance(c["role"], str) or c["role"] not in agents.load()["roles"]:
        raise DelegationError("role is not declared in the shared role registry")
    parent_scopes, child_scopes = _scopes(p["scopes"]), _scopes(c["scopes"])
    if not all(_contains(parent_scopes, value) for value in child_scopes):
        raise DelegationError("child scope is not included in parent scope")
    parent_budget = _integer(p["budget_cents"], "parent budget", 10_000_000)
    child_budget = _integer(c["budget_cents"], "child budget", 10_000_000)
    if child_budget > parent_budget:
        raise DelegationError("child exceeds parent's budget allocation")
    parent_timeout = _integer(p["timeout_seconds"], "parent timeout", 3600)
    child_timeout = _integer(c["timeout_seconds"], "child timeout", 3600)
    if child_timeout > parent_timeout:
        raise DelegationError("child exceeds parent's time allocation")
    depth_limit = _integer(p["max_depth"], "maximum depth", 16)
    depth = _integer(c["depth"], "child depth", 16)
    if depth > depth_limit:
        raise DelegationError("delegation nesting depth exceeded")
    criteria = c["criteria"]
    if not isinstance(criteria, str) or not 8 <= len(criteria.strip()) <= 20_000:
        raise DelegationError("explicit acceptance criteria required")
    context = c["context"]
    if not isinstance(context, list) or len(context) > 40:
        raise DelegationError("context list must be bounded")
    for item in context:
        _fields(item, ("path", "sha256"))
        path = _path(item["path"])
        if not _contains(parent_scopes, path):
            raise DelegationError("context reference exceeds parent's authorized scope")
        if not isinstance(item["sha256"], str) or not SHA.fullmatch(item["sha256"]):
            raise DelegationError("context references require SHA-256 provenance")
    return data


def plan(data, snapshot=None):
    data = validate(data)
    c = data["child"]
    if snapshot is not None:
        if (snapshot["id"] != c["task_id"] or snapshot["state"] != "ready"
            or snapshot["criteria"] != c["criteria"]):
            raise DelegationError("child task and approved lifecycle criteria must match")
        if c["budget_cents"] > snapshot["budget"] - snapshot["spent"]:
            raise DelegationError("child exceeds remaining durable task budget")
    stage = agents.load()["roles"][c["role"]]["stage"]
    return {"status": "planned", "delegation_id": data["id"],
            "parent": data["parent"]["id"], "task": c["task_id"],
            "harness": c["harness"], "role": c["role"], "mode": c["permission"],
            "budget_cents": c["budget_cents"], "timeout_seconds": c["timeout_seconds"],
            "scope": c["scopes"], "context_refs": len(c["context"]),
            "icm_stage": stage,
            "supervised_run_available": c["permission"] == "workspace-write"
                                      and agents.load()["roles"][c["role"]]["mode"] == "write-branch",
            "note": "Planning is not permission. Context hashes are claims until independently verified."}


def dispatch(data, db, actor, *, execute=False, ack_unmetered=False,
             backend="local", container_image=None, executor=supervisor.run):
    """Use the existing stateful supervisor; never launch a separate executor."""
    request = validate(data)
    child = request["child"]
    snapshot = lifecycle.show(db, child["task_id"])
    result = plan(request, snapshot)
    if not execute:
        return result
    if not result["supervised_run_available"]:
        raise DelegationError("durable read-only/reviewer delegation not implemented")
    if not ack_unmetered:
        raise DelegationError("explicit unmetered runtime consent required")
    for item in child["context"]:
        try:
            source = context.confined_file(ROOT, item["path"])
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
        except (OSError, ValueError) as exc:
            raise DelegationError("context source cannot be independently verified") from exc
        if actual != item["sha256"]:
            raise DelegationError("context source hash changed or was misreported")
    if backend not in ("local", "container"):
        raise DelegationError("unknown execution backend")
    # The existing supervisor enforces clean nondefault branches, actual
    # lifecycle transitions, leases and bounded process capture.
    # Scope paths in this contract are advisory until a host sandbox/verified
    # write-set adapter can enforce them. Do not represent them as authority.
    outcome = executor(db, child["task_id"], child["harness"], child["role"], actor,
                       root=ROOT, timeout=child["timeout_seconds"],
                       reserve_cents=child["budget_cents"],
                       execute=True, ack_unmetered=True,
                       backend=backend, container_image=container_image)
    return {"delegation_id": request["id"], "parent": request["parent"]["id"],
            "task": child["task_id"], "execution": outcome,
            "accepted": False, "scope_enforced": False,
            "note": "Execution is not acceptance. Scope must be enforced by host sandbox and reviewed independently."}


def read_contract(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise DelegationError("contract file missing, symlinked or too large")
    return validate(json.loads(path.read_text(encoding="utf-8")))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("providers")
    plan_cmd = sub.add_parser("plan")
    plan_cmd.add_argument("contract", type=Path)
    plan_cmd.add_argument("--db", type=Path)
    run = sub.add_parser("run")
    run.add_argument("contract", type=Path)
    run.add_argument("--db", type=Path, default=lifecycle.DEFAULT_DB)
    run.add_argument("--actor", required=True)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--ack-unmetered", action="store_true")
    run.add_argument("--backend", choices=("local", "container"), default="local")
    run.add_argument("--container-image")
    args = p.parse_args(argv)
    try:
        if args.command == "providers":
            output = {"schema": SCHEMA, "providers": capabilities()}
        else:
            data = read_contract(args.contract)
            if args.command == "plan":
                if args.db:
                    with lifecycle.connect(args.db) as db:
                        output = plan(data, lifecycle.show(db, data["child"]["task_id"]))
                else:
                    output = plan(data)
            else:
                with lifecycle.connect(args.db) as db:
                    output = dispatch(data, db, args.actor, execute=args.execute,
                                      ack_unmetered=args.ack_unmetered,
                                      backend=args.backend, container_image=args.container_image)
        print(json.dumps(output, indent=2))
        return 0
    except (DelegationError, lifecycle.LifecycleError, supervisor.SupervisorError,
            ValueError, OSError) as exc:
        print("delegation: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
