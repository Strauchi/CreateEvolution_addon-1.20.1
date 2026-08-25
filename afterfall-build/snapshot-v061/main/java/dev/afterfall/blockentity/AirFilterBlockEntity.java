package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.machine.FilterBank;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomMachineUtil;
import dev.afterfall.room.RoomScanResult;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.Locale;

public final class AirFilterBlockEntity extends BlockEntity {
    public static final double FLOW_M3_PER_SECOND = 24.0D;
    public static final double TARGET_DUST = 0.10D;
    public static final double TARGET_AIRBORNE_MSV_H = 0.05D;
    public static final int ENERGY_CAPACITY = 50_000;
    public static final int ENERGY_PER_SECOND = 640;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private final FilterBank filters = new FilterBank(this::setChanged);

    public AirFilterBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.AIR_FILTER.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public FilterBank filters() { return filters; }

    public boolean installFilter(ServerPlayer player, ItemStack held) {
        return filters.installFromHeld(player, held);
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, AirFilterBlockEntity blockEntity) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L) return;

        RoomScanResult scan = RoomMachineUtil.findSealedAdjacentRoom(serverLevel, pos);
        if (scan == null || !blockEntity.filters.complete()) return;

        boolean wasteland = RoomEnvironmentManager.isWasteland(serverLevel, scan.anchor());
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere atmosphere = saved.getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), serverLevel.getGameTime());

        if (isClean(atmosphere)) return;
        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, blockEntity.energy, ENERGY_PER_SECOND)) return;

        double processedFraction = Math.min(0.35D, FLOW_M3_PER_SECOND / Math.max(1.0D, scan.volume()));
        atmosphere.filterAir(processedFraction, blockEntity.filters.dustEfficiency(), blockEntity.filters.radiationEfficiency());

        int preWear = Math.max(1, (int) Math.ceil(1.0D + atmosphere.dustPercent() / 12.0D));
        int hepaWear = Math.max(1, (int) Math.ceil(1.0D + atmosphere.dustPercent() / 28.0D));
        int radWear = Math.max(1, (int) Math.ceil(1.0D + atmosphere.airborneRadiationPerSecond() * 1800.0D));
        blockEntity.filters.consume(preWear, hepaWear, radWear);
        saved.markChanged();
    }

    public static boolean isClean(RoomAtmosphere atmosphere) {
        return atmosphere.dustPercent() <= TARGET_DUST
                && atmosphere.airborneRadiationPerSecond() * 3600.0D <= TARGET_AIRBORNE_MSV_H;
    }

    public static Component status(ServerLevel level, BlockPos pos) {
        if (!(level.getBlockEntity(pos) instanceof AirFilterBlockEntity be)) {
            return Component.literal("Air Filter: OFFLINE").withStyle(ChatFormatting.RED);
        }
        RoomScanResult scan = RoomMachineUtil.findSealedAdjacentRoom(level, pos);
        boolean power = MachinePower.available(level, pos, be.energy, ENERGY_PER_SECOND);
        if (!power) return Component.literal(String.format(Locale.ROOT,
                "Air Filter: OFFLINE - NO POWER | %d/%d FE", be.energy.getEnergyStored(), be.energy.getMaxEnergyStored())).withStyle(ChatFormatting.RED);
        if (scan == null) return Component.literal("Air Filter: ERROR - NO SEALED ROOM").withStyle(ChatFormatting.RED);
        if (!be.filters.complete()) return Component.literal("Air Filter: FILTER MEDIA REQUIRED | " + be.filters.compactStatus()).withStyle(ChatFormatting.RED);

        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        RoomAtmosphere atmosphere = RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland), RoomEnvironmentManager.outsideAirborneRadiation(wasteland),
                level.getGameTime());
        String mode = isClean(atmosphere) ? "STANDBY - AIR CLEAN" : "FILTERING";
        ChatFormatting color = isClean(atmosphere) ? ChatFormatting.GREEN : ChatFormatting.YELLOW;
        return Component.literal(String.format(Locale.ROOT,
                "Air Filter: %s | %.0f m³/s | Room %d m³ | Dust %.2f%% | Air Rad %.2f mSv/h | Power %d/%d FE (%s) | %s",
                mode, FLOW_M3_PER_SECOND, scan.volume(), atmosphere.dustPercent(),
                atmosphere.airborneRadiationPerSecond() * 3600.0D,
                be.energy.getEnergyStored(), be.energy.getMaxEnergyStored(), MachinePower.source(level, pos, be.energy),
                be.filters.compactStatus())).withStyle(color);
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        filters.load(tag, "Filter");
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        filters.save(tag, "Filter");
    }
}
