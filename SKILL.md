---
name: agentcore
description: "Use when deploying, operating, or migrating AI agents on Amazon Bedrock AgentCore — creating harnesses or runtime agents, adding skills/tools/gateways/memory/credentials, exporting a harness to code, or migrating AI assistant configurations (.github/agents, .claude/skills, .cursor/rules, MCP configs, hooks) from coding assistants. Triggers: 'migrate to AgentCore', 'agentcore migration', 'deploy to agentcore', 'create harness', 'export harness', 'add skill to harness', 'convert MCP to gateway', 'export agents to AWS', 'move agents to bedrock', 'agentcore harness', 'invoke agent runtime', 'agentcore deploy fails'."
---

# AgentCore

Build, deploy, operate, and migrate AI agents on Amazon Bedrock AgentCore. The `agentcore` CLI (npm `@aws/agentcore`) manages the full lifecycle via CDK/CloudFormation.

There are **two ways to run an agent**:

| Mode | What it is | When |
|---|---|---|
| **Harness** (default since GA, June 2026) | Declarative managed agent: `harness.json` = model + tools + skills + memory + limits. No agent code, no container. `agentcore create --defaults` creates one. | Persona + skills + standard tools cover the need |
| **Runtime** (code agent) | Your code (Strands/LangChain/ADK/OpenAI/VercelAI) deployed as CodeZip or Container | Custom orchestration, custom tool logic, middleware |

Start with a harness; `agentcore export harness` converts it to editable Strands code later if you outgrow the config (one-way door: code, unlike config, is yours to maintain).

## Key Concepts

| Term | Meaning |
|---|---|
| **Harness** | First-class AWS resource (`CreateHarness`/`UpdateHarness`/`InvokeHarness`): a fully managed agent defined by config. In a CLI project: `agentcore.json → harnesses[]` + `app/<name>/harness.json` + `system-prompt.md` |
| **Runtime** | A deployed code agent — `agentcore.json → runtimes[]`, code in `app/<name>/` |
| **Gateway** | MCP tool router — routes agent tool calls to MCP servers, Lambda, API Gateway, HTTP passthrough, inference providers, web-search connector |
| **Identity** | Secret vault — API keys and OAuth credentials; can reference existing AWS Secrets Manager ARNs |
| **Memory** | Managed memory — strategies: SEMANTIC, SUMMARIZATION, USER_PREFERENCE, EPISODIC |
| **Registry** | Private catalog of agents/tools/skills with approval workflow |

## Prerequisites

Run the bundled preflight before any workflow:

```bash
python3 scripts/preflight_check.py
```

Checks: Python ≥ 3.10, Node.js ≥ 20, **uv** (required for Python agents), AWS CLI + credentials, `agentcore` CLI ≥ 0.22 (`npm install -g @aws/agentcore`; upgrade with `agentcore update`), `bedrock-agentcore-control` namespace. Docker only for Container builds.

## Core Lifecycle

```bash
agentcore create --defaults        # New project with a default harness (interactive wizard without flags)
agentcore dev                      # Local dev server + browser-based agent inspector
agentcore validate                 # Validate agentcore/ config files
agentcore deploy                   # Deploy via CDK → CloudFormation stack AgentCore-<project>-default
agentcore invoke --agent <name> "test prompt"
agentcore logs / traces / status   # Observability
agentcore exec -- <cmd>            # Shell into a deployed agent container
```

Non-interactive create (all flags marked `[non-interactive]` in `--help`):

```bash
agentcore create --name <harness> --project-name <proj> --defaults \
  --skip-git --output-dir <dir>
```

Project layout (ground truth, CLI 0.22.0):

```
<project>/
├── AGENTS.md                 # AI-assistant context written by the CLI
├── agentcore/
│   ├── agentcore.json        # Flat resource arrays: runtimes[], harnesses[], memories[], credentials[], agentCoreGateways[], ...
│   ├── aws-targets.json      # ARRAY of {name, account (12-digit string), region}
│   ├── .env.local            # Gitignored secrets
│   ├── .llm-context/         # TypeScript schema types — the schema authority; read these before editing JSON by hand
│   └── cdk/                  # CDK project (npm install required before first deploy)
└── app/
    ├── <harness>/            # harness.json + system-prompt.md (no code)
    └── <agent>/              # main.py, pyproject.toml, model/, skills/, mcp_client/ (code agent)
```

## Harness Workflows

Add/manage harnesses, tools, skills, memory; export to code. See `references/harness.md` for commands, `harness.json` schema, and skill sources (`--path`/`--s3`/`--git`/`--aws-skills`).

```bash
agentcore add harness --name <n> --system-prompt "<text>" [--tools ...] [--memory-mode managed ...]
agentcore add skill --harness <n> --path <dir>        # skill dir with SKILL.md
agentcore add tool  --harness <n> --type remote_mcp --name <t> --url <mcp-url>
agentcore export harness --name <n> | --arn <arn>     # → editable Strands agent under app/
```

## Migration from coding assistants

