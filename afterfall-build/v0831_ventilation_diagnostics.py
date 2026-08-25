from pathlib import Path

root = Path('Afterfall')
src = root / 'src/main/java/dev/afterfall'


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'Pattern not found in {path}: {old[:220]!r}')
    path.write_text(text.replace(old, new, 1))


# -----------------------------------------------------------------------------
# Room-side vent diagnostics. This scans only the current sealed room boundary
# and distinguishes ordinary SUPPLY/RETURN vents from passive Transfer Vents.
# -----------------------------------------------------------------------------
scanner = src / 'room/VentilationNetworkScanner.java'
replace_once(scanner,
'''    public static RoomScanResult roomForVent(ServerLevel level, BlockPos ventPos) {
        BlockState state = level.getBlockState(ventPos);
        if (!state.is(ModBlocks.AIR_VENT.get()) || !state.hasProperty(AirVentBlock.FACING)) return null;
        Direction facing = state.getValue(AirVentBlock.FACING);
        BlockPos start = ventPos.relative(facing);
        if (!RoomScanner.airCanPass(level, start)) return null;
        RoomScanResult scan = RoomScanner.scan(level, start);
        return scan.sealed() ? scan : null;
    }

    public static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {''',
'''    public static RoomScanResult roomForVent(ServerLevel level, BlockPos ventPos) {
        BlockState state = level.getBlockState(ventPos);
        if (!state.is(ModBlocks.AIR_VENT.get()) || !state.hasProperty(AirVentBlock.FACING)) return null;
        Direction facing = state.getValue(AirVentBlock.FACING);
        BlockPos start = ventPos.relative(facing);
        if (!RoomScanner.airCanPass(level, start)) return null;
        RoomScanResult scan = RoomScanner.scan(level, start);
        return scan.sealed() ? scan : null;
    }

    /** Direct SUPPLY/RETURN vent count on this room's own boundary. */
    public static RoomVentDiagnostics inspectRoomVents(ServerLevel level, RoomScanResult room) {
        if (room == null || !room.sealed() || !RoomScanner.airCanPass(level, room.anchor())) {
            return RoomVentDiagnostics.EMPTY;
        }

        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> inspectedVents = new HashSet<>();
        int supply = 0;
        int returns = 0;
        queue.add(room.anchor().immutable());
        visited.add(room.anchor().asLong());

        while (!queue.isEmpty() && visited.size() <= RoomScanner.MAX_ROOM_VOLUME) {
            BlockPos current = queue.removeFirst();
            for (Direction direction : Direction.values()) {
                BlockPos next = current.relative(direction);
                if (RoomScanner.airCanPass(level, next)) {
                    if (visited.add(next.asLong())) queue.addLast(next.immutable());
                    continue;
                }

                BlockState state = level.getBlockState(next);
                if (!state.is(ModBlocks.AIR_VENT.get()) || !state.hasProperty(AirVentBlock.FACING)) continue;
                if (!next.relative(state.getValue(AirVentBlock.FACING)).equals(current)) continue;
                if (!inspectedVents.add(next.asLong())) continue;

                if (state.getValue(AirVentBlock.RETURN_MODE)) returns++;
                else supply++;
            }
        }
        return new RoomVentDiagnostics(supply, returns);
    }

    public static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {''')

replace_once(scanner,
'''    public record Network(RoomScanResult shaft, List<BlockPos> vents, List<BlockPos> fans) {''',
'''    public record RoomVentDiagnostics(int supplyVents, int returnVents) {
        public static final RoomVentDiagnostics EMPTY = new RoomVentDiagnostics(0, 0);
    }

    public record Network(RoomScanResult shaft, List<BlockPos> vents, List<BlockPos> fans) {''')


# -----------------------------------------------------------------------------
# Main fan: retain actual per-room flow samples from the same gameplay tick that
# performs the air exchange. No airflow values or exchange rules are changed.
# -----------------------------------------------------------------------------
fan = src / 'blockentity/VentilationFanBlockEntity.java'
replace_once(fan,
'''import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.RoomAtmosphere;''',
'''import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.IntakeNetworkScanner;
import dev.afterfall.room.RoomAtmosphere;''')

replace_once(fan,
'''import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;''',
'''import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.WeakHashMap;''')

replace_once(fan,
'''    public static final double FLOW_M3_PER_SECOND = 48.0D;
    public static final double MAX_FLOW_PER_VENT = 18.0D;

    private final MachineEnergyStorage energy''',
'''    public static final double FLOW_M3_PER_SECOND = 48.0D;
    public static final double MAX_FLOW_PER_VENT = 18.0D;

    private static final Map<ServerLevel, Map<Long, RoomFlowSample>> LAST_ROOM_FLOWS = new WeakHashMap<>();

    private final MachineEnergyStorage energy''')

