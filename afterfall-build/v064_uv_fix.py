from pathlib import Path
import json

ROOT = Path('Afterfall')
MODELS = ROOT / 'src/main/resources/assets/afterfall/models/block'

# Version: build from the known-good 0.6.2 logic/collision snapshot.
gp = ROOT / 'gradle.properties'
text = gp.read_text()
text = text.replace('mod_version=0.6.2', 'mod_version=0.6.4')
gp.write_text(text)

# The original Blockbench project declares a logical UV resolution of 32x32.
# Blockbench face UV values therefore need a uniform Minecraft conversion of
# 16 / 32 = 0.5, regardless of whether a source PNG is 32x32 or 64x64.
#
# 0.6.2 already used 0.5 for the 32x32 textures (#tex1/#tex3/#tex4), but
# incorrectly used 0.25 for the two 64x64 images (#tex0 door, #tex2 frame_top).
# Doubling only faces using #tex0/#tex2 converts those models to the correct
# uniform 0.5 Blockbench-project scale while leaving the already-correct faces alone.
TARGET_TEXTURE_KEYS = {'#tex0', '#tex2'}
MODEL_NAMES = [
    'heavy_blast_door_closed.json',
    'heavy_blast_door_frame.json',
    'heavy_blast_door_left.json',
    'heavy_blast_door_right.json',
]

changed_faces = 0
examples = []
for name in MODEL_NAMES:
    path = MODELS / name
    model = json.loads(path.read_text())
    model_changed = 0
    for element in model.get('elements', []):
        for face_name, face in element.get('faces', {}).items():
            if not isinstance(face, dict) or face.get('texture') not in TARGET_TEXTURE_KEYS:
                continue
            uv = face.get('uv')
            if not isinstance(uv, list) or len(uv) != 4:
                continue
            old = list(uv)
            new = [round(float(v) * 2.0, 6) for v in uv]
            face['uv'] = new
            changed_faces += 1
            model_changed += 1
            if len(examples) < 12:
                examples.append(f'{name} {element.get("name", "element")} {face_name} {face.get("texture")}: {old} -> {new}')
    if model_changed:
        path.write_text(json.dumps(model, indent=2) + '\n')

report = [
    'Afterfall 0.6.4 Blockbench UV project-resolution correction',
    '',
    'Original .bbmodel logical resolution: 32x32',
    'Correct Minecraft UV factor: 16/32 = 0.5',
    '0.6.2 already-correct texture keys left unchanged: #tex1, #tex3, #tex4',
    'Corrected texture keys from 0.25 -> 0.5: #tex0 (door), #tex2 (frame_top)',
    f'Corrected faces: {changed_faces}',
    '',
    'Examples:',
    *examples,
]
Path('afterfall-build/output/uv-v064.txt').parent.mkdir(parents=True, exist_ok=True)
Path('afterfall-build/output/uv-v064.txt').write_text('\n'.join(report) + '\n')
print('\n'.join(report))

if changed_faces == 0:
    raise RuntimeError('No UV faces were corrected; expected #tex0/#tex2 faces in 0.6.2 snapshot')
