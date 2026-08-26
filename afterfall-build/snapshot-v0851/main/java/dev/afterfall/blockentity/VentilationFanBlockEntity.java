package dev.afterfall.blockentity;

import dev.afterfall.block.AirVentBlock;
import dev.afterfall.block.VentilationFanBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.IntakeNetworkScanner;
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
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.WeakHashMap;

public final class VentilationFanBlockEntity extends BlockEntity {
    public static final int ENERGY_CAPACITY = 80_000;
    public static final int ENERGY_PER_SECOND = 800;
    public static final double FLOW_M3_PER_SECOND = 48.0D;
    public static final double MAX_FLOW_PER_VENT = 18.0D;

    private static final Map<ServerLevel, Map<Long, RoomFlowSample>> LAST_ROOM_FLOWS = new WeakHashMap<>();

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
        RoomScanResult inlet = inspectInlet(level);
        if (inlet == null) return 0;
        AirTreatmentNetwork.Network treatment = AirTreatmentNetwork.trace(level, inlet);
        return collectReturnTargets(level, treatment).size();
    }

    public AirTreatmentNetwork.Network inspectTreatmentNetwork(ServerLevel level) {
        RoomScanResult inlet = inspectInlet(level);
        return inlet == null ? AirTreatmentNetwork.Network.EMPTY : AirTreatmentNetwork.trace(level, inlet);
    }

    public double industrialFilterCapacity(ServerLevel level) {
        AirTreatmentNetwork.Network treatment = inspectTreatmentNetwork(level);
        return treatment.hasIndustrialStages() ? treatment.bottleneckCapacity() : 0.0D;
    }

    public double currentSupplyFlow(ServerLevel level) {
        double flow = Math.min(availableNetworkFlow(level), connectedSupplyVentCount(level) * MAX_FLOW_PER_VENT);
        double passiveCap = inspectTreatmentNetwork(level).passiveBottleneckCapacity();
        return passiveCap > 0.0D ? Math.min(flow, passiveCap) : flow;
    }

    public double currentReturnFlow(ServerLevel level) {
        double flow = Math.min(availableNetworkFlow(level), connectedReturnVentCount(level) * MAX_FLOW_PER_VENT);
        double passiveCap = inspectTreatmentNetwork(level).passiveBottleneckCapacity();
        return passiveCap > 0.0D ? Math.min(flow, passiveCap) : flow;
    }

    /** Last real one-second fan exchange observed for this sealed room. */
    public static RoomFlowSample inspectRoomFlow(ServerLevel level, RoomScanResult room) {
        if (room == null || !room.sealed()) return RoomFlowSample.EMPTY;
        Map<Long, RoomFlowSample> samples = LAST_ROOM_FLOWS.get(level);
        RoomFlowSample sample = samples == null ? null : samples.get(room.anchor().asLong());
        if (sample == null || level.getGameTime() - sample.sampledAt() > 40L) return RoomFlowSample.EMPTY;
        return sample;
    }

    private static void recordRoomFlow(ServerLevel level, RoomScanResult room,
                                       double supplyFlow, double returnFlow, double freshFlow,
                                       double oxygenAdded, double co2Removed,
                                       int filterStages, double dustFilterLoadRatio,
                                       double radiationFilterLoadRatio) {
        if (room == null || !room.sealed()) return;
        long gameTime = level.getGameTime();
        Map<Long, RoomFlowSample> samples = LAST_ROOM_FLOWS.computeIfAbsent(level, ignored -> new HashMap<>());
        long key = room.anchor().asLong();
        RoomFlowSample previous = samples.get(key);
        if (previous == null || previous.sampledAt() != gameTime) previous = RoomFlowSample.EMPTY_AT(gameTime);
        samples.put(key, new RoomFlowSample(
                previous.supplyM3PerSecond() + Math.max(0.0D, supplyFlow),
                previous.returnM3PerSecond() + Math.max(0.0D, returnFlow),
                previous.freshAirM3PerSecond() + Math.max(0.0D, freshFlow),
                previous.oxygenAddedPerSecond() + Math.max(0.0D, oxygenAdded),
                previous.co2RemovedPerSecond() + Math.max(0.0D, co2Removed),
                Math.max(previous.filterStages(), Math.max(0, filterStages)),
                Math.max(previous.maxDustFilterLoadRatio(), Math.max(0.0D, dustFilterLoadRatio)),
                Math.max(previous.maxRadiationFilterLoadRatio(), Math.max(0.0D, radiationFilterLoadRatio)),
                gameTime));
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

        double deliveredFlow = 0.0D;
        double deliveredFreshFlow = 0.0D;
        int deliveredFilterStages = 0;
        double deliveredDustFilterLoad = 0.0D;
        double deliveredRadiationFilterLoad = 0.0D;
        for (List<PoweredFan> group : inletGroups.values()) {
            PoweredFan representative = group.get(0);
            RoomScanResult inlet = representative.inlet;
            double groupFlow = group.size() * FLOW_M3_PER_SECOND;

            // Current make-up air entering this exact treatment path. This is used
            // only for diagnostics; the intake already performed its own exchange.
            double groupFreshInput = IntakeNetworkScanner.inspectUpstream(serverLevel, inlet).currentInput();

            // Trace all treatment plenums upstream of the fan. RETURN vents may be
            // attached to the mixing room before a compact filter or before one or
            // more passive industrial filter walls, so they are not limited to the
            // fan's immediate BACK room anymore.
            AirTreatmentNetwork.Network treatment = AirTreatmentNetwork.trace(serverLevel, inlet);
            List<ReturnTarget> returns = collectReturnTargets(serverLevel, treatment);
            if (!returns.isEmpty()) {
                double perReturnFlow = Math.min(MAX_FLOW_PER_VENT, groupFlow / returns.size());
                for (ReturnTarget target : returns) {
                    RoomAtmosphere networkAir = VentilationNetworkScanner.atmosphere(serverLevel, target.networkRoom);
                    RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
                    double fraction = Math.min(0.30D,
                            perReturnFlow / Math.max(1.0D, target.networkRoom.volume()));
                    networkAir.exchangeFrom(roomAir, fraction);
                    recordRoomFlow(serverLevel, target.room, 0.0D, perReturnFlow, 0.0D,
                            0.0D, 0.0D, 0, 0.0D, 0.0D);
                }
            }

            // Passive industrial filters and Transfer Vents only move air while a
            // powered main fan is pulling through them. Compact filter units keep
            // their own powered block-entity processing.
            AirTreatmentNetwork.ProcessResult treatmentResult =
                    AirTreatmentNetwork.processPassiveDetailed(serverLevel, treatment, groupFlow);
            double effectiveFlow = treatmentResult.effectiveFlow();
            deliveredFilterStages = Math.max(deliveredFilterStages, treatmentResult.industrialStages());
            deliveredDustFilterLoad = Math.max(deliveredDustFilterLoad, treatmentResult.maxDustLoadRatio());
            deliveredRadiationFilterLoad = Math.max(deliveredRadiationFilterLoad, treatmentResult.maxRadiationLoadRatio());
            deliveredFreshFlow += Math.min(Math.max(0.0D, groupFreshInput), effectiveFlow);

            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, inlet);
            double inletFraction = Math.min(1.0D,
                    effectiveFlow / Math.max(1.0D, supplyNetwork.shaft().volume()));
            shaftAir.exchangeFrom(inletAir, inletFraction);
            deliveredFlow += effectiveFlow;
        }
        saved.markChanged();

        // SUPPLY vents are only read from the FRONT network. RETURN vents belong on
        // the fan's BACK/mixing network and are intentionally ignored here.
        List<VentTarget> supplies = collectTargets(serverLevel, supplyNetwork, false, supplyNetwork.shaft().anchor());
        if (supplies.isEmpty()) return; // shaft priming still happened above

        double totalFlow = Math.min(powered.size() * FLOW_M3_PER_SECOND, deliveredFlow);
        double perSupplyFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / supplies.size());
        double freshFraction = deliveredFlow <= 0.0D ? 0.0D
                : Math.min(1.0D, Math.max(0.0D, deliveredFreshFlow / deliveredFlow));
        double perSupplyFresh = perSupplyFlow * freshFraction;
        for (VentTarget target : supplies) {
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double beforeO2 = roomAir.oxygenPercent();
            double beforeCo2 = roomAir.co2Percent();
            double fraction = Math.min(0.30D,
                    perSupplyFlow / Math.max(1.0D, target.room.volume()));
            roomAir.exchangeFrom(shaftAir, fraction);
            recordRoomFlow(serverLevel, target.room, perSupplyFlow, 0.0D, perSupplyFresh,
                    Math.max(0.0D, roomAir.oxygenPercent() - beforeO2),
                    Math.max(0.0D, beforeCo2 - roomAir.co2Percent()),
                    deliveredFilterStages, deliveredDustFilterLoad, deliveredRadiationFilterLoad);
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

    private static List<ReturnTarget> collectReturnTargets(ServerLevel level, AirTreatmentNetwork.Network treatment) {
        Map<Long, ReturnTarget> unique = new LinkedHashMap<>();
        for (RoomScanResult treatmentRoom : treatment.rooms()) {
            VentilationNetworkScanner.Network network = VentilationNetworkScanner.scan(level, treatmentRoom.anchor());
            if (network == null || !network.valid()) continue;
            for (VentTarget target : collectTargets(level, network, true, treatmentRoom.anchor())) {
                unique.putIfAbsent(target.pos.asLong(), new ReturnTarget(target.pos, treatmentRoom, target.room));
            }
        }
        return new ArrayList<>(unique.values());
    }

    public record RoomFlowSample(double supplyM3PerSecond, double returnM3PerSecond,
                                 double freshAirM3PerSecond, double oxygenAddedPerSecond,
                                 double co2RemovedPerSecond, int filterStages,
                                 double maxDustFilterLoadRatio, double maxRadiationFilterLoadRatio,
                                 long sampledAt) {
        public static final RoomFlowSample EMPTY = EMPTY_AT(Long.MIN_VALUE);
        private static RoomFlowSample EMPTY_AT(long time) {
            return new RoomFlowSample(0.0D, 0.0D, 0.0D, 0.0D, 0.0D,
                    0, 0.0D, 0.0D, time);
        }
        public double recirculatedM3PerSecond() {
            return Math.max(0.0D, supplyM3PerSecond - freshAirM3PerSecond);
        }
    }

    private record PoweredFan(VentilationFanBlockEntity fan, BlockPos pos, RoomScanResult inlet) {}
    private record VentTarget(BlockPos pos, RoomScanResult room) {}
    private record ReturnTarget(BlockPos pos, RoomScanResult networkRoom, RoomScanResult room) {}

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
