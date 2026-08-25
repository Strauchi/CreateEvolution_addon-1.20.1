package dev.afterfall.room;

import dev.afterfall.block.HeavyBlastDoorPartBlock;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.FenceGateBlock;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;

import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Set;

/**
 * Flood-fills connected air space around a player. A room is sealed only when
 * every reachable air cell is bounded by an air-tight block before the scan limit
 * or scan radius is reached.
 *
 * This deliberately treats stairs/slabs/fences/panes as leaky. Full blocks,
 * closed doors, closed trapdoors and closed fence gates seal air.
 */
public final class RoomScanner {
    public static final int MAX_ROOM_VOLUME = 8192;
    private static final int MAX_HORIZONTAL_DISTANCE = 32;
    private static final int MAX_VERTICAL_DISTANCE = 20;
    private static final int WALL_THICKNESS_SCAN = 4;

    public static RoomScanResult scan(ServerLevel level, BlockPos start) {
        BlockPos origin = findAirCell(level, start);
        if (origin == null) {
            return RoomScanResult.open(0, start.immutable(), false);
        }

        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        queue.add(origin);
        visited.add(origin.asLong());

        BlockPos anchor = origin;
        boolean open = false;
        boolean exceeded = false;

        while (!queue.isEmpty()) {
            BlockPos current = queue.removeFirst();
            if (compare(current, anchor) < 0) anchor = current;

            if (level.canSeeSky(current)) {
                open = true;
                break;
            }

            if (visited.size() >= MAX_ROOM_VOLUME) {
                open = true;
                exceeded = true;
                break;
            }

            for (Direction direction : Direction.values()) {
                BlockPos next = current.relative(direction);
                if (outsideSearchBounds(origin, next)) {
                    open = true;
                    exceeded = true;
                    break;
                }
                if (!level.hasChunkAt(next)) {
                    open = true;
                    exceeded = true;
                    break;
                }
                if (!airCanPass(level, next)) continue;

                long key = next.asLong();
                if (visited.add(key)) queue.addLast(next);
            }

            if (open) break;
        }

        if (open) {
            return RoomScanResult.open(visited.size(), anchor.immutable(), exceeded);
        }

        // The room is closed. Evaluate every interior->wall face, and include up
        // to four consecutive material layers so wall thickness matters too.
        double transmissionSum = 0.0D;
        int boundaryFaces = 0;

        for (long packed : visited) {
            BlockPos interior = BlockPos.of(packed);
            for (Direction direction : Direction.values()) {
                BlockPos wall = interior.relative(direction);
                if (airCanPass(level, wall)) continue;
                boundaryFaces++;
                transmissionSum += wallTransmission(level, wall, direction);
            }
        }

        if (boundaryFaces == 0) {
            return RoomScanResult.open(visited.size(), anchor.immutable(), false);
        }

        double shieldingFactor = Mth.clamp(transmissionSum / boundaryFaces, 0.01D, 1.0D);
        return new RoomScanResult(true, visited.size(), anchor.immutable(), shieldingFactor, boundaryFaces, false);
    }

    private static BlockPos findAirCell(ServerLevel level, BlockPos start) {
        if (airCanPass(level, start)) return start.immutable();
        if (airCanPass(level, start.above())) return start.above().immutable();
        return null;
    }

    private static boolean outsideSearchBounds(BlockPos origin, BlockPos pos) {
        return Math.abs(pos.getX() - origin.getX()) > MAX_HORIZONTAL_DISTANCE
                || Math.abs(pos.getZ() - origin.getZ()) > MAX_HORIZONTAL_DISTANCE
                || Math.abs(pos.getY() - origin.getY()) > MAX_VERTICAL_DISTANCE;
    }

