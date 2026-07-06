---
name: agentcore-migration
description: "Migrate AI assistant configurations (.github/agents, .claude/skills, .cursor/rules, .agents/, MCP configs, hooks) from 14+ coding assistants to Amazon Bedrock AgentCore Runtime, Gateway, Identity, and Registry project scaffolds. Use when asked to 'migrate to AgentCore', 'agentcore migration', 'convert to AgentCore runtime', 'convert to AgentCore harness', 'export agents to AWS', 'migrate skills to AgentCore', 'deploy agents to AgentCore', 'scan AI assistant configs', 'convert MCP to gateway', 'agentcore harness migration', 'migrate .github agents', or 'move agents to bedrock'."
---

# AgentCore Migration

Migrate AI assistant configurations from coding assistants to Amazon Bedrock AgentCore managed harnesses. A **harness** is an AgentCore project that contains one or more agent runtimes — each runtime reasons, uses tools, and completes multi-step tasks autonomously. The migration scans 15 source formats, maps artifacts to AgentCore equivalents, and generates a deployable harness scaffold using the Strands Agent Framework.

## Key Concepts

| Term | Meaning |
|------|---------|
| **Harness** (project) | An AgentCore project (`agentcore create`) — the managed infrastructure wrapper containing agents, memories, credentials, gateways |
| **Runtime** (agent) | A single agent inside the harness — defined in `agentcore.json` → `runtimes[]`, code lives in `app/<name>/` |
| **Gateway** | An MCP tool router — routes agent tool calls to remote MCP servers, Lambda, or API Gateway |
| **Identity** | Secret vault — API keys, OAuth credentials stored securely and injected at runtime |
| **Memory** | Managed memory — semantic, summarization, user preference, or episodic strategies |

## When to Use

- Migrating a repo's AI assistant setup to AgentCore Runtime
- Converting MCP server configs to AgentCore Gateway
- Deploying existing agents/skills to AgentCore Runtime
- Publishing agents to AWS Agent Registry

## Prerequisites

- Node.js 20+ (`agentcore` CLI: `npm install -g @aws/agentcore`)
- Python 3.10+
- AWS credentials configured (`aws configure`)
- IAM permissions for AgentCore API calls (Bedrock AgentCore, CloudFormation, IAM)
- AWS CLI with AgentCore namespaces available: `bedrock-agentcore-control` for create/list/manage APIs, `bedrock-agentcore` for runtime invocation APIs
- Docker (only required for Container-build runtimes — not needed for CodeZip)

> **Default build: CodeZip** — no Docker required. The managed Python 3.14 runtime handles dependencies via `pyproject.toml`. Only use Container build when agents need system packages or non-Python tools.

---

## Workflow

### Preflight — Verify Prerequisites

Before starting any migration step, run the preflight check to verify all required tools and libraries are installed:

```bash
python3 scripts/preflight_check.py
```

The script checks:

| Check | What it verifies | Install if missing |
|-------|------------------|--------------------|
| Python version | ≥ 3.10 | Install from python.org or `brew install python` |
| Node.js version | ≥ 20 | `brew install node` or `nvm install 20` |
| AWS CLI | `aws` command available | `brew install awscli` or `pip install awscli` |
| AWS credentials | `aws sts get-caller-identity` succeeds | `aws configure` or set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |
| AgentCore CLI | `agentcore` command available | `npm install -g @aws/agentcore` |
| AgentCore namespace | `aws bedrock-agentcore-control help` succeeds | Update AWS CLI: `pip install --upgrade awscli` |

If any check fails, the script prints the install command and exits with a non-zero code. Fix all issues before proceeding to Step 0.

### Step 0 — Confirm Migration Target

The migration **always creates a new CDK-managed AgentCore project**. This is the only supported deployment mode — the `agentcore` CLI manages the full lifecycle (CloudFormation stack, ECR repository, CodeBuild project, IAM roles, and agent runtimes).

