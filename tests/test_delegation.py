"""Delegation: scope, provider, budget and lifecycle boundaries, without paid inference."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts import delegation, lifecycle

HASH = "a" * 64


def fixture():
    return {
        "schema": "openass.delegation.v1", "id": "delegate-001",
        "parent": {
            "id": "parent-001", "permission": "workspace-write",
            "providers": ["codex", "claude", "hermes"],
            "scopes": ["src", "docs"], "budget_cents": 250,
            "timeout_seconds": 120, "max_depth": 2
        },
        "child": {
            "task_id": "child-001", "harness": "codex", "role": "engineer",
            "permission": "workspace-write", "scopes": ["src/worker.py"],
            "budget_cents": 50, "timeout_seconds": 60, "depth": 1,
            "criteria": "Deliver a tested implementation that meets the contract.",
            "context": [{"path": "docs/plan.md", "sha256": HASH}]
        }
    }


class DelegationContractTests(unittest.TestCase):
    def mutate(self, change):
        data = fixture()
        change(data)
        with self.assertRaises(delegation.DelegationError):
            delegation.validate(data)

    def test_normalized_plan_is_provider_neutral(self):
        data = fixture()
        result = delegation.plan(data)
        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["parent"], "parent-001")
        self.assertEqual(result["task"], "child-001")
        self.assertTrue(result["supervised_run_available"])
        self.assertEqual(result["context_refs"], 1)
        self.assertEqual(result["icm_stage"], "implement")

    def test_parent_readonly_cannot_grant_write(self):
        self.mutate(lambda d: d["parent"].update(permission="read-only"))

    def test_child_cannot_change_harness(self):
        self.mutate(lambda d: d["child"].update(harness="unknown"))
        self.mutate(lambda d: d["child"].update(harness="outside-allowlist"))
        self.mutate(lambda d: d["parent"].update(providers=["claude"]))

    def test_parent_budget_and_time_bounds(self):
        self.mutate(lambda d: d["child"].update(budget_cents=251))
        self.mutate(lambda d: d["child"].update(timeout_seconds=121))
        self.mutate(lambda d: d["child"].update(depth=3))
        self.mutate(lambda d: d["child"].update(depth=True))
        self.mutate(lambda d: d["child"].update(budget_cents=False))

    def test_scope_traversal_and_unapproved_context(self):
        self.mutate(lambda d: d["child"].update(scopes=["../secrets"]))
        self.mutate(lambda d: d["child"].update(scopes=["src/../../.env"]))
        self.mutate(lambda d: d["child"].update(scopes=["private/data"]))
        self.mutate(lambda d: d["child"].update(scopes=["/etc/passwd"]))
        self.mutate(lambda d: d["child"].update(context=[{"path": ".env", "sha256": HASH}]))
        self.mutate(lambda d: d["child"].update(context=[{"path": "docs/plan.md", "sha256": "bad"}]))

    def test_contract_rejects_unknown_fields_and_invalid_identifiers(self):
        self.mutate(lambda d: d.update(extra="untrusted"))
        self.mutate(lambda d: d["child"].update(shell_args=["--dangerously-skip-permissions"]))
        self.mutate(lambda d: d["parent"].update(providers=["claude", "claude"]))
        self.mutate(lambda d: d["child"].update(task_id=d["parent"]["id"]))
        self.mutate(lambda d: d["child"].update(criteria=""))

    def test_no_automatic_depth_expansion(self):
        d = fixture()
        d["child"]["permission"] = "read-only"
        d["child"]["role"] = "reviewer"
        result = delegation.plan(d)
        self.assertFalse(result["supervised_run_available"])

    def test_real_task_criteria_and_remaining_budget_are_binding(self):
        d = fixture()
        state = {"id": "child-001", "state": "ready",
                 "criteria": d["child"]["criteria"], "budget": 60, "spent": 20}
        with self.assertRaisesRegex(delegation.DelegationError, "budget"):
            delegation.plan(d, state)
        state["spent"] = 0
        self.assertEqual(delegation.plan(d, state)["status"], "planned")
        state["criteria"] = "Someone changed the accepted specification"
        with self.assertRaisesRegex(delegation.DelegationError, "criteria"):
            delegation.plan(d, state)

    def test_dispatch_is_dry_run_first_with_durable_task(self):
        d = fixture()
        with tempfile.TemporaryDirectory() as folder:
            with lifecycle.connect(Path(folder) / "task.sqlite") as db:
                lifecycle.create(db, "child-001", 48, d["child"]["criteria"], 100, 2)
                lifecycle.transition(db, "child-001", "ready", "owner", 0)
                result = delegation.dispatch(d, db, "worker")
                self.assertEqual(result["status"], "planned")
                self.assertEqual(lifecycle.show(db, "child-001")["state"], "ready")
                self.assertEqual(lifecycle.show(db, "child-001")["spent"], 0)

    def test_dispatch_requires_consent_then_uses_existing_supervisor(self):
        d = fixture()
        d["child"]["context"] = []
        calls = []
        def fake_executor(*args, **kwargs):
            calls.append((args, kwargs))
            return {"status": "verifying", "exit_code": 0, "stdout_sha256": HASH}
        with tempfile.TemporaryDirectory() as folder:
            with lifecycle.connect(Path(folder) / "task.sqlite") as db:
                lifecycle.create(db, "child-001", 48, d["child"]["criteria"], 100, 2)
                lifecycle.transition(db, "child-001", "ready", "owner", 0)
                with self.assertRaisesRegex(delegation.DelegationError, "consent"):
                    delegation.dispatch(d, db, "worker", execute=True,
                                        executor=fake_executor)
                self.assertEqual(calls, [])
                result = delegation.dispatch(d, db, "worker", execute=True,
                         ack_unmetered=True, executor=fake_executor)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][0][1:5], ("child-001", "codex", "engineer", "worker"))
                self.assertEqual(calls[0][1]["reserve_cents"], 50)
                self.assertEqual(calls[0][1]["timeout"], 60)
                self.assertFalse(result["accepted"])
                self.assertFalse(result["scope_enforced"])

    def test_unverified_or_changed_context_never_reaches_executor(self):
        d = fixture()
        with tempfile.TemporaryDirectory() as folder:
            with lifecycle.connect(Path(folder) / "task.sqlite") as db:
                lifecycle.create(db, "child-001", 48, d["child"]["criteria"], 100)
                lifecycle.transition(db, "child-001", "ready", "owner", 0)
                called = []
                with self.assertRaisesRegex(delegation.DelegationError, "context"):
                    delegation.dispatch(d, db, "worker", execute=True,
                            ack_unmetered=True,
                            executor=lambda *args, **kwargs: called.append(1))
                self.assertEqual(called, [])
                self.assertEqual(lifecycle.show(db, "child-001")["state"], "ready")

    def test_readonly_cannot_launch_writable_supervisor(self):
        d = fixture()
        d["child"].update(permission="read-only", role="reviewer")
        self.assertEqual(delegation.plan(d)["icm_stage"], "verify")
        with tempfile.TemporaryDirectory() as folder:
            with lifecycle.connect(Path(folder) / "task.sqlite") as db:
                lifecycle.create(db, "child-001", 48, d["child"]["criteria"], 100)
                lifecycle.transition(db, "child-001", "ready", "owner", 0)
                with self.assertRaisesRegex(delegation.DelegationError, "not implemented"):
                    delegation.dispatch(d, db, "worker", execute=True,
                                        ack_unmetered=True, executor=lambda *a,**kw: None)

    def test_cli_providers_and_plan_no_side_effects(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "delegation.json"
            path.write_text(json.dumps(fixture()))
            self.assertEqual(delegation.main(["plan", str(path)]), 0)
            self.assertEqual(delegation.main(["providers"]), 0)
            self.assertFalse((Path(folder) / "tasks.sqlite").exists())

    def test_rejects_symlinked_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "real.json"
            file.write_text(json.dumps(fixture()))
            alias = Path(folder) / "alias.json"
            alias.symlink_to(file)
            with self.assertRaises(delegation.DelegationError):
                delegation.read_contract(alias)


if __name__ == "__main__":
    unittest.main()
