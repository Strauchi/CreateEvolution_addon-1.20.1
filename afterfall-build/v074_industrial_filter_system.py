from pathlib import Path
import json

ROOT = Path('Afterfall')
JAVA = ROOT / 'src/main/java/dev/afterfall'
RES = ROOT / 'src/main/resources'


def read(path):
    return path.read_text(encoding='utf-8')


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def replace_once(path, old, new):
    text = read(path)
    if old not in text:
        raise RuntimeError(f'Expected text not found in {path}: {old[:120]!r}')
    write(path, text.replace(old, new, 1))

# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
gradle = ROOT / 'gradle.properties'
replace_once(gradle, 'mod_version=0.7.3.2', 'mod_version=0.7.4')

# -----------------------------------------------------------------------------
# Register passive industrial filter blocks and items.
# -----------------------------------------------------------------------------
mod_blocks = JAVA / 'content/ModBlocks.java'
replace_once(mod_blocks,
'''    public static final DeferredBlock<VentilationFanBlock> VENTILATION_FAN = BLOCKS.register("ventilation_fan",
            () -> new VentilationFanBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    private ModBlocks() {}
''',
'''    public static final DeferredBlock<VentilationFanBlock> VENTILATION_FAN = BLOCKS.register("ventilation_fan",
            () -> new VentilationFanBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    // Passive industrial filter media. These blocks deliberately have no facing,
    // block entity, GUI, FE storage or durability. Airflow direction is inferred
    // from the fan and the sealed plenums on both sides of a complete filter wall.
    public static final DeferredBlock<Block> INDUSTRIAL_PRE_FILTER = BLOCKS.registerSimpleBlock(
            "industrial_pre_filter", BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.5F, 8.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL));
    public static final DeferredBlock<Block> INDUSTRIAL_HEPA_FILTER = BLOCKS.registerSimpleBlock(
            "industrial_hepa_filter", BlockBehaviour.Properties.of().mapColor(MapColor.QUARTZ).strength(4.5F, 8.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL));
    public static final DeferredBlock<Block> INDUSTRIAL_RAD_FILTER = BLOCKS.registerSimpleBlock(
            "industrial_rad_filter", BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_BROWN).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL));

    private ModBlocks() {}
''')

mod_items = JAVA / 'content/ModItems.java'
replace_once(mod_items,
'''    public static final DeferredItem<BlockItem> VENTILATION_FAN = ITEMS.registerSimpleBlockItem("ventilation_fan", ModBlocks.VENTILATION_FAN);
''',
'''    public static final DeferredItem<BlockItem> VENTILATION_FAN = ITEMS.registerSimpleBlockItem("ventilation_fan", ModBlocks.VENTILATION_FAN);
    public static final DeferredItem<BlockItem> INDUSTRIAL_PRE_FILTER = ITEMS.registerSimpleBlockItem("industrial_pre_filter", ModBlocks.INDUSTRIAL_PRE_FILTER);
    public static final DeferredItem<BlockItem> INDUSTRIAL_HEPA_FILTER = ITEMS.registerSimpleBlockItem("industrial_hepa_filter", ModBlocks.INDUSTRIAL_HEPA_FILTER);
    public static final DeferredItem<BlockItem> INDUSTRIAL_RAD_FILTER = ITEMS.registerSimpleBlockItem("industrial_rad_filter", ModBlocks.INDUSTRIAL_RAD_FILTER);
''')

creative = JAVA / 'content/ModCreativeTabs.java'
replace_once(creative,
'''                        output.accept(ModItems.VENTILATION_FAN.get());
                        output.accept(ModItems.SEALED_AIRLOCK_DOOR.get());
''',
'''                        output.accept(ModItems.VENTILATION_FAN.get());
                        output.accept(ModItems.INDUSTRIAL_PRE_FILTER.get());
                        output.accept(ModItems.INDUSTRIAL_HEPA_FILTER.get());
                        output.accept(ModItems.INDUSTRIAL_RAD_FILTER.get());
                        output.accept(ModItems.SEALED_AIRLOCK_DOOR.get());
''')

# -----------------------------------------------------------------------------
# Passive air-treatment graph.
# -----------------------------------------------------------------------------
air_treatment = r'''package dev.afterfall.room;

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
'''
write(JAVA / 'room/AirTreatmentNetwork.java', air_treatment)

# -----------------------------------------------------------------------------
# Intake diagnostics: use the unified treatment graph so the fan can see intakes
# through either compact filters or passive industrial filter walls.
# -----------------------------------------------------------------------------
intake_scanner = JAVA / 'room/IntakeNetworkScanner.java'
text = read(intake_scanner)
start = text.index('    public static Stats inspectUpstream')
end = text.index('    private static Stats statsFor', start)
new_upstream = '''    public static Stats inspectUpstream(ServerLevel level, RoomScanResult room) {
        if (!validRoom(level, room)) return Stats.EMPTY;

        AirTreatmentNetwork.Network treatment = AirTreatmentNetwork.trace(level, room);
        Set<Long> roomAnchors = new HashSet<>();
        Set<Long> intakes = new HashSet<>();
        for (RoomScanResult treatmentRoom : treatment.rooms()) {
            roomAnchors.add(treatmentRoom.anchor().asLong());
            intakes.addAll(scanBoundary(level, treatmentRoom).intakes());
        }
        return statsFor(level, intakes, roomAnchors);
    }

'''
text = text[:start] + new_upstream + text[end:]
write(intake_scanner, text)

