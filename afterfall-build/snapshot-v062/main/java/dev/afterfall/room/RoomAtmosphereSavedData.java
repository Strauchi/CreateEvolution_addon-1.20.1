package dev.afterfall.room;

import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.Tag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.saveddata.SavedData;

import java.util.HashMap;
import java.util.Map;

public final class RoomAtmosphereSavedData extends SavedData {
    private static final String DATA_NAME = "afterfall_room_atmospheres";
    private final Map<Long, RoomAtmosphere> rooms = new HashMap<>();

    public static RoomAtmosphereSavedData get(ServerLevel level) {
        return level.getDataStorage().computeIfAbsent(
                new SavedData.Factory<>(RoomAtmosphereSavedData::new, RoomAtmosphereSavedData::load), DATA_NAME);
    }

    public RoomAtmosphere getOrCreate(long roomId, int volume, double outsideDust, double outsideAirborneRadiation, long gameTime) {
        RoomAtmosphere atmosphere = rooms.get(roomId);
        if (atmosphere == null) {
            atmosphere = new RoomAtmosphere(volume, outsideDust, outsideAirborneRadiation, gameTime);
            rooms.put(roomId, atmosphere);
            setDirty();
        } else {
            atmosphere.tickPassive(gameTime);
            atmosphere.updateVolume(volume, outsideDust, outsideAirborneRadiation);
            setDirty();
        }
        return atmosphere;
    }

    public RoomAtmosphere get(long roomId) { return rooms.get(roomId); }

    public void equilibrate(long firstRoomId, long secondRoomId, long gameTime) {
        if (firstRoomId == secondRoomId) return;
        RoomAtmosphere first = rooms.get(firstRoomId);
        RoomAtmosphere second = rooms.get(secondRoomId);
        if (first == null || second == null) return;
        first.equilibrateWith(second, gameTime);
        setDirty();
    }

    public void markChanged() { setDirty(); }

    public static RoomAtmosphereSavedData load(CompoundTag tag, HolderLookup.Provider lookupProvider) {
        RoomAtmosphereSavedData data = new RoomAtmosphereSavedData();
        ListTag list = tag.getList("Rooms", Tag.TAG_COMPOUND);
        for (int i = 0; i < list.size(); i++) {
            CompoundTag roomTag = list.getCompound(i);
            long id = roomTag.getLong("Id");
            int volume = roomTag.getInt("Volume");
            double dust = roomTag.getDouble("Dust");
            double airborne = roomTag.getDouble("AirborneRadiation");
            double oxygen = roomTag.contains("Oxygen") ? roomTag.getDouble("Oxygen") : RoomAtmosphere.NORMAL_OXYGEN;
            double co2 = roomTag.contains("CO2") ? roomTag.getDouble("CO2") : RoomAtmosphere.NORMAL_CO2;
            long lastUpdate = roomTag.getLong("LastUpdate");
            data.rooms.put(id, new RoomAtmosphere(volume, dust, airborne, oxygen, co2, lastUpdate));
        }
        return data;
    }

    @Override
    public CompoundTag save(CompoundTag tag, HolderLookup.Provider registries) {
        ListTag list = new ListTag();
        for (Map.Entry<Long, RoomAtmosphere> entry : rooms.entrySet()) {
            RoomAtmosphere atmosphere = entry.getValue();
            CompoundTag roomTag = new CompoundTag();
            roomTag.putLong("Id", entry.getKey());
            roomTag.putInt("Volume", atmosphere.volume());
            roomTag.putDouble("Dust", atmosphere.dustPercent());
            roomTag.putDouble("AirborneRadiation", atmosphere.airborneRadiationPerSecond());
            roomTag.putDouble("Oxygen", atmosphere.oxygenPercent());
            roomTag.putDouble("CO2", atmosphere.co2Percent());
            roomTag.putLong("LastUpdate", atmosphere.lastUpdateGameTime());
            list.add(roomTag);
        }
        tag.put("Rooms", list);
        return tag;
    }
}
