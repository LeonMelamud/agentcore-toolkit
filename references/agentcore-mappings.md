# AgentCore Mapping Rules

Translate AI assistant artifacts into Amazon Bedrock AgentCore managed harnesses using the Strands Agent Framework.

## Core Concepts

A **harness** is an AgentCore project containing one or more agent runtimes. Each runtime is a Strands-based Python app that reasons, uses tools, and completes multi-step tasks autonomously.

| Source artifact | AgentCore target | Location |
|---|---|---|
| `.agent.md` (persona + body) | Runtime agent (`app/<name>/main.py`) | Harness → `runtimes[]` |
| MCP server config | Gateway target | Harness → `agentCoreGateways[]` |
| Secret env vars | Identity credential | Harness → `credentials[]` |
| Memory/learnings | Memory resource | Harness → `memories[]` |
| Skills | Container filesystem | `app/<agent>/skills/` |

## Harness creation

Create a new CDK-managed project:

```bash
agentcore create --project-name <name> --no-agent --skip-install --skip-git
```

Then add agents via `agentcore.json` (declarative) — do NOT use `agentcore add agent` after the config is written, as it will fail with "already exists".

> **Important — `agentcore create` overwrites `agentcore.json`:** Back up the migration-generated config before running `agentcore create`, then restore it after.

> **Console-created harnesses cannot be imported:** Runtimes created via the AWS Console are harness-managed and locked. Neither `agentcore import runtime` nor the `update-agent-runtime` API can modify them. Always create a new CDK-managed project instead.

## Runtime entrypoint pattern (Strands)

Every migrated agent uses this pattern:

```python
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from model.load import load_model

app = BedrockAgentCoreApp()

DEFAULT_SYSTEM_PROMPT = "..."  # Flattened from persona + body

_agent = None

def get_or_create_agent():
    global _agent
    if _agent is None:
        _agent = Agent(model=load_model(), system_prompt=DEFAULT_SYSTEM_PROMPT, tools=tools)
    return _agent

@app.entrypoint
async def invoke(payload, context):
    agent = get_or_create_agent()
    stream = agent.stream_async(payload.get("prompt"))
    async for event in stream:
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]

if __name__ == "__main__":
    app.run()
```

Dependencies (`pyproject.toml`): `strands-agents >= 1.13.0`, `bedrock-agentcore >= 1.0.3`, `botocore[crt] >= 1.35.0`

## Command validation baseline

Use current AgentCore CLI verbs when generating copy-paste commands:

| Purpose | Current command pattern |
|---|---|
| Create project | `agentcore create --project-name <name> --no-agent --skip-install --skip-git` |
| Add runtime agent (interactive) | `agentcore add agent --name <agent> --type byo --code-location app/<agent> --entrypoint main.py --build Container --language Python --framework Strands --model-provider Bedrock` |
| Add API-key credential | `agentcore add credential --type api-key --name <name> --api-key "$VALUE"` |
| Add OAuth credential | `agentcore add credential --name <name> --type oauth --discovery-url <url> --client-id <id> --client-secret <secret>` |
| Add Gateway | `agentcore add gateway --name <gateway>` |
| Add MCP Gateway target | `agentcore add gateway-target --name <target> --type mcp-server --endpoint <mcp-url> --gateway <gateway>` |
| Validate config | `agentcore validate` |
| Deploy | `agentcore deploy` |
| Run locally | `agentcore dev` |
| Invoke runtime | `agentcore invoke --runtime <agent> --prompt "test"` |

**Important:** If `agentcore.json` already declares agents in `runtimes[]`, do NOT run `agentcore add agent` — it will fail with "already exists". Use `add agent` only for interactive bootstrapping, or edit `agentcore.json` directly.

**Naming constraints** (enforced by AgentCore CLI):
- Agent/runtime names: alphanumeric + underscores, start with a letter, max 48 chars. Convert dots/hyphens to underscores.
- Gateway names: alphanumeric + hyphens only, max 100 chars. No underscores.
- Project names: alphanumeric only (no hyphens, dots, or underscores), start with a letter, max 23 chars.
- `envVars` in `agentcore.json`: must be an array of `{"name": "KEY", "value": "val"}` objects, not a dict.

