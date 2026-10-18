"""Local state and configuration shared by the hook and runner."""
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

DEFAULTS = dict(session_soft=80, session_hard=95, weekly_soft=97, weekly_hard=98)


def git(project, *args, input_data=None, raw=False):
    try:
        stdin = {'input': input_data} if input_data is not None else {'stdin': subprocess.DEVNULL}
        r = subprocess.run(['git', '-C', str(project), *args], capture_output=True, **stdin,
                           text=True, encoding='utf-8', errors='replace', timeout=20)
        return r.returncode, r.stdout if raw else r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ''


def state_dir(project):
    path = Path(project) / '.codex-quota'
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError('Unsafe .codex-quota directory')
    if path.exists() and not path.is_dir():
        raise ValueError('.codex-quota is not a directory')
    return path


def read_json(path):
    if path.is_symlink():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.quota-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def config(project):
    saved = read_json(state_dir(project) / 'config.json')
    result = dict(DEFAULTS)
    for key in DEFAULTS:
        for value in (saved.get(key), os.environ.get('CODEX_QUOTA_' + key.upper())):
            try:
                number = float(value)
                if math.isfinite(number) and 0 < number <= 100:
                    result[key] = number
            except (TypeError, ValueError):
                pass
    result['hard_abort'] = os.environ.get('CODEX_QUOTA_HARD_ABORT', '').lower() in ('1', 'true', 'yes')
    result['language'] = os.environ.get('CODEX_QUOTA_LANG', saved.get('language', 'en'))
    return result


def choose_stop(windows, cfg, soft_allowed=True, now=None):
    now = time.time() if now is None else now
    triggered = []
    hard = False
    for window in windows:
        kind = 'weekly' if window['minutes'] >= 10080 else 'session'
        if window['resets_at'] <= now:
            continue
        is_hard = window['pct'] >= cfg[kind + '_hard']
        if is_hard or window['pct'] >= cfg[kind + '_soft']:
            triggered.append(window)
            hard = hard or is_hard
    if not triggered or (not hard and not soft_allowed):
        return None
    return dict(mode='hard' if hard else 'soft', windows=triggered,
                resets_at=max(w['resets_at'] for w in triggered), stopped_at=now)


MESSAGES = {
    'en': {'stop': 'Quota threshold reached; reset: {reset}.',
           'waiting': 'Waiting for quota reset: {reset}.', 'resume': 'Resuming the saved session.',
           'done': 'Task completed.', 'failed': 'Run stopped after errors; saved progress is available.'},
    'tr': {'stop': 'Kota eşiğine ulaşıldı; yenilenme: {reset}.',
           'waiting': 'Kota yenilenmesi bekleniyor: {reset}.', 'resume': 'Kayıtlı oturum sürdürülüyor.',
           'done': 'Görev tamamlandı.', 'failed': 'Çalışma hatalar nedeniyle durdu; kayıtlı ilerleme kullanılabilir.'},
}


def message(key, language='en', **kwargs):
    return MESSAGES.get(language, MESSAGES['en'])[key].format(**kwargs)
