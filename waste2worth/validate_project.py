from pathlib import Path
import ast
import re
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / 'templates'
STATIC = ROOT / 'static'

# 1) Python syntax
ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
ast.parse((ROOT / 'seed_demo.py').read_text(encoding='utf-8'))

# 2) Every url_for endpoint referenced by templates exists in app.py.
module = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
endpoints = set()
for node in module.body:
    if isinstance(node, ast.FunctionDef):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in {'route','get','post'}:
                endpoints.add(node.name)
                break
refs = set()
for path in TEMPLATES.glob('*.html'):
    refs.update(re.findall(r"url_for\(['\"]([A-Za-z0-9_]+)", path.read_text(encoding='utf-8')))
refs.discard('static')
missing = sorted(refs - endpoints)
if missing:
    raise SystemExit(f'Missing route endpoints: {missing}')

# 3) Jinja syntax parsing.
env = Environment(loader=FileSystemLoader(TEMPLATES))
for path in TEMPLATES.glob('*.html'):
    env.parse(path.read_text(encoding='utf-8'))

# 4) Required project files.
required = [ROOT/'app.py', ROOT/'requirements.txt', ROOT/'README.md', STATIC/'css/style.css', STATIC/'js/app.js', TEMPLATES/'base.html']
missing_files = [str(p) for p in required if not p.exists()]
if missing_files:
    raise SystemExit(f'Missing files: {missing_files}')

print('Waste2Worth validation passed.')
print(f'- Python files parsed: 2')
print(f'- Jinja templates parsed: {len(list(TEMPLATES.glob("*.html")))}')
print(f'- Referenced endpoints checked: {len(refs)}')
print('- Required project files present.')
