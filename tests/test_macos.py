import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    path = ROOT / (name + ".py")
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PATCH = load_module("patch_antigravity_macos")
APP = load_module("macos_app")
FLAGS = (b"conversationForkingEnabled", b"conversationForkingHistoricalStep")


def resource_binary(duplicate_flag=False, compression=zipfile.ZIP_DEFLATED):
    script = b"const defaults={" + b",".join(flag + b":!1" for flag in FLAGS) + b"};"
    if duplicate_flag:
        script += b"const other={conversationForkingEnabled:!1};"
    script += b"/*" + b"a repeated test-only comment " * 3000 + b"*/"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        archive.writestr("other.txt", b"This resource must remain unchanged.")
        archive.writestr("main.js", script, compress_type=compression)
        archive.writestr("nested/data.bin", bytes(range(256)) * 3)
        archive.comment = b"test archive comment"
    prefix, suffix = b"test executable prefix\0", b"test executable suffix\0"
    binary = prefix + stream.getvalue() + suffix
    return binary, len(prefix), len(binary) - len(suffix), script


def fake_app(path, label):
    for relative in ("Contents/MacOS/Antigravity", "Contents/Resources/bin/language_server",
                     "Contents/_CodeSignature/CodeResources"):
        file = path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes((label + relative).encode())
    (path / "user-note.txt").write_text(label)
    return path


class MacPatchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PATCH, "The macOS patch module has not been published.")

    def test_real_profile_is_pinned_to_verified_arm64_build(self):
        self.assertEqual(PATCH.EXPECTED_SHA256,
                         "8b11ecde9d089ebbe4511871e75bd046e04f33865c27b617e29a3c237a2bd575")
        self.assertEqual((PATCH.ARCHIVE_START, PATCH.ARCHIVE_END), (159091037, 165254803))
        with self.assertRaises(ValueError):
            PATCH.patched_binary(b"a different build")

    def patch_fixture(self, data, start, end):
        with mock.patch.object(PATCH, "EXPECTED_SHA256", hashlib.sha256(data).hexdigest()), \
                mock.patch.object(PATCH, "ARCHIVE_START", start), \
                mock.patch.object(PATCH, "ARCHIVE_END", end):
            return PATCH.patched_binary(data)

    def test_round_trip_preserves_executable_and_all_unrelated_resources(self):
        data, start, end, script = resource_binary()
        result = self.patch_fixture(data, start, end)
        self.assertEqual(len(result), len(data))
        self.assertEqual(result[:start], data[:start])
        self.assertEqual(result[end:], data[end:])
        with zipfile.ZipFile(io.BytesIO(data[start:end])) as original, \
                zipfile.ZipFile(io.BytesIO(result[start:end])) as changed:
            self.assertIsNone(changed.testzip())
            self.assertEqual(changed.namelist(), original.namelist())
            self.assertEqual(changed.comment, original.comment)
            self.assertEqual(changed.read("other.txt"), original.read("other.txt"))
            self.assertEqual(changed.read("nested/data.bin"), original.read("nested/data.bin"))
            for flag in FLAGS:
                script = script.replace(flag + b":!1", flag + b":!0")
            self.assertEqual(changed.read("main.js"), script)

    def test_duplicate_flag_is_refused(self):
        data, start, end, _ = resource_binary(duplicate_flag=True)
        with self.assertRaises(ValueError):
            self.patch_fixture(data, start, end)

    def test_unexpected_compression_is_refused(self):
        data, start, end, _ = resource_binary(compression=zipfile.ZIP_STORED)
        with self.assertRaises(ValueError):
            self.patch_fixture(data, start, end)


class MacAppTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(APP, "The macOS application preparation module has not been published.")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_receipt_rejects_another_version(self):
        build = self.root / "build"
        build.mkdir()
        (build / "receipt.json").write_text(json.dumps({"schema": 1, "version": "2.36.0"}))
        with self.assertRaises(ValueError):
            APP.read_receipt(build)

    def test_build_cannot_be_inside_the_source_app(self):
        source = self.root / "Antigravity.app"
        source.mkdir()
        with self.assertRaises(ValueError):
            APP.ensure_outside(source, source / "build")

    def test_install_target_cannot_be_the_backup(self):
        build = self.root / "build"
        build.mkdir()
        with self.assertRaises(ValueError):
            APP.ensure_outside(build, build / "original" / "Antigravity.app")

    def test_canonical_backup_alias_cannot_be_the_install_target(self):
        build = self.root / "build"
        (build / "original").mkdir(parents=True)
        original = fake_app(self.root / "external-original.app", "original")
        (build / "original/Antigravity.app").symlink_to(original, target_is_directory=True)
        patched = fake_app(build / "patched/Antigravity.app", "patched")
        receipt = {"original": APP.fingerprint(original), "patched": APP.fingerprint(patched)}
        with mock.patch.object(APP, "read_receipt", return_value=receipt), \
                mock.patch.object(APP, "verify_signature"), \
                mock.patch.object(APP, "replace_app") as replacement:
            with self.assertRaises(ValueError):
                APP.apply_build("install", build, original)
        replacement.assert_not_called()

    def test_build_cannot_be_inside_the_install_target(self):
        target = fake_app(self.root / "target.app", "original")
        build = target / "build"
        original = fake_app(build / "original/Antigravity.app", "original")
        patched = fake_app(build / "patched/Antigravity.app", "patched")
        receipt = {"original": APP.fingerprint(original), "patched": APP.fingerprint(patched)}
        with mock.patch.object(APP, "read_receipt", return_value=receipt), \
                mock.patch.object(APP, "verify_signature"), \
                mock.patch.object(APP, "replace_app") as replacement:
            with self.assertRaises(ValueError):
                APP.apply_build("install", build, target)
        replacement.assert_not_called()

    def test_restore_preserves_original_directory_metadata(self):
        build = self.root / "build"
        original = fake_app(build / "original/Antigravity.app", "original")
        original.chmod(0o711)
        original_mode = stat.S_IMODE(original.stat().st_mode)
        patched = fake_app(build / "patched/Antigravity.app", "patched")
        target = fake_app(self.root / "target.app", "patched")
        receipt = {"original": APP.fingerprint(original), "patched": APP.fingerprint(patched)}
        with mock.patch.object(APP, "read_receipt", return_value=receipt), \
                mock.patch.object(APP, "verify_signature"), \
                mock.patch.object(APP, "ensure_closed"), \
                mock.patch.object(APP, "copy_app", side_effect=lambda a, b: shutil.copytree(a, b)) as staged_copy, \
                mock.patch.object(APP, "copy_original_app", create=True,
                                  side_effect=lambda a, b: shutil.copytree(a, b)) as original_copy:
            APP.apply_build("restore", build, target)
        original_copy.assert_called_once()
        staged_copy.assert_not_called()
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), original_mode)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "chflags"), "BSD directory flags are unavailable")
    def test_original_copy_preserves_bsd_directory_flags(self):
        original = fake_app(self.root / "original.app", "original")
        original.chmod(0o711)
        os.chflags(original, 0x8000)
        copied = self.root / "copied.app"
        APP.copy_original_app(original, copied)
        self.assertEqual(copied.stat().st_flags, original.stat().st_flags)
        self.assertEqual(stat.S_IMODE(copied.stat().st_mode), stat.S_IMODE(original.stat().st_mode))

    def test_failed_rollback_reports_preserved_application_locations(self):
        target = fake_app(self.root / "target.app", "original")
        patched = fake_app(self.root / "patched.app", "patched")
        old, new = APP.fingerprint(target), APP.fingerprint(patched)
        real_rename = APP.os.rename

        def verify(path):
            if Path(path).resolve() == target.resolve() and APP.fingerprint(target) == new:
                raise RuntimeError("original installation verification failure")

        def rename(source, destination):
            if Path(source).name == "previous.app":
                raise PermissionError("rollback permission denied")
            return real_rename(source, destination)

        with mock.patch.object(APP, "copy_app", side_effect=lambda a, b: shutil.copytree(a, b)), \
                mock.patch.object(APP, "verify_signature", side_effect=verify), \
                mock.patch.object(APP, "ensure_closed"), \
                mock.patch.object(APP.os, "rename", side_effect=rename):
            with self.assertRaises(RuntimeError) as caught:
                APP.replace_app(patched, target, old, new)
        self.assertIn("previous.app", str(caught.exception))
        self.assertIn("failed.app", str(caught.exception))
        self.assertIn("original installation verification failure", str(caught.exception))
        self.assertIn("rollback permission denied", str(caught.exception))
        previous = next(self.root.glob(".antigravity-fork-*/previous.app"))
        self.assertEqual(APP.fingerprint(previous), old)

    def replace(self, source, target, old, new):
        with mock.patch.object(APP, "copy_app", side_effect=lambda a, b: shutil.copytree(a, b)), \
                mock.patch.object(APP, "verify_signature"), \
                mock.patch.object(APP, "ensure_closed"):
            return APP.replace_app(source, target, old, new)

    def test_unknown_target_is_refused_before_any_copy(self):
        original = fake_app(self.root / "original.app", "original")
        target = fake_app(self.root / "target.app", "updated")
        patched = fake_app(self.root / "patched.app", "patched")
        with mock.patch.object(APP, "copy_app") as copier, mock.patch.object(APP, "ensure_closed"):
            with self.assertRaises(ValueError):
                APP.replace_app(patched, target, APP.fingerprint(original), APP.fingerprint(patched))
        copier.assert_not_called()
        self.assertEqual((target / "user-note.txt").read_text(), "updated")

    def test_running_language_server_prevents_replacement(self):
        target = fake_app(self.root / "target.app", "original").resolve()
        patched = fake_app(self.root / "patched.app", "patched")
        processes = str(target / "Contents/Resources/bin/language_server") + "\n"
        with mock.patch.object(APP, "run", return_value=processes), \
                mock.patch.object(APP, "copy_app") as copier:
            with self.assertRaises(ValueError):
                APP.replace_app(patched, target, APP.fingerprint(target), APP.fingerprint(patched))
        copier.assert_not_called()

    def test_modified_sealed_resources_are_refused_before_copy(self):
        target = fake_app(self.root / "target.app", "original")
        patched = fake_app(self.root / "patched.app", "patched")
        old, new = APP.fingerprint(target), APP.fingerprint(patched)

        def verify(path):
            if Path(path).resolve() == target.resolve():
                raise RuntimeError("sealed resource was modified")

        with mock.patch.object(APP, "copy_app", side_effect=lambda a, b: shutil.copytree(a, b)) as copier, \
                mock.patch.object(APP, "verify_signature", side_effect=verify), \
                mock.patch.object(APP, "ensure_closed"):
            with self.assertRaises(RuntimeError):
                APP.replace_app(patched, target, old, new)
        copier.assert_not_called()

    def test_already_installed_checks_the_complete_signature(self):
        build = self.root / "build"
        original = fake_app(build / "original/Antigravity.app", "original")
        patched = fake_app(build / "patched/Antigravity.app", "patched")
        target = fake_app(self.root / "target.app", "patched")
        receipt = {"original": APP.fingerprint(original), "patched": APP.fingerprint(patched)}

        def verify(path, **kwargs):
            if Path(path).resolve() == target.resolve():
                raise RuntimeError("sealed resource was modified")

        with mock.patch.object(APP, "read_receipt", return_value=receipt), \
                mock.patch.object(APP, "verify_signature", side_effect=verify):
            with self.assertRaises(RuntimeError):
                APP.apply_build("install", build, target)

    def test_success_keeps_the_exact_previous_application(self):
        target = fake_app(self.root / "target.app", "original")
        patched = fake_app(self.root / "patched.app", "patched")
        old, new = APP.fingerprint(target), APP.fingerprint(patched)
        previous = self.replace(patched, target, old, new)
        self.assertEqual(APP.fingerprint(target), new)
        self.assertEqual(APP.fingerprint(previous), old)
        self.assertEqual((previous / "user-note.txt").read_text(), "original")

    def test_post_replacement_verification_failure_restores_original(self):
        target = fake_app(self.root / "target.app", "original")
        patched = fake_app(self.root / "patched.app", "patched")
        old, new = APP.fingerprint(target), APP.fingerprint(patched)

        def verify(path):
            if Path(path).resolve() == target.resolve() and APP.fingerprint(target) == new:
                raise RuntimeError("injected final signature failure")

        with mock.patch.object(APP, "copy_app", side_effect=lambda a, b: shutil.copytree(a, b)), \
                mock.patch.object(APP, "verify_signature", side_effect=verify), \
                mock.patch.object(APP, "ensure_closed"):
            with self.assertRaises(RuntimeError):
                APP.replace_app(patched, target, old, new)
        self.assertEqual(APP.fingerprint(target), old)
        self.assertEqual((target / "user-note.txt").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
