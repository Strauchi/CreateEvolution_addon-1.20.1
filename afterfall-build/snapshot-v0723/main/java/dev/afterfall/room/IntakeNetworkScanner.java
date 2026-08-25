package dev.afterfall.room;

import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;

import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Set;

/** Aggregates all outside-air intakes bordering one sealed mixing plenum. */
public final class IntakeNetworkScanner {
    public static Stats inspect(ServerLevel level, RoomScanResult room) {
        if (room == null || !room.sealed() || !RoomScanner.airCanPass(level, room.anchor())) return Stats.EMPTY;

        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> intakePositions = new HashSet<>();
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
                }
            }
        }

        int ready = 0;
        int active = 0;
        long anchor = room.anchor().asLong();
        for (long packed : intakePositions) {
            if (!(level.getBlockEntity(BlockPos.of(packed)) instanceof AirIntakeBlockEntity intake)) continue;
            if (intake.networkReadyFor(anchor)) ready++;
            if (intake.ventilatingRoom(anchor)) active++;
        }

        return new Stats(intakePositions.size(), ready, active);
    }

    public record Stats(int totalIntakes, int readyIntakes, int activeIntakes) {
        public static final Stats EMPTY = new Stats(0, 0, 0);
        public double readyCapacity() { return readyIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }
        public double currentInput() { return activeIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }
    }

    private IntakeNetworkScanner() {}
}
