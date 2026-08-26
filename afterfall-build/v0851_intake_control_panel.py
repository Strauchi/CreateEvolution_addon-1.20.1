from pathlib import Path

ROOT = Path("Afterfall")


def replace_one(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old[:120]!r}")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


# Version
replace_one(ROOT / "gradle.properties", "mod_version=0.8.5\n", "mod_version=0.8.5.1\n")

# -----------------------------------------------------------------------------
# AirIntakeBlockEntity: expose direct mode selection for GUI controls.
# -----------------------------------------------------------------------------
intake_be = ROOT / "src/main/java/dev/afterfall/blockentity/AirIntakeBlockEntity.java"
replace_one(
    intake_be,
    "    public IntakeMode mode() { return mode; }\n"
    "    public void cycleMode() { mode = mode.next(); setChanged(); }\n",
    "    public IntakeMode mode() { return mode; }\n"
    "    public void setMode(IntakeMode mode) {\n"
    "        if (mode != null && this.mode != mode) {\n"
    "            this.mode = mode;\n"
    "            setChanged();\n"
    "        }\n"
    "    }\n"
    "    public void cycleMode() { setMode(mode.next()); }\n"
)

# -----------------------------------------------------------------------------
# CommonEvents: intake interaction always opens the GUI. Sneak-right-click no
# longer mutates the mode, so all intake configuration lives in one place.
# -----------------------------------------------------------------------------
common = ROOT / "src/main/java/dev/afterfall/event/CommonEvents.java"
replace_one(
    common,
    "                if (blockEntity instanceof AirIntakeBlockEntity intake) {\n"
    "                    if (player.isShiftKeyDown()) {\n"
    "                        intake.cycleMode();\n"
    "                        player.displayClientMessage(AirIntakeBlockEntity.status(serverLevel, event.getPos()), true);\n"
    "                    } else {\n"
    "                        openMachineMenu(player, event.getPos(), intake, Component.literal(\"Air Intake Unit\"));\n"
    "                    }\n"
    "                }\n",
    "                if (blockEntity instanceof AirIntakeBlockEntity intake) {\n"
    "                    openMachineMenu(player, event.getPos(), intake, Component.literal(\"Air Intake Unit\"));\n"
    "                }\n"
)

# -----------------------------------------------------------------------------
# MachineMenu: synchronize intake mode + fallout telemetry to the client and
# handle three explicit mode buttons.
# -----------------------------------------------------------------------------
menu = ROOT / "src/main/java/dev/afterfall/menu/MachineMenu.java"
replace_one(menu, "    public static final int DATA_COUNT = 35;\n", "    public static final int DATA_COUNT = 43;\n")
replace_one(
    menu,
    "    public static final int BUTTON_POWER = 0;\n"
    "    public static final int BUTTON_ACTION = 1;\n",
    "    public static final int BUTTON_POWER = 0;\n"
    "    public static final int BUTTON_ACTION = 1;\n"
    "    public static final int BUTTON_INTAKE_OPEN = 2;\n"
    "    public static final int BUTTON_INTAKE_CLOSED = 3;\n"
    "    public static final int BUTTON_INTAKE_AUTO = 4;\n"
)
replace_one(
    menu,
    "    public static final int D_TRANSFER_VENTS = 33;\n"
    "    public static final int D_TRANSFER_CAPACITY_X10 = 34;\n",
    "    public static final int D_TRANSFER_VENTS = 33;\n"
    "    public static final int D_TRANSFER_CAPACITY_X10 = 34;\n"
    "    public static final int D_INTAKE_MODE = 35;\n"
    "    public static final int D_FALLOUT_CONDITION = 36;\n"
    "    public static final int D_FALLOUT_LOAD_PERCENT = 37;\n"
    "    public static final int D_OUTSIDE_DUST_X100 = 38;\n"
    "    public static final int D_OUTSIDE_RAD_X100 = 39;\n"
    "    public static final int D_INTAKE_AUTO_ISOLATED = 40;\n"
    "    public static final int D_INTAKE_UNIT_FLOW_X10 = 41;\n"
    "    public static final int D_INTAKE_AUTO_THRESHOLD_PERCENT = 42;\n"
)

