from pathlib import Path

controller = Path("Afterfall/src/main/java/dev/afterfall/blockentity/AirlockControllerBlockEntity.java")
text = controller.read_text()
if "public int stateTicks()" not in text:
    marker = "    public CycleState cycleState() { return cycleState; }\n"
    if marker not in text:
        raise RuntimeError("cycleState getter marker missing")
    text = text.replace(marker, marker + "    public int stateTicks() { return stateTicks; }\n", 1)
controller.write_text(text)

menu = Path("Afterfall/src/main/java/dev/afterfall/menu/MachineMenu.java")
text = menu.read_text()
text = text.replace("            case UNSAFE_READY -> 15;\n", "")
if "default -> 15;" not in text:
    marker = "            case SAFE -> 16;\n        };\n"
    if marker not in text:
        raise RuntimeError("airlock status switch marker missing")
    text = text.replace(marker, "            case SAFE -> 16;\n            default -> 15; // unsafe-but-purgeable / future status fallback\n        };\n", 1)
menu.write_text(text)
