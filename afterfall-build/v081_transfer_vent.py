from pathlib import Path

root = Path('Afterfall')
src = root / 'src/main/java/dev/afterfall'
res = root / 'src/main/resources'


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'Pattern not found in {path}: {old[:120]!r}')
    path.write_text(text.replace(old, new, 1))

# -----------------------------------------------------------------------------
# Block/item registration
# -----------------------------------------------------------------------------
mod_blocks = src / 'content/ModBlocks.java'
replace_once(mod_blocks,
'''    public static final DeferredBlock<AirVentBlock> AIR_VENT = BLOCKS.register("air_vent",
            () -> new AirVentBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(3.5F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    public static final DeferredBlock<VentilationFanBlock> VENTILATION_FAN = BLOCKS.register("ventilation_fan",''',
'''    public static final DeferredBlock<AirVentBlock> AIR_VENT = BLOCKS.register("air_vent",
            () -> new AirVentBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(3.5F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    // Passive, orientation-free room-to-room airflow grille. It remains airtight
    // to the RoomScanner; the ventilation graph moves air through it only while a
    // powered main fan is pulling across two distinct sealed rooms.
    public static final DeferredBlock<Block> TRANSFER_VENT = BLOCKS.registerSimpleBlock("transfer_vent",
            BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(3.5F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL));

    public static final DeferredBlock<VentilationFanBlock> VENTILATION_FAN = BLOCKS.register("ventilation_fan",''')

mod_items = src / 'content/ModItems.java'
replace_once(mod_items,
'''    public static final DeferredItem<BlockItem> AIR_VENT = ITEMS.registerSimpleBlockItem("air_vent", ModBlocks.AIR_VENT);
    public static final DeferredItem<BlockItem> VENTILATION_FAN = ITEMS.registerSimpleBlockItem("ventilation_fan", ModBlocks.VENTILATION_FAN);''',
'''    public static final DeferredItem<BlockItem> AIR_VENT = ITEMS.registerSimpleBlockItem("air_vent", ModBlocks.AIR_VENT);
    public static final DeferredItem<BlockItem> TRANSFER_VENT = ITEMS.registerSimpleBlockItem("transfer_vent", ModBlocks.TRANSFER_VENT);
    public static final DeferredItem<BlockItem> VENTILATION_FAN = ITEMS.registerSimpleBlockItem("ventilation_fan", ModBlocks.VENTILATION_FAN);''')

creative = src / 'content/ModCreativeTabs.java'
replace_once(creative,
'''                        output.accept(ModItems.AIR_VENT.get());
                        output.accept(ModItems.VENTILATION_FAN.get());''',
'''                        output.accept(ModItems.AIR_VENT.get());
                        output.accept(ModItems.TRANSFER_VENT.get());
                        output.accept(ModItems.VENTILATION_FAN.get());''')

# -----------------------------------------------------------------------------
# RoomScanner: Transfer Vent is an airtight boundary, not an open air cell.
# -----------------------------------------------------------------------------
scanner = src / 'room/RoomScanner.java'
replace_once(scanner,
'''        if (state.is(ModBlocks.AIR_VENT.get()) || state.is(ModBlocks.VENTILATION_FAN.get())) return false;''',
'''        if (state.is(ModBlocks.AIR_VENT.get()) || state.is(ModBlocks.TRANSFER_VENT.get())
                || state.is(ModBlocks.VENTILATION_FAN.get())) return false;''')
replace_once(scanner,
'''        if (state.is(ModBlocks.AIR_VENT.get())) return 0.48D;
        if (state.is(Blocks.IRON_BLOCK)) return 0.22D;''',
'''        if (state.is(ModBlocks.AIR_VENT.get())) return 0.48D;
        if (state.is(ModBlocks.TRANSFER_VENT.get())) return 0.46D;
        if (state.is(Blocks.IRON_BLOCK)) return 0.22D;''')

