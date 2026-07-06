# AgentCore Skill

General skill for Amazon Bedrock AgentCore: deploy and operate harnesses and runtime agents, and migrate AI assistant configurations from 15 coding assistants (GitHub Copilot, Claude Code, Cursor, Cline, Codex, Windsurf, Antigravity, Gemini CLI, Deep Agents, Dexto, Firebender, Kimi Code CLI, OpenCode, Warp, agentic-core).

**Harness-first:** agents that are persona + skills + standard tools deploy as declarative harnesses (no code). Only agents with custom logic get generated Strands code. Verified against `agentcore` CLI 0.22.0 (July 2026).

## Quick Start

### Prerequisites

```bash
python3 scripts/preflight_check.py
```

Needs: Python ≥3.10, Node ≥20, uv, AWS CLI + credentials, `agentcore` CLI ≥0.22.

### Migration

```bash
# 1. Scan a repository for AI assistant configs
python3 scripts/scan_configs.py --repo-root <path> --format json

# 2. Generate the AgentCore project (harnesses + code runtimes)
python3 scripts/generate_project.py \
  --inventory migration-inventory.json \
  --output-dir ./agentcore-project \
  --region us-east-1

# 3. Deploy (or run the generated agentcore-commands.sh)
cd agentcore-project
./agentcore-commands.sh
```

## Structure

```
├── SKILL.md                     # General AgentCore skill (entry point)
├── scripts/
│   ├── preflight_check.py       # Verify prerequisites
│   ├── scan_configs.py          # Scan repo for AI configs → inventory
│   └── generate_project.py      # Inventory → AgentCore project (harness-first)
├── references/
│   ├── harness.md               # Harness commands, schema, skills, export-to-code
│   ├── migration.md             # Migration workflow
│   ├── source-formats.md        # Per-tool detection/parsing rules
│   ├── agentcore-mappings.md    # Mapping rules
│   ├── migration-modes.md       # Deploy workflow, errors, teardown
│   └── templates/
└── assets/
    └── poc-cve-verify/          # Worked migration example
```

## Installing as a Skill

```bash
# Claude Code (project-level)
cp -r <this-repo> .claude/skills/agentcore/
# or GitHub Copilot
cp -r <this-repo> .github/skills/agentcore/
```

## License

Internal use only.
