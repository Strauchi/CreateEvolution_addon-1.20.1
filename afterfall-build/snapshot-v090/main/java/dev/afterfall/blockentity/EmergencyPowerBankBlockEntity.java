package dev.afterfall.blockentity;

import dev.afterfall.block.EmergencyPowerBankBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachineEnergyStorage;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.energy.IEnergyStorage;
import org.jetbrains.annotations.Nullable;

/**
 * Bunker reserve / UPS. Priority is intentionally physical instead of magical:
 * players wire the FRONT face to critical life-support loads and use the other
 * output faces for auxiliary loads. AUTO sheds auxiliary output below the reserve.
 */
public final class EmergencyPowerBankBlockEntity extends BlockEntity {
    public enum PowerMode {
        AUTO,
        CRITICAL,
        ALL
    }

    public static final int ENERGY_CAPACITY = 1_000_000;
    public static final int MAX_INPUT_PER_TICK = 2_000;
    public static final int MAX_CRITICAL_OUTPUT_PER_TICK = 400;
    public static final int MAX_AUX_OUTPUT_PER_TICK = 200;
    public static final int RESERVE_PERCENT = 30;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(
            ENERGY_CAPACITY, MAX_INPUT_PER_TICK, MAX_CRITICAL_OUTPUT_PER_TICK, this::setChanged);

    private boolean enabled = true;
    private PowerMode mode = PowerMode.AUTO;

    private long counterTick = Long.MIN_VALUE;
    private int inputThisTick;
    private int criticalThisTick;
    private int auxiliaryThisTick;
    private int lastInputPerTick;
    private int lastCriticalPerTick;
    private int lastAuxiliaryPerTick;

    private final IEnergyStorage inputPort = new IEnergyStorage() {
        @Override public int receiveEnergy(int maxReceive, boolean simulate) {
            return receiveTracked(maxReceive, simulate);
        }
        @Override public int extractEnergy(int maxExtract, boolean simulate) { return 0; }
        @Override public int getEnergyStored() { return energy.getEnergyStored(); }
        @Override public int getMaxEnergyStored() { return energy.getMaxEnergyStored(); }
        @Override public boolean canExtract() { return false; }
        @Override public boolean canReceive() { return energy.getEnergyStored() < energy.getMaxEnergyStored(); }
    };

    private final IEnergyStorage criticalPort = new IEnergyStorage() {
        @Override public int receiveEnergy(int maxReceive, boolean simulate) { return 0; }
        @Override public int extractEnergy(int maxExtract, boolean simulate) {
            return extractTracked(maxExtract, simulate, true);
        }
        @Override public int getEnergyStored() { return energy.getEnergyStored(); }
        @Override public int getMaxEnergyStored() { return energy.getMaxEnergyStored(); }
        @Override public boolean canExtract() { return enabled && energy.getEnergyStored() > 0; }
        @Override public boolean canReceive() { return false; }
    };

    private final IEnergyStorage auxiliaryPort = new IEnergyStorage() {
        @Override public int receiveEnergy(int maxReceive, boolean simulate) { return 0; }
        @Override public int extractEnergy(int maxExtract, boolean simulate) {
            return extractTracked(maxExtract, simulate, false);
        }
        @Override public int getEnergyStored() { return energy.getEnergyStored(); }
        @Override public int getMaxEnergyStored() { return energy.getMaxEnergyStored(); }
        @Override public boolean canExtract() { return auxiliaryAllowed() && energy.getEnergyStored() > 0; }
        @Override public boolean canReceive() { return false; }
    };

