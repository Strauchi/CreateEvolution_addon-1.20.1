package dev.afterfall.blockentity;

import dev.afterfall.block.AirVentBlock;
import dev.afterfall.block.VentilationFanBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.VentilationNetworkScanner;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class VentilationFanBlockEntity extends BlockEntity {
    public static final int ENERGY_CAPACITY = 80_000;
    public static final int ENERGY_PER_SECOND = 800;
    public static final double FLOW_M3_PER_SECOND = 48.0D;
    public static final double MAX_FLOW_PER_VENT = 18.0D;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(
            ENERGY_CAPACITY, 4_000, 0, this::setChanged);
    private boolean enabled = true;

    public VentilationFanBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.VENTILATION_FAN.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; setChanged(); }

    public VentilationNetworkScanner.Network inspectNetwork(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        return VentilationNetworkScanner.scan(level, worldPosition.relative(facing));
    }

    public double availableNetworkFlow(ServerLevel level) {
        VentilationNetworkScanner.Network network = inspectNetwork(level);
        if (network == null || !network.valid()) return 0.0D;
        int availableFans = 0;
        for (BlockPos fanPos : network.fans()) {
            if (level.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan
                    && fan.enabled && MachinePower.available(level, fanPos, fan.energy, ENERGY_PER_SECOND)) {
                availableFans++;
            }
        }
        return availableFans * FLOW_M3_PER_SECOND;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, VentilationFanBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L || !be.enabled) return;

        VentilationNetworkScanner.Network network = be.inspectNetwork(serverLevel);
        if (network == null || !network.valid() || network.vents().isEmpty() || network.fans().isEmpty()) return;

        BlockPos leader = network.fans().stream().min(Comparator.comparingLong(BlockPos::asLong)).orElse(pos);
        if (!leader.equals(pos)) return; // one network update per second, even with multiple fans

        List<VentTarget> targets = new ArrayList<>();
        for (BlockPos ventPos : network.vents()) {
            BlockState ventState = serverLevel.getBlockState(ventPos);
            if (!ventState.is(ModBlocks.AIR_VENT.get())) continue;
            RoomScanResult room = VentilationNetworkScanner.roomForVent(serverLevel, ventPos);
            if (room == null || room.anchor().equals(network.shaft().anchor())) continue;
            boolean returnMode = ventState.getValue(AirVentBlock.RETURN_MODE);
            targets.add(new VentTarget(ventPos, room, returnMode));
        }
        if (targets.isEmpty()) return;

        int poweredFans = 0;
        for (BlockPos fanPos : network.fans()) {
            if (!(serverLevel.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan) || !fan.enabled) continue;
            if (MachinePower.consumeOrRedstoneFallback(serverLevel, fanPos, fan.energy, ENERGY_PER_SECOND)) poweredFans++;
        }
        if (poweredFans <= 0) return;

        double totalFlow = poweredFans * FLOW_M3_PER_SECOND;
        double perVentFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / Math.max(1, targets.size()));
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere shaftAir = VentilationNetworkScanner.atmosphere(serverLevel, network.shaft());

        // Return air is mixed into the shaft first; supply vents then distribute the
        // resulting central air mixture. Pressure/mass balance is intentionally deferred
        // to 0.8, but composition and rated volumetric flow already matter here.
        for (VentTarget target : targets) {
            if (!target.returnMode) continue;
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double fraction = Math.min(0.30D, perVentFlow / Math.max(1.0D, network.shaft().volume()));
            shaftAir.exchangeFrom(roomAir, fraction);
        }
        for (VentTarget target : targets) {
            if (target.returnMode) continue;
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double fraction = Math.min(0.30D, perVentFlow / Math.max(1.0D, target.room.volume()));
            roomAir.exchangeFrom(shaftAir, fraction);
        }
        saved.markChanged();
    }

    private record VentTarget(BlockPos pos, RoomScanResult room, boolean returnMode) {}

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        tag.putBoolean("Enabled", enabled);
    }
}
