"""Trusted host wrapper. Never import target files or execute target commands on host."""
import argparse
import ast
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

LIMIT = 262144


def bounded_run(command, *, timeout=180, cwd=None):
    output = bytearray()
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env={k: v for k, v in os.environ.items() if k not in
                                    ('GITHUB_TOKEN', 'GH_TOKEN', 'ACTIONS_RUNTIME_TOKEN', 'JULES_API_KEY')})
    def read():
        while chunk := process.stdout.read(4096):
            output.extend(chunk[:max(0, LIMIT - len(output))])
            if len(output) >= LIMIT:
                process.kill()
                break
    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait(timeout=10)
    thread.join(timeout=10)
    process.stdout.close()
    return (124 if timed_out else process.returncode), output.decode('utf-8', errors='replace')


def relative(path):
    if (not isinstance(path, str) or not path or any(x in path for x in ('\\', ':', '\n', '\r', '\x00')) or
            path.startswith('/') or any(p in ('', '.', '..') for p in path.split('/'))):
        raise ValueError('Unsafe target path')
    return str(PurePosixPath(path))


def inspect_tests(source):
    tree = ast.parse(source)
    if any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Subscript) and
           isinstance(t.value, ast.Attribute) and t.value.attr == 'modules' for t in n.targets)
           for n in ast.walk(tree)):
        raise ValueError('Module substitution requires owner review')
    if any(isinstance(n, ast.ExceptHandler) and any(isinstance(v, ast.Pass) for v in n.body)
           for n in ast.walk(tree)):
        raise ValueError('Swallowed exceptions are not behavioral proof')
    selectors = []
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for method in cls.body:
            if not isinstance(method, ast.FunctionDef) or not method.name.startswith('test_'):
                continue
            assertions = [n for n in ast.walk(method) if isinstance(n, ast.Call) and
                          isinstance(n.func, ast.Attribute) and n.func.attr.startswith('assert')]
            if not assertions or not any(any(not isinstance(arg, ast.Constant) for arg in a.args) for a in assertions):
                raise ValueError('Every selected test needs an observable behavioral assertion')
            if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and
                   n.func.attr in ('skip', 'skipIf', 'skipUnless', 'expectedFailure') for n in ast.walk(method)):
                raise ValueError('Skipped tests require owner review')
            selectors.append(cls.name + '.' + method.name)
    if not selectors:
        raise ValueError('No unittest behavioral cases found')
    return selectors


def read_phase_output(output, code):
    empty = {'test_count': 0, 'test_ids': [], 'skipped_count': 0, 'errors': 1, 'failures': 0}
    lines = [line[len('QUALITY_RESULT='):] for line in output.splitlines() if line.startswith('QUALITY_RESULT=')]
    try:
        parsed = json.loads(lines[0]) if len(lines) == 1 else empty
        if (set(parsed) - set(empty) or any(type(parsed.get(k)) is not int or not 0 <= parsed[k] <= 2000
                for k in ('test_count', 'skipped_count', 'errors', 'failures')) or
                not isinstance(parsed.get('test_ids'), list) or len(parsed['test_ids']) > 2000 or
                any(not isinstance(s, str) or len(s) > 500 for s in parsed['test_ids'])):
            parsed = empty
    except (ValueError, TypeError):
        parsed = empty
    return parsed | {'exit_code': code, 'timed_out': code == 124}


def container_command(image, snapshot, driver, selectors):
    return ['docker', 'run', '--rm', '--name', 'jules-phase-' + uuid.uuid4().hex, '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--user=65534:65534', '--pids-limit=128', '--memory=1g',
            '--cpus=2', '--tmpfs=/tmp:rw,nosuid,size=128m', '--workdir=/workspace',
            '--mount', f'type=bind,source={snapshot.resolve()},target=/workspace,readonly',
            '--mount', f'type=bind,source={driver.resolve()},target=/driver/phase.py,readonly',
            image, 'python', '-B', '/driver/phase.py', json.dumps(selectors, separators=(',', ':'))]


