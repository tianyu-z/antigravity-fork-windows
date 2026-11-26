"""Prepare, install, or restore the verified macOS Fork patch.

Only prepare writes a build receipt. Install/restore keep the exact previous
target in a sibling directory so failures and unsealed files remain recoverable.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile

from patch_antigravity_macos import EXPECTED_SHA256, patched_binary


VERSION = "2.35.2"
CODE_FILES = (
    "Contents/MacOS/Antigravity",
    "Contents/Resources/bin/language_server",
    "Contents/_CodeSignature/CodeResources",
)
LIBRARY_ENTITLEMENT = "com.apple.security.cs.disable-library-validation"


def run(command, env=None):
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=120)
    if result.returncode:
        raise RuntimeError("{} failed ({}): {}".format(
            Path(command[0]).name, result.returncode, (result.stderr or result.stdout).strip()))
    return result.stdout


def fingerprint(app):
    return {name: hashlib.sha256((Path(app) / name).read_bytes()).hexdigest()
            for name in CODE_FILES}


def ensure_outside(container, candidate):
    container, candidate = Path(container).resolve(), Path(candidate).resolve()
    try:
        candidate.relative_to(container)
    except ValueError:
        if not container.exists() or not any(
                ancestor.exists() and ancestor.samefile(container)
                for ancestor in [candidate] + list(candidate.parents)):
            return
    raise ValueError("The output/target must be outside {}.".format(container))


def verify_signature(app, original=False):
    command = ["codesign", "--verify", "--deep", "--strict", str(app)]
    if original:
        command += ["-R", '=anchor apple generic and certificate leaf[subject.OU] = "EQHXZ8M8AV"']
    run(command)


def validate_original(app):
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != "com.google.antigravity" or \
            info.get("CFBundleShortVersionString") != VERSION:
        raise ValueError("An unmodified Antigravity 2.35.2 application is required.")
    result = fingerprint(app)
    if result[CODE_FILES[1]] != EXPECTED_SHA256:
        raise ValueError("Language-server hash does not match the verified 2.35.2 arm64 build.")
    verify_signature(app, original=True)
    return result


def copy_app(source, destination):
    # Construct a fresh app container rather than inheriting the download
    # attributes of the original app's outer directory. Preserve its contents.
    source, destination = Path(source), Path(destination)
    destination.mkdir()
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_symlink():
            target.symlink_to(os.readlink(str(entry)))
        elif entry.is_dir():
            run(["ditto", str(entry), str(target)])
        else:
            shutil.copy2(str(entry), str(target))


def copy_original_app(source, destination):
    if Path(destination).exists() or Path(destination).is_symlink():
        raise ValueError("Original application copy destination already exists.")
    run(["ditto", "--rsrc", "--extattr", "--acl", "--qtn", str(source), str(destination)])
    if hasattr(os, "chflags"):
        flags = Path(source).stat().st_flags
        if Path(destination).stat().st_flags != flags:
            os.chflags(str(destination), flags)


def rebuild_file(source, destination, data=None):
    source, destination = Path(source), Path(destination)
    new = destination.with_name(destination.name + ".fork-build")
    with new.open("xb") as output:
        if data is None:
            with source.open("rb") as original:
                shutil.copyfileobj(original, output)
        else:
            output.write(data)
    new.chmod(source.stat().st_mode & 0o777)
    os.replace(str(new), str(destination))


def prepare(source, build):
    source, build = Path(source).resolve(), Path(build).resolve()
    ensure_outside(source, build)
    if build.exists():
        raise ValueError("Build directory already exists; choose a new directory.")
    original_hashes = validate_original(source)
    build.mkdir()
    original = build / "original" / "Antigravity.app"
    patched = build / "patched" / "Antigravity.app"
    original.parent.mkdir()
    patched.parent.mkdir()
    print("Copying the complete original application...", flush=True)
    copy_original_app(source, original)
    if validate_original(original) != original_hashes:
        raise ValueError("The source changed while its backup was being created.")
    copy_app(original, patched)
    server = patched / CODE_FILES[1]
    rebuild_file(original / CODE_FILES[1], server,
                 patched_binary((original / CODE_FILES[1]).read_bytes()))
    preserve = "identifier,entitlements,flags,runtime"
    run(["codesign", "--force", "--sign", "-", "--timestamp=none",
         "--preserve-metadata=" + preserve, str(server)])
    run(["codesign", "--verify", "--strict", str(server)])
    print("Signing the main app and checking native startup...", flush=True)
    entitlements = plistlib.loads(run(["codesign", "-d", "--entitlements", ":-", str(original)]).encode())
    entitlements[LIBRARY_ENTITLEMENT] = True
    entitlement_file = build / "local-app-entitlements.plist"
    entitlement_file.write_bytes(plistlib.dumps(entitlements))
    rebuild_file(original / CODE_FILES[0], patched / CODE_FILES[0])
    run(["codesign", "--force", "--sign", "-", "--timestamp=none",
         "--preserve-metadata=identifier,flags,runtime",
         "--entitlements", str(entitlement_file), str(patched)])
    verify_signature(patched)
    run([str(server), "--stamp"])
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
    marker = "ANTIGRAVITY_FORK_NATIVE_OK"
    output = run([str(patched / CODE_FILES[0]), "--eval",
                  'process.stdout.write("' + marker + '")'], env=env)
    if output != marker:
        raise RuntimeError("The native startup smoke check did not return its expected result.")
    if validate_original(source) != original_hashes:
        raise ValueError("The source app changed during preparation; do not install this build.")
    receipt = {"schema": 1, "version": VERSION,
               "original": original_hashes, "patched": fingerprint(patched)}
    (build / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Prepared and verified: {}".format(patched))
    print("Original backup: {}".format(original))


def read_receipt(build):
    receipt = json.loads((Path(build) / "receipt.json").read_text())
    if not isinstance(receipt, dict) or receipt.get("schema") != 1 or receipt.get("version") != VERSION:
        raise ValueError("Unsupported or incomplete build receipt.")
    for kind in ("original", "patched"):
        values = receipt.get(kind)
        if not isinstance(values, dict) or set(values) != set(CODE_FILES) or any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in values.values()):
            raise ValueError("Invalid application fingerprints in the build receipt.")
    if receipt["original"][CODE_FILES[1]] != EXPECTED_SHA256:
        raise ValueError("Receipt does not refer to the verified original build.")
    return receipt


def ensure_closed(app):
    processes = {line.strip() for line in run(["ps", "-axo", "comm"]).splitlines()}
    paths = {str(Path(app) / CODE_FILES[0]), str(Path(app) / CODE_FILES[1])}
    if paths & processes:
        raise ValueError("Quit Antigravity completely and wait for its language server to exit.")


def replace_app(source, target, expected_current, expected_new, preserve_metadata=False):
    source, target = Path(source).resolve(), Path(target).resolve()
    ensure_outside(source, target)
    ensure_outside(target, source)
    ensure_closed(target)
    if fingerprint(target) != expected_current:
        raise ValueError("Installed app differs from the expected build; refusing to replace an update or unknown changes.")
    if fingerprint(source) != expected_new:
        raise ValueError("Backup/staged app differs from its build receipt.")
    verify_signature(target)
    verify_signature(source)
    transaction = Path(tempfile.mkdtemp(prefix=".antigravity-fork-", dir=str(target.parent)))
    pending, previous = transaction / "pending.app", transaction / "previous.app"
    copier = copy_original_app if preserve_metadata else copy_app
    copier(source, pending)
    verify_signature(pending)
    if fingerprint(pending) != expected_new or fingerprint(target) != expected_current:
        raise ValueError("An application changed before replacement; original remains installed.")
    ensure_closed(target)
    os.rename(str(target), str(previous))
    installed = False
    try:
        if fingerprint(previous) != expected_current:
            raise ValueError("The original app changed during replacement.")
        verify_signature(previous)
        os.rename(str(pending), str(target))
        installed = True
        verify_signature(target)
        if fingerprint(target) != expected_new:
            raise ValueError("Installed copy failed fingerprint verification.")
    except BaseException as failure:
        failed_copy = transaction / "failed.app"
        try:
            if installed:
                os.rename(str(target), str(failed_copy))
            if target.exists():
                raise RuntimeError("Another application appeared at the target.")
            os.rename(str(previous), str(target))
        except BaseException as recovery_failure:
            candidate = failed_copy if failed_copy.exists() else target if target.exists() else pending
            raise RuntimeError(
                "Replacement failed: {}. Rollback failed: {}. "
                "Previous application preserved at: {}. "
                "Candidate/current application: {}.".format(
                    failure, recovery_failure, previous, candidate)) from recovery_failure
        raise
    return previous


def apply_build(action, build, target):
    build, target = Path(build).resolve(), Path(target).resolve()
    ensure_outside(build, target)
    ensure_outside(target, build)
    receipt = read_receipt(build)
    original, patched = build / "original/Antigravity.app", build / "patched/Antigravity.app"
    for protected in (original, patched):
        ensure_outside(protected, target)
        ensure_outside(target, protected)
    if fingerprint(original) != receipt["original"]:
        raise ValueError("Original backup does not match the build receipt.")
    verify_signature(original, original=True)
    if action == "install":
        source, current, new = patched, receipt["original"], receipt["patched"]
    else:
        source, current, new = original, receipt["patched"], receipt["original"]
    if fingerprint(target) == new:
        verify_signature(target)
        print("The requested build is already installed.")
        return
    previous = replace_app(source, target, current, new, preserve_metadata=(action == "restore"))
    print("{} complete: {}".format(action.capitalize(), target))
    print("Exact previous application preserved at: {}".format(previous))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "install", "restore"))
    parser.add_argument("source_or_build", help="Original .app for prepare; build directory for install/restore")
    parser.add_argument("output_or_app", help="New build directory for prepare; installed .app for install/restore")
    args = parser.parse_args()
    try:
        if sys.platform != "darwin":
            raise RuntimeError("macOS application operations must run on macOS.")
        if args.action == "prepare":
            prepare(args.source_or_build, args.output_or_app)
        else:
            apply_build(args.action, args.source_or_build, args.output_or_app)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        message = str(error)
        if "Operation not permitted" in message or "Permission denied" in message:
            message += "\nEnable App Management for the terminal/desktop host in macOS Privacy & Security, then retry."
        raise SystemExit(message)


if __name__ == "__main__":
    main()