replace_once(fan,
'''    public double currentReturnFlow(ServerLevel level) {
        double flow = Math.min(availableNetworkFlow(level), connectedReturnVentCount(level) * MAX_FLOW_PER_VENT);
        double passiveCap = inspectTreatmentNetwork(level).passiveBottleneckCapacity();
        return passiveCap > 0.0D ? Math.min(flow, passiveCap) : flow;
    }

    private static int validVentCount''',
'''    public double currentReturnFlow(ServerLevel level) {
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
                                       double oxygenAdded, double co2Removed) {
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
                gameTime));
    }

    private static int validVentCount''')

replace_once(fan,
'''        double deliveredFlow = 0.0D;
        for (List<PoweredFan> group : inletGroups.values()) {
            PoweredFan representative = group.get(0);
            RoomScanResult inlet = representative.inlet;
            double groupFlow = group.size() * FLOW_M3_PER_SECOND;

            // Trace all treatment plenums upstream of the fan.''',
'''        double deliveredFlow = 0.0D;
        double deliveredFreshFlow = 0.0D;
        for (List<PoweredFan> group : inletGroups.values()) {
            PoweredFan representative = group.get(0);
            RoomScanResult inlet = representative.inlet;
            double groupFlow = group.size() * FLOW_M3_PER_SECOND;

            // Current make-up air entering this exact treatment path. This is used
            // only for diagnostics; the intake already performed its own exchange.
            double groupFreshInput = IntakeNetworkScanner.inspectUpstream(serverLevel, inlet).currentInput();

            // Trace all treatment plenums upstream of the fan.''')

replace_once(fan,
'''                    double fraction = Math.min(0.30D,
                            perReturnFlow / Math.max(1.0D, target.networkRoom.volume()));
                    networkAir.exchangeFrom(roomAir, fraction);
                }
            }

            // Passive industrial filters and Transfer Vents only move air while a''',
'''                    double fraction = Math.min(0.30D,
                            perReturnFlow / Math.max(1.0D, target.networkRoom.volume()));
                    networkAir.exchangeFrom(roomAir, fraction);
                    recordRoomFlow(serverLevel, target.room, 0.0D, perReturnFlow, 0.0D, 0.0D, 0.0D);
                }
            }

            // Passive industrial filters and Transfer Vents only move air while a''')

replace_once(fan,
'''            double effectiveFlow = AirTreatmentNetwork.processPassive(serverLevel, treatment, groupFlow);

            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, inlet);''',
'''            double effectiveFlow = AirTreatmentNetwork.processPassive(serverLevel, treatment, groupFlow);
            deliveredFreshFlow += Math.min(Math.max(0.0D, groupFreshInput), effectiveFlow);

            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, inlet);''')

replace_once(fan,
'''        double totalFlow = Math.min(powered.size() * FLOW_M3_PER_SECOND, deliveredFlow);
        double perSupplyFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / supplies.size());
        for (VentTarget target : supplies) {
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double fraction = Math.min(0.30D,
                    perSupplyFlow / Math.max(1.0D, target.room.volume()));
            roomAir.exchangeFrom(shaftAir, fraction);
        }
        saved.markChanged();''',
'''        double totalFlow = Math.min(powered.size() * FLOW_M3_PER_SECOND, deliveredFlow);
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
                    Math.max(0.0D, beforeCo2 - roomAir.co2Percent()));
        }
        saved.markChanged();''')

replace_once(fan,
'''    private record PoweredFan(VentilationFanBlockEntity fan, BlockPos pos, RoomScanResult inlet) {}''',
'''    public record RoomFlowSample(double supplyM3PerSecond, double returnM3PerSecond,
                                 double freshAirM3PerSecond, double oxygenAddedPerSecond,
                                 double co2RemovedPerSecond, long sampledAt) {
        public static final RoomFlowSample EMPTY = EMPTY_AT(Long.MIN_VALUE);
        private static RoomFlowSample EMPTY_AT(long time) {
            return new RoomFlowSample(0.0D, 0.0D, 0.0D, 0.0D, 0.0D, time);
        }
        public double recirculatedM3PerSecond() {
            return Math.max(0.0D, supplyM3PerSecond - freshAirM3PerSecond);
        }
    }

    private record PoweredFan(VentilationFanBlockEntity fan, BlockPos pos, RoomScanResult inlet) {}''')


# -----------------------------------------------------------------------------
# /af room info: show direct duct ventilation separately from passive Transfer
# Vents. Life-support balance now uses the actual gas correction performed by
# the Main Fan instead of trying to discover an intake directly from the room.
# -----------------------------------------------------------------------------
commands = src / 'command/AfterfallCommands.java'
replace_once(commands,
'''import dev.afterfall.blockentity.AirIntakeBlockEntity;''',
'''import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.blockentity.VentilationFanBlockEntity;''')
replace_once(commands,
'''import dev.afterfall.room.IntakeNetworkScanner;
import dev.afterfall.room.RoomAtmosphere;''',
'''import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.VentilationNetworkScanner;''')