# -----------------------------------------------------------------------------
# Main fan: return air can enter any upstream treatment plenum, then passive
# industrial stages are processed toward the fan before supply air is moved.
# -----------------------------------------------------------------------------
fan = JAVA / 'blockentity/VentilationFanBlockEntity.java'
replace_once(fan,
'''import dev.afterfall.room.RoomAtmosphere;
''',
'''import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.RoomAtmosphere;
''')

replace_once(fan,
'''    public int connectedReturnVentCount(ServerLevel level) {
        VentilationNetworkScanner.Network network = inspectReturnNetwork(level);
        RoomScanResult inlet = inspectInlet(level);
        return network == null || !network.valid() || inlet == null
                ? 0 : validVentCount(level, network, true, inlet.anchor());
    }
''',
'''    public int connectedReturnVentCount(ServerLevel level) {
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
''')

old_group = '''        for (List<PoweredFan> group : inletGroups.values()) {
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
'''
new_group = '''        for (List<PoweredFan> group : inletGroups.values()) {
            PoweredFan representative = group.get(0);
            RoomScanResult inlet = representative.inlet;
            double groupFlow = group.size() * FLOW_M3_PER_SECOND;

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
                }
            }

            // Passive industrial filters only move air while a powered main fan is
            // pulling through them. Compact filter units keep their own powered BE
            // processing; the treatment graph simply lets both systems coexist.
            AirTreatmentNetwork.processIndustrial(serverLevel, treatment, groupFlow);

            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, inlet);
            double effectiveFlow = treatment.hasIndustrialStages()
                    ? Math.min(groupFlow, treatment.bottleneckCapacity()) : groupFlow;
            double inletFraction = Math.min(1.0D,
                    effectiveFlow / Math.max(1.0D, supplyNetwork.shaft().volume()));
            shaftAir.exchangeFrom(inletAir, inletFraction);
        }
'''
replace_once(fan, old_group, new_group)

replace_once(fan,
'''    private record PoweredFan(VentilationFanBlockEntity fan, BlockPos pos, RoomScanResult inlet) {}
    private record VentTarget(BlockPos pos, RoomScanResult room) {}
''',
'''    private static List<ReturnTarget> collectReturnTargets(ServerLevel level, AirTreatmentNetwork.Network treatment) {
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

    private record PoweredFan(VentilationFanBlockEntity fan, BlockPos pos, RoomScanResult inlet) {}
    private record VentTarget(BlockPos pos, RoomScanResult room) {}
    private record ReturnTarget(BlockPos pos, RoomScanResult networkRoom, RoomScanResult room) {}
''')

# -----------------------------------------------------------------------------
# Fan GUI data for passive filter counts and serial bottleneck capacity.
# -----------------------------------------------------------------------------
menu = JAVA / 'menu/MachineMenu.java'
replace_once(menu,
'''import dev.afterfall.room.RoomAtmosphere;
''',
'''import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.RoomAtmosphere;
''')
replace_once(menu, '    public static final int DATA_COUNT = 28;\n', '    public static final int DATA_COUNT = 32;\n')
replace_once(menu,
'''    public static final int D_INPUT_AIR_RAD_X100 = 27;
''',
'''    public static final int D_INPUT_AIR_RAD_X100 = 27;
    public static final int D_IND_PRE = 28;
    public static final int D_IND_HEPA = 29;
    public static final int D_IND_RAD = 30;
    public static final int D_IND_CAPACITY_X10 = 31;
''')
replace_once(menu,
'''            if (inlet != null) setIntakeStats(IntakeNetworkScanner.inspectUpstream(level, inlet));
''',
'''            if (inlet != null) {
                setIntakeStats(IntakeNetworkScanner.inspectUpstream(level, inlet));
                AirTreatmentNetwork.Network treatment = AirTreatmentNetwork.trace(level, inlet);
                data.set(D_IND_PRE, treatment.preBlocks());
                data.set(D_IND_HEPA, treatment.hepaBlocks());
                data.set(D_IND_RAD, treatment.radBlocks());
                data.set(D_IND_CAPACITY_X10, scale(treatment.bottleneckCapacity(), 10.0D));
            }
''')
replace_once(menu,
'''    public double inputAirRadiation() { return get(D_INPUT_AIR_RAD_X100) / 100.0D; }
''',
'''    public double inputAirRadiation() { return get(D_INPUT_AIR_RAD_X100) / 100.0D; }
    public int industrialPreBlocks() { return get(D_IND_PRE); }
    public int industrialHepaBlocks() { return get(D_IND_HEPA); }
    public int industrialRadBlocks() { return get(D_IND_RAD); }
    public double industrialCapacity() { return get(D_IND_CAPACITY_X10) / 10.0D; }
''')

