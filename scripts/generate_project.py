#!/usr/bin/env python3
"""Generate an AgentCore project scaffold from a migration inventory.

Usage:
    python3 generate_project.py \
        --inventory migration-inventory.json \
        --output-dir ./agentcore-project \
        --region us-west-2
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SECRET_PATTERNS = re.compile(
    r"(KEY|SECRET|TOKEN|PASSWORD|PASSCODE|CREDENTIAL|AUTH|USERCODE)", re.IGNORECASE
)

DEFAULT_MODEL_ID = "amazon.nova-lite-v1:0"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def slugify(value: str) -> str:
    """Return a CLI-safe resource name (alphanumeric + underscores, start with letter)."""
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    # Must start with a letter
    if slug and not slug[0].isalpha():
        slug = "a" + slug
    return slug[:48] or "unnamed"


def project_slugify(value: str) -> str:
    """Return a project-safe name (alphanumeric only, start with letter, max 23 chars)."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "", value.strip().lower())
    if slug and not slug[0].isalpha():
        slug = "p" + slug
    return slug[:23] or "project"


def env_vars_to_array(env_dict: dict[str, str]) -> list[dict[str, str]]:
    """Convert env vars dict to AgentCore array format [{name, value}]."""
    return [{"name": k, "value": v} for k, v in env_dict.items()]


def gateway_slugify(value: str) -> str:
    """Return a gateway-safe name (alphanumeric + hyphens, max 100 chars)."""
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if slug and not slug[0].isalpha():
        slug = "g" + slug
    return slug[:100] or "gateway"


def classify_env_var(name: str) -> str:
    """Classify an env var as secret or config."""
    return "secret" if SECRET_PATTERNS.search(name) else "config"


def flatten_persona_to_prompt(agent: dict[str, Any]) -> str:
    """Convert agent persona + body into a system prompt string."""
    parts: list[str] = []
    persona = agent.get("persona", {})

    if persona.get("role"):
        parts.append(f"You are {persona['role']}.")
    if persona.get("identity"):
        parts.append(f"Identity: {persona['identity']}.")
    if persona.get("communication_style"):
        parts.append(f"Communication style: {persona['communication_style']}.")
    if persona.get("principles"):
        principles_text = "; ".join(
            f"({i + 1}) {p}" for i, p in enumerate(persona["principles"])
        )
        parts.append(f"Principles: {principles_text}.")

    body = agent.get("body", "")
    body = re.sub(r"##\s*Persona\s*\n.*?(?=\n##\s|\Z)", "", body, flags=re.DOTALL)
    body = body.strip()
    if body:
        parts.append(f"\n## Instructions\n{body}")

    return "\n".join(parts).strip()


def map_allowed_tools(agent: dict[str, Any]) -> list[str]:
    """Map source assistant tool names to AgentCore runtime categories."""
    tool_map = {
        "read": "file_operations",
        "search": "file_operations",
        "file": "file_operations",
        "execute": "shell",
        "shell": "shell",
        "bash": "shell",
        "browser": "agentcore_browser",
        "web": "agentcore_browser",
        "code_interpreter": "agentcore_code_interpreter",
        "*": "*",
    }
    tools = agent.get("tools", []) or []
    if not tools:
        return ["file_operations", "shell"]
    mapped = {
        tool_map.get(t.lower() if isinstance(t, str) else str(t), str(t))
        for t in tools
    }
    return sorted(mapped)


def collect_runtime_env(mcp_servers: list[dict]) -> dict[str, str]:
    """Collect non-secret MCP env vars for runtime configuration."""
    env_vars: dict[str, str] = {}
    for mcp in mcp_servers:
        for var_name, var_info in mcp.get("env_vars", {}).items():
            if not var_info.get("is_secret"):
                env_vars[var_name] = var_info.get("value", "")
    return env_vars


def collect_secret_names(mcp_servers: list[dict]) -> list[str]:
    """Collect secret env var names that must become AgentCore Identity credentials."""
    names: list[str] = []
    for mcp in mcp_servers:
        for var_name, var_info in mcp.get("env_vars", {}).items():
            if var_info.get("is_secret") and var_name not in names:
                names.append(var_name)
    return names


