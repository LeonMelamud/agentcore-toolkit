# Harness Reference

A harness is a fully managed AgentCore agent defined by configuration — model + tools + skills + memory + execution limits. No agent code, no container build. GA since June 2026 (`CreateHarness`/`UpdateHarness`/`InvokeHarness`). All commands below verified against CLI 0.22.0.

## Files

In a CLI project, each harness is:

```
agentcore/agentcore.json    →  "harnesses": [{ "name": "<n>", "path": "app/<n>" }]
app/<n>/harness.json        →  full harness spec
app/<n>/system-prompt.md    →  system prompt text
```

`harness.json` (ground truth, CLI 0.22.0):

```json
{
  "name": "myharness",
  "model": {
    "provider": "bedrock",
    "modelId": "global.anthropic.claude-sonnet-4-6"
  },
  "tools": [
    {
      "type": "remote_mcp",
      "name": "my_mcp",
      "config": { "remoteMcp": { "url": "https://mcp.example.com/mcp" } }
    }
  ],
  "skills": [
    { "path": "/abs/or/relative/skill-dir" }
  ],
  "memory": { "mode": "disabled" }
}
```

## Create / add

```bash
# New project whose default resource is a harness
agentcore create --name <harness> --project-name <proj> --defaults

# Add a harness to an existing project
agentcore add harness --name <n> \
  --system-prompt "You are ..." \
  --model-provider bedrock --model-id global.anthropic.claude-sonnet-4-6 \
  --allowed-tools "*" \
  --env KEY=VALUE \
  --max-iterations 50 --max-tokens 200000 --timeout 900
```

Selected flags (full list: `agentcore add harness --help`):

| Flag | Purpose |
|---|---|
| `--model-provider` | `bedrock`, `open_ai`, `gemini`, `lite_llm` (lite_llm: `--api-base`, `--additional-params`) |
| `--api-key-arn` | Secrets Manager ARN for non-Bedrock providers |
| `--tools` | Comma-separated: `agentcore_browser`, `agentcore_code_interpreter`, `remote_mcp`, `agentcore_gateway` |
| `--mcp-name` / `--mcp-url` / `--mcp-headers` | Required when `--tools` includes `remote_mcp` |
| `--gateway-arn` + `--gateway-outbound-auth` | Required when `--tools` includes `agentcore_gateway` |
| `--allowed-tools` | Allow-list of tool names, or `"*"` |
| `--memory-mode` | `disabled` (default), `managed`, `existing` (`--memory-name`/`--memory-arn`) |
| `--memory-strategies` | `SEMANTIC,SUMMARIZATION,USER_PREFERENCE,EPISODIC` (managed mode) |
| `--session-storage <path>` | Persistent session filesystem mount |
| `--efs-access-point` / `--s3-access-point` | BYO filesystem mounts `<arn>:<mountPath>` (VPC mode, max 2 each) |
| `--env KEY=VALUE` | Environment variables (repeatable) |
| `--truncation-strategy` | `sliding_window`, `summarization`, `none` |
| `--authorizer-type` | `AWS_IAM` or `CUSTOM_JWT` (+ `--discovery-url`, `--allowed-clients`, …) |
| `--container <uri-or-Dockerfile>` | Custom container image for the harness |
| `--with-invoke-script` | Generate a standalone Python invoke script |

## Skills

Skills are standard skill directories (SKILL.md with YAML frontmatter + scripts/references). Four sources:

```bash
agentcore add skill --harness <n> --path <local-skill-dir>
agentcore add skill --harness <n> --s3 s3://bucket/path
agentcore add skill --harness <n> --git https://github.com/org/repo [--git-path sub/dir] [--credential <name>] [--username <u>]
agentcore add skill --harness <n> --aws-skills [paths]   # AWS-curated catalog; omit paths for all
```

Skills mounted on a harness load at invocation time — update a skill without redeploying the agent. Code agents get the same sources via `skills/fetcher.py` in the generated app (s3/git skills download to a temp cache at runtime; the runtime working dir is read-only).

## Tools

```bash
agentcore add tool --harness <n> --type remote_mcp --name <t> --url <mcp-url>
agentcore add tool --harness <n> --type agentcore_browser|agentcore_code_interpreter --name <t>
agentcore add tool --harness <n> --type agentcore_gateway --gateway <project-gateway-name> [--outbound-auth awsIam|none|oauth]
agentcore add tool --harness <n> --type inline_function --name <t> --description "<shown to model>" --input-schema @schema.json
```

## Export to code

When the config ceases to be enough (custom tool logic, middleware, custom loop):

```bash
agentcore export harness --name <n>                    # in-project harness
agentcore export harness --arn <arn>                   # harness created elsewhere (e.g., AWS Console)
  [--target-agent-name <name>] [--build CodeZip|Container]
```

Generates a Strands Python runtime agent under `app/<name>Agent/` mirroring the harness's model, tools, skills, memory, limits, and mounts. **Always read `app/<agent>/EXPORT_NOTES.md` before deploying** — it lists what the exporter could not automate. Then `agentcore deploy`; the exported agent deploys as a normal runtime. Exported code can also self-host anywhere with Python 3.12+ (Lambda, ECS, EKS, on-prem).

This is the supported path for Console-created harnesses — the pre-GA "harness-managed runtimes cannot be updated" dead end no longer applies.

## HITL / approvals

Human-in-the-loop no longer requires custom infrastructure:

- **Gateway elicitation pass-through** — an MCP tool behind a gateway can request user input mid-execution (form mode: structured confirm; URL mode: e.g. OAuth consent). Requires gateway MCP sessions.
- **Step Functions integration** — wrap `InvokeHarness` in a workflow with human-approval, error-handling, or conditional steps.

## Invoke

```bash
agentcore invoke --agent <name> "prompt"           # deployed agent/harness endpoint
agentcore dev "prompt"                             # local run (code agents)
aws bedrock-agentcore invoke-agent-runtime ...     # raw API for runtimes
```
