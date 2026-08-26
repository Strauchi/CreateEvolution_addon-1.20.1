package dev.afterfall.room;

import dev.afterfall.block.AirFilterBlock;
import dev.afterfall.block.Co2ScrubberBlock;
import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.Co2ScrubberBlockEntity;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Traces passive/filtered airflow upstream from a main fan inlet.
 *
 * Compact filter units are directional machine edges (FRONT -> BACK while tracing
 * upstream). Industrial filter blocks and Transfer Vents are passive and have no
 * facing. Their direction is inferred from the fan: the room farther from the fan
 * is upstream, the room closer to the fan is downstream.
 */
public final class AirTreatmentNetwork {
    public static final int MAX_DEPTH = 12;

    public static final double PRE_CAPACITY_PER_BLOCK = 14.0D;
    public static final double HEPA_CAPACITY_PER_BLOCK = 10.0D;
    public static final double RAD_CAPACITY_PER_BLOCK = 8.0D;
    public static final double TRANSFER_CAPACITY_PER_BLOCK = 18.0D;

    public static final double PRE_DUST_EFFICIENCY = 0.70D;
    public static final double HEPA_DUST_EFFICIENCY = 0.95D;
    public static final double RAD_AIRBORNE_EFFICIENCY = 0.98D;

    public static Network trace(ServerLevel level, RoomScanResult fanInlet) {
        if (!validRoom(level, fanInlet)) return Network.EMPTY;

        LinkedHashMap<Long, RoomScanResult> rooms = new LinkedHashMap<>();
        List<IndustrialStage> industrialStages = new ArrayList<>();
        List<TransferStage> transferStages = new ArrayList<>();
        List<ScrubberStage> scrubberStages = new ArrayList<>();
        Set<Long> visited = new HashSet<>();
        walk(level, fanInlet, 0, visited, rooms, industrialStages, transferStages, scrubberStages);

        int pre = 0;
        int hepa = 0;
        int rad = 0;
        double industrialBottleneck = Double.POSITIVE_INFINITY;
        for (IndustrialStage stage : industrialStages) {
            pre += stage.preBlocks();
            hepa += stage.hepaBlocks();
            rad += stage.radBlocks();
            industrialBottleneck = Math.min(industrialBottleneck, stage.capacity());
        }
        if (industrialStages.isEmpty()) industrialBottleneck = 0.0D;

        int transferVents = 0;
        double transferBottleneck = Double.POSITIVE_INFINITY;
        for (TransferStage stage : transferStages) {
            transferVents += stage.ventCount();
            transferBottleneck = Math.min(transferBottleneck, stage.capacity());
        }
        if (transferStages.isEmpty()) transferBottleneck = 0.0D;

        int scrubbers = 0;
        double scrubberBottleneck = Double.POSITIVE_INFINITY;
        for (ScrubberStage stage : scrubberStages) {
            scrubbers += stage.scrubberPositions().size();
            scrubberBottleneck = Math.min(scrubberBottleneck, stage.capacity());
        }
        if (scrubberStages.isEmpty()) scrubberBottleneck = 0.0D;

        return new Network(List.copyOf(rooms.values()), List.copyOf(industrialStages),
                List.copyOf(transferStages), List.copyOf(scrubberStages), pre, hepa, rad,
                transferVents, scrubbers, industrialBottleneck, transferBottleneck,
                scrubberBottleneck);
    }

    /**
     * Local Transfer Vent diagnostics for operator balancing. Since Transfer Vents
     * are physically undirected, composition deltas are reported as absolute maxima
     * across directly connected sealed rooms.
     */
    public static TransferDiagnostics inspectTransfers(ServerLevel level, RoomScanResult room) {
        if (!validRoom(level, room)) return TransferDiagnostics.EMPTY;

        Boundary boundary = scanBoundary(level, room);
        RoomAtmosphere local = atmosphere(level, room);
        int vents = 0;
        double maxO2Delta = 0.0D;
        double maxCo2Delta = 0.0D;

        for (TransferBank bank : boundary.transferBanks().values()) {
            vents += bank.ventCount();
            RoomAtmosphere other = atmosphere(level, bank.otherRoom());
            maxO2Delta = Math.max(maxO2Delta,
                    Math.abs(local.oxygenPercent() - other.oxygenPercent()));
            maxCo2Delta = Math.max(maxCo2Delta,
                    Math.abs(local.co2Percent() - other.co2Percent()));
        }

        return new TransferDiagnostics(boundary.transferBanks().size(), vents,
                vents * TRANSFER_CAPACITY_PER_BLOCK, maxO2Delta, maxCo2Delta);
    }

