package dev.afterfall.room;

import dev.afterfall.block.AirFilterBlock;
import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachinePower;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;

import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Aggregates outside-air intakes bordering sealed ventilation plenums. */
public final class IntakeNetworkScanner {
    private static final int MAX_UPSTREAM_FILTER_DEPTH = 8;

    /** Direct intakes attached to exactly this sealed room/plenum. */
    public static Stats inspect(ServerLevel level, RoomScanResult room) {
        if (!validRoom(level, room)) return Stats.EMPTY;
        Boundary boundary = scanBoundary(level, room);
        return statsFor(level, boundary.intakes(), Set.of(room.anchor().asLong()),
                Set.of(room.anchor().asLong()));
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

        AirTreatmentNetwork.Network treatment = AirTreatmentNetwork.trace(level, room);
        Set<Long> roomAnchors = new HashSet<>();
        Set<Long> intakeRoomAnchors = new HashSet<>();
        Set<Long> intakes = new HashSet<>();
        for (RoomScanResult treatmentRoom : treatment.rooms()) {
            long anchor = treatmentRoom.anchor().asLong();
            roomAnchors.add(anchor);
            Boundary boundary = scanBoundary(level, treatmentRoom);
            if (!boundary.intakes().isEmpty()) intakeRoomAnchors.add(anchor);
            intakes.addAll(boundary.intakes());
        }
        return statsFor(level, intakes, roomAnchors, intakeRoomAnchors);
    }

    /** Number of currently usable intakes directly feeding this mixing room. */
    public static int readyIntakeCount(ServerLevel level, RoomScanResult room) {
        if (!validRoom(level, room)) return 0;
        int ready = 0;
        for (long packed : scanBoundary(level, room).intakes()) {
            BlockPos pos = BlockPos.of(packed);
            if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity intake)
                    || !intake.acceptsOutsideAir(level, pos)) continue;
            RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, pos);
            if (connection.room() == null || !connection.room().anchor().equals(room.anchor())
                    || !connection.outsideConnected()) continue;
            if (MachinePower.available(level, pos, intake.energyStorage(), AirIntakeBlockEntity.ENERGY_PER_SECOND)) ready++;
        }
        return ready;
    }

    /**
     * Highest active fallout mass-load multiplier feeding the specified treatment
     * rooms. Closed/AUTO-isolated intakes contribute nothing because no outside air
     * is entering the recirculation loop.
     */
    public static double activeFalloutLoadMultiplier(ServerLevel level, List<RoomScanResult> rooms) {
        if (rooms == null || rooms.isEmpty()) return 1.0D;
        double max = 1.0D;
        Set<Long> inspected = new HashSet<>();
        for (RoomScanResult room : rooms) {
            if (!validRoom(level, room)) continue;
            for (long packed : scanBoundary(level, room).intakes()) {
                if (!inspected.add(packed)) continue;
                BlockPos pos = BlockPos.of(packed);
                if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity intake)) continue;
                if (intake.currentFlowM3PerSecond() <= 0.01D) continue;
                max = Math.max(max, intake.currentFalloutLoadMultiplier());
            }
        }
        return max;
    }

    private static Stats statsFor(ServerLevel level, Set<Long> intakePositions, Set<Long> roomAnchors,
                                  Set<Long> intakeRoomAnchors) {
        int ready = 0;
        int active = 0;
        double currentInput = 0.0D;
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
            if (roomAnchors.contains(intake.targetRoomAnchor())) {
                currentInput += intake.currentFlowM3PerSecond();
            }
        }

        double demand = 0.0D;
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
        for (long anchor : intakeRoomAnchors) {
            RoomAtmosphere atmosphere = saved.get(anchor);
            if (atmosphere != null) demand += AirIntakeBlockEntity.freshAirDemandM3PerSecond(atmosphere);
        }
        return new Stats(intakePositions.size(), ready, active, currentInput, demand);
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
                    var filterState = level.getBlockState(next);
                    // Only expose a compact filter as an upstream edge when this
                    // room physically touches its FRONT/output face. This is more
                    // robust than comparing independently scanned room anchors.
                    if (filterState.hasProperty(AirFilterBlock.FACING)
                            && next.relative(filterState.getValue(AirFilterBlock.FACING)).equals(current)) {
                        filterPositions.add(next.asLong());
                    }
                }
            }
        }
        return new Boundary(intakePositions, filterPositions);
    }

    private static boolean validRoom(ServerLevel level, RoomScanResult room) {
        return room != null && room.sealed() && RoomScanner.airCanPass(level, room.anchor());
    }

    private record Boundary(Set<Long> intakes, Set<Long> filters) {}

    public record Stats(int totalIntakes, int readyIntakes, int activeIntakes,
                        double currentInput, double freshAirDemand) {
        public static final Stats EMPTY = new Stats(0, 0, 0, 0.0D, 0.0D);
        public double readyCapacity() { return readyIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }
    }

    private IntakeNetworkScanner() {}
}
