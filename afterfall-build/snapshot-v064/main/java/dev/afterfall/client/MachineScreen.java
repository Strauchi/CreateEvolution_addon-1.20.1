package dev.afterfall.client;

import dev.afterfall.menu.MachineMenu;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;

import java.util.Locale;

public final class MachineScreen extends AbstractContainerScreen<MachineMenu> {
    private static final int PANEL_W = 244;
    private static final int PANEL_H = 188;

    public MachineScreen(MachineMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title);
        this.imageWidth = PANEL_W;
        this.imageHeight = PANEL_H;
        this.inventoryLabelY = 10_000; // no vanilla inventory slots in the 0.6 dashboard
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        renderBackground(graphics, mouseX, mouseY, partialTick);
        super.render(graphics, mouseX, mouseY, partialTick);
        renderTooltip(graphics, mouseX, mouseY);
    }

    @Override
    protected void renderBg(GuiGraphics graphics, float partialTick, int mouseX, int mouseY) {
        int x = leftPos;
        int y = topPos;
        graphics.fill(x, y, x + imageWidth, y + imageHeight, 0xE614181A);
        graphics.fill(x + 1, y + 1, x + imageWidth - 1, y + 22, 0xFF242B2E);
        graphics.fill(x + 7, y + 30, x + imageWidth - 7, y + imageHeight - 8, 0xCC0B0E10);

        drawEnergyBar(graphics, x + 12, y + 47, 104, 9);
        if (menu.get(MachineMenu.D_TYPE) != MachineMenu.TYPE_GENERATOR) {
            drawFilterBar(graphics, x + 12, y + 88, 67, menu.prePercent());
            drawFilterBar(graphics, x + 88, y + 88, 67, menu.hepaPercent());
            drawFilterBar(graphics, x + 164, y + 88, 67, menu.radPercent());
        }
    }

    @Override
    protected void renderLabels(GuiGraphics graphics, int mouseX, int mouseY) {
        graphics.drawString(font, machineTitle(), 9, 8, 0xFFE8ECEE, false);
        graphics.drawString(font, statusText(), 12, 29, statusColor(), false);

        int stored = menu.get(MachineMenu.D_ENERGY) * 10;
        int max = Math.max(10, menu.get(MachineMenu.D_ENERGY_MAX) * 10);
        graphics.drawString(font, String.format(Locale.ROOT, "Energy  %,d / %,d FE", stored, max), 12, 38, 0xFFB7C4C8, false);
        graphics.drawString(font, "Source  " + powerSource(), 124, 38, 0xFFB7C4C8, false);

        if (menu.get(MachineMenu.D_TYPE) == MachineMenu.TYPE_GENERATOR) {
            renderGenerator(graphics);
            return;
        }

        graphics.drawString(font, "Pre-Filter", 12, 76, 0xFFAAB6B9, false);
        graphics.drawString(font, "HEPA", 88, 76, 0xFFAAB6B9, false);
        graphics.drawString(font, "RAD", 164, 76, 0xFFAAB6B9, false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.prePercent()), 12, 100, filterColor(menu.prePercent()), false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.hepaPercent()), 88, 100, filterColor(menu.hepaPercent()), false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.radPercent()), 164, 100, filterColor(menu.radPercent()), false);

        graphics.drawString(font, "Filter condition: " + filterCondition(), 12, 116, filterConditionColor(), false);

        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        if (volume > 0) {
            graphics.drawString(font, "Room: " + volume + " m³", 12, 134, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 124, 134, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 12, 147, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 124, 147, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%%", menu.oxygenPercent()), 12, 160, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "CO2: %.2f%%", menu.co2Percent()), 124, 160, 0xFFD3DDDF, false);
        }

        if (menu.get(MachineMenu.D_TYPE) == MachineMenu.TYPE_FILTER || menu.get(MachineMenu.D_TYPE) == MachineMenu.TYPE_INTAKE) {
            graphics.drawString(font, String.format(Locale.ROOT, "Rated airflow: %.1f m³/s", menu.flow()), 12, 173, 0xFF7F9298, false);
        } else if (menu.get(MachineMenu.D_TYPE) == MachineMenu.TYPE_AIRLOCK) {
            graphics.drawString(font, "Cycle: " + airlockCycle(), 12, 173, 0xFF7F9298, false);
        }
    }

    private void renderGenerator(GuiGraphics graphics) {
        graphics.drawString(font, String.format(Locale.ROOT, "Generation: %.0f FE/t", menu.flow()), 12, 76, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Fuel remaining: %.1f s", menu.get(MachineMenu.D_EXTRA) / 20.0D), 12, 92, 0xFFD3DDDF, false);
        graphics.drawString(font, "Fuel: coal / charcoal / coal block", 12, 116, 0xFF7F9298, false);
        graphics.drawString(font, "Right-click with fuel to load generator.", 12, 132, 0xFF7F9298, false);
    }

    private void drawEnergyBar(GuiGraphics graphics, int x, int y, int width, int height) {
        int stored = menu.get(MachineMenu.D_ENERGY);
        int max = Math.max(1, menu.get(MachineMenu.D_ENERGY_MAX));
        int fill = (int) Math.round(width * Math.min(1.0D, stored / (double) max));
        graphics.fill(x, y, x + width, y + height, 0xFF24282A);
        graphics.fill(x + 1, y + 1, x + Math.max(1, fill - 1), y + height - 1, 0xFFB7C05C);
    }

    private void drawFilterBar(GuiGraphics graphics, int x, int y, int width, double percent) {
        int fill = (int) Math.round(width * Math.max(0.0D, Math.min(100.0D, percent)) / 100.0D);
        graphics.fill(x, y, x + width, y + 7, 0xFF24282A);
        int color = percent < 10.0D ? 0xFFC84C4C : percent < 25.0D ? 0xFFD79747 : 0xFF6FAE78;
        graphics.fill(x + 1, y + 1, x + Math.max(1, fill - 1), y + 6, color);
    }

    private String machineTitle() {
        return switch (menu.get(MachineMenu.D_TYPE)) {
            case MachineMenu.TYPE_INTAKE -> "AFTERFALL // AIR INTAKE UNIT";
            case MachineMenu.TYPE_AIRLOCK -> "AFTERFALL // AIRLOCK CONTROLLER";
            case MachineMenu.TYPE_GENERATOR -> "AFTERFALL // EMERGENCY GENERATOR";
            default -> "AFTERFALL // AIR FILTRATION UNIT";
        };
    }

    private String statusText() {
        int status = menu.get(MachineMenu.D_STATUS);
        if (status >= 20) return "AUTOMATIC CYCLE: " + airlockCycle();
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
            default -> "INITIALIZING";
        };
    }

    private int statusColor() {
        int status = menu.get(MachineMenu.D_STATUS);
        if (status == 5 || status == 8 || status == 9 || status == 16) return 0xFF66C477;
        if (status == 4 || status == 7 || status >= 20) return 0xFFE1B45A;
        return 0xFFDF6262;
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