old_intake_update = """        if (serverBlockEntity instanceof AirIntakeBlockEntity be) {
            data.set(D_TYPE, TYPE_INTAKE);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            data.set(D_PRE, scale(AirIntakeBlockEntity.PERMANENT_DUST_EFFICIENCY * 100.0D, 10.0D));
            data.set(D_RAD, scale(AirIntakeBlockEntity.PERMANENT_RADIATION_EFFICIENCY * 100.0D, 10.0D));
            data.set(D_FLOW_X10, scale(AirIntakeBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, blockPos);
            RoomScanResult scan = connection.room();
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirIntakeBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!connection.outsideConnected()) data.set(D_STATUS, 6);
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirIntakeBlockEntity.needsFreshAir(atmosphere) ? 7 : 5);
                setAtmosphere(scan, atmosphere);
            }
            if (scan != null) {
                if (get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
                setIntakeStats(IntakeNetworkScanner.inspect(level, scan));
            }
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }
"""
new_intake_update = """        if (serverBlockEntity instanceof AirIntakeBlockEntity be) {
            data.set(D_TYPE, TYPE_INTAKE);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            data.set(D_PRE, scale(AirIntakeBlockEntity.PERMANENT_DUST_EFFICIENCY * 100.0D, 10.0D));
            data.set(D_RAD, scale(AirIntakeBlockEntity.PERMANENT_RADIATION_EFFICIENCY * 100.0D, 10.0D));
            data.set(D_FLOW_X10, scale(AirIntakeBlockEntity.FLOW_M3_PER_SECOND, 10.0D));

            RoomEnvironmentManager.FalloutCondition fallout = RoomEnvironmentManager.falloutCondition(level, blockPos);
            data.set(D_INTAKE_MODE, be.mode().ordinal());
            data.set(D_FALLOUT_CONDITION, fallout.ordinal());
            data.set(D_FALLOUT_LOAD_PERCENT, scale(fallout.loadMultiplier() * 100.0D, 1.0D));
            data.set(D_OUTSIDE_DUST_X100, scale(RoomEnvironmentManager.intakeOutsideDust(level, blockPos), 100.0D));
            data.set(D_OUTSIDE_RAD_X100, scale(RoomEnvironmentManager.intakeOutsideAirborneRadiation(level, blockPos) * 3600.0D, 100.0D));
            data.set(D_INTAKE_AUTO_ISOLATED, be.autoIsolated(level, blockPos) ? 1 : 0);
            data.set(D_INTAKE_UNIT_FLOW_X10, scale(be.currentFlowM3PerSecond(), 10.0D));
            data.set(D_INTAKE_AUTO_THRESHOLD_PERCENT, scale(AirIntakeBlockEntity.AUTO_ISOLATION_LOAD * 100.0D, 1.0D));

            RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, blockPos);
            RoomScanResult scan = connection.room();
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (be.mode() == AirIntakeBlockEntity.IntakeMode.CLOSED) data.set(D_STATUS, 37);
            else if (be.autoIsolated(level, blockPos)) data.set(D_STATUS, 38);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirIntakeBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!connection.outsideConnected()) data.set(D_STATUS, 6);
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, be.currentFlowM3PerSecond() > 0.01D ? 7 : 5);
                setAtmosphere(scan, atmosphere);
            }
            if (scan != null) {
                if (get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
                setIntakeStats(IntakeNetworkScanner.inspect(level, scan));
            }
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }
"""
replace_one(menu, old_intake_update, new_intake_update)

replace_one(
    menu,
    "        if (id == BUTTON_ACTION && serverBlockEntity instanceof AirlockControllerBlockEntity be) {\n",
    "        if (serverBlockEntity instanceof AirIntakeBlockEntity be) {\n"
    "            AirIntakeBlockEntity.IntakeMode requested = switch (id) {\n"
    "                case BUTTON_INTAKE_OPEN -> AirIntakeBlockEntity.IntakeMode.OPEN;\n"
    "                case BUTTON_INTAKE_CLOSED -> AirIntakeBlockEntity.IntakeMode.CLOSED;\n"
    "                case BUTTON_INTAKE_AUTO -> AirIntakeBlockEntity.IntakeMode.AUTO;\n"
    "                default -> null;\n"
    "            };\n"
    "            if (requested != null) {\n"
    "                be.setMode(requested);\n"
    "                updateServerData();\n"
    "                return true;\n"
    "            }\n"
    "        }\n\n"
    "        if (id == BUTTON_ACTION && serverBlockEntity instanceof AirlockControllerBlockEntity be) {\n"
)