> **⚠️ AWS Limitation — Console-created harnesses:** Runtimes created via the AWS Console (Bedrock → AgentCore → Harness) are **harness-managed** and cannot be updated through the CLI or API. The `agentcore import runtime` and `update-agent-runtime` APIs both return: *"This agent runtime is managed by harness '...' and cannot be updated directly."* If you have a Console-created harness, this migration creates a **separate, new project** alongside it.

Before running the generator, confirm:
- The target AWS region (e.g., `us-east-1`)
- AWS credentials are configured (`aws sts get-caller-identity`)
- No conflicting CloudFormation stack exists (pattern: `AgentCore-<projectname>-default`)

### Step 1 — Discover

Scan the repository for all AI assistant configuration files:

```bash
python3 scripts/scan_configs.py --repo-root <path> --format json
```

The script checks 15 known source formats and reports what it finds. See `references/source-formats.md` for the full detection table.

**Supported sources:** GitHub Copilot, Claude Code, Cursor, Cline, Codex, Windsurf, Antigravity, Gemini CLI, Deep Agents, Dexto, Firebender, Kimi Code CLI, OpenCode, Warp, agentic-core.

Print a discovery summary:

```
╔═══════════════════════════════════════════════════╗
║          AgentCore Migration — Discovery           ║
╠═══════════════════════════════════════════════════╣
║  Agents found:      {N}                           ║
║  Skills found:      {M}                           ║
║  MCP servers:       {K}                           ║
║  Hooks:             {H}                           ║
║  Prompts:           {P}                           ║
║  Sources detected:  {list of tool names}          ║
╚═══════════════════════════════════════════════════╝
```

### Step 2 — Parse

For each detected source, extract structured data. Output a `migration-inventory.json` with all parsed artifacts, each tagged with:

| Artifact type | Fields extracted |
|---|---|
| **Agent** | name, description, persona, system prompt, tools, handoffs, activation |
| **Skill** | name, description, body, scripts (paths), references (paths) |
| **MCP server** | name, URL/command, transport, env vars, auth config |
| **Hook** | event name, script path, backend type |
| **Memory** | type, path, content summary |
| **Prompt** | name, path, content |

### Step 3 — Map to AgentCore

Apply mapping rules from `references/agentcore-mappings.md`:

**Agents → Runtime agents**
- Persona + Instructions → `systemPrompt` in `runtime-metadata.json` and `SYSTEM_PROMPT` in `main.py`
- Flatten persona block (role, identity, style, principles) into coherent system prompt
- Tools list → reviewable `allowedTools` metadata and runtime adapter requirements
- Handoffs → additional agents in same project (`agentcore add agent --name <handoff_target> --type byo --language Python --framework Strands --model-provider Bedrock ...`)

**Skills → Harness-mounted skills (preferred) or baked into code package**
- **Auto-loading at runtime:** The generated `main.py` automatically discovers and loads skills from two paths (in priority order): (1) `.agent/skills/` — harness-mounted via Console UI, and (2) `skills/` — baked into the code package. No manual code changes needed.
- **Harness mode (preferred):** Add skills via the Console "Add skill" button or harness config. Skills are mounted to the runtime filesystem at `.agent/skills/<name>/SKILL.md`. The agent reads them at invocation time — no redeploy needed to update skills.
- **CodeZip mode (fallback):** `SKILL.md` + `scripts/` + `references/` → copied into `app/<agent>/skills/<name>/` at build time. Skills declared in the agent's `skills:` frontmatter are automatically included by the generator.
- **Generic agent pattern:** A single generic agent with a minimal system prompt can load any combination of skills mounted at runtime. Swap skills without redeploying the agent.

**MCP servers → Gateway targets**
- Production → `agentcore add gateway --name <gateway>` + `agentcore add gateway-target --type mcp-server --endpoint <url> --gateway <gateway>`
- Stdio MCP → `MANUAL`; publish as a remote MCP endpoint before adding a Gateway target
- MCP env vars → AgentCore Identity credentials or runtime `envVars`

