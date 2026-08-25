package dev.afterfall.blockentity;

import dev.afterfall.block.AirFilterBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.FilterBank;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.RoomScanner;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
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

/**
 * Compact high-efficiency filtration unit.
 * BACK = dirty/mixing room. FRONT = clean room.
 * Cartridge wear remains the balancing mechanic for this compact early-game solution.
 */
public final class AirFilterBlockEntity extends BlockEntity {
    public static final double FLOW_M3_PER_SECOND = 24.0D;
    public static final double TARGET_DUST = 0.10D;
    public static final double TARGET_AIRBORNE_MSV_H = 0.05D;
    public static final int ENERGY_CAPACITY = 50_000;
    public static final int ENERGY_PER_SECOND = 640;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private final FilterBank filters = new FilterBank(this::setChanged);
    private boolean enabled = true;

    public AirFilterBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.AIR_FILTER.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public FilterBank filters() { return filters; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }

    public boolean installFilter(ServerPlayer player, ItemStack held) {
        return filters.installFromHeld(player, held);
    }

    public RoomScanResult inspectInput(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.AIR_FILTER_UNIT.get()) || !state.hasProperty(AirFilterBlock.FACING)) return null;
        Direction facing = state.getValue(AirFilterBlock.FACING);
        return scanSide(level, worldPosition.relative(facing.getOpposite()));
    }

    public RoomScanResult inspectOutput(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.AIR_FILTER_UNIT.get()) || !state.hasProperty(AirFilterBlock.FACING)) return null;
        Direction facing = state.getValue(AirFilterBlock.FACING);
        return scanSide(level, worldPosition.relative(facing));
    }

    private static RoomScanResult scanSide(ServerLevel level, BlockPos start) {
        if (!RoomScanner.airCanPass(level, start)) return null;
        RoomScanResult scan = RoomScanner.scan(level, start);
        return scan.sealed() ? scan : null;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, AirFilterBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L || !be.enabled) return;

        RoomScanResult input = be.inspectInput(serverLevel);
        RoomScanResult output = be.inspectOutput(serverLevel);
        if (input == null || output == null || input.anchor().equals(output.anchor()) || !be.filters.complete()) return;

        RoomAtmosphere inputAir = atmosphere(serverLevel, input);
        RoomAtmosphere outputAir = atmosphere(serverLevel, output);
        if (isClean(outputAir)) return;
        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, be.energy, ENERGY_PER_SECOND)) return;

        double processedFraction = Math.min(0.35D, FLOW_M3_PER_SECOND / Math.max(1.0D, output.volume()));
        double inputDust = inputAir.dustPercent();
        double inputAirborne = inputAir.airborneRadiationPerSecond();
        outputAir.exchangeFilteredFrom(inputAir, processedFraction,
                be.filters.dustEfficiency(), be.filters.radiationEfficiency());

        int preWear = Math.max(1, (int) Math.ceil(1.0D + inputDust / 12.0D));
        int hepaWear = Math.max(1, (int) Math.ceil(1.0D + inputDust / 28.0D));
        int radWear = Math.max(1, (int) Math.ceil(1.0D + inputAirborne * 1800.0D));
        be.filters.consume(preWear, hepaWear, radWear);
        RoomAtmosphereSavedData.get(serverLevel).markChanged();
    }

    private static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        return RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
    }

    public static boolean isClean(RoomAtmosphere atmosphere) {
        return atmosphere != null
                && atmosphere.dustPercent() <= TARGET_DUST
                && atmosphere.airborneRadiationPerSecond() * 3600.0D <= TARGET_AIRBORNE_MSV_H;
    }

    public static Component status(ServerLevel level, BlockPos pos) {
        if (!(level.getBlockEntity(pos) instanceof AirFilterBlockEntity be))
            return Component.literal("Compact Filter: OFFLINE").withStyle(ChatFormatting.RED);
        if (!be.enabled) return Component.literal("Compact Filter: SWITCHED OFF").withStyle(ChatFormatting.GRAY);
        if (!MachinePower.available(level, pos, be.energy, ENERGY_PER_SECOND))
            return Component.literal(String.format(Locale.ROOT, "Compact Filter: OFFLINE - NO POWER | %d/%d FE",
                    be.energy.getEnergyStored(), be.energy.getMaxEnergyStored())).withStyle(ChatFormatting.RED);

        RoomScanResult input = be.inspectInput(level);
        RoomScanResult output = be.inspectOutput(level);
        if (input == null) return Component.literal("Compact Filter: ERROR - NO SEALED BACK INPUT").withStyle(ChatFormatting.RED);
        if (output == null) return Component.literal("Compact Filter: ERROR - NO SEALED FRONT OUTPUT").withStyle(ChatFormatting.RED);
        if (input.anchor().equals(output.anchor())) return Component.literal("Compact Filter: ERROR - INPUT AND OUTPUT ARE SAME AIR VOLUME").withStyle(ChatFormatting.RED);
        if (!be.filters.complete()) return Component.literal("Compact Filter: FILTER MEDIA REQUIRED | " + be.filters.compactStatus()).withStyle(ChatFormatting.RED);

        RoomAtmosphere inputAir = atmosphere(level, input);
        RoomAtmosphere outputAir = atmosphere(level, output);
        boolean clean = isClean(outputAir);
        return Component.literal(String.format(Locale.ROOT,
                "Compact Filter: %s | BACK %dm³ Dust %.2f%% Rad %.2f | FRONT %dm³ Dust %.2f%% Rad %.2f | %.0f m³/s | %s",
                clean ? "STANDBY" : "FILTERING", input.volume(), inputAir.dustPercent(),
                inputAir.airborneRadiationPerSecond() * 3600.0D, output.volume(), outputAir.dustPercent(),
                outputAir.airborneRadiationPerSecond() * 3600.0D, FLOW_M3_PER_SECOND, be.filters.compactStatus()))
                .withStyle(clean ? ChatFormatting.GREEN : ChatFormatting.YELLOW);
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        filters.load(tag, "Filter", registries);
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        filters.save(tag, "Filter", registries);
        tag.putBoolean("Enabled", enabled);
    }
}
