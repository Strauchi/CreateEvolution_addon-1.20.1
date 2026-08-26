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
 * BYPASS is a high-flow passive path, while AUTO switches between both roles.
 */
public final class Co2ScrubberBlockEntity extends BlockEntity {
    public enum ScrubberMode {
        SCRUB,
        BYPASS,
        AUTO
    }

    /** Compatibility name used by existing diagnostics: treatment-mode capacity. */
    public static final double FLOW_M3_PER_SECOND = 18.0D;
    public static final double BYPASS_FLOW_M3_PER_SECOND = 36.0D;
    public static final double PLAYER_EQUIVALENT_CAPACITY = 2.0D;
    public static final int ENERGY_CAPACITY = 120_000;
    public static final int ENERGY_PER_SECOND = 1_200;
    public static final long AUTO_SWITCH_DELAY_TICKS = 60L;
    public static final double FRESH_AVAILABLE_THRESHOLD_M3_PER_SECOND = 0.10D;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(
            ENERGY_CAPACITY, 4_000, 0, this::setChanged);
    private boolean enabled = true;
    private ScrubberMode mode = ScrubberMode.SCRUB;

    // AUTO state is intentionally transient. Existing worlds therefore preserve
    // old scrubber behavior until the player explicitly selects AUTO.
    private boolean autoScrubbing = true;
    private boolean autoCandidateScrubbing = true;
    private long autoCandidateSince = Long.MIN_VALUE;
    private long lastFreshSignalGameTime = Long.MIN_VALUE;
    private double lastFreshInputM3PerSecond;
    private double lastFreshCapacityM3PerSecond;

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

    public ScrubberMode mode() { return mode; }
    public void setMode(ScrubberMode mode) {
        if (mode == null || this.mode == mode) return;
        this.mode = mode;
        autoCandidateScrubbing = autoScrubbing;
        autoCandidateSince = Long.MIN_VALUE;
        setChanged();
    }

    /** True when the scrubber is currently configured to remove CO2. */
    public boolean scrubbingRequested() {
        return switch (mode) {
            case SCRUB -> true;
            case BYPASS -> false;
            case AUTO -> autoScrubbing;
        };
    }

    /** Current airflow capacity exposed to the fan treatment network. */
    public double effectiveFlowCapacity() {
        return scrubbingRequested() ? FLOW_M3_PER_SECOND : BYPASS_FLOW_M3_PER_SECOND;
    }

    /**
     * Feed AUTO with real intake-network telemetry. Usable fresh-air capacity is
     * preferred over instantaneous demand flow so an OPEN/armed intake does not
     * make the scrubber chatter whenever room demand briefly reaches zero.
     */
    public void observeFreshAir(ServerLevel level, double currentFreshInput, double readyFreshCapacity) {
        lastFreshSignalGameTime = level.getGameTime();
        lastFreshInputM3PerSecond = Math.max(0.0D, currentFreshInput);
        lastFreshCapacityM3PerSecond = Math.max(0.0D, readyFreshCapacity);
        if (mode != ScrubberMode.AUTO) return;

        boolean desiredScrubbing = lastFreshCapacityM3PerSecond <= FRESH_AVAILABLE_THRESHOLD_M3_PER_SECOND;
        long now = level.getGameTime();
        if (desiredScrubbing != autoCandidateScrubbing) {
            autoCandidateScrubbing = desiredScrubbing;
            autoCandidateSince = now;
            return;
        }
        if (desiredScrubbing != autoScrubbing
                && autoCandidateSince != Long.MIN_VALUE
                && now - autoCandidateSince >= AUTO_SWITCH_DELAY_TICKS) {
            autoScrubbing = desiredScrubbing;
            setChanged();
        }
    }

    public boolean autoScrubbing() { return autoScrubbing; }

    private boolean freshSignalRecent(ServerLevel level) {
        return level.getGameTime() - lastFreshSignalGameTime <= 40L;
    }

    public double recentFreshInputM3PerSecond(ServerLevel level) {
        return freshSignalRecent(level) ? lastFreshInputM3PerSecond : 0.0D;
    }

    public double recentFreshCapacityM3PerSecond(ServerLevel level) {
        return freshSignalRecent(level) ? lastFreshCapacityM3PerSecond : 0.0D;
    }

    /** Ready means ready to perform CO2 treatment, not merely able to pass air. */
    public boolean ready(ServerLevel level) {
        return enabled && scrubbingRequested() && MachinePower.available(level, worldPosition, energy, 1);
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

        // BYPASS still records real airflow, but deliberately performs no treatment
        // and consumes no energy.
        if (!enabled || !scrubbingRequested() || outputAir == null || outputRoom == null
                || airflowM3PerSecond <= 0.0D) return 0.0D;

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

        RoomAtmosphere inputAir = atmosphere(level, input);
        RoomAtmosphere outputAir = atmosphere(level, output);
        String effective = be.scrubbingRequested() ? "SCRUB" : "BYPASS";
        boolean active = be.recentActualPlayerEquivalent(level) > 0.0001D;
        return Component.literal(String.format(Locale.ROOT,
                "CO2 SCRUBBER: %s/%s | BACK %.3f%% -> FRONT %.3f%% CO2 | Flow %.1f/%.1f m³/s | Actual %.2f/%.2f player-eq | Last %d FE/s",
                be.mode.name(), effective, inputAir.co2Percent(), outputAir.co2Percent(),
                be.recentFlowM3PerSecond(level), be.effectiveFlowCapacity(),
                be.recentActualPlayerEquivalent(level), PLAYER_EQUIVALENT_CAPACITY,
                be.recentEnergyUse(level)))
                .withStyle(active || !be.scrubbingRequested() ? ChatFormatting.GREEN : ChatFormatting.YELLOW);
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
        if (tag.contains("ScrubberMode")) {
            try {
                mode = ScrubberMode.valueOf(tag.getString("ScrubberMode"));
            } catch (IllegalArgumentException ignored) {
                mode = ScrubberMode.SCRUB;
            }
        }
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        tag.putBoolean("Enabled", enabled);
        tag.putString("ScrubberMode", mode.name());
    }
}