    public EmergencyPowerBankBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.EMERGENCY_POWER_BANK.get(), pos, state);
    }

    public MachineEnergyStorage internalEnergy() { return energy; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) {
        if (this.enabled != enabled) {
            this.enabled = enabled;
            setChanged();
        }
    }

    public PowerMode mode() { return mode; }
    public void setMode(PowerMode mode) {
        if (mode != null && this.mode != mode) {
            this.mode = mode;
            setChanged();
        }
    }

    public int reserveFloorEnergy() {
        return ENERGY_CAPACITY * RESERVE_PERCENT / 100;
    }

    public boolean auxiliaryAllowed() {
        if (!enabled) return false;
        return switch (mode) {
            case ALL -> true;
            case CRITICAL -> false;
            case AUTO -> energy.getEnergyStored() > reserveFloorEnergy();
        };
    }

    public boolean reserveActive() {
        return mode == PowerMode.AUTO && !auxiliaryAllowed() && energy.getEnergyStored() > 0;
    }

    /** Capability port mapping. Null-sided access is charging-only for safe automation. */
    public IEnergyStorage energyStorage(@Nullable Direction side) {
        if (side == null) return inputPort;
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.EMERGENCY_POWER_BANK.get()) || !state.hasProperty(EmergencyPowerBankBlock.FACING)) {
            return inputPort;
        }
        Direction facing = state.getValue(EmergencyPowerBankBlock.FACING);
        if (side == facing.getOpposite()) return inputPort;
        if (side == facing) return criticalPort;
        return auxiliaryPort;
    }

    private void syncCounters() {
        if (!(level instanceof ServerLevel serverLevel)) return;
        long now = serverLevel.getGameTime();
        if (counterTick == Long.MIN_VALUE) {
            counterTick = now;
            return;
        }
        if (counterTick == now) return;
        if (counterTick == now - 1L) {
            lastInputPerTick = inputThisTick;
            lastCriticalPerTick = criticalThisTick;
            lastAuxiliaryPerTick = auxiliaryThisTick;
        } else {
            lastInputPerTick = 0;
            lastCriticalPerTick = 0;
            lastAuxiliaryPerTick = 0;
        }
        inputThisTick = 0;
        criticalThisTick = 0;
        auxiliaryThisTick = 0;
        counterTick = now;
    }

    private int receiveTracked(int maxReceive, boolean simulate) {
        syncCounters();
        int remaining = Math.max(0, MAX_INPUT_PER_TICK - inputThisTick);
        if (maxReceive <= 0 || remaining <= 0) return 0;
        int received = energy.receiveEnergy(Math.min(maxReceive, remaining), simulate);
        if (!simulate && received > 0) inputThisTick += received;
        return received;
    }

    private int extractTracked(int maxExtract, boolean simulate, boolean critical) {
        syncCounters();
        if (!enabled || maxExtract <= 0) return 0;
        if (!critical && !auxiliaryAllowed()) return 0;
        int used = critical ? criticalThisTick : auxiliaryThisTick;
        int cap = critical ? MAX_CRITICAL_OUTPUT_PER_TICK : MAX_AUX_OUTPUT_PER_TICK;
        int remaining = Math.max(0, cap - used);
        if (remaining <= 0) return 0;
        int extracted = energy.extractEnergy(Math.min(maxExtract, remaining), simulate);
        if (!simulate && extracted > 0) {
            if (critical) criticalThisTick += extracted;
            else auxiliaryThisTick += extracted;
        }
        return extracted;
    }

    public int recentInputPerTick() {
        syncCounters();
        return inputThisTick > 0 ? inputThisTick : lastInputPerTick;
    }

    public int recentCriticalOutputPerTick() {
        syncCounters();
        return criticalThisTick > 0 ? criticalThisTick : lastCriticalPerTick;
    }

    public int recentAuxiliaryOutputPerTick() {
        syncCounters();
        return auxiliaryThisTick > 0 ? auxiliaryThisTick : lastAuxiliaryPerTick;
    }

    /** Estimated seconds at current observed output load; -1 means no measurable load. */
    public int estimatedRuntimeSeconds() {
        int outputPerTick = recentCriticalOutputPerTick() + recentAuxiliaryOutputPerTick();
        if (outputPerTick <= 0) return -1;
        return (int) Math.min(Integer.MAX_VALUE,
                Math.ceil(energy.getEnergyStored() / (outputPerTick * 20.0D)));
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
        int savedMode = tag.getInt("Mode");
        PowerMode[] modes = PowerMode.values();
        mode = savedMode >= 0 && savedMode < modes.length ? modes[savedMode] : PowerMode.AUTO;
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        tag.putBoolean("Enabled", enabled);
        tag.putInt("Mode", mode.ordinal());
    }
}
