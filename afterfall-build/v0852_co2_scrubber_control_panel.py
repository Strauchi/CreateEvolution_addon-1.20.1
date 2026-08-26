from pathlib import Path

ROOT = Path("Afterfall")


def replace_one(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old[:160]!r}")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


# Version
replace_one(ROOT / "gradle.properties", "mod_version=0.8.5.1\n", "mod_version=0.8.5.2\n")

# -----------------------------------------------------------------------------
# CommonEvents: CO2 scrubber interaction now always opens a proper machine GUI.
# Power toggling moves into the existing machine POWER button.
# -----------------------------------------------------------------------------
common = ROOT / "src/main/java/dev/afterfall/event/CommonEvents.java"
replace_one(
    common,
    """        if (state.is(ModBlocks.CO2_SCRUBBER.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel
                    && serverLevel.getBlockEntity(event.getPos()) instanceof Co2ScrubberBlockEntity scrubber) {
                if (player.isShiftKeyDown()) {
                    scrubber.setEnabled(!scrubber.enabled());
                    player.displayClientMessage(Component.literal("CO2 SCRUBBER: "
                            + (scrubber.enabled() ? "ENABLED" : "DISABLED"))
                            .withStyle(scrubber.enabled() ? ChatFormatting.GREEN : ChatFormatting.GRAY), true);
                } else {
                    player.displayClientMessage(Co2ScrubberBlockEntity.status(serverLevel, event.getPos()), true);
                }
            }
            return;
        }
""",
    """        if (state.is(ModBlocks.CO2_SCRUBBER.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel
                    && serverLevel.getBlockEntity(event.getPos()) instanceof Co2ScrubberBlockEntity scrubber) {
                openMachineMenu(player, event.getPos(), scrubber, Component.literal("CO2 Scrubber"));
            }
            return;
        }
"""
)

# -----------------------------------------------------------------------------
# MachineMenu: add a first-class scrubber machine type and synchronize all data
# needed by its control panel. No inventory/media slot yet; the layout reserves
# room for future consumable scrubber media without inventing that mechanic now.
# -----------------------------------------------------------------------------
menu = ROOT / "src/main/java/dev/afterfall/menu/MachineMenu.java"
replace_one(
    menu,
    "import dev.afterfall.blockentity.AirlockLogic;\n",
    "import dev.afterfall.blockentity.AirlockLogic;\nimport dev.afterfall.blockentity.Co2ScrubberBlockEntity;\n"
)
replace_one(menu, "    public static final int DATA_COUNT = 43;\n", "    public static final int DATA_COUNT = 50;\n")
replace_one(
    menu,
    "    public static final int TYPE_FAN = 4;\n",
    "    public static final int TYPE_FAN = 4;\n    public static final int TYPE_SCRUBBER = 5;\n"
)
replace_one(
    menu,
    "    public static final int D_INTAKE_AUTO_THRESHOLD_PERCENT = 42;\n",
    "    public static final int D_INTAKE_AUTO_THRESHOLD_PERCENT = 42;\n"
    "    public static final int D_SCRUBBER_INPUT_CO2_X1000 = 43;\n"
    "    public static final int D_SCRUBBER_OUTPUT_CO2_X1000 = 44;\n"
    "    public static final int D_SCRUBBER_ACTUAL_EQ_X100 = 45;\n"
    "    public static final int D_SCRUBBER_REMOVAL_PER_MIN_X100000 = 46;\n"
    "    public static final int D_SCRUBBER_ENERGY_USE = 47;\n"
    "    public static final int D_SCRUBBER_ACTUAL_FLOW_X10 = 48;\n"
    "    public static final int D_SCRUBBER_NOMINAL_EQ_X100 = 49;\n"
)
replace_one(
    menu,
    "        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1\n"
    "                : ((machineType == TYPE_FAN || machineType == TYPE_INTAKE) ? 0 : 3);\n",
    "        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1\n"
    "                : ((machineType == TYPE_FAN || machineType == TYPE_INTAKE || machineType == TYPE_SCRUBBER) ? 0 : 3);\n"
)
replace_one(
    menu,
    "        if (blockEntity instanceof VentilationFanBlockEntity) return TYPE_FAN;\n"
    "        return TYPE_FILTER;\n",
    "        if (blockEntity instanceof VentilationFanBlockEntity) return TYPE_FAN;\n"
    "        if (blockEntity instanceof Co2ScrubberBlockEntity) return TYPE_SCRUBBER;\n"
    "        return TYPE_FILTER;\n"
)
replace_one(
    menu,
    "        if (blockEntity instanceof VentilationFanBlockEntity) return new ItemStackHandler(0);\n"
    "        if (type == TYPE_INTAKE || type == TYPE_FAN) return new ItemStackHandler(0);\n",
    "        if (blockEntity instanceof VentilationFanBlockEntity) return new ItemStackHandler(0);\n"
    "        if (blockEntity instanceof Co2ScrubberBlockEntity) return new ItemStackHandler(0);\n"
    "        if (type == TYPE_INTAKE || type == TYPE_FAN || type == TYPE_SCRUBBER) return new ItemStackHandler(0);\n"
)