For raw AWS CLI fallback, the validated service namespaces are:

| Purpose | AWS CLI operation |
|---|---|
| Create runtime (standalone) | `aws bedrock-agentcore-control create-agent-runtime` |
| Update runtime (standalone only) | `aws bedrock-agentcore-control update-agent-runtime` |
| Get runtime details | `aws bedrock-agentcore-control get-agent-runtime` |
| List runtimes | `aws bedrock-agentcore-control list-agent-runtimes` |
| Delete runtime | `aws bedrock-agentcore-control delete-agent-runtime` |
| Invoke runtime | `aws bedrock-agentcore invoke-agent-runtime` |
| Create memory | `aws bedrock-agentcore-control create-memory` |
| Create gateway | `aws bedrock-agentcore-control create-gateway` |
| Create OAuth credential provider | `aws bedrock-agentcore-control create-oauth2-credential-provider` |

> **Note:** `update-agent-runtime` only works for standalone (CLI/API-created) runtimes. Console-created harness-managed runtimes return an error.

## Agent mapping

### Persona and instructions → runtime entrypoint

Flatten `.agent.md` persona and body into a coherent `SYSTEM_PROMPT` constant in `app/<agent>/main.py` and mirror it in `runtime-metadata.json` for review.

```text
Input (.agent.md)
  ## Persona
  - role: CVE verification tool
  - identity: A lean, automation-friendly verifier
  - communication_style: Box-diagram output, minimal prose
  - principles:
    - Activation is the only interactive moment
    - Always use the unified script
    - Never store credentials in files

Output
  app/cve-verify/main.py
    SYSTEM_PROMPT = "You are a CVE verification tool..."
  app/cve-verify/runtime-metadata.json
    { "systemPrompt": "You are a CVE verification tool..." }
```

The generated `main.py` is a scaffold. Teams must connect it to their preferred model/runtime adapter before production deployment.

### Tools → runtime requirements

| Source tool | Runtime requirement |
|---|---|
| `read` / `search` / `file` | Container filesystem access; record `file_operations` in metadata |
| `execute` / `shell` / `bash` | Container shell access; record `shell` in metadata |
| `browser` / `web` | Add/use AgentCore Browser capability if available in the target project |
| `code_interpreter` | Add/use AgentCore Code Interpreter capability if available in the target project |
| MCP tool reference | Convert MCP server to Gateway target, then wire the runtime adapter to that Gateway |
| `*` / all | Mark `MANUAL`; broad tool grants require human review |

### Handoffs → multi-agent project

Each handoff target becomes a separate runtime in the same project:

```bash
agentcore add agent --name <handoff_target> --type byo --code-location app/<handoff_target> --entrypoint main.py --build Container --language Python --framework Strands --model-provider Bedrock
```

Include handoff instructions in the primary agent's `SYSTEM_PROMPT` and list the relationship in `migration-report.md`.

## Skill mapping

Copy each agent's **declared skills** (from `skills:` frontmatter) into the generated runtime container. Do not copy all skills into every agent — only the skills the agent explicitly declares.

If an agent has no `skills:` frontmatter, no skill directories are created; note this in the migration report as a review item.

```text
app/<agent>/skills/<skill-name>/
├── SKILL.md
├── scripts/
├── references/
└── assets/
```

```dockerfile
COPY skills/ /app/skills/
```

The runtime adapter decides how to load those files at execution time. Do not use `--skill-path`; current generated projects bake skills into the container filesystem.

## MCP server mapping

### Remote MCP → AgentCore Gateway target

```bash
agentcore add gateway --name <server>-gateway
agentcore add gateway-target --name <server> --type mcp-server --endpoint <mcp-url> --gateway <server>-gateway
```

### Stdio MCP → manual conversion

Stdio MCP configs (`command` + `args`) cannot be attached directly. Mark them `MANUAL` and require one of these actions:

