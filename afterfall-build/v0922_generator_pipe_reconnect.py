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
if "mod_version=0.9.2.1" not in text:
    raise SystemExit("Expected exact 0.9.2.1 source snapshot")
props.write_text(text.replace("mod_version=0.9.2.1", "mod_version=0.9.2.2"), encoding="utf-8")


replace_java(
    "blockentity/EmergencyGeneratorBlockEntity.java",
    "    private int burnTicks;\n    private boolean enabled = true;",
    "    private int burnTicks;\n    private boolean enabled = true;\n    // Existing cable blocks can cache a missing capability if they were placed before\n    // the generator block entity became available. Refresh once after load/placement.\n    private boolean connectionRefreshPending = true;"
)

replace_java(
    "blockentity/EmergencyGeneratorBlockEntity.java",
    "    public static void serverTick(Level level, BlockPos pos, BlockState state, EmergencyGeneratorBlockEntity be) {\n        if (!(level instanceof ServerLevel serverLevel) || !be.enabled) return;\n\n        be.startFuelIfNeeded();",
    "    public static void serverTick(Level level, BlockPos pos, BlockState state, EmergencyGeneratorBlockEntity be) {\n        if (!(level instanceof ServerLevel serverLevel)) return;\n\n        // NeoForge block capabilities can be cached by cable mods. A generator placed\n        // against an already existing pipe may therefore need one post-load invalidation\n        // after its block entity exists. The neighbour update also asks cable blocks such\n        // as Pipez to rebuild their side connection immediately. This runs only once.\n        if (be.connectionRefreshPending) {\n            be.connectionRefreshPending = false;\n            serverLevel.invalidateCapabilities(pos);\n            serverLevel.updateNeighborsAt(pos, state.getBlock());\n        }\n\n        if (!be.enabled) return;\n\n        be.startFuelIfNeeded();"
)

replace_java(
    "blockentity/EmergencyGeneratorBlockEntity.java",
    '"Emergency Generator: %s | %d/%d FE | %.0f FE/t | Fuel %.1f s | Output max %d FE/t (all faces)",',
    '"Emergency Generator: %s | %d/%d FE | %.0f FE/t | Fuel %.1f s | Output max %d FE/t (all faces / auto reconnect)",'
)

print("Prepared Afterfall 0.9.2.2: Emergency Generator refreshes FE capability and neighbouring pipes after load/placement.")
