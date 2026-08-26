package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomMachineUtil;
import dev.afterfall.room.IntakeNetworkScanner;
import dev.afterfall.room.RoomScanResult;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.Locale;

/**
 * Permanent outside-air intake / coarse separator.
 * It is intentionally weak compared with the compact/industrial filter systems:
 * it protects downstream equipment but does not make wasteland air safe by itself.
 */
public final class AirIntakeBlockEntity extends BlockEntity {
    public static final double FLOW_M3_PER_SECOND = 18.0D;
    public static final double PERMANENT_DUST_EFFICIENCY = 0.40D;
    public static final double PERMANENT_RADIATION_EFFICIENCY = 0.18D;
    // Fresh-air demand controller. Normal occupied bunkers are intentionally
    // allowed to settle above outdoor CO2 instead of being clamped to 0.08%.
    public static final double OXYGEN_DEMAND_START = 20.75D;
    public static final double CO2_DEMAND_START = 0.10D;
    public static final double OXYGEN_DEMAND_GAIN = 3.0D; // m3/s per O2 percentage point deficit
    public static final double CO2_DEMAND_GAIN = 4.0D;    // m3/s per CO2 percentage point excess
    public static final int ENERGY_CAPACITY = 20_000;
    public static final int ENERGY_PER_SECOND = 120;
    public static final double AUTO_ISOLATION_LOAD = 2.0D;

    public enum IntakeMode {
        OPEN,
        CLOSED,
        AUTO;

        public IntakeMode next() {
            return switch (this) {
                case OPEN -> CLOSED;
                case CLOSED -> AUTO;
                case AUTO -> OPEN;
            };
        }
    }

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private boolean enabled = true;
    private IntakeMode mode = IntakeMode.AUTO;
    private long lastTargetRoom = Long.MIN_VALUE;
    private boolean lastNetworkReady = false;
    private boolean lastVentilating = false;
    private double lastFlowM3PerSecond = 0.0D;
    private double lastFalloutLoadMultiplier = 1.0D;

