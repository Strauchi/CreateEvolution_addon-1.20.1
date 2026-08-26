package dev.afterfall.client;

import dev.afterfall.blockentity.SmartPowerTapBlockEntity;
import dev.afterfall.menu.SmartPowerTapMenu;
import dev.afterfall.network.PowerNetworking;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;
import net.neoforged.neoforge.network.PacketDistributor;

public final class SmartPowerTapScreen extends AbstractContainerScreen<SmartPowerTapMenu> {
    private Button criticalButton;
    private Button auxButton;
    private Button relayButton;
    private EditBox nameBox;

    public SmartPowerTapScreen(SmartPowerTapMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title);
        imageWidth = 264;
        imageHeight = 190;
        inventoryLabelY = 10_000;
    }

    @Override
    protected void init() {
        super.init();
        nameBox = new EditBox(font, leftPos + 12, topPos + 38, 170, 18, Component.literal("Circuit name"));
        nameBox.setMaxLength(32);
        nameBox.setValue(menu.tapName());
        addRenderableWidget(nameBox);
        addRenderableWidget(Button.builder(Component.literal("SAVE"), b -> saveName())
                .bounds(leftPos + 188, topPos + 38, 64, 18).build());
        criticalButton = addRenderableWidget(Button.builder(Component.literal("CRITICAL"), b -> sendButton(SmartPowerTapMenu.BUTTON_CRITICAL))
                .bounds(leftPos + 12, topPos + 68, 76, 18).build());
        auxButton = addRenderableWidget(Button.builder(Component.literal("AUX"), b -> sendButton(SmartPowerTapMenu.BUTTON_AUX))
                .bounds(leftPos + 94, topPos + 68, 76, 18).build());
        relayButton = addRenderableWidget(Button.builder(Component.literal("RELAY"), b -> sendButton(SmartPowerTapMenu.BUTTON_RELAY))
                .bounds(leftPos + 176, topPos + 68, 76, 18).build());
    }

    private void saveName() {
        if (nameBox == null) return;
        String value = nameBox.getValue();
        menu.setClientName(value);
        PacketDistributor.sendToServer(new PowerNetworking.TapRenamePayload(menu.blockPos(), value));
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
        int circuit = menu.get(SmartPowerTapMenu.D_CIRCUIT);
        if (criticalButton != null) criticalButton.setMessage(Component.literal(circuit == 0 ? "[ CRITICAL ]" : "CRITICAL"));
        if (auxButton != null) auxButton.setMessage(Component.literal(circuit == 1 ? "[ AUX ]" : "AUX"));
        if (relayButton != null) relayButton.setMessage(Component.literal(menu.get(SmartPowerTapMenu.D_RELAY) != 0 ? "RELAY: ON" : "RELAY: OFF"));
    }

    @Override
    protected void renderBg(GuiGraphics graphics, float partialTick, int mouseX, int mouseY) {
        graphics.fill(leftPos, topPos, leftPos + imageWidth, topPos + imageHeight, 0xE614181A);
        graphics.fill(leftPos + 1, topPos + 1, leftPos + imageWidth - 1, topPos + 22, 0xFF242B2E);
        graphics.fill(leftPos + 7, topPos + 94, leftPos + imageWidth - 7, topPos + imageHeight - 8, 0xCC0B0E10);
    }

    @Override
    protected void renderLabels(GuiGraphics graphics, int mouseX, int mouseY) {
        graphics.drawString(font, "AFTERFALL // SMART POWER TAP", 10, 8, 0xFF76D7EA, false);
        int energy = menu.get(SmartPowerTapMenu.D_ENERGY);
        int max = Math.max(1, menu.get(SmartPowerTapMenu.D_ENERGY_MAX));
        int pct = energy * 100 / max;
        String circuit = menu.get(SmartPowerTapMenu.D_CIRCUIT) == 0 ? "CRITICAL" : "AUX";
        String auxState = switch (menu.get(SmartPowerTapMenu.D_AUX_STATE)) {
            case 1 -> "SHED";
            case 2 -> "REARMING";
            default -> "ACTIVE";
        };
        int y = 102;
        graphics.drawString(font, "Circuit: " + circuit + " | Relay: " + (menu.get(SmartPowerTapMenu.D_RELAY) != 0 ? "ON" : "OFF"), 14, y, 0xFFE8E8E8, false);
        graphics.drawString(font, "Buffer: " + energy + " / " + max + " FE (" + pct + "%)", 14, y + 14, 0xFFE8E8E8, false);
        graphics.drawString(font, "Input: " + menu.get(SmartPowerTapMenu.D_INPUT) + " FE/t | Output: " + menu.get(SmartPowerTapMenu.D_OUTPUT) + " FE/t", 14, y + 28, 0xFFE8E8E8, false);
        if (menu.get(SmartPowerTapMenu.D_CIRCUIT) == 1) {
            graphics.drawString(font, "AUX state: " + auxState + " | Rearm: " + menu.get(SmartPowerTapMenu.D_REARM_PERCENT) + "%", 14, y + 42,
                    auxState.equals("ACTIVE") ? 0xFF72E06A : (auxState.equals("REARMING") ? 0xFFFFD166 : 0xFFFF6B6B), false);
        } else {
            graphics.drawString(font, menu.get(SmartPowerTapMenu.D_DEFICIT) != 0 ? "CRITICAL DEFICIT" : "Critical supply stable", 14, y + 42,
                    menu.get(SmartPowerTapMenu.D_DEFICIT) != 0 ? 0xFFFF6B6B : 0xFF72E06A, false);
        }
        graphics.drawString(font, "BACK = GRID | FRONT = LOAD | Max " + menu.get(SmartPowerTapMenu.D_THROUGHPUT) + " FE/t", 14, y + 56, 0xFF9AA4A8, false);
    }
}
