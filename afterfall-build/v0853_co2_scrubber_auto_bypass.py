from pathlib import Path

ROOT = Path("Afterfall")


def replace_one(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old[:180]!r}")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


# Version
replace_one(ROOT / "gradle.properties", "mod_version=0.8.5.2\n", "mod_version=0.8.5.3\n")

# -----------------------------------------------------------------------------
# CO2 Scrubber: explicit SCRUB / BYPASS / AUTO modes.
# SCRUB keeps the existing 18 m3/s treatment path and removes CO2.
# BYPASS opens a 36 m3/s air path and performs no CO2 removal/no FE use.
# AUTO follows usable fresh-air capacity from the intake network. A 3 second
# debounce prevents rapid toggling when intake availability changes.
# -----------------------------------------------------------------------------
co2_be = ROOT / "src/main/java/dev/afterfall/blockentity/Co2ScrubberBlockEntity.java"
co2_be.write_text(r'''package dev.afterfall.blockentity;

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
''', encoding="utf-8")

# -----------------------------------------------------------------------------
# AirTreatmentNetwork: scrubber stage capacity is now mode-dependent. AUTO state
# is updated from the same intake telemetry used by the fan. Parallel scrubbers
# share airflow proportional to their individual active capacities.
# -----------------------------------------------------------------------------
treatment = ROOT / "src/main/java/dev/afterfall/room/AirTreatmentNetwork.java"
replace_one(
    treatment,
    """        int scrubbers = 0;
        double scrubberBottleneck = Double.POSITIVE_INFINITY;
        for (ScrubberStage stage : scrubberStages) {
            scrubbers += stage.scrubberPositions().size();
            scrubberBottleneck = Math.min(scrubberBottleneck, stage.capacity());
        }
        if (scrubberStages.isEmpty()) scrubberBottleneck = 0.0D;
""",
    """        int scrubbers = 0;
        double scrubberBottleneck = Double.POSITIVE_INFINITY;
        for (ScrubberStage stage : scrubberStages) {
            scrubbers += stage.scrubberPositions().size();
            scrubberBottleneck = Math.min(scrubberBottleneck, stage.capacity());
        }
        if (scrubberStages.isEmpty()) scrubberBottleneck = 0.0D;
"""
)
# (The aggregation code above intentionally remains structurally identical; the
# stage capacity itself becomes dynamic below.)

replace_one(
    treatment,
    """        int units = 0;
        int ready = 0;
        int active = 0;
        double actualSupport = 0.0D;
        double removalPerSecond = 0.0D;

        for (ScrubberBank bank : boundary.scrubberBanks().values()) {
            for (BlockPos scrubberPos : bank.scrubberPositions()) {
                units++;
                if (!(level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber)) continue;
                if (scrubber.ready(level)) ready++;
                double recentSupport = scrubber.recentActualPlayerEquivalent(level);
                if (recentSupport > 0.0001D) active++;
                actualSupport += recentSupport;
                removalPerSecond += scrubber.recentRemovedCo2PerSecond(level);
            }
        }

        return new ScrubberDiagnostics(units, ready, active,
                units * Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND,
                units * Co2ScrubberBlockEntity.PLAYER_EQUIVALENT_CAPACITY,
                actualSupport, removalPerSecond);
""",
    """        int units = 0;
        int ready = 0;
        int active = 0;
        double flowCapacity = 0.0D;
        double nominalSupport = 0.0D;
        double actualSupport = 0.0D;
        double removalPerSecond = 0.0D;

        for (ScrubberBank bank : boundary.scrubberBanks().values()) {
            for (BlockPos scrubberPos : bank.scrubberPositions()) {
                units++;
                if (!(level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber)) continue;
                flowCapacity += scrubber.effectiveFlowCapacity();
                if (scrubber.scrubbingRequested()) nominalSupport += Co2ScrubberBlockEntity.PLAYER_EQUIVALENT_CAPACITY;
                if (scrubber.ready(level)) ready++;
                double recentSupport = scrubber.recentActualPlayerEquivalent(level);
                if (recentSupport > 0.0001D) active++;
                actualSupport += recentSupport;
                removalPerSecond += scrubber.recentRemovedCo2PerSecond(level);
            }
        }

        return new ScrubberDiagnostics(units, ready, active,
                flowCapacity, nominalSupport, actualSupport, removalPerSecond);
"""
)

