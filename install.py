"""One-shot installer for the SillyTavern local-search + LM Studio tweaks.

Does the five things that are otherwise five manual steps:

  1. installs the one Python dependency (ddgs)
  2. turns on server plugins in config.yaml
  3. links st-plugin into SillyTavern's plugins folder, so search starts and
     stops with SillyTavern
  4. points the Web Search extension at the local endpoint, and stops it firing
     on ordinary roleplay turns
  5. sets Prompt Post-Processing, which is what stops strict chat templates
     (Qwen3 and friends) rejecting every message with
     "System message must be at the beginning"

Run:
    python install.py                 # find SillyTavern automatically
    python install.py --sillytavern "C:\\path\\to\\SillyTavern"
    python install.py --dry-run       # print the plan, change nothing

Safe to re-run; every step checks before it writes.

SillyTavern must be CLOSED. It holds settings in the browser tab and writes
them back over the file, so anything changed here while it is open is lost.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PLUGIN_SRC = REPO / 'st-plugin'
PLUGIN_NAME = 'local-search'
SEARCH_URL = 'http://127.0.0.1:18888'

OK, NOPE, INFO = '[ ok ]', '[FAIL]', '[ -- ]'
changed: list[str] = []


def say(tag: str, msg: str) -> None:
    print(f'{tag} {msg}')


def die(msg: str) -> None:
    say(NOPE, msg)
    sys.exit(1)


# --------------------------------------------------------------------------
# finding SillyTavern
# --------------------------------------------------------------------------

def looks_like_sillytavern(path: Path) -> bool:
    return (path / 'server.js').is_file() and (path / 'config.yaml').is_file()


def find_sillytavern(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get('SILLYTAVERN_PATH'):
        candidates.append(Path(os.environ['SILLYTAVERN_PATH']))
    candidates += [
        REPO.parent / 'SillyTavern',
        Path.home() / 'SillyTavern',
        Path('C:/SillyTavern'),
    ]

    for c in candidates:
        if looks_like_sillytavern(c.expanduser()):
            return c.expanduser().resolve()

    if explicit:
        die(f'{explicit} does not look like a SillyTavern install '
            '(no server.js + config.yaml next to each other).')

    print('Could not find SillyTavern automatically.')
    print('Looked in:')
    for c in candidates:
        print(f'    {c}')
    entered = input('\nFull path to your SillyTavern folder: ').strip().strip('"')
    if not entered:
        die('No path given.')
    resolved = Path(entered).expanduser()
    if not looks_like_sillytavern(resolved):
        die(f'{resolved} does not contain server.js and config.yaml.')
    return resolved.resolve()


def config_port(config: Path) -> int:
    match = re.search(r'^port:\s*(\d+)', config.read_text(encoding='utf-8'), re.M)
    return int(match.group(1)) if match else 8000


def is_running(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex(('127.0.0.1', port)) == 0


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------

def step_dependency(dry: bool) -> None:
    probe = subprocess.run([sys.executable, '-c', 'import ddgs'], capture_output=True)
    if probe.returncode == 0:
        say(OK, 'ddgs already installed')
        return
    if dry:
        say(INFO, f'would run: {sys.executable} -m pip install ddgs')
        return
    say(INFO, 'installing ddgs...')
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'ddgs'])
    if result.returncode != 0:
        die('pip install ddgs failed. Install it yourself, then re-run.')
    say(OK, 'ddgs installed')
    changed.append('installed ddgs')


def step_enable_plugins(config: Path, dry: bool) -> None:
    text = config.read_text(encoding='utf-8')
    if re.search(r'^enableServerPlugins:\s*true\s*$', text, re.M):
        say(OK, 'enableServerPlugins already true')
        return
    if re.search(r'^enableServerPlugins:', text, re.M):
        new = re.sub(r'^enableServerPlugins:.*$', 'enableServerPlugins: true', text, count=1, flags=re.M)
        what = 'set enableServerPlugins: true'
    else:
        new = text.rstrip('\n') + '\nenableServerPlugins: true\n'
        what = 'added enableServerPlugins: true'
    if dry:
        say(INFO, f'would {what} in config.yaml')
        return
    config.write_text(new, encoding='utf-8')
    say(OK, f'{what} in config.yaml')
    changed.append(what)


def step_link_plugin(st: Path, dry: bool) -> None:
    link = st / 'plugins' / PLUGIN_NAME
    if link.exists():
        try:
            target = Path(os.path.realpath(link))
        except OSError:
            target = link
        if target == PLUGIN_SRC:
            say(OK, f'plugin already linked ({link})')
            return
        say(NOPE, f'{link} exists but points at {target}. Remove it and re-run.')
        sys.exit(1)
    if dry:
        say(INFO, f'would link {link}  ->  {PLUGIN_SRC}')
        return

    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        # Junction: no admin rights needed, unlike a real symlink.
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(PLUGIN_SRC)],
                                capture_output=True, text=True)
        made = result.returncode == 0
        detail = (result.stderr or result.stdout).strip()
    else:
        try:
            os.symlink(PLUGIN_SRC, link, target_is_directory=True)
            made, detail = True, ''
        except OSError as exc:
            made, detail = False, str(exc)

    if not made:
        say(NOPE, f'could not link the plugin: {detail}')
        say(INFO, 'copying it instead (re-run this installer after you pull updates)')
        shutil.copytree(PLUGIN_SRC, link)
    say(OK, f'plugin installed at {link}')
    changed.append('installed the server plugin')


def step_settings(st: Path, dry: bool) -> None:
    files = sorted(st.glob('data/*/settings.json'))
    if not files:
        say(NOPE, 'no data/<user>/settings.json yet - start SillyTavern once, then re-run.')
        return

    for path in files:
        user = path.parent.name
        settings = json.loads(path.read_text(encoding='utf-8'))
        edits: list[str] = []

        # Web search -> the local endpoint, and only when actually asked.
        web = settings.setdefault('extension_settings', {}).setdefault('websearch', {})
        for key, value, why in [
            ('source', 'searxng', 'source = searxng'),
            ('searxng_url', SEARCH_URL, f'searxng_url = {SEARCH_URL}'),
            ('use_backticks', True, 'use_backticks = true'),
            ('use_trigger_phrases', False, 'use_trigger_phrases = false (52 phrases matched normal roleplay)'),
        ]:
            if web.get(key) != value:
                web[key] = value
                edits.append(why)

        # Prompt post-processing, but only where it applies: this field is sent
        # on every source, so setting it for a hosted API would change that
        # API's prompt too.
        oai = settings.setdefault('oai_settings', {})
        if oai.get('chat_completion_source') == 'custom':
            if oai.get('custom_prompt_post_processing') != 'semi_tools':
                oai['custom_prompt_post_processing'] = 'semi_tools'
                edits.append("custom_prompt_post_processing = semi_tools")
        elif oai.get('custom_prompt_post_processing') in (None, ''):
            say(INFO, f'{user}: not on Custom (OpenAI-compatible), so Prompt Post-Processing '
                      'was left alone. Set it to "Semi-strict, tools" when you switch.')

        if not edits:
            say(OK, f'{user}: settings already correct')
            continue
        if dry:
            for e in edits:
                say(INFO, f'would set {user}: {e}')
            continue

        backup = path.with_suffix(f'.json.bak-install')
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(json.dumps(settings, indent=4, ensure_ascii=False), encoding='utf-8')
        for e in edits:
            say(OK, f'{user}: {e}')
        changed.append(f'{user}: {len(edits)} setting(s)')


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sillytavern', help='path to the SillyTavern folder')
    ap.add_argument('--dry-run', action='store_true', help='print the plan, change nothing')
    args = ap.parse_args()

    if not PLUGIN_SRC.is_dir():
        die(f'{PLUGIN_SRC} is missing. Run this from inside a full checkout of the repo.')

    st = find_sillytavern(args.sillytavern)
    say(OK, f'SillyTavern: {st}')

    port = config_port(st / 'config.yaml')
    if is_running(port) and not args.dry_run:
        die(f'SillyTavern is running on port {port}. Close it (and its browser tab) first - '
            'an open tab writes its own copy of the settings back over this one.')

    print()
    step_dependency(args.dry_run)
    step_enable_plugins(st / 'config.yaml', args.dry_run)
    step_link_plugin(st, args.dry_run)
    step_settings(st, args.dry_run)

    print()
    if args.dry_run:
        say(INFO, 'dry run: nothing was changed')
    elif changed:
        say(OK, 'done: ' + '; '.join(changed))
    else:
        say(OK, 'everything was already set up')

    print('\nNext: start SillyTavern. You should see this in its console:')
    print(f'    [local-search] started on {SEARCH_URL}')
    print('Then search the web from a chat by wrapping the query in backticks:')
    print('    `current version of rust`')
    return 0


if __name__ == '__main__':
    sys.exit(main())
