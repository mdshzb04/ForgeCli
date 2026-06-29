# ForgeCLI

> **AI Development Operating System** — describe the outcome you want, and ForgeCLI orchestrates Graphify, Ponytail and the selected LLM to achieve it.

The headline command takes a single free-form prompt and runs the
full pipeline end-to-end:

```bash
forge --prompt "Build a Meeting Intelligence SaaS with FastAPI, Next.js, PostgreSQL and AI meeting summaries"
forge --prompt "Create an AI CRM with LangGraph agents"
forge --prompt "Add JWT authentication and Stripe subscriptions"
```

ForgeCLI classifies the prompt's intent (build / ask / plan / docs /
review / explain / commit), picks a workflow, then runs:

1. **Graphify retrieval** — find the relevant nodes/files in the repo.
2. **Ponytail optimization** — apply the YAGNI "ladder" to the prompt.
3. **Model selection** — use Claude, OpenAI, Gemini, or `auto` (cheapest).
4. **Plan** — render the architecture, milestones and affected files.
5. **Code generation** — call the LLM, extract a unified diff.
6. **Apply** — write the changes to disk (uses `git apply` when possible).
7. **Tests** — run the project's test command and capture the result.
8. **Auto-fix** — if tests fail, ask the LLM for a focused fix and retry.
9. **Commit** — stage the files; the user runs `forge commit` to record them.
10. **Summary** — Rich-formatted report of everything that happened.

If the prompt is a question, a plan request, or a docs request, the
classifier dispatches to a smaller workflow (`ask`, `plan`, `docs`,
`explain`, `review`, `commit`).

ForgeCLI ships intelligent subcommands for explicit, fine-grained
control:

* `forge graph` &nbsp; `forge ask` &nbsp; `forge explain` &nbsp; `forge plan` &nbsp; `forge build`
* `forge review` &nbsp; `forge commit` &nbsp; `forge docs` &nbsp; `forge release` &nbsp; `forge config`

Plugins may register additional workflows, providers, optimizers,
analyzers, and intent classifiers via the `forgecli.plugins`
entry-point group — no core changes required.

---

## Highlights

