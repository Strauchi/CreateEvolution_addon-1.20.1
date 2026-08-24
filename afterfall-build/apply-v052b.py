# Triggered rebuild for Afterfall 0.5.2 door safety
import runpy
from pathlib import Path

runpy.run_path('afterfall-build/apply-v052.py', run_name='__main__')

controller = Path('Afterfall/src/main/java/dev/afterfall/blockentity/AirlockControllerBlockEntity.java')
text = controller.read_text()
text = text.replace('DOOR_CLOSE_DELAY_TICKS', '20')
text = text.replace('DOOR_SEAL_SETTLE_TICKS', '12')
controller.write_text(text)
