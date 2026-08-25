package dev.afterfall.room;

import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Mth;

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
        List<RoomScanResult> rooms = RoomMachineUtil.findSealedRoomsOnDoorSides(level, doorPos);
        if (rooms.size() != 2) return;

        RoomScanResult firstScan = rooms.get(0);
        RoomScanResult secondScan = rooms.get(1);
        if (firstScan.anchor().equals(secondScan.anchor())) return;

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
        long gameTime = level.getGameTime();

        boolean firstWasteland = isWasteland(level, firstScan.anchor());
        boolean secondWasteland = isWasteland(level, secondScan.anchor());
        saved.getOrCreate(firstScan.anchor().asLong(), firstScan.volume(),
                outsideDust(firstWasteland), outsideAirborneRadiation(firstWasteland), gameTime);
        saved.getOrCreate(secondScan.anchor().asLong(), secondScan.volume(),
                outsideDust(secondWasteland), outsideAirborneRadiation(secondWasteland), gameTime);
        saved.equilibrate(firstScan.anchor().asLong(), secondScan.anchor().asLong(), gameTime);
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