    /** Downstream-facing scrubber diagnostics for the current sealed room. */
    public static ScrubberDiagnostics inspectScrubbers(ServerLevel level, RoomScanResult room) {
        if (!validRoom(level, room)) return ScrubberDiagnostics.EMPTY;
        Boundary boundary = scanBoundary(level, room);
        int units = 0;
        int ready = 0;
        int active = 0;
        double actualSupport = 0.0D;
        double removalPerSecond = 0.0D;

        for (ScrubberBank bank : boundary.scrubberBanks().values()) {
            for (BlockPos scrubberPos : bank.scrubberPositions()) {
                units++;
                if (!(level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber)) continue;
                if (scrubber.ready(level)) ready++;
                double recentSupport = scrubber.recentActualPlayerEquivalent(level);
                if (recentSupport > 0.0001D) active++;
                actualSupport += recentSupport;
                removalPerSecond += scrubber.recentRemovedCo2PerSecond(level);
            }
        }

        return new ScrubberDiagnostics(units, ready, active,
                units * Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND,
                units * Co2ScrubberBlockEntity.PLAYER_EQUIVALENT_CAPACITY,
                actualSupport, removalPerSecond);
    }

    /**
     * Moves atmosphere through passive treatment edges while a powered main fan is
     * running. Deepest/upstream edges are processed first so a serial path such as
     * Return -> Transfer -> Greenhouse -> Transfer -> Filter -> Fan propagates in
     * the same direction as the actual airflow.
     */
    public static double processPassive(ServerLevel level, Network network, double requestedFlow) {
        if (network == null || requestedFlow <= 0.0D) return requestedFlow;

        boolean changed = false;
        for (int depth = MAX_DEPTH; depth >= 0; depth--) {
            for (TransferStage stage : network.transferStages()) {
                if (stage.depth() != depth) continue;
                double flow = Math.min(requestedFlow, stage.capacity());
                if (flow <= 0.0D) continue;

                RoomAtmosphere source = atmosphere(level, stage.upstream());
                RoomAtmosphere destination = atmosphere(level, stage.downstream());
                double fraction = Math.min(0.35D,
                        flow / Math.max(1.0D, stage.downstream().volume()));
                destination.exchangeFrom(source, fraction);
                changed = true;
            }

            for (ScrubberStage stage : network.scrubberStages()) {
                if (stage.depth() != depth) continue;
                double flow = Math.min(requestedFlow, stage.capacity());
                if (flow <= 0.0D || stage.scrubberPositions().isEmpty()) continue;

                RoomAtmosphere source = atmosphere(level, stage.upstream());
                RoomAtmosphere destination = atmosphere(level, stage.downstream());
                double fraction = Math.min(0.35D,
                        flow / Math.max(1.0D, stage.downstream().volume()));
                destination.exchangeFrom(source, fraction);

                double perUnitFlow = Math.min(Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND,
                        flow / Math.max(1, stage.scrubberPositions().size()));
                for (BlockPos scrubberPos : stage.scrubberPositions()) {
                    if (level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber) {
                        scrubber.processScrubbing(level, destination, stage.downstream(), perUnitFlow);
                    }
                }
                changed = true;
            }

            for (IndustrialStage stage : network.industrialStages()) {
                if (stage.depth() != depth) continue;
                double flow = Math.min(requestedFlow, stage.capacity());
                if (flow <= 0.0D) continue;

                RoomAtmosphere source = atmosphere(level, stage.upstream());
                RoomAtmosphere destination = atmosphere(level, stage.downstream());
                double fraction = Math.min(0.35D,
                        flow / Math.max(1.0D, stage.downstream().volume()));
                destination.exchangeFilteredFrom(source, fraction,
                        stage.dustEfficiency(), stage.radiationEfficiency());
                changed = true;
            }
        }

        if (changed) RoomAtmosphereSavedData.get(level).markChanged();
        double bottleneck = network.passiveBottleneckCapacity();
        return bottleneck > 0.0D ? Math.min(requestedFlow, bottleneck) : requestedFlow;
    }

