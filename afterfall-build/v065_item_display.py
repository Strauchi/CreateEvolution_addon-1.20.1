from pathlib import Path
import json

root = Path('Afterfall')
item_model = root / 'src/main/resources/assets/afterfall/models/item/heavy_blast_door.json'
props = root / 'gradle.properties'

model = {
    "parent": "afterfall:block/heavy_blast_door_closed",
    "display": {
        "gui": {
            "rotation": [30, 225, 0],
            "translation": [0, -1.0, 0],
            "scale": [0.30, 0.30, 0.30]
        },
        "ground": {
            "rotation": [0, 0, 0],
            "translation": [0, 2.0, 0],
            "scale": [0.18, 0.18, 0.18]
        },
        "fixed": {
            "rotation": [0, 180, 0],
            "translation": [0, 0, 0],
            "scale": [0.30, 0.30, 0.30]
        },
        "thirdperson_righthand": {
            "rotation": [75, 45, 0],
            "translation": [0, 1.5, 0],
            "scale": [0.20, 0.20, 0.20]
        },
        "thirdperson_lefthand": {
            "rotation": [75, 225, 0],
            "translation": [0, 1.5, 0],
            "scale": [0.20, 0.20, 0.20]
        },
        "firstperson_righthand": {
            "rotation": [0, 45, 0],
            "translation": [1.5, 1.5, 1.0],
            "scale": [0.16, 0.16, 0.16]
        },
        "firstperson_lefthand": {
            "rotation": [0, 225, 0],
            "translation": [-1.5, 1.5, 1.0],
            "scale": [0.16, 0.16, 0.16]
        }
    }
}
item_model.write_text(json.dumps(model, indent=2) + '\n', encoding='utf-8')

text = props.read_text(encoding='utf-8')
text = text.replace('mod_version=0.6.4', 'mod_version=0.6.5')
props.write_text(text, encoding='utf-8')

print('Afterfall 0.6.5 Heavy Blast Door item display transforms')
print('GUI scale: 0.30')
print('First person scale: 0.16')
print('Third person scale: 0.20')
print('Ground scale: 0.18')
print('Fixed/item-frame scale: 0.30')