scrubber_update = """
        if (serverBlockEntity instanceof Co2ScrubberBlockEntity be) {
            data.set(D_TYPE, TYPE_SCRUBBER);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            data.set(D_FLOW_X10, scale(Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            data.set(D_SCRUBBER_NOMINAL_EQ_X100, scale(Co2ScrubberBlockEntity.PLAYER_EQUIVALENT_CAPACITY, 100.0D));
            data.set(D_SCRUBBER_ACTUAL_EQ_X100, scale(be.recentActualPlayerEquivalent(level), 100.0D));
            data.set(D_SCRUBBER_REMOVAL_PER_MIN_X100000,
                    scale(be.recentRemovedCo2PerSecond(level) * 60.0D, 100000.0D));
            data.set(D_SCRUBBER_ENERGY_USE, be.recentEnergyUse(level));
            data.set(D_SCRUBBER_ACTUAL_FLOW_X10, scale(be.recentFlowM3PerSecond(level), 10.0D));

            RoomScanResult input = be.inspectInput(level);
            RoomScanResult output = be.inspectOutput(level);
            RoomAtmosphere inputAir = input == null ? null : atmosphere(level, input);
            RoomAtmosphere outputAir = output == null ? null : atmosphere(level, output);

            if (input != null && inputAir != null) {
                data.set(D_INPUT_ROOM_VOLUME, input.volume());
                data.set(D_SCRUBBER_INPUT_CO2_X1000, scale(inputAir.co2Percent(), 1000.0D));
            }
            if (output != null && outputAir != null) {
                setAtmosphere(output, outputAir);
                data.set(D_SCRUBBER_OUTPUT_CO2_X1000, scale(outputAir.co2Percent(), 1000.0D));
            }

            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), 1)) data.set(D_STATUS, 1);
            else if (input == null) data.set(D_STATUS, 34);
            else if (output == null) data.set(D_STATUS, 35);
            else if (input.anchor().equals(output.anchor())) data.set(D_STATUS, 36);
            else if (be.recentActualPlayerEquivalent(level) > 0.0001D) data.set(D_STATUS, 8);
            else if (outputAir != null && outputAir.co2Percent() <= RoomAtmosphere.NORMAL_CO2 + 0.000001D) data.set(D_STATUS, 5);
            else data.set(D_STATUS, 39);

            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

"""
replace_one(
    menu,
    "        if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {\n",
    scrubber_update + "        if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {\n"
)
replace_one(
    menu,
    "            else if (serverBlockEntity instanceof VentilationFanBlockEntity be) be.setEnabled(!be.enabled());\n"
    "            else if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {\n",
    "            else if (serverBlockEntity instanceof VentilationFanBlockEntity be) be.setEnabled(!be.enabled());\n"
    "            else if (serverBlockEntity instanceof Co2ScrubberBlockEntity be) be.setEnabled(!be.enabled());\n"
    "            else if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {\n"
)
replace_one(
    menu,
    "    public int intakeAutoThresholdPercent() { return get(D_INTAKE_AUTO_THRESHOLD_PERCENT); }\n",
    "    public int intakeAutoThresholdPercent() { return get(D_INTAKE_AUTO_THRESHOLD_PERCENT); }\n"
    "    public double scrubberInputCo2() { return get(D_SCRUBBER_INPUT_CO2_X1000) / 1000.0D; }\n"
    "    public double scrubberOutputCo2() { return get(D_SCRUBBER_OUTPUT_CO2_X1000) / 1000.0D; }\n"
    "    public double scrubberActualEq() { return get(D_SCRUBBER_ACTUAL_EQ_X100) / 100.0D; }\n"
    "    public double scrubberRemovalPerMinute() { return get(D_SCRUBBER_REMOVAL_PER_MIN_X100000) / 100000.0D; }\n"
    "    public int scrubberEnergyUse() { return get(D_SCRUBBER_ENERGY_USE); }\n"
    "    public double scrubberActualFlow() { return get(D_SCRUBBER_ACTUAL_FLOW_X10) / 10.0D; }\n"
    "    public double scrubberNominalEq() { return get(D_SCRUBBER_NOMINAL_EQ_X100) / 100.0D; }\n"
)