    /** Compatibility alias for older call sites. */
    public static double processIndustrial(ServerLevel level, Network network, double requestedFlow) {
        return processPassive(level, network, requestedFlow);
    }

    private static void walk(ServerLevel level, RoomScanResult downstream, int depth,
                             Set<Long> visited, Map<Long, RoomScanResult> rooms,
                             List<IndustrialStage> industrialStages,
                             List<TransferStage> transferStages,
                             List<ScrubberStage> scrubberStages) {
        if (depth > MAX_DEPTH || !validRoom(level, downstream)) return;
        long downstreamAnchor = downstream.anchor().asLong();
        if (!visited.add(downstreamAnchor)) return;
        rooms.putIfAbsent(downstreamAnchor, downstream);

        Boundary boundary = scanBoundary(level, downstream);

        // Directional compact filter: current room is the FRONT/clean output.
        for (long packed : boundary.compactFilters()) {
            BlockPos filterPos = BlockPos.of(packed);
            if (!(level.getBlockEntity(filterPos) instanceof AirFilterBlockEntity compact)) continue;
            RoomScanResult input = compact.inspectInput(level);
            if (input == null || input.anchor().asLong() == downstreamAnchor
                    || visited.contains(input.anchor().asLong())) continue;
            walk(level, input, depth + 1, visited, rooms, industrialStages, transferStages, scrubberStages);
        }

        // Powered directional CO2 scrubber. Current room must be its FRONT/output;
        // the room behind the block is traced farther upstream toward RETURN air.
        for (ScrubberBank bank : boundary.scrubberBanks().values()) {
            RoomScanResult upstream = bank.otherRoom();
            if (upstream == null || upstream.anchor().asLong() == downstreamAnchor
                    || visited.contains(upstream.anchor().asLong())) continue;

            ScrubberStage stage = bank.toStage(upstream, downstream, depth);
            if (stage.capacity() <= 0.0D) continue;
            scrubberStages.add(stage);
            walk(level, upstream, depth + 1, visited, rooms, industrialStages, transferStages, scrubberStages);
        }

        // Passive industrial wall: direction is inferred from distance to the fan.
        for (Bank bank : boundary.banks().values()) {
            RoomScanResult upstream = bank.otherRoom();
            if (upstream == null || upstream.anchor().asLong() == downstreamAnchor
                    || visited.contains(upstream.anchor().asLong())) continue;

            IndustrialStage stage = bank.toStage(upstream, downstream, depth);
            if (stage.capacity() <= 0.0D) continue;
            industrialStages.add(stage);
            walk(level, upstream, depth + 1, visited, rooms, industrialStages, transferStages, scrubberStages);
        }

        // Transfer Vent: no filtration, just a controlled passive airflow edge.
        for (TransferBank bank : boundary.transferBanks().values()) {
            RoomScanResult upstream = bank.otherRoom();
            if (upstream == null || upstream.anchor().asLong() == downstreamAnchor
                    || visited.contains(upstream.anchor().asLong())) continue;

            TransferStage stage = bank.toStage(upstream, downstream, depth);
            if (stage.capacity() <= 0.0D) continue;
            transferStages.add(stage);
            walk(level, upstream, depth + 1, visited, rooms, industrialStages, transferStages, scrubberStages);
        }
    }