# -----------------------------------------------------------------------------
# Air treatment graph with passive transfer edges.
# -----------------------------------------------------------------------------
air_treatment = src / 'room/AirTreatmentNetwork.java'
air_treatment.write_text(r'''package dev.afterfall.room;

import dev.afterfall.block.AirFilterBlock;
import dev.afterfall.blockentity.AirFilterBlockEntity;
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
        Set<Long> visited = new HashSet<>();
        walk(level, fanInlet, 0, visited, rooms, industrialStages, transferStages);

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

        return new Network(List.copyOf(rooms.values()), List.copyOf(industrialStages),
                List.copyOf(transferStages), pre, hepa, rad, transferVents,
                industrialBottleneck, transferBottleneck);
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
                             List<TransferStage> transferStages) {
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
            walk(level, input, depth + 1, visited, rooms, industrialStages, transferStages);
        }

        // Passive industrial wall: direction is inferred from distance to the fan.
        for (Bank bank : boundary.banks().values()) {
            RoomScanResult upstream = bank.otherRoom();
            if (upstream == null || upstream.anchor().asLong() == downstreamAnchor
                    || visited.contains(upstream.anchor().asLong())) continue;

            IndustrialStage stage = bank.toStage(upstream, downstream, depth);
            if (stage.capacity() <= 0.0D) continue;
            industrialStages.add(stage);
            walk(level, upstream, depth + 1, visited, rooms, industrialStages, transferStages);
        }

        // Transfer Vent: no filtration, just a controlled passive airflow edge.
        for (TransferBank bank : boundary.transferBanks().values()) {
            RoomScanResult upstream = bank.otherRoom();
            if (upstream == null || upstream.anchor().asLong() == downstreamAnchor
                    || visited.contains(upstream.anchor().asLong())) continue;

            TransferStage stage = bank.toStage(upstream, downstream, depth);
            if (stage.capacity() <= 0.0D) continue;
            transferStages.add(stage);
            walk(level, upstream, depth + 1, visited, rooms, industrialStages, transferStages);
        }
    }

    private static Boundary scanBoundary(ServerLevel level, RoomScanResult room) {
        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> compactFilters = new HashSet<>();
        Set<Long> inspectedTransferVents = new HashSet<>();
        Map<Long, BankBuilder> builders = new LinkedHashMap<>();
        Map<Long, TransferBankBuilder> transferBuilders = new LinkedHashMap<>();

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
        return new Boundary(compactFilters, banks, transferBanks);
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

    private record Boundary(Set<Long> compactFilters, Map<Long, Bank> banks,
                            Map<Long, TransferBank> transferBanks) {}

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

    public record IndustrialStage(RoomScanResult upstream, RoomScanResult downstream,
                                  int preBlocks, int hepaBlocks, int radBlocks,
                                  double capacity, double dustEfficiency,
                                  double radiationEfficiency, int depth) {}

    public record TransferStage(RoomScanResult upstream, RoomScanResult downstream,
                                int ventCount, double capacity, int depth) {}

    public record TransferConnection(RoomScanResult first, RoomScanResult second, Direction.Axis axis) {
        public RoomScanResult otherSide(BlockPos anchor) {
            if (first.anchor().equals(anchor)) return second;
            if (second.anchor().equals(anchor)) return first;
            return null;
        }
    }

    public record Network(List<RoomScanResult> rooms, List<IndustrialStage> industrialStages,
                          List<TransferStage> transferStages,
                          int preBlocks, int hepaBlocks, int radBlocks, int transferVentCount,
                          double bottleneckCapacity, double transferBottleneckCapacity) {
        public static final Network EMPTY = new Network(List.of(), List.of(), List.of(),
                0, 0, 0, 0, 0.0D, 0.0D);

        public boolean hasIndustrialStages() { return !industrialStages.isEmpty(); }
        public boolean hasTransferStages() { return !transferStages.isEmpty(); }

        /** Minimum passive capacity in the traced serial treatment path. */
        public double passiveBottleneckCapacity() {
            double cap = Double.POSITIVE_INFINITY;
            if (hasIndustrialStages() && bottleneckCapacity > 0.0D) cap = Math.min(cap, bottleneckCapacity);
            if (hasTransferStages() && transferBottleneckCapacity > 0.0D) cap = Math.min(cap, transferBottleneckCapacity);
            return Double.isFinite(cap) ? cap : 0.0D;
        }
    }

    private AirTreatmentNetwork() {}
}
''')

# -----------------------------------------------------------------------------
# Main fan uses the complete passive path and reports/obeys its bottleneck.
# -----------------------------------------------------------------------------
fan = src / 'blockentity/VentilationFanBlockEntity.java'
replace_once(fan,
'''    public double currentSupplyFlow(ServerLevel level) {
        return Math.min(availableNetworkFlow(level), connectedSupplyVentCount(level) * MAX_FLOW_PER_VENT);
    }

    public double currentReturnFlow(ServerLevel level) {
        return Math.min(availableNetworkFlow(level), connectedReturnVentCount(level) * MAX_FLOW_PER_VENT);
    }''',
'''    public double currentSupplyFlow(ServerLevel level) {
        double flow = Math.min(availableNetworkFlow(level), connectedSupplyVentCount(level) * MAX_FLOW_PER_VENT);
        double passiveCap = inspectTreatmentNetwork(level).passiveBottleneckCapacity();
        return passiveCap > 0.0D ? Math.min(flow, passiveCap) : flow;
    }

    public double currentReturnFlow(ServerLevel level) {
        double flow = Math.min(availableNetworkFlow(level), connectedReturnVentCount(level) * MAX_FLOW_PER_VENT);
        double passiveCap = inspectTreatmentNetwork(level).passiveBottleneckCapacity();
        return passiveCap > 0.0D ? Math.min(flow, passiveCap) : flow;
    }''')