    public AirIntakeBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.AIR_INTAKE.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }
    public IntakeMode mode() { return mode; }
    public void setMode(IntakeMode mode) {
        if (mode != null && this.mode != mode) {
            this.mode = mode;
            setChanged();
        }
    }
    public void cycleMode() { setMode(mode.next()); }
    public boolean networkReadyFor(long roomAnchor) { return lastTargetRoom == roomAnchor && lastNetworkReady; }
    public boolean ventilatingRoom(long roomAnchor) { return lastTargetRoom == roomAnchor && lastVentilating; }
    public long targetRoomAnchor() { return lastTargetRoom; }
    public double currentFlowM3PerSecond() { return lastFlowM3PerSecond; }
    public double currentFalloutLoadMultiplier() { return lastFalloutLoadMultiplier; }

    public boolean acceptsOutsideAir(ServerLevel level, BlockPos pos) {
        if (!enabled) return false;
        return switch (mode) {
            case OPEN -> true;
            case CLOSED -> false;
            case AUTO -> RoomEnvironmentManager.falloutLoadMultiplier(level, pos) < AUTO_ISOLATION_LOAD;
        };
    }

    public boolean autoIsolated(ServerLevel level, BlockPos pos) {
        return mode == IntakeMode.AUTO
                && RoomEnvironmentManager.falloutLoadMultiplier(level, pos) >= AUTO_ISOLATION_LOAD;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, AirIntakeBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L) return;

        be.lastTargetRoom = Long.MIN_VALUE;
        be.lastNetworkReady = false;
        be.lastVentilating = false;
        be.lastFlowM3PerSecond = 0.0D;
        be.lastFalloutLoadMultiplier = RoomEnvironmentManager.falloutLoadMultiplier(serverLevel, pos);
        if (!be.acceptsOutsideAir(serverLevel, pos)) return;

        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(serverLevel, pos);
        RoomScanResult scan = connection.room();
        if (scan == null) return;
        be.lastTargetRoom = scan.anchor().asLong();
        if (!connection.outsideConnected()) return;
        be.lastNetworkReady = MachinePower.available(serverLevel, pos, be.energy, ENERGY_PER_SECOND);
        if (!be.lastNetworkReady) return;

        double outsideDust = RoomEnvironmentManager.intakeOutsideDust(serverLevel, pos);
        double outsideAirborne = RoomEnvironmentManager.intakeOutsideAirborneRadiation(serverLevel, pos);
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere atmosphere = saved.getOrCreate(scan.anchor().asLong(), scan.volume(), outsideDust, outsideAirborne, serverLevel.getGameTime());

        double totalDemand = freshAirDemandM3PerSecond(atmosphere);
        if (totalDemand <= 0.01D) return;

        // Multiple intakes on the same mixing plenum share the requested make-up
        // airflow instead of every unit blindly injecting its full 18 m3/s rating.
        int readyIntakes = Math.max(1, IntakeNetworkScanner.readyIntakeCount(serverLevel, scan));
        double requestedFlow = Math.min(FLOW_M3_PER_SECOND, totalDemand / readyIntakes);
        if (requestedFlow <= 0.01D) return;

        int energyCost = Math.max(1, (int) Math.ceil(ENERGY_PER_SECOND
                * (requestedFlow / FLOW_M3_PER_SECOND)));
        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, be.energy, energyCost)) {
            be.lastNetworkReady = false;
            return;
        }
        be.lastVentilating = true;
        be.lastFlowM3PerSecond = requestedFlow;

        double exchangeFraction = Math.min(0.30D, requestedFlow / Math.max(1.0D, scan.volume()));
        atmosphere.ventilateFiltered(outsideDust, outsideAirborne, exchangeFraction,
                PERMANENT_DUST_EFFICIENCY, PERMANENT_RADIATION_EFFICIENCY);
        saved.markChanged();
    }

    public static double freshAirDemandM3PerSecond(RoomAtmosphere atmosphere) {
        if (atmosphere == null) return 0.0D;
        double co2Demand = Math.max(0.0D,
                (atmosphere.co2Percent() - CO2_DEMAND_START) * CO2_DEMAND_GAIN);
        double oxygenDemand = Math.max(0.0D,
                (OXYGEN_DEMAND_START - atmosphere.oxygenPercent()) * OXYGEN_DEMAND_GAIN);
        return Math.max(co2Demand, oxygenDemand);
    }

    public static boolean needsFreshAir(RoomAtmosphere atmosphere) {
        return freshAirDemandM3PerSecond(atmosphere) > 0.01D;
    }

    public static Component status(ServerLevel level, BlockPos pos) {
        if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity be))
            return Component.literal("Air Intake: OFFLINE").withStyle(ChatFormatting.RED);

        RoomEnvironmentManager.FalloutCondition fallout = RoomEnvironmentManager.falloutCondition(level, pos);
        double load = fallout.loadMultiplier();
        double outsideDust = RoomEnvironmentManager.intakeOutsideDust(level, pos);
        double outsideRadHour = RoomEnvironmentManager.intakeOutsideAirborneRadiation(level, pos) * 3600.0D;
        String environmental = String.format(Locale.ROOT,
                " | Fallout %s %.0f%% | Outside Dust %.0f%% / Rad %.1f mSv/h",
                fallout.name(), load * 100.0D, outsideDust, outsideRadHour);

        if (!be.enabled) return Component.literal("Air Intake: DISABLED | Mode " + be.mode + environmental)
                .withStyle(ChatFormatting.GRAY);
        if (be.mode == IntakeMode.CLOSED) return Component.literal("Air Intake: ISOLATED | Mode CLOSED" + environmental)
                .withStyle(ChatFormatting.GRAY);
        if (be.autoIsolated(level, pos)) return Component.literal("Air Intake: AUTO ISOLATED - SEVERE FALLOUT" + environmental)
                .withStyle(ChatFormatting.RED);

        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, pos);
        if (!MachinePower.available(level, pos, be.energy, ENERGY_PER_SECOND))
            return Component.literal(String.format(Locale.ROOT, "Air Intake: OFFLINE - NO POWER | Mode %s | %d/%d FE%s",
                    be.mode, be.energy.getEnergyStored(), be.energy.getMaxEnergyStored(), environmental)).withStyle(ChatFormatting.RED);
        if (connection.room() == null) return Component.literal("Air Intake: ERROR - NO SEALED MIXING ROOM | Mode " + be.mode + environmental)
                .withStyle(ChatFormatting.RED);
        if (!connection.outsideConnected()) return Component.literal("Air Intake: ERROR - NO OUTSIDE CONNECTION | Mode " + be.mode + environmental)
                .withStyle(ChatFormatting.RED);

        RoomScanResult scan = connection.room();
        RoomAtmosphere atmosphere = RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                outsideDust, RoomEnvironmentManager.intakeOutsideAirborneRadiation(level, pos), level.getGameTime());
        double demand = freshAirDemandM3PerSecond(atmosphere);
        boolean active = be.lastVentilating;
        return Component.literal(String.format(Locale.ROOT,
                "Air Intake: %s | Mode %s | Flow %.2f/%.0f m³/s | Demand %.2f m³/s%s",
                active ? "VENTILATING" : "STANDBY", be.mode,
                be.lastFlowM3PerSecond, FLOW_M3_PER_SECOND, demand, environmental))
                .withStyle(active ? ChatFormatting.YELLOW : ChatFormatting.GREEN);
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
        if (tag.contains("Mode")) {
            try { mode = IntakeMode.valueOf(tag.getString("Mode")); }
            catch (IllegalArgumentException ignored) { mode = IntakeMode.AUTO; }
        } else {
            mode = IntakeMode.AUTO;
        }
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        tag.putBoolean("Enabled", enabled);
        tag.putString("Mode", mode.name());
    }
}
