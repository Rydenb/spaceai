# Build SpaceAI — an AI-powered disk cleanup and system analysis CLI

I want you to build a polished CLI application called **SpaceAI**.

The purpose of SpaceAI is to help users understand what is consuming disk space on their computer and safely recover space through an AI-powered interface.

The key idea is:

> The user should be able to ask natural-language questions like "What's taking up all my space?", "Can I safely free up 20GB?", or "Clean up my caches", and SpaceAI should inspect the computer, explain what it finds, propose cleanup actions, and require explicit user approval before making destructive changes.

## Important principles

### Safety comes first

NEVER allow the AI to blindly execute arbitrary destructive shell commands.

The AI must interact with the operating system through a controlled set of tools.

Every destructive operation must:

1. Be represented as a structured cleanup action.
2. Explain what will be deleted.
3. Estimate how much space will be recovered.
4. Show the exact paths/resources affected.
5. Require explicit user confirmation.
6. Prefer reversible operations where possible.
7. Refuse to delete critical system files.

Do NOT implement a generic `run_any_command(command)` tool for the AI.

The AI should instead receive carefully scoped tools such as:

* `scan_disk`
* `find_large_files`
* `find_large_directories`
* `analyze_cache`
* `analyze_python`
* `analyze_node`
* `analyze_docker`
* `analyze_git`
* `analyze_wsl`
* `get_disk_usage`
* `preview_cleanup`
* `execute_cleanup`

## Initial platform

Build for **Windows first**, with strong support for **WSL/Linux environments**.

Design the architecture so macOS/Linux support can be added later.

Detect the current operating system automatically.

## Technology

Use:

* Python 3.12+
* Typer for the CLI
* Rich for terminal UI
* Pydantic for structured models
* pathlib/os/shutil/subprocess for system operations
* SQLite for persistent local data if needed
* An LLM API for the AI agent

Keep the code modular and typed.

Use async code where it actually provides value, but don't introduce unnecessary complexity.

## CLI

The primary command should be:

```bash
spaceai
```

Also support commands such as:

```bash
spaceai scan
spaceai clean
spaceai analyze
spaceai doctor
```

The default `spaceai` command should open an interactive terminal interface.

Example:

```text
╭──────────────────────────────────────────────╮
│                   SPACEAI                    │
│          Intelligent Disk Cleanup            │
╰──────────────────────────────────────────────╯

Disk usage

███████████████████████░░░░░░  412 / 512 GB

Used:       412 GB
Free:       100 GB
Usage:       80.5%

Potentially recoverable: 27.4 GB

Largest categories:

  Docker                 12.1 GB
  Downloads               6.8 GB
  Python                  3.9 GB
  Node.js                 2.7 GB
  Caches                  1.9 GB

What would you like to do?
>
```

The interface should feel polished and modern.

## Natural language interaction

The user should be able to type:

```text
What's taking up all my space?
```

The agent should decide which tools it needs.

For example:

```text
User:
What's taking up all my space?

Agent:
I'll scan your disk and identify the largest categories.

[Scanning filesystem...]

Found:

Docker       12.1 GB
Downloads     6.8 GB
Python        3.9 GB
Node.js       2.7 GB

Docker appears to be the biggest opportunity.

Would you like me to investigate Docker?
```

The agent should NOT immediately delete anything.

## Tool architecture

Create a clean tool abstraction.

For example:

```text
spaceai/
    agent/
        agent.py
        tools.py
        prompts.py

    system/
        filesystem.py
        disk.py
        windows.py
        wsl.py

    analyzers/
        docker.py
        python.py
        node.py
        git.py
        cache.py
        downloads.py

    cleanup/
        planner.py
        actions.py
        executor.py
        safety.py

    ui/
        terminal.py
        panels.py
        prompts.py

    models/
        disk.py
        cleanup.py
        analysis.py

    storage/
        database.py

    config/
        settings.py

    main.py
```

Adjust the structure if you have a better architecture, but maintain strong separation of concerns.

## Disk scanner

Implement a fast filesystem scanner.

It should be able to determine:

* Total disk space
* Free disk space
* Used disk space
* Largest directories
* Largest files
* File counts
* Directory sizes

Avoid loading the entire filesystem into memory.

Use efficient traversal and gracefully handle:

* Permission errors
* Symbolic links
* Junctions
* Files that disappear during scanning
* Locked files
* System-protected directories

Never crash because one directory cannot be accessed.

## Intelligent categorization

The application should attempt to categorize storage usage.

Initial categories:

* Windows
* Applications
* Downloads
* Documents
* Pictures
* Videos
* Games
* Docker
* Python
* Node.js
* Git
* VS Code
* WSL
* Caches
* Temporary files
* Unknown

Do not simply classify based on filenames.

Use known locations and heuristics where appropriate.

## Cleanup system

Create a structured cleanup model.

Example:

```python
class CleanupAction:
    id: str
    title: str
    description: str
    category: str
    paths: list[str]
    estimated_bytes: int
    risk_level: str
    reversible: bool
```

Possible risk levels:

```text
SAFE
LOW
MEDIUM
HIGH
BLOCKED
```

The AI should only be allowed to execute actions that pass the safety layer.

## Cleanup preview

When the user asks to clean something, show a preview first.

Example:

```text
╭──────────── Cleanup Preview ─────────────╮

Docker build cache

Potential recovery: 8.4 GB

The following resources will be removed:

  • Unused Docker build cache
  • Unused intermediate layers

Risk: LOW

Nothing has been deleted yet.

Proceed? [y/N]
╰──────────────────────────────────────────╯
```

