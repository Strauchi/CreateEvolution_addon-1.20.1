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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

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

    /** FRONT/FACING is the outlet into the distribution/supply shaft. */
    public VentilationNetworkScanner.Network inspectNetwork(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        return VentilationNetworkScanner.scan(level, worldPosition.relative(facing));
    }

    /** BACK/opposite FACING is the sealed mixing plenum / return-network volume. */
    public RoomScanResult inspectInlet(ServerLevel level) {
        return VentilationNetworkScanner.inletForFan(level, worldPosition);
    }

    public VentilationNetworkScanner.Network inspectReturnNetwork(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        return VentilationNetworkScanner.scan(level, worldPosition.relative(facing.getOpposite()));
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

    public int connectedSupplyVentCount(ServerLevel level) {
        VentilationNetworkScanner.Network network = inspectNetwork(level);
        return network == null || !network.valid() ? 0 : validVentCount(level, network, false, network.shaft().anchor());
    }

    public int connectedReturnVentCount(ServerLevel level) {
        VentilationNetworkScanner.Network network = inspectReturnNetwork(level);
        RoomScanResult inlet = inspectInlet(level);
        return network == null || !network.valid() || inlet == null
                ? 0 : validVentCount(level, network, true, inlet.anchor());
    }

    public double currentSupplyFlow(ServerLevel level) {
        return Math.min(availableNetworkFlow(level), connectedSupplyVentCount(level) * MAX_FLOW_PER_VENT);
    }

    public double currentReturnFlow(ServerLevel level) {
        return Math.min(availableNetworkFlow(level), connectedReturnVentCount(level) * MAX_FLOW_PER_VENT);
    }

    private static int validVentCount(ServerLevel level, VentilationNetworkScanner.Network network,
                                      boolean returnMode, BlockPos networkAnchor) {
        int count = 0;
        for (BlockPos ventPos : network.vents()) {
            BlockState ventState = level.getBlockState(ventPos);
            if (!ventState.is(ModBlocks.AIR_VENT.get())
                    || ventState.getValue(AirVentBlock.RETURN_MODE) != returnMode) continue;
            RoomScanResult room = VentilationNetworkScanner.roomForVent(level, ventPos);
            if (room != null && !room.anchor().equals(networkAnchor)) count++;
        }
        return count;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, VentilationFanBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L || !be.enabled) return;

        VentilationNetworkScanner.Network supplyNetwork = be.inspectNetwork(serverLevel);
        if (supplyNetwork == null || !supplyNetwork.valid() || supplyNetwork.fans().isEmpty()) return;

        BlockPos leader = supplyNetwork.fans().stream().min(Comparator.comparingLong(BlockPos::asLong)).orElse(pos);
        if (!leader.equals(pos)) return; // one update per shared supply network per second

        List<PoweredFan> powered = new ArrayList<>();
        for (BlockPos fanPos : supplyNetwork.fans()) {
            if (!(serverLevel.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan) || !fan.enabled) continue;
            RoomScanResult inlet = fan.inspectInlet(serverLevel);
            if (inlet == null || inlet.anchor().equals(supplyNetwork.shaft().anchor())) continue;
            if (MachinePower.consumeOrRedstoneFallback(serverLevel, fanPos, fan.energy, ENERGY_PER_SECOND)) {
                powered.add(new PoweredFan(fan, fanPos, inlet));
            }
        }
        if (powered.isEmpty()) return;

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere shaftAir = VentilationNetworkScanner.atmosphere(serverLevel, supplyNetwork.shaft());

        // Fans sharing the same BACK plenum form one suction group. RETURN vents
        // bordering that plenum/return shaft feed room air into it before supply air
        // is pushed through the fan. This supports physically separate return shafts.
        Map<Long, List<PoweredFan>> inletGroups = new LinkedHashMap<>();
        for (PoweredFan fan : powered) {
            inletGroups.computeIfAbsent(fan.inlet.anchor().asLong(), ignored -> new ArrayList<>()).add(fan);
        }

        for (List<PoweredFan> group : inletGroups.values()) {
            PoweredFan representative = group.get(0);
            RoomScanResult inlet = representative.inlet;
            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, inlet);
            VentilationNetworkScanner.Network returnNetwork = representative.fan.inspectReturnNetwork(serverLevel);

            if (returnNetwork != null && returnNetwork.valid()) {
                List<VentTarget> returns = collectTargets(serverLevel, returnNetwork, true, inlet.anchor());
                if (!returns.isEmpty()) {
                    double returnCapacity = group.size() * FLOW_M3_PER_SECOND;
                    double perReturnFlow = Math.min(MAX_FLOW_PER_VENT, returnCapacity / returns.size());
                    for (VentTarget target : returns) {
                        RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
                        double fraction = Math.min(0.30D,
                                perReturnFlow / Math.max(1.0D, inlet.volume()));
                        inletAir.exchangeFrom(roomAir, fraction);
                    }
                }
            }

            // Move the resulting return/mixing-plenum composition through the fan
            // into the supply shaft. Multiple fans on one inlet scale throughput.
            double groupFlow = group.size() * FLOW_M3_PER_SECOND;
            double inletFraction = Math.min(1.0D,
                    groupFlow / Math.max(1.0D, supplyNetwork.shaft().volume()));
            shaftAir.exchangeFrom(inletAir, inletFraction);
        }
        saved.markChanged();

        // SUPPLY vents are only read from the FRONT network. RETURN vents belong on
        // the fan's BACK/mixing network and are intentionally ignored here.
        List<VentTarget> supplies = collectTargets(serverLevel, supplyNetwork, false, supplyNetwork.shaft().anchor());
        if (supplies.isEmpty()) return; // shaft priming still happened above

        double totalFlow = powered.size() * FLOW_M3_PER_SECOND;
        double perSupplyFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / supplies.size());
        for (VentTarget target : supplies) {
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double fraction = Math.min(0.30D,
                    perSupplyFlow / Math.max(1.0D, target.room.volume()));
            roomAir.exchangeFrom(shaftAir, fraction);
        }
        saved.markChanged();
    }

    private static List<VentTarget> collectTargets(ServerLevel level, VentilationNetworkScanner.Network network,
                                                    boolean returnMode, BlockPos networkAnchor) {
        List<VentTarget> targets = new ArrayList<>();
        for (BlockPos ventPos : network.vents()) {
            BlockState ventState = level.getBlockState(ventPos);
            if (!ventState.is(ModBlocks.AIR_VENT.get())
                    || ventState.getValue(AirVentBlock.RETURN_MODE) != returnMode) continue;
            RoomScanResult room = VentilationNetworkScanner.roomForVent(level, ventPos);
            if (room == null || room.anchor().equals(networkAnchor)) continue;
            targets.add(new VentTarget(ventPos, room));
        }
        return targets;
    }

    private record PoweredFan(VentilationFanBlockEntity fan, BlockPos pos, RoomScanResult inlet) {}
    private record VentTarget(BlockPos pos, RoomScanResult room) {}

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
