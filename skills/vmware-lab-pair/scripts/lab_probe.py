#!/usr/bin/env python3
"""Generic VMware GuestOps probe.

Reads one external JSON config, checks already-running VMs, performs read-only
authentication plus a uniquely named file roundtrip in the guest temp directory,
and writes new evidence to a directory that must not already exist.

It never starts, stops, snapshots, clones or reconfigures a VM.  Supported
guests: Linux/POSIX with a POSIX /bin/sh.  Host: tested on Windows only.
"""

import argparse
import datetime
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

EXIT_OK = 0
EXIT_PROBE_FAILED = 1
EXIT_USAGE = 2

ROLE_KEYS = {"vmx", "user", "password_env", "expected_hostname",
             "expected_ipv4", "ping_target"}
TOP_KEYS = {"vmrun", "timeout_seconds", "roles"}
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PING_TARGET_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
REMOTE_DIR_RE = re.compile(r"^/tmp/lab-probe-[0-9a-f]{32}$")


class ConfigError(Exception):
    pass


def _require_string(value, label, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ConfigError(f"{label} must be a non-empty string")
    return value


def load_config(config_path):
    """Validate the whole config and return (config, config_dir).

    Relative VMX paths and an explicit relative vmrun path are resolved
    against the config file's own directory.
    """
    path = Path(config_path).expanduser()
    try:
        path = path.resolve(strict=True)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {config_path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"config is not valid UTF-8 JSON: {exc}")
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a JSON object")
    unknown = set(raw) - TOP_KEYS
    if unknown:
        raise ConfigError(f"unknown config key(s): {', '.join(sorted(unknown))}")

    timeout = raw.get("timeout_seconds", 90)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise ConfigError("timeout_seconds must be an integer in 1..600")

    vmrun = raw.get("vmrun")
    if vmrun is not None:
        _require_string(vmrun, "vmrun")
        vmrun_path = Path(vmrun).expanduser()
        if not vmrun_path.is_absolute():
            vmrun_path = path.parent / vmrun_path
        vmrun = str(vmrun_path)

    roles_raw = raw.get("roles")
    if not isinstance(roles_raw, dict) or not roles_raw:
        raise ConfigError("roles must be a non-empty JSON object")

    roles = {}
    for name, spec in roles_raw.items():
        _require_string(name, "role name")
        if not isinstance(spec, dict):
            raise ConfigError(f"role {name!r} must be an object")
        unknown = set(spec) - ROLE_KEYS
        if unknown:
            raise ConfigError(f"role {name!r} has unknown key(s): "
                              f"{', '.join(sorted(unknown))}")
        vmx = _require_string(spec.get("vmx"), f"role {name!r} vmx")
        vmx_path = Path(vmx).expanduser()
        if not vmx_path.is_absolute():
            vmx_path = path.parent / vmx_path
        try:
            vmx_path = vmx_path.resolve(strict=True)
        except FileNotFoundError:
            raise ConfigError(f"role {name!r} VMX not found: {vmx_path}")
        if not vmx_path.is_file():
            raise ConfigError(f"role {name!r} VMX is not a file: {vmx_path}")
        user = _require_string(spec.get("user"), f"role {name!r} user")
        password_env = _require_string(spec.get("password_env"),
                                       f"role {name!r} password_env")
        if not ENV_NAME_RE.match(password_env):
            raise ConfigError(f"role {name!r} password_env is not a valid "
                              "environment variable name")
        role = {"vmx": str(vmx_path), "user": user,
                "password_env": password_env}

        if "expected_hostname" in spec:
            role["expected_hostname"] = _require_string(
                spec["expected_hostname"], f"role {name!r} expected_hostname")
        if "expected_ipv4" in spec:
            raw_ip = _require_string(spec["expected_ipv4"],
                                     f"role {name!r} expected_ipv4")
            try:
                role["expected_ipv4"] = str(ipaddress.IPv4Address(raw_ip))
            except ValueError:
                raise ConfigError(f"role {name!r} expected_ipv4 is not an IPv4 address")
        if "ping_target" in spec:
            target = _require_string(spec["ping_target"],
                                     f"role {name!r} ping_target")
            if not PING_TARGET_RE.match(target):
                raise ConfigError(f"role {name!r} ping_target contains "
                                  "unsupported characters")
            role["ping_target"] = target
        roles[name] = role

    return {"vmrun": vmrun, "timeout_seconds": timeout, "roles": roles}, path.parent


def resolve_passwords(roles):
    """Read passwords from the environment; never return or print values."""
    passwords = {}
    for name, role in roles.items():
        value = os.environ.get(role["password_env"])
        if value is None:
            raise ConfigError(f"role {name!r}: environment variable "
                              f"{role['password_env']} is not set")
        if not value:
            raise ConfigError(f"role {name!r}: environment variable "
                              f"{role['password_env']} is empty")
        passwords[name] = value
    return passwords


def discover_vmrun(explicit, config_vmrun):
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"vmrun not found at --vmrun: {explicit}")
        return str(path)
    if config_vmrun:
        if not Path(config_vmrun).is_file():
            raise ConfigError(f"vmrun from config not found: {config_vmrun}")
        return config_vmrun
    found = shutil.which("vmrun")
    if not found:
        raise ConfigError("vmrun not found on PATH; use --vmrun or config 'vmrun'")
    return found


