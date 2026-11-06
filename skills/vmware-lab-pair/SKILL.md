---
name: vmware-lab-pair
description: "Probe already-running VMware VMs through vmrun GuestOps from an external JSON config: running and Tools state separately, real guest authentication, unique temp-file roundtrip, strict hostname/IP/ping checks, and new evidence output. Linux/POSIX guests only. Use for lab VM tool diagnosis and authorized lifecycle, console and GUI checks without assuming a particular VM pair."
---

# VMware lab guest operations

Generic method for VMware guests. This skill contains no machine names,
addresses, drive letters or passwords; an external JSON config supplies them.

**Support.** Host tooling tested on Windows with VMware Workstation's `vmrun`;
other host OSes are not claimed. Guest probing requires Linux/POSIX with a POSIX
`/bin/sh` (`hostname`, `id`, plus `ip` or `ifconfig`). Platform tools such as
agent-desktop or VNC are options to discover when available, not universal
prerequisites.

## Decision flow

1. **Discover** `vmrun`: the script checks PATH, or accepts `--vmrun` / config
   `vmrun`. Never assume a drive or install directory.
2. **Bind an explicit target**: use a JSON config; relative VMX paths resolve
   against the config file's directory.
3. **Smallest read-only probe**: `vmrun list` and `checkToolsState`, then
   `listDirectoryInGuest` per VM.
4. **Authorized task**: full probe adds a uniquely named `/tmp/lab-probe-*`
   roundtrip and optional hostname/IP/ping verification.
5. **Verify evidence**: read `probe-results.json` plus preserved per-role output.
6. **Diagnose one layer**: running state -> Tools -> authentication -> copy ->
   vmrun execution status -> remote exit status -> identity/ping -> cleanup.

The probe never starts, stops, snapshots, clones or reconfigures a VM. A stopped
VM is reported, not powered on.

## Config and run

```json
{
  "vmrun": "optional/path/to/vmrun",
  "timeout_seconds": 90,
  "roles": {
    "alpha": {
      "vmx": "../vms/alpha.vmx",
      "user": "labuser",
      "password_env": "LAB_ALPHA_PASSWORD",
      "expected_hostname": "alpha-lab",
      "expected_ipv4": "192.0.2.10",
      "ping_target": "192.0.2.11"
    }
  }
}
```

Role names are arbitrary. One account and one password environment variable per
VM; the value is supplied at runtime and never written. `expected_hostname`,
`expected_ipv4` and `ping_target` are optional.

Resolve the skill root from the loaded SKILL.md location; do not assume the
current directory or a particular installation path:

```bash
SKILL_ROOT=/absolute/path/to/vmware-lab-pair
python "$SKILL_ROOT/scripts/lab_probe.py" \
  --config /path/to/lab.json --out /path/to/new-dir
```

Exit codes: `0` all roles verified; `1` a probe step failed with diagnostics
preserved; `2` usage/config validation failed before guest actions.

Unknown keys, invalid IPv4 values, unsafe ping targets, missing VMX files,
unset/empty password variables and an existing output directory are rejected
first. Old evidence is never overwritten.

## What the evidence establishes

- **Running state** comes from the current `vmrun list`; that list is not a
  complete VM library, and absence means only "not running now".
- **Tools state** (`checkToolsState`) is recorded separately. A label that is
  not `running` does not by itself prove GuestOps are unusable.
- **Authentication** is demonstrated by successful GuestOps, not by account
  status text.
- **Roundtrip** keeps vmrun execution status, the guest program's explicit exit
  status, and captured output. A successful copy alone is not proof.
- **Identity** is matched exactly against the labeled `hostname` and `ipv4`
  sections, so a peer address in ping output cannot satisfy `expected_ipv4`.
  Ping must show exactly 2 sent and 2 received.
- **Cleanup** deletes only the three generated files, then the uniquely named
  directory (`deleteDirectoryInGuest` has no recursive flag). Leftovers or a
  failed removal make the probe fail and diagnostics are kept.
- Sanitized stdout/stderr and the command line (password redacted) are retained.

## Lifecycle, console and GUI

Detailed conditional branches live in [references/operations.md](references/operations.md).
Key distinctions:

- **Authorization persists.** If the user already authorized starting/stopping
  a named VMX, do not re-ask for the same action. Start/stop only explicitly
  named VMX files, bounded by a timeout, and record the exact return code. Do
  not expand the target set or add repairs without task authorization. No
  implicit power operation belongs inside a probe.
- **Screenshots** use `vmrun ... captureScreen <vmx> <new.png>` with a real
  guest account and a new filename. Record VMX absolute path, timestamp, exit
  code, image dimensions and SHA-256; keep the original image. GuestOps text is
  not a console screenshot, and a login screen is not an experiment screenshot.
- **VMX identity vs disk chain**: read `displayName` and `scsi0:0.fileName` as
  candidates. Do not infer addresses from names, and do not delete or repoint
  disks because a filename looks similar.
- **GUI** prefers agent-desktop headless: read its desktop/platform skills
  first, then snapshot -> semantic action -> new snapshot. Quote refs in
  PowerShell. No `--headed` without explicit authorization. Guest pixels are
  not host UIA controls. CLI evidence never proves a GUI action.
