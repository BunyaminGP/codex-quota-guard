"""Codex PostToolUse checkpoint feedback and Stop completion guard."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from common import choose_stop, config, git, message, read_json, state_dir, write_json
from notify import notify
from usage import get_usage


def tracked(project, name):
    return git(project, 'ls-files', '--error-unmatch', '.codex-quota/' + name)[0] == 0


def plan_state(project, previous, plan, session_id):
    tasks = [dict(content=p['step'], status=p['status']) for p in plan
             if isinstance(p, dict) and isinstance(p.get('step'), str)
             and p.get('status') in ('pending', 'in_progress', 'completed')]
    active = next((p['content'] for p in tasks if p['status'] == 'in_progress'), None)
    old = previous.get('in_progress') or {}
    checkpoint = old if old.get('content') == active else None
    if active and not checkpoint:
        code, head = git(project, 'rev-parse', 'HEAD')
        status, changes = git(project, 'status', '--porcelain', '--untracked-files=all',
                              '--', '.', ':(exclude).codex-quota')
        checkpoint = dict(content=active, commit=head if code == 0 else None,
                          clean=code == 0 and status == 0 and not changes)
    return dict(session_id=session_id, todos=tasks, in_progress=checkpoint if active else None)


def revert_item(project, state):
    active = state.get('in_progress') or {}
    if not active.get('clean') or not active.get('commit') or tracked(project, 'todos_state.json'):
        return False
    code, head = git(project, 'rev-parse', 'HEAD')
    if code or head != active['commit']:
        return False
    code, changed = git(project, 'diff', '--relative', '--name-only', '-z', 'HEAD', raw=True)
    other_code, untracked = git(project, 'ls-files', '--others', '--exclude-standard', '-z', raw=True)
    if code or other_code:
        return False
    paths = sorted({p for p in (changed + untracked).split('\0')
                    if p and p != '.codex-quota' and not p.startswith('.codex-quota/')})
    if not paths:
        return False
    _, before = git(project, 'rev-parse', '--verify', 'refs/stash')
    code, _ = git(project, 'stash', 'push', '-u', '-m', 'codex-quota-guard checkpoint',
                  '--pathspec-from-file=-', '--pathspec-file-nul',
                  input_data=''.join(':(literal)' + p + '\0' for p in paths))
    _, after = git(project, 'rev-parse', '--verify', 'refs/stash')
    if code or not after or before == after:
        return False
    for task in state.get('todos', []):
        if task.get('content') == active['content']:
            task['status'] = 'pending'
    state['in_progress'] = None
    return True


def feedback(marker, event='PostToolUse'):
    reset = datetime.fromtimestamp(marker['resets_at'], timezone.utc).isoformat()
    instruction = (
        f"Quota {marker['mode']} threshold reached; reset {reset}. "
        "Do not start another task. Save completed work, pending steps and resume context to "
        ".codex-quota/progress.md, then END THE TURN. Preserve existing user changes. "
        "Commit only if the user's task authorizes commits. Do not write CODEX_QUOTA_DONE "
        "unless the entire requested task is complete."
    )
    if marker.get('reverted'):
        instruction += ' The current item was stashed successfully; it is pending and must be redone after reset.'
    return dict(decision='block', reason=instruction, hookSpecificOutput=dict(
        hookEventName=event, additionalContext=instruction)) if event == 'PostToolUse' else dict(
            decision='block', reason=instruction)


def handle(payload):
    project = Path(payload.get('cwd') or os.getcwd())
    folder = state_dir(project)
    session_id = payload.get('session_id')
    if not session_id:
        return {}
    run = read_json(folder / 'run.json')
    run_id = os.environ.get('CODEX_QUOTA_RUN_ID')
    if (folder / 'runner.lock').exists() and run_id != run.get('run_id'):
        return {}
    if run_id and run.get('thread_id') not in (None, session_id):
        return {}
    # A cloned runtime file must never claim a checkpoint or stop for this session.
    for name in ('todos_state.json', 'STOP.json'):
        if tracked(project, name):
            return {}
    marker = read_json(folder / 'STOP.json')
    same_marker = marker.get('session_id') == session_id and marker.get('run_id') == run_id
    event = payload.get('hook_event_name', 'PostToolUse')
    if event == 'Stop':
        if same_marker and marker.get('resets_at', 0) > time.time():
            # One continuation gives the model a chance to persist its checkpoint.
            progress = folder / 'progress.md'
            updated = (not progress.is_symlink() and progress.is_file()
                       and progress.stat().st_mtime_ns != marker.get('progress_mtime'))
            if not payload.get('stop_hook_active') and not updated:
                return feedback(marker, 'Stop')
        return {}
    if event != 'PostToolUse':
        return {}
    if same_marker and marker.get('resets_at', 0) > time.time():
        return {}  # allow checkpoint writes after the initial instruction
    previous = read_json(folder / 'todos_state.json')
    if previous.get('session_id') != session_id:
        previous = {}
    state = previous
    tool = payload.get('tool_name', '').split('.')[-1]
    soft_allowed = not previous.get('in_progress')
    args = payload.get('tool_input') or {}
    if tool == 'update_plan' and isinstance(args, dict) and isinstance(args.get('plan'), list):
        state = plan_state(project, previous, args['plan'], session_id)
        soft_allowed = state.get('in_progress') != previous.get('in_progress') or not state.get('in_progress')
        write_json(folder / 'todos_state.json', state)
    cfg = config(project)
    marker = choose_stop(get_usage(), cfg, soft_allowed=soft_allowed)
    if not marker:
        return {}
    marker.update(session_id=session_id, run_id=run_id, reverted=False)
    progress = folder / 'progress.md'
    marker['progress_mtime'] = progress.stat().st_mtime_ns if progress.is_file() and not progress.is_symlink() else None
    if marker['mode'] == 'hard' and cfg['hard_abort']:
        marker['reverted'] = revert_item(project, state)
        if marker['reverted']:
            write_json(folder / 'todos_state.json', state)
    write_json(folder / 'STOP.json', marker)
    reset = datetime.fromtimestamp(marker['resets_at'], timezone.utc).isoformat()
    text = message('stop', cfg['language'], reset=reset)
    notify(text)
    result = feedback(marker)
    result['systemMessage'] = text
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError('Invalid hook input')
        # Parallel PostToolUse hooks must not overwrite each other's checkpoint.
        folder = state_dir(Path(payload.get('cwd') or os.getcwd()))
        folder.mkdir(exist_ok=True)
        lock = folder / 'hook.lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            print('{}')
            return
        try:
            os.close(fd)
            result = handle(payload)
        finally:
            lock.unlink(missing_ok=True)
        print(json.dumps(result, ensure_ascii=True))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        print('{}')  # quota/config/service errors must not break an ordinary Codex session


if __name__ == '__main__':
    main()