replace_once(fan,
'''        for (List<PoweredFan> group : inletGroups.values()) {''',
'''        double deliveredFlow = 0.0D;
        for (List<PoweredFan> group : inletGroups.values()) {''')

replace_once(fan,
'''            // Passive industrial filters only move air while a powered main fan is
            // pulling through them. Compact filter units keep their own powered BE
            // processing; the treatment graph simply lets both systems coexist.
            AirTreatmentNetwork.processIndustrial(serverLevel, treatment, groupFlow);

            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, inlet);
            double effectiveFlow = treatment.hasIndustrialStages()
                    ? Math.min(groupFlow, treatment.bottleneckCapacity()) : groupFlow;
            double inletFraction = Math.min(1.0D,
                    effectiveFlow / Math.max(1.0D, supplyNetwork.shaft().volume()));
            shaftAir.exchangeFrom(inletAir, inletFraction);''',
'''            // Passive industrial filters and Transfer Vents only move air while a
            // powered main fan is pulling through them. Compact filter units keep
            // their own powered block-entity processing.
            double effectiveFlow = AirTreatmentNetwork.processPassive(serverLevel, treatment, groupFlow);

            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, inlet);
            double inletFraction = Math.min(1.0D,
                    effectiveFlow / Math.max(1.0D, supplyNetwork.shaft().volume()));
            shaftAir.exchangeFrom(inletAir, inletFraction);
            deliveredFlow += effectiveFlow;''')

replace_once(fan,
'''        double totalFlow = powered.size() * FLOW_M3_PER_SECOND;
        double perSupplyFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / supplies.size());''',
'''        double totalFlow = Math.min(powered.size() * FLOW_M3_PER_SECOND, deliveredFlow);
        double perSupplyFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / supplies.size());''')

# -----------------------------------------------------------------------------
# Fan GUI diagnostics: Transfer count + bottleneck.
# -----------------------------------------------------------------------------
menu = src / 'menu/MachineMenu.java'
replace_once(menu, 'public static final int DATA_COUNT = 33;', 'public static final int DATA_COUNT = 35;')
replace_once(menu,
'''    public static final int D_INTAKE_DEMAND_X10 = 32;''',
'''    public static final int D_INTAKE_DEMAND_X10 = 32;
    public static final int D_TRANSFER_VENTS = 33;
    public static final int D_TRANSFER_CAPACITY_X10 = 34;''')
replace_once(menu,
'''                data.set(D_IND_RAD, treatment.radBlocks());
                data.set(D_IND_CAPACITY_X10, scale(treatment.bottleneckCapacity(), 10.0D));''',
'''                data.set(D_IND_RAD, treatment.radBlocks());
                data.set(D_IND_CAPACITY_X10, scale(treatment.bottleneckCapacity(), 10.0D));
                data.set(D_TRANSFER_VENTS, treatment.transferVentCount());
                data.set(D_TRANSFER_CAPACITY_X10, scale(treatment.transferBottleneckCapacity(), 10.0D));''')
replace_once(menu,
'''    public double industrialCapacity() { return get(D_IND_CAPACITY_X10) / 10.0D; }''',
'''    public double industrialCapacity() { return get(D_IND_CAPACITY_X10) / 10.0D; }
    public int transferVentCount() { return get(D_TRANSFER_VENTS); }
    public double transferCapacity() { return get(D_TRANSFER_CAPACITY_X10) / 10.0D; }''')

screen = src / 'client/MachineScreen.java'
replace_once(screen,
'''        graphics.drawString(font, String.format(Locale.ROOT, "Intakes %d/%d | Industrial P:%d H:%d R:%d",
                menu.intakeReady(), menu.intakeTotal(), menu.industrialPreBlocks(),
                menu.industrialHepaBlocks(), menu.industrialRadBlocks()),
                12, 166, 0xFF9DB7BD, false);''',
'''        String transferCap = menu.transferCapacity() > 0.0D
                ? String.format(Locale.ROOT, "%.1f", menu.transferCapacity()) : "--";
        graphics.drawString(font, String.format(Locale.ROOT, "I %d/%d | P:%d H:%d R:%d | X:%d cap %s",
                menu.intakeReady(), menu.intakeTotal(), menu.industrialPreBlocks(),
                menu.industrialHepaBlocks(), menu.industrialRadBlocks(),
                menu.transferVentCount(), transferCap),
                12, 166, 0xFF9DB7BD, false);''')

