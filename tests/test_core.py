import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from unlocked_tv.model import Model
from unlocked_tv.store import Store, validate_settings


class FakePlayer:
    active = False
    kind = None
    title = ""

    def stop(self):
        self.active = False


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data")
        self.model = Model(self.store, FakePlayer())

    def tearDown(self):
        self.temp.cleanup()

    def package(self, app_id="test-app", entries=None):
        path = self.root / "test.zip"
        manifest = {"schema_version": 1, "id": app_id, "name": "Test App", "type": "native", "runtime": "python3", "entry": "main.py"}
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("main.py", "raise SystemExit(0)\n")
            for name, value in (entries or {}).items():
                archive.writestr(name, value)
        return path

    def test_preferences_survive_restart_and_independent_writers(self):
        other = Store(self.store.root)
        self.store.save(theme="Forest")
        other.save(volume=25)
        saved = Store(self.store.root).settings
        self.assertEqual(saved["theme"], "Forest")
        self.assertEqual(saved["volume"], 25)

    def test_invalid_settings_are_preserved_before_recovery(self):
        self.store.path.write_text('{"broken":')
        recovered = Store(self.store.root)
        self.assertEqual(recovered.settings["theme"], "Midnight")
        backups = list((self.store.root / "backups").glob("settings-invalid-*.json"))
        self.assertEqual(backups[0].read_text(), '{"broken":')
        self.assertTrue(recovered.warnings)

    def test_failed_package_does_not_replace_working_app(self):
        self.store.install(self.package())
        original = (self.store.root / "apps/test-app/main.py").read_bytes()
        with self.assertRaises(ValueError):
            self.store.install(self.package(entries={"../escape.py": "bad"}))
        self.assertEqual((self.store.root / "apps/test-app/main.py").read_bytes(), original)
        self.assertFalse((self.store.root / "apps/escape.py").exists())

    def test_packages_reject_symlinks_and_reserved_ids(self):
        with self.assertRaises(ValueError):
            self.store.install(self.package("videos"))
        path = self.package()
        with zipfile.ZipFile(path, "a") as archive:
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120777 << 16)
            archive.writestr(info, "/etc/passwd")
        with self.assertRaises(ValueError):
            self.store.install(path)

    def test_app_remove_cleans_shortcuts_and_preserves_backup(self):
        self.store.install(self.package())
        self.store.save(shortcuts=["test-app", None, None, None, None, None])
        self.store.uninstall("test-app")
        self.assertNotIn("test-app", [app["id"] for app in self.store.apps()])
        self.assertIsNone(self.store.settings["shortcuts"][0])
        self.assertTrue(list((self.store.root / "backups").glob("removed-test-app-*")))

    def test_remote_navigation_reorder_and_shortcut_persist(self):
        for _ in range(3):
            self.model.action("right")
        self.model.action("select")
        self.assertEqual(self.model.screen, "settings")
        self.model.action("right")
        self.assertEqual(self.store.settings["theme"], "Mist")
        self.model.action("down")
        self.model.action("select")
        self.model.action("select")
        self.model.action("down")
        self.model.action("select")
        self.assertEqual(self.store.settings["home_order"][:2], ["photos", "videos"])
        self.model.action("home")
        self.model.action("shortcut_3")
        self.assertEqual(self.model.screen, "clock")
        self.model.action("home")
        self.assertEqual(self.model.screen, "home")

    def test_media_scan_skips_symlinks_and_lists_streams(self):
        media = self.store.root / "media"
        (media / "sample.mp4").write_bytes(b"fixture")
        (media / "alias.mp4").symlink_to(media / "sample.mp4")
        self.store.save(streams=[{"name": "Live", "url": "https://example.org/live.m3u8"}])
        self.assertEqual(len(self.store.media("videos")), 2)

    def test_config_rejects_executable_stream_scheme(self):
        value = copy.deepcopy(self.store.settings)
        value["streams"] = [{"name": "Bad", "url": "exec://command"}]
        with self.assertRaises(ValueError):
            validate_settings(value)


if __name__ == "__main__":
    unittest.main()
