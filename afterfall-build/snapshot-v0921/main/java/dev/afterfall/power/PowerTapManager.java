package dev.afterfall.power;

import dev.afterfall.blockentity.SmartPowerTapBlockEntity;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Lightweight registry of loaded/recent Smart Power Taps. No volume block scans are used. */
public final class PowerTapManager {
    private static final Map<ResourceKey<Level>, Map<UUID, BlockPos>> TAPS = new HashMap<>();

    public static void register(ServerLevel level, SmartPowerTapBlockEntity tap) {
        TAPS.computeIfAbsent(level.dimension(), ignored -> new HashMap<>())
                .put(tap.tapId(), tap.getBlockPos().immutable());
    }

    public static void unregister(ServerLevel level, UUID id) {
        Map<UUID, BlockPos> map = TAPS.get(level.dimension());
        if (map != null) map.remove(id);
    }

    public static List<SmartPowerTapBlockEntity> find(ServerLevel level, BlockPos center, int radius) {
        Map<UUID, BlockPos> map = TAPS.computeIfAbsent(level.dimension(), ignored -> new HashMap<>());
        double radiusSq = (double) radius * radius;
        List<SmartPowerTapBlockEntity> result = new ArrayList<>();
        Iterator<Map.Entry<UUID, BlockPos>> iterator = map.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<UUID, BlockPos> entry = iterator.next();
            BlockPos pos = entry.getValue();
            if (!level.hasChunkAt(pos)) continue;
            BlockEntity blockEntity = level.getBlockEntity(pos);
            if (!(blockEntity instanceof SmartPowerTapBlockEntity tap) || !tap.tapId().equals(entry.getKey())) {
                iterator.remove();
                continue;
            }
            if (center.distSqr(pos) <= radiusSq) result.add(tap);
        }
        result.sort((a, b) -> {
            int priority = Integer.compare(b.priority(), a.priority());
            if (priority != 0) return priority;
            int name = a.displayName().compareToIgnoreCase(b.displayName());
            if (name != 0) return name;
            return a.getBlockPos().compareTo(b.getBlockPos());
        });
        return result;
    }

    public static SmartPowerTapBlockEntity findById(ServerLevel level, BlockPos center, int radius, UUID id) {
        for (SmartPowerTapBlockEntity tap : find(level, center, radius)) {
            if (tap.tapId().equals(id)) return tap;
        }
        return null;
    }

    private PowerTapManager() {}
}
