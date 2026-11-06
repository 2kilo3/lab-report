# VMware lab operations reference

Conditional details for when the read-only probe is not enough. No local
machine values belong here; bind a VMX explicitly first.

## Authorized lifecycle actions

When the user has already authorized start/stop for named VMX files:

1. Read current state with `vmrun list`; absence from that list is not proof a
   VM does not exist.
2. Start or stop only the named VMX, with a bounded command timeout, and keep
   stdout/stderr and the actual return code.
3. Verify the new state with a fresh `vmrun list`, not from the command's
   optimistic output.
4. Never retry blindly after a timeout: first check whether the original
   process is alive and read the host state.

Keep each power, configuration, network or repair action within the user's
requested scope. Routine diagnosis needs no repair clone. Starting a stopped
VM is a power operation; the probe itself never does it implicitly.

## Tools and GuestOps

`checkToolsState` and running state are separate facts. If Tools reports
`installed`/`unknown`, try one bounded read-only GuestOps call such as
`listDirectoryInGuest <vmx> /tmp`:

- success: record the state discrepancy and continue;
- failure: check console, power state and logs; do not assume a wrong password
  and do not loop indefinitely.

Authentication failure is diagnosed by rechecking the VMX identity, the
provided account and Tools state. Do not cycle through guessed passwords.

## File roundtrip

The supported sequence is:

```text
copyFileFromHostToGuest -> runProgramInGuest -> copyFileFromGuestToHost
```

For POSIX guests, write scripts with LF endings, set `LC_ALL=C` for stable
output, and have the remote wrapper write `$?` to a status file. Recover and
record:

- vmrun execution return code (wrapper launch),
- the guest program's explicit exit status,
- combined guest output,
- cleanup results for each generated file and the directory.

A successful copy or a zero wrapper code alone does not prove the remote
program ran successfully.

## Console screenshots

```bash
vmrun -gu "$GUEST_USER" -gp "$GUEST_PASSWORD" captureScreen "$VMX" "$NEW_PNG"
```

Supply `GUEST_PASSWORD` from the environment and redact logged commands. vmrun
requires the value in its process arguments; use it on a trusted host and avoid
shell tracing or credential-bearing process dumps. After capture:

- verify the file exists and is non-empty;
- record VMX absolute path, timestamp, exit code, dimensions and SHA-256;
- keep the original image and use a new output name each time;
- view the image before describing it.

Distinguish GuestOps text, a login screen, and a screenshot of the actual
experiment state. Do not add synthetic mouse markers and do not present one as
another.

## VMX identity and disks

Read `displayName`, `scsi0:0.fileName` and adapter types as candidates only.
Snapshot chains may change; never hard-code an incremental disk name. Do not
delete, rebuild or repoint a disk because a parent file is missing or a name
looks similar. Record the full parent chain before any authorized action.

## GUI and modals

Use agent-desktop headless when desktop interaction is needed: load its
`desktop` and `platform` skills, then snapshot -> semantic action -> fresh
snapshot. PowerShell refs must be quoted (for example `'@s8f3k2p9:e1'`).
`--headed` requires explicit user authorization.

Guest console pixels are not host accessibility-tree controls; do not drive
them with repeated SendInput/WM_CHAR guesses. If a configured VNC channel is
already authorized, confirm the port and VM identity before input and do not
expose a new port.

When a start command appears to hang on a host dialog (for example a serial
log Append/Replace prompt), check that the original process is still alive,
then inspect the host UI with a fresh snapshot. Append preserves the existing
log; never choose Replace blindly, and do not launch a duplicate start or clone
while waiting.

## Failure branches

- **Copy or screenshot fails**: keep raw exit code and sanitized error, reread
  state, then decide whether a bounded retry is justified; never overwrite old
  evidence.
- **initramfs/fsck errors**: record diagnostics. For a requested repair, verify
  mount state and rollback conditions; never let a rescue VM and the normal VM
  write the same disk.
- **Missing vmdk**: inspect the complete parent chain; do not delete or
  recreate disks from a similar filename.
- **Duplicate library entries**: compare absolute VMX paths. A repeated
  registration of one VMX is not an extra disk. Back up library configuration
  and close related GUI/tray processes before any authorized cleanup.
- **Tools misreporting**: prefer one bounded GuestOps call over conclusions
  drawn from the Tools label alone.
- **Hash command unavailable**: use Python `hashlib` or a documented fallback;
  do not conclude that every shell on the host lacks the command.

Label conclusions as measured now, historical, or unverified.
