package dev.afterfall.room;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DoubleBlockHalf;
import net.minecraft.server.level.ServerLevel;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class RoomMachineUtil {
    public static RoomScanResult findSealedAdjacentRoom(ServerLevel level, BlockPos machinePos) {
        RoomScanResult best = null;
        Set<Long> scannedStarts = new HashSet<>();
        for (Direction direction : Direction.values()) {
            BlockPos start = machinePos.relative(direction);
            if (!RoomScanner.airCanPass(level, start) || !scannedStarts.add(start.asLong())) continue;
            RoomScanResult scan = RoomScanner.scan(level, start);
            if (scan.sealed() && (best == null || scan.volume() > best.volume())) best = scan;
        }
        return best;
    }

    public static IntakeConnection findIntakeConnection(ServerLevel level, BlockPos machinePos) {
        RoomScanResult sealed = null;
        boolean hasOutside = false;
        Set<Long> seenAnchors = new HashSet<>();
        for (Direction direction : Direction.values()) {
            BlockPos start = machinePos.relative(direction);
            if (!RoomScanner.airCanPass(level, start)) continue;
            RoomScanResult scan = RoomScanner.scan(level, start);
            if (scan.sealed()) {
                if (seenAnchors.add(scan.anchor().asLong()) && (sealed == null || scan.volume() > sealed.volume())) sealed = scan;
            } else {
                hasOutside = true;
            }
        }
        return new IntakeConnection(sealed, hasOutside);
    }

    public static List<RoomScanResult> findSealedRoomsOnDoorSides(ServerLevel level, BlockPos clickedDoor) {
        BlockPos lower = lowerDoorPos(level, clickedDoor);
        if (lower == null) return List.of();

        BlockState doorState = level.getBlockState(lower);
        if (!doorState.hasProperty(BlockStateProperties.HORIZONTAL_FACING)) return List.of();
        Direction facing = doorState.getValue(BlockStateProperties.HORIZONTAL_FACING);

        List<RoomScanResult> rooms = new ArrayList<>();
        Set<Long> seenAnchors = new HashSet<>();
        for (Direction side : new Direction[]{facing, facing.getOpposite()}) {
            RoomScanResult found = scanDoorSide(level, lower, side);
            if (found != null && found.sealed() && seenAnchors.add(found.anchor().asLong())) {
                rooms.add(found);
            }
        }
        return rooms;
    }

    public static RoomScanResult scanDoorSide(ServerLevel level, BlockPos lowerDoor, Direction side) {
        BlockPos lowerStart = lowerDoor.relative(side);
        if (RoomScanner.airCanPass(level, lowerStart)) return RoomScanner.scan(level, lowerStart);

        BlockPos upperStart = lowerDoor.above().relative(side);
        if (RoomScanner.airCanPass(level, upperStart)) return RoomScanner.scan(level, upperStart);
        return null;
    }

    private static BlockPos lowerDoorPos(ServerLevel level, BlockPos pos) {
        BlockState state = level.getBlockState(pos);
        if (!(state.getBlock() instanceof DoorBlock)) return null;
        if (state.hasProperty(BlockStateProperties.DOUBLE_BLOCK_HALF)
                && state.getValue(BlockStateProperties.DOUBLE_BLOCK_HALF) == DoubleBlockHalf.UPPER) {
            return pos.below().immutable();
        }
        return pos.immutable();
    }

    public record IntakeConnection(RoomScanResult room, boolean outsideConnected) {}
    private RoomMachineUtil() {}
}