def find_agent_script_refs(agent: dict[str, Any], repo_root: Path) -> list[Path]:
    """Find .github/scripts references inside an agent body."""
    body = agent.get("body", "")
    refs = re.findall(r"(?:^|\s)(?:\./)?\.github/scripts/([^\s`'\"]+\.(?:sh|py))", body)
    paths: list[Path] = []
    for ref in refs:
        path = (repo_root / ".github" / "scripts" / ref).resolve()
        if path.is_file() and path not in paths:
            paths.append(path)
    return paths


def copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree, replacing any existing destination."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def generate_runtime_metadata(agent: dict[str, Any], mcp_servers: list[dict]) -> dict[str, Any]:
    """Generate reviewable metadata consumed by the migrated entrypoint."""
    return {
        "modelId": DEFAULT_MODEL_ID,
        "systemPrompt": flatten_persona_to_prompt(agent),
        "allowedTools": map_allowed_tools(agent),
        "mcpServers": [
            {
                "name": mcp.get("name", "unnamed"),
                "transport": mcp.get("transport", "unknown"),
                "url": mcp.get("url", ""),
                "migrationStatus": "MANUAL" if mcp.get("transport") == "stdio" else "AUTO",
                "note": "stdio MCP must be exposed through Gateway or a remote MCP endpoint"
                if mcp.get("transport") == "stdio" else "remote endpoint can become a Gateway target",
            }
            for mcp in mcp_servers
            if not mcp.get("disabled")
        ],
        "envVars": env_vars_to_array(collect_runtime_env(mcp_servers)),
        "identityCredentials": [slugify(name) for name in collect_secret_names(mcp_servers)],
        "maxIterations": 75,
        "timeoutSeconds": 3600,
    }


def generate_main_py(agent: dict[str, Any]) -> str:
    """Generate a Strands-based AgentCore Runtime entrypoint with auto skill loading."""
    system_prompt = flatten_persona_to_prompt(agent)
    agent_name = agent.get("name", "agent")
    return f'''#!/usr/bin/env python3
"""AgentCore Runtime entrypoint for the migrated `{agent_name}` agent.

This scaffold preserves the original assistant instructions in DEFAULT_SYSTEM_PROMPT.
Skills are loaded automatically from the skills/ directory (baked into code package)
or from .agent/skills/ (mounted by harness at runtime).
"""

from pathlib import Path
from typing import Any

from strands import Agent
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from model.load import load_model

app = BedrockAgentCoreApp()
log = app.logger

DEFAULT_SYSTEM_PROMPT = {system_prompt!r}


def _discover_skills() -> str:
    """Auto-discover and load skill files from available paths.

    Checks two locations (in priority order):
    1. .agent/skills/ — Harness-mounted skills (added via Console UI or config)
    2. skills/ — Skills baked into the code package at build time
    """
    skill_dirs = [
        Path("/app/.agent/skills"),   # Harness-mounted path
        Path(__file__).parent / "skills",  # Baked into code package
    ]
    skills_content: list[str] = []
    seen: set[str] = set()

    for skill_dir in skill_dirs:
        if not skill_dir.is_dir():
            continue
        # Load SKILL.md from each skill subfolder, or direct .md files
        for path in sorted(skill_dir.rglob("SKILL.md")):
            name = path.parent.name
            if name not in seen:
                seen.add(name)
                skills_content.append(f"\\n--- SKILL: {{name}} ---\\n{{path.read_text()}}")
                log.info(f"Loaded skill: {{name}} from {{path}}")
        for path in sorted(skill_dir.glob("*.md")):
            name = path.stem
            if name not in seen:
                seen.add(name)
                skills_content.append(f"\\n--- SKILL: {{name}} ---\\n{{path.read_text()}}")
                log.info(f"Loaded skill: {{name}} from {{path}}")

    return "\\n".join(skills_content)


# Build final system prompt with skills injected
_skills_text = _discover_skills()
SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT + (_skills_text if _skills_text else "")

# Define tools used by the model
tools = []

# TODO: Add migrated tools here as @tool functions or MCP clients


_agent = None


def get_or_create_agent():
    global _agent
    if _agent is None:
        _agent = Agent(
            model=load_model(),
            system_prompt=SYSTEM_PROMPT,
            tools=tools,
        )
    return _agent


@app.entrypoint
async def invoke(payload, context):
    log.info("Invoking {agent_name}...")

    agent = get_or_create_agent()
    result = agent(payload.get("prompt"))
    return {{"response": str(result)}}


if __name__ == "__main__":
    app.run()
'''


