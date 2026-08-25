from pathlib import Path

root = Path('Afterfall')
src = root / 'src/main/java/dev/afterfall'


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'Pattern not found in {path}: {old[:160]!r}')
    path.write_text(text.replace(old, new, 1))

# -----------------------------------------------------------------------------
# Biological Air Manager
# -----------------------------------------------------------------------------
biological = src / 'room/BiologicalAirManager.java'
biological.write_text(r'''package dev.afterfall.room;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.tags.BlockTags;
import net.minecraft.util.Mth;
import net.minecraft.world.level.LightLayer;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.BushBlock;
import net.minecraft.world.level.block.CropBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.IntegerProperty;
import net.minecraft.world.level.block.state.properties.Property;

import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;
import java.util.WeakHashMap;

/**
 * Room-local biological life support.
 *
 * Plant geometry is cached per sealed room. Light and growth state are evaluated
 * every biological tick, so switching lamps or maturing ordinary crops does not
 * require a full room rescan. Geometry is refreshed after nearby block changes and
 * periodically as a safety net for tree growth / worldgen-style block replacement.
 */
public final class BiologicalAirManager {
    public static final long CACHE_REFRESH_TICKS = 600L; // 30 s safety rescan
    public static final double PLAYER_EQUIVALENT_CAPACITY = 55.0D;

    private static final Map<ServerLevel, Map<Long, CachedRoom>> CACHE = new WeakHashMap<>();

    public static void tick(MinecraftServer server) {
        for (ServerLevel level : server.getAllLevels()) {
            if (level.getGameTime() % 20L != 0L) continue;
            tickLevel(level);
        }
    }

    private static void tickLevel(ServerLevel level) {
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
        long gameTime = level.getGameTime();
        boolean changed = false;

        for (long roomId : saved.roomIds()) {
            BlockPos anchor = BlockPos.of(roomId);
            if (!level.hasChunkAt(anchor)) continue;

            RoomAtmosphere atmosphere = saved.get(roomId);
            if (atmosphere == null) continue;

            CachedRoom cached = cachedRoom(level, roomId, atmosphere.volume(), gameTime);
            if (!cached.valid()) continue;

            Snapshot snapshot = evaluate(level, cached);
            if (snapshot.activeCapacity() <= 0.0D) continue;

            if (atmosphere.photosynthesize(snapshot.activeCapacity(), 1.0D) > 0.0D) {
                changed = true;
            }
        }

        if (changed) saved.markChanged();
    }

    /** Diagnostics for /af room info. Reuses the cache unless it is stale. */
    public static Snapshot inspect(ServerLevel level, RoomScanResult scan) {
        if (scan == null || !scan.sealed()) return Snapshot.EMPTY;
        long gameTime = level.getGameTime();
        long roomId = scan.anchor().asLong();
        Map<Long, CachedRoom> levelCache = CACHE.computeIfAbsent(level, ignored -> new HashMap<>());
        CachedRoom cached = levelCache.get(roomId);
        if (cached == null || !cached.valid() || cached.volume() != scan.volume()
                || gameTime - cached.scannedAt() >= CACHE_REFRESH_TICKS) {
            cached = rebuild(level, scan, gameTime);
            levelCache.put(roomId, cached);
        }
        return cached.valid() ? evaluate(level, cached) : Snapshot.EMPTY;
    }

    /**
     * Invalidate only cached rooms whose air-space bounds are close to a changed
     * block. The +2 margin catches walls, doors and a newly placed plant just beyond
     * the previous flood-fill bounds without globally rescanning every greenhouse.
     */
    public static void invalidateNear(ServerLevel level, BlockPos pos) {
        Map<Long, CachedRoom> levelCache = CACHE.get(level);
        if (levelCache == null || levelCache.isEmpty()) return;
        Iterator<Map.Entry<Long, CachedRoom>> iterator = levelCache.entrySet().iterator();
        while (iterator.hasNext()) {
            CachedRoom cached = iterator.next().getValue();
            if (cached.touches(pos, 2)) iterator.remove();
        }
    }

    private static CachedRoom cachedRoom(ServerLevel level, long roomId, int knownVolume, long gameTime) {
        Map<Long, CachedRoom> levelCache = CACHE.computeIfAbsent(level, ignored -> new HashMap<>());
        CachedRoom cached = levelCache.get(roomId);
        if (cached != null && cached.volume() == knownVolume
                && gameTime - cached.scannedAt() < CACHE_REFRESH_TICKS) {
            return cached;
        }

        BlockPos anchor = BlockPos.of(roomId);
        RoomScanResult scan = RoomScanner.scan(level, anchor);
        if (!scan.sealed() || scan.anchor().asLong() != roomId) {
            cached = CachedRoom.invalid(anchor, gameTime, knownVolume);
        } else {
            cached = rebuild(level, scan, gameTime);
        }
        levelCache.put(roomId, cached);
        return cached;
    }

    private static CachedRoom rebuild(ServerLevel level, RoomScanResult scan, long gameTime) {
        BlockPos anchor = scan.anchor();
        if (!scan.sealed() || !level.hasChunkAt(anchor)) {
            return CachedRoom.invalid(anchor, gameTime, scan.volume());
        }

        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> plants = new HashSet<>();
        queue.add(anchor.immutable());
        visited.add(anchor.asLong());

        int minX = anchor.getX();
        int minY = anchor.getY();
        int minZ = anchor.getZ();
        int maxX = minX;
        int maxY = minY;
        int maxZ = minZ;

        while (!queue.isEmpty() && visited.size() <= RoomScanner.MAX_ROOM_VOLUME) {
            BlockPos current = queue.removeFirst();
            minX = Math.min(minX, current.getX());
            minY = Math.min(minY, current.getY());
            minZ = Math.min(minZ, current.getZ());
            maxX = Math.max(maxX, current.getX());
            maxY = Math.max(maxY, current.getY());
            maxZ = Math.max(maxZ, current.getZ());

            BlockState currentState = level.getBlockState(current);
            if (basePlantCapacity(currentState) > 0.0D) plants.add(current.asLong());

            for (Direction direction : Direction.values()) {
                BlockPos next = current.relative(direction);
                if (!level.hasChunkAt(next)) continue;

                BlockState nextState = level.getBlockState(next);
                if (basePlantCapacity(nextState) > 0.0D) {
                    plants.add(next.asLong());
                    minX = Math.min(minX, next.getX());
                    minY = Math.min(minY, next.getY());
                    minZ = Math.min(minZ, next.getZ());
                    maxX = Math.max(maxX, next.getX());
                    maxY = Math.max(maxY, next.getY());
                    maxZ = Math.max(maxZ, next.getZ());
                }

                if (RoomScanner.airCanPass(level, next) && visited.add(next.asLong())) {
                    queue.addLast(next.immutable());
                }
            }
        }

        // The RoomScanner just confirmed this exact sealed room. If a concurrent
        // topology change made the auxiliary flood-fill diverge wildly, fail closed
        // and let the periodic/event invalidation rebuild it later.
        if (visited.size() > RoomScanner.MAX_ROOM_VOLUME) {
            return CachedRoom.invalid(anchor, gameTime, scan.volume());
        }

        return new CachedRoom(true, scan.volume(), gameTime, Set.copyOf(plants),
                minX, minY, minZ, maxX, maxY, maxZ);
    }

    private static Snapshot evaluate(ServerLevel level, CachedRoom cached) {
        int plantBlocks = 0;
        double nominal = 0.0D;
        double active = 0.0D;

        for (long packed : cached.plants()) {
            BlockPos pos = BlockPos.of(packed);
            if (!level.hasChunkAt(pos)) continue;
            BlockState state = level.getBlockState(pos);
            double base = basePlantCapacity(state);
            if (base <= 0.0D) continue;

            double growth = growthFactor(state);
            double capacity = base * growth;
            double light = lightFactor(level, pos);

            plantBlocks++;
            nominal += capacity;
            active += capacity * light;
        }

        double lightUtilization = nominal > 0.0D ? Mth.clamp(active / nominal, 0.0D, 1.0D) : 0.0D;
        double support = active / PLAYER_EQUIVALENT_CAPACITY;
        return new Snapshot(plantBlocks, nominal, active, lightUtilization, support);
    }

    /**
     * Gameplay weights in mature-crop equivalents. These are intentionally broad:
     * ordinary crops and modded BushBlock-style plants work without a special
     * hydroponics machine, while leaves make actual underground trees viable.
     */
    private static double basePlantCapacity(BlockState state) {
        Block block = state.getBlock();
        String path = BuiltInRegistries.BLOCK.getKey(block).getPath();

        // Fungi and non-photosynthetic Nether vegetation never count.
        if (path.contains("mushroom") || path.contains("fungus") || path.contains("nether")
                || path.contains("roots") || path.equals("dead_bush")) {
            return 0.0D;
        }

        if (block instanceof CropBlock) return 1.00D;

        if (state.is(BlockTags.LEAVES)) {
            // Player-placed persistent leaf cubes are deliberately much weaker than
            // natural tree foliage, preventing cheap sheared-leaf oxygen walls.
            boolean persistent = state.hasProperty(BlockStateProperties.PERSISTENT)
                    && state.getValue(BlockStateProperties.PERSISTENT);
            return persistent ? 0.045D : 0.18D;
        }

        if (state.is(BlockTags.SAPLINGS)) return 0.35D;
        if (state.is(BlockTags.FLOWERS)) return 0.45D;

        if (state.is(Blocks.SUGAR_CANE) || state.is(Blocks.CACTUS) || state.is(Blocks.BAMBOO)) return 0.60D;
        if (state.is(Blocks.VINE) || state.is(Blocks.CAVE_VINES) || state.is(Blocks.CAVE_VINES_PLANT)) return 0.35D;

        // Covers grass/ferns, berry bushes, stems, azalea-like plants and most
        // conventional modded plants while the explicit exclusions above keep
        // mushrooms/fungi out of the biological air system.
        if (block instanceof BushBlock) return 0.30D;

        return 0.0D;
    }

    /** Generic AGE property support lets crops/berry bushes/stems scale with growth. */
    private static double growthFactor(BlockState state) {
        for (Property<?> property : state.getProperties()) {
            if (!"age".equals(property.getName()) || !(property instanceof IntegerProperty ageProperty)) continue;
            int age = state.getValue(ageProperty);
            int min = Integer.MAX_VALUE;
            int max = Integer.MIN_VALUE;
            for (int value : ageProperty.getPossibleValues()) {
                min = Math.min(min, value);
                max = Math.max(max, value);
            }
            if (max <= min) return 1.0D;
            double normalized = Mth.clamp((age - min) / (double) (max - min), 0.0D, 1.0D);
            return 0.25D + 0.75D * normalized;
        }
        return 1.0D;
    }

    /** Light 0-7 = no photosynthesis; 8-15 ramps linearly to full output. */
    private static double lightFactor(ServerLevel level, BlockPos pos) {
        int blockLight = level.getBrightness(LightLayer.BLOCK, pos);
        int skyLight = level.getBrightness(LightLayer.SKY, pos);
        int light = Math.max(blockLight, skyLight);
        if (light <= 7) return 0.0D;
        return Mth.clamp((light - 7) / 8.0D, 0.0D, 1.0D);
    }

    public record Snapshot(int plantBlocks, double nominalCapacity, double activeCapacity,
                           double lightUtilization, double supportedPlayers) {
        public static final Snapshot EMPTY = new Snapshot(0, 0.0D, 0.0D, 0.0D, 0.0D);
    }

    private record CachedRoom(boolean valid, int volume, long scannedAt, Set<Long> plants,
                              int minX, int minY, int minZ, int maxX, int maxY, int maxZ) {
        static CachedRoom invalid(BlockPos anchor, long gameTime, int volume) {
            return new CachedRoom(false, volume, gameTime, Set.of(),
                    anchor.getX(), anchor.getY(), anchor.getZ(),
                    anchor.getX(), anchor.getY(), anchor.getZ());
        }

        boolean touches(BlockPos pos, int margin) {
            return pos.getX() >= minX - margin && pos.getX() <= maxX + margin
                    && pos.getY() >= minY - margin && pos.getY() <= maxY + margin
                    && pos.getZ() >= minZ - margin && pos.getZ() <= maxZ + margin;
        }
    }

    private BiologicalAirManager() {}
}
''')