**Hooks → Exec commands + Observability**
- `sessionStart` → pre-invocation script + `agentcore invoke --runtime <name> --session-id <sid> --exec "<script>"`
- `sessionEnd` → post-invocation script + same exec pattern after the agent completes
- Error hooks → CloudWatch Observability (automatic OTEL)
- HITL gates → runtime adapter approval tool/function; mark `MANUAL` if the target app has no tool-use adapter yet

**Memory → AgentCore Memory**
- Conversation context → `agentcore add agent --memory shortTerm` or a generated memory resource
- Long-term learnings → `agentcore add agent --memory longAndShortTerm` or `agentcore add memory --strategies SEMANTIC,SUMMARIZATION,USER_PREFERENCE,EPISODIC`
- Feature memory → runtime filesystem/session storage (persistent per session when configured)

**Secrets → AgentCore Identity**
- API keys, passwords, tokens, passcodes, user codes → `agentcore add credential --type api-key --name <name> --api-key "$VALUE"`
- Non-secret env vars → runtime `envVars` in `agentcore/agentcore.json` and `runtime-metadata.json`

Classify each mapping: `AUTO` (no review needed), `MANUAL` (needs human review), `SKIP` (no equivalent).

### Step 4 — Generate

Run the generator:

```bash
python3 scripts/generate_project.py \
  --inventory migration-inventory.json \
  --output-dir ./agentcore-project \
  --region us-east-1
```

#### Output structure (CodeZip build — no Docker):

```
agentcore-project/                    # ← The project
├── agentcore/
│   ├── agentcore.json        # Project config — runtimes (CodeZip), gateways, credentials
│   ├── aws-targets.json      # JSON array: [{"name","account","region"}]
│   └── cdk/                  # CDK project (auto-scaffolded, needs npm install)
├── app/
│   └── <agent-name>/         # ← One runtime per agent
│       ├── main.py           # Strands Agent entrypoint (BedrockAgentCoreApp)
│       ├── model/
│       │   ├── __init__.py
│       │   └── load.py       # BedrockModel loader (Nova Lite default)
│       ├── pyproject.toml    # Dependencies (strands-agents, bedrock-agentcore)
│       ├── runtime-metadata.json # Review: systemPrompt, tools, env
│       ├── scripts/          # Migrated agent scripts
│       └── skills/           # Declared skills baked into package
├── registry/                 # Registry record manifests per agent
├── agentcore-commands.sh     # Credential + gateway + deploy commands
└── migration-report.md       # Summary + manual action items
```

Use templates from `references/templates/` for file generation.

The generator writes a complete `agentcore/agentcore.json` with all runtimes pre-populated. Do **not** run `agentcore add agent` commands separately — they will fail with "already exists". The generated `agentcore-commands.sh` only contains credential, gateway, deploy, and invoke commands.

**Skills filtering:** Only skills explicitly declared in an agent's `skills:` frontmatter are copied into that agent's package. Agents with no `skills:` declaration get no skill files — note this in the migration report as a review item.

**Idempotent re-runs:** The generator cleans the output directory before writing, so repeated runs produce a consistent result.

### Step 5 — Report

Generate `migration-report.md`:
1. Summary table — counts by artifact type and status
2. Per-agent detail — what mapped, what skipped
3. Manual action items — secrets, gateway ARNs, custom deps
4. Deployment commands — ready to copy-paste

### Step 6 — Initialize & Deploy

This step bootstraps the AgentCore project and deploys to AWS. The `agentcore` CLI creates a CloudFormation stack (named `AgentCore-<projectname>-default`) that provisions IAM roles and the agent runtimes.

