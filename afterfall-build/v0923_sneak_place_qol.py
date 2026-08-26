from pathlib import Path

ROOT = Path("Afterfall")
JAVA = ROOT / "src/main/java/dev/afterfall"


def replace_java(rel: str, old: str, new: str) -> None:
    path = JAVA / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected patch anchor not found in {rel}: {old[:140]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


props = ROOT / "gradle.properties"
text = props.read_text(encoding="utf-8")
if "mod_version=0.9.2.2" not in text:
    raise SystemExit("Expected exact 0.9.2.2 source snapshot")
props.write_text(text.replace("mod_version=0.9.2.2", "mod_version=0.9.2.3"), encoding="utf-8")


# Sneak-use on GUI machines must remain available to vanilla/item interaction so blocks,
# pipes and cables can be placed against the machine instead of opening its screen.
replace_java(
    "event/CommonEvents.java",
    "    public static void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {\n        BlockState state = event.getLevel().getBlockState(event.getPos());\n\n        if (state.is(ModBlocks.TRANSFER_VENT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {",
    "    public static void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {\n        BlockState state = event.getLevel().getBlockState(event.getPos());\n\n        // Standard machine-building UX: normal right-click opens the Afterfall GUI,\n        // while sneak + right-click is deliberately not consumed by GUI machines.\n        // Leaving the event untouched lets the held BlockItem / cable / pipe perform\n        // its normal use-on-block action against the machine face.\n        if (event.getHand() == InteractionHand.MAIN_HAND\n                && event.getEntity().isShiftKeyDown()\n                && isGuiMachine(state)) {\n            return;\n        }\n\n        if (state.is(ModBlocks.TRANSFER_VENT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {"
)

# The Airlock Controller was the one GUI machine whose old GUI binding lived on sneak-use.
# Move its GUI to ordinary right-click; the existing GUI already contains the cycle button,
# so no operational feature is lost and sneak-use becomes free for placement like every
# other GUI machine.
replace_java(
    "event/CommonEvents.java",
    "                    } else if (!player.isShiftKeyDown()) {\n                        controller.requestFromController(serverLevel, player);\n                        player.displayClientMessage(controller.shortCycleStatus(serverLevel), true);\n                    } else {\n                        openMachineMenu(player, event.getPos(), controller, Component.literal(\"Airlock Controller\"));\n                    }",
    "                    } else {\n                        openMachineMenu(player, event.getPos(), controller, Component.literal(\"Airlock Controller\"));\n                    }"
)

# Central list keeps the bypass scoped to blocks whose primary interaction is a GUI.
# Non-GUI controls (Air Vent mode toggle, Transfer Vent diagnostics, Airlock Call Panel,
# and linked airlock doors) intentionally keep their established interactions.
replace_java(
    "event/CommonEvents.java",
    "    private static void openMachineMenu(ServerPlayer player, net.minecraft.core.BlockPos pos, BlockEntity blockEntity,\n                                        Component title) {",
    "    private static boolean isGuiMachine(BlockState state) {\n        return state.is(ModBlocks.VENTILATION_FAN.get())\n                || state.is(ModBlocks.CO2_SCRUBBER.get())\n                || state.is(ModBlocks.AIR_FILTER_UNIT.get())\n                || state.is(ModBlocks.AIR_INTAKE_UNIT.get())\n                || state.is(ModBlocks.AIRLOCK_CONTROLLER.get())\n                || state.is(ModBlocks.SMART_POWER_TAP.get())\n                || state.is(ModBlocks.POWER_CONTROL_PANEL.get())\n                || state.is(ModBlocks.EMERGENCY_POWER_BANK.get())\n                || state.is(ModBlocks.EMERGENCY_GENERATOR.get());\n    }\n\n    private static void openMachineMenu(ServerPlayer player, net.minecraft.core.BlockPos pos, BlockEntity blockEntity,\n                                        Component title) {"
)

# Keep the dormant diagnostics helper text from advertising the retired sneak binding.
replace_java(
    "event/CommonEvents.java",
    "        player.sendSystemMessage(Component.literal(\"Tip: right-click = automatic cycle, sneak + right-click = diagnostics\")\n                .withStyle(ChatFormatting.GRAY));",
    "        player.sendSystemMessage(Component.literal(\"Tip: right-click = controller GUI; sneak + right-click = place blocks against controller\")\n                .withStyle(ChatFormatting.GRAY));"
)

print("Prepared Afterfall 0.9.2.3: GUI machines no longer consume sneak-right-click; Airlock Controller GUI moved to normal right-click.")
