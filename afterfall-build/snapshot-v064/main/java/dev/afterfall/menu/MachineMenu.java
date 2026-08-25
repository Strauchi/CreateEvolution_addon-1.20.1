package dev.afterfall.menu;

import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.AirlockLogic;
import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;
import dev.afterfall.content.ModMenus;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomMachineUtil;
import dev.afterfall.room.RoomScanResult;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.SimpleContainerData;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.entity.BlockEntity;

/**
 * Read-only technical dashboard shared by Afterfall bunker machines.
 * The first 0.6 GUI intentionally keeps filter insertion/fuel loading on the
 * physical machine interaction path while replacing chat spam with a live panel.
 */
public final class MachineMenu extends AbstractContainerMenu {
    public static final int DATA_COUNT = 17;

    public static final int TYPE_FILTER = 0;
    public static final int TYPE_INTAKE = 1;
    public static final int TYPE_AIRLOCK = 2;
    public static final int TYPE_GENERATOR = 3;

    // Synced data indices.
    public static final int D_TYPE = 0;
    public static final int D_ENERGY = 1;
    public static final int D_ENERGY_MAX = 2;
    public static final int D_STATUS = 3;
    public static final int D_PRE = 4;
    public static final int D_HEPA = 5;
    public static final int D_RAD = 6;
    public static final int D_ROOM_VOLUME = 7;
    public static final int D_DUST_X100 = 8;
    public static final int D_AIR_RAD_X100 = 9;
    public static final int D_O2_X100 = 10;
    public static final int D_CO2_X100 = 11;
    public static final int D_AIR_QUALITY_X10 = 12;
    public static final int D_FLOW_X10 = 13;
    public static final int D_EXTRA = 14;
    public static final int D_POWER_SOURCE = 15;
    public static final int D_FILTER_CONDITION = 16;

    private final SimpleContainerData data = new SimpleContainerData(DATA_COUNT);
    private final BlockPos blockPos;
    private final BlockEntity serverBlockEntity;

    /** Client constructor used by IContainerFactory. */
    public MachineMenu(int containerId, Inventory inventory, RegistryFriendlyByteBuf buf) {
        this(containerId, inventory, buf.readBlockPos(), null);
    }

    /** Server constructor. */
    public MachineMenu(int containerId, Inventory inventory, BlockPos pos, BlockEntity blockEntity) {
        super(ModMenus.MACHINE.get(), containerId);
        this.blockPos = pos.immutable();
        this.serverBlockEntity = blockEntity;
        addDataSlots(data);
        if (serverBlockEntity != null) updateServerData();
    }

    @Override
    public void broadcastChanges() {
        if (serverBlockEntity != null) updateServerData();
        super.broadcastChanges();
    }