1. Deploy the MCP server as a remote HTTP/SSE/streamable endpoint.
2. Package it behind an AgentCore Gateway-compatible target.
3. Replace it with an equivalent native runtime tool.

Preserve the original command/args in `runtime-metadata.json` for review.

### MCP auth → Identity

Classify env vars with `KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `PASSCODE`, `CREDENTIAL`, `AUTH`, or `USERCODE` as secrets.

```bash
agentcore add credential --type api-key --name <credential-name> --api-key "$SECRET_VALUE"
```

Non-secret env vars go to runtime `envVars` in `agentcore/agentcore.json` and `runtime-metadata.json`.

## Hook mapping

| Source hook | AgentCore equivalent | Implementation |
|---|---|---|
| `sessionStart` | Pre-invocation exec | Generate `exec-scripts/pre-invoke.sh`; call with `agentcore invoke --runtime <name> --session-id <sid> --exec "exec-scripts/pre-invoke.sh"` |
| `sessionEnd` | Post-invocation exec | Generate `exec-scripts/post-invoke.sh`; call after the main invocation |
| `errorOccurred` | Observability | CloudWatch/OTEL traces and logs; add manual note if custom alerting is needed |
| `PostToolUseFailure` | Observability | Tool failures should appear in traces; add manual note for custom retry hooks |
| HITL gate | Runtime approval adapter | Preserve prompt text and mark `MANUAL` unless the generated app implements approval callbacks |

## Memory mapping

| Source memory | AgentCore target | Config |
|---|---|---|
| Conversation history | Short-term memory | `agentcore add agent --memory shortTerm` or generated memory resource |
| Agent learnings (`.github/memory/agents/`) | Long + short term memory | `agentcore add agent --memory longAndShortTerm` |
| Feature state (tasks, progress) | Runtime filesystem/session storage | Copy or mount under the runtime workspace; mark retention needs in report |
| Constitution / governance | System prompt | Bake into `SYSTEM_PROMPT` when relevant |

For explicit memory resources, prefer strategy-based commands such as:

```bash
agentcore add memory --name <memory-name> --strategies SEMANTIC,SUMMARIZATION,USER_PREFERENCE,EPISODIC --expiry 30
```

## Project file mapping

Generate current flat project config instead of legacy harness config.

```json
{
  "$schema": "https://schema.agentcore.aws.dev/v1/agentcore.json",
  "version": 1,
  "name": "migratedagents",
  "managedBy": "CDK",
  "tags": {
    "agentcore:created-by": "agentcore-migration-skill"
  },
  "runtimes": [
    {
      "name": "cve_verify",
      "build": "Container",
      "codeLocation": "app/cve_verify/",
      "entrypoint": "main.py",
      "runtimeVersion": "PYTHON_3_14",
      "networkMode": "PUBLIC",
      "protocol": "HTTP",
      "envVars": [
        { "name": "NEXUS_IQ_URL", "value": "https://iq.example.com" }
      ]
    }
  ],
  "memories": [],
  "credentials": [
    { "authorizerType": "ApiKeyCredentialProvider", "name": "nexus_iq_passcode" }
  ],
  "evaluators": [],
  "onlineEvalConfigs": [],
  "agentCoreGateways": [],
  "policyEngines": [],
  "configBundles": [],
  "abTests": [],
  "httpGateways": []
}
```

Runtimes are defined here — do NOT generate separate `agentcore add agent` commands (they would fail with "already exists"). Use `agentcore-commands.sh` only for credentials, gateways, deploy, and invoke.

Generate deployment targets as an array:

```json
[
  {
    "name": "default",
    "description": "Default deployment target (us-west-2)",
    "account": "<AWS_ACCOUNT_ID>",
    "region": "us-west-2"
  }
]
```

## Registry record mapping

Each migrated agent produces a Registry record manifest:

```json
{
  "name": "<agent-name>",
  "type": "AGENT",
  "description": "<from agent description>",
  "metadata": {
    "source_file": "<original path>",
    "migrated_from": "<source tool>",
    "migration_date": "<ISO timestamp>"
  }
}
```
