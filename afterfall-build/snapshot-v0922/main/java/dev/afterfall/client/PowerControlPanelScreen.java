package dev.afterfall.client;

import dev.afterfall.blockentity.PowerControlPanelBlockEntity;
import dev.afterfall.menu.PowerControlPanelMenu;
import dev.afterfall.network.PowerNetworking;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;
import net.neoforged.neoforge.network.PacketDistributor;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class PowerControlPanelScreen extends AbstractContainerScreen<PowerControlPanelMenu> {
    private static final int ROWS = 6;
    private final List<Button> rowButtons = new ArrayList<>();
    private Button prevButton;
    private Button nextButton;
    private Button criticalButton;
    private Button auxButton;
    private Button onButton;
    private Button offButton;
    private int page;
    private UUID selectedId;

    public PowerControlPanelScreen(PowerControlPanelMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title);
        imageWidth = 340;
        imageHeight = 292;
        inventoryLabelY = 10_000;
    }

    @Override
    protected void init() {
        super.init();
        rowButtons.clear();
        for (int i = 0; i < ROWS; i++) {
            final int row = i;
            rowButtons.add(addRenderableWidget(Button.builder(Component.literal("--"), b -> selectRow(row))
                    .bounds(leftPos + 12, topPos + 54 + i * 24, 316, 20).build()));
        }
        prevButton = addRenderableWidget(Button.builder(Component.literal("<"), b -> page = Math.max(0, page - 1))
                .bounds(leftPos + 12, topPos + 202, 30, 18).build());
        nextButton = addRenderableWidget(Button.builder(Component.literal(">"), b -> page++)
                .bounds(leftPos + 298, topPos + 202, 30, 18).build());
        criticalButton = addRenderableWidget(Button.builder(Component.literal("CRITICAL"), b -> sendSelected(PowerNetworking.CMD_CRITICAL))
                .bounds(leftPos + 12, topPos + 230, 76, 18).build());
        auxButton = addRenderableWidget(Button.builder(Component.literal("AUX"), b -> sendSelected(PowerNetworking.CMD_AUX))
                .bounds(leftPos + 94, topPos + 230, 76, 18).build());
        onButton = addRenderableWidget(Button.builder(Component.literal("ON"), b -> sendSelected(PowerNetworking.CMD_ON))
                .bounds(leftPos + 176, topPos + 230, 70, 18).build());
        offButton = addRenderableWidget(Button.builder(Component.literal("OFF"), b -> sendSelected(PowerNetworking.CMD_OFF))
                .bounds(leftPos + 252, topPos + 230, 76, 18).build());
    }

    private void selectRow(int row) {
        int index = page * ROWS + row;
        List<PowerNetworking.TapEntry> entries = menu.entries();
        if (index >= 0 && index < entries.size()) selectedId = entries.get(index).id();
    }

    private PowerNetworking.TapEntry selected() {
        if (selectedId == null) return null;
        for (PowerNetworking.TapEntry entry : menu.entries()) if (entry.id().equals(selectedId)) return entry;
        return null;
    }

    private void sendSelected(int command) {
        PowerNetworking.TapEntry entry = selected();
        if (entry == null) return;
        PacketDistributor.sendToServer(new PowerNetworking.PanelCommandPayload(menu.panelPos(), entry.id(), command));
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        updateButtons();
        renderBackground(graphics, mouseX, mouseY, partialTick);
        super.render(graphics, mouseX, mouseY, partialTick);
        renderTooltip(graphics, mouseX, mouseY);
    }

    private void updateButtons() {
        List<PowerNetworking.TapEntry> entries = menu.entries();
        int pages = Math.max(1, (entries.size() + ROWS - 1) / ROWS);
        if (page >= pages) page = pages - 1;
        if (page < 0) page = 0;
        for (int row = 0; row < ROWS; row++) {
            int index = page * ROWS + row;
            Button button = rowButtons.get(row);
            if (index >= entries.size()) {
                button.visible = false;
                continue;
            }
            button.visible = true;
            PowerNetworking.TapEntry entry = entries.get(index);
            String circuit = entry.circuit() == 0 ? "CRIT" : "AUX";
            String state = entry.relay() ? "ON" : "OFF";
            if (entry.circuit() == 1) {
                if (entry.auxState() == 1) state += "/SHED";
                else if (entry.auxState() == 2) state += "/REARM";
            }
            String marker = entry.id().equals(selectedId) ? "> " : "  ";
            button.setMessage(Component.literal(marker + entry.name() + " | " + circuit + " | " + state
                    + " | " + entry.outputPerTick() + " FE/t"));
        }
        if (prevButton != null) prevButton.active = page > 0;
        if (nextButton != null) nextButton.active = page + 1 < pages;
        boolean selected = selected() != null;
        if (criticalButton != null) criticalButton.active = selected;
        if (auxButton != null) auxButton.active = selected;
        if (onButton != null) onButton.active = selected;
        if (offButton != null) offButton.active = selected;
    }

    @Override
    protected void renderBg(GuiGraphics graphics, float partialTick, int mouseX, int mouseY) {
        graphics.fill(leftPos, topPos, leftPos + imageWidth, topPos + imageHeight, 0xE614181A);
        graphics.fill(leftPos + 1, topPos + 1, leftPos + imageWidth - 1, topPos + 22, 0xFF242B2E);
        graphics.fill(leftPos + 7, topPos + 28, leftPos + imageWidth - 7, topPos + imageHeight - 8, 0xCC0B0E10);
    }

    @Override
    protected void renderLabels(GuiGraphics graphics, int mouseX, int mouseY) {
        graphics.drawString(font, "AFTERFALL // POWER CONTROL PANEL", 10, 8, 0xFF76D7EA, false);
        String status;
        int statusColor;
        if (menu.criticalDeficit()) {
            status = "CRITICAL DEFICIT - AUX LOAD SHED";
            statusColor = 0xFFFF6B6B;
        } else if (menu.recoveryWaiting()) {
            int remaining = Math.max(0, PowerControlPanelBlockEntity.CRITICAL_STABLE_REQUIRED_TICKS - menu.stableTicks());
            status = "CRITICAL RECOVERY - AUX HOLD " + String.format(java.util.Locale.ROOT, "%.1fs", remaining / 20.0D);
            statusColor = 0xFFFFD166;
        } else if (menu.loadShedActive()) {
            status = "STAGED AUX REARMING";
            statusColor = 0xFFFFD166;
        } else {
            status = "POWER DISTRIBUTION STABLE";
            statusColor = 0xFF72E06A;
        }
        graphics.drawString(font, status, 12, 32, statusColor, false);
        graphics.drawString(font, "Detected taps: " + menu.entries().size() + " | Radius: " + PowerControlPanelBlockEntity.CONTROL_RADIUS + " blocks", 12, 43, 0xFF9AA4A8, false);

        PowerNetworking.TapEntry entry = selected();
        if (entry != null) {
            int pct = entry.maxEnergy() <= 0 ? 0 : entry.energy() * 100 / entry.maxEnergy();
            graphics.drawString(font, entry.name() + " @ " + entry.pos().toShortString(), 50, 207, 0xFFE8E8E8, false);
            graphics.drawString(font, "Buffer " + pct + "% | IN " + entry.inputPerTick() + " FE/t | OUT " + entry.outputPerTick()
                    + " FE/t | " + (entry.managedByPanel() ? "MANAGED" : "NEARBY"), 12, 256,
                    entry.managedByPanel() ? 0xFF72E06A : 0xFF9AA4A8, false);
            if (entry.criticalDeficit()) graphics.drawString(font, "CRITICAL DEFICIT", 12, 270, 0xFFFF6B6B, false);
        } else {
            graphics.drawString(font, "Select a tap to inspect/control it.", 12, 256, 0xFF9AA4A8, false);
        }
    }
}