Only execute after explicit confirmation.

## Safety rules

Implement a dedicated safety module.

The cleanup engine must prevent deletion of:

* Windows system directories
* User profile root
* Documents unless explicitly selected
* Desktop unless explicitly selected
* Important application directories
* Boot-related files
* System32
* Program Files
* Windows directory
* Arbitrary paths proposed by the LLM

Do not trust the LLM to determine whether a path is safe.

The safety layer itself must enforce these rules.

Normalize and resolve paths before performing operations.

Protect against path traversal and symlink/junction tricks.

## Docker analyzer

If Docker is installed, analyze:

* Images
* Containers
* Volumes
* Build cache

Report:

```text
Docker

Images:       8.2 GB
Containers:   1.4 GB
Volumes:      2.1 GB
Build cache:  5.8 GB

Potentially recoverable: 7.3 GB
```

Do not automatically remove anything.

## Python analyzer

Detect common Python storage usage:

* pip cache
* Poetry cache
* Conda environments
* virtual environments
* package caches

Clearly distinguish between:

```text
cache
```

and:

```text
environment / project data
```

Never suggest deleting an active project environment without warning.

## Node analyzer

Detect:

* npm cache
* pnpm store
* Yarn cache
* node_modules

For `node_modules`, show which projects they belong to instead of treating all of them as disposable.

Example:

```text
Node.js

node_modules: 14.8 GB

Largest projects:

project-a     5.2 GB
project-b     3.7 GB
project-c     2.1 GB
```

## WSL analyzer

Detect WSL installations if available.

Show:

* Distributions
* Approximate storage usage
* Large directories inside distributions

Be VERY careful around `.vhdx` files.

Do not automatically modify or compact WSL virtual disks.

Instead explain what is happening and provide a safe recommendation.

## AI behavior

The AI should act like a knowledgeable system administrator.

It should:

* Investigate before making claims.
* Explain technical findings in understandable language.
* Ask for clarification only when necessary.
* Never pretend it performed an action it didn't perform.
* Never claim something is safe without evidence.
* Prefer inspection before cleanup.
* Provide estimates rather than fake precision.
* Tell the user when it doesn't have enough information.

Example:

```text
User:
Free up 10GB.

AI:
I found several possible cleanup opportunities totaling
18.3GB.

The safest options are:

1. Docker build cache — 7.4GB
2. pip cache — 2.1GB
3. npm cache — 1.3GB

These total 10.8GB.

I can prepare a cleanup plan for these three.
```

## LLM abstraction

Do not hard-code the application around one specific model provider.

Create an abstraction such as:

```python
class LLMProvider:
    async def generate(...)
```

Then allow providers to be configured through environment variables.

For example:

```text
SPACEAI_PROVIDER=
SPACEAI_API_KEY=
SPACEAI_MODEL=
```

Keep provider-specific code isolated.

## Configuration

Use a configuration file and environment variables.

Potential configuration:

```text
SPACEAI_PROVIDER
SPACEAI_MODEL
SPACEAI_API_KEY
SPACEAI_SCAN_DEPTH
SPACEAI_MAX_FILE_SIZE
SPACEAI_EXCLUDED_PATHS
```

Never store API keys directly in source code.

## Persistent history

Store previous scans locally.

Allow the user to see:

```text
spaceai history
```

Example:

```text
Sep 7    412 GB used
Sep 5    398 GB used
Aug 28   371 GB used
```

Eventually this should allow SpaceAI to identify trends:

```text
Your disk usage increased by 41 GB over the last 10 days.

The largest increase appears to be:

Docker: +23 GB
Games:  +11 GB
Other:   +7 GB
```

## Performance

Disk scanning can be expensive.

Implement:

* Progress indicators
* Cancellation
* Caching where appropriate
* Incremental scanning where possible
* Parallelism only where beneficial

Never freeze the terminal UI during a long scan.

## Error handling

The program should gracefully handle:

* Permission denied
* Missing files
* Files changing during scans
* Docker unavailable
* WSL unavailable
* API unavailable
* Network errors
* Corrupted configuration
* Invalid user input

Provide useful error messages.

## Testing

Write tests for:

* Disk calculations
* Path safety
* Cleanup validation
* Categorization
* Cleanup planning
* Configuration
* Dangerous path detection

Create tests that specifically verify the application CANNOT delete protected paths through malformed input.

## Documentation

Create:

```text
README.md
CONTRIBUTING.md
SECURITY.md
```

The README should include:

* What SpaceAI is
* Installation
* Configuration
* Usage
* Example interactions
* Safety model
* Architecture
* Development instructions

## Development process

Do NOT attempt to build every feature immediately.

Work incrementally.

First:

1. Create the repository structure.
2. Implement the CLI.
3. Implement disk scanning.
4. Implement the terminal UI.
5. Implement the cleanup action/safety architecture.
6. Implement Docker/Python/Node analyzers.
7. Add the LLM agent.
8. Add WSL analysis.
9. Add history.
10. Polish the UI.

After each major feature:

* Run tests.
* Run the application.
* Fix errors.
* Keep the project in a working state.

Before writing large amounts of code, inspect the repository and existing files.

If the repository already contains code, preserve useful existing work rather than overwriting it.

## First task

Start by inspecting the current directory/repository.

Then create the initial SpaceAI project with:

* Python project configuration
* CLI entry point
* Basic Rich UI
* Disk usage scanner
* Safe filesystem traversal
* Tests
* README

Do NOT implement destructive cleanup yet.

Once the initial version works, summarize what you built, how to run it, and what the next logical milestone is.