replace_one(
    treatment,
    """    /**
     * Moves atmosphere through passive treatment edges while a powered main fan is
""",
    """    /** Updates AUTO scrubbers from the intake telemetry for this exact fan path. */
    public static void updateScrubberAutoStates(ServerLevel level, Network network,
                                                 IntakeNetworkScanner.Stats intakeStats) {
        if (network == null || network.scrubberStages().isEmpty()) return;
        double currentFresh = intakeStats == null ? 0.0D : intakeStats.currentInput();
        double readyCapacity = intakeStats == null ? 0.0D : intakeStats.readyCapacity();
        Set<Long> updated = new HashSet<>();
        for (ScrubberStage stage : network.scrubberStages()) {
            for (BlockPos scrubberPos : stage.scrubberPositions()) {
                if (!updated.add(scrubberPos.asLong())) continue;
                if (level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber) {
                    scrubber.observeFreshAir(level, currentFresh, readyCapacity);
                }
            }
        }
    }

    /**
     * Moves atmosphere through passive treatment edges while a powered main fan is
"""
)

replace_one(
    treatment,
    """                double perUnitFlow = Math.min(Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND,
                        flow / Math.max(1, stage.scrubberPositions().size()));
                for (BlockPos scrubberPos : stage.scrubberPositions()) {
                    if (level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber) {
                        scrubber.processScrubbing(level, destination, stage.downstream(), perUnitFlow);
                    }
                }
""",
    """                double currentCapacity = 0.0D;
                for (BlockPos scrubberPos : stage.scrubberPositions()) {
                    if (level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber) {
                        currentCapacity += scrubber.effectiveFlowCapacity();
                    }
                }
                for (BlockPos scrubberPos : stage.scrubberPositions()) {
                    if (level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber) {
                        double share = currentCapacity <= 0.0D ? 0.0D
                                : scrubber.effectiveFlowCapacity() / currentCapacity;
                        scrubber.processScrubbing(level, destination, stage.downstream(), flow * share);
                    }
                }
"""
)

replace_one(
    treatment,
    """            ScrubberStage stage = bank.toStage(upstream, downstream, depth);
""",
    """            ScrubberStage stage = bank.toStage(level, upstream, downstream, depth);
"""
)

replace_one(
    treatment,
    """    private record ScrubberBank(RoomScanResult otherRoom, List<BlockPos> scrubberPositions) {
        private ScrubberStage toStage(RoomScanResult upstream, RoomScanResult downstream, int depth) {
            return new ScrubberStage(upstream, downstream, scrubberPositions,
                    scrubberPositions.size() * Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND, depth);
        }
    }
""",
    """    private record ScrubberBank(RoomScanResult otherRoom, List<BlockPos> scrubberPositions) {
        private ScrubberStage toStage(ServerLevel level, RoomScanResult upstream, RoomScanResult downstream, int depth) {
            double capacity = 0.0D;
            for (BlockPos scrubberPos : scrubberPositions) {
                if (level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber) {
                    capacity += scrubber.effectiveFlowCapacity();
                }
            }
            return new ScrubberStage(upstream, downstream, scrubberPositions, capacity, depth);
        }
    }
"""
)

