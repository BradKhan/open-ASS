# Risk, permissions and acceptance policy

## Risk classes
- fast: bounded, reversible documentation or low-impact change. Issue optional when traceable PR description and reproducible verification are supplied. Review and required checks still apply.
- standard: application code, features, dependencies, and significant defects. Issue/spec or accepted contract, relevant tests and independent review.
- critical: authorization, payments, personal data, infrastructure, destructive changes or other high-impact work. Add threat review, negative tests, recovery plan and explicit owner approval.

Risk can be raised by any reviewer. Lowering risk requires owner approval recorded against the issue.

## Authorized actions
Agents may read code, edit isolated branches, run scoped tests and submit PRs. Agents may not disable required checks, change branch protections, alter approval roles, raise spending limits or approve their own work. Production deployment, irreversible actions and privilege changes require approval.

## Acceptance
Require a traceable change, testable criteria where behavior changes, current-head CI, applicable independent review and authorized merge. Standard and critical human PRs require an issue; bounded fast documentation changes may use the PR itself. For authenticated Dependabot GitHub Actions pin updates, the policy gate verifies the precise one-file, one-line pinned update and assigns critical risk without inventing an issue or agent-written security-review narrative. This **does not approve or merge** the change; CI, supply-chain inspection and GitHub rulesets still apply.

The risk classifier is conservative across common source trees and language manifests. Unknown file types are standard by default. High-impact domains and organization/project overlays need further implementation, so this is a baseline, not an industry compliance certification. Tests passing are necessary but do not prove UX or business correctness.

## Execution limits
Set budgets, retry ceilings and timeouts in real orchestration controls, not merely prompts. Use idempotent task claims, leases, unique run IDs and reconciliation to recover from interrupted execution.
