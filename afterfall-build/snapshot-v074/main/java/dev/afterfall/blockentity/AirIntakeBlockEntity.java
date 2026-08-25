package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
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
    public static final double TARGET_OXYGEN = 20.75D;
    public static final double TARGET_CO2 = 0.08D;
    public static final int ENERGY_CAPACITY = 20_000;
    public static final int ENERGY_PER_SECOND = 120;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private boolean enabled = true;
    private long lastTargetRoom = Long.MIN_VALUE;
    private boolean lastNetworkReady = false;
    private boolean lastVentilating = false;

    public AirIntakeBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.AIR_INTAKE.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }
    public boolean networkReadyFor(long roomAnchor) { return lastTargetRoom == roomAnchor && lastNetworkReady; }
    public boolean ventilatingRoom(long roomAnchor) { return lastTargetRoom == roomAnchor && lastVentilating; }

    public static void serverTick(Level level, BlockPos pos, BlockState state, AirIntakeBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L) return;

        be.lastTargetRoom = Long.MIN_VALUE;
        be.lastNetworkReady = false;
        be.lastVentilating = false;
        if (!be.enabled) return;

        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(serverLevel, pos);
        RoomScanResult scan = connection.room();
        if (scan == null) return;
        be.lastTargetRoom = scan.anchor().asLong();
        if (!connection.outsideConnected()) return;
        be.lastNetworkReady = MachinePower.available(serverLevel, pos, be.energy, ENERGY_PER_SECOND);
        if (!be.lastNetworkReady) return;

        boolean wasteland = RoomEnvironmentManager.isWasteland(serverLevel, pos);
        double outsideDust = RoomEnvironmentManager.outsideDust(wasteland);
        double outsideAirborne = RoomEnvironmentManager.outsideAirborneRadiation(wasteland);
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere atmosphere = saved.getOrCreate(scan.anchor().asLong(), scan.volume(), outsideDust, outsideAirborne, serverLevel.getGameTime());

        if (!needsFreshAir(atmosphere)) return;
        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, be.energy, ENERGY_PER_SECOND)) {
            be.lastNetworkReady = false;
            return;
        }
        be.lastVentilating = true;

        double exchangeFraction = Math.min(0.30D, FLOW_M3_PER_SECOND / Math.max(1.0D, scan.volume()));
        atmosphere.ventilateFiltered(outsideDust, outsideAirborne, exchangeFraction,
                PERMANENT_DUST_EFFICIENCY, PERMANENT_RADIATION_EFFICIENCY);
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
        if (connection.room() == null) return Component.literal("Air Intake: ERROR - NO SEALED MIXING ROOM").withStyle(ChatFormatting.RED);
        if (!connection.outsideConnected()) return Component.literal("Air Intake: ERROR - NO OUTSIDE CONNECTION").withStyle(ChatFormatting.RED);

        RoomScanResult scan = connection.room();
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, pos);
        RoomAtmosphere atmosphere = RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland), RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
        boolean active = needsFreshAir(atmosphere);
        return Component.literal(String.format(Locale.ROOT,
                "Air Intake: %s | %.0f m³/s | Permanent pre-clean Dust %.0f%% / Rad %.0f%% | Mixing %dm³ | O2 %.2f%% | CO2 %.2f%%",
                active ? "VENTILATING" : "STANDBY - AIR BALANCED", FLOW_M3_PER_SECOND,
                PERMANENT_DUST_EFFICIENCY * 100.0D, PERMANENT_RADIATION_EFFICIENCY * 100.0D,
                scan.volume(), atmosphere.oxygenPercent(), atmosphere.co2Percent()))
                .withStyle(active ? ChatFormatting.YELLOW : ChatFormatting.GREEN);
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