# -----------------------------------------------------------------------------
# Main fan: collect intake stats once, feed them into AUTO scrubbers, then retrace
# so this same tick uses the new 18/36 m3/s capacity.
# -----------------------------------------------------------------------------
fan = ROOT / "src/main/java/dev/afterfall/blockentity/VentilationFanBlockEntity.java"
replace_one(
    fan,
    """            // Current make-up air entering this exact treatment path. This is used
            // only for diagnostics; the intake already performed its own exchange.
            double groupFreshInput = IntakeNetworkScanner.inspectUpstream(serverLevel, inlet).currentInput();

            // Trace all treatment plenums upstream of the fan. RETURN vents may be
            // attached to the mixing room before a compact filter or before one or
            // more passive industrial filter walls, so they are not limited to the
            // fan's immediate BACK room anymore.
            AirTreatmentNetwork.Network treatment = AirTreatmentNetwork.trace(serverLevel, inlet);
""",
    """            // Current make-up air and usable fresh-air capacity entering this exact
            // treatment path. AUTO scrubbers use usable capacity so an OPEN intake
            // remains BYPASS even when demand temporarily reaches zero.
            IntakeNetworkScanner.Stats groupIntakeStats = IntakeNetworkScanner.inspectUpstream(serverLevel, inlet);
            double groupFreshInput = groupIntakeStats.currentInput();

            // Trace once to discover scrubbers, update their AUTO state, then retrace
            // so the effective 18/36 m3/s scrubber capacity applies in this same tick.
            AirTreatmentNetwork.Network treatment = AirTreatmentNetwork.trace(serverLevel, inlet);
            AirTreatmentNetwork.updateScrubberAutoStates(serverLevel, treatment, groupIntakeStats);
            treatment = AirTreatmentNetwork.trace(serverLevel, inlet);
"""
)

# -----------------------------------------------------------------------------
# Machine menu: synchronize scrubber mode/AUTO telemetry and add explicit mode
# buttons. Existing POWER control remains independent.
# -----------------------------------------------------------------------------
menu = ROOT / "src/main/java/dev/afterfall/menu/MachineMenu.java"
replace_one(menu, "    public static final int DATA_COUNT = 50;\n", "    public static final int DATA_COUNT = 54;\n")
replace_one(
    menu,
    """    public static final int BUTTON_INTAKE_AUTO = 4;
""",
    """    public static final int BUTTON_INTAKE_AUTO = 4;
    public static final int BUTTON_SCRUBBER_SCRUB = 5;
    public static final int BUTTON_SCRUBBER_BYPASS = 6;
    public static final int BUTTON_SCRUBBER_AUTO = 7;
"""
)
replace_one(
    menu,
    """    public static final int D_SCRUBBER_NOMINAL_EQ_X100 = 49;
""",
    """    public static final int D_SCRUBBER_NOMINAL_EQ_X100 = 49;
    public static final int D_SCRUBBER_MODE = 50;
    public static final int D_SCRUBBER_AUTO_SCRUBBING = 51;
    public static final int D_SCRUBBER_FRESH_INPUT_X10 = 52;
    public static final int D_SCRUBBER_FRESH_CAPACITY_X10 = 53;
"""
)

replace_one(
    menu,
    """            data.set(D_FLOW_X10, scale(Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            data.set(D_SCRUBBER_NOMINAL_EQ_X100, scale(Co2ScrubberBlockEntity.PLAYER_EQUIVALENT_CAPACITY, 100.0D));
""",
    """            data.set(D_FLOW_X10, scale(be.effectiveFlowCapacity(), 10.0D));
            data.set(D_SCRUBBER_NOMINAL_EQ_X100, scale(Co2ScrubberBlockEntity.PLAYER_EQUIVALENT_CAPACITY, 100.0D));
            data.set(D_SCRUBBER_MODE, be.mode().ordinal());
            data.set(D_SCRUBBER_AUTO_SCRUBBING, be.autoScrubbing() ? 1 : 0);
            data.set(D_SCRUBBER_FRESH_INPUT_X10, scale(be.recentFreshInputM3PerSecond(level), 10.0D));
            data.set(D_SCRUBBER_FRESH_CAPACITY_X10, scale(be.recentFreshCapacityM3PerSecond(level), 10.0D));
"""
)