def require_new_dir(path):
    out = Path(path).expanduser().resolve()
    if out.exists():
        raise ConfigError(f"output directory already exists, choose a new one: {out}")
    try:
        out.mkdir(parents=True)
    except OSError as exc:
        raise ConfigError(f"cannot create output directory {out}: {exc}")
    return out


def sanitize(text, password):
    if not text:
        return ""
    if password:
        text = text.replace(password, "<redacted>")
    return text


def describe_args(args, password):
    """A loggable command description with the password removed."""
    return " ".join("<redacted>" if part == password else part for part in args)


def run_vmrun(vmrun, args, timeout, password):
    """Run vmrun with a bounded timeout; return rc/stdout/stderr (sanitized)."""
    try:
        proc = subprocess.run(
            [vmrun, *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        partial_out = exc.stdout or b""
        partial_err = exc.stderr or b""
        if isinstance(partial_out, bytes):
            partial_out = partial_out.decode("utf-8", "replace")
        if isinstance(partial_err, bytes):
            partial_err = partial_err.decode("utf-8", "replace")
        partial_err = (partial_err.rstrip() + f"\nvmrun timed out after {timeout}s").strip()
        return {"exit_code": 124,
                "stdout": sanitize(partial_out, password),
                "stderr": sanitize(partial_err, password),
                "command": describe_args(args, password)}
    except OSError as exc:
        return {"exit_code": None, "stdout": "",
                "stderr": f"cannot execute vmrun: {exc}",
                "command": describe_args(args, password)}
    return {"exit_code": proc.returncode,
            "stdout": sanitize(proc.stdout, password),
            "stderr": sanitize(proc.stderr, password),
            "command": describe_args(args, password)}


def running_vm_paths(vmrun, timeout):
    result = run_vmrun(vmrun, ["list"], timeout, "")
    paths = []
    for line in result["stdout"].splitlines():
        line = line.strip()
        if not line or line.lower().startswith("total running vms"):
            continue
        paths.append(os.path.normcase(os.path.normpath(line)))
    result["paths"] = paths
    return result


def slug(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:40] or "role"


def probe_script(ping_target):
    lines = [
        "#!/bin/sh",
        "set -u",
        "export LC_ALL=C",
        "status=0",
        "echo '=== hostname ==='",
        "hostname || status=1",
        "echo '=== id ==='",
        "id || status=1",
        "echo '=== ipv4 ==='",
        "if command -v ip >/dev/null 2>&1; then",
        "  ip -4 -br addr || status=1",
        "elif command -v ifconfig >/dev/null 2>&1; then",
        "  ifconfig -a || status=1",
        "else",
        "  echo 'no ip/ifconfig tool available'",
        "fi",
    ]
    if ping_target:
        lines += [
            "echo '=== ping ==='",
            f"ping -c 2 -W 2 '{ping_target}' || status=1",
        ]
    lines += ["exit \"$status\"", ""]
    return "\n".join(lines)


def parse_sections(output):
    """Split the probe output on its '=== name ===' markers."""
    sections = {}
    current = None
    for line in output.splitlines():
        marker = re.fullmatch(r"===\s*(.+?)\s*===", line.strip())
        if marker:
            current = marker.group(1)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def ipv4_tokens(lines):
    tokens = set()
    for line in lines:
        for match in re.finditer(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})"
                                 r"(?:/\d{1,2})?(?![\d.])", line):
            try:
                tokens.add(str(ipaddress.IPv4Address(match.group(1))))
            except ValueError:
                pass
    return tokens


