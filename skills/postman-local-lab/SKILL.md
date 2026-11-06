---
name: postman-local-lab
description: "Run an existing Postman collection or environment with the installed Postman CLI, discover the CLI from PATH or an override, verify assertions and the real child exit code, and train tool behavior with a loopback-only fixture plus a genuinely failing negative collection. Fixture runs are not real-service tests; CLI evidence never proves GUI success."
---

# Postman local collection runs

Reuse the user's existing collection, environment and variable names. This
skill contains no machine paths, credentials or frozen CLI help text.

**Support.** Tested on Windows with a locally installed Postman CLI; Python is
stdlib-only. Other host OSes and CLI versions are not claimed. Read the
installed CLI's own help before relying on a flag.

## Decision flow

1. **Discover** the CLI with `shutil.which("postman")` or `--cli`; confirm with
   `postman --version` and `postman collection run --help`.
2. **Bind an explicit target**: collection, optional environment, existing
   variable names, non-secret `--env-var KEY=VALUE`.
3. **Smallest read-only probe**: choose a known read-only, authorized request
   to identify the real target. A collection may contain writes; inspect its
   scope before running it. For tool training, use the fixture below.
4. **Authorized task**: run the collection.
5. **Verify evidence**: child exit code + requests/assertions executed/failed +
   actual target. HTTP 200 alone is not a pass; zero assertions is not proof.
6. **Diagnose one layer**: CLI presence/help -> paths -> target reachability ->
   response -> assertion -> exit-code propagation.

Do not add blanket login prompts, cloud publishing, `init`/`update` or
`--suppress-exit-code`. A cloud-publishing hint is not a local test failure.

## Real collection: invoke the CLI directly

Run the user's real collection against its real target with the Postman CLI
itself. The helper in this skill always substitutes a loopback base URL and must
**not** be used for that purpose.

Resolve the installed help first, then use the flags it documents:

```bash
postman collection run --help
postman --version

postman collection run "$COLLECTION" \
  --environment "$ENVIRONMENT" \
  --env-var hint=value \
  --no-report-events \
  --timeout 30000 --timeout-request 5000
```

Capture `$?` (or PowerShell `$LASTEXITCODE`) immediately after the CLI command;
do not let a later command overwrite it. If you wrap it, return the child's
actual code. Keep raw stdout/stderr, the collection/environment paths, the
actual target, and assertion counts as evidence.

Only pass `--environment` / `--env-var` when the collection needs them, and
never put real credentials in a collection, command log or evidence file.

## Fixture helper: training only

The helper below starts a loopback-only teaching fixture, rewrites the selected
base variable to the fixture URL, and runs a **test** collection against it.
It is not a real-service runner.

Resolve the skill root from the loaded SKILL.md location; do not assume the
current directory or a particular installation path:

```bash
SKILL_ROOT=/absolute/path/to/postman-local-lab

python "$SKILL_ROOT/scripts/run_fixture.py" --self-test

python "$SKILL_ROOT/scripts/run_fixture.py" \
  --collection "$SKILL_ROOT/assets/training.postman_collection.json" \
  --evidence-dir /path/to/new-dir-pass

python "$SKILL_ROOT/scripts/run_fixture.py" \
  --collection "$SKILL_ROOT/assets/training.postman_collection.fail.json" \
  --evidence-dir /path/to/new-dir-fail
```

- Fixture binds `127.0.0.1` on a random port and stops afterwards.
- `fixture_binding_loopback_only` describes the server's binding. `target`
  records the injected fixture URL, not a capture of every request. Inspect
  custom collection URLs and scripts before running them; they can name other
  targets. The bundled collections are the verified fixture examples.
- `GET /health` -> 200 `{status:"ok",fixture:true}`; `/echo?message=client` ->
  200; other paths -> 404 `{error:"not_found"}`.
- The positive v2.1 JSON collection is parameterized by `{{baseUrl}}`, with 3
  requests and 6 `pm.test` assertions; expected exit 0.
- The negative collection deliberately expects 201 from `/health`; it must
  return a **nonzero** child exit code and a real assertion failure. Never
  suppress or overwrite that code.
- If the collection's base variable has another name, pass `--base-var NAME`.
  The selected base variable is reserved for the fixture.
- Before binding a socket the helper validates paths/JSON and checks the
  installed `collection run --help` for the flags it will use. If a flag is
  missing, it fails clearly instead of guessing.
- `--evidence-dir` must not exist. It receives `stdout.txt`, `stderr.txt` and
  `result.json` (target, collection SHA-256, child exit code, CLI path,
  environment variable **names** only).
- Existing v3 YAML projects keep that format; no conversion is required.

## GUI

GUI work prefers agent-desktop headless and its desktop/platform skills.
Listing a window is not a working snapshot, and CLI results never stand in for
a requested GUI action. If GUI automation is unavailable, record the specific
failure and use an authorized GUI channel; do not claim GUI success.