def generate_model_load_py() -> str:
    """Generate model/load.py for Bedrock model loading.

    Uses Amazon Nova Lite by default — available without use-case form submission.
    Anthropic Claude models require a separate access request in the Bedrock Console.
    """
    return '''from strands.models.bedrock import BedrockModel


def load_model() -> BedrockModel:
    """Get Bedrock model client using IAM credentials.

    Default: amazon.nova-lite-v1:0 (available without access request).
    For better quality, switch to amazon.nova-pro-v1:0 or request Claude access.
    Note: Nova models have daily token quotas — request increase via Service Quotas
    if you hit ThrottlingException during testing.
    """
    return BedrockModel(model_id="amazon.nova-lite-v1:0")
'''


def generate_pyproject_toml(agent_name: str) -> str:
    """Generate pyproject.toml with AgentCore dependencies."""
    return f'''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{agent_name}"
version = "0.1.0"
description = "AgentCore Runtime Application — migrated from agentic-core"
requires-python = ">=3.10"
dependencies = [
    "aws-opentelemetry-distro",
    "bedrock-agentcore >= 1.0.3",
    "botocore[crt] >= 1.35.0",
    "strands-agents >= 1.13.0",
]

[tool.hatch.build.targets.wheel]
packages = ["."]
'''


def generate_dockerfile(has_scripts: bool, has_skills: bool) -> str:
    """Generate a container Dockerfile for BYO AgentCore runtime deployment."""
    lines = [
        "FROM public.ecr.aws/docker/library/python:3.12-slim",
        "",
        "RUN apt-get update && apt-get install -y --no-install-recommends \\",
        "    curl jq git \\",
        "    && rm -rf /var/lib/apt/lists/*",
        "",
        "WORKDIR /app",
        "COPY pyproject.toml /app/pyproject.toml",
        "RUN pip install --no-cache-dir .",
        "",
        "COPY main.py /app/main.py",
        "COPY model/ /app/model/",
        "COPY runtime-metadata.json /app/runtime-metadata.json",
    ]
    if has_scripts:
        lines.extend([
            "COPY scripts/ /app/scripts/",
            "RUN chmod +x /app/scripts/*.sh 2>/dev/null || true",
            'ENV PATH="/app/scripts:${PATH}"',
        ])
    if has_skills:
        lines.append("COPY skills/ /app/skills/")
    lines.extend([
        "",
        "CMD [\"python3\", \"/app/main.py\"]",
        "",
    ])
    return "\n".join(lines)


def generate_agentcore_json(inventory: dict, region: str) -> dict[str, Any]:
    """Generate the current flat AgentCore project config shape.

    Schema validated against: https://schema.agentcore.aws.dev/v1/agentcore.json
    - name: alphanumeric only, start with letter, max 23 chars
    - runtime names: alphanumeric + underscores, start with letter, max 48 chars
    - envVars: array of {name, value} objects
    - No unknown root keys (description, defaultTarget, region are invalid)
    """
    agents = inventory.get("agents", [])
    secret_names = collect_secret_names(inventory.get("mcp_servers", []))

    runtimes = [
        {
            "name": slugify(agent.get("name", f"agent_{i}")),
            "build": "CodeZip",
            "codeLocation": f"app/{slugify(agent.get('name', f'agent_{i}'))}/",
            "entrypoint": "main.py",
            "runtimeVersion": "PYTHON_3_14",
            "networkMode": "PUBLIC",
            "protocol": "HTTP",
        }
        for i, agent in enumerate(agents)
    ]
    return {
        "$schema": "https://schema.agentcore.aws.dev/v1/agentcore.json",
        "version": 1,
        "name": project_slugify("migratedagents"),
        "managedBy": "CDK",
        "tags": {
            "agentcore:created-by": "agentcore-migration-skill",
        },
        "runtimes": runtimes,
        "memories": [],
        "credentials": [
            {"name": slugify(name), "type": "api-key", "sourceEnvVar": name}
            for name in secret_names
        ],
        "evaluators": [],
        "onlineEvalConfigs": [],
        "agentCoreGateways": [
            {
                "name": f"{gateway_slugify(mcp.get('name', 'mcp'))}-gateway",
                "targets": [
                    {
                        "name": slugify(mcp.get("name", "mcp")),
                        "type": "mcp-server",
                        "endpoint": mcp.get("url") or "<REMOTE_MCP_URL>",
                        "migrationStatus": "MANUAL" if mcp.get("transport") == "stdio" else "AUTO",
                    }
                ],
            }
            for mcp in inventory.get("mcp_servers", [])
            if not mcp.get("disabled")
        ],
        "policyEngines": [],
        "configBundles": [],
        "abTests": [],
        "httpGateways": [],
    }


