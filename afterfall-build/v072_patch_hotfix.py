from pathlib import Path
p = Path('afterfall-build/v072_return_mixing_fix.py')
text = p.read_text(encoding='utf-8')
old = "replace_once(JAVA / 'Afterfall.java', 'Afterfall 0.6.0 initialized', 'Afterfall 0.7.2 initialized')"
new = "replace_once(JAVA / 'Afterfall.java', 'Afterfall 0.7.1 initialized', 'Afterfall 0.7.2 initialized')"
if old not in text:
    raise RuntimeError('0.7.2 patch version-log line not found')
p.write_text(text.replace(old, new, 1), encoding='utf-8')
print('0.7.2 patch hotfix applied')
