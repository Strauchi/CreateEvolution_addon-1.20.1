package dev.afterfall.client;

import dev.afterfall.menu.MachineMenu;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;

import java.util.Locale;

public final class MachineScreen extends AbstractContainerScreen<MachineMenu> {
    private static final int PANEL_W = 244;
    private static final int PANEL_H = 304;
    private Button powerButton;
    private Button actionButton;
    private Button intakeOpenButton;
    private Button intakeClosedButton;
    private Button intakeAutoButton;
    private Button scrubberScrubButton;
    private Button scrubberBypassButton;
    private Button scrubberAutoButton;
    private Button powerBankAutoButton;
    private Button powerBankCriticalButton;
    private Button powerBankAllButton;

    public MachineScreen(MachineMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title);
        this.imageWidth = PANEL_W;
        this.imageHeight = PANEL_H;
        this.inventoryLabelY = 10_000;
    }

    @Override
    protected void init() {
        super.init();
        powerButton = addRenderableWidget(Button.builder(Component.literal("POWER"), b -> sendButton(MachineMenu.BUTTON_POWER))
                .bounds(leftPos + 166, topPos + 26, 66, 18).build());
        if (menu.machineType() == MachineMenu.TYPE_AIRLOCK) {
            actionButton = addRenderableWidget(Button.builder(Component.literal("START CYCLE"), b -> sendButton(MachineMenu.BUTTON_ACTION))
                    .bounds(leftPos + 166, topPos + 48, 66, 18).build());
        } else if (menu.machineType() == MachineMenu.TYPE_INTAKE) {
            intakeOpenButton = addRenderableWidget(Button.builder(Component.literal("OPEN"), b -> sendButton(MachineMenu.BUTTON_INTAKE_OPEN))
                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());
            intakeClosedButton = addRenderableWidget(Button.builder(Component.literal("CLOSED"), b -> sendButton(MachineMenu.BUTTON_INTAKE_CLOSED))
                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());
            intakeAutoButton = addRenderableWidget(Button.builder(Component.literal("AUTO"), b -> sendButton(MachineMenu.BUTTON_INTAKE_AUTO))
                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());
        } else if (menu.machineType() == MachineMenu.TYPE_SCRUBBER) {
            scrubberScrubButton = addRenderableWidget(Button.builder(Component.literal("SCRUB"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_SCRUB))
                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());
            scrubberBypassButton = addRenderableWidget(Button.builder(Component.literal("BYPASS"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_BYPASS))
                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());
            scrubberAutoButton = addRenderableWidget(Button.builder(Component.literal("AUTO"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_AUTO))
                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());
        } else if (menu.machineType() == MachineMenu.TYPE_POWER_BANK) {
            powerBankAutoButton = addRenderableWidget(Button.builder(Component.literal("AUTO"), b -> sendButton(MachineMenu.BUTTON_POWERBANK_AUTO))
                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());
            powerBankCriticalButton = addRenderableWidget(Button.builder(Component.literal("CRITICAL"), b -> sendButton(MachineMenu.BUTTON_POWERBANK_CRITICAL))
                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());
            powerBankAllButton = addRenderableWidget(Button.builder(Component.literal("ALL"), b -> sendButton(MachineMenu.BUTTON_POWERBANK_ALL))
                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());
        }
    }

    private void sendButton(int id) {
        if (minecraft != null && minecraft.gameMode != null) {
            minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
        }
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        updateButtons();
        renderBackground(graphics, mouseX, mouseY, partialTick);
        super.render(graphics, mouseX, mouseY, partialTick);
        renderTooltip(graphics, mouseX, mouseY);
    }

    private void updateButtons() {
        if (powerButton != null) {
            powerButton.setMessage(Component.literal(menu.enabled() ? "POWER: ON" : "POWER: OFF"));
            powerButton.active = !(menu.machineType() == MachineMenu.TYPE_AIRLOCK && menu.get(MachineMenu.D_STATUS) >= 20 && menu.enabled());
        }
        if (actionButton != null) {
            boolean busy = menu.get(MachineMenu.D_STATUS) >= 20;
            actionButton.setMessage(Component.literal(busy ? "CYCLE BUSY" : "PURGE/CYCLE"));
            actionButton.active = menu.enabled() && !busy;
        }
        if (intakeOpenButton != null) {
            intakeOpenButton.setMessage(Component.literal(menu.intakeMode() == 0 ? "[ OPEN ]" : "OPEN"));
            intakeClosedButton.setMessage(Component.literal(menu.intakeMode() == 1 ? "[ CLOSED ]" : "CLOSED"));
            intakeAutoButton.setMessage(Component.literal(menu.intakeMode() == 2 ? "[ AUTO ]" : "AUTO"));
        }
        if (scrubberScrubButton != null) {
            scrubberScrubButton.setMessage(Component.literal(menu.scrubberMode() == 0 ? "[ SCRUB ]" : "SCRUB"));
            scrubberBypassButton.setMessage(Component.literal(menu.scrubberMode() == 1 ? "[ BYPASS ]" : "BYPASS"));
            scrubberAutoButton.setMessage(Component.literal(menu.scrubberMode() == 2 ? "[ AUTO ]" : "AUTO"));
        }
        if (powerBankAutoButton != null) {
            powerBankAutoButton.setMessage(Component.literal(menu.powerBankMode() == 0 ? "[ AUTO ]" : "AUTO"));
            powerBankCriticalButton.setMessage(Component.literal(menu.powerBankMode() == 1 ? "[ CRITICAL ]" : "CRITICAL"));
            powerBankAllButton.setMessage(Component.literal(menu.powerBankMode() == 2 ? "[ ALL ]" : "ALL"));
        }
    }

    @Override
    protected void renderBg(GuiGraphics graphics, float partialTick, int mouseX, int mouseY) {
        int x = leftPos;
        int y = topPos;
        graphics.fill(x, y, x + imageWidth, y + imageHeight, 0xE614181A);
        graphics.fill(x + 1, y + 1, x + imageWidth - 1, y + 22, 0xFF242B2E);
        graphics.fill(x + 7, y + 30, x + imageWidth - 7, y + imageHeight - 8, 0xCC0B0E10);

        drawEnergyBar(graphics, x + 12, y + 75, 140, 9);

        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            drawSlotBox(graphics, x + MachineMenu.FUEL_SLOT_X, y + MachineMenu.FUEL_SLOT_Y);
        } else if (menu.machineType() == MachineMenu.TYPE_FILTER || menu.machineType() == MachineMenu.TYPE_AIRLOCK) {
            for (int i = 0; i < 3; i++) drawSlotBox(graphics, x + MachineMenu.FILTER_SLOT_X[i], y + MachineMenu.FILTER_SLOT_Y);
            drawFilterBar(graphics, x + 12, y + 116, 60, menu.prePercent());
            drawFilterBar(graphics, x + 92, y + 116, 60, menu.hepaPercent());
            drawFilterBar(graphics, x + 172, y + 116, 60, menu.radPercent());
        }

        // Player inventory slot backgrounds.
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                drawSlotBox(graphics, x + MachineMenu.PLAYER_INV_X + col * 18, y + MachineMenu.PLAYER_INV_Y + row * 18);
            }
        }
        for (int col = 0; col < 9; col++) drawSlotBox(graphics, x + MachineMenu.PLAYER_INV_X + col * 18, y + MachineMenu.HOTBAR_Y);
    }

    @Override
    protected void renderLabels(GuiGraphics graphics, int mouseX, int mouseY) {
        graphics.drawString(font, machineTitle(), 9, 8, 0xFFE8ECEE, false);
        graphics.drawString(font, statusText(), 12, 29, statusColor(), false);

        int stored = menu.get(MachineMenu.D_ENERGY) * 10;
        int max = Math.max(10, menu.get(MachineMenu.D_ENERGY_MAX) * 10);
        graphics.drawString(font, String.format(Locale.ROOT, "Energy: %,d / %,d FE", stored, max), 12, 50, 0xFFB7C4C8, false);
        graphics.drawString(font, "Source: " + powerSource(), 12, 63, 0xFF829399, false);

        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            renderGenerator(graphics);
        } else if (menu.machineType() == MachineMenu.TYPE_FAN) {
            renderFan(graphics);
        } else if (menu.machineType() == MachineMenu.TYPE_INTAKE) {
            renderIntake(graphics);
        } else if (menu.machineType() == MachineMenu.TYPE_SCRUBBER) {
            renderScrubber(graphics);
        } else if (menu.machineType() == MachineMenu.TYPE_POWER_BANK) {
            renderPowerBank(graphics);
        } else {
            renderFilters(graphics);
        }
        graphics.drawString(font, "INVENTORY", 12, 207, 0xFF7F9298, false);
    }

    private void renderFilters(GuiGraphics graphics) {
        graphics.drawString(font, "Pre-Filter", 12, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, "HEPA", 92, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, "RAD", 172, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.prePercent()), 12, 126, filterColor(menu.prePercent()), false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.hepaPercent()), 92, 126, filterColor(menu.hepaPercent()), false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.radPercent()), 172, 126, filterColor(menu.radPercent()), false);
        graphics.drawString(font, "Filter condition: " + filterCondition(), 12, 140, filterConditionColor(), false);

        if (menu.machineType() == MachineMenu.TYPE_FILTER) {
            graphics.drawString(font, String.format(Locale.ROOT, "BACK input: %d m³ | Dust %.2f%%",
                    menu.inputRoomVolume(), menu.inputDustPercent()), 12, 154, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Input Air Rad: %.2f mSv/h", menu.inputAirRadiation()),
                    12, 167, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "FRONT output: %d m³ | Air %.1f%%",
                    menu.get(MachineMenu.D_ROOM_VOLUME), menu.airQuality()), 12, 180, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust %.2f%% | Rad %.2f | Flow %.1f m³/s",
                    menu.dustPercent(), menu.airRadiation(), menu.flow()), 12, 193, 0xFF9DB7BD, false);
            return;
        }

        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        if (volume > 0) {
            graphics.drawString(font, "Room: " + volume + " m³", 12, 155, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 124, 155, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 12, 168, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 124, 168, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%%", menu.oxygenPercent()), 12, 181, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "CO2: %.2f%%", menu.co2Percent()), 124, 181, 0xFFD3DDDF, false);
        }
        graphics.drawString(font, "Cycle: " + airlockCycle(), 12, 194, 0xFF7F9298, false);
    }

    private void renderScrubber(GuiGraphics graphics) {
        int inputVolume = menu.inputRoomVolume();
        int outputVolume = menu.get(MachineMenu.D_ROOM_VOLUME);
        double actualEq = menu.scrubberActualEq();
        double actualFlow = menu.scrubberActualFlow();
        double maxFlow = menu.flow();
        int energyUse = menu.scrubberEnergyUse();
        boolean effectiveScrub = menu.scrubberMode() == 0
                || (menu.scrubberMode() == 2 && menu.scrubberAutoScrubbing());
        String selectedMode = switch (menu.scrubberMode()) {
            case 0 -> "SCRUB";
            case 1 -> "BYPASS";
            default -> "AUTO";
        };
        String effective = effectiveScrub ? "SCRUBBING" : "BYPASS";
        int effectiveColor = effectiveScrub ? 0xFFE1B45A : 0xFF66C477;

        graphics.drawString(font, "CO2 TREATMENT // O2 IS NOT GENERATED", 12, 111, 0xFFE1B45A, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Mode %s | Effective: %s",
                selectedMode, effective), 12, 124, effectiveColor, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Fresh: %.1f m³/s | Available %.1f m³/s",
                menu.scrubberFreshInput(), menu.scrubberFreshCapacity()), 12, 137,
                menu.scrubberFreshCapacity() > 0.1D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "BACK %d m³ CO2 %.3f%% | FRONT %d m³ %.3f%%",
                inputVolume, menu.scrubberInputCo2(), outputVolume, menu.scrubberOutputCo2()),
                12, 150, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Airflow: %.1f / %.1f m³/s",
                actualFlow, maxFlow), 12, 163, actualFlow > 0.01D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, effectiveScrub
                ? String.format(Locale.ROOT, "CO2: -%.5f%%/min | Support %.2f/%.2f eq",
                    menu.scrubberRemovalPerMinute(), actualEq, menu.scrubberNominalEq())
                : "CO2 removal: OFF | High-flow bypass active",
                12, 176, effectiveScrub && actualEq > 0.0001D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Power: %,d / %,d FE/s | %s",
                energyUse, 1200, effectiveScrub ? "treatment" : "bypass: 0 FE"),
                12, 189, energyUse > 0 ? 0xFF9DB7BD : 0xFF7F9298, false);
    }

    private void renderIntake(GuiGraphics graphics) {
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

    private void renderFan(GuiGraphics graphics) {
        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        graphics.drawString(font, "Ventilation shaft", 12, 88, 0xFFAAB6B9, false);
        graphics.drawString(font, "Supply shaft: " + volume + " m³", 12, 103, 0xFFD3DDDF, false);
        graphics.drawString(font, "Supply vents: " + menu.get(MachineMenu.D_EXTRA)
                + " | Return vents: " + menu.returnVentCount(), 12, 116, 0xFFD3DDDF, false);
        String filterCap = menu.industrialCapacity() > 0.0D
                ? String.format(Locale.ROOT, "%.1f", menu.industrialCapacity()) : "--";
        graphics.drawString(font, String.format(Locale.ROOT, "Fan %.1f m³/s | Industrial cap %s m³/s", menu.flow(), filterCap),
                12, 129, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Supply flow: %.1f | Return flow: %.1f m³/s",
                menu.supplyFlow(), menu.returnFlow()), 12, 140, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Fresh %.1f/%.1f | Demand %.1f m³/s",
                menu.intakeInput(), menu.intakeCapacity(), menu.intakeDemand()),
                12, 153, 0xFF9DB7BD, false);
        String transferCap = menu.transferCapacity() > 0.0D
                ? String.format(Locale.ROOT, "%.1f", menu.transferCapacity()) : "--";
        graphics.drawString(font, String.format(Locale.ROOT, "I %d/%d | P:%d H:%d R:%d | X:%d cap %s",
                menu.intakeReady(), menu.intakeTotal(), menu.industrialPreBlocks(),
                menu.industrialHepaBlocks(), menu.industrialRadBlocks(),
                menu.transferVentCount(), transferCap),
                12, 166, 0xFF9DB7BD, false);
        if (volume > 0) {
            graphics.drawString(font, String.format(Locale.ROOT, "Air %.1f%% | Dust %.2f%% | Rad %.2f",
                    menu.airQuality(), menu.dustPercent(), menu.airRadiation()), 12, 179, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2 %.2f%% | CO2 %.2f%%",
                    menu.oxygenPercent(), menu.co2Percent()), 12, 192, 0xFFD3DDDF, false);
        }
    }

    private void renderPowerBank(GuiGraphics graphics) {
        String mode = switch (menu.powerBankMode()) {
            case 1 -> "CRITICAL";
            case 2 -> "ALL";
            default -> "AUTO";
        };
        String auxState = menu.powerBankAuxAvailable() ? "ENABLED" : "SHED";
        int auxColor = menu.powerBankAuxAvailable() ? 0xFF66C477 : 0xFFE1B45A;
        int runtime = menu.powerBankRuntimeSeconds();
        String runtimeText = runtime < 0 ? "-- (no measured load)"
                : String.format(Locale.ROOT, "%dm %02ds", runtime / 60, runtime % 60);

        graphics.drawString(font, "BUNKER UPS // PHYSICAL LOAD PRIORITY", 12, 111, 0xFF8EC9D1, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Mode %s | Reserve floor %d%%",
                mode, menu.powerBankReservePercent()), 12, 124, 0xFFD3DDDF, false);
        graphics.drawString(font, "Ports: BACK charge | FRONT critical | SIDES auxiliary",
                12, 137, 0xFF9DB7BD, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Charge input: %,d / %,d FE/t",
                menu.powerBankInputPerTick(), 2000), 12, 150, 0xFF9DB7BD, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Critical bus: %,d / %,d FE/t",
                menu.powerBankCriticalOut(), menu.powerBankCriticalCap()), 12, 163,
                menu.powerBankCriticalOut() > 0 ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Aux bus: %,d / %,d FE/t | %s",
                menu.powerBankAuxOut(), menu.powerBankAuxCap(), auxState), 12, 176, auxColor, false);
        graphics.drawString(font, "Runtime at measured load: " + runtimeText,
                12, 189, runtime >= 0 ? 0xFFE1B45A : 0xFF7F9298, false);
    }

    private void renderGenerator(GuiGraphics graphics) {
        graphics.drawString(font, "Fuel", 12, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Generation: %.0f FE/t", menu.flow()), 54, 96, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Burn remaining: %.1f s", menu.get(MachineMenu.D_EXTRA) / 20.0D), 54, 109, 0xFFD3DDDF, false);
        graphics.drawString(font, "Accepted: coal / charcoal / coal block", 12, 130, 0xFF7F9298, false);
        graphics.drawString(font, "Fuel is consumed automatically from the slot.", 12, 143, 0xFF7F9298, false);
    }

    private void drawSlotBox(GuiGraphics graphics, int x, int y) {
        graphics.fill(x - 1, y - 1, x + 17, y + 17, 0xFF4A5255);
        graphics.fill(x, y, x + 16, y + 16, 0xFF171B1D);
    }

    private void drawEnergyBar(GuiGraphics graphics, int x, int y, int width, int height) {
        int stored = menu.get(MachineMenu.D_ENERGY);
        int max = Math.max(1, menu.get(MachineMenu.D_ENERGY_MAX));
        int fill = (int) Math.round(width * Math.min(1.0D, stored / (double) max));
        graphics.fill(x, y, x + width, y + height, 0xFF24282A);
        if (fill > 0) graphics.fill(x + 1, y + 1, x + Math.max(1, fill - 1), y + height - 1, 0xFFB7C05C);
    }

    private void drawFilterBar(GuiGraphics graphics, int x, int y, int width, double percent) {
        int fill = (int) Math.round(width * Math.max(0.0D, Math.min(100.0D, percent)) / 100.0D);
        graphics.fill(x, y, x + width, y + 7, 0xFF24282A);
        int color = percent < 10.0D ? 0xFFC84C4C : percent < 25.0D ? 0xFFD79747 : 0xFF6FAE78;
        if (fill > 0) graphics.fill(x + 1, y + 1, x + Math.max(1, fill - 1), y + 6, color);
    }

    private String machineTitle() {
        return switch (menu.machineType()) {
            case MachineMenu.TYPE_INTAKE -> "AFTERFALL // AIR INTAKE UNIT";
            case MachineMenu.TYPE_AIRLOCK -> "AFTERFALL // AIRLOCK CONTROLLER";
            case MachineMenu.TYPE_GENERATOR -> "AFTERFALL // EMERGENCY GENERATOR";
            case MachineMenu.TYPE_FAN -> "AFTERFALL // VENTILATION FAN";
            case MachineMenu.TYPE_SCRUBBER -> "AFTERFALL // CO2 SCRUBBER";
            case MachineMenu.TYPE_POWER_BANK -> "AFTERFALL // EMERGENCY POWER BANK";
            default -> "AFTERFALL // COMPACT AIR FILTRATION UNIT";
        };
    }

    private String statusText() {
        int status = menu.get(MachineMenu.D_STATUS);
        if (menu.machineType() == MachineMenu.TYPE_AIRLOCK && status >= 20) return "CYCLE: " + airlockCycle();
        return switch (status) {
            case 1 -> "OFFLINE - NO POWER";
            case 2 -> "ERROR - NO SEALED ROOM";
            case 3 -> "FILTER MEDIA REQUIRED";
            case 4 -> "FILTERING";
            case 5 -> "STANDBY";
            case 6 -> "ERROR - NO OUTSIDE CONNECTION";
            case 7 -> "VENTILATING";
            case 8 -> "RUNNING";
            case 9 -> "BUFFERED";
            case 10 -> "NO FUEL";
            case 11 -> "NOT CONFIGURED";
            case 12 -> "DOOR OPEN / INTERLOCK";
            case 13 -> "CHAMBER NOT SEALED";
            case 14 -> "CHAMBER TOO LARGE";
            case 15 -> "UNSAFE - READY TO PURGE";
            case 16 -> "SAFE TO OPEN";
            case 17 -> "SWITCHED OFF";
            case 30 -> "ERROR - SHAFT NOT SEALED";
            case 31 -> "PRIMING SHAFT - NO VENTS";
            case 32 -> "CIRCULATING";
            case 33 -> "ERROR - NO SEALED INLET";
            case 34 -> "ERROR - NO SEALED BACK INPUT";
            case 35 -> "ERROR - NO SEALED FRONT OUTPUT";
            case 36 -> "ERROR - INPUT = OUTPUT VOLUME";
            case 37 -> "ISOLATED - CLOSED";
            case 38 -> "AUTO ISOLATED - FALLOUT";
            case 39 -> "READY - WAITING FOR AIRFLOW";
            case 40 -> "BYPASS - MAX AIRFLOW";
            case 41 -> "AUTO BYPASS - FRESH AIR AVAILABLE";
            case 42 -> "NORMAL DISTRIBUTION";
            case 43 -> "RESERVE ACTIVE - AUX LOAD SHED";
            case 44 -> "CRITICAL BUS ONLY";
            case 45 -> "RESERVE EMPTY";
            default -> "INITIALIZING";
        };
    }

    private int statusColor() {
        int status = menu.get(MachineMenu.D_STATUS);
        if (status == 17 || status == 37) return 0xFF8A979B;
        if (status == 5 || status == 8 || status == 9 || status == 16 || status == 32
                || status == 40 || status == 41 || status == 42) return 0xFF66C477;
        if (status == 4 || status == 7 || status == 31 || status == 39 || status == 43 || status == 44
                || (menu.machineType() == MachineMenu.TYPE_AIRLOCK && status >= 20)) return 0xFFE1B45A;
        return 0xFFDF6262;
    }

    private String intakeModeLabel() {
        return switch (menu.intakeMode()) {
            case 0 -> "OPEN";
            case 1 -> "CLOSED";
            default -> "AUTO";
        };
    }

    private String falloutLabel() {
        return switch (menu.falloutCondition()) {
            case 1 -> "ELEVATED";
            case 2 -> "SEVERE";
            default -> "NORMAL";
        };
    }

    private int falloutColor() {
        return switch (menu.falloutCondition()) {
            case 1 -> 0xFFE1B45A;
            case 2 -> 0xFFDF6262;
            default -> 0xFF66C477;
        };
    }

    private String powerSource() {
        return switch (menu.get(MachineMenu.D_POWER_SOURCE)) {
            case 1 -> "FE";
            case 2 -> "REDSTONE LEGACY";
            case 3 -> "INTERNAL";
            default -> "NONE";
        };
    }

    private String filterCondition() {
        return switch (menu.get(MachineMenu.D_FILTER_CONDITION)) {
            case 1 -> "DEGRADED";
            case 2 -> "CRITICAL";
            case 3 -> "EXHAUSTED";
            default -> "OK";
        };
    }

    private int filterConditionColor() {
        return switch (menu.get(MachineMenu.D_FILTER_CONDITION)) {
            case 1 -> 0xFFE1B45A;
            case 2, 3 -> 0xFFDF6262;
            default -> 0xFF66C477;
        };
    }

    private int filterColor(double percent) {
        return percent < 10.0D ? 0xFFDF6262 : percent < 25.0D ? 0xFFE1B45A : 0xFF66C477;
    }

    private String airlockCycle() {
        int state = menu.get(MachineMenu.D_EXTRA);
        String[] labels = {"IDLE", "PREPARING ENTRY", "WAITING FOR ENTRY", "SEALING ENTRY", "PURGING", "OPENING EXIT", "WAITING FOR EXIT", "SEALING EXIT"};
        return state >= 0 && state < labels.length ? labels[state] : "UNKNOWN";
    }
}