replace_one(
    menu,
    """            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), 1)) data.set(D_STATUS, 1);
            else if (input == null) data.set(D_STATUS, 34);
            else if (output == null) data.set(D_STATUS, 35);
            else if (input.anchor().equals(output.anchor())) data.set(D_STATUS, 36);
            else if (be.recentActualPlayerEquivalent(level) > 0.0001D) data.set(D_STATUS, 8);
            else if (outputAir != null && outputAir.co2Percent() <= RoomAtmosphere.NORMAL_CO2 + 0.000001D) data.set(D_STATUS, 5);
            else data.set(D_STATUS, 39);
""",
    """            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (input == null) data.set(D_STATUS, 34);
            else if (output == null) data.set(D_STATUS, 35);
            else if (input.anchor().equals(output.anchor())) data.set(D_STATUS, 36);
            else if (be.mode() == Co2ScrubberBlockEntity.ScrubberMode.BYPASS) data.set(D_STATUS, 40);
            else if (be.mode() == Co2ScrubberBlockEntity.ScrubberMode.AUTO && !be.autoScrubbing()) data.set(D_STATUS, 41);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), 1)) data.set(D_STATUS, 1);
            else if (be.recentActualPlayerEquivalent(level) > 0.0001D) data.set(D_STATUS, 8);
            else if (outputAir != null && outputAir.co2Percent() <= RoomAtmosphere.NORMAL_CO2 + 0.000001D) data.set(D_STATUS, 5);
            else data.set(D_STATUS, 39);
"""
)

replace_one(
    menu,
    """        if (id == BUTTON_ACTION && serverBlockEntity instanceof AirlockControllerBlockEntity be) {
""",
    """        if (serverBlockEntity instanceof Co2ScrubberBlockEntity be) {
            Co2ScrubberBlockEntity.ScrubberMode requested = switch (id) {
                case BUTTON_SCRUBBER_SCRUB -> Co2ScrubberBlockEntity.ScrubberMode.SCRUB;
                case BUTTON_SCRUBBER_BYPASS -> Co2ScrubberBlockEntity.ScrubberMode.BYPASS;
                case BUTTON_SCRUBBER_AUTO -> Co2ScrubberBlockEntity.ScrubberMode.AUTO;
                default -> null;
            };
            if (requested != null) {
                be.setMode(requested);
                updateServerData();
                return true;
            }
        }

        if (id == BUTTON_ACTION && serverBlockEntity instanceof AirlockControllerBlockEntity be) {
"""
)

replace_one(
    menu,
    """    public double scrubberNominalEq() { return get(D_SCRUBBER_NOMINAL_EQ_X100) / 100.0D; }
""",
    """    public double scrubberNominalEq() { return get(D_SCRUBBER_NOMINAL_EQ_X100) / 100.0D; }
    public int scrubberMode() { return get(D_SCRUBBER_MODE); }
    public boolean scrubberAutoScrubbing() { return get(D_SCRUBBER_AUTO_SCRUBBING) != 0; }
    public double scrubberFreshInput() { return get(D_SCRUBBER_FRESH_INPUT_X10) / 10.0D; }
    public double scrubberFreshCapacity() { return get(D_SCRUBBER_FRESH_CAPACITY_X10) / 10.0D; }
"""
)

# -----------------------------------------------------------------------------
# Machine screen: three direct mode buttons and compact AUTO/fresh-air telemetry.
# -----------------------------------------------------------------------------
screen = ROOT / "src/main/java/dev/afterfall/client/MachineScreen.java"
replace_one(
    screen,
    """    private Button intakeAutoButton;
""",
    """    private Button intakeAutoButton;
    private Button scrubberScrubButton;
    private Button scrubberBypassButton;
    private Button scrubberAutoButton;
"""
)