```bash
cd <output-dir>

# 1. Initialize the agentcore project (creates CDK scaffold)
agentcore create --defaults
# OR if you have a pre-generated agentcore.json:
#   cp agentcore/agentcore.json agentcore/agentcore.json.bak
#   agentcore create --name <project-name> --no-agent
#   cp agentcore/agentcore.json.bak agentcore/agentcore.json

# 2. Install CDK dependencies (REQUIRED before first deploy)
cd agentcore/cdk && npm install && cd ../..

# 3. Validate the project
agentcore validate

# 4. Add credentials (secrets → Identity vault)
agentcore add credential --type api-key --name <name> --api-key "$SECRET"

# 5. Add gateways (MCP servers → Gateway targets)
agentcore add gateway --name <gateway>
agentcore add gateway-target --name <target> --type mcp-server --endpoint <url> --gateway <gateway>

# 6. Deploy to AWS
agentcore deploy

# 7. Test
agentcore invoke --runtime <agent> --prompt "test"
```

> **Critical — `npm install` in `agentcore/cdk/`:** The CDK project requires `node_modules` before deploy. Skip this and `agentcore deploy` fails with `tsc: not found`.

> **Important — `agentcore create` overwrites `agentcore.json`:** The `agentcore create` command generates a fresh config. If you pre-generated one, back up and restore after init (steps shown above).

> **Model access — Nova Lite is the safe default:** Anthropic Claude models require a use-case form submission in the Bedrock Console. Nova Lite (`amazon.nova-lite-v1:0`) is available immediately but has low daily token quotas. Request a quota increase via Service Quotas → Amazon Bedrock if you hit `ThrottlingException` during testing.

Run `agentcore-commands.sh` to execute the generated credential, gateway, and deploy commands, or run them individually after review.

#### Teardown

To remove all deployed resources:

```bash
# Delete the CloudFormation stack (removes ECR, CodeBuild, runtimes, IAM roles)
aws cloudformation delete-stack --stack-name AgentCore-<projectname>-default --region <region>
aws cloudformation wait stack-delete-complete --stack-name AgentCore-<projectname>-default --region <region>
```

---

## POC: cve-verify Migration

See `assets/poc-cve-verify/` for a complete worked example. Key mappings:

| Source | Target | Notes |
|---|---|---|
| Persona + instructions | `main.py` + `runtime-metadata.json` | Flattened `SYSTEM_PROMPT` |
| `tools: [read, search, execute]` | `allowedTools: ["shell", "file_operations"]` | Builtins |
| `query-cve-agent.sh`, `query_cve_core.py` | `Dockerfile COPY` | Scripts in container |
| `NEXUS_IQ_USERCODE/PASSCODE` | `agentcore add credential` | Identity vault |
| `NEXUS_IQ_URL` | runtime `envVars` | Non-secret config |
| HITL gate ("Continue?") | Runtime adapter approval function | Agent pauses |
| CSV file I/O | Runtime filesystem | Built-in persistent |

---

## Error Handling

| Error | Action |
|-------|--------|
| No configs found | Print paths checked, halt |
| Unsupported format | Log as SKIP, continue |
| Script deps missing | Add to Dockerfile |
| MCP stdio transport | Flag MANUAL — needs Gateway URL |
| Secret env vars | Flag for Identity vault |
| CLI not installed | Print install command, halt |

## Key Rules

