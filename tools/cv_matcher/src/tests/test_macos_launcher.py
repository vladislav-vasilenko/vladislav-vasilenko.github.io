import plistlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import install_macos_app as installer,service

class Launcher(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name)
    def test_applescript_holds_paths_only_and_quotes_them(self):
        script=installer.launcher('/a b/py','/x"y/service.py')
        self.assertIn('quoted form of "/a b/py"',script);self.assertIn('/x\\"y/service.py',script);self.assertNotIn('token',script.lower())
    def test_installer_refuses_to_replace_another_app(self):
        app=self.dir/'Other.app';(app/'Contents').mkdir(parents=True)
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.example.other'}))
        with self.assertRaises(RuntimeError):installer.check_replaceable(app)
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':installer.BUNDLE_ID}))
        installer.check_replaceable(app)
    def test_dock_entry_is_recognised_with_a_cyrillic_path(self):
        app=Path('/Users/me/Applications/Рабочий поиск.app')
        self.assertTrue(installer.in_dock([{'tile-data':{'file-data':{'_CFURLString':app.as_uri()+'/'}}}],app))
        self.assertFalse(installer.in_dock([{'tile-data':{'file-data':{'_CFURLString':'file:///Applications/Other.app/'}}}],app))
    def test_stop_never_signals_a_process_that_is_not_this_service(self):
        (self.dir/'server.pid').write_text('4242')
        foreign=type('R',(),{'stdout':'/usr/bin/python /other/resume_import_server.py\n'})()
        with patch.object(service,'STATE',self.dir),patch.object(service,'healthy',return_value=False),patch('subprocess.run',return_value=foreign),patch('os.kill') as kill:
            self.assertIsNone(service.owned_pid());service.stop()
        kill.assert_not_called()
    def test_health_is_false_without_a_token_or_for_another_service(self):
        with patch.object(service,'TOKEN',self.dir/'missing.txt'):self.assertFalse(service.healthy())
        with patch.object(service,'request',return_value={'service':'other'}):self.assertFalse(service.healthy())
