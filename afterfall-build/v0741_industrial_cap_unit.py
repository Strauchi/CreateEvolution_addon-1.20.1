from pathlib import Path

root = Path('Afterfall')

screen = root / 'src/main/java/dev/afterfall/client/MachineScreen.java'
text = screen.read_text()
old = 'graphics.drawString(font, String.format(Locale.ROOT, "Fan %.1f m³/s | Industrial cap %s", menu.flow(), filterCap),'
new = 'graphics.drawString(font, String.format(Locale.ROOT, "Fan %.1f m³/s | Industrial cap %s m³/s", menu.flow(), filterCap),'
if old not in text:
    raise SystemExit('MachineScreen industrial cap label pattern not found')
screen.write_text(text.replace(old, new, 1))

props = root / 'gradle.properties'
p = props.read_text()
if 'mod_version=0.7.4\n' not in p:
    raise SystemExit('Expected 0.7.4 base version not found')
props.write_text(p.replace('mod_version=0.7.4\n', 'mod_version=0.7.4.1\n', 1))

main = root / 'src/main/java/dev/afterfall/Afterfall.java'
m = main.read_text()
m = m.replace('Afterfall 0.7.4 initialized', 'Afterfall 0.7.4.1 initialized')
main.write_text(m)

print('Afterfall 0.7.4.1 industrial capacity unit hotfix applied')