    private void updateServerData() {
        if (!(serverBlockEntity.getLevel() instanceof ServerLevel level)) return;
        for (int i = 0; i < DATA_COUNT; i++) data.set(i, 0);

        if (serverBlockEntity instanceof AirFilterBlockEntity be) {
            data.set(D_TYPE, TYPE_FILTER);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_FLOW_X10, scale(AirFilterBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomScanResult scan = RoomMachineUtil.findSealedAdjacentRoom(level, blockPos);
            if (!MachinePower.available(level, blockPos, be.energyStorage(), AirFilterBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1); // no power
            else if (scan == null) data.set(D_STATUS, 2); // no room
            else if (!be.filters().complete()) data.set(D_STATUS, 3); // filter required
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirFilterBlockEntity.isClean(atmosphere) ? 5 : 4); // standby / filtering
                setAtmosphere(scan, atmosphere);
            }
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof AirIntakeBlockEntity be) {
            data.set(D_TYPE, TYPE_INTAKE);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_FLOW_X10, scale(AirIntakeBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, blockPos);
            RoomScanResult scan = connection.room();
            if (!MachinePower.available(level, blockPos, be.energyStorage(), AirIntakeBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!be.filters().complete()) data.set(D_STATUS, 3);
            else if (!connection.outsideConnected()) data.set(D_STATUS, 6); // no outside connection
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirIntakeBlockEntity.needsFreshAir(atmosphere) ? 7 : 5); // ventilating / standby
                setAtmosphere(scan, atmosphere);
            }
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {
            data.set(D_TYPE, TYPE_AIRLOCK);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_EXTRA, be.cycleState().ordinal());
            AirlockLogic.AirlockStatus status = AirlockLogic.inspectStatus(level, blockPos);
            data.set(D_STATUS, airlockStatusCode(be, status));
            if (status.hasAtmosphere()) setAtmosphere(status.scan(), status.atmosphere());
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) {
            data.set(D_TYPE, TYPE_GENERATOR);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            data.set(D_STATUS, be.burnTicks() > 0 ? 8 : (be.energyStorage().getEnergyStored() > 0 ? 9 : 10));
            data.set(D_FLOW_X10, EmergencyGeneratorBlockEntity.GENERATION_PER_TICK * 10);
            data.set(D_EXTRA, be.burnTicks());
            data.set(D_POWER_SOURCE, 3); // generator/local
        }
    }

    private int airlockStatusCode(AirlockControllerBlockEntity be, AirlockLogic.AirlockStatus status) {
        if (be.isBusy()) return 20 + be.cycleState().ordinal();
        return switch (status.type()) {
            case NOT_CONFIGURED -> 11;
            case DOOR_OPEN -> 12;
            case NO_SEALED_CHAMBER -> 13;
            case CHAMBER_TOO_LARGE -> 14;
            case UNSAFE_NO_POWER -> 1;
            case FILTER_REQUIRED -> 3;
            case SAFE -> 16;
            default -> 15; // unsafe-but-purgeable / future status fallback
        };
    }

    private void setEnergy(int stored, int max) {
        // ContainerData is kept in a conservative 16-bit-safe range. GUI displays
        // energy in 10 FE units so even the 100k emergency-generator buffer syncs safely.
        data.set(D_ENERGY, stored / 10);
        data.set(D_ENERGY_MAX, Math.max(1, max / 10));
    }

    private void setFilters(double pre, double hepa, double rad, String condition) {
        data.set(D_PRE, scale(pre * 100.0D, 10.0D));
        data.set(D_HEPA, scale(hepa * 100.0D, 10.0D));
        data.set(D_RAD, scale(rad * 100.0D, 10.0D));
        data.set(D_FILTER_CONDITION, switch (condition) {
            case "EXHAUSTED" -> 3;
            case "CRITICAL" -> 2;
            case "DEGRADED" -> 1;
            default -> 0;
        });
    }

    private void setAtmosphere(RoomScanResult scan, RoomAtmosphere atmosphere) {
        data.set(D_ROOM_VOLUME, scan.volume());
        data.set(D_DUST_X100, scale(atmosphere.dustPercent(), 100.0D));
        data.set(D_AIR_RAD_X100, scale(atmosphere.airborneRadiationPerSecond() * 3600.0D, 100.0D));
        data.set(D_O2_X100, scale(atmosphere.oxygenPercent(), 100.0D));
        data.set(D_CO2_X100, scale(atmosphere.co2Percent(), 100.0D));
        data.set(D_AIR_QUALITY_X10, scale(atmosphere.airQualityPercent(), 10.0D));
    }

    private static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        return RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
    }

    private static int powerSource(ServerLevel level, BlockPos pos, dev.afterfall.machine.MachineEnergyStorage storage) {
        String source = MachinePower.source(level, pos, storage);
        if ("FE".equals(source)) return 1;
        if (source.startsWith("REDSTONE")) return 2;
        return 0;
    }

    private static int scale(double value, double multiplier) {
        return (int) Math.round(Math.max(0.0D, Math.min(2_000_000.0D, value * multiplier)));
    }

    public BlockPos blockPos() { return blockPos; }
    public int get(int index) { return data.get(index); }
    public double prePercent() { return get(D_PRE) / 10.0D; }
    public double hepaPercent() { return get(D_HEPA) / 10.0D; }
    public double radPercent() { return get(D_RAD) / 10.0D; }
    public double dustPercent() { return get(D_DUST_X100) / 100.0D; }
    public double airRadiation() { return get(D_AIR_RAD_X100) / 100.0D; }
    public double oxygenPercent() { return get(D_O2_X100) / 100.0D; }
    public double co2Percent() { return get(D_CO2_X100) / 100.0D; }
    public double airQuality() { return get(D_AIR_QUALITY_X10) / 10.0D; }
    public double flow() { return get(D_FLOW_X10) / 10.0D; }

    @Override
    public boolean stillValid(Player player) {
        return player.distanceToSqr(blockPos.getX() + 0.5D, blockPos.getY() + 0.5D, blockPos.getZ() + 0.5D) <= 64.0D;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        return ItemStack.EMPTY;
    }
}
