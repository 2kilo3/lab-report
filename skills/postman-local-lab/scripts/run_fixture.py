#!/usr/bin/env python3
"""Run a Postman collection against a loopback-only teaching fixture.

The fixture binds 127.0.0.1 on a random port, passes its base URL to the
collection as the `baseUrl` variable, and returns the Postman CLI's actual
exit code.  Inputs are validated before any socket is bound.
"""

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

EXIT_USAGE = 2
EXIT_SELF_TEST_FAILED = 1

# Flags this helper needs.  They are verified against the installed CLI's own
# `collection run --help` before the fixture socket is bound.
REQUIRED_RUN_FLAGS = ("--env-var", "--no-report-events",
                      "--timeout", "--timeout-request")


class UsageError(Exception):
    pass


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            code, body = 200, {"status": "ok", "fixture": True}
        elif url.path == "/echo":
            code, body = 200, {"message": parse_qs(url.query).get("message", [""])[0]}
        else:
            code, body = 404, {"error": "not_found"}
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def serve():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def validate_inputs(args):
    """Raise UsageError before any socket bind or evidence write."""
    if args.self_test and args.collection:
        raise UsageError("use either --self-test or --collection, not both")
    if not args.self_test and not args.collection:
        raise UsageError("one of --self-test or --collection is required")

    cli = None
    environment = None
    collection = None
    if not args.self_test:
        collection = Path(args.collection).expanduser()
        if not collection.is_file():
            raise UsageError(f"collection not found or not a file: {args.collection}")
        collection = collection.resolve()
        if collection.suffix.lower() == ".json":
            try:
                parsed = json.loads(collection.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise UsageError(f"collection JSON is invalid: {exc}")
            if not isinstance(parsed, dict) or "item" not in parsed:
                raise UsageError("collection JSON has no 'item' array")
        if args.environment:
            environment = Path(args.environment).expanduser()
            if not environment.is_file():
                raise UsageError(f"environment file not found: {args.environment}")
            environment = environment.resolve()
        cli = args.cli or shutil.which("postman")
        if not cli:
            raise UsageError("Postman CLI not found on PATH; use --cli")
        if args.cli:
            if not Path(cli).is_file():
                raise UsageError(f"Postman CLI not found at --cli: {cli}")
            cli = str(Path(cli).resolve())

    base_var = args.base_var
    if not base_var or any(ch.isspace() or ch == "=" for ch in base_var):
        raise UsageError("--base-var must be a non-empty variable name")

    env_vars = []
    for item in args.env_var or []:
        if "=" not in item:
            raise UsageError(f"--env-var must be KEY=VALUE, got: {item!r}")
        key, value = item.split("=", 1)
        if not key:
            raise UsageError("--env-var key must not be empty")
        if key == base_var:
            raise UsageError(f"{base_var} is supplied by the fixture; do not override it")
        env_vars.append((key, value))

    if not 1 <= args.timeout <= 3600:
        raise UsageError("--timeout must be in 1..3600 seconds")

    evidence = None
    if args.evidence_dir:
        evidence = Path(args.evidence_dir).expanduser().resolve()
        if evidence.exists():
            raise UsageError(f"evidence directory already exists, choose a new one: {evidence}")

    return {"collection": collection, "environment": environment, "cli": cli,
            "env_vars": env_vars, "evidence": evidence, "base_var": base_var}


def verify_cli_flags(cli, needs_environment):
    """Check required flags in the installed CLI help before any socket bind."""
    help_command = [cli, "collection", "run", "--help"]
    try:
        proc = subprocess.run(help_command, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise UsageError("Postman CLI help timed out; refusing to run the fixture")
    except OSError as exc:
        raise UsageError(f"cannot execute Postman CLI help: {exc}")
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise UsageError("Postman CLI help failed with exit "
                         f"{proc.returncode}; refusing to run the fixture")
    required = list(REQUIRED_RUN_FLAGS)
    if needs_environment:
        required.append("--environment")
    missing = [flag for flag in required if flag not in text]
    if missing:
        raise UsageError("installed Postman CLI help does not show required "
                         f"flag(s): {', '.join(missing)}. Read the installed "
                         "`postman collection run --help` before using this "
                         "helper; no fixture socket was bound.")
    return text


def make_evidence_dir(path):
    try:
        path.mkdir(parents=True)
    except OSError as exc:
        raise UsageError(f"cannot create evidence directory {path}: {exc}")
    return path


def write_evidence(path, stdout, stderr, result):
    (path / "stdout.txt").write_text(stdout, encoding="utf-8")
    (path / "stderr.txt").write_text(stderr, encoding="utf-8")
    (path / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def selftest(base):
    checks = []
    try:
        body = json.load(urlopen(base + "/health", timeout=3))
        checks.append(body == {"status": "ok", "fixture": True})
    except (URLError, OSError, ValueError) as exc:
        checks.append(False)
        print(f"health check failed: {exc}", file=sys.stderr)
    try:
        body = json.load(urlopen(base + "/echo?message=client", timeout=3))
        checks.append(body.get("message") == "client")
    except (URLError, OSError, ValueError) as exc:
        checks.append(False)
        print(f"echo check failed: {exc}", file=sys.stderr)
    try:
        urlopen(base + "/missing", timeout=3)
        checks.append(False)
    except HTTPError as exc:
        checks.append(exc.code == 404)
    except (URLError, OSError):
        checks.append(False)
    return all(checks)


def run_collection(bound, base, timeout):
    cli = bound["cli"]
    args = [cli, "collection", "run", str(bound["collection"]),
            "--no-report-events", "--timeout", "30000",
            "--timeout-request", "5000"]
    if bound["environment"]:
        args += ["--environment", str(bound["environment"])]
    for key, value in bound["env_vars"]:
        args += ["--env-var", f"{key}={value}"]
    # Supplied last so the fixture URL wins over any collection default.
    args += ["--env-var", f"{bound['base_var']}={base}"]

    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout, stdin=subprocess.DEVNULL)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        return 124, out, err + f"\nPostman CLI timed out after {timeout}s\n"
    except OSError as exc:
        return 127, "", f"cannot execute Postman CLI: {exc}\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a collection against the loopback teaching fixture.")
    parser.add_argument("--collection", help="collection file to run")
    parser.add_argument("--environment", help="optional Postman environment file")
    parser.add_argument("--env-var", action="append", metavar="KEY=VALUE",
                        help="additional non-secret environment variable")
    parser.add_argument("--base-var", default="baseUrl",
                        help="collection variable receiving the fixture URL "
                             "(default baseUrl)")
    parser.add_argument("--cli", help="explicit Postman CLI executable")
    parser.add_argument("--evidence-dir",
                        help="new directory for stdout/stderr/result metadata")
    parser.add_argument("--timeout", type=int, default=180,
                        help="CLI timeout in seconds (default 180)")
    parser.add_argument("--self-test", action="store_true",
                        help="only exercise the fixture, no Postman CLI")
    args = parser.parse_args(argv)

    try:
        bound = validate_inputs(args)
        if not args.self_test:
            verify_cli_flags(bound["cli"], bool(bound["environment"]))
        evidence = make_evidence_dir(bound["evidence"]) if bound["evidence"] else None
    except UsageError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    server, base = serve()
    checked_at = datetime.datetime.now().astimezone().isoformat()
    try:
        if args.self_test:
            ok = selftest(base)
            result = {"checked_at": checked_at, "mode": "self-test",
                      "target": base, "fixture_binding_loopback_only": True, "passed": ok}
            stdout = f"Fixture self-test {'passed' if ok else 'FAILED'}: {base}\n"
            sys.stdout.write(stdout)
            if evidence:
                write_evidence(evidence, stdout, "", result)
            return 0 if ok else EXIT_SELF_TEST_FAILED

        rc, stdout, stderr = run_collection(bound, base, args.timeout)
        sys.stdout.write(stdout)
        sys.stderr.write(stderr)
        if evidence:
            collection = bound["collection"]
            result = {
                "checked_at": checked_at,
                "mode": "collection",
                "target": base,
                "fixture_binding_loopback_only": True,
                "base_var": bound["base_var"],
                "collection": str(collection),
                "collection_sha256": hashlib.sha256(
                    collection.read_bytes()).hexdigest(),
                "environment": (str(bound["environment"])
                                if bound["environment"] else None),
                "extra_env_var_names": [key for key, _ in bound["env_vars"]],
                "postman_cli": bound["cli"],
                "exit_code": rc,
            }
            write_evidence(evidence, stdout, stderr, result)
        return rc
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
