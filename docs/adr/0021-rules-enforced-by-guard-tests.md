# 0021. Enforce the rules with guard tests and one check command

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

The rules in `AGENTS.md` protect people's keys and TVs, and many contributions come through AI tools. A rule that's only
written down depends on being read.

## Decision

- **Guard tests.** `tests/test_guards.py` turns every rule a test can check into a test. They read the source or call the
  app in-process, and their failure messages name the rule. Changing one is a design decision, and it needs an issue first.
- **One command.** `scripts/check.py` runs the same checks for people, AI agents and CI. CI adds gitleaks and starting the
  Docker image.
- **No linter or formatter.** Match the file you're in. Reformatting isn't welcome.
- **Closer review.** `.github/CODEOWNERS` marks security-critical files.

## Consequences

- Someone who hasn't read the rules still can't break them by accident, at least the checkable ones.
- Guards read source patterns, so a refactor can trip them, and they can't see everything. Review still has to look for
  `esc()`.
- Allowlists in the guards, such as `STATE_HTTP_OK` and `OUTSIDE_HOSTS`, make each exception visible in a diff.
- With no linter, style stays a matter for review.

## Alternatives

**Inferred:** review alone wouldn't scale or catch every slip. Not on record as having been weighed.

## Where it lives

`tests/test_guards.py`, `scripts/check.py`, `.github/workflows/ci.yml`, `.github/CODEOWNERS`.