screen = JAVA / 'client/MachineScreen.java'
replace_once(screen,
'''        graphics.drawString(font, String.format(Locale.ROOT, "Fan capacity: %.1f m³/s", menu.flow()), 12, 129, 0xFFD3DDDF, false);
''',
'''        String filterCap = menu.industrialCapacity() > 0.0D
                ? String.format(Locale.ROOT, "%.1f", menu.industrialCapacity()) : "--";
        graphics.drawString(font, String.format(Locale.ROOT, "Fan %.1f m³/s | Industrial cap %s", menu.flow(), filterCap),
                12, 129, 0xFFD3DDDF, false);
''')
replace_once(screen,
'''        if (volume > 0) {
            graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 12, 166, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 124, 166, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%%", menu.oxygenPercent()), 12, 179, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "CO2: %.2f%%", menu.co2Percent()), 124, 179, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 12, 192, 0xFFD3DDDF, false);
        }
''',
'''        graphics.drawString(font, String.format(Locale.ROOT, "Industrial P:%d H:%d R:%d",
                menu.industrialPreBlocks(), menu.industrialHepaBlocks(), menu.industrialRadBlocks()),
                12, 166, 0xFF9DB7BD, false);
        if (volume > 0) {
            graphics.drawString(font, String.format(Locale.ROOT, "Air %.1f%% | Dust %.2f%% | Rad %.2f",
                    menu.airQuality(), menu.dustPercent(), menu.airRadiation()), 12, 179, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2 %.2f%% | CO2 %.2f%%",
                    menu.oxygenPercent(), menu.co2Percent()), 12, 192, 0xFFD3DDDF, false);
        }
''')

# -----------------------------------------------------------------------------
# Shielding: industrial filters are intentional air paths, so they shield less
# than solid bunker blocks while still remaining airtight room boundaries.
# -----------------------------------------------------------------------------
scanner = JAVA / 'room/RoomScanner.java'
replace_once(scanner,
'''        if (state.is(ModBlocks.AIR_FILTER_UNIT.get())) return 0.20D;
''',
'''        if (state.is(ModBlocks.AIR_FILTER_UNIT.get())) return 0.20D;
        if (state.is(ModBlocks.INDUSTRIAL_PRE_FILTER.get())) return 0.46D;
        if (state.is(ModBlocks.INDUSTRIAL_HEPA_FILTER.get())) return 0.44D;
        if (state.is(ModBlocks.INDUSTRIAL_RAD_FILTER.get())) return 0.36D;
''')

# -----------------------------------------------------------------------------
# Visible version string.
# -----------------------------------------------------------------------------
afterfall = JAVA / 'Afterfall.java'
replace_once(afterfall, 'LOGGER.info("Afterfall 0.7.3 initialized");', 'LOGGER.info("Afterfall 0.7.4 initialized");')

# -----------------------------------------------------------------------------
# Language + placeholder assets.
# -----------------------------------------------------------------------------
lang_path = RES / 'assets/afterfall/lang/en_us.json'
lang = json.loads(read(lang_path))
lang['block.afterfall.industrial_pre_filter'] = 'Industrial Pre-Filter'
lang['block.afterfall.industrial_hepa_filter'] = 'Industrial HEPA Filter'
lang['block.afterfall.industrial_rad_filter'] = 'Industrial Radiological Filter'
write(lang_path, json.dumps(lang, indent=2) + '\n')

assets = {
    'industrial_pre_filter': 'minecraft:block/gray_concrete',
    'industrial_hepa_filter': 'minecraft:block/quartz_block_side',
    'industrial_rad_filter': 'minecraft:block/brown_concrete',
}
for name, texture in assets.items():
    write(RES / f'assets/afterfall/blockstates/{name}.json', json.dumps({
        'variants': {'': {'model': f'afterfall:block/{name}'}}
    }, indent=2) + '\n')
    write(RES / f'assets/afterfall/models/block/{name}.json', json.dumps({
        'parent': 'minecraft:block/cube_all',
        'textures': {'all': texture}
    }, indent=2) + '\n')
    write(RES / f'assets/afterfall/models/item/{name}.json', json.dumps({
        'parent': f'afterfall:block/{name}'
    }, indent=2) + '\n')
    write(RES / f'data/afterfall/loot_table/blocks/{name}.json', json.dumps({
        'type': 'minecraft:block',
        'pools': [{
            'rolls': 1,
            'entries': [{'type': 'minecraft:item', 'name': f'afterfall:{name}'}],
            'conditions': [{'condition': 'minecraft:survives_explosion'}]
        }]
    }, indent=2) + '\n')

print('Afterfall 0.7.4 passive industrial filtration system applied')