# -----------------------------------------------------------------------------
# MachineScreen: dedicated scrubber panel. The normal POWER button remains the
# single control; all live treatment telemetry is visible without /af life.
# -----------------------------------------------------------------------------
screen = ROOT / "src/main/java/dev/afterfall/client/MachineScreen.java"
replace_one(
    screen,
    "        } else if (menu.machineType() == MachineMenu.TYPE_INTAKE) {\n"
    "            renderIntake(graphics);\n"
    "        } else {\n"
    "            renderFilters(graphics);\n"
    "        }\n",
    "        } else if (menu.machineType() == MachineMenu.TYPE_INTAKE) {\n"
    "            renderIntake(graphics);\n"
    "        } else if (menu.machineType() == MachineMenu.TYPE_SCRUBBER) {\n"
    "            renderScrubber(graphics);\n"
    "        } else {\n"
    "            renderFilters(graphics);\n"
    "        }\n"
)

render_scrubber = """    private void renderScrubber(GuiGraphics graphics) {
        int inputVolume = menu.inputRoomVolume();
        int outputVolume = menu.get(MachineMenu.D_ROOM_VOLUME);
        double inputCo2 = menu.scrubberInputCo2();
        double outputCo2 = menu.scrubberOutputCo2();
        double actualEq = menu.scrubberActualEq();
        double nominalEq = menu.scrubberNominalEq();
        double actualFlow = menu.scrubberActualFlow();
        double maxFlow = menu.flow();
        int energyUse = menu.scrubberEnergyUse();

        graphics.drawString(font, "CO2 TREATMENT // O2 IS NOT GENERATED", 12, 88, 0xFFE1B45A, false);
        graphics.drawString(font, String.format(Locale.ROOT, "BACK input: %d m³ | CO2 %.3f%%",
                inputVolume, inputCo2), 12, 106, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "FRONT output: %d m³ | CO2 %.3f%%",
                outputVolume, outputCo2), 12, 119, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Flow: %.1f / %.1f m³/s",
                actualFlow, maxFlow), 12, 137, actualFlow > 0.01D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Removal: %.5f%% CO2/min",
                menu.scrubberRemovalPerMinute()), 12, 150,
                menu.scrubberRemovalPerMinute() > 0.000001D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Support: %.2f / %.2f player-eq",
                actualEq, nominalEq), 12, 163,
                actualEq > 0.0001D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Power use: %,d / %,d FE/s",
                energyUse, 1200), 12, 176, energyUse > 0 ? 0xFF9DB7BD : 0xFF7F9298, false);
        graphics.drawString(font, "Future media bay: not required in 0.8.5.2", 12, 193, 0xFF6F7D82, false);
    }

"""
replace_one(screen, "    private void renderIntake(GuiGraphics graphics) {\n", render_scrubber + "    private void renderIntake(GuiGraphics graphics) {\n")
replace_one(
    screen,
    "            case MachineMenu.TYPE_FAN -> \"AFTERFALL // VENTILATION FAN\";\n"
    "            default -> \"AFTERFALL // COMPACT AIR FILTRATION UNIT\";\n",
    "            case MachineMenu.TYPE_FAN -> \"AFTERFALL // VENTILATION FAN\";\n"
    "            case MachineMenu.TYPE_SCRUBBER -> \"AFTERFALL // CO2 SCRUBBER\";\n"
    "            default -> \"AFTERFALL // COMPACT AIR FILTRATION UNIT\";\n"
)
replace_one(
    screen,
    "            case 38 -> \"AUTO ISOLATED - FALLOUT\";\n"
    "            default -> \"INITIALIZING\";\n",
    "            case 38 -> \"AUTO ISOLATED - FALLOUT\";\n"
    "            case 39 -> \"READY - WAITING FOR AIRFLOW\";\n"
    "            default -> \"INITIALIZING\";\n"
)
replace_one(
    screen,
    "        if (status == 4 || status == 7 || status == 31\n"
    "                || (menu.machineType() == MachineMenu.TYPE_AIRLOCK && status >= 20)) return 0xFFE1B45A;\n",
    "        if (status == 4 || status == 7 || status == 31 || status == 39\n"
    "                || (menu.machineType() == MachineMenu.TYPE_AIRLOCK && status >= 20)) return 0xFFE1B45A;\n"
)

print("Applied Afterfall 0.8.5.2 CO2 Scrubber Control Panel patch")