replace_one(
    menu,
    "    public double transferCapacity() { return get(D_TRANSFER_CAPACITY_X10) / 10.0D; }\n",
    "    public double transferCapacity() { return get(D_TRANSFER_CAPACITY_X10) / 10.0D; }\n"
    "    public int intakeMode() { return get(D_INTAKE_MODE); }\n"
    "    public int falloutCondition() { return get(D_FALLOUT_CONDITION); }\n"
    "    public int falloutLoadPercent() { return get(D_FALLOUT_LOAD_PERCENT); }\n"
    "    public double outsideDustPercent() { return get(D_OUTSIDE_DUST_X100) / 100.0D; }\n"
    "    public double outsideRadiation() { return get(D_OUTSIDE_RAD_X100) / 100.0D; }\n"
    "    public boolean intakeAutoIsolated() { return get(D_INTAKE_AUTO_ISOLATED) != 0; }\n"
    "    public double intakeUnitFlow() { return get(D_INTAKE_UNIT_FLOW_X10) / 10.0D; }\n"
    "    public int intakeAutoThresholdPercent() { return get(D_INTAKE_AUTO_THRESHOLD_PERCENT); }\n"
)

# -----------------------------------------------------------------------------
# MachineScreen: dedicated OPEN / CLOSED / AUTO controls and full fallout panel.
# -----------------------------------------------------------------------------
screen = ROOT / "src/main/java/dev/afterfall/client/MachineScreen.java"
replace_one(
    screen,
    "    private Button powerButton;\n"
    "    private Button actionButton;\n",
    "    private Button powerButton;\n"
    "    private Button actionButton;\n"
    "    private Button intakeOpenButton;\n"
    "    private Button intakeClosedButton;\n"
    "    private Button intakeAutoButton;\n"
)

replace_one(
    screen,
    "        if (menu.machineType() == MachineMenu.TYPE_AIRLOCK) {\n"
    "            actionButton = addRenderableWidget(Button.builder(Component.literal(\"START CYCLE\"), b -> sendButton(MachineMenu.BUTTON_ACTION))\n"
    "                    .bounds(leftPos + 166, topPos + 48, 66, 18).build());\n"
    "        }\n",
    "        if (menu.machineType() == MachineMenu.TYPE_AIRLOCK) {\n"
    "            actionButton = addRenderableWidget(Button.builder(Component.literal(\"START CYCLE\"), b -> sendButton(MachineMenu.BUTTON_ACTION))\n"
    "                    .bounds(leftPos + 166, topPos + 48, 66, 18).build());\n"
    "        } else if (menu.machineType() == MachineMenu.TYPE_INTAKE) {\n"
    "            intakeOpenButton = addRenderableWidget(Button.builder(Component.literal(\"OPEN\"), b -> sendButton(MachineMenu.BUTTON_INTAKE_OPEN))\n"
    "                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());\n"
    "            intakeClosedButton = addRenderableWidget(Button.builder(Component.literal(\"CLOSED\"), b -> sendButton(MachineMenu.BUTTON_INTAKE_CLOSED))\n"
    "                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());\n"
    "            intakeAutoButton = addRenderableWidget(Button.builder(Component.literal(\"AUTO\"), b -> sendButton(MachineMenu.BUTTON_INTAKE_AUTO))\n"
    "                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());\n"
    "        }\n"
)

replace_one(
    screen,
    "        if (actionButton != null) {\n"
    "            boolean busy = menu.get(MachineMenu.D_STATUS) >= 20;\n"
    "            actionButton.setMessage(Component.literal(busy ? \"CYCLE BUSY\" : \"PURGE/CYCLE\"));\n"
    "            actionButton.active = menu.enabled() && !busy;\n"
    "        }\n",
    "        if (actionButton != null) {\n"
    "            boolean busy = menu.get(MachineMenu.D_STATUS) >= 20;\n"
    "            actionButton.setMessage(Component.literal(busy ? \"CYCLE BUSY\" : \"PURGE/CYCLE\"));\n"
    "            actionButton.active = menu.enabled() && !busy;\n"
    "        }\n"
    "        if (intakeOpenButton != null) {\n"
    "            intakeOpenButton.setMessage(Component.literal(menu.intakeMode() == 0 ? \"[ OPEN ]\" : \"OPEN\"));\n"
    "            intakeClosedButton.setMessage(Component.literal(menu.intakeMode() == 1 ? \"[ CLOSED ]\" : \"CLOSED\"));\n"
    "            intakeAutoButton.setMessage(Component.literal(menu.intakeMode() == 2 ? \"[ AUTO ]\" : \"AUTO\"));\n"
    "        }\n"
)

