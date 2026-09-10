# SpaceAI

**Intelligent disk cleanup and system analysis for the terminal.**

SpaceAI inspects your machine, explains what is actually consuming disk space,
and — once the cleanup milestone lands — proposes recoverable space as
structured, reviewable actions that only run after you approve them.

> **Status: milestone 1 of 10.**
> Scanning, categorisation, the terminal UI and the safety layer are complete
> and tested. **No code path in this build can delete a file.** See
> [Roadmap](#roadmap).

```text
╭──────────────────────────────────────────────╮
│                   SPACEAI                    │
│          Intelligent Disk Cleanup            │
╰──────────────────────────────────────────────╯

╭─ Disk usage — / ─────────────────────────────────────────╮
│                                                          │
│  ███████░░░░░░░░░░░░░░░░░░░░░░░  107 GB / 465 GB         │
│                                                          │
│  Used                      107 GB                        │
│  Free                      334 GB                        │
│  Usage                      23.1%                        │
│  Potentially recoverable  10.5 GB                        │
│                                                          │
╰──────────────────────────────────────────────────────────╯

28.0 GB across 381,319 files in 34,366 directories · 2.06s · 423 entries skipped

Largest categories
  Category           Size    Share      Files
  Python          11.2 GB    39.9%    155,912
  Caches           4.9 GB    17.6%     98,906
  Git              1.6 GB     5.6%        376
  VS Code          823 MB     2.9%      8,435
  Downloads        539 MB     1.9%         15
```

## Installation

Requires Python 3.12 or newer.

```bash
git clone https://github.com/Rydenb/Storage-cleaner
cd Storage-cleaner
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Then run:

```bash
spaceai
```

## Usage

| Command | What it does |
| --- | --- |
| `spaceai` | Interactive dashboard and command prompt |
| `spaceai scan [PATH]` | Scan a directory and report the biggest files and directories |
| `spaceai analyze [PATH]` | Category breakdown plus every known storage location on the host |
| `spaceai volumes` | Capacity of every mounted volume |
| `spaceai check PATH...` | Ask the safety layer whether a path could ever be cleaned |
| `spaceai doctor` | Environment report: config, provider, Docker, WSL, permissions |
| `spaceai clean` | Reserved for the cleanup milestone; refuses to run today |

Useful flags:

```bash
spaceai scan ~/projects --top 25       # more rows
spaceai scan /var --json               # machine-readable output
spaceai check ~/.cache/pip /etc/passwd # exit code 1 if anything is blocked
```

Inside the interactive prompt: `scan`, `categories`, `files`, `dirs`,
`volumes`, `check <path>`, `host`, `help`, `quit`. Anything else is treated as
a question for the AI assistant, which reports that it is not configured until
you set a provider.

Press **Ctrl+C** during a scan to cancel it — partial results are kept and
clearly labelled as partial.

## Configuration

Settings come from a TOML file, overridden by environment variables. A broken
config file never stops the tool from starting; it falls back to defaults and
says so.

Config file location:

* Linux/WSL — `~/.config/spaceai/config.toml` (or `$XDG_CONFIG_HOME`)
* Windows — `%APPDATA%\SpaceAI\config.toml`
* Override with `SPACEAI_CONFIG`

```toml
[spaceai]
provider = "anthropic"
model = "claude-sonnet-5"
scan_depth = 6
min_report_size = 10485760
top_n = 15
excluded_paths = ["/proc", "/sys"]
```

| Variable | Meaning | Default |
| --- | --- | --- |
| `SPACEAI_PROVIDER` | LLM provider id (`none` disables the assistant) | `none` |
| `SPACEAI_MODEL` | Model name passed to the provider | unset |
| `SPACEAI_API_KEY` | API key — **environment only, never the config file in practice** | unset |
| `SPACEAI_API_BASE` | Custom endpoint for self-hosted or proxied providers | unset |
| `SPACEAI_SCAN_DEPTH` | Deepest directory level reported individually | `6` |
| `SPACEAI_MAX_FILE_SIZE` | Ignore files above this size, in bytes (`0` = no limit) | `0` |
| `SPACEAI_MIN_REPORT_SIZE` | Smallest directory worth listing, in bytes | `10485760` |
| `SPACEAI_TOP_N` | Rows per table | `15` |
| `SPACEAI_EXCLUDED_PATHS` | `:`-separated (`;` on Windows) paths never to walk | see defaults |
| `SPACEAI_FOLLOW_SYMLINKS` | Follow links and junctions while scanning | `false` |
| `SPACEAI_CROSS_FILESYSTEMS` | Descend into other mounted filesystems | `false` |
| `SPACEAI_DATA_DIR` | Where scan history will be stored | platform data dir |

API keys are read from the environment and excluded from every serialisation
of the settings object, so a key can never leak into a log line, a JSON dump or
a scan record.

## Safety model

The whole design assumes the AI can be wrong, so it is never the thing standing
between a suggestion and your files.

1. **No generic shell tool.** The agent will only ever get narrow, typed tools
   (`scan_disk`, `find_large_files`, `preview_cleanup`, …). There is no
   `run_any_command`, and adding one would defeat everything below.
2. **The safety layer decides, not the model.** Every path is resolved —
   symlinks, junctions, `..`, environment variables and `~` all collapsed —
   *before* it is judged, so `~/.cache/../../../etc` is caught as `/etc`.
3. **Protected locations are refused outright**: `/etc`, `/usr`, `/boot`,
   `/var/lib`, `C:\Windows`, `System32`, `Program Files`, `ProgramData`, boot
   files, the page file, and their contents. A path that *contains* a protected
   location is refused too.
4. **Containers cannot be removed, only cleaned inside**: `/`, `/home`, `/mnt`,
   `C:\`, `C:\Users` and your home directory itself.
5. **Personal data requires explicit selection.** `Documents`, `Desktop`,
   `Pictures`, `Videos`, `.ssh`, `.gnupg`, `.aws` and friends are blocked
   unless you pick them yourself, and are then rated `HIGH` risk.
6. **Virtual disks are never touched.** `.vhdx`, `.vhd`, `.img`, `.sys` and
   `.efi` files are refused at every risk level; WSL disks get an explanation
   and a recommendation instead of an operation.
7. **A declared risk level can only go up.** An action that calls itself `SAFE`
   is re-judged from its paths; the stricter verdict wins, and anything above
   the configured ceiling (`MEDIUM` by default) is refused.
8. **Windows-style paths on a POSIX host are refused** rather than silently
   resolved into the working directory.

Check any path yourself:

```bash
$ spaceai check '~/.cache/../../../etc/passwd'
╭─ Safety check ───────────────────────────────────╮
│  Path         ~/.cache/../../../etc/passwd       │
│  Resolves to  /etc/passwd                        │
│  Decision     blocked                            │
│  Risk         BLOCKED                            │
│  Reason       protected system location: /etc    │
╰──────────────────────────────────────────────────╯
```

Risk levels are `SAFE`, `LOW`, `MEDIUM`, `HIGH`, `BLOCKED`.

## Architecture

```text
src/spaceai/
    main.py              Typer CLI: scan, analyze, volumes, check, clean, doctor
    config/settings.py   TOML + environment configuration
    models/              Pydantic models: disk, analysis, cleanup
    system/
        platform.py      Windows / WSL / Linux / macOS detection
        disk.py          Volume enumeration and capacity
        filesystem.py    The scanner: iterative, bounded-memory, cancellable
    analyzers/
        locations.py     Catalogue of known storage locations per platform
        categorizer.py   Location- and marker-based categorisation
        overview.py      Combines scan + categories + capacity
    cleanup/safety.py    The safety layer (the authority on what may be touched)
    ui/
        theme.py         Console and colour theme
        format.py        Byte, bar and path formatting
        panels.py        Rich renderables
        terminal.py      Interactive app and live scan progress
tests/                   132 tests, including adversarial path-safety cases
```

Design decisions worth knowing:

* **The scanner is iterative, not recursive.** An explicit stack means a
  pathological tree cannot exhaust the interpreter stack, and a hard depth
  guard (128) stops reparse loops.
* **Memory is bounded.** Only two small heaps of the largest files and
  directories are retained, never a list of every file, so scanning a
  million-file tree costs the same memory as scanning a hundred.
* **Failure is data, not an exception.** Permission errors, files that vanish
  mid-scan, locked files and unreadable directories increment
  `skipped_paths` and appear in the summary line. One bad directory never ends
  a scan.
* **Symlinks and junctions are skipped by default**, so nothing is
  double-counted and no loop can trap the walker.
* **Sparse and hard-linked files** are measured by allocated blocks where the
  platform reports them, so totals reflect real disk consumption.
* **One pass, two outputs.** Categorisation rides along on the scan through an
  observer hook rather than costing a second traversal.
* **Category attribution follows location, not filename.** `~/.npm` is npm's
  cache because that is where npm puts it. Where a known location and a marker
  directory disagree, whichever matches deeper in the path wins — so
  `~/Documents/app/node_modules` is Node.js, not Documents.

Scanning ~380,000 files takes roughly 2 seconds on a warm cache.

## Platform support

Windows is the primary target, with first-class WSL support; the platform layer
is isolated behind `system/platform.py` so macOS support is additive. Today the
scanner, safety layer and categoriser run on Windows, WSL, Linux and macOS;
Windows-specific known locations are populated when running on Windows or WSL.

## Development

```bash
pytest                    # 132 tests
ruff check src tests      # lint
ruff format src tests     # format
mypy                      # strict type checking, zero errors
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow and
[SECURITY.md](SECURITY.md) for the threat model and how to report a
vulnerability.

## Roadmap

| # | Milestone | State |
| --- | --- | --- |
| 1 | Project structure, CLI, scanner, UI, safety layer, tests | **done** |
| 2 | Cleanup actions, planner, preview and confirmation-gated executor | next |
| 3 | Docker, Python and Node analyzers | planned |
| 4 | LLM agent with scoped tools | planned |
| 5 | WSL analysis (read-only reporting on `.vhdx` disks) | planned |
| 6 | SQLite scan history and trend detection (`spaceai history`) | planned |
| 7 | Incremental scanning and caching | planned |

## License

MIT.
