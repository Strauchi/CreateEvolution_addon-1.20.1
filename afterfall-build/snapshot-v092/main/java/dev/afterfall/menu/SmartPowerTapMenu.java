package dev.afterfall.menu;

import dev.afterfall.blockentity.SmartPowerTapBlockEntity;
import dev.afterfall.content.ModMenus;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.SimpleContainerData;
import net.minecraft.world.item.ItemStack;

public final class SmartPowerTapMenu extends AbstractContainerMenu {
    public static final int DATA_COUNT = 10;
    public static final int BUTTON_CRITICAL = 0;
    public static final int BUTTON_AUX = 1;
    public static final int BUTTON_RELAY = 2;

    public static final int D_CIRCUIT = 0;
    public static final int D_RELAY = 1;
    public static final int D_AUX_STATE = 2;
    public static final int D_ENERGY = 3;
    public static final int D_ENERGY_MAX = 4;
    public static final int D_INPUT = 5;
    public static final int D_OUTPUT = 6;
    public static final int D_DEFICIT = 7;
    public static final int D_REARM_PERCENT = 8;
    public static final int D_THROUGHPUT = 9;

    private final SimpleContainerData data = new SimpleContainerData(DATA_COUNT);
    private final BlockPos blockPos;
    private final SmartPowerTapBlockEntity serverTap;
    private String clientName;

    public SmartPowerTapMenu(int containerId, Inventory inventory, RegistryFriendlyByteBuf buf) {
        this(containerId, inventory, buf.readBlockPos(), null, buf.readUtf(32));
    }

    public SmartPowerTapMenu(int containerId, Inventory inventory, BlockPos pos, SmartPowerTapBlockEntity tap) {
        this(containerId, inventory, pos, tap, tap == null ? "Power Tap" : tap.displayName());
    }

    private SmartPowerTapMenu(int containerId, Inventory inventory, BlockPos pos,
                              SmartPowerTapBlockEntity tap, String name) {
        super(ModMenus.SMART_POWER_TAP.get(), containerId);
        blockPos = pos.immutable();
        serverTap = tap;
        clientName = name;
        addDataSlots(data);
        if (tap != null) updateServerData();
    }

    @Override
    public void broadcastChanges() {
        if (serverTap != null) updateServerData();
        super.broadcastChanges();
    }

    private void updateServerData() {
        if (!(serverTap.getLevel() instanceof ServerLevel)) return;
        data.set(D_CIRCUIT, serverTap.circuitMode().ordinal());
        data.set(D_RELAY, serverTap.relayEnabled() ? 1 : 0);
        data.set(D_AUX_STATE, serverTap.auxState().ordinal());
        data.set(D_ENERGY, serverTap.energyStored());
        data.set(D_ENERGY_MAX, serverTap.maxEnergyStored());
        data.set(D_INPUT, serverTap.recentInputPerTick());
        data.set(D_OUTPUT, serverTap.recentOutputPerTick());
        data.set(D_DEFICIT, serverTap.criticalDeficit() ? 1 : 0);
        data.set(D_REARM_PERCENT, SmartPowerTapBlockEntity.AUX_REARM_PERCENT);
        data.set(D_THROUGHPUT, SmartPowerTapBlockEntity.MAX_TRANSFER_PER_TICK);
    }

    @Override
    public boolean clickMenuButton(Player player, int id) {
        if (serverTap == null) return true;
        if (id == BUTTON_CRITICAL) serverTap.setCircuitMode(SmartPowerTapBlockEntity.CircuitMode.CRITICAL);
        else if (id == BUTTON_AUX) serverTap.setCircuitMode(SmartPowerTapBlockEntity.CircuitMode.AUX);
        else if (id == BUTTON_RELAY) serverTap.setRelayEnabled(!serverTap.relayEnabled());
        else return false;
        updateServerData();
        return true;
    }

    public BlockPos blockPos() { return blockPos; }
    public String tapName() { return clientName; }
    public void setClientName(String value) { clientName = value; }
    public int get(int index) { return data.get(index); }

    @Override
    public boolean stillValid(Player player) {
        return player.blockPosition().distSqr(blockPos) <= 64.0D;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        return ItemStack.EMPTY;
    }
}
