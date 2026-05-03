# hello-world

Reference plugin in the `personal-agents` marketplace. Use it as a template when adding new plugins.

## Contents

- `commands/hello.md` — `/hello <name>` slash command (legacy `commands/` layout).
- `skills/hello-skill/SKILL.md` — model-invoked skill that fires on phrases like "test the personal-agents marketplace".

## Install

```text
/plugin marketplace add Riku-KANO/agent-plugins
/plugin install hello-world@personal-agents
```

## Try it

- Run `/hello Riku` — should produce a one-line greeting.
- Say "test the personal-agents marketplace" — `hello-skill` should reply with a confirmation line.

## Layout reference

```
plugins/hello-world/
├── .claude-plugin/plugin.json   # required metadata
├── commands/hello.md            # user-invoked slash command
├── skills/hello-skill/SKILL.md  # model-invoked skill
└── README.md
```

For frontmatter details and other extension points (agents, hooks, MCP), see the root `docs/AUTHORING.md`.
