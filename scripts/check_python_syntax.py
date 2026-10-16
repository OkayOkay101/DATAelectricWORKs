"""Parse tracked Python sources without importing or executing application code."""
import ast
import subprocess
from pathlib import Path


def main():
    tracked = subprocess.check_output(['git', 'ls-files', '-z', '--', '*.py'])
    paths = [Path(p.decode('utf-8')) for p in tracked.split(b'\0') if p]
    if not paths:
        raise SystemExit('No tracked Python sources found')
    for path in paths:
        ast.parse(path.read_bytes(), filename=str(path))
    print(f'Syntax passed: {len(paths)} Python files. Functional tests are not yet configured.')


if __name__ == '__main__':
    main()