    private static Boundary scanBoundary(ServerLevel level, RoomScanResult room) {
        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> compactFilters = new HashSet<>();
        Set<Long> inspectedTransferVents = new HashSet<>();
        Map<Long, BankBuilder> builders = new LinkedHashMap<>();
        Map<Long, TransferBankBuilder> transferBuilders = new LinkedHashMap<>();
        Map<Long, ScrubberBankBuilder> scrubberBuilders = new LinkedHashMap<>();

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
                if (state.is(ModBlocks.AIR_FILTER_UNIT.get())) {
                    if (state.hasProperty(AirFilterBlock.FACING)
                            && next.relative(state.getValue(AirFilterBlock.FACING)).equals(current)) {
                        compactFilters.add(next.asLong());
                    }
                    continue;
                }

                if (state.is(ModBlocks.CO2_SCRUBBER.get())) {
                    if (!state.hasProperty(Co2ScrubberBlock.FACING)) continue;
                    Direction facing = state.getValue(Co2ScrubberBlock.FACING);
                    // The current/downstream room must touch the scrubber FRONT.
                    if (!next.relative(facing).equals(current)) continue;
                    BlockPos farSide = next.relative(facing.getOpposite());
                    if (!RoomScanner.airCanPass(level, farSide)) continue;
                    RoomScanResult other = RoomScanner.scan(level, farSide);
                    if (!other.sealed() || other.anchor().equals(room.anchor())) continue;

                    long otherAnchor = other.anchor().asLong();
                    scrubberBuilders.computeIfAbsent(otherAnchor,
                            ignored -> new ScrubberBankBuilder(other)).add(next);
                    continue;
                }

                if (state.is(ModBlocks.TRANSFER_VENT.get())) {
                    if (!inspectedTransferVents.add(next.asLong())) continue;
                    TransferConnection connection = inspectTransferVent(level, next);
                    if (connection == null) continue;
                    RoomScanResult other = connection.otherSide(room.anchor());
                    if (other == null || other.anchor().equals(room.anchor())) continue;

                    long otherAnchor = other.anchor().asLong();
                    transferBuilders.computeIfAbsent(otherAnchor,
                            ignored -> new TransferBankBuilder(other)).add(next);
                    continue;
                }

                FilterType type = FilterType.of(state);
                if (type == null) continue;

                // A valid passive filter wall has air on the exact opposite side.
                BlockPos farSide = next.relative(direction);
                if (!RoomScanner.airCanPass(level, farSide)) continue;
                RoomScanResult other = RoomScanner.scan(level, farSide);
                if (!other.sealed() || other.anchor().equals(room.anchor())) continue;

                long otherAnchor = other.anchor().asLong();
                BankBuilder builder = builders.computeIfAbsent(otherAnchor,
                        ignored -> new BankBuilder(other));
                builder.add(next, type);
            }
        }

        Map<Long, Bank> banks = new LinkedHashMap<>();
        for (Map.Entry<Long, BankBuilder> entry : builders.entrySet()) {
            banks.put(entry.getKey(), entry.getValue().build());
        }

        Map<Long, TransferBank> transferBanks = new LinkedHashMap<>();
        for (Map.Entry<Long, TransferBankBuilder> entry : transferBuilders.entrySet()) {
            transferBanks.put(entry.getKey(), entry.getValue().build());
        }
        Map<Long, ScrubberBank> scrubberBanks = new LinkedHashMap<>();
        for (Map.Entry<Long, ScrubberBankBuilder> entry : scrubberBuilders.entrySet()) {
            scrubberBanks.put(entry.getKey(), entry.getValue().build());
        }
        return new Boundary(compactFilters, banks, transferBanks, scrubberBanks);
    }

    /**
     * Resolves one orientation-free Transfer Vent. A connection exists only when
     * exactly one axis has two distinct sealed air volumes on opposite sides.
     */
    public static TransferConnection inspectTransferVent(ServerLevel level, BlockPos ventPos) {
        if (!level.getBlockState(ventPos).is(ModBlocks.TRANSFER_VENT.get())) return null;

        TransferConnection found = null;
        for (Direction.Axis axis : Direction.Axis.values()) {
            Direction negative = switch (axis) {
                case X -> Direction.WEST;
                case Y -> Direction.DOWN;
                case Z -> Direction.NORTH;
            };
            Direction positive = switch (axis) {
                case X -> Direction.EAST;
                case Y -> Direction.UP;
                case Z -> Direction.SOUTH;
            };

            BlockPos firstPos = ventPos.relative(negative);
            BlockPos secondPos = ventPos.relative(positive);
            if (!RoomScanner.airCanPass(level, firstPos) || !RoomScanner.airCanPass(level, secondPos)) continue;

            RoomScanResult first = RoomScanner.scan(level, firstPos);
            RoomScanResult second = RoomScanner.scan(level, secondPos);
            if (!first.sealed() || !second.sealed() || first.anchor().equals(second.anchor())) continue;

            // More than one valid opposite-room axis is ambiguous; reject it rather
            // than creating an accidental multi-room junction.
            if (found != null) return null;
            found = new TransferConnection(first, second, axis);
        }
        return found;
    }

    private static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        return RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
    }

    private static boolean validRoom(ServerLevel level, RoomScanResult room) {
        return room != null && room.sealed() && RoomScanner.airCanPass(level, room.anchor());
    }

    public record TransferDiagnostics(int connectedRooms, int ventCount,
                                      double totalCapacity, double maxOxygenDelta,
                                      double maxCo2Delta) {
        public static final TransferDiagnostics EMPTY =
                new TransferDiagnostics(0, 0, 0.0D, 0.0D, 0.0D);
    }

    public record ScrubberDiagnostics(int units, int readyUnits, int activeUnits,
                                      double flowCapacity, double nominalPlayerEquivalent,
                                      double actualPlayerEquivalent, double co2RemovedPerSecond) {
        public static final ScrubberDiagnostics EMPTY =
                new ScrubberDiagnostics(0, 0, 0, 0.0D, 0.0D, 0.0D, 0.0D);
    }

    public enum FilterType {
        PRE(PRE_CAPACITY_PER_BLOCK, PRE_DUST_EFFICIENCY, 0.0D),
        HEPA(HEPA_CAPACITY_PER_BLOCK, HEPA_DUST_EFFICIENCY, 0.0D),
        RAD(RAD_CAPACITY_PER_BLOCK, 0.0D, RAD_AIRBORNE_EFFICIENCY);

        private final double capacity;
        private final double dustEfficiency;
        private final double radiationEfficiency;

        FilterType(double capacity, double dustEfficiency, double radiationEfficiency) {
            this.capacity = capacity;
            this.dustEfficiency = dustEfficiency;
            this.radiationEfficiency = radiationEfficiency;
        }

        public double capacity() { return capacity; }
        public double dustEfficiency() { return dustEfficiency; }
        public double radiationEfficiency() { return radiationEfficiency; }

        public static FilterType of(BlockState state) {
            if (state.is(ModBlocks.INDUSTRIAL_PRE_FILTER.get())) return PRE;
            if (state.is(ModBlocks.INDUSTRIAL_HEPA_FILTER.get())) return HEPA;
            if (state.is(ModBlocks.INDUSTRIAL_RAD_FILTER.get())) return RAD;
            return null;
        }
    }

    private static final class BankBuilder {
        private final RoomScanResult otherRoom;
        private final Map<Long, FilterType> blocks = new HashMap<>();

        private BankBuilder(RoomScanResult otherRoom) {
            this.otherRoom = otherRoom;
        }

        private void add(BlockPos pos, FilterType type) {
            blocks.putIfAbsent(pos.asLong(), type);
        }

        private Bank build() {
            int pre = 0;
            int hepa = 0;
            int rad = 0;
            for (FilterType type : blocks.values()) {
                switch (type) {
                    case PRE -> pre++;
                    case HEPA -> hepa++;
                    case RAD -> rad++;
                }
            }
            return new Bank(otherRoom, pre, hepa, rad);
        }
    }

    private static final class TransferBankBuilder {
        private final RoomScanResult otherRoom;
        private final Set<Long> vents = new HashSet<>();

        private TransferBankBuilder(RoomScanResult otherRoom) {
            this.otherRoom = otherRoom;
        }

        private void add(BlockPos pos) {
            vents.add(pos.asLong());
        }

        private TransferBank build() {
            return new TransferBank(otherRoom, vents.size());
        }
    }

    private static final class ScrubberBankBuilder {
        private final RoomScanResult otherRoom;
        private final Set<Long> scrubbers = new HashSet<>();

        private ScrubberBankBuilder(RoomScanResult otherRoom) {
            this.otherRoom = otherRoom;
        }

        private void add(BlockPos pos) {
            scrubbers.add(pos.asLong());
        }

        private ScrubberBank build() {
            List<BlockPos> positions = scrubbers.stream().map(BlockPos::of).toList();
            return new ScrubberBank(otherRoom, positions);
        }
    }

    private record Boundary(Set<Long> compactFilters, Map<Long, Bank> banks,
                            Map<Long, TransferBank> transferBanks,
                            Map<Long, ScrubberBank> scrubberBanks) {}

    private record Bank(RoomScanResult otherRoom, int preBlocks, int hepaBlocks, int radBlocks) {
        private IndustrialStage toStage(RoomScanResult upstream, RoomScanResult downstream, int depth) {
            double preFlow = preBlocks * PRE_CAPACITY_PER_BLOCK;
            double hepaFlow = hepaBlocks * HEPA_CAPACITY_PER_BLOCK;
            double radFlow = radBlocks * RAD_CAPACITY_PER_BLOCK;
            double capacity = preFlow + hepaFlow + radFlow;
            if (capacity <= 0.0D) return new IndustrialStage(upstream, downstream, 0, 0, 0, 0, 0, 0, depth);

            double dustPass = preFlow * (1.0D - PRE_DUST_EFFICIENCY)
                    + hepaFlow * (1.0D - HEPA_DUST_EFFICIENCY)
                    + radFlow;
            double radPass = preFlow + hepaFlow
                    + radFlow * (1.0D - RAD_AIRBORNE_EFFICIENCY);
            double dustEfficiency = 1.0D - dustPass / capacity;
            double radiationEfficiency = 1.0D - radPass / capacity;
            return new IndustrialStage(upstream, downstream, preBlocks, hepaBlocks, radBlocks,
                    capacity, dustEfficiency, radiationEfficiency, depth);
        }
    }

    private record TransferBank(RoomScanResult otherRoom, int ventCount) {
        private TransferStage toStage(RoomScanResult upstream, RoomScanResult downstream, int depth) {
            return new TransferStage(upstream, downstream, ventCount,
                    ventCount * TRANSFER_CAPACITY_PER_BLOCK, depth);
        }
    }

    private record ScrubberBank(RoomScanResult otherRoom, List<BlockPos> scrubberPositions) {
        private ScrubberStage toStage(RoomScanResult upstream, RoomScanResult downstream, int depth) {
            return new ScrubberStage(upstream, downstream, scrubberPositions,
                    scrubberPositions.size() * Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND, depth);
        }
    }

    public record IndustrialStage(RoomScanResult upstream, RoomScanResult downstream,
                                  int preBlocks, int hepaBlocks, int radBlocks,
                                  double capacity, double dustEfficiency,
                                  double radiationEfficiency, int depth) {}

    public record TransferStage(RoomScanResult upstream, RoomScanResult downstream,
                                int ventCount, double capacity, int depth) {}

    public record ScrubberStage(RoomScanResult upstream, RoomScanResult downstream,
                                List<BlockPos> scrubberPositions, double capacity, int depth) {}

    public record TransferConnection(RoomScanResult first, RoomScanResult second, Direction.Axis axis) {
        public RoomScanResult otherSide(BlockPos anchor) {
            if (first.anchor().equals(anchor)) return second;
            if (second.anchor().equals(anchor)) return first;
            return null;
        }
    }

    public record Network(List<RoomScanResult> rooms, List<IndustrialStage> industrialStages,
                          List<TransferStage> transferStages, List<ScrubberStage> scrubberStages,
                          int preBlocks, int hepaBlocks, int radBlocks, int transferVentCount,
                          int scrubberCount, double bottleneckCapacity,
                          double transferBottleneckCapacity, double scrubberBottleneckCapacity) {
        public static final Network EMPTY = new Network(List.of(), List.of(), List.of(), List.of(),
                0, 0, 0, 0, 0, 0.0D, 0.0D, 0.0D);

        public boolean hasIndustrialStages() { return !industrialStages.isEmpty(); }
        public boolean hasTransferStages() { return !transferStages.isEmpty(); }
        public boolean hasScrubberStages() { return !scrubberStages.isEmpty(); }

        /** Minimum airflow capacity in the traced serial treatment path. */
        public double passiveBottleneckCapacity() {
            double cap = Double.POSITIVE_INFINITY;
            if (hasIndustrialStages() && bottleneckCapacity > 0.0D) cap = Math.min(cap, bottleneckCapacity);
            if (hasTransferStages() && transferBottleneckCapacity > 0.0D) cap = Math.min(cap, transferBottleneckCapacity);
            if (hasScrubberStages() && scrubberBottleneckCapacity > 0.0D) cap = Math.min(cap, scrubberBottleneckCapacity);
            return Double.isFinite(cap) ? cap : 0.0D;
        }
    }

    private AirTreatmentNetwork() {}
}
