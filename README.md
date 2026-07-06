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

This repo is a Claude Code **plugin** that bundles the `agentcore` skill.

```
├── .claude-plugin/
│   ├── plugin.json              # Plugin manifest
│   └── marketplace.json         # Marketplace manifest (installable via /plugin)
└── skills/agentcore/            # The skill
    ├── SKILL.md                 # Entry point
    ├── scripts/
    │   ├── preflight_check.py   # Verify prerequisites
    │   ├── scan_configs.py      # Scan repo for AI configs → inventory
    │   ├── generate_project.py  # Inventory → AgentCore project (harness-first)
    │   └── invoke_harness.py    # boto3 invoke fallback
    ├── references/              # harness.md, migration.md, security-iam.md, deployment-checklist.md, ...
    ├── evals/evals.json         # Regression scenarios (self-test)
    └── assets/
        ├── poc-cve-verify/      # Worked migration example (+ VERIFIED.md)
        └── iam-policies/        # Least-privilege trust + permissions templates
```

## Installing

**As a plugin (Claude Code marketplace):**

```
/plugin marketplace add <owner>/agentcore-migration
/plugin install agentcore@agentcore-skills
```

**As a personal or project skill (copy the bundle):**

```bash
cp -r skills/agentcore ~/.claude/skills/agentcore        # personal
cp -r skills/agentcore .claude/skills/agentcore          # project (or .github/skills/ for Copilot)
```

## License

MIT — see [LICENSE](LICENSE).
