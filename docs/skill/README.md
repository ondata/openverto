# Install the verto-explorer skill

The `verto-explorer` skill enables guided, interactive coordinate conversion
between Italian reference systems directly in your AI coding agent, using the
**[openverto](https://github.com/ondata/openverto)** CLI under the hood.

Skills can be installed in many ways — refer to your agent's documentation for the
available options. Here we use [skills](https://github.com/vercel-labs/skills), a
convenient tool that installs a skill in a single step across multiple agents
(Claude Code, OpenCode, GitHub Copilot, Codex, and more) in a unified way.

## Prerequisites

- The **openverto** CLI (`uv tool install openverto`) available on your PATH.
- Node.js (v18+) — required only for the `npx skills` method below. Install it via
  your system's package manager or from [nodejs.org](https://nodejs.org).

## Installation

Run:

```bash
npx skills add ondata/openverto --skill verto-explorer
```

### Step 1 — Select agents

The installer fetches the skill from the repository and asks which agents to
install it for. Several universal agents (including Claude Code) are enabled by
default. If your agent is missing from the default list, scroll down to
**Additional agents** to find and select it.

### Step 2 — Choose installation scope (Global recommended)

Choose between installing for the current project or globally (home directory,
available across all projects). **Global** makes the skill available in every
project.

### Step 3 — Symlink (Recommended)

Choose how the skill file is installed. We recommend **Symlink**: instead of
copying the file, a symbolic link points to the original source, so any update to
the skill is reflected immediately everywhere, with no need to reinstall.

### Step 4 — Confirm

Review and confirm with **Yes** to proceed.

## Alternative: manual installation

If you prefer not to use `npx skills`, you can download the skill folder directly
and add it to your agent without Node.js. The skill is located at
[`skills/verto-explorer/`](../../skills/verto-explorer/) in this repository —
refer to your agent's documentation for how to register a local skill folder.

## Update

To update the skill to the latest version:

```bash
npx skills update verto-explorer
```

## Usage

Once installed, use `/verto-explorer` in the selected agents to start a guided
coordinate-conversion session using openverto.

To explore the skill's full capabilities before or after installing, see the
[skill definition](../../skills/verto-explorer/SKILL.md).