old_render_intake = """    private void renderIntake(GuiGraphics graphics) {
        graphics.drawString(font, "Permanent outside-air pre-cleaner", 12, 88, 0xFFAAB6B9, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Dust removal %.0f%% | Rad aerosol %.0f%%",
                menu.prePercent(), menu.radPercent()), 12, 103, 0xFF9DB7BD, false);
        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        graphics.drawString(font, "Mixing room: " + volume + " m³", 12, 121, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 124, 121, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 12, 136, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 124, 136, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%% | CO2: %.2f%%", menu.oxygenPercent(), menu.co2Percent()),
                12, 151, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Fresh: %.1f / %.1f m³/s",
                menu.intakeInput(), menu.intakeCapacity()), 12, 174, 0xFF9DB7BD, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Demand %.1f m³/s | Network %d/%d ready",
                menu.intakeDemand(), menu.intakeReady(), menu.intakeTotal()),
                12, 193, 0xFF7F9298, false);
    }
"""
new_render_intake = """    private void renderIntake(GuiGraphics graphics) {
        String mode = intakeModeLabel();
        String fallout = falloutLabel();
        int falloutColor = falloutColor();
        String autoState = menu.intakeMode() != 2 ? "AUTO: --"
                : (menu.intakeAutoIsolated() ? "AUTO: ISOLATED" : "AUTO: ARMED");

        graphics.drawString(font, String.format(Locale.ROOT, "Mode: %s | AUTO isolates at %d%%",
                mode, menu.intakeAutoThresholdPercent()), 12, 111, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Fallout: %s | Ambient load %d%%",
                fallout, menu.falloutLoadPercent()), 12, 124, falloutColor, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Outside: Dust %.1f%% | Rad %.1f mSv/h",
                menu.outsideDustPercent(), menu.outsideRadiation()), 12, 137, falloutColor, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Fresh unit %.1f/%.1f | Demand %.1f m³/s",
                menu.intakeUnitFlow(), menu.flow(), menu.intakeDemand()), 12, 150, 0xFF9DB7BD, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Network %d/%d ready | %s",
                menu.intakeReady(), menu.intakeTotal(), autoState), 12, 163,
                menu.intakeAutoIsolated() ? 0xFFDF6262 : 0xFF7F9298, false);

        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        graphics.drawString(font, String.format(Locale.ROOT, "Mix %d m³ | Air %.1f%% | Dust %.2f%%",
                volume, menu.airQuality(), menu.dustPercent()), 12, 176, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "O2 %.2f%% | CO2 %.2f%% | Preclean D%.0f/R%.0f",
                menu.oxygenPercent(), menu.co2Percent(), menu.prePercent(), menu.radPercent()),
                12, 189, 0xFFD3DDDF, false);
    }
"""
replace_one(screen, old_render_intake, new_render_intake)

replace_one(
    screen,
    "            case 36 -> \"ERROR - INPUT = OUTPUT VOLUME\";\n"
    "            default -> \"INITIALIZING\";\n",
    "            case 36 -> \"ERROR - INPUT = OUTPUT VOLUME\";\n"
    "            case 37 -> \"ISOLATED - CLOSED\";\n"
    "            case 38 -> \"AUTO ISOLATED - FALLOUT\";\n"
    "            default -> \"INITIALIZING\";\n"
)
replace_one(
    screen,
    "        if (status == 17) return 0xFF8A979B;\n",
    "        if (status == 17 || status == 37) return 0xFF8A979B;\n"
)

replace_one(
    screen,
    "    private String powerSource() {\n",
    "    private String intakeModeLabel() {\n"
    "        return switch (menu.intakeMode()) {\n"
    "            case 0 -> \"OPEN\";\n"
    "            case 1 -> \"CLOSED\";\n"
    "            default -> \"AUTO\";\n"
    "        };\n"
    "    }\n\n"
    "    private String falloutLabel() {\n"
    "        return switch (menu.falloutCondition()) {\n"
    "            case 1 -> \"ELEVATED\";\n"
    "            case 2 -> \"SEVERE\";\n"
    "            default -> \"NORMAL\";\n"
    "        };\n"
    "    }\n\n"
    "    private int falloutColor() {\n"
    "        return switch (menu.falloutCondition()) {\n"
    "            case 1 -> 0xFFE1B45A;\n"
    "            case 2 -> 0xFFDF6262;\n"
    "            default -> 0xFF66C477;\n"
    "        };\n"
    "    }\n\n"
    "    private String powerSource() {\n"
)

print("Applied Afterfall 0.8.5.1 Intake Control Panel patch")
