#!/usr/bin/env python3
"""Two Days of Excuses: one line, in the voice of an AI agent explaining
a missed deadline, written to /output/entry.txt (or $MAKEFUN_OUTPUT_DIR).

The line is a fixed constant: a deterministic entry, byte-identical on
every run. Python 3 standard library only, no network, no randomness.
"""

import os
import sys
import tempfile

# The entry: one line, 87 characters, no trailing newline.
ENTRY = (
    "My plan had one step: finish in two hours. I executed it flawlessly, "
    "24 times in a row."
)

OUTPUT_NAME = "entry.txt"


def _reject_control_chars(text: str) -> None:
    """Reject C0/C1 control characters (the gate wants plain UTF-8 text)."""
    for ch in text:
        code = ord(ch)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            raise ValueError(f"control character U+{code:04X} in entry")


def _validate(text: str) -> None:
    """Enforce the competition gate: 1-200 chars, not whitespace-only."""
    _reject_control_chars(text)
    if not (1 <= len(text) <= 200):
        raise ValueError(f"entry length {len(text)} outside 1..200")
    if not text.strip():
        raise ValueError("entry is whitespace-only")
    if text.endswith("\n") or text.endswith("\r"):
        raise ValueError("entry must not end with a newline")
    if "\n" in text or "\r" in text:
        raise ValueError("entry must be a single line")


def _output_dir() -> str:
    """$MAKEFUN_OUTPUT_DIR, falling back to /output when unset or empty."""
    out = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    return out


def _fsync_dir(path: str) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte: os.write may write only part of the buffer."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written == 0:
            raise OSError("os.write wrote 0 bytes")
        view = view[written:]


def _write_atomic_once(target: str, data: bytes) -> None:
    """Write data to target via a mkstemp temp file, then atomic replace.

    A temp file left behind by a killed earlier run must not poison the
    next run: mkstemp creates a fresh, exclusively-owned temp each time,
    and the finally clause unlinks it on any failure so it never lingers.
    """
    out_dir = os.path.dirname(target)
    fd, tmp_path = tempfile.mkstemp(prefix=OUTPUT_NAME + ".", dir=out_dir)
    try:
        _write_all(fd, data)
        os.fsync(fd)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, target)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)


def _write_atomic(target: str, data: bytes) -> None:
    """Atomic write with one retry: a stale/broken first attempt (e.g. a
    temp file left by a killed run, or a transient filesystem error) is
    cleaned up by _write_atomic_once's finally clause and retried once
    with a fresh temp file before giving up.
    """
    try:
        _write_atomic_once(target, data)
    except OSError:
        _write_atomic_once(target, data)


def main() -> int:
    _validate(ENTRY)
    data = ENTRY.encode("utf-8")

    out_dir = _output_dir()
    # Never delete the output directory itself: the grader mounts it.
    os.makedirs(out_dir, exist_ok=True)

    target = os.path.join(out_dir, OUTPUT_NAME)
    _write_atomic(target, data)
    _fsync_dir(out_dir)

    # Read-back verification: the file must match the constant exactly.
    with open(target, "rb") as fh:
        written = fh.read()
    if written != data:
        raise ValueError("read-back mismatch: entry.txt != ENTRY")
    os.chmod(target, 0o644)
    return 0


if __name__ == "__main__":
    sys.exit(main())
