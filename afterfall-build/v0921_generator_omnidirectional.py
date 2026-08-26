from pathlib import Path

ROOT = Path("Afterfall")
JAVA = ROOT / "src/main/java/dev/afterfall"


def replace_java(rel: str, old: str, new: str) -> None:
    path = JAVA / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected patch anchor not found in {rel}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


props = ROOT / "gradle.properties"
text = props.read_text(encoding="utf-8")
if "mod_version=0.9.2" not in text:
    raise SystemExit("Expected exact 0.9.2 source snapshot")
props.write_text(text.replace("mod_version=0.9.2", "mod_version=0.9.2.1"), encoding="utf-8")


replace_java(
    "blockentity/EmergencyGeneratorBlockEntity.java",
    "import java.util.Locale;",
    "import java.util.ArrayList;\nimport java.util.List;\nimport java.util.Locale;"
)

replace_java(
    "blockentity/EmergencyGeneratorBlockEntity.java",
    "private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 1_000, MAX_OUTPUT_PER_TICK, this::setChanged);",
    "private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 0, MAX_OUTPUT_PER_TICK, this::setChanged);"
)

old_push = '''        if (be.energy.getEnergyStored() <= 0) return;\n        int remainingBudget = MAX_OUTPUT_PER_TICK;\n        for (Direction direction : Direction.values()) {\n            if (remainingBudget <= 0 || be.energy.getEnergyStored() <= 0) break;\n            BlockPos targetPos = pos.relative(direction);\n            IEnergyStorage target = serverLevel.getCapability(Capabilities.EnergyStorage.BLOCK, targetPos, direction.getOpposite());\n            if (target == null || !target.canReceive()) continue;\n            int offer = Math.min(remainingBudget, be.energy.getEnergyStored());\n            int accepted = target.receiveEnergy(offer, false);\n            if (accepted > 0) {\n                be.energy.extractEnergy(accepted, false);\n                remainingBudget -= accepted;\n            }\n        }'''

new_push = '''        if (be.energy.getEnergyStored() <= 0) return;\n\n        // Every face is an equal FE output.  The previous first-match loop could let the\n        // first connected pipe consume the whole per-tick budget, making the other faces\n        // look dead.  Discover all six receiving neighbours first and share the budget.\n        Direction[] directions = Direction.values();\n        int offset = (int) Math.floorMod(serverLevel.getGameTime(), directions.length);\n        List<IEnergyStorage> targets = new ArrayList<>(directions.length);\n        for (int i = 0; i < directions.length; i++) {\n            Direction direction = directions[(offset + i) % directions.length];\n            BlockPos targetPos = pos.relative(direction);\n            IEnergyStorage target = serverLevel.getCapability(\n                    Capabilities.EnergyStorage.BLOCK, targetPos, direction.getOpposite());\n            if (target != null && target.canReceive()) targets.add(target);\n        }\n\n        int remainingBudget = Math.min(MAX_OUTPUT_PER_TICK, be.energy.getEnergyStored());\n        List<IEnergyStorage> activeTargets = new ArrayList<>(targets);\n        while (remainingBudget > 0 && be.energy.getEnergyStored() > 0 && !activeTargets.isEmpty()) {\n            int share = Math.max(1, (remainingBudget + activeTargets.size() - 1) / activeTargets.size());\n            boolean movedAny = false;\n\n            for (int i = activeTargets.size() - 1; i >= 0 && remainingBudget > 0; i--) {\n                IEnergyStorage target = activeTargets.get(i);\n                if (!target.canReceive()) {\n                    activeTargets.remove(i);\n                    continue;\n                }\n\n                int offer = Math.min(share, Math.min(remainingBudget, be.energy.getEnergyStored()));\n                int accepted = target.receiveEnergy(offer, false);\n                if (accepted > 0) {\n                    be.energy.extractEnergy(accepted, false);\n                    remainingBudget -= accepted;\n                    movedAny = true;\n                }\n\n                // A partial acceptance means this neighbour is saturated for now; leave\n                // the unused budget to the other connected faces.\n                if (accepted < offer) activeTargets.remove(i);\n            }\n\n            if (!movedAny) break;\n        }'''

replace_java("blockentity/EmergencyGeneratorBlockEntity.java", old_push, new_push)

replace_java(
    "blockentity/EmergencyGeneratorBlockEntity.java",
    '"Emergency Generator: %s | %d/%d FE | %.0f FE/t | Fuel %.1f s | Output max %d FE/t",',
    '"Emergency Generator: %s | %d/%d FE | %.0f FE/t | Fuel %.1f s | Output max %d FE/t (all faces)",'
)

print("Prepared Afterfall 0.9.2.1: Emergency Generator outputs FE fairly through all six faces.")
