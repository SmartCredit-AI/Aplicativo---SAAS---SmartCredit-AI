---
name: code-review
description: 'Review code changes for bugs, security risks, regressions, missing tests, and maintainability problems. Use when the user asks for a code review, PR review, diff review, risk assessment, or review checklist.'
argument-hint: 'What files, diff, pull request, or behavior should be reviewed?'
user-invocable: true
---

# Code Review

## When to Use

- Review a pull request, diff, commit, or selected files.
- Look for behavioral regressions, security risks, and missing tests.
- Assess whether an implementation satisfies a stated requirement.

## Procedure

1. Establish scope from the request and inspect the changed files, nearby callers, and relevant tests.
2. Trace the changed behavior far enough to identify inputs, state changes, error paths, and external boundaries.
3. Check for correctness first, then security, compatibility, performance, and maintainability risks.
4. Validate important findings with the narrowest available test, type check, linter, or reproducible example.
5. Report findings first, ordered by severity. Each finding must include the file, the affected code, why it matters, and a concrete fix direction.
6. Separate confirmed findings from open questions and assumptions.
7. End with a concise summary and remaining test gaps. If no issues are found, say so explicitly and name residual risks.

## Decision Rules

- Report only actionable issues supported by the code or a reproducible check.
- Treat user-visible breakage, data loss, authorization failures, and security vulnerabilities as highest priority.
- Do not report style preferences unless they create a real defect or violate an established project convention.
- Do not expand into unrelated pre-existing problems unless the change worsens them.
- Prefer a focused review over broad repository exploration when the changed behavior is clear.

## Completion Criteria

- The review scope and validation performed are stated.
- Findings are severity-ordered and grounded in file references.
- Important claims have a test, diagnostic, or code-path explanation behind them.
- Test gaps, assumptions, and residual risk are explicit.