    public static boolean airCanPass(ServerLevel level, BlockPos pos) {
        BlockState state = level.getBlockState(pos);
        if (state.isAir()) return true;
        if (!state.getFluidState().isEmpty()) return false;

        if (state.is(ModBlocks.AIR_VENT.get()) || state.is(ModBlocks.VENTILATION_FAN.get())) return false;

        if (state.is(ModBlocks.HEAVY_BLAST_DOOR_PART.get())
                && state.getBlock() instanceof HeavyBlastDoorPartBlock part) {
            BlockPos center = part.centerLower(state, pos);
            BlockState master = level.getBlockState(center);
            return !master.is(ModBlocks.HEAVY_BLAST_DOOR.get())
                    || (master.hasProperty(BlockStateProperties.OPEN) && master.getValue(BlockStateProperties.OPEN));
        }

        if (state.getBlock() instanceof DoorBlock) {
            return state.hasProperty(BlockStateProperties.OPEN) && state.getValue(BlockStateProperties.OPEN);
        }
        if (state.getBlock() instanceof TrapDoorBlock) {
            return state.hasProperty(BlockStateProperties.OPEN) && state.getValue(BlockStateProperties.OPEN);
        }
        if (state.getBlock() instanceof FenceGateBlock) {
            return state.hasProperty(BlockStateProperties.OPEN) && state.getValue(BlockStateProperties.OPEN);
        }

        // Partial blocks have gaps and therefore do not form an airtight bunker.
        return !state.isCollisionShapeFullBlock(level, pos);
    }

    private static double wallTransmission(ServerLevel level, BlockPos firstWall, Direction outward) {
        double factor = 1.0D;
        BlockPos pos = firstWall;
        for (int i = 0; i < WALL_THICKNESS_SCAN; i++) {
            if (airCanPass(level, pos)) break;
            factor *= materialTransmission(level.getBlockState(pos));
            if (factor <= 0.01D) return 0.01D;
            pos = pos.relative(outward);
        }
        return Mth.clamp(factor, 0.01D, 1.0D);
    }

    private static double materialTransmission(BlockState state) {
        if (state.is(ModBlocks.LEAD_COMPOSITE_BLOCK.get())) return 0.05D;
        if ((state.is(ModBlocks.HEAVY_BLAST_DOOR.get()) || state.is(ModBlocks.HEAVY_BLAST_DOOR_PART.get()))) return 0.025D;
        if (state.is(ModBlocks.SEALED_AIRLOCK_DOOR.get())) return 0.07D;
        // Bunker hardware has an insulated/lead-backed casing so embedding a panel
        // or controller in a shelter wall does not create a radiation weak spot.
        if (state.is(ModBlocks.AIRLOCK_CALL_PANEL.get())) return 0.10D;
        if (state.is(ModBlocks.AIRLOCK_CONTROLLER.get())) return 0.16D;
        if (state.is(ModBlocks.AIR_FILTER_UNIT.get())) return 0.20D;
        if (state.is(ModBlocks.EMERGENCY_GENERATOR.get())) return 0.26D;
        // The intake contains an intentional air duct and therefore shields less
        // effectively than a sealed control panel.
        if (state.is(ModBlocks.AIR_INTAKE_UNIT.get())) return 0.42D;
        if (state.is(ModBlocks.VENTILATION_FAN.get())) return 0.34D;
        if (state.is(ModBlocks.AIR_VENT.get())) return 0.48D;
        if (state.is(Blocks.IRON_BLOCK)) return 0.22D;
        if (state.is(Blocks.DEEPSLATE) || state.is(Blocks.COBBLED_DEEPSLATE)) return 0.38D;
        if (state.is(Blocks.STONE) || state.is(Blocks.COBBLESTONE)) return 0.50D;
        if (state.is(Blocks.GLASS) || state.is(Blocks.TINTED_GLASS)) return 0.82D;
        if (state.is(Blocks.DIRT) || state.is(Blocks.COARSE_DIRT)) return 0.58D;
        return 0.64D;
    }

    private static int compare(BlockPos a, BlockPos b) {
        int y = Integer.compare(a.getY(), b.getY());
        if (y != 0) return y;
        int x = Integer.compare(a.getX(), b.getX());
        if (x != 0) return x;
        return Integer.compare(a.getZ(), b.getZ());
    }

    private RoomScanner() {}
}
