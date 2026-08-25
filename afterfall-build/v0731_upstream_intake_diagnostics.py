from pathlib import Path

root = Path('Afterfall')

scanner = root / 'src/main/java/dev/afterfall/room/IntakeNetworkScanner.java'
scanner.write_text(r'''package dev.afterfall.room;

import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;

import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Set;

/** Aggregates outside-air intakes bordering sealed ventilation plenums. */
public final class IntakeNetworkScanner {
    private static final int MAX_UPSTREAM_FILTER_DEPTH = 8;

    /** Direct intakes attached to exactly this sealed room/plenum. */
    public static Stats inspect(ServerLevel level, RoomScanResult room) {
        if (!validRoom(level, room)) return Stats.EMPTY;
        Boundary boundary = scanBoundary(level, room);
        return statsFor(level, boundary.intakes(), Set.of(room.anchor().asLong()));
    }

    /**
     * Finds fresh-air sources upstream of a clean plenum by walking backwards through
     * directional compact filters. A filter is traversed only when its FRONT/output
     * belongs to the current room; recursion then continues from its BACK/input room.
     * This keeps physically separate mixing and clean plenums separate while allowing
     * the main fan GUI to report the fresh-air supply feeding the complete filter chain.
     */
    public static Stats inspectUpstream(ServerLevel level, RoomScanResult room) {
        if (!validRoom(level, room)) return Stats.EMPTY;

        Set<Long> visitedRooms = new HashSet<>();
        Set<Long> roomAnchors = new HashSet<>();
        Set<Long> intakes = new HashSet<>();
        collectUpstream(level, room, 0, visitedRooms, roomAnchors, intakes);
        return statsFor(level, intakes, roomAnchors);
    }

    private static void collectUpstream(ServerLevel level, RoomScanResult room, int depth,
                                        Set<Long> visitedRooms, Set<Long> roomAnchors, Set<Long> intakes) {
        if (depth > MAX_UPSTREAM_FILTER_DEPTH || !validRoom(level, room)) return;
        long anchor = room.anchor().asLong();
        if (!visitedRooms.add(anchor)) return;
        roomAnchors.add(anchor);

        Boundary boundary = scanBoundary(level, room);
        intakes.addAll(boundary.intakes());

        for (long packed : boundary.filters()) {
            BlockPos filterPos = BlockPos.of(packed);
            if (!(level.getBlockEntity(filterPos) instanceof AirFilterBlockEntity filter)) continue;
            RoomScanResult output = filter.inspectOutput(level);
            RoomScanResult input = filter.inspectInput(level);
            if (output == null || input == null) continue;
            if (output.anchor().asLong() != anchor) continue; // only walk FRONT -> BACK
            if (input.anchor().equals(output.anchor())) continue;
            collectUpstream(level, input, depth + 1, visitedRooms, roomAnchors, intakes);
        }
    }

    private static Stats statsFor(ServerLevel level, Set<Long> intakePositions, Set<Long> roomAnchors) {
        int ready = 0;
        int active = 0;
        for (long packed : intakePositions) {
            if (!(level.getBlockEntity(BlockPos.of(packed)) instanceof AirIntakeBlockEntity intake)) continue;
            boolean intakeReady = false;
            boolean intakeActive = false;
            for (long anchor : roomAnchors) {
                if (!intakeReady && intake.networkReadyFor(anchor)) intakeReady = true;
                if (!intakeActive && intake.ventilatingRoom(anchor)) intakeActive = true;
                if (intakeReady && intakeActive) break;
            }
            if (intakeReady) ready++;
            if (intakeActive) active++;
        }
        return new Stats(intakePositions.size(), ready, active);
    }

    private static Boundary scanBoundary(ServerLevel level, RoomScanResult room) {
        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> intakePositions = new HashSet<>();
        Set<Long> filterPositions = new HashSet<>();
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
                if (level.getBlockState(next).is(ModBlocks.AIR_INTAKE_UNIT.get())) {
                    intakePositions.add(next.asLong());
                } else if (level.getBlockState(next).is(ModBlocks.AIR_FILTER_UNIT.get())) {
                    filterPositions.add(next.asLong());
                }
            }
        }
        return new Boundary(intakePositions, filterPositions);
    }

    private static boolean validRoom(ServerLevel level, RoomScanResult room) {
        return room != null && room.sealed() && RoomScanner.airCanPass(level, room.anchor());
    }

    private record Boundary(Set<Long> intakes, Set<Long> filters) {}

    public record Stats(int totalIntakes, int readyIntakes, int activeIntakes) {
        public static final Stats EMPTY = new Stats(0, 0, 0);
        public double readyCapacity() { return readyIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }
        public double currentInput() { return activeIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }
    }

    private IntakeNetworkScanner() {}
}
''', encoding='utf-8')

menu = root / 'src/main/java/dev/afterfall/menu/MachineMenu.java'
text = menu.read_text(encoding='utf-8')
old = 'if (inlet != null) setIntakeStats(IntakeNetworkScanner.inspect(level, inlet));'
new = 'if (inlet != null) setIntakeStats(IntakeNetworkScanner.inspectUpstream(level, inlet));'
if old not in text:
    raise SystemExit('MachineMenu fan intake stats hook not found')
text = text.replace(old, new, 1)
menu.write_text(text, encoding='utf-8')

props = root / 'gradle.properties'
p = props.read_text(encoding='utf-8')
if 'mod_version=0.7.3\n' not in p:
    raise SystemExit('Expected 0.7.3 base version not found')
p = p.replace('mod_version=0.7.3\n', 'mod_version=0.7.3.1\n', 1)
props.write_text(p, encoding='utf-8')

print('Afterfall 0.7.3.1 upstream intake diagnostics hotfix applied')
