# AgentCore Skill

General skill for Amazon Bedrock AgentCore: deploy and operate harnesses and runtime agents, and migrate AI assistant configurations from 15 coding assistants (GitHub Copilot, Claude Code, Cursor, Cline, Codex, Windsurf, Antigravity, Gemini CLI, Deep Agents, Dexto, Firebender, Kimi Code CLI, OpenCode, Warp, agentic-core).

**Harness-first:** agents that are persona + skills + standard tools deploy as declarative harnesses (no code). Only agents with custom logic get generated Strands code. Verified against `agentcore` CLI 0.22.0 (July 2026).

The plugin also bundles companion AWS skills — `aws-cloudformation`, `aws-expert`, `aws-serverless`, `aws-skills`, `aws-solution-architect` — so a coding agent has broader AWS context when building or migrating agents.

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

This repo is a Claude Code **plugin** that bundles the `agentcore` skill plus a set of companion AWS skills (all auto-discovered from `skills/`).

```
├── .claude-plugin/
│   ├── plugin.json              # Plugin manifest
│   └── marketplace.json         # Marketplace manifest (installable via /plugin)
├── skills/
│   ├── aws-cloudformation/      # CloudFormation authoring
│   ├── aws-expert/              # General AWS guidance
│   ├── aws-serverless/          # Serverless (Lambda/API GW) patterns
│   ├── aws-skills/              # AWS skills index
│   ├── aws-solution-architect/  # Architecture guidance
│   └── agentcore/               # The AgentCore migration skill
│       ├── SKILL.md             # Entry point
│       ├── scripts/             # preflight_check, scan_configs, generate_project, invoke_harness
│       ├── references/          # harness.md, migration.md, security-iam.md, deployment-checklist.md, ...
│       ├── evals/evals.json     # Regression scenarios (self-test)
│       └── assets/              # poc-cve-verify/ (+ VERIFIED.md), iam-policies/
└── LICENSE                      # MIT
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
