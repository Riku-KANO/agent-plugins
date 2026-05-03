#!/usr/bin/env node
// Lightweight validator for the personal-agents marketplace.
// Run: node scripts/validate.mjs
// Exits non-zero on any error.

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const errors = [];

function err(msg) {
  errors.push(msg);
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (e) {
    err(`${path}: invalid JSON — ${e.message}`);
    return null;
  }
}

function listDirs(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).filter((n) => statSync(join(dir, n)).isDirectory());
}

// Minimal frontmatter check: extract block between leading --- lines and look for keys.
function checkFrontmatter(path, requiredKeys) {
  const text = readFileSync(path, "utf8");
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) {
    err(`${path}: missing YAML frontmatter delimited by ---`);
    return;
  }
  const block = m[1];
  for (const key of requiredKeys) {
    const re = new RegExp(`^${key}\\s*:\\s*(\\S|\\|)`, "m");
    if (!re.test(block)) {
      err(`${path}: frontmatter missing required key "${key}"`);
    }
  }
}

// 1. Marketplace manifest
const marketplacePath = join(ROOT, ".claude-plugin", "marketplace.json");
const marketplace = readJson(marketplacePath);
if (!marketplace) process.exit(1);

if (!marketplace.name) err(`${marketplacePath}: missing "name"`);
if (!Array.isArray(marketplace.plugins)) err(`${marketplacePath}: "plugins" must be an array`);

const declaredNames = new Set();

for (const entry of marketplace.plugins ?? []) {
  if (!entry.name) {
    err(`marketplace.json: plugin entry missing "name"`);
    continue;
  }
  if (declaredNames.has(entry.name)) {
    err(`marketplace.json: duplicate plugin name "${entry.name}"`);
  }
  declaredNames.add(entry.name);

  if (typeof entry.source !== "string" || !entry.source.startsWith("./plugins/")) {
    // External sources (github, url, git-subdir) are out of scope for this local check.
    continue;
  }

  const pluginDir = resolve(ROOT, entry.source);
  if (!existsSync(pluginDir)) {
    err(`marketplace.json: plugin "${entry.name}" source "${entry.source}" does not exist`);
    continue;
  }

  const pluginJsonPath = join(pluginDir, ".claude-plugin", "plugin.json");
  if (!existsSync(pluginJsonPath)) {
    err(`${pluginDir}: missing .claude-plugin/plugin.json`);
    continue;
  }

  const pluginJson = readJson(pluginJsonPath);
  if (!pluginJson) continue;
  if (pluginJson.name !== entry.name) {
    err(`${pluginJsonPath}: name "${pluginJson.name}" does not match marketplace entry "${entry.name}"`);
  }
  if (!pluginJson.version) err(`${pluginJsonPath}: missing "version"`);
  if (!pluginJson.description) err(`${pluginJsonPath}: missing "description"`);

  // 2. Skills frontmatter
  const skillsDir = join(pluginDir, "skills");
  for (const skillName of listDirs(skillsDir)) {
    const skillFile = join(skillsDir, skillName, "SKILL.md");
    if (!existsSync(skillFile)) {
      err(`${skillsDir}/${skillName}: missing SKILL.md`);
      continue;
    }
    checkFrontmatter(skillFile, ["name", "description"]);
  }

  // 3. Commands frontmatter (description is the key prompt for /help)
  const commandsDir = join(pluginDir, "commands");
  if (existsSync(commandsDir)) {
    for (const file of readdirSync(commandsDir)) {
      if (!file.endsWith(".md")) continue;
      checkFrontmatter(join(commandsDir, file), ["description"]);
    }
  }

  // 4. Agents frontmatter
  const agentsDir = join(pluginDir, "agents");
  if (existsSync(agentsDir)) {
    for (const file of readdirSync(agentsDir)) {
      if (!file.endsWith(".md")) continue;
      checkFrontmatter(join(agentsDir, file), ["name", "description"]);
    }
  }
}

// 5. Detect plugins on disk that are NOT registered in marketplace.json
const pluginsRoot = join(ROOT, "plugins");
for (const dir of listDirs(pluginsRoot)) {
  if (!declaredNames.has(dir)) {
    err(`plugins/${dir}: directory exists but is not listed in .claude-plugin/marketplace.json`);
  }
}

if (errors.length) {
  console.error(`validate: ${errors.length} error(s)`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}

console.log(`validate: OK (${declaredNames.size} plugin(s))`);
