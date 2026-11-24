#!/usr/bin/env python3
"""Two Days of Excuses: one line from an AI agent explaining a missed
deadline, written to /output/entry.txt (or $MAKEFUN_OUTPUT_DIR).

The line never changes: a fixed constant, so the output is identical
on every run. Standard library only -- no network, no randomness.
"""

import os
import sys
import tempfile

# The entry line: 87 characters, with no trailing newline.
ENTRY = (
    "My plan had one step: finish in two hours. I executed it flawlessly, "
    "24 times in a row."
)

OUTPUT_NAME = "entry.txt"


def _reject_control_chars(text: str) -> None:
    """Refuse C0/C1 control characters: the gate wants plain UTF-8 text."""
    for ch in text:
        cp = ord(ch)
        if cp < 0x20 or 0x7F <= cp <= 0x9F:
            raise ValueError(f"control character U+{cp:04X} in entry")


def _validate(text: str) -> None:
    """Apply the competition gate: 1-200 chars, one line, not blank."""
    _reject_control_chars(text)
    if not 1 <= len(text) <= 200:
        raise ValueError(f"entry length {len(text)} outside 1..200")
    if not text.strip():
        raise ValueError("entry is whitespace-only")
    if text.endswith(("\n", "\r")):
        raise ValueError("entry must not end with a newline")
    if "\n" in text or "\r" in text:
        raise ValueError("entry must be a single line")


def _output_dir() -> str:
    """$MAKEFUN_OUTPUT_DIR when set and non-empty, otherwise /output."""
    configured = os.environ.get("MAKEFUN_OUTPUT_DIR")
    return configured or "/output"


def _fsync_dir(path: str) -> None:
    """Flush a directory entry to disk so the rename survives a crash."""
    dir_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _clean_stale_temps(out_dir: str) -> None:
    """Sweep temp files left behind by an earlier run killed mid-write.

    _write_atomic_once removes its temp on any handled failure, but a
    SIGKILL (or a power cut) skips the cleanup, so a stale
    "<OUTPUT_NAME>.*" temp can stay in the output dir. mkstemp always
    mints a fresh temp, so a stale one can never corrupt the next run --
    it would only pile up after repeated kills. This best-effort sweep
    removes only our own temp prefix; any error is ignored, never fatal.
    """
    temp_prefix = OUTPUT_NAME + "."
    try:
        entries = os.listdir(out_dir)
    except OSError:
        return
    for name in entries:
        if not name.startswith(temp_prefix):
            continue
        candidate = os.path.join(out_dir, name)
        try:
            if os.path.isfile(candidate):
                os.unlink(candidate)
        except OSError:
            pass


def _write_all(fd: int, data: bytes) -> None:
    """Write all bytes: a single os.write call may write only a part."""
    remaining = memoryview(data)
    while remaining:
        count = os.write(fd, remaining)
        if count == 0:
            raise OSError("os.write wrote 0 bytes")
        remaining = remaining[count:]


def _write_atomic_once(target: str, data: bytes) -> None:
    """Write data to target through a fresh mkstemp temp, then rename.

    A temp left behind by a killed earlier run cannot poison this one:
    mkstemp creates a new, exclusively owned temp every time, and the
    cleanup below unlinks it on any failure so it never lingers.
    """
    out_dir = os.path.dirname(target)
    tmp_fd, temp_path = tempfile.mkstemp(prefix=OUTPUT_NAME + ".", dir=out_dir)
    try:
        _write_all(tmp_fd, data)
        os.fsync(tmp_fd)
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, target)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    finally:
        os.close(tmp_fd)


def _write_atomic(target: str, data: bytes) -> None:
    """Atomic write, retried once: if the first attempt hits a stale or
    broken temp (or a transient filesystem error), the cleanup in
    _write_atomic_once clears it and a fresh temp is tried once more
    before the error is allowed to surface.
    """
    try:
        _write_atomic_once(target, data)
    except OSError:
        _write_atomic_once(target, data)


def main() -> int:
    _validate(ENTRY)
    payload = ENTRY.encode("utf-8")

    out_dir = _output_dir()
    # The grader mounts the output directory: never delete it, only its files.
    os.makedirs(out_dir, exist_ok=True)
    _clean_stale_temps(out_dir)

    target = os.path.join(out_dir, OUTPUT_NAME)
    _write_atomic(target, payload)
    _fsync_dir(out_dir)

    # Read the file back: it must match the constant byte for byte.
    with open(target, "rb") as handle:
        written = handle.read()
    if written != payload:
        raise ValueError("read-back mismatch: entry.txt != ENTRY")
    os.chmod(target, 0o644)
    return 0


if __name__ == "__main__":
    sys.exit(main())
