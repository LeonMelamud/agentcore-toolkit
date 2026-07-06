# AgentCore Migration Skill

Migrate AI assistant configurations from 14+ coding assistants to Amazon Bedrock AgentCore Runtime, Gateway, Identity, and Registry project scaffolds.

## Supported Sources

GitHub Copilot, Claude Code, Cursor, Cline, Codex, Windsurf, Antigravity, Gemini CLI, Deep Agents, Dexto, Firebender, Kimi Code CLI, OpenCode, Warp, agentic-core.

## Quick Start

### Prerequisites

```bash
python3 scripts/preflight_check.py
```

### 1. Scan repository

```bash
python3 scripts/scan_configs.py --repo-root <path> --format json
```

### 2. Generate AgentCore project

```bash
python3 scripts/generate_project.py \
  --inventory migration-inventory.json \
  --output-dir ./agentcore-project \
  --region us-east-1
```

### 3. Deploy

```bash
cd agentcore-project
agentcore create --defaults
cd agentcore/cdk && npm install && cd ../..
agentcore validate
agentcore deploy
```

## Structure

```
├── SKILL.md           # Skill instructions (for AI assistant integration)
├── scripts/           # Migration automation scripts
│   ├── preflight_check.py   # Verify prerequisites
│   ├── scan_configs.py      # Scan repo for AI configs
│   └── generate_project.py  # Generate AgentCore project
├── references/        # Mapping docs and templates
│   ├── source-formats.md
│   ├── agentcore-mappings.md
│   ├── migration-modes.md
│   └── templates/
└── assets/            # POC examples
    └── poc-cve-verify/
```

## Installing as a Skill

To use this as a skill in your AI assistant:

```bash
# In your project, copy the skill:
cp -r <this-repo> .github/skills/agentcore-migration/
```

Or reference it directly from your agent's `skills:` frontmatter.

## License

Internal use only.