def assess(kind, red, green, mutation):
    green = green or {'exit_code': 2, 'test_count': 0, 'test_ids': [], 'skipped_count': 0, 'errors': 1}
    status = 'PASSED'
    reason = 'assertion_failure' if red and red.get('failures', 0) > 0 else 'not_proven'
    if kind in ('docs', 'analysis'):
        status = 'PASSED'
    elif green.get('timed_out') or green.get('errors') or not green.get('test_count'):
        status = 'BLOCKED'
    elif green['exit_code'] != 0 or green['skipped_count'] >= green['test_count']:
        status = 'FAILED'
    elif kind in ('bug', 'security') and (not red or red.get('timed_out') or red.get('errors') or
            red.get('exit_code') == 0 or not red.get('failures') or set(red['test_ids']) != set(green['test_ids'])):
        status = 'BLOCKED'
    elif kind in ('test', 'test_setup') and (not mutation or mutation.get('errors') or
            mutation.get('timed_out') or not mutation.get('failures') or mutation.get('exit_code') == 0):
        status = 'FAILED'
    killed = bool(mutation and mutation.get('exit_code') == 1 and mutation.get('failures') and not mutation.get('errors'))
    return {'status': status, 'test_ids': green['test_ids'], 'test_count': green['test_count'],
            'skipped_count': green['skipped_count'], 'red_reason': reason,
            'red_exit_code': red['exit_code'] if red else 0, 'green_exit_code': green['exit_code'],
            'sensitivity_result': ('killed' if killed else 'survived') if kind in ('test', 'test_setup') else 'not_required',
            'mutation_restored': True}


def git(repo, *args):
    code, output = bounded_run(['git', '-C', str(repo), *args], timeout=30)
    if code:
        raise ValueError('Git object unavailable; no target code executed')
    return output


def export_tree(repo, sha, destination):
    if not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise ValueError('Expected full commit SHA')
    entries = git(repo, 'ls-tree', '-rz', sha).split('\x00')
    if len(entries) > 5001:
        raise ValueError('Snapshot too large')
    total = 0
    for entry in entries:
        if not entry:
            continue
        metadata, name = entry.split('\t', 1)
        mode, kind, _ = metadata.split()
        path = relative(name)
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('Symlink/submodule requires owner review')
        if path.startswith(('.git/', '.github/')) or any(p.startswith('.env') for p in path.split('/')):
            continue
        size = int(git(repo, 'cat-file', '-s', metadata.split()[2]).strip())
        if size > 2 * 1024 * 1024 or total + size > 20 * 1024 * 1024:
            raise ValueError('Snapshot byte limit exceeded')
        # Use bytes for target files. The wrapper never imports or launches them.
        data = subprocess.run(['git', '-C', str(repo), 'show', f'{sha}:{path}'], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30).stdout
        total += len(data)
        if len(data) > 2 * 1024 * 1024 or total > 20 * 1024 * 1024:
            raise ValueError('Snapshot byte limit exceeded')
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def mutations(source):
    """Small deterministic mutants; no assertion/output is invented by the wrapper."""
    tree = ast.parse(source)
    for index, node in enumerate(ast.walk(tree)):
        if isinstance(node, (ast.Compare, ast.BinOp, ast.BoolOp, ast.Return)):
            mutated = copy.deepcopy(tree)
            replacement = list(ast.walk(mutated))[index]
            if isinstance(replacement, ast.Compare):
                swaps = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.LtE: ast.Gt,
                         ast.Gt: ast.LtE, ast.GtE: ast.Lt, ast.In: ast.NotIn, ast.NotIn: ast.In}
                if type(replacement.ops[0]) not in swaps:
                    continue
                replacement.ops[0] = swaps[type(replacement.ops[0])]()
            elif isinstance(replacement, ast.BinOp):
                replacement.op = ast.Sub() if isinstance(replacement.op, ast.Add) else ast.Add()
            elif isinstance(replacement, ast.BoolOp):
                replacement.op = ast.Or() if isinstance(replacement.op, ast.And) else ast.And()
            elif isinstance(replacement, ast.Return) and replacement.value:
                replacement.value = ast.Constant(value=None)
            else:
                continue
            yield ast.unparse(ast.fix_missing_locations(mutated))