# -----------------------------------------------------------------------------
# Atmosphere: stoichiometrically coupled CO2 consumption and O2 production.
# One full plant-capacity unit removes 0.002 percentage points * m3 / second.
# 55 active units exactly counter the existing one-player respiration values
# (CO2 +0.11 / volume, O2 -0.14 / volume per second).
# -----------------------------------------------------------------------------
atmosphere = src / 'room/RoomAtmosphere.java'
replace_once(atmosphere,
'''    public void simulateBreathing(int occupants, int seconds) {
        double exposure = Math.max(0, occupants) * Math.max(0, seconds)
                / Math.max(1.0D, volume);
        oxygenPercent = Math.max(0.0D, oxygenPercent - 0.14D * exposure);
        co2Percent = Math.min(20.0D, co2Percent + 0.11D * exposure);
    }

    public void tickPassive(long gameTime) {''',
'''    public void simulateBreathing(int occupants, int seconds) {
        double exposure = Math.max(0, occupants) * Math.max(0, seconds)
                / Math.max(1.0D, volume);
        oxygenPercent = Math.max(0.0D, oxygenPercent - 0.14D * exposure);
        co2Percent = Math.min(20.0D, co2Percent + 0.11D * exposure);
    }

    /**
     * Biological closed-loop treatment. CO2 is the limiting reactant: plants never
     * pull below normal atmospheric CO2 and O2 production is coupled to the amount
     * of CO2 that was actually consumed.
     *
     * @return CO2 percentage points removed from this room
     */
    public double photosynthesize(double activePlantCapacity, double seconds) {
        double capacity = Math.max(0.0D, activePlantCapacity);
        double duration = Math.max(0.0D, seconds);
        if (capacity <= 0.0D || duration <= 0.0D) return 0.0D;

        double desiredCo2Removal = 0.002D * capacity * duration / Math.max(1.0D, volume);
        double availableCo2 = Math.max(0.0D, co2Percent - NORMAL_CO2);
        double removedCo2 = Math.min(desiredCo2Removal, availableCo2);
        if (removedCo2 <= 0.0D) return 0.0D;

        co2Percent = Math.max(NORMAL_CO2, co2Percent - removedCo2);
        // Ratio mirrors the gameplay respiration model: 0.14 O2 consumed for every
        // 0.11 CO2 produced. This makes 55 active plant units one resident-equivalent.
        oxygenPercent = Math.min(NORMAL_OXYGEN, oxygenPercent + removedCo2 * (0.14D / 0.11D));
        return removedCo2;
    }

    public void tickPassive(long gameTime) {''')

