package dev.afterfall.room;

import dev.afterfall.block.AirFilterBlock;
import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Traces the air-treatment path upstream from a main fan inlet.
 *
 * Compact filter units are directional machine edges (FRONT -> BACK when tracing
 * upstream). Industrial filter blocks are passive and have no facing. Their flow
 * direction is inferred from the fan: starting in the fan inlet/clean plenum, the
 * room on the far side of a complete filter wall is upstream.
 */
public final class AirTreatmentNetwork {
    public static final int MAX_DEPTH = 12;

    public static final double PRE_CAPACITY_PER_BLOCK = 14.0D;
    public static final double HEPA_CAPACITY_PER_BLOCK = 10.0D;
    public static final double RAD_CAPACITY_PER_BLOCK = 8.0D;

    public static final double PRE_DUST_EFFICIENCY = 0.70D;
    public static final double HEPA_DUST_EFFICIENCY = 0.95D;
    public static final double RAD_AIRBORNE_EFFICIENCY = 0.98D;

    public static Network trace(ServerLevel level, RoomScanResult fanInlet) {
        if (!validRoom(level, fanInlet)) return Network.EMPTY;

        LinkedHashMap<Long, RoomScanResult> rooms = new LinkedHashMap<>();
        List<IndustrialStage> stages = new ArrayList<>();
        Set<Long> visited = new HashSet<>();
        walk(level, fanInlet, 0, visited, rooms, stages);

        int pre = 0;
        int hepa = 0;
        int rad = 0;
        double bottleneck = Double.POSITIVE_INFINITY;
        for (IndustrialStage stage : stages) {
            pre += stage.preBlocks();
            hepa += stage.hepaBlocks();
            rad += stage.radBlocks();
            bottleneck = Math.min(bottleneck, stage.capacity());
        }
        if (stages.isEmpty()) bottleneck = 0.0D;

        return new Network(List.copyOf(rooms.values()), List.copyOf(stages),
                pre, hepa, rad, bottleneck);
    }

    /**
     * Pushes upstream composition through every passive industrial stage toward
     * the fan. Deepest stages are processed first, so serial filter rooms update
     * in the physical upstream -> downstream order.
     */
    public static double processIndustrial(ServerLevel level, Network network, double requestedFlow) {
        if (network == null || network.industrialStages().isEmpty() || requestedFlow <= 0.0D) return requestedFlow;

        List<IndustrialStage> ordered = new ArrayList<>(network.industrialStages());
        ordered.sort(Comparator.comparingInt(IndustrialStage::depth).reversed());

        boolean changed = false;
        for (IndustrialStage stage : ordered) {
            double flow = Math.min(requestedFlow, stage.capacity());
            if (flow <= 0.0D) continue;

            RoomAtmosphere source = atmosphere(level, stage.upstream());
            RoomAtmosphere destination = atmosphere(level, stage.downstream());
            double fraction = Math.min(0.35D, flow / Math.max(1.0D, stage.downstream().volume()));
            destination.exchangeFilteredFrom(source, fraction,
                    stage.dustEfficiency(), stage.radiationEfficiency());
            changed = true;
        }
        if (changed) RoomAtmosphereSavedData.get(level).markChanged();
        return Math.min(requestedFlow, network.bottleneckCapacity() > 0.0D
                ? network.bottleneckCapacity() : requestedFlow);
    }

    private static void walk(ServerLevel level, RoomScanResult downstream, int depth,
                             Set<Long> visited, Map<Long, RoomScanResult> rooms,
                             List<IndustrialStage> stages) {
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
            if (input == null || input.anchor().asLong() == downstreamAnchor) continue;
            walk(level, input, depth + 1, visited, rooms, stages);
        }

        // Passive industrial wall: direction is defined by distance from the fan.
        for (Bank bank : boundary.banks().values()) {
            RoomScanResult upstream = bank.otherRoom();
            if (upstream == null || upstream.anchor().asLong() == downstreamAnchor
                    || visited.contains(upstream.anchor().asLong())) continue;

            IndustrialStage stage = bank.toStage(upstream, downstream, depth);
            if (stage.capacity() <= 0.0D) continue;
            stages.add(stage);
            walk(level, upstream, depth + 1, visited, rooms, stages);
        }
    }

    private static Boundary scanBoundary(ServerLevel level, RoomScanResult room) {
        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> compactFilters = new HashSet<>();
        Map<Long, BankBuilder> builders = new LinkedHashMap<>();

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

                FilterType type = FilterType.of(state);
                if (type == null) continue;

                // A valid passive filter wall has air on the exact opposite side of
                // this block. If the far side belongs to the same room, the wall has
                // a bypass/opening and therefore does not act as a treatment stage.
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
        return new Boundary(compactFilters, banks);
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

    private record Boundary(Set<Long> compactFilters, Map<Long, Bank> banks) {}

    private record Bank(RoomScanResult otherRoom, int preBlocks, int hepaBlocks, int radBlocks) {
        private IndustrialStage toStage(RoomScanResult upstream, RoomScanResult downstream, int depth) {
            double preFlow = preBlocks * PRE_CAPACITY_PER_BLOCK;
            double hepaFlow = hepaBlocks * HEPA_CAPACITY_PER_BLOCK;
            double radFlow = radBlocks * RAD_CAPACITY_PER_BLOCK;
            double capacity = preFlow + hepaFlow + radFlow;
            if (capacity <= 0.0D) return new IndustrialStage(upstream, downstream, 0, 0, 0, 0, 0, 0, depth);

            // Mixed walls are interpreted as parallel lanes. Normal gameplay is one
            // filter type per wall, but this weighted form behaves sensibly if a
            // player intentionally mixes types in one plane.
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

    public record IndustrialStage(RoomScanResult upstream, RoomScanResult downstream,
                                  int preBlocks, int hepaBlocks, int radBlocks,
                                  double capacity, double dustEfficiency,
                                  double radiationEfficiency, int depth) {}

    public record Network(List<RoomScanResult> rooms, List<IndustrialStage> industrialStages,
                          int preBlocks, int hepaBlocks, int radBlocks,
                          double bottleneckCapacity) {
        public static final Network EMPTY = new Network(List.of(), List.of(), 0, 0, 0, 0.0D);
        public boolean hasIndustrialStages() { return !industrialStages.isEmpty(); }
    }

    private AirTreatmentNetwork() {}
}
