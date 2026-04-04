---
name: commit-staged-changes
description: Review staged Git changes, derive a conventional commit message from the staged diff, and create the commit. Use when the user asks to inspect `git add`ed changes, write a Conventional Commits subject, or commit only the current staging area safely without sweeping in unstaged work.
---

# Commit Staged Changes

Inspect only staged changes, choose a defensible Conventional Commits message, and commit without altering the staging area beyond the requested commit.

## Workflow

1. Confirm the current directory is inside a Git repository with `git rev-parse --show-toplevel`.
2. Inspect staged state before proposing a message:
   - `git status --short`
   - `git diff --cached --stat`
   - `git diff --cached --name-status`
   - `git diff --cached --minimal`
3. Stop if there are no staged changes. Tell the user there is nothing to commit.
4. Stop if the staged changes mix unrelated concerns. Ask the user to split the commit instead of inventing a broad message.
5. Derive the commit type from the actual staged behavior:
   - `feat`: user-visible capability or behavior added
   - `fix`: bug fix or behavioral correction
   - `refactor`: internal restructuring without intended behavior change
   - `perf`: measurable performance improvement
   - `docs`: documentation-only changes
   - `test`: test-only changes
   - `build`: build, dependency, packaging, or tooling changes
   - `ci`: CI workflow or automation pipeline changes
   - `chore`: maintenance work that does not fit the above
6. Add a scope only when the affected area is obvious and concise, such as `feat(auth): ...` or `fix(skill): ...`.
7. Mark breaking changes with `!` only when the staged diff clearly changes public behavior, interfaces, data formats, CLI flags, environment requirements, or required configuration.
8. Write a subject in imperative form and keep it tight. Prefer one line under 72 characters.
9. Always write a body.
   - First paragraph: explain why the change exists or what behavior it introduces.
   - Keep body lines concise and typically wrap near 72 characters.
10. If the change is breaking, include a `BREAKING CHANGE:` paragraph in the body that states what changed and what the caller or user must do.
11. Commit with `git commit -m "<type>(<scope>): <subject>" -m "<body>"` and add more `-m` arguments when the body needs multiple paragraphs.

## Decision Rules

- Base the message on staged changes only. Ignore unstaged and untracked files unless the user asks to stage them.
- Do not run `git add`, `git commit -a`, or amend existing commits unless the user explicitly asks.
- If the best message depends on intent that is not visible from the diff, ask one short question instead of guessing.
- Prefer the smallest accurate type. Do not use `chore` when `feat`, `fix`, `refactor`, `docs`, or `test` fits.
- Always include a body, even for small changes.
- Use the body to explain why the change exists, not to restate the diff mechanically.
- Mention migration steps, renamed interfaces, removed flags, schema changes, and config requirements in the body when present.
- Use `!` in the header only for genuine breaking changes. Do not use it as emphasis.
- If the diff looks breaking but the impact is ambiguous, stop and ask instead of labeling it as breaking by default.

## Commit Body Rules

- First body paragraph: explain motivation or behavioral context in one to three short lines.
- Treat that first body paragraph as required, not optional.
- Optional second paragraph: call out side effects, rollout notes, or follow-up expectations.
- Breaking changes: add a separate paragraph starting with `BREAKING CHANGE:`.
- Avoid boilerplate such as "update code" or "misc fixes".
- Do not paste raw diff details or file lists into the body unless the user explicitly wants that style.

## Breaking Change Heuristics

Treat the staged change as breaking when the diff clearly shows one of these:

- Public API shape changed incompatibly.
- Required config keys, env vars, or CLI flags changed or were removed.
- Output format, schema, or contract changed incompatibly.
- Default behavior changed in a way existing users or callers must adapt to.
- A supported path, endpoint, command, or option was removed or renamed without backward compatibility.

Do not mark as breaking when the diff is only:

- Internal refactoring with preserved behavior.
- Additive behavior that keeps old callers working.
- Documentation, tests, comments, or formatting changes.
- Dependency or tooling churn without user-facing contract impact.

## Suggested Command Sequence

```bash
git status --short
git diff --cached --stat
git diff --cached --name-status
git diff --cached --minimal
git commit -m "fix(scope): concise subject" \
  -m "Explain why the change is needed and what behavior it affects."
git commit -m "feat(api)!: remove legacy token field" \
  -m "Require callers to use the bearer_token field for API auth." \
  -m "BREAKING CHANGE: requests using token must switch to bearer_token."
```

Replace the commit message with one justified by the staged diff.