def detect_aws_account_id() -> str:
    """Auto-detect AWS account ID from configured credentials."""
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def generate_aws_targets(region: str, account_id: str = "") -> list[dict[str, str]]:
    """Generate aws-targets.json in the current target-list style.

    Auto-detects AWS account ID from configured credentials if not provided.
    """
    if not account_id:
        account_id = detect_aws_account_id()
    if not account_id:
        account_id = "<AWS_ACCOUNT_ID>"
        print("⚠️  Could not detect AWS account ID. Replace <AWS_ACCOUNT_ID> in aws-targets.json.", file=sys.stderr)
    return [
        {
            "name": "default",
            "description": f"Default deployment target ({region})",
            "account": account_id,
            "region": region,
        }
    ]


def generate_registry_record(agent: dict[str, Any]) -> dict[str, Any]:
    """Generate a Registry record manifest for an agent."""
    return {
        "name": agent.get("name", "unnamed"),
        "type": "AGENT",
        "description": agent.get("description", ""),
        "metadata": {
            "source_file": agent.get("source_file", ""),
            "migrated_from": "agentic-core",
            "migration_date": "__TIMESTAMP__",
        },
    }


def generate_exec_scripts(hooks: list[dict]) -> dict[str, str]:
    """Generate pre/post exec scripts from lifecycle hooks."""
    scripts: dict[str, str] = {}
    pre_cmds: list[str] = []
    post_cmds: list[str] = []

    for hook in hooks:
        event = hook.get("event", "")
        config = hook.get("config", {})
        if isinstance(config, dict):
            cmd = config.get("command", config.get("script", ""))
        elif isinstance(config, str):
            cmd = config
        else:
            cmd = ""

        if not cmd:
            continue
        if event.lower() == "sessionstart":
            pre_cmds.extend([f"# From: {hook.get('source_file', 'unknown')}", cmd])
        elif event.lower() == "sessionend":
            post_cmds.extend([f"# From: {hook.get('source_file', 'unknown')}", cmd])

    if pre_cmds:
        scripts["pre-invoke.sh"] = "#!/bin/bash\nset -euo pipefail\n\n" + "\n".join(pre_cmds) + "\n"
    if post_cmds:
        scripts["post-invoke.sh"] = "#!/bin/bash\nset -euo pipefail\n\n" + "\n".join(post_cmds) + "\n"
    return scripts


def build_mappings(inventory: dict) -> list[dict[str, str]]:
    """Build migration status records for the report."""
    mappings: list[dict[str, str]] = []
    for agent in inventory.get("agents", []):
        name = agent.get("name", "unnamed")
        mappings.append({"type": "agent", "name": name, "status": "AUTO", "target": f"app/{name}/main.py"})
    for skill in inventory.get("skills", []):
        mappings.append({
            "type": "skill",
            "name": skill.get("name", "unknown"),
            "status": "AUTO",
            "target": f"app/<agent>/skills/{skill.get('name', 'unknown')}/",
        })
    for mcp in inventory.get("mcp_servers", []):
        status = "MANUAL" if mcp.get("transport") == "stdio" else "AUTO"
        reason = "stdio transport must be published as remote MCP or Gateway target" if status == "MANUAL" else "remote MCP URL can become a Gateway target"
        mappings.append({"type": "mcp_server", "name": mcp.get("name", "unknown"), "status": status, "reason": reason})
        for var_name, var_info in mcp.get("env_vars", {}).items():
            if var_info.get("is_secret"):
                mappings.append({
                    "type": "secret",
                    "name": var_name,
                    "status": "MANUAL",
                    "reason": f"Add via: agentcore add credential --type api-key --name {slugify(var_name)} --api-key \"${var_name}\"",
                })
    return mappings