def verify_output(output, role):
    """Check only the labeled sections so peer/ping text cannot satisfy identity."""
    problems = []
    sections = parse_sections(output)

    expected_hostname = role.get("expected_hostname")
    if expected_hostname:
        host_lines = [line.strip() for line in sections.get("hostname", [])
                      if line.strip()]
        if not host_lines:
            problems.append("hostname section missing or empty")
        elif host_lines[0] != expected_hostname:
            problems.append(f"hostname {host_lines[0]!r} does not exactly match "
                            f"expected {expected_hostname!r}")

    expected_ip = role.get("expected_ipv4")
    if expected_ip:
        addresses = ipv4_tokens(sections.get("ipv4", []))
        if expected_ip not in addresses:
            problems.append(f"IPv4 {expected_ip} not found in the guest's "
                            "labeled ipv4 section")

    if role.get("ping_target"):
        ping_text = "\n".join(sections.get("ping", []))
        match = re.search(
            r"(\d+)\s+packets transmitted,\s+(\d+)\s+(?:packets\s+)?received",
            ping_text)
        if not match:
            problems.append("ping summary not found or not in C locale form")
        elif int(match.group(1)) != 2 or int(match.group(2)) != 2:
            problems.append(f"ping expected 2 sent and 2 received, got "
                            f"{match.group(1)} sent, {match.group(2)} received")
    return problems


def probe_role(name, index, role, password, vmrun, timeout, out, running_paths):
    result = {
        "role": name,
        "vmx": role["vmx"],
        "user": role["user"],
        "password_env": role["password_env"],
        "running": os.path.normcase(os.path.normpath(role["vmx"])) in running_paths,
        "tools_state": None,
        "authentication_ok": False,
        "roundtrip_ok": False,
        "remote_exit_code": None,
        "cleanup_ok": None,
        "problems": [],
        "commands": [],
    }
    base = f"{index:02d}-{slug(name)}"
    auth = ["-gu", role["user"], "-gp", password]
    vmx = role["vmx"]

    tools = run_vmrun(vmrun, ["checkToolsState", vmx], timeout, password)
    result["tools_state"] = tools
    result["commands"].append(tools["command"])

    if not result["running"]:
        result["problems"].append(
            "VMX is not currently running; no power operation was attempted")
        return result

    readonly = run_vmrun(vmrun, [*auth, "listDirectoryInGuest", vmx, "/tmp"],
                         timeout, password)
    result["readonly"] = readonly
    result["commands"].append(readonly["command"])
    if readonly["exit_code"] != 0:
        result["problems"].append("read-only GuestOps authentication failed")
        result["readonly"] = readonly
        return result
    result["authentication_ok"] = True

    remote_dir = f"/tmp/lab-probe-{uuid.uuid4().hex}"
    if not REMOTE_DIR_RE.match(remote_dir):  # defensive; cannot happen
        raise RuntimeError("internal error: unsafe remote path")
    local_script = out / f"{base}-probe.sh"
    local_output = out / f"{base}-output.txt"
    local_status = out / f"{base}-status.txt"
    local_script.write_text(probe_script(role.get("ping_target")),
                            encoding="utf-8", newline="\n")
    created_ok = False
    try:
        created = run_vmrun(vmrun,
                            [*auth, "createDirectoryInGuest", vmx, remote_dir],
                            timeout, password)
        result["create_directory"] = created
        result["commands"].append(created["command"])
        if created["exit_code"] != 0:
            result["problems"].append("could not create unique guest temp directory")
            result["create_directory"] = created
            return result
        created_ok = True

        copied = run_vmrun(vmrun, [*auth, "copyFileFromHostToGuest", vmx,
                                   str(local_script),
                                   f"{remote_dir}/probe.sh"],
                           timeout, password)
        result["copy_to_guest"] = copied
        result["commands"].append(copied["command"])
        if copied["exit_code"] != 0:
            result["problems"].append("host-to-guest copy failed")
            result["copy_to_guest"] = copied
            return result

        wrapped = (f"sh '{remote_dir}/probe.sh' > '{remote_dir}/output.txt' "
                   f"2>&1; echo $? > '{remote_dir}/status.txt'")
        ran = run_vmrun(vmrun, [*auth, "runProgramInGuest", vmx,
                                "/bin/sh", "-c", wrapped],
                        timeout, password)
        result["commands"].append(ran["command"])
        result["run"] = ran
        if ran["exit_code"] != 0:
            # A successful file copy alone does not prove guest execution.
            result["problems"].append(
                f"runProgramInGuest failed with vmrun exit {ran['exit_code']}")
        # The wrapper reports the guest program's status through status.txt.
        status_copy = run_vmrun(
            vmrun, [*auth, "copyFileFromGuestToHost", vmx,
                    f"{remote_dir}/status.txt", str(local_status)],
            timeout, password)
        result["commands"].append(status_copy["command"])
        output_copy = run_vmrun(
            vmrun, [*auth, "copyFileFromGuestToHost", vmx,
                    f"{remote_dir}/output.txt", str(local_output)],
            timeout, password)
        result["copy_status"] = status_copy
        result["copy_from_guest"] = output_copy
        result["commands"].append(output_copy["command"])

        if output_copy["exit_code"] != 0:
            result["problems"].append("guest-to-host output copy failed; "
                                      "raw vmrun result preserved")
            result["copy_from_guest"] = output_copy
        else:
            output = local_output.read_text(encoding="utf-8", errors="replace")
            result["roundtrip_ok"] = True
            result["problems"].extend(verify_output(output, role))

        if status_copy["exit_code"] != 0 or not local_status.is_file():
            result["problems"].append("remote exit status was not retrieved")
        else:
            try:
                code = int(local_status.read_text(encoding="utf-8").strip())
            except ValueError:
                result["problems"].append("remote exit status is not an integer")
            else:
                result["remote_exit_code"] = code
                if code != 0:
                    result["problems"].append(
                        f"remote probe exited {code}; see preserved output")
    finally:
        if created_ok:
            # This directory was created fresh and only receives these three
            # files.  Delete them explicitly, then remove the empty directory
            # (deleteDirectoryInGuest has no recursive flag).  Anything else
            # left behind makes the final removal fail visibly.
            result["cleanup_files"] = []
            for leaf in ("probe.sh", "output.txt", "status.txt"):
                removed = run_vmrun(
                    vmrun, [*auth, "deleteFileInGuest", vmx,
                            f"{remote_dir}/{leaf}"], timeout, password)
                result["commands"].append(removed["command"])
                result["cleanup_files"].append(
                    {"file": leaf, "exit_code": removed["exit_code"],
                     "stdout": removed["stdout"], "stderr": removed["stderr"]})
            cleanup = run_vmrun(
                vmrun, [*auth, "deleteDirectoryInGuest", vmx, remote_dir],
                timeout, password)
            result["cleanup"] = cleanup
            result["commands"].append(cleanup["command"])
            result["cleanup_ok"] = cleanup["exit_code"] == 0
            if not result["cleanup_ok"]:
                result["problems"].append(
                    "guest temp directory cleanup failed; see cleanup diagnostics")
                result["cleanup"] = cleanup
    return result


