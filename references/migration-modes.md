# Migration Modes Reference

The migration creates a **new CDK-managed AgentCore project**. Two target modes per agent (chosen in mapping — see `migration.md` Step 3):

| Mode | What gets generated | Deploys as |
|------|---------------------|-----------|
| **Harness** (default) | `app/<name>/harness.json` + `system-prompt.md` | Managed harness — no code, no build |
| **Code runtime** | `app/<name>/main.py` + `model/` + `pyproject.toml` | CodeZip (default) or Container |

## Build Types (code runtimes only)

| Build | When to use | Docker needed? |
|-------|-------------|----------------|
| **CodeZip** (default) | Pure Python agents with pip dependencies | No |
| **Container** | System packages, non-Python tools, custom OS deps | Yes |

## Generator CLI Flags

```
python3 scripts/generate_project.py \
  --inventory <path>          # migration-inventory.json (required)
  --output-dir <path>         # Output directory (default: ./agentcore-project)
  --region <region>           # AWS region (default: us-west-2)
```

## Deploy Workflow

```bash
cd agentcore-project

# 1. Initialize project scaffold (CDK). create OVERWRITES agentcore.json — back up first.
cp agentcore/agentcore.json agentcore/agentcore.json.bak
agentcore create --project-name <project> --no-agent --skip-git
cp agentcore/agentcore.json.bak agentcore/agentcore.json

# 2. Install CDK dependencies (REQUIRED before first deploy)
cd agentcore/cdk && npm install && cd ../..

# 3. Validate
agentcore validate

# 4. Credentials, skills, gateways (or run agentcore-commands.sh)
agentcore add credential --type api-key --name <name> --api-key "$SECRET"
agentcore add skill --harness <n> --path <skill-dir>
agentcore add gateway --name <gateway>
agentcore add gateway-target --name <target> --type mcp-server --endpoint <url> --gateway <gateway>

# 5. Deploy
agentcore deploy

# 6. Test
agentcore invoke --agent <name> "test"
```

> **Critical: `npm install` in `agentcore/cdk/`** — skip it and `agentcore deploy` fails with `tsc: not found`.

## What `agentcore deploy` Creates

CloudFormation stack `AgentCore-<projectname>-default`:

| Resource | Purpose |
|---|---|
| Harnesses | Managed harness resources |
| Agent Runtimes | CodeZip or Container runtimes |
| IAM Roles | Service roles for execution |
| ECR Repository + CodeBuild | Container builds only |

## aws-targets.json Format

**JSON array**, `account` (not `accountId`) is the 12-digit account ID string:

```json
[
  { "name": "default", "account": "123456789012", "region": "us-east-1" }
]
```

## Validation

| Check | Expected |
|---|---|
| `agentcore.json` | ≥1 entry across `harnesses[]` + `runtimes[]`; conforms to `.llm-context/` types |
| `harness.json` per harness | name, model, tools[], skills[], memory block |
| `aws-targets.json` | JSON **array** with `account` field |
| `agentcore/cdk/node_modules` | Exists |
| `agentcore validate` | Passes |
| Code-agent dirs | `main.py` + `pyproject.toml` each |

## Teardown

```bash
aws cloudformation delete-stack --stack-name AgentCore-<projectname>-default --region <region>
aws cloudformation wait stack-delete-complete --stack-name AgentCore-<projectname>-default --region <region>
```

## Error Handling

| Error | Cause | Fix |
|---|---|---|
| `tsc: not found` during deploy | CDK deps not installed | `cd agentcore/cdk && npm install` |
| `agentcore validate` fails | Config drift | Restore backed-up `agentcore.json`; check `.llm-context/` types |
| "already exists" from `add` | Resource already declared in config | Edit JSON directly |
| Stack already exists | Previous deployment | `aws cloudformation delete-stack ...` |
| IAM permission denied | Missing permissions | Need CloudFormation, ECR, IAM, Bedrock AgentCore permissions |
| `ThrottlingException: Too many tokens` | Bedrock token quota | Request increase via Service Quotas |
| `ModelNotAccessibleException` | Model access not enabled in account | Enable in Bedrock Console → Model access, or switch to `amazon.nova-lite-v1:0` |
| `agentcore create` outputs nothing | Invalid project name | Alphanumeric only, start with letter, max 23 chars |
| Docker Hub rate limits (Container) | CodeBuild pulls throttled | Use ECR Public Gallery base images |

## Model Selection

| Model | Notes |
|-------|-------|
| `global.anthropic.claude-sonnet-4-6` | Harness default (CLI 0.22.0) |
| `global.anthropic.claude-sonnet-4-5-20250929-v1:0` | Code-agent template default |
| `amazon.nova-lite-v1:0` / `amazon.nova-pro-v1:0` | Fallback if Anthropic model access is not enabled; low default daily quotas |

More providers: harness `--model-provider open_ai | gemini | lite_llm` (LiteLLM/Bedrock Mantle expose OpenAI GPT models on Bedrock).
