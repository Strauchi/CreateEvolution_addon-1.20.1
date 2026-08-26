package dev.afterfall.menu;

import dev.afterfall.blockentity.PowerControlPanelBlockEntity;
import dev.afterfall.content.ModMenus;
import dev.afterfall.network.PowerNetworking;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.item.ItemStack;

import java.util.List;

public final class PowerControlPanelMenu extends AbstractContainerMenu {
    private final BlockPos panelPos;
    private final PowerControlPanelBlockEntity serverPanel;
    private final ServerPlayer serverPlayer;
    private List<PowerNetworking.TapEntry> clientEntries = List.of();
    private boolean clientCriticalDeficit;
    private boolean clientLoadShed;
    private boolean clientRecoveryWaiting;
    private int clientStableTicks;

    public PowerControlPanelMenu(int containerId, Inventory inventory, RegistryFriendlyByteBuf buf) {
        this(containerId, inventory, buf.readBlockPos(), null);
    }

    public PowerControlPanelMenu(int containerId, Inventory inventory, BlockPos pos,
                                 PowerControlPanelBlockEntity panel) {
        super(ModMenus.POWER_CONTROL_PANEL.get(), containerId);
        panelPos = pos.immutable();
        serverPanel = panel;
        serverPlayer = inventory.player instanceof ServerPlayer sp ? sp : null;
    }

    @Override
    public void broadcastChanges() {
        super.broadcastChanges();
        if (serverPanel != null && serverPlayer != null && serverPlayer.tickCount % 10 == 0) {
            PowerNetworking.sendPanelSnapshot(serverPlayer, panelPos);
        }
    }

    public void acceptSnapshot(PowerNetworking.PanelSnapshotPayload payload) {
        if (!panelPos.equals(payload.panelPos())) return;
        clientEntries = List.copyOf(payload.entries());
        clientCriticalDeficit = payload.criticalDeficit();
        clientLoadShed = payload.loadShedActive();
        clientRecoveryWaiting = payload.recoveryWaiting();
        clientStableTicks = payload.stableTicks();
    }

    public BlockPos panelPos() { return panelPos; }
    public List<PowerNetworking.TapEntry> entries() { return clientEntries; }
    public boolean criticalDeficit() { return clientCriticalDeficit; }
    public boolean loadShedActive() { return clientLoadShed; }
    public boolean recoveryWaiting() { return clientRecoveryWaiting; }
    public int stableTicks() { return clientStableTicks; }

    @Override
    public boolean stillValid(Player player) {
        return player.blockPosition().distSqr(panelPos) <= 64.0D;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        return ItemStack.EMPTY;
    }
}