def validate_request(request, profile):
    for key in ('base_sha', 'subject_head_sha', 'workflow_revision'):
        if not re.fullmatch(r'[a-f0-9]{40}', request.get(key, '')):
            raise ValueError('Full SHA required')
    for key in ('task_id', 'attempt_id', 'operation', 'profile_version'):
        if not isinstance(request.get(key), str) or not 1 <= len(request[key]) <= 200:
            raise ValueError('Invalid identity')
    if (request['profile_version'] != profile['version'] or profile['framework'] != 'unittest' or
            profile['command'][:3] != ['python', '-m', 'unittest']):
        raise ValueError('Unsupported owner profile')
    members = request.get('members', [])
    if not 1 <= len(members) <= 3 or len({m['task_id'] for m in members}) != len(members):
        raise ValueError('One to three unique members required')
    for member in members:
        if member['kind'] not in ('bug', 'security', 'test', 'test_setup', 'docs', 'analysis', 'performance',
                                  'code_health', 'readability') or not 1 <= len(member['paths']) <= 100:
            raise ValueError('Invalid member scope')
        for path in member['paths']:
            relative(path)
    return members


def execute(repo, request, profile, phase=None, commands=None):
    deadline = time.monotonic() + 720
    commands = [] if commands is None else commands
    members = validate_request(request, profile)
    results, limitations = [], ['Static assertion screening and mutation sensitivity do not prove complete coverage.',
        'Target stdout is untrusted; Controller verifies host artifact provenance and exact subject SHA.']
    with tempfile.TemporaryDirectory(prefix='jules-quality-') as folder:
        root = Path(folder)
        base, head = root / 'base', root / 'head'
        base.mkdir()
        head.mkdir()
        export_tree(repo, request['base_sha'], base)
        export_tree(repo, request['subject_head_sha'], head)
        image = 'jules-quality-' + hashlib.sha256(request['base_sha'].encode()).hexdigest()[:16]
        if phase is None:
            if not shutil.which('docker'):
                raise ValueError('Docker unavailable; adapter not verified')
            context = root / 'image'
            context.mkdir()
            requirements = base / 'requirements-test.txt'
            (context / 'requirements-test.txt').write_bytes(requirements.read_bytes() if requirements.exists() else b'')
            (context / 'Dockerfile').write_text('FROM python:3.12-slim\nCOPY requirements-test.txt /requirements-test.txt\n'
                'RUN python -m pip install --no-cache-dir -r /requirements-test.txt\n', encoding='utf-8')
            code, _ = bounded_run(['docker', 'build', '--quiet', '--tag', image, str(context)])
            if code:
                raise ValueError('Approved-base dependency environment failed')
            def phase(directory, selectors):
                remaining = deadline - time.monotonic()
                if remaining < 1:
                    return read_phase_output('', 124)
                command = container_command(image, directory, Path(__file__).with_name('phase.py'), selectors)
                commands.append(command[-4:])
                try:
                    code, output = bounded_run(command, timeout=min(180, remaining))
                    return read_phase_output(output, code)
                finally:
                    # Killing the Docker CLI alone does not stop a malicious/hung container.
                    bounded_run(['docker', 'rm', '-f', command[command.index('--name') + 1]], timeout=10)
        for member in members:
            if member['kind'] in ('docs', 'analysis'):
                results.append(assess(member['kind'], None, None, None) | {'task_id': member['task_id']})
                continue
            selected = [p for p in member['paths'] if p.endswith('.py') and
                        any(p.startswith(relative(r) + '/') for r in profile['test_roots'])]
            if not selected:
                raise ValueError('Approved scope contains no behavioral test file')
            selectors, imports = [], set()
            for path in selected:
                source = (head / path).read_text(encoding='utf-8')
                selectors.extend({'path': path, 'selector': name} for name in inspect_tests(source))
                if len(selectors) > 100 or len(json.dumps(selectors).encode()) > 16384:
                    raise ValueError('Too many selected behavioral cases for a bounded phase')
                for node in ast.walk(ast.parse(source)):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                        [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                    for name in names:
                        candidate = name.replace('.', '/') + '.py'
                        if (head / candidate).is_file() and not any(candidate.startswith(r + '/') for r in profile['test_roots']):
                            imports.add(candidate)
            if not imports:
                raise ValueError('Selected tests do not import an actual application module')
            green = phase(head, selectors)
            red = mutation = None
            if member['kind'] in ('bug', 'security'):
                if not any(not (base / p).exists() or (base / p).read_bytes() != (head / p).read_bytes() for p in selected):
                    raise ValueError('Regression test must be added or strengthened in candidate')
                for path in selected:
                    target = base / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((head / path).read_bytes())
                red = phase(base, selectors)
            elif member['kind'] in ('test', 'test_setup'):
                attempts = 0
                for path in sorted(imports):
                    original_bytes = (head / path).read_bytes()
                    original = original_bytes.decode('utf-8')
                    for index, changed in enumerate(mutations(original)):
                        if attempts >= 3:
                            break
                        attempts += 1
                        try:
                            (head / path).write_text(changed, encoding='utf-8')
                            mutation = phase(head, selectors)
                        finally:
                            (head / path).write_bytes(original_bytes)
                        if mutation.get('failures') and not mutation.get('errors'):
                            break
                    if mutation and mutation.get('failures') and not mutation.get('errors'):
                        break
                    if attempts >= 3:
                        break
                # Re-run the restored original, not merely claim restoration.
                green = phase(head, selectors)
            expected = {'quality_' + hashlib.sha256(s['path'].encode()).hexdigest()[:12] + '.' + s['selector']
                        for s in selectors}
            if set(green['test_ids']) != expected or green['test_count'] != len(expected):
                raise ValueError('Observed case inventory differs from selected behavioral tests')
            results.append(assess(member['kind'], red, green, mutation) | {'task_id': member['task_id']})
    return results, limitations


def main():
    parser = argparse.ArgumentParser()
    for name in ('task-file', 'base', 'head', 'profile'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--repository', default='.')
    parser.add_argument('--output', default='quality-report.json')
    args = parser.parse_args()
    request = json.loads(Path(args.task_file).read_text(encoding='utf-8'))
    profile = json.loads(Path(args.profile).read_text(encoding='utf-8'))
    if (request['base_sha'] != args.base or request['subject_head_sha'] != args.head or
            request['workflow_revision'] != os.environ['GITHUB_SHA'] or
            request['repository_id'] != int(os.environ['GITHUB_REPOSITORY_ID'])):
        raise ValueError('Workflow/subject identity mismatch')
    empty = assess('bug', None, None, None)
    commands = []
    try:
        members, limitations = execute(Path(args.repository), request, profile, commands=commands)
        status = 'BLOCKED' if any(m['status'] == 'BLOCKED' for m in members) else (
            'FAILED' if any(m['status'] == 'FAILED' for m in members) else 'PASSED')
    except (ValueError, OSError, subprocess.SubprocessError, SyntaxError) as exc:
        status, members, limitations = 'BLOCKED', [], [str(exc)[:500]]
    summary = dict(empty, status=status, test_ids=sorted({t for m in members for t in m['test_ids']}),
                   test_count=sum(m['test_count'] for m in members), skipped_count=sum(m['skipped_count'] for m in members),
                   green_exit_code=0 if members and all(m['green_exit_code'] == 0 for m in members) else 1)
    if len(members) == 1:
        summary.update(members[0])
    report = summary | {'schema_version': 2, 'repository_id': request['repository_id'], 'task_id': request['task_id'],
        'attempt_id': request['attempt_id'], 'base_sha': args.base, 'subject_head_sha': args.head,
        'workflow_id': request['workflow_id'], 'workflow_path': '.github/workflows/jules-quality.yml',
        'workflow_revision': os.environ['GITHUB_SHA'], 'run_id': int(os.environ['GITHUB_RUN_ID']),
        'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']), 'profile_version': profile['version'],
        'test_command': profile['command'], 'member_results': members if len(members) > 1 else [],
        'executed_commands': commands,
        'produced_at': datetime.now(timezone.utc).isoformat(), 'limitations': limitations}
    report['task_id'] = request['task_id']
    report['artifact_digest'] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(',', ':'),
                                                       ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if status == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