replace_one(
    screen,
    """        } else if (menu.machineType() == MachineMenu.TYPE_INTAKE) {
            intakeOpenButton = addRenderableWidget(Button.builder(Component.literal("OPEN"), b -> sendButton(MachineMenu.BUTTON_INTAKE_OPEN))
                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());
            intakeClosedButton = addRenderableWidget(Button.builder(Component.literal("CLOSED"), b -> sendButton(MachineMenu.BUTTON_INTAKE_CLOSED))
                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());
            intakeAutoButton = addRenderableWidget(Button.builder(Component.literal("AUTO"), b -> sendButton(MachineMenu.BUTTON_INTAKE_AUTO))
                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());
        }
""",
    """        } else if (menu.machineType() == MachineMenu.TYPE_INTAKE) {
            intakeOpenButton = addRenderableWidget(Button.builder(Component.literal("OPEN"), b -> sendButton(MachineMenu.BUTTON_INTAKE_OPEN))
                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());
            intakeClosedButton = addRenderableWidget(Button.builder(Component.literal("CLOSED"), b -> sendButton(MachineMenu.BUTTON_INTAKE_CLOSED))
                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());
            intakeAutoButton = addRenderableWidget(Button.builder(Component.literal("AUTO"), b -> sendButton(MachineMenu.BUTTON_INTAKE_AUTO))
                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());
        } else if (menu.machineType() == MachineMenu.TYPE_SCRUBBER) {
            scrubberScrubButton = addRenderableWidget(Button.builder(Component.literal("SCRUB"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_SCRUB))
                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());
            scrubberBypassButton = addRenderableWidget(Button.builder(Component.literal("BYPASS"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_BYPASS))
                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());
            scrubberAutoButton = addRenderableWidget(Button.builder(Component.literal("AUTO"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_AUTO))
                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());
        }
"""
)

replace_one(
    screen,
    """        if (intakeOpenButton != null) {
            intakeOpenButton.setMessage(Component.literal(menu.intakeMode() == 0 ? "[ OPEN ]" : "OPEN"));
            intakeClosedButton.setMessage(Component.literal(menu.intakeMode() == 1 ? "[ CLOSED ]" : "CLOSED"));
            intakeAutoButton.setMessage(Component.literal(menu.intakeMode() == 2 ? "[ AUTO ]" : "AUTO"));
        }
""",
    """        if (intakeOpenButton != null) {
            intakeOpenButton.setMessage(Component.literal(menu.intakeMode() == 0 ? "[ OPEN ]" : "OPEN"));
            intakeClosedButton.setMessage(Component.literal(menu.intakeMode() == 1 ? "[ CLOSED ]" : "CLOSED"));
            intakeAutoButton.setMessage(Component.literal(menu.intakeMode() == 2 ? "[ AUTO ]" : "AUTO"));
        }
        if (scrubberScrubButton != null) {
            scrubberScrubButton.setMessage(Component.literal(menu.scrubberMode() == 0 ? "[ SCRUB ]" : "SCRUB"));
            scrubberBypassButton.setMessage(Component.literal(menu.scrubberMode() == 1 ? "[ BYPASS ]" : "BYPASS"));
            scrubberAutoButton.setMessage(Component.literal(menu.scrubberMode() == 2 ? "[ AUTO ]" : "AUTO"));
        }
"""
)