# -----------------------------------------------------------------------------
# Saved room iteration for server-side biological ticks.
# -----------------------------------------------------------------------------
saved = src / 'room/RoomAtmosphereSavedData.java'
replace_once(saved,
'''import java.util.HashMap;
import java.util.Map;''',
'''import java.util.HashMap;
import java.util.Map;
import java.util.Set;''')
replace_once(saved,
'''    public RoomAtmosphere get(long roomId) { return rooms.get(roomId); }

    public void equilibrate(long firstRoomId, long secondRoomId, long gameTime) {''',
'''    public RoomAtmosphere get(long roomId) { return rooms.get(roomId); }
    public Set<Long> roomIds() { return Set.copyOf(rooms.keySet()); }

    public void equilibrate(long firstRoomId, long secondRoomId, long gameTime) {''')

# -----------------------------------------------------------------------------
# Events: biological server tick + localized cache invalidation.
# -----------------------------------------------------------------------------
events = src / 'event/CommonEvents.java'
replace_once(events,
'''import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.RoomEnvironmentManager;''',
'''import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.BiologicalAirManager;
import dev.afterfall.room.RoomEnvironmentManager;''')
replace_once(events,
'''import net.neoforged.neoforge.event.tick.PlayerTickEvent;''',
'''import net.neoforged.neoforge.event.tick.PlayerTickEvent;
import net.neoforged.neoforge.event.tick.ServerTickEvent;''')
replace_once(events,
'''    public static void onBlockBreak(BlockEvent.BreakEvent event) {
        if (event.isCanceled() || !(event.getLevel() instanceof ServerLevel serverLevel)) return;
        RoomEnvironmentManager.prepareForBarrierBreak(serverLevel, event.getPos());
        if (event.getPlayer() instanceof ServerPlayer player) RoomEnvironmentManager.invalidate(player);
    }

    public static void onPlayerTick(PlayerTickEvent.Post event) {''',
'''    public static void onBlockBreak(BlockEvent.BreakEvent event) {
        if (event.isCanceled() || !(event.getLevel() instanceof ServerLevel serverLevel)) return;
        BiologicalAirManager.invalidateNear(serverLevel, event.getPos());
        RoomEnvironmentManager.prepareForBarrierBreak(serverLevel, event.getPos());
        if (event.getPlayer() instanceof ServerPlayer player) RoomEnvironmentManager.invalidate(player);
    }

    public static void onBlockPlace(BlockEvent.EntityPlaceEvent event) {
        if (event.isCanceled() || !(event.getLevel() instanceof ServerLevel serverLevel)) return;
        BiologicalAirManager.invalidateNear(serverLevel, event.getPos());
    }

    public static void onServerTick(ServerTickEvent.Post event) {
        BiologicalAirManager.tick(event.getServer());
    }

    public static void onPlayerTick(PlayerTickEvent.Post event) {''')
