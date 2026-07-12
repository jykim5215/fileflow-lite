from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import shutil

from fileflow_lite.core.executor import execute_plan, undo_latest
from fileflow_lite.core.flatten import plan_flatten
from fileflow_lite.core.rename import plan_sequential_rename
from fileflow_lite.core.safety import SafetyError
from fileflow_lite.integration.updater import _validate_update_url


class TempWorkspace(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.local_app_data = self.root / "appdata"
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.local_app_data)})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    def write(self, relative: str, content: str = "data") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class FlattenTests(TempWorkspace):
    def test_collision_number_preview(self) -> None:
        self.write("source/one/photo.jpg", "one")
        self.write("source/two/photo.jpg", "two")
        plan = plan_flatten(self.root / "source", self.root / "target")
        names = sorted(Path(item.destination).name for item in plan.items)
        self.assertEqual(names, ["photo (2).jpg", "photo.jpg"])
        self.assertTrue(plan.warnings)

    def test_collision_folder_prefix(self) -> None:
        self.write("source/one/photo.jpg", "one")
        self.write("source/two/photo.jpg", "two")
        plan = plan_flatten(
            self.root / "source",
            self.root / "target",
            collision_policy="folder_prefix",
        )
        names = {Path(item.destination).name for item in plan.items}
        self.assertEqual(len(names), 2)
        self.assertTrue(any(name.startswith(("one_", "two_")) for name in names))

    def test_extension_filter(self) -> None:
        self.write("source/a/image.jpg")
        self.write("source/a/readme.txt")
        plan = plan_flatten(
            self.root / "source", self.root / "target", extensions={"jpg"}
        )
        self.assertEqual([Path(item.source).suffix for item in plan.items], [".jpg"])
        self.assertEqual(len(plan.excluded), 1)

    def test_target_inside_source_is_blocked(self) -> None:
        (self.root / "source").mkdir()
        with self.assertRaises(SafetyError):
            plan_flatten(self.root / "source", self.root / "source" / "target")

    def test_copy_and_undo(self) -> None:
        source = self.write("source/a/report.txt", "hello")
        target = self.root / "target"
        plan = plan_flatten(self.root / "source", target)
        log_path = execute_plan(plan)
        copied = target / "report.txt"
        self.assertEqual(copied.read_text(encoding="utf-8"), "hello")
        self.assertTrue(source.exists())
        self.assertEqual(json.loads(log_path.read_text(encoding="utf-8"))["status"], "success")
        self.assertEqual(undo_latest(), 1)
        self.assertFalse(copied.exists())
        self.assertTrue(source.exists())

    def test_move_delete_empty_and_undo(self) -> None:
        source = self.write("source/a/b/report.txt", "hello")
        target = self.root / "target"
        plan = plan_flatten(
            self.root / "source", target, mode="move", delete_empty=True
        )
        execute_plan(plan)
        self.assertFalse(source.exists())
        self.assertFalse(self.root.joinpath("source/a/b").exists())
        undo_latest()
        self.assertEqual(source.read_text(encoding="utf-8"), "hello")

    def test_changed_source_blocks_apply(self) -> None:
        source = self.write("source/a/report.txt", "before")
        plan = plan_flatten(self.root / "source", self.root / "target")
        source.write_text("changed and longer", encoding="utf-8")
        with self.assertRaises(SafetyError):
            execute_plan(plan)

    def test_changed_copy_blocks_undo(self) -> None:
        self.write("source/a/report.txt", "before")
        target = self.root / "target"
        execute_plan(plan_flatten(self.root / "source", target))
        (target / "report.txt").write_text("user edit", encoding="utf-8")
        with self.assertRaises(SafetyError):
            undo_latest()

    def test_partial_copy_failure_rolls_back(self) -> None:
        self.write("source/a/one.txt", "one")
        self.write("source/b/two.txt", "two")
        target = self.root / "target"
        plan = plan_flatten(self.root / "source", target)
        real_copy = shutil.copy2
        calls = 0

        def flaky_copy(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated copy failure")
            return real_copy(source, destination)

        with patch("fileflow_lite.core.executor.shutil.copy2", side_effect=flaky_copy):
            with self.assertRaises(OSError):
                execute_plan(plan)
        self.assertTrue((self.root / "source/a/one.txt").exists())
        self.assertTrue((self.root / "source/b/two.txt").exists())
        self.assertFalse(target.exists())

    def test_undo_precheck_prevents_partial_change(self) -> None:
        self.write("source/a/one.txt", "one")
        self.write("source/b/two.txt", "two")
        target = self.root / "target"
        execute_plan(plan_flatten(self.root / "source", target))
        (target / "one.txt").write_text("edited", encoding="utf-8")
        with self.assertRaises(SafetyError):
            undo_latest()
        self.assertTrue((target / "one.txt").exists())
        self.assertTrue((target / "two.txt").exists())


class RenameTests(TempWorkspace):
    def test_padding_sort_and_extension(self) -> None:
        b = self.write("files/b.png", "bbbb")
        a = self.write("files/a.txt", "a")
        plan = plan_sequential_rename(
            [b, a], prefix="item-", padding=3, start=7, sort_by="name"
        )
        self.assertEqual(
            [Path(item.destination).name for item in plan.items],
            ["item-007.txt", "item-008.png"],
        )

    def test_existing_destination_collision(self) -> None:
        source = self.write("files/a.txt")
        self.write("files/01.txt", "occupied")
        with self.assertRaises(SafetyError):
            plan_sequential_rename([source], padding=2)

    def test_rename_and_undo(self) -> None:
        a = self.write("files/a.txt", "alpha")
        b = self.write("files/b.txt", "beta")
        plan = plan_sequential_rename([b, a], prefix="doc-", padding=2)
        execute_plan(plan)
        self.assertEqual((self.root / "files/doc-01.txt").read_text(), "alpha")
        self.assertEqual((self.root / "files/doc-02.txt").read_text(), "beta")
        self.assertEqual(undo_latest(), 2)
        self.assertEqual(a.read_text(), "alpha")
        self.assertEqual(b.read_text(), "beta")

    def test_name_swap_uses_two_phase(self) -> None:
        one = self.write("files/1.txt", "one")
        two = self.write("files/2.txt", "two")
        plan = plan_sequential_rename(
            [two, one], padding=1, start=1, sort_by="name", descending=True
        )
        execute_plan(plan)
        self.assertEqual((self.root / "files/1.txt").read_text(), "two")
        self.assertEqual((self.root / "files/2.txt").read_text(), "one")
        undo_latest()
        self.assertEqual(one.read_text(), "one")
        self.assertEqual(two.read_text(), "two")

    def test_invalid_prefix_is_blocked(self) -> None:
        source = self.write("files/a.txt")
        with self.assertRaises(SafetyError):
            plan_sequential_rename([source], prefix="bad/name")


class UpdateSafetyTests(unittest.TestCase):
    def test_allows_expected_github_https_url(self) -> None:
        url = "https://github.com/jykim5215/fileflow-lite/releases/download/v1/a.zip"
        self.assertEqual(_validate_update_url(url), url)

    def test_blocks_non_https_or_untrusted_host(self) -> None:
        for url in (
            "http://github.com/example",
            "https://evil.example/update.zip",
            "file:///C:/update.zip",
            "https://github.com.evil.example/update.zip",
        ):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                _validate_update_url(url)


if __name__ == "__main__":
    unittest.main()
