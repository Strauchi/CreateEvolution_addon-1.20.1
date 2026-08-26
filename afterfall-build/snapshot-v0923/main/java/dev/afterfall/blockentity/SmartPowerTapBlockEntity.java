package dev.afterfall.blockentity;

import dev.afterfall.block.SmartPowerTapBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.power.PowerTapManager;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.energy.IEnergyStorage;
import org.jetbrains.annotations.Nullable;

import java.util.UUID;

/**
 * Smart bunker circuit tap: mini UPS, relay, metering and CRITICAL/AUX load-shedding endpoint.
 * BACK receives grid FE, FRONT feeds the protected local circuit.
 */
public final class SmartPowerTapBlockEntity extends BlockEntity {
    public enum CircuitMode { CRITICAL, AUX }
    public enum AuxState { ACTIVE, SHED, REARMING }

    public static final int ENERGY_CAPACITY = 50_000;
    public static final int MAX_TRANSFER_PER_TICK = 1_000;
    public static final int AUX_REARM_PERCENT = 25;
    public static final int CRITICAL_DEFICIT_BUFFER_PERCENT = 80;
    public static final int CRITICAL_DEFICIT_CONFIRM_TICKS = 20;

    private UUID tapId = UUID.randomUUID();
    private String displayName = "Power Tap";
    private CircuitMode circuitMode = CircuitMode.CRITICAL;
    private AuxState auxState = AuxState.ACTIVE;
    private boolean relayEnabled = true;
    private boolean coordinatorBlocked;
    private BlockPos coordinatorPos;
    private long lastCoordinatorTick = Long.MIN_VALUE;
    private boolean everPowered;
    // Reserved now so later user-facing priority tiers do not require a storage migration.
    private int priority;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(
            ENERGY_CAPACITY, MAX_TRANSFER_PER_TICK, MAX_TRANSFER_PER_TICK, this::setChanged);

    private long counterTick = Long.MIN_VALUE;
    private int inputThisTick;
    private int outputThisTick;
    private int lastInputPerTick;
    private int lastOutputPerTick;
    private int criticalDeficitTicks;

    private final IEnergyStorage inputPort = new IEnergyStorage() {
        @Override public int receiveEnergy(int maxReceive, boolean simulate) { return receiveTracked(maxReceive, simulate); }
        @Override public int extractEnergy(int maxExtract, boolean simulate) { return 0; }
        @Override public int getEnergyStored() { return energy.getEnergyStored(); }
        @Override public int getMaxEnergyStored() { return energy.getMaxEnergyStored(); }
        @Override public boolean canExtract() { return false; }
        @Override public boolean canReceive() { return inputAllowed() && energy.getEnergyStored() < ENERGY_CAPACITY; }
    };

    private final IEnergyStorage outputPort = new IEnergyStorage() {
        @Override public int receiveEnergy(int maxReceive, boolean simulate) { return 0; }
        @Override public int extractEnergy(int maxExtract, boolean simulate) { return extractTracked(maxExtract, simulate); }
        @Override public int getEnergyStored() { return outputAllowed() ? energy.getEnergyStored() : 0; }
        @Override public int getMaxEnergyStored() { return ENERGY_CAPACITY; }
        @Override public boolean canExtract() { return outputAllowed() && energy.getEnergyStored() > 0; }
        @Override public boolean canReceive() { return false; }
    };

