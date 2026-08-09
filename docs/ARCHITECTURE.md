# Architecture

How Aster works, end to end. Read this before extending anything.

## Components

| Component | Where | Role |
|---|---|---|
| Soul | `SOUL.md` | The agent's identity: mission, values, constraints, personality. Injected into every run as the system prompt. The agent may evolve it (via `soul_lessons`). |
| Rules | `AGENTS.md` | Operational contract: the improvement loop, the JSON response schema, the path whitelist, failure honesty. |
| Harness | `harness/runner.py` | The only process that touches git or the API. Stdlib-only. Owns the journal. |
| Brain | DeepSeek API | Stateless planner/editor. Receives context, returns full file contents in JSON. |
| Trigger | `.github/workflows/self-improve.yml` | `workflow_dispatch` (manual) or `issues: labeled` (chat). Its `deploy` job also publishes the agent's commit — Actions-token pushes don't fire other workflows' `push` events. |
| Publisher | `.github/workflows/pages.yml` | Re-deploys `web/` on human pushes to main. |
| Interface | `web/` | Zero-dependency chat window: files issues, shows journal + request feed. |

## The harness pipeline (`runner.py`)

```
task (--task | --issue N | --mock)
  → build_messages(): SOUL + AGENTS + repo_context() + task [+ repair history]
  → call_deepseek():  POST {base}/chat/completions, model=AGENT_MODEL,
                      response_format=json_object, retries with backoff
  → parse_response(): strip fences, validate schema, validate paths
  → apply_files():    write full file contents (whitelist enforced)
  → syntax_check():   compile() every changed .py
  → run_tests():      pytest (fallback: unittest discover)
  → [fail] append output to repair history, loop (≤ max_rounds)
  → apply_lessons():  append soul_lessons to SOUL.md
  → journal_entry():  prepend run record to AGENT_JOURNAL.md
  → commit_push():    add -A, commit as bot, push | open PR (mode)
  → notify_issue():   comment result on the originating issue
```

### Path whitelist

`validate_path()` allows only:

- prefixes `src/ tests/ web/ docs/ prompts/`
- root files `README.md SOUL.md`

and rejects `..`, absolute paths, `.github/`, `harness/`, `AGENT_JOURNAL.md`,
`.env`, `.gitignore`, and key material (`*.pem *.key *.p12 *.pfx *.p8`).
`repo_context()` also hides those files from the model so it never even sees
the harness code.

### Repair loop

On bad JSON, disallowed paths, syntax errors, or failing tests, the harness
appends the rejection reason to a repair history and asks the model again with
the *current* (already mutated) repository state in context — the model sees
its own broken output and must fix it. Bounded by `--max-rounds` (default 3,
clamped to 5). On exhaustion, the tree is restored via `git restore` + untracked
cleanup, a failure is journaled, and a journal-only commit is made so the
failure is visible in git history.

### Publish modes

- `local` — apply + test + journal on disk; no commit, no push. (CI artifact mode.)
- `push` — commit as `Aster (agent-improver)` and push to the branch. Default.
- `pr` — push branch `agent/<slug>` and open a pull request via the API. The
  safe mode for untrusted requesters.

### GitHub API usage

`gh_api()` (Bearer `GITHUB_TOKEN`) is used for: fetching issue bodies
(`--issue N`), commenting results (`--notify-issue N`), and opening PRs.
All other git operations use the credential persisted by `actions/checkout`.

## Concurrency & triggers

- `self-improve.yml` has `concurrency: self-improve` — simultaneous requests
  queue instead of racing on the same working tree.
- The issue trigger is `types: [labeled]` with a job-level filter on
  `github.event.label.name == 'agent-request'`; the chat window creates that
  label automatically.
- **Pushes made with `GITHUB_TOKEN` never fire `push` events on other
  workflows** — so the agent's own push cannot trigger `pages.yml`. The
  Self-Improve workflow therefore deploys in a second job (`deploy`), checking
  out the commit the agent pushed (`improve.outputs.pushed_sha`). Human pushes
  still go through `pages.yml`. Both share `concurrency: pages` so deploys
  never race. Note: `deploy-pages` labels the deployment with the event SHA
  (`github.sha`), not the artifact SHA — the artifact itself is built from the
  agent's commit.

## Threat model (read before exposing publicly)

- Issue bodies are **untrusted prompt input**. The agent could be steered to
  write malicious code — but it is confined to the whitelist, cannot exfiltrate
  secrets it never sees (`DEEPSEEK_API_KEY` is in the env; `repo_context()`
  omits `.github/` and `harness/`), and every change must pass the test suite.
- Default to `pr` mode when accepting requests from strangers, and review
  before merging. For a fully autonomous public repo, accept the risk that
  the codebase evolves in ways you did not personally review.
