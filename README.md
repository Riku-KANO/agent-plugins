# personal-agents

Personal Claude Code marketplace. Each subdirectory under `plugins/` is an installable plugin (skills, slash commands, subagents, hooks, MCP servers).

## Install in another project

```text
/plugin marketplace add Riku-KANO/agent-plugins
/plugin install <plugin-name>@personal-agents
```

After updating this repository, refresh consumers with:

```text
/plugin marketplace update personal-agents
```

## Plugins

| Name | Description |
| --- | --- |
| [`hello-world`](plugins/hello-world) | Reference plugin - `/hello` slash command and a sample skill. Use as a template. |
| [`xquik-social-automation`](plugins/xquik-social-automation) | Xquik workflow guidance for X data, extraction, monitors, webhooks, MCP, and confirmation-gated publishing. |

## Add a new plugin

See [`docs/AUTHORING.md`](docs/AUTHORING.md). Short version:

1. Copy `plugins/hello-world` to `plugins/<your-plugin>` and edit metadata.
2. Append an entry to `.claude-plugin/marketplace.json`.
3. Run `node scripts/validate.mjs`.
4. Commit and push. Consumers run `/plugin marketplace update personal-agents` to pick it up.

## Layout

```
agent-plugins/
├── .claude-plugin/marketplace.json   # marketplace manifest (the index of plugins)
├── plugins/
│   └── <plugin-name>/
│       ├── .claude-plugin/plugin.json
│       ├── commands/                 # /slash-commands (legacy layout)
│       ├── skills/<skill>/SKILL.md   # model-invoked skills
│       ├── agents/                   # subagents
│       ├── hooks/hooks.json          # session hooks
│       └── .mcp.json                 # MCP servers
├── scripts/validate.mjs              # local manifest checker
└── docs/AUTHORING.md
```

Inside any plugin, scripts and hooks can refer to the plugin root via `${CLAUDE_PLUGIN_ROOT}`.