# -----------------------------------------------------------------------------
# Right-click diagnostics for the passive Transfer Vent.
# -----------------------------------------------------------------------------
common = src / 'event/CommonEvents.java'
replace_once(common,
'''import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomScanResult;''',
'''import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomScanResult;''')
replace_once(common,
'''    public static void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {
        BlockState state = event.getLevel().getBlockState(event.getPos());


        if (state.is(ModBlocks.AIR_VENT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {''',
'''    public static void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {
        BlockState state = event.getLevel().getBlockState(event.getPos());

        if (state.is(ModBlocks.TRANSFER_VENT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                AirTreatmentNetwork.TransferConnection connection =
                        AirTreatmentNetwork.inspectTransferVent(serverLevel, event.getPos());
                if (connection == null) {
                    player.displayClientMessage(Component.literal(
                            "TRANSFER VENT: INVALID - NEEDS TWO DISTINCT SEALED ROOMS ON OPPOSITE SIDES")
                            .withStyle(ChatFormatting.RED), true);
                } else {
                    player.displayClientMessage(Component.literal(String.format(Locale.ROOT,
                            "TRANSFER VENT: CONNECTED | Axis %s | %.1f m³/s | %dm³ <-> %dm³",
                            connection.axis().getName().toUpperCase(Locale.ROOT),
                            AirTreatmentNetwork.TRANSFER_CAPACITY_PER_BLOCK,
                            connection.first().volume(), connection.second().volume()))
                            .withStyle(ChatFormatting.AQUA), true);
                }
            }
            return;
        }

        if (state.is(ModBlocks.AIR_VENT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {''')

# -----------------------------------------------------------------------------
# Assets / loot / translations.
# -----------------------------------------------------------------------------
(res / 'assets/afterfall/blockstates/transfer_vent.json').write_text('''{
  "variants": {
    "": { "model": "afterfall:block/transfer_vent" }
  }
}\n''')
(res / 'assets/afterfall/models/block/transfer_vent.json').write_text('''{
  "parent": "minecraft:block/cube_all",
  "textures": { "all": "minecraft:block/iron_trapdoor" }
}\n''')
(res / 'assets/afterfall/models/item/transfer_vent.json').write_text('''{
  "parent": "afterfall:block/transfer_vent"
}\n''')
loot = res / 'data/afterfall/loot_table/blocks/transfer_vent.json'
loot.parent.mkdir(parents=True, exist_ok=True)
loot.write_text('''{
  "type": "minecraft:block",
  "pools": [
    {
      "rolls": 1,
      "entries": [
        { "type": "minecraft:item", "name": "afterfall:transfer_vent" }
      ],
      "conditions": [
        { "condition": "minecraft:survives_explosion" }
      ]
    }
  ]
}\n''')

en = res / 'assets/afterfall/lang/en_us.json'
replace_once(en,
'''  "block.afterfall.air_vent": "Air Vent",
  "block.afterfall.ventilation_fan": "Main Ventilation Fan",''',
'''  "block.afterfall.air_vent": "Air Vent",
  "block.afterfall.transfer_vent": "Air Transfer Vent",
  "block.afterfall.ventilation_fan": "Main Ventilation Fan",''')

de = res / 'assets/afterfall/lang/de_de.json'
replace_once(de,
'''  "block.afterfall.air_vent": "Lüftungsventil",
  "block.afterfall.ventilation_fan": "Hauptlüfter"''',
'''  "block.afterfall.air_vent": "Lüftungsventil",
  "block.afterfall.transfer_vent": "Luft-Transfergitter",
  "block.afterfall.ventilation_fan": "Hauptlüfter"''')

# -----------------------------------------------------------------------------
# Version metadata.
# -----------------------------------------------------------------------------
props = root / 'gradle.properties'
replace_once(props, 'mod_version=0.8.0.1\n', 'mod_version=0.8.1\n')
main = src / 'Afterfall.java'
replace_once(main, 'Afterfall 0.8.0.1 initialized', 'Afterfall 0.8.1 initialized')

print('Afterfall 0.8.1 Transfer Vent patch applied')