- **Free-form top-level command** — `forge --prompt "..."` is the single entry point.
- **Plugin-based architecture** with first-class extension points (entry-point plugins, provider plugins, custom commands).
- **Fully cross-platform** — Windows 10/11 (PowerShell, Command Prompt, Windows Terminal), macOS (Intel + Apple Silicon), and Linux (Ubuntu, Fedora, Debian, Arch, Kali, openSUSE). OS detection, XDG-style config dirs, `pathlib` everywhere, `shutil.which()` for tool discovery, and a single shell adapter that never hardcodes POSIX-only commands. Install via `pip`, `uv tool`, Homebrew, Scoop, or Winget.
- **Provider abstraction + router** — `forge model claude|openai|gemini|auto` picks a real provider behind a unified interface (OpenAI, Anthropic, Google Gemini). With `auto`, the router picks the cheapest compatible model based on a per-1k-token price table.
- **Dependency injection** via a lightweight `Container` exposed through `AppContext`.
- **Graphify-powered knowledge graph** — `forge graph build / query / explain` shells out to the [Graphify](https://graphifylabs.ai/) CLI behind a clean `RepositoryGraph` interface. No Graphify code is modified or vendored.
- **Ponytail prompt optimizer** — `forge optimizer on|off|lite|full|ultra` rewrites every chat prompt before it reaches a provider, applying the [Ponytail](https://ponytail.dev/) "ladder" (YAGNI → reuse existing helpers → stdlib → native → installed deps → one-liner → minimum code). Optional external `ponytail` binary is auto-detected and preferred when present.
- **Context optimizer** that chunks, ranks, and (optionally) summarizes large repositories for LLM context windows.
- **Planner + Agent** for declarative, multi-step task execution.
- **Auto-fix loop** — if tests fail, the LLM is asked for a focused fix and the patch is retried up to `max_fix_attempts` times.
- **Git automation** built on GitPython with typed errors.
- **Local memory** (SQLite) for history, embeddings cache, and plugin state.
- **Rich-powered terminal UI** with a small, themed helper layer.
- **Production-ready project layout**: typed config, structured logging, error hierarchy, tests, and lint/typecheck tooling.

---

## Project layout

```
forgecli/
├── cli/            # Typer commands, Rich UI helpers, bootstrap
├── core/           # AppContext, DI container, errors, events, plugins
├── providers/      # AI provider abstraction (Provider, ProviderRegistry, MockProvider)
├── graph/          # Code graph: nodes/edges, Indexer, GraphifyClient, RepositoryGraph
│                   #   repository.py    - abstract RepositoryGraph interface
│                   #   graphify.py      - async subprocess wrapper (no Python imports)
│                   #   backend_graphify - RepositoryGraph impl backed by Graphify
├── optimizer/      # Context chunking, ranking, summarization
├── planner/        # Plans, steps, planners, agent executor
├── builder/        # Edit/format/build pipeline
├── review/         # Findings, severity, diff analyzer, reviewer strategies
├── git/            # GitPython wrapper, GitService, commit types
├── prompts/        # Prompt template loader, registry, renderer
├── memory/         # SQLite MemoryStore, history repository, cache
├── templates/      # Template engine and registry
├── config/         # Settings models (Pydantic) and loader
└── utils/          # fs, io, paths, timing, ids
```

---

## Installation (development)

```bash
git clone https://github.com/forgecli/forgecli
cd forgecli
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The CLI entry point is `forge` (alias `forgecli`):

```bash
forge --help
forgecli --help
```

---

## Configuration

ForgeCLI reads configuration from any of (highest priority first):

1. `--config` flag on the command line
2. `./forgecli.toml`, `./.forgecli.toml`, or `[tool.forgecli]` in `./pyproject.toml`
3. Environment variables prefixed with `FORGECLI_`
4. Built-in defaults

An example configuration lives at [`examples/forgecli.toml`](examples/forgecli.toml).
Environment variables are documented in [`.env.example`](.env.example).

---

## Commands (scaffold)

| Command                    | Description                                              |
| -------------------------- | -------------------------------------------------------- |
| `forge init`               | Initialize a ForgeCLI project                            |
| `forge config`             | Show / validate configuration                            |
| `forge providers list`     | List registered AI providers                             |
| `forge model claude`       | Use Anthropic Claude as the active provider              |
| `forge model openai`       | Use OpenAI as the active provider                        |
| `forge model gemini`       | Use Google Gemini as the active provider                 |
| `forge model auto`         | Auto-select the cheapest provider with creds             |
| `forge model status`       | Show current selection, costs, and credentials           |
| `forge model list`         | List all registered providers and their defaults         |
| `forge index`              | Build the in-memory code graph (lightweight)             |
| `forge graph build`        | Build the Graphify knowledge graph for a project         |
| `forge graph status`       | Show whether Graphify is installed and graph.json exists |
| `forge graph query "..."`  | BFS/DFS-traverse the graph with a free-form question     |
| `forge graph explain X`    | Explain a node and its neighbors (text from Graphify)    |
| `forge graph path A B`     | Shortest edge path between two nodes                     |
| `forge graph affected X`   | Reverse-traverse to find blast radius of a node          |
| `forge optimizer on/off`   | Turn the Ponytail prompt optimizer on/off                |
| `forge optimizer lite|full|ultra` | Set the Ponytail intensity                       |
| `forge optimizer status`   | Show current intensity, backend, and binary path          |
| `forge optimizer preview`  | Show what would be prepended to a system message          |
| `forge explain X`          | Top-level alias for `forge graph explain X`              |
| `forge plan <goal>`        | Build a software plan (architecture, milestones, tasks, risks, prompts) |
| `forge review`             | Run a code-quality review (security, performance, architecture, complexity, dead code, duplicates) |
| `forge commit`             | Analyze the git diff, generate a semantic commit + changelog entry, optional push |
| `forge build`              | Run the builder pipeline                                 |
| `forge review`             | Review code changes                                      |
| `forge git`                | Inspect / operate on the git repository                  |
| `forge history`            | Show recent CLI history                                  |

Every command is wired through the shared `AppContext` and supports
`--config <path>`, `--verbose`, and `--version` global flags.

---

## Graphify integration

ForgeCLI treats [Graphify](https://graphifylabs.ai/) as an *external*
back-end and never imports or modifies its code. The integration is a
thin async wrapper around the `graphify` CLI:

```bash
# Install Graphify
uv tool install graphifyy
graphify .          # verify it works

# In any project:
forge graph build                  # → graphify extract . --out .
forge graph query "what does foo do?"
forge graph explain foo.py
forge graph path foo.py bar.py
forge graph affected foo.py --depth 3

# Top-level shortcut
forge explain foo.py
```

The integration layer (`forgecli.graph.repository`) is a small
abstract interface:

```python
class RepositoryGraph(ABC):
    name: str
    async def is_available(self) -> bool: ...
    async def build(self, *, force: bool = False) -> BuildResult: ...
    async def load(self) -> GraphSnapshot: ...
    async def query(self, question: str, *, budget: int = 2000) -> QueryResult: ...
    async def explain(self, target: str) -> ExplainResult: ...
    async def shortest_path(self, a: str, b: str) -> list[GraphEdge]: ...
    async def affected(self, target: str, *, relation=None, depth: int = 2) -> list[GraphEdge]: ...
```

`GraphifyRepositoryGraph` is the production implementation; an
in-memory `CodeGraph` (used by `forge index`) remains available for
tests and small projects that don't need full AST extraction.

---

## Ponytail prompt optimizer

[Ponitail](https://ponytail.dev/) is a *ruleset* that nudges AI coding
agents toward the smallest correct code change. ForgeCLI ships the
ruleset in pure Python (`forgecli.optimizer.ponytail.ruleset`) and
also wraps an external `ponytail` binary when one is installed.

```bash
# Intensity levels: lite (default) | full | ultra
forge optimizer on                 # restore last intensity (or default to lite)
forge optimizer off                # pass prompts through unchanged
forge optimizer lite
forge optimizer full
forge optimizer ultra
forge optimizer set full --backend cli --binary /usr/local/bin/ponytail
forge optimizer status             # show current state
forge optimizer preview "build a CLI"   # see the rewritten system prompt
```

The ruleset implements the official "ladder":

> 1. Does this need to exist? Speculative need = skip it (YAGNI).
> 2. Already in this codebase? Reuse the helper, util, or pattern that already lives here.
> 3. Does the standard library do it? Use it.
> 4. Native platform feature covers it? Use it.
> 5. Already-installed dependency solves it? Use it. Don't add a new one.
> 6. Can it be one line? One line.
> 7. Only then: the minimum code that works.

The integration is a clean :class:`PromptOptimizer` interface
(`forgecli.optimizer.ponytail`) with two implementations
(`PonytailRulesetOptimizer`, `PonytailCLIOptimizer`) selected at
runtime by :class:`CompositeOptimizer`. The :class:`OptimizedProvider`
decorator wraps any :class:`Provider` so every `chat()` call is
optimized transparently before the request hits the model — embedding
calls pass through unchanged.

---

## Software planner

`forge plan <natural-language goal>` turns a one-line idea into a full
software plan rendered in the terminal:

```bash
forge plan "Build a Python FastAPI service for user authentication"
forge plan --md --save plan.md "Build a CLI in Rust"
forge plan --json "Build a Go API" | jq .tasks
```

The planner is deterministic and rule-based (no network required). It
emits a structured `SoftwarePlan` with:

* **architecture** — three-layer components, data flow, contracts;
* **folder structure** — a tree tailored to the detected project kind (API / CLI / library);
* **milestones** — six coarse-grained phases (Discovery → Quality & release) with deliverables;
* **tasks** — 15+ fine-grained units, each with priority, estimate (S/M/L/XL), acceptance criteria, and intra-milestone dependencies;
* **risks** — a register of known unknowns with severity/likelihood and mitigations;
* **prompt sequences** — the system + user prompts an AI agent would feed to a model to execute each task (Ponytail-style).

Options:

```bash
forge plan --max-milestones 4 "Build a Go API"      # cap the roadmap
forge plan --no-observability "Build a CLI"         # drop metrics/tracing tasks
forge plan --no-tests "Build a library"             # drop the coverage task
```

The plan can be exported as `--md` (Markdown, ideal for PRs) or
`--json` (machine-readable). The `forgecli.planner.software` module
also exposes the typed Pydantic model so you can consume the plan
from your own scripts.

---

## Model routing

ForgeCLI ships with a small `ModelRouter` (`forgecli.providers.router`)
that resolves a high-level choice (`claude` / `openai` / `gemini` /
`auto`) to a concrete provider + model. Real providers are
implemented in `forgecli.providers.openai`, `.anthropic`, and `.google`
and are all `httpx`-based async clients.

```bash
# Pick a provider for the current project
forge model claude                                # -> anthropic / claude-3-5-haiku-latest
forge model openai --model gpt-4o                 # explicit model override
forge model gemini --model gemini-1.5-pro
forge model auto                                  # cheapest with creds

# Inspect the active selection and cost model
forge model status
forge model list
```

Environment variables drive credentials:

| Provider  | Variable(s)                                |
| --------- | ------------------------------------------ |
| OpenAI    | `OPENAI_API_KEY`                           |
| Anthropic | `ANTHROPIC_API_KEY`                        |
| Google    | `GOOGLE_API_KEY` (or `GEMINI_API_KEY`)     |

`auto` selects the cheapest provider with at least one credential set
(by in-price, then out-price, then provider name for determinism). If
no real provider has credentials, the router falls back to the
`mock` provider and the CLI prints a warning. The selection persists
to `data_dir/router.json` and is read on every subsequent CLI
invocation.

---

## Repository review

`forge review` runs six AST + regex-based analyzers against a project
and produces a Rich, JSON, or Markdown report. It runs locally and
has no external dependencies.

```bash
# Default: print a Rich report to the terminal.
forge review

# Filter by category, severity, or both.
forge review --only security,performance --severity high
forge review --exclude dead-code,duplicates

# Save the report.
forge review --md --save review.md
forge review --json --save report.json

# Exit non-zero when critical findings are present (CI gate).
forge review --fail-on-critical

# List the available categories.
forge review categories
```

What the analyzers catch:

* **security** — hard-coded AWS keys, API tokens, PEM private keys,
  `pickle.load`, `eval`/`exec`, `subprocess(shell=True)`, weak hashes
  (`md5`/`sha1`), `assert` statements.
* **performance** — blocking I/O (`open`, `read_text`) inside
  `async def`, `time.sleep` in async code, deeply nested loops.
* **architecture** — layer dependency direction (e.g. `core` cannot
  import `graph`), circular imports between layers, configurable
  forbidden imports.
* **complexity** — function line count, parameter count, and an
  approximate cyclomatic complexity (per function).
* **dead-code** — private symbols (`_foo`) that are never referenced
  anywhere in the project; ignores dunders, `__all__` re-exports, and
  test files.
* **duplicates** — near-duplicate 6-line blocks across files, using a
  rolling token shingle. Output is capped at 50 findings per scan.

The output is grouped by category, ranked by severity, and capped
per scan so the report stays small. Use `forge review --json` to
pipe the report into CI dashboards.

---

## Semantic commits

`forge commit` runs against the current git diff and produces a
Conventional Commits-style message, a changelog entry, and an
optional release-notes document. It is fully self-contained: it
subprocesses `git` directly and never imports a Python git library.

```bash
# Inspect the proposed message + changelog draft; make no changes.
forge commit --dry-run

# Stage everything in the working tree, commit, update CHANGELOG.md.
forge commit --all --yes --changelog

# Override the auto-generated message and sign off.
forge commit --all --yes -m "feat(graph): add Graphify integration" --signoff

# Render release notes from the current Unreleased entries.
forge commit release 1.2.0 --notes-path release-notes.md
```

What the analyzer infers:

* **Kind** (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`,
  `build`, `ci`, `style`) from the file kinds in the diff.
* **Scope** from the top-level directory under the project source root
  (e.g. `forgecli/graph/...` → scope `graph`).
* **Summary** as `verb(scope): payload` — `add(graph): graph.py`.
* **Breaking** when the diff contains a Conventional Commits footer
  (`BREAKING CHANGE: …` on its own line) or a `feat!:`-style subject.

The `--changelog` flag appends the entry to `CHANGELOG.md` under an
"Unreleased" section. `forge commit release <version>` promotes those
entries to a versioned section (`## [1.2.0] - 2024-05-12`) and writes
the release notes to the path of your choice.

---

## Plugin extension points

ForgeCLI is designed to be extended. A plugin is a Python package
that contributes one or more of the following:

* a `Workflow` — a named, executable unit that orchestrates the
  standard pipeline stages. The top-level `forge` command
  dispatches to a `Workflow` based on the prompt's intent.
* a `Provider` — an AI provider registered with the router.
* a `PromptOptimizer` — a prompt-rewriting strategy picked by the
  Ponytail intensity.
* an `Analyzer` — a code-review analyzer run by `forge review`.
* an `IntentClassifier` — a smarter intent classifier that runs
  before the built-in heuristic one.

A plugin is discovered via the `forgecli.plugins` entry-point
group; the registered factory is called once at startup with the
shared `PluginRegistry`, and the plugin can wire up whatever it
needs (commands, providers, workflows, etc.).

```toml
# pyproject.toml of a ForgeCLI plugin
[project.entry-points."forgecli.plugins"]
my_plugin = "my_plugin:register"
```

```python
# my_plugin/__init__.py
def register(registry):
    from forgecli.plugins import Workflow, Intent
    from my_plugin.workflows import MyWorkflow

    registry.register_workflow(MyWorkflow())
```

The top-level `forge --prompt` then dispatches to the registered
`Workflow` whenever the intent matches.

---

## Execution Engine

The :mod:`forgecli.engine` package defines the *contract* for every
orchestration stage in ForgeCLI. The pipeline is a fixed sequence of
eight stages:

    1. **Intent Analyzer**      — turn the prompt into an Intent
    2. **Repository Analyzer**  — query Graphify for relevant context
    3. **Context Optimizer**    — apply Ponytail to the prompt + context
    4. **Planning Engine**      — produce a SoftwarePlan
    5. **Model Router**         — pick (provider, model) for the call
    6. **Execution Engine**     — invoke the LLM, extract a diff
    7. **Validation Engine**    — apply the diff + run tests + auto-fix
    8. **Git Engine**           — stage / commit / push the changes

Every stage is a small async callable behind the :class:`Stage`
Protocol. The :class:`ExecutionEngine` runs them in order and is
responsible for:

* **Structured events** — :class:`StageEvent`, :class:`ProgressEvent`,
  :class:`TextLogEvent` flow through the :class:`EventBus` so
  callers can stream progress and logs in real time.
* **Retries** — each stage has ``max_attempts``; transient failures
  retry with a backoff (``retry_backoff_seconds * attempt``).
* **Cancellation** — a single :class:`asyncio.Event` token
  (``bus.cancellation``) is checked between stages; a stage may also
  set the token itself to short-circuit the run.
* **DI / plugins** — stages are looked up by name in a
  :class:`StageRegistry`. Plugins may register or replace stages
  via the ``forgecli.plugins`` entry-point group.
* **Structured output** — every stage returns a
  :class:`StageResult` (status, data, notes, error), not a string.
  The engine accumulates them on :class:`EngineContext.log` for
  reporting.

The engine does *no* business logic. Stages encapsulate the work.
The default pipeline name list is exposed as
``ExecutionEngine.DEFAULT_PIPELINE``.

```python
import asyncio
from forgecli.engine import (
    EngineContext, EventBus, ExecutionEngine,
    PipelineBuilder, StageResult, StageStatus,
)

class IntentStage:
    name = "intent-analyzer"
    async def __call__(self, ctx):
        # … do work, then return structured output …
        return StageResult(status=StageStatus.SUCCEEDED, data={"intent": "build"})

engine = (
    PipelineBuilder()
    .stage(IntentStage())
    .with_max_attempts(3)
    .with_retry_backoff(0.5)
    .build()
)

async def main():
    result = await engine.run(EngineContext(prompt="...", cwd=Path(".")))
    print("success:", result.success, "stages:", len(result.stage_results))

asyncio.run(main())
```

Hooks (``before_pipeline`` / ``after_pipeline``) run before/after the
run via :class:`HookManager`; plugins register them through
:func:`register_plugin`. Hooks that raise are logged and do *not*
abort the engine.

---

## Architecture notes

- **Composition root**: `forgecli/cli/bootstrap.py` builds the
  `AppContext`, instantiates the DI container, and registers default
  services. Tests build their own contexts via the same primitives.
- **Errors**: every domain has its own exception type under
  `forgecli.core.errors`. The CLI translates `ForgeCLIError` into a
  clean exit code.
- **Logging**: a single `configure_logging()` call sets up structured
  stderr output. Services use `forgecli.core.service.Service` to obtain
  a named logger.
- **Plugins**: third parties may implement
  `forgecli.core.plugins.Plugin` and register via the
  `forgecli.plugins` entry-point group. The CLI calls
  `discover_plugins()` and `install_plugins()` during bootstrap.
- **Providers**: every concrete provider subclasses
  `forgecli.providers.base.Provider` and is registered into the
  `ProviderRegistry`. OpenAI, Anthropic, and Google Gemini are
  implemented as `httpx`-based async clients in
  `forgecli.providers.openai`, `.anthropic`, and `.google`.
- **Graphify**: integration is purely an async subprocess wrapper. The
  `RepositoryGraph` interface (`forgecli.graph.repository`) is the only
  surface area; the Graphify CLI is invoked via `asyncio.create_subprocess_exec`
  and never imported as a Python module. Swap the backend by
  implementing `RepositoryGraph` and registering it in
  `forgecli.cli.bootstrap._build_container`.

---

## Development

```bash
# Run the test suite
pytest

# Lint
ruff check .

# Type check
mypy forgecli
```

Continuous integration should run all three.

---

## Cross-platform support

ForgeCLI is built to run identically on Windows, macOS and Linux.
The :mod:`forgecli.platform` package is the only place that may
import :mod:`sys` / :mod:`platform` / :mod:`subprocess` directly;
everything else goes through the platform layer.

### Detection

```python
from forgecli.platform import (
    current_platform, is_windows, is_macos, is_linux,
    python_version, has_git, has_graphify, has_ponytail,
)

print(current_platform().os)        # OS.linux | OS.macos | OS.windows
print(is_windows())                  # bool
print(python_version())              # "3.12.3"
print(has_git(), has_graphify())     # bool, bool
```

### Config and data directories

ForgeCLI uses platform-appropriate locations for state, honoring
environment variable overrides:

* Linux: ``$XDG_DATA_HOME/forgecli`` (default
  ``~/.local/share/forgecli``)
* macOS: ``~/Library/Application Support/ForgeCLI``
* Windows: ``%LOCALAPPDATA%\forgecli``

Override with ``FORGECLI_DATA_DIR``, ``FORGECLI_CONFIG_DIR``,
``FORGECLI_CACHE_DIR`` for tests and CI.

### Install

```bash
# pip / uv
pip install forgecli
uv tool install forgecli

# macOS / Linux
brew install mdshzb04/tap/forgecli   # once a tap exists

# Windows (Scoop)
scoop bucket add mdshzb04 https://github.com/mdshzb04/scoop-bucket
scoop install forgecli

# Windows (Winget)
winget install mdshzb04.ForgeCli
```

Packaging manifests live in :file:`packaging/`.

### Self-check

Run ``forge doctor`` to print a structured report of the host
(OS, arch, Python version, all known external dependencies).
Exit non-zero with ``--strict`` if any required dep is missing.

```bash
forge doctor --json | jq .
forge doctor --strict   # exit 1 if git is missing
```

### Update check

```bash
forge --check-update     # queries PyPI once; result is cached for 24h
```

Set ``FORGECLI_CHECK_UPDATE=1`` to opt into startup checks;
``FORGECLI_PYPI_URL`` to point at a staging index.

### CI

GitHub Actions matrix runs the full test suite on
``ubuntu-latest``, ``macos-latest`` and ``windows-latest`` with
Python 3.12 and 3.13. See :file:`.github/workflows/ci.yml`.

---


<img width="1854" height="1005" alt="image" src="https://github.com/user-attachments/assets/03f3c2e2-424c-4784-8a59-b2b0f4b99447" />



<img width="1854" height="1005" alt="image" src="https://github.com/user-attachments/assets/6eb06d10-6f1f-4648-b679-028368362c24" />


## License

[MIT](LICENSE)
# ForgeCli