def generate_agentcore_commands(inventory: dict) -> str:
    """Generate a reviewed command script using current AgentCore CLI verbs.

    Generates create-project + credential + gateway + deploy commands.
    Agents are declared in agentcore.json — no add-agent commands needed.
    """
    project_name = project_slugify("migratedagents")

    lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        "",
        "# Review placeholders before running. Commands are generated from migration-inventory.json.",
        "",
        "# Agents are already defined in agentcore/agentcore.json — no add-agent commands needed.",
        "",
        "# ──── Initialize project ────",
        f"agentcore create --name {project_name} --no-agent",
    ]

    # Credentials — both modes need these
    secret_names = collect_secret_names(inventory.get("mcp_servers", []))
    if secret_names:
        lines.extend(["", "# ──── Credentials ────"])
        for secret_name in secret_names:
            lines.append(
                f"agentcore add credential --type api-key --name {slugify(secret_name)} --api-key \"${secret_name}\""
            )

    # Gateways — both modes need these
    mcp_gateways = [mcp for mcp in inventory.get("mcp_servers", []) if not mcp.get("disabled")]
    if mcp_gateways:
        lines.extend(["", "# ──── Gateways ────"])
        for mcp in mcp_gateways:
            gateway_name = f"{gateway_slugify(mcp.get('name', 'mcp'))}-gateway"
            target_name = slugify(mcp.get("name", "mcp"))
            endpoint = mcp.get("url") or "<REMOTE_MCP_URL>"
            lines.extend([
                "",
                f"agentcore add gateway --name {gateway_name}",
                f"agentcore add gateway-target --name {target_name} --type mcp-server --endpoint {endpoint} --gateway {gateway_name}",
            ])

    # Deploy and invoke
    agent_name = slugify(inventory.get("agents", [{}])[0].get("name", "agent")) if inventory.get("agents") else "<agent_name>"
    lines.extend([
        "",
        "# ──── Validate & Deploy ────",
        "agentcore validate",
        "agentcore deploy",
        f"agentcore invoke --runtime {agent_name} --prompt \"test\"",
        "",
    ])
    return "\n".join(lines)