Migrate agents/skills/MCP/hooks from 15 assistant formats (Claude Code, Copilot, Cursor, …) to AgentCore. **REQUIRED:** follow `references/migration.md` — discovery scan, mapping rules, harness-first generation, deploy. Supporting docs: `references/source-formats.md` (detection), `references/agentcore-mappings.md` (mapping rules), `references/migration-modes.md` (deploy/teardown/errors).

```bash
python3 scripts/scan_configs.py --repo-root <path> --format json   # → migration-inventory.json
python3 scripts/generate_project.py --inventory migration-inventory.json --output-dir ./agentcore-project --region us-east-1
```

## Key Rules

- **Harness-first** — agents that are persona + skills + standard tools become harnesses (config), not code. Generate code runtimes only for custom logic.
- **`.llm-context/` is the schema authority** — when editing `agentcore.json`/`harness.json` by hand, conform to the TypeScript types there, then `agentcore validate`.
- **Never put secrets in generated files** — API keys → Identity credentials (`agentcore add credential`), or reference an existing Secrets Manager ARN. Non-secrets → `envVars`.
- **Renaming a resource destroys and recreates it** — the `name` field is the CloudFormation logical ID.
- **`npm install` in `agentcore/cdk/`** before first deploy, or deploy fails with `tsc: not found`.
- **`agentcore create` overwrites `agentcore.json`** — back up a pre-generated config, create with `--no-agent`, restore.
- **Don't `add agent` for runtimes already in `agentcore.json`** — fails with "already exists". `add` commands are for adding NEW resources.
- **aws-targets.json is a JSON array** — `[{"name","account","region"}]`, `account` is the 12-digit ID string (not `accountId`).
- **Naming**: harness/agent names alphanumeric+underscores, start with letter, ≤48 chars; project names alphanumeric only, ≤23 chars; gateway names alphanumeric+hyphens.
- **Default model is Claude** — harness default `global.anthropic.claude-sonnet-4-6`; code-agent template uses `global.anthropic.claude-sonnet-4-5-20250929-v1:0`. Nova (`amazon.nova-lite-v1:0`) remains a fallback if Anthropic model access isn't enabled in the account.
- **Streaming is the default entrypoint pattern** — `async for event in agent.stream_async(...): yield event` (the CLI's own template). The old "non-streaming only" workaround is obsolete.
- **Read EXPORT_NOTES.md after `export harness`** — it lists manual follow-ups the exporter couldn't automate.
- **Test with simple prompts first** — verify deploy works before complex prompts.

## Resolved Blockers (May → July 2026)

Limitations documented by earlier migrations that AWS has since fixed — do not re-apply old workarounds:

| Old blocker | Current state |
|---|---|
| Console-created harnesses locked (no `update-harness` API) | Harness GA: `UpdateHarness` API exists; `agentcore export harness --arn <arn>` converts any harness (incl. Console-created) to a CLI-managed code agent |
| Skills mountable only via Console UI | `agentcore add skill --harness <n> --path/--s3/--git/--aws-skills` |
| HITL gates had no mechanism | Gateway **elicitation pass-through** (form/URL modes); Step Functions harness integration with approval steps |
| Claude required use-case form; Nova Lite forced default | Claude Sonnet is the CLI default; LiteLLM + Bedrock Mantle add more providers |
| Streaming `yield` broke CLI display | Fixed — streaming is the default template pattern |
| Secrets had to be copied into Identity vault | Identity credential providers can reference existing Secrets Manager ARNs |

## Error Handling

| Error | Action |
|---|---|
| `tsc: not found` on deploy | `cd agentcore/cdk && npm install` |
| "already exists" from `add agent` | Resource already in `agentcore.json` — edit the JSON instead |
| Deploy fails: stack already exists | `aws cloudformation delete-stack --stack-name AgentCore-<project>-default` |
| `ThrottlingException` (tokens/day) | Request increase via Service Quotas → Amazon Bedrock |
| `ModelNotAccessibleException` | Enable model access in Bedrock Console, or switch `modelId` to `amazon.nova-lite-v1:0` |
| `agentcore create` outputs nothing | Invalid project name — alphanumeric only, ≤23 chars |
| Stdio MCP server | No direct support — see MCP mapping in `references/agentcore-mappings.md` |

## Bundled Resources

### Scripts
- `scripts/preflight_check.py` — verify all prerequisites
- `scripts/scan_configs.py` — scan a repo for 15 AI-assistant config formats → `migration-inventory.json`
- `scripts/generate_project.py` — generate an AgentCore project (harnesses + code runtimes) from the inventory

### References
- `references/harness.md` — harness commands, `harness.json` schema, skills, export-to-code
- `references/migration.md` — the migration workflow (discover → parse → map → generate → deploy)
- `references/source-formats.md` — per-tool parsing rules for 15 assistant formats
- `references/agentcore-mappings.md` — mapping rules: source artifacts → AgentCore equivalents
- `references/migration-modes.md` — deploy workflow, validation, teardown, error table
- `references/templates/` — templates for `agentcore.json`, `harness.json`, `runtime-metadata.json`, `Dockerfile`, registry records

### Assets
- `assets/poc-cve-verify/` — complete worked migration of `cve-verify.agent.md`