replace_once(events,
'''        if (!(state.getBlock() instanceof DoorBlock)) return;
        var controllerPos = AirlockLogic.findControllerForDoor(event.getLevel(), event.getPos());''',
'''        if (!(state.getBlock() instanceof DoorBlock)) return;
        if (event.getLevel() instanceof ServerLevel serverLevel) {
            BiologicalAirManager.invalidateNear(serverLevel, event.getPos());
        }
        var controllerPos = AirlockLogic.findControllerForDoor(event.getLevel(), event.getPos());''')

# -----------------------------------------------------------------------------
# Register new listeners and version log.
# -----------------------------------------------------------------------------
main = src / 'Afterfall.java'
replace_once(main,
'''        NeoForge.EVENT_BUS.addListener(CommonEvents::onPlayerTick);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onRightClickBlock);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onBlockBreak);''',
'''        NeoForge.EVENT_BUS.addListener(CommonEvents::onServerTick);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onPlayerTick);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onRightClickBlock);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onBlockBreak);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onBlockPlace);''')
replace_once(main, 'Afterfall 0.8.1 initialized', 'Afterfall 0.8.2 initialized')

# -----------------------------------------------------------------------------
# /af room info diagnostics for greenhouse tuning.
# -----------------------------------------------------------------------------
commands = src / 'command/AfterfallCommands.java'
replace_once(commands,
'''import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;''',
'''import dev.afterfall.room.BiologicalAirManager;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;''')
replace_once(commands,
'''        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()), false);
        return 1;''',
'''        BiologicalAirManager.Snapshot bio = BiologicalAirManager.inspect(room.level, room.scan);
        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Biological: %d plant blocks | Plant capacity %.1f | Active %.1f | Light %.0f%% | Support %.2f player-eq",
                bio.plantBlocks(), bio.nominalCapacity(), bio.activeCapacity(),
                bio.lightUtilization() * 100.0D, bio.supportedPlayers())), false);
        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()), false);
        return 1;''')

# -----------------------------------------------------------------------------
# Version metadata.
# -----------------------------------------------------------------------------
props = root / 'gradle.properties'
replace_once(props, 'mod_version=0.8.1\n', 'mod_version=0.8.2\n')

print('Afterfall 0.8.2 Biological Air System patch applied')
