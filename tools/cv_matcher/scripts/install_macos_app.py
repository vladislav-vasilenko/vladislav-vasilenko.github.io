#!/usr/bin/env python3
"""Build the AppleScript app and add one entry for it to the user's Dock.

The app holds only the path to scripts/service.py, never the token or other secrets.
Run again after moving the project. Usage: install_macos_app.py [--no-dock] [--app PATH]
"""
import argparse
import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

PROJECT = Path(__file__).resolve().parent.parent
NAME = 'Рабочий поиск'
APP = Path.home() / 'Applications' / (NAME + '.app')
BUNDLE_ID = 'local.career.workspace'


def applescript_string(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def launcher(python, service):
    return f'''on run
    try
        set serviceURL to do shell script (quoted form of {applescript_string(python)} & " " & quoted form of {applescript_string(service)} & " url")
        open location serviceURL
    on error messageText
        display dialog messageText with title {applescript_string(NAME)} buttons {{"OK"}} default button "OK" with icon caution
    end try
end run
'''


def check_replaceable(app):
    """Never overwrite an app that isn't ours."""
    if not app.exists():
        return
    info_path = app / 'Contents/Info.plist'
    info = plistlib.loads(info_path.read_bytes()) if info_path.exists() else {}
    if info.get('CFBundleIdentifier') != BUNDLE_ID:
        raise RuntimeError('Уже есть другое приложение ' + str(app) + ', оно сохранено.')


def make_icon(directory):
    """Returns the .icns path, or None if the tools are missing: the app works without a custom icon."""
    source = directory / 'icon.png'
    iconset = directory / 'icon.iconset'
    try:
        subprocess.run(['/usr/bin/swift', str(PROJECT / 'scripts/make_icon.swift'), str(source)], check=True, capture_output=True)
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale, suffix in ((1, ''), (2, '@2x')):
                target = iconset / f'icon_{size}x{size}{suffix}.png'
                pixels = str(size * scale)
                subprocess.run(['/usr/bin/sips', '-z', pixels, pixels, str(source), '--out', str(target)], check=True, capture_output=True)
        result = directory / 'icon.icns'
        subprocess.run(['/usr/bin/iconutil', '-c', 'icns', str(iconset), '-o', str(result)], check=True, capture_output=True)
        return result
    except (OSError, subprocess.CalledProcessError):
        print('Значок не собран; приложение будет со стандартным значком.', file=sys.stderr)
        return None


def build(app):
    check_replaceable(app)
    app.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='career-app-') as temporary:
        temporary = Path(temporary)
        source = temporary / 'launcher.applescript'
        source.write_text(launcher(PROJECT / '.venv/bin/python', PROJECT / 'scripts/service.py'), encoding='utf-8')
        built = temporary / 'app.app'
        subprocess.run(['/usr/bin/osacompile', '-o', str(built), str(source)], check=True, capture_output=True)
        info_path = built / 'Contents/Info.plist'
        info = plistlib.loads(info_path.read_bytes())
        info.update(CFBundleIdentifier=BUNDLE_ID, CFBundleName=NAME, CFBundleDisplayName=NAME,
                    CFBundleShortVersionString='0.1.0', NSHighResolutionCapable=True)
        info_path.write_bytes(plistlib.dumps(info))
        icon = make_icon(temporary)
        if icon:
            shutil.copyfile(icon, built / 'Contents/Resources/applet.icns')
        if app.exists():
            shutil.rmtree(app)
        shutil.copytree(built, app)
    subprocess.run(['/usr/bin/codesign', '--force', '--deep', '--sign', '-', str(app)], check=True, capture_output=True)


def in_dock(entries, app):
    """True when a Dock entry already points at this app."""
    for entry in entries:
        url = entry.get('tile-data', {}).get('file-data', {}).get('_CFURLString', '')
        if unquote(urlparse(url).path).rstrip('/') == str(app):
            return True
    return False


def add_to_dock(app):
    settings = subprocess.run(['/usr/bin/defaults', 'export', 'com.apple.dock', '-'], check=True, capture_output=True).stdout
    if in_dock(plistlib.loads(settings).get('persistent-apps', []), app):
        return 'already_present'
    entry = {'tile-type': 'file-tile', 'tile-data': {'file-data': {'_CFURLString': app.as_uri() + '/', '_CFURLStringType': 15},
                                                      'file-label': NAME, 'bundle-identifier': BUNDLE_ID}}
    xml = plistlib.dumps(entry, fmt=plistlib.FMT_XML).decode()
    subprocess.run(['/usr/bin/defaults', 'write', 'com.apple.dock', 'persistent-apps', '-array-add', xml], check=True)
    subprocess.run(['/usr/bin/killall', 'Dock'], capture_output=True)
    return 'added'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-dock', action='store_true', help='Build the app only')
    parser.add_argument('--app', type=Path, default=APP, help='Where to build the app')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('Установщик предназначен для macOS.')
    try:
        build(args.app)
    except RuntimeError as error:
        raise SystemExit(str(error))
    print(json.dumps({'application': str(args.app), 'dock': 'skipped' if args.no_dock else add_to_dock(args.app)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
