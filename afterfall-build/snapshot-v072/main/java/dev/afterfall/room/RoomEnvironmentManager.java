package dev.afterfall.room;

import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Mth;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DoubleBlockHalf;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class RoomEnvironmentManager {
    private static final Map<UUID, CachedScan> CACHE = new HashMap<>();
    private static final Map<UUID, Long> LAST_SEALED_ROOM = new HashMap<>();
    public static final double WASTELAND_OUTSIDE_DUST = 92.0D;
    public static final double WASTELAND_OUTSIDE_AIRBORNE_MSV_PER_SECOND = 0.013D;

    public static RoomEnvironment sample(ServerPlayer player, boolean wasteland) {
        ServerLevel level = player.serverLevel();
        RoomScanResult scan = scanCached(player);
        double outsideDust = outsideDust(wasteland);
        double outsideAirborne = outsideAirborneRadiation(wasteland);

        if (!scan.sealed()) {
            Long previousRoom = LAST_SEALED_ROOM.remove(player.getUUID());
            if (previousRoom != null) {
                RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
                RoomAtmosphere previous = saved.get(previousRoom);
                if (previous != null) {
                    // Opening a previously sealed room causes a fast initial exchange with outside air.
                    previous.exposeToOutside(outsideDust, outsideAirborne, 0.28D);
                    saved.markChanged();
                }
            }
            return new RoomEnvironment(scan, outsideDust, outsideAirborne,
                    Mth.clamp(100.0D - outsideDust * 0.8D, 0.0D, 100.0D),
                    RoomAtmosphere.NORMAL_OXYGEN, RoomAtmosphere.NORMAL_CO2);
        }

        LAST_SEALED_ROOM.put(player.getUUID(), scan.anchor().asLong());
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
        RoomAtmosphere atmosphere = saved.getOrCreate(scan.anchor().asLong(), scan.volume(), outsideDust, outsideAirborne, level.getGameTime());
        return new RoomEnvironment(scan, atmosphere.dustPercent(), atmosphere.airborneRadiationPerSecond(),
                atmosphere.airQualityPercent(), atmosphere.oxygenPercent(), atmosphere.co2Percent());
    }

    public static void consumeBreathingAir(ServerPlayer player, RoomEnvironment environment) {
        if (!environment.sealed()) return;
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(player.serverLevel());
        RoomAtmosphere atmosphere = saved.get(environment.scan().anchor().asLong());
        if (atmosphere != null) {
            atmosphere.consumeBreathingAir();
            saved.markChanged();
        }
    }

    public static RoomScanResult scanCached(ServerPlayer player) {
        BlockPos pos = player.blockPosition();
        long second = player.serverLevel().getGameTime() / 20L;
        CachedScan cached = CACHE.get(player.getUUID());
        if (cached != null && cached.second == second && cached.position.equals(pos)) return cached.scan;
        RoomScanResult scan = RoomScanner.scan(player.serverLevel(), pos);
        CACHE.put(player.getUUID(), new CachedScan(second, pos.immutable(), scan));
        return scan;
    }

    public static void equilibrateAcrossClosedDoor(ServerLevel level, BlockPos doorPos) {
        BlockState clicked = level.getBlockState(doorPos);
        if (!(clicked.getBlock() instanceof DoorBlock)) return;

        BlockPos lower = doorPos;
        if (clicked.hasProperty(BlockStateProperties.DOUBLE_BLOCK_HALF)
                && clicked.getValue(BlockStateProperties.DOUBLE_BLOCK_HALF) == DoubleBlockHalf.UPPER) {
            lower = doorPos.below();
        }
        BlockState doorState = level.getBlockState(lower);
        if (!(doorState.getBlock() instanceof DoorBlock)
                || !doorState.hasProperty(BlockStateProperties.HORIZONTAL_FACING)) return;

        Direction facing = doorState.getValue(BlockStateProperties.HORIZONTAL_FACING);
        RoomScanResult firstScan = RoomMachineUtil.scanDoorSide(level, lower, facing);
        RoomScanResult secondScan = RoomMachineUtil.scanDoorSide(level, lower, facing.getOpposite());
        if (firstScan == null || secondScan == null) return;

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
        long gameTime = level.getGameTime();

        if (firstScan.sealed() && secondScan.sealed()) {
            if (firstScan.anchor().equals(secondScan.anchor())) return;

            boolean firstWasteland = isWasteland(level, firstScan.anchor());
            boolean secondWasteland = isWasteland(level, secondScan.anchor());
            saved.getOrCreate(firstScan.anchor().asLong(), firstScan.volume(),
                    outsideDust(firstWasteland), outsideAirborneRadiation(firstWasteland), gameTime);
            saved.getOrCreate(secondScan.anchor().asLong(), secondScan.volume(),
                    outsideDust(secondWasteland), outsideAirborneRadiation(secondWasteland), gameTime);
            saved.equilibrate(firstScan.anchor().asLong(), secondScan.anchor().asLong(), gameTime);

            // Open door cells become part of the joined air volume. Heavy blast doors
            // expose six cells (3x2); normal doors expose two.
            int connectorCells = doorState.is(ModBlocks.HEAVY_BLAST_DOOR.get()) ? 6 : 2;
            saved.prepareMergedVolume(firstScan.anchor().asLong(), secondScan.anchor().asLong(),
                    firstScan.volume() + secondScan.volume() + connectorCells);
            return;
        }

        // Opening a sealed room to an unsealed side means that the saved sealed
        // atmosphere can no longer remain pristine. Gameplay-scale equalization is
        // immediate so closing the room again starts with actual wasteland air.
        RoomScanResult sealedSide = firstScan.sealed() ? firstScan : (secondScan.sealed() ? secondScan : null);
        if (sealedSide != null) {
            boolean wasteland = isWasteland(level, doorPos);
            RoomAtmosphere atmosphere = saved.getOrCreate(sealedSide.anchor().asLong(), sealedSide.volume(),
                    outsideDust(wasteland), outsideAirborneRadiation(wasteland), gameTime);
            atmosphere.exposeToOutside(outsideDust(wasteland), outsideAirborneRadiation(wasteland), 1.0D);
            saved.markChanged();
        }
    }

    public static boolean isWasteland(ServerLevel level, BlockPos pos) {
        return level.getBiome(pos).unwrapKey().map(key -> key.location().getNamespace().equals("afterfall")
                && key.location().getPath().equals("wasteland")).orElse(false);
    }

    public static double outsideDust(boolean wasteland) { return wasteland ? WASTELAND_OUTSIDE_DUST : 4.0D; }
    public static double outsideAirborneRadiation(boolean wasteland) { return wasteland ? WASTELAND_OUTSIDE_AIRBORNE_MSV_PER_SECOND : 0.0D; }
    public static void invalidate(ServerPlayer player) { CACHE.remove(player.getUUID()); }

    private record CachedScan(long second, BlockPos position, RoomScanResult scan) {}
    private RoomEnvironmentManager() {}
}