old_render_scrubber = r'''    private void renderScrubber(GuiGraphics graphics) {
        int inputVolume = menu.inputRoomVolume();
        int outputVolume = menu.get(MachineMenu.D_ROOM_VOLUME);
        double inputCo2 = menu.scrubberInputCo2();
        double outputCo2 = menu.scrubberOutputCo2();
        double actualEq = menu.scrubberActualEq();
        double nominalEq = menu.scrubberNominalEq();
        double actualFlow = menu.scrubberActualFlow();
        double maxFlow = menu.flow();
        int energyUse = menu.scrubberEnergyUse();

        graphics.drawString(font, "CO2 TREATMENT // O2 IS NOT GENERATED", 12, 88, 0xFFE1B45A, false);
        graphics.drawString(font, String.format(Locale.ROOT, "BACK input: %d m³ | CO2 %.3f%%",
                inputVolume, inputCo2), 12, 106, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "FRONT output: %d m³ | CO2 %.3f%%",
                outputVolume, outputCo2), 12, 119, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Flow: %.1f / %.1f m³/s",
                actualFlow, maxFlow), 12, 137, actualFlow > 0.01D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Removal: %.5f%% CO2/min",
                menu.scrubberRemovalPerMinute()), 12, 150,
                menu.scrubberRemovalPerMinute() > 0.000001D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Support: %.2f / %.2f player-eq",
                actualEq, nominalEq), 12, 163,
                actualEq > 0.0001D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Power use: %,d / %,d FE/s",
                energyUse, 1200), 12, 176, energyUse > 0 ? 0xFF9DB7BD : 0xFF7F9298, false);
        graphics.drawString(font, "Future media bay: not required in 0.8.5.2", 12, 193, 0xFF6F7D82, false);
    }
'''
new_render_scrubber = r'''    private void renderScrubber(GuiGraphics graphics) {
        int inputVolume = menu.inputRoomVolume();
        int outputVolume = menu.get(MachineMenu.D_ROOM_VOLUME);
        double actualEq = menu.scrubberActualEq();
        double actualFlow = menu.scrubberActualFlow();
        double maxFlow = menu.flow();
        int energyUse = menu.scrubberEnergyUse();
        boolean effectiveScrub = menu.scrubberMode() == 0
                || (menu.scrubberMode() == 2 && menu.scrubberAutoScrubbing());
        String selectedMode = switch (menu.scrubberMode()) {
            case 0 -> "SCRUB";
            case 1 -> "BYPASS";
            default -> "AUTO";
        };
        String effective = effectiveScrub ? "SCRUBBING" : "BYPASS";
        int effectiveColor = effectiveScrub ? 0xFFE1B45A : 0xFF66C477;

        graphics.drawString(font, "CO2 TREATMENT // O2 IS NOT GENERATED", 12, 111, 0xFFE1B45A, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Mode %s | Effective: %s",
                selectedMode, effective), 12, 124, effectiveColor, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Fresh: %.1f m³/s | Available %.1f m³/s",
                menu.scrubberFreshInput(), menu.scrubberFreshCapacity()), 12, 137,
                menu.scrubberFreshCapacity() > 0.1D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "BACK %d m³ CO2 %.3f%% | FRONT %d m³ %.3f%%",
                inputVolume, menu.scrubberInputCo2(), outputVolume, menu.scrubberOutputCo2()),
                12, 150, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Airflow: %.1f / %.1f m³/s",
                actualFlow, maxFlow), 12, 163, actualFlow > 0.01D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, effectiveScrub
                ? String.format(Locale.ROOT, "CO2: -%.5f%%/min | Support %.2f/%.2f eq",
                    menu.scrubberRemovalPerMinute(), actualEq, menu.scrubberNominalEq())
                : "CO2 removal: OFF | High-flow bypass active",
                12, 176, effectiveScrub && actualEq > 0.0001D ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Power: %,d / %,d FE/s | %s",
                energyUse, 1200, effectiveScrub ? "treatment" : "bypass: 0 FE"),
                12, 189, energyUse > 0 ? 0xFF9DB7BD : 0xFF7F9298, false);
    }
'''
replace_one(screen, old_render_scrubber, new_render_scrubber)

replace_one(
    screen,
    """            case 39 -> "READY - WAITING FOR AIRFLOW";
            default -> "INITIALIZING";
""",
    """            case 39 -> "READY - WAITING FOR AIRFLOW";
            case 40 -> "BYPASS - MAX AIRFLOW";
            case 41 -> "AUTO BYPASS - FRESH AIR AVAILABLE";
            default -> "INITIALIZING";
"""
)
replace_one(
    screen,
    """        if (status == 5 || status == 8 || status == 9 || status == 16 || status == 32) return 0xFF66C477;
""",
    """        if (status == 5 || status == 8 || status == 9 || status == 16 || status == 32
                || status == 40 || status == 41) return 0xFF66C477;
"""
)

print("Applied Afterfall 0.8.5.3 CO2 Scrubber Auto/Bypass patch")
