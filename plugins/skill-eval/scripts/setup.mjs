#!/usr/bin/env node
// skill-eval setup: vendor the workflow + Python runner into the consumer repo.
// Invoked by /skill-eval:setup.
//
// Usage:
//   node setup.mjs            # refuse to overwrite existing files (exit 1 on conflict)
//   node setup.mjs --force    # wipe vendor-managed files + re-vendor cleanly
//
// Version tracking:
//   The plugin's version is recorded in `.skill-eval/.version` at setup time.
//   On re-run, if the recorded version differs from the current plugin
//   version, the script flags an upgrade. With --force, it also removes
//   known-legacy paths from prior layouts and wipes the vendored runner
//   directory before re-vendoring (so stale Python files from older
//   plugin versions don't hang around).

import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
  statSync,
  existsSync,
  rmSync,
} from "node:fs";
import { dirname, join, resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = resolve(HERE, "..");
const TEMPLATES = join(PLUGIN_ROOT, "templates");
const PROJECT_ROOT = process.cwd();

const force = process.argv.includes("--force");

// Paths from older plugin versions that are no longer used. When detected,
// the script offers to remove them (auto-removes on --force).
// Format: paths relative to PROJECT_ROOT.
const LEGACY_PATHS = [
  "skill-eval-scripts",  // pre-alpha.2: runner was at <root>/skill-eval-scripts/
];

const VERSION_FILE_REL = ".skill-eval/.version";

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

function readPluginVersion() {
  const pkgPath = join(PLUGIN_ROOT, ".claude-plugin", "plugin.json");
  return JSON.parse(readFileSync(pkgPath, "utf8")).version;
}

function readInstalledVersion() {
  const f = join(PROJECT_ROOT, VERSION_FILE_REL);
  if (!existsSync(f)) return null;
  return readFileSync(f, "utf8").trim();
}

function writeInstalledVersion(version) {
  const f = join(PROJECT_ROOT, VERSION_FILE_REL);
  mkdirSync(dirname(f), { recursive: true });
  writeFileSync(f, version + "\n");
}

function planCopies() {
  const copies = [];

  // 1. Workflow
  copies.push({
    src: join(TEMPLATES, "workflow.yml.template"),
    dst: join(PROJECT_ROOT, ".github", "workflows", "skill-eval.yml"),
  });

  // 2. Runner tree -> .skill-eval/scripts/
  const runnerDir = join(TEMPLATES, "runner");
  for (const file of listFilesRecursive(runnerDir)) {
    const rel = relative(runnerDir, file);
    copies.push({
      src: file,
      dst: join(PROJECT_ROOT, ".skill-eval", "scripts", rel),
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

function detectLegacyPaths() {
  return LEGACY_PATHS
    .map((p) => ({ rel: p, abs: join(PROJECT_ROOT, p) }))
    .filter((x) => existsSync(x.abs));
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

function rmDir(p) {
  if (!existsSync(p)) return false;
  rmSync(p, { recursive: true, force: true });
  return true;
}

function main() {
  if (!isProjectRoot(PROJECT_ROOT)) {
    err(`✗ Not a git repository: ${PROJECT_ROOT}`);
    err(`  Run \`git init\` first, then re-run /skill-eval:setup.`);
    process.exit(1);
  }

  const currentVersion = readPluginVersion();
  const installedVersion = readInstalledVersion();
  const isUpgrade = installedVersion && installedVersion !== currentVersion;
  const isFreshInstall = installedVersion === null;
  const legacy = detectLegacyPaths();

  if (isUpgrade) {
    log(`↑ skill-eval upgrade detected: ${installedVersion} → ${currentVersion}`);
  } else if (installedVersion === currentVersion) {
    log(`= skill-eval already at ${currentVersion}`);
  } else if (isFreshInstall) {
    log(`+ skill-eval ${currentVersion} (fresh install)`);
  }
  if (legacy.length) {
    log(`⚠️  Legacy path(s) from older layout detected:`);
    for (const x of legacy) log(`     - ${x.rel}/`);
  }

  const copies = planCopies();
  const conflicts = detectConflicts(copies);

  if ((conflicts.length || legacy.length) && !force) {
    if (conflicts.length) {
      err(`✗ Refusing to overwrite ${conflicts.length} existing file(s):`);
      for (const c of conflicts) {
        err(`  - ${relative(PROJECT_ROOT, c.dst)}`);
      }
    }
    if (legacy.length) {
      err(`✗ Legacy path(s) need removal: ${legacy.map((x) => x.rel + "/").join(", ")}`);
    }
    err(``);
    if (isUpgrade) {
      err(`  This is an upgrade (${installedVersion} → ${currentVersion}).`);
      err(`  Re-run with --force to migrate cleanly:`);
      err(`    - removes legacy paths`);
      err(`    - wipes .skill-eval/scripts/ before re-vendoring (drops stale runner files)`);
      err(`    - rewrites vendored files (workflow, schema, README)`);
      err(`  User-authored data (.claude/skills/<skill>/skill-eval/scenarios.json,`);
      err(`  .skill-eval/reports/) is NEVER touched.`);
    } else {
      err(`  Re-run with --force to overwrite, or remove these files first.`);
    }
    process.exit(1);
  }

  // --force path: clean up before vendoring.
  if (force) {
    const cleaned = [];
    for (const x of legacy) {
      if (rmDir(x.abs)) cleaned.push(x.rel + "/");
    }
    // Wipe the vendored runner dir so files removed in the new plugin
    // version don't linger from a previous install.
    const runnerDst = join(PROJECT_ROOT, ".skill-eval", "scripts");
    if (rmDir(runnerDst)) cleaned.push(".skill-eval/scripts/");

    if (cleaned.length) {
      log(`✓ Cleaned: ${cleaned.join(", ")}`);
    }
  }

  for (const c of copies) {
    copyFile(c.src, c.dst);
  }

  // Empty reports directory with .gitkeep (the workflow writes here)
  ensureGitkeep(join(PROJECT_ROOT, ".skill-eval", "reports"));

  // Record the version we just installed so future runs can detect upgrades.
  writeInstalledVersion(currentVersion);

  log(`✓ skill-eval ${currentVersion} set up in ${PROJECT_ROOT}`);
  log(`  - .github/workflows/skill-eval.yml`);
  log(`  - .skill-eval/scripts/ (Python runner)`);
  log(`  - .skill-eval/scenario.schema.json + README.md`);
  log(`  - .skill-eval/.version (= ${currentVersion})`);
  log(`  - .skill-eval/reports/ (empty — populated by CI)`);
  log(``);
  log(`Scenarios live at .claude/skills/<skill>/skill-eval/scenarios.json`);
  log(`(co-located with each SKILL.md). Run /skill-eval:create-test to author them.`);
  log(``);
  log(`Next: add COPILOT_GITHUB_TOKEN secret, then /skill-eval:create-test.`);
}

main();
