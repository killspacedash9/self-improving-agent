# Aster — a self-improving repository

A sample repo with an agent soul built in. **Aster** is the agent that *is*
this repository: it reads its own identity (`SOUL.md`), takes tasks from
humans, edits its own code via the DeepSeek API, tests it, commits it, pushes
it, and re-publishes itself to GitHub Pages. A chat window on the Pages site
lets anyone request features or fixes — the request becomes a GitHub issue,
the agent does the work, and it comments the result back.

All you need to run it: a **DeepSeek API key** (for the agent's brain) and a
**GitHub PAT** (for the chat window, browser-side only).

```
        ┌──────────────────┐   feature request    ┌──────────────────┐
        │  Chat window     │ ───────────────────▶ │  GitHub issue    │
        │  (GitHub Pages)  │                      │  agent-request   │
        └──────────────────┘                      └────────┬─────────┘
                                                           │ labeled event
                                                           ▼
        ┌──────────────────┐   commit + push    ┌──────────────────┐
        │  Pages re-deploys│ ◀───────────────── │  Self-Improve    │
        │  itself          │                    │  workflow        │
        └──────────────────┘                    └────────┬─────────┘
                                                         │ runs harness
                                                         ▼
        ┌──────────────────┐      DeepSeek      ┌──────────────────┐
        │  harness/        │ ─────────────────▶ │  DeepSeek API    │
        │  runner.py       │   JSON plan        │  deepseek-chat   │
        └──────────────────┘   (full files)     └──────────────────┘
```

## The loop, step by step

1. **A task arrives** — either you dispatch the *Self-Improve* workflow with a
   prompt, or the chat window files an issue labeled `agent-request`.
2. The workflow runs `harness/runner.py` with `DEEPSEEK_API_KEY` and
   `GITHUB_TOKEN` in the environment.
3. The harness assembles a prompt from **`SOUL.md`** (identity, values,
   constraints), **`AGENTS.md`** (operating rules + response contract), and
   the current repository contents.
4. DeepSeek replies with a JSON plan: full file contents for every file to
   change.
5. The harness **validates** paths against a whitelist, **writes** the files,
   **syntax-checks** Python, and **runs the test suite**.
6. If tests fail, the failure output is sent back to the model for repair —
   up to 3 rounds per run.
7. When green: the agent **journals** the run (`AGENT_JOURNAL.md`), **commits**
   as the bot, and **pushes** to the branch (or opens a PR in `pr` mode).
8. The push triggers the *Deploy Pages* workflow — the repo **re-publishes
   itself**, and the chat window's journal feed updates. If the task came from
   an issue, the agent **comments** the result on it.

## Repo map

```
SOUL.md                  the agent's soul — identity, mission, values, constraints
AGENTS.md                operating rules + the JSON response contract
AGENT_JOURNAL.md         the agent's memory — every run is logged here
harness/runner.py        the harness: DeepSeek client, path validation, test
                         gate, repair loop, commit/push/PR, issue comments
harness/mock_response.py canned response for the offline demo (--mock)
harness/demo.sh          runs the full loop offline — no API key needed
.github/workflows/self-improve.yml   the agent loop (dispatch + issue trigger)
.github/workflows/pages.yml          publishes web/ to GitHub Pages
src/tinymind.py          the sample product the agent improves
tests/                   the test suite that gates every change
web/                     the chat window (zero dependencies, no build step)
prompts/                 copy-paste task templates
```

## Quick start

1. **Fork or copy** this repo into your own GitHub account.
2. **Add the DeepSeek secret** — Settings → Secrets and variables → Actions →
   `DEEPSEEK_API_KEY`. Optional: a repository variable `AGENT_MODEL`
   (defaults to `deepseek-chat`).
3. **Enable Pages** — Settings → Pages → Source: *GitHub Actions* (or run
   `gh api -X POST repos/{owner}/{repo}/pages -f build_type=workflow`).
4. **Trigger the agent** — Actions → *Self-Improve* → Run workflow → type a
   task, e.g. *"Add a method that returns a random proverb, with tests."*
5. **Open the chat window** — at `https://{owner}.github.io/{repo}/`, click
   ⚙ Settings and enter owner, repository, and your GitHub PAT
   (classic `repo` scope, or fine-grained `issues: write`). Type a request.

> Private repos: Pages and the API calls require access, so the chat window
> works for people with repo access. Flip the repo public to let anyone file
> requests.

## Try it offline (no key)

```bash
bash harness/demo.sh
```

Copies the repo to a temp dir and runs the harness in `--mock` mode: the
canned response adds a `quote()` method to TinyMind, tests pass, the agent
commits and pushes to a throwaway git repo. You see the exact loop the real
thing runs.

## Safety model

- The agent can only write to a **path whitelist** (`src/`, `tests/`, `web/`,
  `docs/`, `prompts/`, `README.md`, `SOUL.md`). It cannot touch its own
  workflows or harness — the brain stem is off-limits.
- `.env`, keys, and the journal are blocked.
- Every change is gated by syntax check + the test suite, with a repair loop.
- `AGENT_JOURNAL.md` records every run — successes *and* failures.
- `pr` mode makes the agent open a pull request instead of pushing directly —
  the safe choice if requests come from untrusted people.
- The agent is prompt-injectable like any LLM tool: treat issue bodies as
  untrusted input, use `pr` mode, and keep the repo token scoped.

## Customizing

- **Change its personality/mission** → edit `SOUL.md`. The agent reads it
  every run and is allowed to evolve it itself.
- **Change the rules** → edit `AGENTS.md` (allowed paths, response contract).
- **Change the product it improves** → replace `src/` and `tests/`.
- **Different model/provider** → set `AGENT_MODEL` and optionally
  `DEEPSEEK_BASE_URL` (any OpenAI-compatible endpoint works).

## Troubleshooting

- **Run is green but says "Agent stood down"** → `DEEPSEEK_API_KEY` is not
  configured; add it and re-run.
- **Run fails with "DeepSeek API error"** → check the key and quota.
- **Pages 404** → the first deploy can take a minute; check the *Deploy
  Pages* workflow run.
- **Chat shows "GitHub API 404"** → wrong owner/repo in Settings, or the PAT
  lacks `issues: write`.
