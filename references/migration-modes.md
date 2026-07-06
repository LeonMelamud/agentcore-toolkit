# Migration Modes Reference

The AgentCore migration creates a **new CDK-managed AgentCore project** using **CodeZip** build (serverless — no Docker needed). The `agentcore` CLI manages the full deployment lifecycle through CloudFormation.

## Build Types

| Build | When to use | Docker needed? |
|-------|-------------|----------------|
| **CodeZip** (default) | Pure Python agents with pip dependencies | No |
| **Container** | Agents needing system packages, non-Python tools, custom OS deps | Yes |

CodeZip is preferred — it's faster to deploy, doesn't require Docker locally or CodeBuild, and uses the managed Python 3.14 runtime.

## CLI Flags

```
python3 scripts/generate_project.py \
  --inventory <path>          # migration-inventory.json (required)
  --output-dir <path>         # Output directory (default: ./agentcore-project)
  --region <region>           # AWS region (default: us-west-2)
```

## What Gets Generated

```
agentcore-project/
├── agentcore/
│   ├── agentcore.json        # runtimes[] — CodeZip build, Python 3.14
│   ├── aws-targets.json      # JSON array: [{"name","account","region"}]
│   └── cdk/                  # CDK project (auto-generated on first deploy)
├── app/<agent>/              # One directory per agent
│   ├── main.py               # Strands Agent entrypoint (BedrockAgentCoreApp)
│   ├── model/load.py         # BedrockModel loader (Nova Lite default)
│   ├── pyproject.toml        # Dependencies (strands-agents, bedrock-agentcore)
│   ├── runtime-metadata.json # Review: systemPrompt, tools, env
│   ├── scripts/              # Migrated scripts
│   └── skills/               # Declared skills baked into package
├── agentcore-commands.sh     # Create project + credentials + gateways + deploy
└── migration-report.md       # Summary + manual action items
```

## Deploy Workflow

```bash
cd agentcore-project

# 1. Initialize: creates local project structure + CDK scaffold
agentcore create --defaults
# If agentcore.json was pre-generated, back it up first:
#   cp agentcore/agentcore.json agentcore/agentcore.json.bak
#   agentcore create --name <project> --no-agent
#   cp agentcore/agentcore.json.bak agentcore/agentcore.json

# 2. Install CDK dependencies (REQUIRED before first deploy)
cd agentcore/cdk && npm install && cd ../..

# 3. Validate
agentcore validate

# 4. Add credentials and gateways (or run agentcore-commands.sh)
agentcore add credential --type api-key --name <name> --api-key "$SECRET"
agentcore add gateway --name <gateway>
agentcore add gateway-target --name <target> --type mcp-server --endpoint <url> --gateway <gateway>

# 5. Deploy to AWS
agentcore deploy

# 6. Test
agentcore invoke --runtime <agent> --prompt "test"
```

> **Critical: `npm install` in `agentcore/cdk/`** — The CDK project requires `node_modules` before the first deploy. If you skip this, `agentcore deploy` fails with `tsc: not found`.

> **Critical: `agentcore create` overwrites `agentcore.json`** — Back up and restore if you have a pre-generated config.

## What `agentcore deploy` Creates

The deploy command creates a CloudFormation stack (named `AgentCore-<projectname>-default`) containing:

| Resource | Purpose |
|---|---|
| Agent Runtimes | The actual AgentCore Runtime resources (CodeZip or Container) |
| IAM Roles | Service roles for runtime execution |
| ECR Repository | (Container build only) Stores built container images |
| CodeBuild Project | (Container build only) Builds Docker images |

## aws-targets.json Format

**Must be a JSON array** (not an object). Field is `"account"` not `"accountId"`:

```json
[
  {
    "name": "default",
    "account": "123456789012",
    "region": "us-east-1"
  }
]
```

## Validation

| Check | Expected |
|---|---|
| `agentcore.json` runtimes[] | Must have ≥1 entry (one per agent) |
| `agentcore.json` build field | `"CodeZip"` (default) or `"Container"` |
| `aws-targets.json` | JSON **array** with `"account"` field (not "accountId") |
| `agentcore/cdk/node_modules` | Exists (run `npm install` in `agentcore/cdk/`) |
| `agentcore validate` | Passes with no errors |
| App directories | One per agent, each with `main.py`, `pyproject.toml` |
| `model/load.py` | Uses `amazon.nova-lite-v1:0` or another available model |

## Teardown

To remove all deployed resources:

```bash
aws cloudformation delete-stack --stack-name AgentCore-<projectname>-default --region <region>
aws cloudformation wait stack-delete-complete --stack-name AgentCore-<projectname>-default --region <region>
```

## Error Handling

| Error | Cause | Fix |
|---|---|---|
| `tsc: not found` during deploy | CDK deps not installed | Run `cd agentcore/cdk && npm install` |
| `agentcore validate` fails | Missing runtimes in `agentcore.json` | Restore the backed-up `agentcore.json` |
| Deploy fails: stack already exists | Previous deployment | Delete stack: `aws cloudformation delete-stack --stack-name <name>` |
| Deploy fails: IAM permission denied | Missing permissions | Need CloudFormation, ECR, IAM, Bedrock AgentCore permissions |
| `ThrottlingException: Too many tokens per day` | Daily Bedrock token quota exhausted | Wait for quota reset (midnight UTC) or request increase via Service Quotas |
| Claude `ModelNotAccessibleException` | Anthropic models require use-case form | Switch to Nova Lite (`amazon.nova-lite-v1:0`) or submit form in Bedrock Console |
| `agentcore create` outputs nothing | Project name invalid | Use alphanumeric only, start with letter, max 23 chars |
| Console harness locked | Harness-managed runtime | Cannot update — create a new CDK-managed project instead |
| Docker Hub rate limits (Container build) | CodeBuild pulls throttled | Use ECR Public Gallery base images |

## Model Selection

| Model | Access | Quality | Daily Quota |
|-------|--------|---------|-------------|
| `amazon.nova-lite-v1:0` | Available immediately | Good for testing | Low default — request increase |
| `amazon.nova-pro-v1:0` | Available immediately | Better quality | Low default — request increase |
| `us.anthropic.claude-sonnet-4-6-20250514-v1:0` | Requires use-case form | Best quality | Higher once approved |

> **Recommendation:** Start with Nova Lite for deployment validation, then upgrade to Claude once access is approved.

## Known AWS Limitation: Console-Created Harnesses

Runtimes created via the **AWS Console** (Bedrock → AgentCore → Harness) are **harness-managed** and **cannot be updated** through any public CLI or API:

| Approach Tested | Result |
|---|---|
| `agentcore import runtime` | CloudFormation IMPORT fails — CDK cannot import harness-managed resources |
| `aws bedrock-agentcore-control update-agent-runtime` | API returns: *"This agent runtime is managed by harness '...' and cannot be updated directly. Use UpdateHarness to update this resource."* |
| `aws bedrock-agentcore-control update-harness` | API does not exist in the public CLI |

**Impact:** If you have a Console-created harness, this migration creates a **separate, new CDK-managed project**. The Console-created harness remains untouched.

**Recommendation:** Use this migration skill to create all runtimes via CLI (`agentcore create` + `agentcore deploy`). CLI-created runtimes are fully manageable and updatable.