- **Default build is CodeZip** — no Docker needed. Only use Container when system packages are required
- **Never put secrets in generated files** — credentials → Identity vault
- **Preserve original files** — migration is additive
- **One runtime per agent** — each `.agent.md` → its own AgentCore Runtime scaffold
- **Skills are baked OR mounted** — prefer harness-mounted skills (`.agent/skills/<name>.md`) for flexibility; fall back to baking into code package for CLI-only deploys
- **Generic agent + skills pattern** — a single generic agent can load multiple skills at runtime from the harness filesystem without redeploying
- **Test with simple prompts first** — verify deploy works before testing complex prompts
- **`npm install` in `agentcore/cdk/`** — required before first deploy or you get `tsc: not found`
- **aws-targets.json must be a JSON array** — `[{"name":"default","account":"...","region":"..."}]` not an object
- **Field is `"account"` not `"accountId"`** — in aws-targets.json
- **Idempotent** — rerunning overwrites cleanly (output dir is cleaned before generation)
- **No `add agent` commands in scripts** — runtimes are defined in `agentcore.json`; `agentcore add agent` would fail with "already exists"
- **Back up `agentcore.json`** — `agentcore create` overwrites the generated config; always back up and restore after project init
- **Skills are scoped** — only skills declared in an agent's `skills:` frontmatter are included; for harness-mounted mode, list skill paths in the harness config; agents without `skills:` get no skill files
- **Model: Nova Lite default** — `amazon.nova-lite-v1:0` works without access forms. Claude requires a separate use-case submission
- **Daily token quotas** — Nova models have low daily limits. Request increase via Service Quotas if testing is blocked by `ThrottlingException`
- **Non-streaming entrypoint** — use `return {"response": str(result)}` pattern. The streaming `yield` pattern has CLI display issues
- **Agent naming**: alphanumeric + underscores only, start with a letter, max 48 chars
- **Project naming**: alphanumeric only (no hyphens/dots/underscores), start with letter, max 23 chars
- **Console-created harnesses cannot be updated via CLI** — always create a new CDK-managed project instead

## Validation Checkpoints

Between each workflow step, validate before proceeding:

| After Step | Validation | Action on Failure |
|---|---|---|
| **1 — Discover** | `migration-inventory.json` exists and has `>0` artifacts | Re-check repo paths; verify at least one source format detected |
| **2 — Parse** | All parsed artifacts have required fields (name, type) | Log missing fields; skip malformed entries with warning |
| **3 — Map** | No `AUTO` mapping references undefined targets | Review `agentcore-mappings.md`; reclassify as MANUAL |
| **4 — Generate** | `runtime-metadata.json` and `agentcore/agentcore.json` are valid JSON; `aws-targets.json` is a JSON array with `"account"` field; `model/load.py` uses available model | Fix template output; regenerate with `--verbose` if needed |
| **5 — Report** | Report lists all MANUAL items; no secrets in generated files | Scan output for secret patterns; move to Identity vault |
| **6 — Initialize** | `agentcore validate` passes; `agentcore.json` has runtimes populated; `agentcore/cdk/node_modules` exists; CloudFormation stack created successfully | Restore backed-up `agentcore.json`, run `npm install` in `agentcore/cdk/`, check IAM permissions, verify no stack name collision |

If generated runtime metadata fails validation, diagnose by comparing against `references/templates/runtime-metadata.json.tmpl` and re-run `generate_project.py` after fixing the mapping chain.

## Bundled Resources

### Scripts

- `scripts/preflight_check.py` — Verify all prerequisites (Python, Node.js, AWS CLI, credentials, AgentCore CLI) before starting migration
- `scripts/scan_configs.py` — Scan repository for 15 AI assistant config formats, parse agents/skills/MCP/hooks/memory/prompts, output `migration-inventory.json`
- `scripts/generate_project.py` — Generate full AgentCore project scaffold from migration inventory

### References

- `references/source-formats.md` — Per-tool parsing rules for all 15 assistant formats
- `references/agentcore-mappings.md` — Complete mapping rules: source artifacts → AgentCore equivalents
- `references/migration-modes.md` — Deploy workflow details: CLI flags, output structure, deploy steps, validation, teardown, and known AWS limitations
- `references/templates/` — templates for `agentcore.json`, `runtime-metadata.json`, `Dockerfile`, `registry-record.json`

### Assets

- `assets/poc-cve-verify/` — Complete worked POC migrating `cve-verify.agent.md` to AgentCore (`main.py`, `runtime-metadata.json`, Dockerfile, agentcore.json, registry-record.json, migration-report.md)