replace_once(commands,
'''        AirTreatmentNetwork.TransferDiagnostics transfer =
                AirTreatmentNetwork.inspectTransfers(room.level, room.scan);
        IntakeNetworkScanner.Stats fresh = IntakeNetworkScanner.inspectUpstream(room.level, room.scan);

        int occupants = roomOccupants(room.level, room.scan);
        double actualBioSupport = bioRate.actualCo2PerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double freshSupport = freshCorrectionPlayerEquivalent(room.air, fresh.currentInput());
        double netSupport = actualBioSupport + freshSupport - occupants;
        boolean co2Available = room.air.co2Percent() > RoomAtmosphere.NORMAL_CO2 + 0.000001D;''',
'''        AirTreatmentNetwork.TransferDiagnostics transfer =
                AirTreatmentNetwork.inspectTransfers(room.level, room.scan);
        VentilationNetworkScanner.RoomVentDiagnostics roomVents =
                VentilationNetworkScanner.inspectRoomVents(room.level, room.scan);
        VentilationFanBlockEntity.RoomFlowSample flow =
                VentilationFanBlockEntity.inspectRoomFlow(room.level, room.scan);

        int occupants = roomOccupants(room.level, room.scan);
        double actualBioSupport = bioRate.actualCo2PerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double ventilationO2Support = flow.oxygenAddedPerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.14D;
        double ventilationCo2Support = flow.co2RemovedPerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double ventilationSupport = Math.max(ventilationO2Support, ventilationCo2Support);
        double netLocalSupport = actualBioSupport + ventilationSupport - occupants;
        boolean co2Available = room.air.co2Percent() > RoomAtmosphere.NORMAL_CO2 + 0.000001D;''')

replace_once(commands,
'''        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Transfer: %d connected room(s) | %d vent(s) | %.1f m³/s | Max dO2 %.3f%% | Max dCO2 %.3f%%",
                transfer.connectedRooms(), transfer.ventCount(), transfer.totalCapacity(),
                transfer.maxOxygenDelta(), transfer.maxCo2Delta())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Life support: Respiration %.2f player-eq | Bio actual %.2f | Fresh correction %.2f | Net %+.2f | Fresh input %.2f m³/s",
                (double) occupants, actualBioSupport, freshSupport, netSupport, fresh.currentInput())), false);''',
'''        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Ventilation: Supply %.2f m³/s (%d vent) | Return %.2f m³/s (%d vent) | Fresh share %.2f m³/s | Recirc %.2f m³/s",
                flow.supplyM3PerSecond(), roomVents.supplyVents(),
                flow.returnM3PerSecond(), roomVents.returnVents(),
                flow.freshAirM3PerSecond(), flow.recirculatedM3PerSecond())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Vent gas: O2 +%.4f%%/min | CO2 -%.4f%%/min",
                flow.oxygenAddedPerSecond() * 60.0D,
                flow.co2RemovedPerSecond() * 60.0D)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Passive transfer: %d connected room(s) | %d Transfer Vent(s) | %.1f m³/s | Max dO2 %.3f%% | Max dCO2 %.3f%%",
                transfer.connectedRooms(), transfer.ventCount(), transfer.totalCapacity(),
                transfer.maxOxygenDelta(), transfer.maxCo2Delta())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Life support (local): Respiration %.2f player-eq | Bio actual %.2f | Vent actual %.2f | Net %+.2f",
                (double) occupants, actualBioSupport, ventilationSupport, netLocalSupport)), false);''')

# Remove the obsolete direct-intake conversion helper. The room now uses measured
# supply correction from the Main Fan, which includes fresh + recirculated air.
start = '''    /**
     * Converts the currently delivered fresh-air correction into the same
     * player-equivalent scale as respiration. This is an instantaneous diagnostic,
     * not a new control input and does not alter intake behaviour.
     */
    private static double freshCorrectionPlayerEquivalent(RoomAtmosphere atmosphere, double flowM3PerSecond) {
        double flow = Math.max(0.0D, flowM3PerSecond);
        double oxygenEquivalent = flow
                * Math.max(0.0D, RoomAtmosphere.NORMAL_OXYGEN - atmosphere.oxygenPercent()) / 0.14D;
        double co2Equivalent = flow
                * Math.max(0.0D, atmosphere.co2Percent() - RoomAtmosphere.NORMAL_CO2) / 0.11D;
        return Math.max(oxygenEquivalent, co2Equivalent);
    }

'''
replace_once(commands, start, '')

# Version identity.
afterfall = src / 'Afterfall.java'
replace_once(afterfall, 'LOGGER.info("Afterfall 0.8.3 initialized");',
             'LOGGER.info("Afterfall 0.8.3.1 initialized");')
props = root / 'gradle.properties'
replace_once(props, 'mod_version=0.8.3', 'mod_version=0.8.3.1')

print('Applied Afterfall 0.8.3.1 ventilation diagnostics fix')