def generate_migration_report(inventory: dict, mappings: list[dict]) -> str:
    """Generate migration-report.md."""
    lines = [
        "# AgentCore Migration Report",
        "",
        f"**Source repository:** {inventory.get('repo_root', 'unknown')}",
        f"**Sources detected:** {', '.join(inventory.get('sources_detected', []))}",
    ]

    lines.extend([
        "",
        "## Summary",
        "",
        "| Artifact | Count | Auto | Manual | Skip |",
        "|----------|-------|------|--------|------|",
    ])

    type_counts: dict[str, dict[str, int]] = {}
    for mapping in mappings:
        artifact_type = mapping.get("type", "unknown")
        status = mapping.get("status", "AUTO")
        type_counts.setdefault(artifact_type, {"total": 0, "AUTO": 0, "MANUAL": 0, "SKIP": 0})
        type_counts[artifact_type]["total"] += 1
        type_counts[artifact_type][status] = type_counts[artifact_type].get(status, 0) + 1

    for artifact_type, counts in type_counts.items():
        lines.append(
            f"| {artifact_type} | {counts['total']} | {counts.get('AUTO', 0)} "
            f"| {counts.get('MANUAL', 0)} | {counts.get('SKIP', 0)} |"
        )

    lines.extend(["", "## Manual Action Items", ""])
    manual_items = [mapping for mapping in mappings if mapping.get("status") == "MANUAL"]
    if manual_items:
        for item in manual_items:
            lines.append(f"- **{item.get('name', 'unknown')}** ({item.get('type')}): {item.get('reason', '')}")
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Deployment",
        "",
        "1. Review `agentcore/agentcore.json`, `agentcore/aws-targets.json`, and generated app files.",
        "2. Review and run `agentcore-commands.sh`, or apply the same commands manually.",
        "3. Test locally with `agentcore dev` before cloud deployment when Docker/runtime dependencies are present.",
        "",
        "```bash",
        "cd agentcore-project",
        "./agentcore-commands.sh",
        "```",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AgentCore project from inventory")
    parser.add_argument("--inventory", required=True, help="Path to migration-inventory.json")
    parser.add_argument("--output-dir", default="./agentcore-project", help="Output directory")
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    args = parser.parse_args()

    inv_path = Path(args.inventory)
    if not inv_path.is_file():
        print(f"Error: inventory file not found: {inv_path}", file=sys.stderr)
        sys.exit(1)

    inventory = json.loads(inv_path.read_text())
    repo_root = Path(inventory.get("repo_root", ".")).resolve()
    out_dir = Path(args.output_dir)
    # Clean output dir for idempotent re-runs
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    agentcore_dir = out_dir / "agentcore"
    agentcore_dir.mkdir(parents=True, exist_ok=True)
    (agentcore_dir / "agentcore.json").write_text(
        json.dumps(generate_agentcore_json(inventory, args.region), indent=2)
    )
    (agentcore_dir / "aws-targets.json").write_text(
        json.dumps(generate_aws_targets(args.region), indent=2)
    )

    skills = inventory.get("skills", [])
    mcp_servers = inventory.get("mcp_servers", [])
    for agent in inventory.get("agents", []):
        agent_name = slugify(agent.get("name", "unnamed"))
        agent_dir = out_dir / "app" / agent_name
        scripts_dir = agent_dir / "scripts"
        skills_dir = agent_dir / "skills"
        model_dir = agent_dir / "model"
        agent_dir.mkdir(parents=True, exist_ok=True)

        script_refs = find_agent_script_refs(agent, repo_root)
        if script_refs:
            scripts_dir.mkdir(exist_ok=True)
            for script in script_refs:
                shutil.copy2(script, scripts_dir / script.name)

        # Only copy skills the agent explicitly declares in frontmatter
        agent_skills = agent.get("frontmatter", {}).get("skills", [])
        if agent_skills:
            matching_skills = [s for s in skills if s.get("name") in agent_skills]
        else:
            matching_skills = []  # No skills declared → copy none; note in report
        if matching_skills:
            skills_dir.mkdir(exist_ok=True)
            for skill in matching_skills:
                source_file = Path(skill.get("source_file", ""))
                skill_source_dir = source_file.parent if source_file.is_file() else None
                if skill_source_dir and skill_source_dir.is_dir():
                    copy_tree(skill_source_dir, skills_dir / skill.get("name", skill_source_dir.name))

        (agent_dir / "main.py").write_text(generate_main_py(agent))
        (agent_dir / "pyproject.toml").write_text(generate_pyproject_toml(agent_name))

        # Generate model/ module for Bedrock model loading
        model_dir.mkdir(exist_ok=True)
        (model_dir / "__init__.py").write_text("")
        (model_dir / "load.py").write_text(generate_model_load_py())

        (agent_dir / "runtime-metadata.json").write_text(
            json.dumps(generate_runtime_metadata(agent, mcp_servers), indent=2)
        )
        (agent_dir / "Dockerfile").write_text(
            generate_dockerfile(has_scripts=bool(script_refs), has_skills=bool(matching_skills))
        )

        registry_dir = out_dir / "registry"
        registry_dir.mkdir(exist_ok=True)
        (registry_dir / f"{agent_name}.json").write_text(
            json.dumps(generate_registry_record(agent), indent=2)
        )

    exec_scripts = generate_exec_scripts(inventory.get("hooks", []))
    if exec_scripts:
        exec_dir = out_dir / "exec-scripts"
        exec_dir.mkdir(exist_ok=True)
        for name, content in exec_scripts.items():
            path = exec_dir / name
            path.write_text(content)
            path.chmod(0o755)

    command_script = out_dir / "agentcore-commands.sh"
    command_script.write_text(generate_agentcore_commands(inventory))
    command_script.chmod(0o755)

    mappings = build_mappings(inventory)
    (out_dir / "migration-report.md").write_text(generate_migration_report(inventory, mappings))

    auto = sum(1 for mapping in mappings if mapping["status"] == "AUTO")
    manual = sum(1 for mapping in mappings if mapping["status"] == "MANUAL")
    skip = sum(1 for mapping in mappings if mapping["status"] == "SKIP")
    print(f"\n✅ AgentCore project generated at: {out_dir}")
    print(f"   Agents: {len(inventory.get('agents', []))}")
    print(f"   Mappings: {auto} auto, {manual} manual, {skip} skipped")
    print(f"   Commands: {command_script}")
    print(f"   Report: {out_dir / 'migration-report.md'}")


if __name__ == "__main__":
    main()
