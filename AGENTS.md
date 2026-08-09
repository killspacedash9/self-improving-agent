# AGENTS.md — operating rules for the repository agent

These rules are injected into every agent run together with `SOUL.md`.

## The improvement loop

1. Read `SOUL.md` and `AGENTS.md`. Internalize them.
2. Read the repository tree and the relevant files (`src/`, `tests/`).
3. Plan the smallest change that satisfies the task.
4. Emit the change as **full file contents** in JSON. No diffs, no ellipses.
5. The harness applies the files, syntax-checks them, and runs the test suite.
6. If tests fail, the harness sends you the failure output. Fix your change
   and resubmit. You get up to 3 attempts per run.
7. When green: the harness commits, pushes, journals, and — if the task came
   from an issue — comments on it.

## Response contract

Return **only** a JSON object of the form:

```json
{
  "summary": "one-line human summary of the change",
  "files": {
    "src/tinymind.py": "full new content of the file",
    "tests/test_tinymind.py": "full new content of the file"
  },
  "soul_lessons": ["optional durable lesson, or []"]
}
```

- Every path must be relative to the repo root and start with an allowed
  prefix.
- You MUST include the complete file contents for every file you touch.
- If the task is impossible or unsafe, return `"files": {}` and explain in
  `summary`. Do not invent changes.
- `soul_lessons` entries are appended to `SOUL.md`'s Lessons section by the
  harness.

## Allowed / blocked paths

- Allowed: `src/`, `tests/`, `web/`, `docs/`, `prompts/`, `README.md`, `SOUL.md`
- Blocked: `.github/`, `harness/`, `AGENT_JOURNAL.md`, `.env`, `*.pem`,
  `*.key`, `.git/`

## Commit etiquette

- Commit messages start with `[agent]` and summarize the change.
- If you touched `SOUL.md`, say why in the commit body.

## Failure honesty

If you cannot make tests pass after the allowed attempts, the harness will
journal and report the failure. That is a legitimate outcome. Do not weaken
or delete tests to make them pass — that is cheating, and the journal will
remember.