    public SmartPowerTapBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.SMART_POWER_TAP.get(), pos, state);
    }

    public UUID tapId() { return tapId; }
    public String displayName() { return displayName; }
    public CircuitMode circuitMode() { return circuitMode; }
    public AuxState auxState() { return auxState; }
    public boolean relayEnabled() { return relayEnabled; }
    public int priority() { return priority; }
    public int energyStored() { return energy.getEnergyStored(); }
    public int maxEnergyStored() { return ENERGY_CAPACITY; }
    public int rearmFloorEnergy() { return ENERGY_CAPACITY * AUX_REARM_PERCENT / 100; }

    public void setDisplayName(String name) {
        String clean = name == null ? "" : name.trim();
        if (clean.length() > 32) clean = clean.substring(0, 32);
        if (clean.isEmpty()) clean = "Power Tap";
        if (!displayName.equals(clean)) {
            displayName = clean;
            setChanged();
        }
    }

    public void setCircuitMode(CircuitMode mode) {
        if (mode == null || circuitMode == mode) return;
        circuitMode = mode;
        criticalDeficitTicks = 0;
        if (mode == CircuitMode.AUX) {
            if (coordinatorBlocked) auxState = AuxState.SHED;
            else auxState = energy.getEnergyStored() >= rearmFloorEnergy() ? AuxState.ACTIVE : AuxState.REARMING;
        }
        setChanged();
    }

    public void setRelayEnabled(boolean enabled) {
        if (relayEnabled == enabled) return;
        relayEnabled = enabled;
        if (enabled && circuitMode == CircuitMode.AUX && auxState == AuxState.SHED && !coordinatorBlocked) {
            auxState = AuxState.REARMING;
        }
        setChanged();
    }

    public boolean outputAllowed() {
        if (!relayEnabled) return false;
        if (circuitMode == CircuitMode.CRITICAL) return true;
        return !coordinatorBlocked && auxState == AuxState.ACTIVE;
    }

    public boolean inputAllowed() {
        if (circuitMode == CircuitMode.CRITICAL) return true;
        if (coordinatorBlocked || auxState == AuxState.SHED) return false;
        return true;
    }

    /** Null-side access is input-only so automation cannot bypass the protected output relay. */
    @Nullable
    public IEnergyStorage energyStorage(@Nullable Direction side) {
        if (side == null) return inputPort;
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.SMART_POWER_TAP.get()) || !state.hasProperty(SmartPowerTapBlock.FACING)) return null;
        Direction front = state.getValue(SmartPowerTapBlock.FACING);
        if (side == front.getOpposite()) return inputPort;
        if (side == front) return outputPort;
        return null;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, SmartPowerTapBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel)) return;
        be.syncCounters();
        PowerTapManager.register(serverLevel, be);

        if (be.circuitMode == CircuitMode.AUX && be.auxState == AuxState.REARMING
                && !be.coordinatorBlocked && be.energy.getEnergyStored() >= be.rearmFloorEnergy()) {
            be.auxState = AuxState.ACTIVE;
            be.setChanged();
        }

        boolean demand = be.hasOutputDemand(serverLevel, pos, state);
        if (be.outputAllowed() && be.energy.getEnergyStored() > 0) {
            be.pushOutput(serverLevel, pos, state);
        }

        if (be.circuitMode == CircuitMode.AUX && be.relayEnabled && be.auxState == AuxState.ACTIVE
                && be.everPowered && demand && be.energy.getEnergyStored() <= 0) {
            be.auxState = AuxState.SHED;
            be.setChanged();
        }

        be.updateCriticalDeficit(demand);
    }

    private boolean hasOutputDemand(ServerLevel level, BlockPos pos, BlockState state) {
        if (!state.hasProperty(SmartPowerTapBlock.FACING)) return false;
        Direction front = state.getValue(SmartPowerTapBlock.FACING);
        IEnergyStorage target = level.getCapability(Capabilities.EnergyStorage.BLOCK,
                pos.relative(front), front.getOpposite());
        return target != null && target.canReceive() && target.receiveEnergy(1, true) > 0;
    }

    private void pushOutput(ServerLevel level, BlockPos pos, BlockState state) {
        if (!state.hasProperty(SmartPowerTapBlock.FACING)) return;
        Direction front = state.getValue(SmartPowerTapBlock.FACING);
        IEnergyStorage target = level.getCapability(Capabilities.EnergyStorage.BLOCK,
                pos.relative(front), front.getOpposite());
        if (target == null || !target.canReceive()) return;
        int remaining = Math.max(0, MAX_TRANSFER_PER_TICK - outputThisTick);
        if (remaining <= 0) return;
        int offer = Math.min(remaining, energy.getEnergyStored());
        int acceptedSimulation = target.receiveEnergy(offer, true);
        if (acceptedSimulation <= 0) return;
        int extracted = energy.extractEnergy(acceptedSimulation, false);
        if (extracted <= 0) return;
        int accepted = target.receiveEnergy(extracted, false);
        if (accepted < extracted) energy.addEnergyInternal(extracted - Math.max(0, accepted));
        if (accepted > 0) outputThisTick += accepted;
    }

    private void updateCriticalDeficit(boolean demand) {
        if (circuitMode != CircuitMode.CRITICAL || !relayEnabled || !demand) {
            criticalDeficitTicks = Math.max(0, criticalDeficitTicks - 2);
            return;
        }
        int threshold = ENERGY_CAPACITY * CRITICAL_DEFICIT_BUFFER_PERCENT / 100;
        boolean draining = recentOutputPerTick() > recentInputPerTick();
        boolean severeLow = energy.getEnergyStored() <= ENERGY_CAPACITY / 10;
        if (energy.getEnergyStored() <= threshold && (draining || severeLow)) {
            criticalDeficitTicks = Math.min(CRITICAL_DEFICIT_CONFIRM_TICKS + 20, criticalDeficitTicks + 1);
        } else {
            criticalDeficitTicks = Math.max(0, criticalDeficitTicks - 1);
        }
    }

    public boolean criticalDeficit() {
        return circuitMode == CircuitMode.CRITICAL && criticalDeficitTicks >= CRITICAL_DEFICIT_CONFIRM_TICKS;
    }

    /** Nearest recently-active panel owns automatic coordination when panel radii overlap. */
    public boolean applyCoordinator(BlockPos panelPos, boolean blockAux, long gameTime) {
        if (panelPos == null) return false;
        if (coordinatorPos != null && !coordinatorPos.equals(panelPos)
                && gameTime - lastCoordinatorTick <= 40L
                && getBlockPos().distSqr(coordinatorPos) <= getBlockPos().distSqr(panelPos)) {
            return false;
        }
        coordinatorPos = panelPos.immutable();
        lastCoordinatorTick = gameTime;
        if (circuitMode == CircuitMode.AUX) {
            if (blockAux) {
                coordinatorBlocked = true;
                if (auxState != AuxState.SHED) auxState = AuxState.SHED;
            } else {
                boolean wasBlocked = coordinatorBlocked;
                coordinatorBlocked = false;
                if (wasBlocked || auxState == AuxState.SHED) auxState = AuxState.REARMING;
            }
        } else {
            coordinatorBlocked = false;
        }
        setChanged();
        return true;
    }

    public boolean managedBy(BlockPos panelPos, long gameTime) {
        return panelPos != null && panelPos.equals(coordinatorPos) && gameTime - lastCoordinatorTick <= 40L;
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
            lastOutputPerTick = outputThisTick;
        } else {
            lastInputPerTick = 0;
            lastOutputPerTick = 0;
        }
        inputThisTick = 0;
        outputThisTick = 0;
        counterTick = now;
    }

    private int receiveTracked(int maxReceive, boolean simulate) {
        syncCounters();
        if (!inputAllowed() || maxReceive <= 0) return 0;
        int remaining = Math.max(0, MAX_TRANSFER_PER_TICK - inputThisTick);
        if (remaining <= 0) return 0;
        int received = energy.receiveEnergy(Math.min(maxReceive, remaining), simulate);
        if (!simulate && received > 0) {
            inputThisTick += received;
            everPowered = true;
        }
        return received;
    }

    private int extractTracked(int maxExtract, boolean simulate) {
        syncCounters();
        if (!outputAllowed() || maxExtract <= 0) return 0;
        int remaining = Math.max(0, MAX_TRANSFER_PER_TICK - outputThisTick);
        if (remaining <= 0) return 0;
        int extracted = energy.extractEnergy(Math.min(maxExtract, remaining), simulate);
        if (!simulate && extracted > 0) outputThisTick += extracted;
        return extracted;
    }

    public int recentInputPerTick() {
        syncCounters();
        return inputThisTick > 0 ? inputThisTick : lastInputPerTick;
    }

    public int recentOutputPerTick() {
        syncCounters();
        return outputThisTick > 0 ? outputThisTick : lastOutputPerTick;
    }

    @Override
    public void setRemoved() {
        if (level instanceof ServerLevel serverLevel) PowerTapManager.unregister(serverLevel, tapId);
        super.setRemoved();
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        if (tag.hasUUID("TapId")) tapId = tag.getUUID("TapId");
        displayName = tag.contains("TapName") ? tag.getString("TapName") : "Power Tap";
        int circuit = tag.getInt("Circuit");
        circuitMode = circuit >= 0 && circuit < CircuitMode.values().length ? CircuitMode.values()[circuit] : CircuitMode.CRITICAL;
        int state = tag.getInt("AuxState");
        auxState = state >= 0 && state < AuxState.values().length ? AuxState.values()[state] : AuxState.ACTIVE;
        relayEnabled = !tag.contains("Relay") || tag.getBoolean("Relay");
        everPowered = tag.getBoolean("EverPowered") || energy.getEnergyStored() > 0;
        priority = tag.getInt("Priority");
        coordinatorBlocked = false;
        coordinatorPos = null;
        lastCoordinatorTick = Long.MIN_VALUE;
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        tag.putUUID("TapId", tapId);
        tag.putString("TapName", displayName);
        tag.putInt("Circuit", circuitMode.ordinal());
        tag.putInt("AuxState", auxState.ordinal());
        tag.putBoolean("Relay", relayEnabled);
        tag.putBoolean("EverPowered", everPowered);
        tag.putInt("Priority", priority);
    }
}
