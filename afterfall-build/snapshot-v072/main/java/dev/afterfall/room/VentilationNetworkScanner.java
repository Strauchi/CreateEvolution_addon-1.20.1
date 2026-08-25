package dev.afterfall.room;

import dev.afterfall.block.AirVentBlock;
import dev.afterfall.block.VentilationFanBlock;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayDeque;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Treats a player-built, enclosed air tunnel as a ventilation network. The air
 * cells remain ordinary Minecraft air blocks; vents/fans are airtight boundary
 * blocks and are discovered while flood-filling the shaft volume.
 */
public final class VentilationNetworkScanner {
    public static final int MAX_SHAFT_VOLUME = 8192;

    public static Network scan(ServerLevel level, BlockPos shaftStart) {
        if (!RoomScanner.airCanPass(level, shaftStart)) return null;
        RoomScanResult shaft = RoomScanner.scan(level, shaftStart);
        if (!shaft.sealed()) return new Network(shaft, List.of(), List.of());

        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> vents = new HashSet<>();
        Set<Long> fans = new HashSet<>();
        queue.add(shaftStart.immutable());
        visited.add(shaftStart.asLong());

        while (!queue.isEmpty() && visited.size() <= MAX_SHAFT_VOLUME) {
            BlockPos current = queue.removeFirst();
            for (Direction direction : Direction.values()) {
                BlockPos next = current.relative(direction);
                if (RoomScanner.airCanPass(level, next)) {
                    if (visited.add(next.asLong())) queue.addLast(next.immutable());
                    continue;
                }

                BlockState state = level.getBlockState(next);
                if (state.is(ModBlocks.AIR_VENT.get()) && state.hasProperty(AirVentBlock.FACING)) {
                    Direction facing = state.getValue(AirVentBlock.FACING);
                    if (next.relative(facing.getOpposite()).equals(current)) vents.add(next.asLong());
                }
                if (state.is(ModBlocks.VENTILATION_FAN.get()) && state.hasProperty(VentilationFanBlock.FACING)) {
                    Direction facing = state.getValue(VentilationFanBlock.FACING);
                    // FACING is the fan outlet/front. It must point into this shaft.
                    if (next.relative(facing).equals(current)) fans.add(next.asLong());
                }
            }
        }

        List<BlockPos> ventPositions = vents.stream().map(BlockPos::of)
                .sorted(Comparator.comparingLong(BlockPos::asLong)).toList();
        List<BlockPos> fanPositions = fans.stream().map(BlockPos::of)
                .sorted(Comparator.comparingLong(BlockPos::asLong)).toList();
        return new Network(shaft, ventPositions, fanPositions);
    }

    /** Returns the sealed air volume directly behind a directional fan. */
    public static RoomScanResult inletForFan(ServerLevel level, BlockPos fanPos) {
        BlockState state = level.getBlockState(fanPos);
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        BlockPos start = fanPos.relative(facing.getOpposite());
        if (!RoomScanner.airCanPass(level, start)) return null;
        RoomScanResult scan = RoomScanner.scan(level, start);
        return scan.sealed() ? scan : null;
    }

    public static RoomScanResult roomForVent(ServerLevel level, BlockPos ventPos) {
        BlockState state = level.getBlockState(ventPos);
        if (!state.is(ModBlocks.AIR_VENT.get()) || !state.hasProperty(AirVentBlock.FACING)) return null;
        Direction facing = state.getValue(AirVentBlock.FACING);
        BlockPos start = ventPos.relative(facing);
        if (!RoomScanner.airCanPass(level, start)) return null;
        RoomScanResult scan = RoomScanner.scan(level, start);
        return scan.sealed() ? scan : null;
    }

    public static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        return RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
    }

    public record Network(RoomScanResult shaft, List<BlockPos> vents, List<BlockPos> fans) {
        public boolean valid() { return shaft != null && shaft.sealed(); }
        public int supplyVentCount(ServerLevel level) {
            int count = 0;
            for (BlockPos pos : vents) {
                BlockState state = level.getBlockState(pos);
                if (state.is(ModBlocks.AIR_VENT.get()) && !state.getValue(AirVentBlock.RETURN_MODE)) count++;
            }
            return count;
        }
        public int returnVentCount(ServerLevel level) {
            int count = 0;
            for (BlockPos pos : vents) {
                BlockState state = level.getBlockState(pos);
                if (state.is(ModBlocks.AIR_VENT.get()) && state.getValue(AirVentBlock.RETURN_MODE)) count++;
            }
            return count;
        }
    }

    private VentilationNetworkScanner() {}
}