def write_results(out, results):
    target = out / "probe-results.json"
    target.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only VMware GuestOps probe from an external JSON config.")
    parser.add_argument("--config", required=True,
                        help="JSON config naming VMX paths, accounts and targets")
    parser.add_argument("--out", required=True,
                        help="new output directory for evidence (must not exist)")
    parser.add_argument("--vmrun", help="explicit vmrun executable; default PATH")
    args = parser.parse_args(argv)

    try:
        config, config_dir = load_config(args.config)
        passwords = resolve_passwords(config["roles"])
        vmrun = discover_vmrun(args.vmrun, config.get("vmrun"))
        out = require_new_dir(args.out)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    timeout = config["timeout_seconds"]
    results = {
        "checked_at": datetime.datetime.now().astimezone().isoformat(),
        "vmrun": vmrun,
        "config": str(Path(args.config).expanduser().resolve()),
        "config_dir": str(config_dir),
        "timeout_seconds": timeout,
        "running_vms": None,
        "roles": {},
        "probe_ok": False,
    }

    listed = running_vm_paths(vmrun, timeout)
    results["running_vms"] = listed
    if listed["exit_code"] != 0:
        results["problems"] = ["vmrun list failed; running state is unknown"]
        write_results(out, results)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return EXIT_PROBE_FAILED

    running = listed["paths"]
    for index, (name, role) in enumerate(config["roles"].items(), start=1):
        try:
            results["roles"][name] = probe_role(
                name, index, role, passwords[name], vmrun, timeout, out, running)
        except Exception as exc:  # keep evidence for the remaining roles
            results["roles"][name] = {
                "role": name, "vmx": role["vmx"], "problems": [
                    f"unexpected probe error: {type(exc).__name__}: {exc}"],
                "cleanup_ok": None,
            }

    results["probe_ok"] = all(
        not role.get("problems") for role in results["roles"].values())
    write_results(out, results)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return EXIT_OK if results["probe_ok"] else EXIT_PROBE_FAILED


if __name__ == "__main__":
    sys.exit(main())
