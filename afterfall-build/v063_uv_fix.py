from pathlib import Path
import json
import struct

ROOT = Path("Afterfall")
RES = ROOT / "src/main/resources/assets/afterfall"
MODELS = RES / "models/block"
TEXTURES = RES / "textures/block"
OUTPUT = Path("afterfall-build/output")
OUTPUT.mkdir(parents=True, exist_ok=True)

# Version
gp = ROOT / "gradle.properties"
text = gp.read_text()
if "mod_version=0.6.2" not in text:
    raise RuntimeError("Expected Afterfall 0.6.2 source snapshot")
gp.write_text(text.replace("mod_version=0.6.2", "mod_version=0.6.3", 1))


def png_dimensions(path: Path):
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise RuntimeError(f"Not a valid PNG: {path}")
    return struct.unpack(">II", data[16:24])


def resolve_texture(texture_ref: str, textures: dict):
    if not texture_ref or not texture_ref.startswith("#"):
        return None
    resolved = textures.get(texture_ref[1:])
    if not isinstance(resolved, str):
        return None
    prefix = "afterfall:block/"
    if not resolved.startswith(prefix):
        return None
    return TEXTURES / (resolved[len(prefix):] + ".png")


report = ["Afterfall 0.6.3 Heavy Blast Door UV normalization", ""]
texture_cache = {}
changed_models = []
changed_faces = 0

# Blockbench stores face UV coordinates in texture pixels. Minecraft's block-model
# JSON interprets UV coordinates in a virtual 0..16 coordinate space regardless of
# the underlying PNG resolution. Normalize U and V independently for every texture.
for model_path in sorted(MODELS.glob("heavy_blast_door*.json")):
    try:
        model = json.loads(model_path.read_text())
    except json.JSONDecodeError:
        continue

    elements = model.get("elements")
    textures = model.get("textures", {})
    if not isinstance(elements, list) or not isinstance(textures, dict):
        continue

    model_changed = False
    for element in elements:
        faces = element.get("faces", {}) if isinstance(element, dict) else {}
        if not isinstance(faces, dict):
            continue
        for face_name, face in faces.items():
            if not isinstance(face, dict) or "uv" not in face:
                continue
            uv = face.get("uv")
            if not isinstance(uv, list) or len(uv) != 4:
                continue
            texture_path = resolve_texture(face.get("texture"), textures)
            if texture_path is None or not texture_path.exists():
                continue

            if texture_path not in texture_cache:
                width, height = png_dimensions(texture_path)
                texture_cache[texture_path] = (width, height)
            else:
                width, height = texture_cache[texture_path]

            scaled = [
                round(float(uv[0]) * 16.0 / width, 6),
                round(float(uv[1]) * 16.0 / height, 6),
                round(float(uv[2]) * 16.0 / width, 6),
                round(float(uv[3]) * 16.0 / height, 6),
            ]
            if scaled != uv:
                face["uv"] = scaled
                model_changed = True
                changed_faces += 1

    if model_changed:
        model_path.write_text(json.dumps(model, indent=2) + "\n")
        changed_models.append(model_path.name)

for path, (width, height) in sorted(texture_cache.items(), key=lambda item: item[0].name):
    report.append(
        f"{path.name}: {width}x{height} | UV factors U={16.0/width:.6f}, V={16.0/height:.6f}"
    )

report += [
    "",
    f"Changed models: {', '.join(changed_models) if changed_models else 'none'}",
    f"Changed faces: {changed_faces}",
]

if changed_faces == 0:
    raise RuntimeError("No Heavy Blast Door UVs were changed; expected raw Blockbench pixel UVs")

(OUTPUT / "uv-v063.txt").write_text("\n".join(report) + "\n")
print("\n".join(report))
