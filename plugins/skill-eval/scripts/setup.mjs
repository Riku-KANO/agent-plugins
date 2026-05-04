#!/usr/bin/env node
// skill-eval setup: vendor the workflow + Python runner into the consumer repo.
// Invoked by /skill-eval:setup.
//
// Usage:
//   node setup.mjs            # refuse to overwrite existing files (exit 1 on conflict)
//   node setup.mjs --force    # overwrite existing files

import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
  statSync,
  existsSync,
} from "node:fs";
import { dirname, join, resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = resolve(HERE, "..");
const TEMPLATES = join(PLUGIN_ROOT, "templates");
const PROJECT_ROOT = process.cwd();

const force = process.argv.includes("--force");

function log(msg) {
  process.stdout.write(msg + "\n");
}
function err(msg) {
  process.stderr.write(msg + "\n");
}

function isProjectRoot(dir) {
  return existsSync(join(dir, ".git"));
}

function listFilesRecursive(dir) {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...listFilesRecursive(full));
    } else {
      out.push(full);
    }
  }
  return out;
}

function planCopies() {
  // Map of relative source path -> destination path (relative to PROJECT_ROOT).
  const copies = [];

  // 1. Workflow
  copies.push({
    src: join(TEMPLATES, "workflow.yml.template"),
    dst: join(PROJECT_ROOT, ".github", "workflows", "skill-eval.yml"),
  });

  // 2. Runner tree -> skill-eval-scripts/
  const runnerDir = join(TEMPLATES, "runner");
  for (const file of listFilesRecursive(runnerDir)) {
    const rel = relative(runnerDir, file);
    copies.push({
      src: file,
      dst: join(PROJECT_ROOT, "skill-eval-scripts", rel),
    });
  }

  // 3. Scenario schema
  copies.push({
    src: join(TEMPLATES, "scenario.schema.json"),
    dst: join(PROJECT_ROOT, ".skill-eval", "scenario.schema.json"),
  });

  // 4. Consumer-side README
  copies.push({
    src: join(TEMPLATES, "README.template.md"),
    dst: join(PROJECT_ROOT, ".skill-eval", "README.md"),
  });

  return copies;
}

function detectConflicts(copies) {
  return copies.filter((c) => existsSync(c.dst));
}

function copyFile(src, dst) {
  mkdirSync(dirname(dst), { recursive: true });
  const data = readFileSync(src);
  writeFileSync(dst, data);
}

function ensureGitkeep(dir) {
  mkdirSync(dir, { recursive: true });
  const keep = join(dir, ".gitkeep");
  if (!existsSync(keep)) writeFileSync(keep, "");
}

function main() {
  if (!isProjectRoot(PROJECT_ROOT)) {
    err(`✗ Not a git repository: ${PROJECT_ROOT}`);
    err(`  Run \`git init\` first, then re-run /skill-eval:setup.`);
    process.exit(1);
  }

  const copies = planCopies();
  const conflicts = detectConflicts(copies);

  if (conflicts.length && !force) {
    err(`✗ Refusing to overwrite ${conflicts.length} existing file(s):`);
    for (const c of conflicts) {
      err(`  - ${relative(PROJECT_ROOT, c.dst)}`);
    }
    err(``);
    err(`  Re-run with --force to overwrite, or remove these files first.`);
    process.exit(1);
  }

  for (const c of copies) {
    copyFile(c.src, c.dst);
  }

  // Empty reports directory with .gitkeep (the workflow writes here)
  ensureGitkeep(join(PROJECT_ROOT, ".skill-eval", "reports"));

  log(`✓ skill-eval set up in ${PROJECT_ROOT}`);
  log(`  - .github/workflows/skill-eval.yml`);
  log(`  - skill-eval-scripts/ (Python runner)`);
  log(`  - .skill-eval/scenario.schema.json + README.md`);
  log(`  - .skill-eval/reports/ (empty — populated by CI)`);
  log(``);
  log(`Scenarios live at .claude/skills/<skill>/skill-eval/scenarios.json`);
  log(`(co-located with each SKILL.md). Run /skill-eval:create-test to author them.`);
  log(``);
  log(`Next: add COPILOT_GITHUB_TOKEN secret, then /skill-eval:create-test.`);
}

main();
