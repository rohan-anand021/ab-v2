COLLECTIONS_REWRITE = """cd {workdir} && python - <<'PY'
from pathlib import Path
repl = {{
    'from collections import MutableMapping': 'from collections.abc import MutableMapping',
    'from collections import Mapping': 'from collections.abc import Mapping',
    'collections.MutableMapping': 'collections.abc.MutableMapping',
    'collections.Mapping': 'collections.abc.Mapping',
}}
for p in Path('.').rglob('*.py'):
    txt = p.read_text()
    new = txt
    for old, new_val in repl.items():
        new = new.replace(old, new_val)
    if new != txt:
        p.write_text(new)
PY"""
