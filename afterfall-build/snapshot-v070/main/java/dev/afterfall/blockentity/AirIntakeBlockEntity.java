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

public final class AirIntakeBlockEntity extends BlockEntity {
    public static final double FLOW_M3_PER_SECOND = 18.0D;
    public static final double TARGET_OXYGEN = 20.75D;
    public static final double TARGET_CO2 = 0.08D;
    public static final int ENERGY_CAPACITY = 40_000;
    public static final int ENERGY_PER_SECOND = 480;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private final FilterBank filters = new FilterBank(this::setChanged);
    private boolean enabled = true;

    public AirIntakeBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.AIR_INTAKE.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public FilterBank filters() { return filters; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }

    public boolean installFilter(ServerPlayer player, ItemStack held) {
        return filters.installFromHeld(player, held);
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, AirIntakeBlockEntity blockEntity) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L) return;
        if (!blockEntity.enabled) return;

        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(serverLevel, pos);
        RoomScanResult scan = connection.room();
        if (scan == null || !connection.outsideConnected() || !blockEntity.filters.complete()) return;

        boolean wasteland = RoomEnvironmentManager.isWasteland(serverLevel, pos);
        double outsideDust = RoomEnvironmentManager.outsideDust(wasteland);
        double outsideAirborne = RoomEnvironmentManager.outsideAirborneRadiation(wasteland);

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere atmosphere = saved.getOrCreate(scan.anchor().asLong(), scan.volume(), outsideDust, outsideAirborne, serverLevel.getGameTime());

        if (!needsFreshAir(atmosphere)) return;
        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, blockEntity.energy, ENERGY_PER_SECOND)) return;

        double exchangeFraction = Math.min(0.30D, FLOW_M3_PER_SECOND / Math.max(1.0D, scan.volume()));
        atmosphere.ventilateFiltered(outsideDust, outsideAirborne, exchangeFraction,
                blockEntity.filters.dustEfficiency(), blockEntity.filters.radiationEfficiency());

        int preWear = Math.max(1, (int) Math.ceil(1.0D + outsideDust / 14.0D));
        int hepaWear = Math.max(1, (int) Math.ceil(1.0D + outsideDust / 32.0D));
        int radWear = Math.max(1, (int) Math.ceil(1.0D + outsideAirborne * 900.0D));
        blockEntity.filters.consume(preWear, hepaWear, radWear);
        saved.markChanged();
    }

    public static boolean needsFreshAir(RoomAtmosphere atmosphere) {
        return atmosphere.oxygenPercent() < TARGET_OXYGEN || atmosphere.co2Percent() > TARGET_CO2;
    }

    public static Component status(ServerLevel level, BlockPos pos) {
        if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity be))
            return Component.literal("Air Intake: OFFLINE").withStyle(ChatFormatting.RED);
        if (!be.enabled) return Component.literal("Air Intake: SWITCHED OFF").withStyle(ChatFormatting.GRAY);
        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, pos);
        if (!MachinePower.available(level, pos, be.energy, ENERGY_PER_SECOND))
            return Component.literal(String.format(Locale.ROOT, "Air Intake: OFFLINE - NO POWER | %d/%d FE",
                    be.energy.getEnergyStored(), be.energy.getMaxEnergyStored())).withStyle(ChatFormatting.RED);
        if (connection.room() == null) return Component.literal("Air Intake: ERROR - NO SEALED ROOM").withStyle(ChatFormatting.RED);
        if (!connection.outsideConnected()) return Component.literal("Air Intake: ERROR - NO OUTSIDE CONNECTION").withStyle(ChatFormatting.RED);
        if (!be.filters.complete()) return Component.literal("Air Intake: FILTER MEDIA REQUIRED | " + be.filters.compactStatus()).withStyle(ChatFormatting.RED);

        RoomScanResult scan = connection.room();
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, pos);
        RoomAtmosphere atmosphere = RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland), RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
        String mode = needsFreshAir(atmosphere) ? "VENTILATING" : "STANDBY - AIR BALANCED";
        ChatFormatting color = needsFreshAir(atmosphere) ? ChatFormatting.YELLOW : ChatFormatting.GREEN;
        return Component.literal(String.format(Locale.ROOT,
                "Air Intake: %s | %.0f m³/s | Room %d m³ | O2 %.2f%% | CO2 %.2f%% | Dust %.2f%% | Power %d/%d FE (%s) | %s",
                mode, FLOW_M3_PER_SECOND, scan.volume(), atmosphere.oxygenPercent(), atmosphere.co2Percent(), atmosphere.dustPercent(),
                be.energy.getEnergyStored(), be.energy.getMaxEnergyStored(), MachinePower.source(level, pos, be.energy), be.filters.compactStatus())).withStyle(color);
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
