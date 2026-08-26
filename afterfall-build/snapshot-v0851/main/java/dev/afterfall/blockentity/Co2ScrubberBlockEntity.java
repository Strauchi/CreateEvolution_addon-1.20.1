package dev.afterfall.blockentity;

import dev.afterfall.block.Co2ScrubberBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
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
import net.minecraft.util.Mth;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.Locale;

/**
 * Powered CO2 removal stage for the fan-driven treatment network.
 * It removes CO2 only; unlike biological treatment it does not create oxygen.
 */
public final class Co2ScrubberBlockEntity extends BlockEntity {
    public static final double FLOW_M3_PER_SECOND = 18.0D;
    public static final double PLAYER_EQUIVALENT_CAPACITY = 2.0D;
    public static final int ENERGY_CAPACITY = 120_000;
    public static final int ENERGY_PER_SECOND = 1_200;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(
            ENERGY_CAPACITY, 4_000, 0, this::setChanged);
    private boolean enabled = true;

    private double lastFlowM3PerSecond;
    private double lastActualPlayerEquivalent;
    private double lastRemovedCo2PerSecond;
    private int lastEnergyUse;
    private long lastProcessGameTime = Long.MIN_VALUE;

    public Co2ScrubberBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.CO2_SCRUBBER.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) {
        if (this.enabled != enabled) {
            this.enabled = enabled;
            setChanged();
        }
    }

    public boolean ready(ServerLevel level) {
        return enabled && MachinePower.available(level, worldPosition, energy, 1);
    }

    public RoomScanResult inspectInput(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.CO2_SCRUBBER.get()) || !state.hasProperty(Co2ScrubberBlock.FACING)) return null;
        Direction facing = state.getValue(Co2ScrubberBlock.FACING);
        return scanSide(level, worldPosition.relative(facing.getOpposite()));
    }

    public RoomScanResult inspectOutput(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.CO2_SCRUBBER.get()) || !state.hasProperty(Co2ScrubberBlock.FACING)) return null;
        Direction facing = state.getValue(Co2ScrubberBlock.FACING);
        return scanSide(level, worldPosition.relative(facing));
    }

    private static RoomScanResult scanSide(ServerLevel level, BlockPos start) {
        if (!RoomScanner.airCanPass(level, start)) return null;
        RoomScanResult scan = RoomScanner.scan(level, start);
        return scan.sealed() ? scan : null;
    }

    /** Called once per fan treatment pass. Air movement itself is handled by the network. */
    public double processScrubbing(ServerLevel level, RoomAtmosphere outputAir,
                                   RoomScanResult outputRoom, double airflowM3PerSecond) {
        lastProcessGameTime = level.getGameTime();
        lastFlowM3PerSecond = Math.max(0.0D, airflowM3PerSecond);
        lastActualPlayerEquivalent = 0.0D;
        lastRemovedCo2PerSecond = 0.0D;
        lastEnergyUse = 0;

        if (!enabled || outputAir == null || outputRoom == null || airflowM3PerSecond <= 0.0D) return 0.0D;

        double flowLoad = Mth.clamp(airflowM3PerSecond / FLOW_M3_PER_SECOND, 0.0D, 1.0D);
        double nominalSupport = PLAYER_EQUIVALENT_CAPACITY * flowLoad;
        double desiredRemoval = 0.11D * nominalSupport / Math.max(1.0D, outputRoom.volume());
        double availableCo2 = Math.max(0.0D, outputAir.co2Percent() - RoomAtmosphere.NORMAL_CO2);
        double potentialRemoval = Math.min(desiredRemoval, availableCo2);
        if (potentialRemoval <= 0.0D || desiredRemoval <= 0.0D) return 0.0D;

        double co2Load = Mth.clamp(potentialRemoval / desiredRemoval, 0.0D, 1.0D);
        int energyUse = Math.max(1, (int) Math.ceil(ENERGY_PER_SECOND * flowLoad * co2Load));
        if (!MachinePower.consumeOrRedstoneFallback(level, worldPosition, energy, energyUse)) return 0.0D;

        double requestedSupport = nominalSupport * co2Load;
        double removed = outputAir.scrubCarbonDioxide(requestedSupport, 1.0D);
        if (removed <= 0.0D) return 0.0D;

        lastRemovedCo2PerSecond = removed;
        lastActualPlayerEquivalent = removed * Math.max(1.0D, outputRoom.volume()) / 0.11D;
        lastEnergyUse = energyUse;
        RoomAtmosphereSavedData.get(level).markChanged();
        return removed;
    }

    private boolean recent(ServerLevel level) {
        return level.getGameTime() - lastProcessGameTime <= 40L;
    }

    public double recentActualPlayerEquivalent(ServerLevel level) {
        return recent(level) ? lastActualPlayerEquivalent : 0.0D;
    }

    public double recentRemovedCo2PerSecond(ServerLevel level) {
        return recent(level) ? lastRemovedCo2PerSecond : 0.0D;
    }

    public double recentFlowM3PerSecond(ServerLevel level) {
        return recent(level) ? lastFlowM3PerSecond : 0.0D;
    }

    public int recentEnergyUse(ServerLevel level) {
        return recent(level) ? lastEnergyUse : 0;
    }

    private static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        return RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
    }

    public static Component status(ServerLevel level, BlockPos pos) {
        if (!(level.getBlockEntity(pos) instanceof Co2ScrubberBlockEntity be)) {
            return Component.literal("CO2 SCRUBBER: OFFLINE").withStyle(ChatFormatting.RED);
        }
        if (!be.enabled) return Component.literal("CO2 SCRUBBER: SWITCHED OFF").withStyle(ChatFormatting.GRAY);

        RoomScanResult input = be.inspectInput(level);
        RoomScanResult output = be.inspectOutput(level);
        if (input == null) return Component.literal("CO2 SCRUBBER: ERROR - NO SEALED BACK INPUT").withStyle(ChatFormatting.RED);
        if (output == null) return Component.literal("CO2 SCRUBBER: ERROR - NO SEALED FRONT OUTPUT").withStyle(ChatFormatting.RED);
        if (input.anchor().equals(output.anchor())) {
            return Component.literal("CO2 SCRUBBER: ERROR - INPUT AND OUTPUT ARE SAME AIR VOLUME").withStyle(ChatFormatting.RED);
        }
        if (!MachinePower.available(level, pos, be.energy, 1)) {
            return Component.literal(String.format(Locale.ROOT,
                    "CO2 SCRUBBER: OFFLINE - NO POWER | %d/%d FE",
                    be.energy.getEnergyStored(), be.energy.getMaxEnergyStored())).withStyle(ChatFormatting.RED);
        }

        RoomAtmosphere inputAir = atmosphere(level, input);
        RoomAtmosphere outputAir = atmosphere(level, output);
        boolean active = be.recentActualPlayerEquivalent(level) > 0.0001D;
        String mode = active ? "ACTIVE" : (outputAir.co2Percent() <= RoomAtmosphere.NORMAL_CO2 + 0.000001D ? "STANDBY" : "READY");
        return Component.literal(String.format(Locale.ROOT,
                "CO2 SCRUBBER: %s | BACK %.3f%% -> FRONT %.3f%% CO2 | Flow %.1f/%.1f m³/s | Actual %.2f/%.2f player-eq | Power %d/%d FE | Last %d FE/s",
                mode, inputAir.co2Percent(), outputAir.co2Percent(), be.recentFlowM3PerSecond(level),
                FLOW_M3_PER_SECOND, be.recentActualPlayerEquivalent(level), PLAYER_EQUIVALENT_CAPACITY,
                be.energy.getEnergyStored(), be.energy.getMaxEnergyStored(), be.recentEnergyUse(level)))
                .withStyle(active ? ChatFormatting.GREEN : ChatFormatting.YELLOW);
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        tag.putBoolean("Enabled", enabled);
    }
}
