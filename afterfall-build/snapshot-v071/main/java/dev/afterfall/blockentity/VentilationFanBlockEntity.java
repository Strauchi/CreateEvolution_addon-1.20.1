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

    /** FRONT/FACING is the outlet into the distribution shaft. */
    public VentilationNetworkScanner.Network inspectNetwork(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        return VentilationNetworkScanner.scan(level, worldPosition.relative(facing));
    }

    /** BACK/opposite FACING is the sealed inlet plenum/source volume. */
    public RoomScanResult inspectInlet(ServerLevel level) {
        return VentilationNetworkScanner.inletForFan(level, worldPosition);
    }

    public double availableNetworkFlow(ServerLevel level) {
        VentilationNetworkScanner.Network network = inspectNetwork(level);
        if (network == null || !network.valid()) return 0.0D;
        int availableFans = 0;
        for (BlockPos fanPos : network.fans()) {
            if (level.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan
                    && fan.enabled && fan.inspectInlet(level) != null
                    && MachinePower.available(level, fanPos, fan.energy, ENERGY_PER_SECOND)) {
                availableFans++;
            }
        }
        return availableFans * FLOW_M3_PER_SECOND;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, VentilationFanBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L || !be.enabled) return;

        VentilationNetworkScanner.Network network = be.inspectNetwork(serverLevel);
        if (network == null || !network.valid() || network.fans().isEmpty()) return;

        BlockPos leader = network.fans().stream().min(Comparator.comparingLong(BlockPos::asLong)).orElse(pos);
        if (!leader.equals(pos)) return; // one network update per second, even with multiple fans

        List<PoweredFan> powered = new ArrayList<>();
        for (BlockPos fanPos : network.fans()) {
            if (!(serverLevel.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan) || !fan.enabled) continue;
            RoomScanResult inlet = fan.inspectInlet(serverLevel);
            if (inlet == null || inlet.anchor().equals(network.shaft().anchor())) continue;
            if (MachinePower.consumeOrRedstoneFallback(serverLevel, fanPos, fan.energy, ENERGY_PER_SECOND)) {
                powered.add(new PoweredFan(fanPos, inlet));
            }
        }
        if (powered.isEmpty()) return;

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere shaftAir = VentilationNetworkScanner.atmosphere(serverLevel, network.shaft());

        // 0.7.1: Fans now physically move composition from their sealed BACK/inlet
        // plenum into the FRONT/distribution shaft. 0.7.0 only powered vent exchange,
        // leaving the prefiltered inlet room and downstream shaft as unrelated atmospheres.
        for (PoweredFan fan : powered) {
            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, fan.inlet);
            double inletFraction = Math.min(1.0D,
                    FLOW_M3_PER_SECOND / Math.max(1.0D, network.shaft().volume()));
            shaftAir.exchangeFrom(inletAir, inletFraction);
        }
        saved.markChanged();

        // The fan must be able to prime/clean a shaft before any room vents exist.
        if (network.vents().isEmpty()) return;

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

        double totalFlow = powered.size() * FLOW_M3_PER_SECOND;
        double perVentFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / Math.max(1, targets.size()));

        // Return air is mixed into the shaft first, then the resulting central air
        // is distributed through supply vents. Pressure/mass balance remains 0.8 work.
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

    private record PoweredFan(BlockPos pos, RoomScanResult inlet) {}
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
