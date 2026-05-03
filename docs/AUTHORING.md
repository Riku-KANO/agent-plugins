# Authoring a plugin

Steps for adding a new plugin to the `personal-agents` marketplace.

## 1. Create the plugin directory

```text
plugins/<plugin-name>/
└── .claude-plugin/plugin.json   # required
```

`plugin.json`:

```json
{
  "name": "<plugin-name>",
  "version": "0.1.0",
  "description": "One-line description shown in the marketplace listing.",
  "author": { "name": "Riku-KANO" }
}
```

`name` MUST match the marketplace entry name.

## 2. Add the extension files you need

A plugin can contain any combination of the following — none are required individually.

### Slash commands — `commands/<name>.md`

User-invoked. Triggered by `/<name>` with optional arguments.

```markdown
---
description: Short description shown in /help.
argument-hint: <required-arg> [optional-arg]
allowed-tools: [Read, Glob, Grep, Bash]
---

Instructions for Claude. Reference user input via $ARGUMENTS.
```

Frontmatter fields: `description`, `argument-hint`, `allowed-tools`, optional `model`.

### Skills — `skills/<name>/SKILL.md`

Model-invoked. Claude activates the skill when the request matches the description.

```markdown
---
name: <name>
description: Use when the user asks to "<phrase 1>", "<phrase 2>", or otherwise wants <topic>.
version: 0.1.0
---

# <name>

Instructions, references, examples.
```

The `description` is the trigger spec — list concrete user phrases or keywords. Vague descriptions = the skill never fires.

Skills can carry supporting files alongside `SKILL.md`:

```text
skills/<name>/
├── SKILL.md
├── references/<topic>.md
├── scripts/<helper>.mjs
└── assets/<file>
```

### Subagents — `agents/<name>.md`

```markdown
---
name: <name>
description: When to delegate to this subagent.
model: sonnet
tools: Bash, Read, Grep
---

System prompt for the subagent.
```

### Hooks — `hooks/hooks.json`

```json
{
  "description": "Optional description.",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "node \"${CLAUDE_PLUGIN_ROOT}/scripts/start.mjs\"", "timeout": 5 }
        ]
      }
    ]
  }
}
```

`${CLAUDE_PLUGIN_ROOT}` resolves to the plugin's installed directory at runtime.

### MCP servers — `.mcp.json`

```json
{
  "<server-name>": {
    "type": "http",
    "url": "https://mcp.example.com/api"
  }
}
```

## 3. Register the plugin in the marketplace

Edit `.claude-plugin/marketplace.json` and append to `plugins[]`:

```json
{
  "name": "<plugin-name>",
  "description": "One-line description.",
  "source": "./plugins/<plugin-name>",
  "category": "<category>"
}
```

Categories that are common: `development`, `productivity`, `database`, `security`, `design`, `example`. Pick whatever fits.

## 4. Validate

```bash
node scripts/validate.mjs
```

Catches:

- Plugin listed in `marketplace.json` but directory missing.
- Plugin directory exists but not registered.
- `plugin.json` `name` mismatched with marketplace entry.
- `SKILL.md` / `agents/*.md` / `commands/*.md` missing required frontmatter keys.

## 5. Ship

```bash
git add .
git commit -m "add <plugin-name> plugin"
git push
```

Consumers refresh with `/plugin marketplace update personal-agents`, then `/plugin install <plugin-name>@personal-agents` if it's a new plugin.

## Reference plugin

`plugins/hello-world/` is the simplest working example — copy and edit it when starting a new plugin.

## External references

The two installed marketplaces are great for reading patterns:

- `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/example-plugin/` — minimal plugin demonstrating commands, skills, MCP.
- `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/skill-creator/` — large skill with `references/`, `scripts/`, `agents/` subdirectories.
- `~/.claude/plugins/marketplaces/openai-codex/plugins/codex/` — full-featured plugin with hooks, subagents, schemas, helper scripts.
