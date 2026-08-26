from pathlib import Path
import json

ROOT = Path("Afterfall")
JAVA = ROOT / "src/main/java/dev/afterfall"
RES = ROOT / "src/main/resources"


def write_java(rel: str, content: str) -> None:
    path = JAVA / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_res(rel: str, content: str) -> None:
    path = RES / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def replace_java(rel: str, old: str, new: str) -> None:
    path = JAVA / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected patch anchor not found in {rel}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


props = ROOT / "gradle.properties"
text = props.read_text(encoding="utf-8")
if "mod_version=0.9.1.2" not in text:
    raise SystemExit("Expected exact 0.9.1.2 source snapshot")
props.write_text(text.replace("mod_version=0.9.1.2", "mod_version=0.9.2"), encoding="utf-8")


write_java("block/SmartPowerTapBlock.java", r'''package dev.afterfall.block;

import dev.afterfall.blockentity.SmartPowerTapBlockEntity;
import dev.afterfall.content.ModBlockEntities;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.EntityBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityTicker;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import org.jetbrains.annotations.Nullable;

/**
 * Local bunker circuit interface: BACK = grid input, FRONT = protected load output.
 * Placement follows the player's look direction, matching Afterfall machinery.
 */
public final class SmartPowerTapBlock extends Block implements EntityBlock {
    public static final DirectionProperty FACING = BlockStateProperties.FACING;

    public SmartPowerTapBlock(Properties properties) {
        super(properties);
        registerDefaultState(stateDefinition.any().setValue(FACING, Direction.NORTH));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        return defaultBlockState().setValue(FACING, context.getNearestLookingDirection().getOpposite());
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(FACING);
    }

    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
        return new SmartPowerTapBlockEntity(pos, state);
    }

    @Override
    @Nullable
    public <T extends BlockEntity> BlockEntityTicker<T> getTicker(Level level, BlockState state, BlockEntityType<T> type) {
        return level.isClientSide ? null
                : createTicker(type, ModBlockEntities.SMART_POWER_TAP.get(), SmartPowerTapBlockEntity::serverTick);
    }

    @SuppressWarnings("unchecked")
    private static <E extends BlockEntity, T extends BlockEntity> BlockEntityTicker<T> createTicker(
            BlockEntityType<T> actual, BlockEntityType<E> expected, BlockEntityTicker<? super E> ticker) {
        return actual == expected ? (BlockEntityTicker<T>) ticker : null;
    }
}
''')


write_java("block/PowerControlPanelBlock.java", r'''package dev.afterfall.block;

import dev.afterfall.blockentity.PowerControlPanelBlockEntity;
import dev.afterfall.content.ModBlockEntities;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.EntityBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityTicker;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import org.jetbrains.annotations.Nullable;

/** Central telemetry/load-shedding controller. It does not transport FE itself. */
public final class PowerControlPanelBlock extends Block implements EntityBlock {
    public static final DirectionProperty FACING = BlockStateProperties.HORIZONTAL_FACING;

    public PowerControlPanelBlock(Properties properties) {
        super(properties);
        registerDefaultState(stateDefinition.any().setValue(FACING, Direction.NORTH));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        return defaultBlockState().setValue(FACING, context.getHorizontalDirection().getOpposite());
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(FACING);
    }

    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
        return new PowerControlPanelBlockEntity(pos, state);
    }

    @Override
    @Nullable
    public <T extends BlockEntity> BlockEntityTicker<T> getTicker(Level level, BlockState state, BlockEntityType<T> type) {
        return level.isClientSide ? null
                : createTicker(type, ModBlockEntities.POWER_CONTROL_PANEL.get(), PowerControlPanelBlockEntity::serverTick);
    }

    @SuppressWarnings("unchecked")
    private static <E extends BlockEntity, T extends BlockEntity> BlockEntityTicker<T> createTicker(
            BlockEntityType<T> actual, BlockEntityType<E> expected, BlockEntityTicker<? super E> ticker) {
        return actual == expected ? (BlockEntityTicker<T>) ticker : null;
    }
}
''')


write_java("power/PowerTapManager.java", r'''package dev.afterfall.power;

import dev.afterfall.blockentity.SmartPowerTapBlockEntity;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Lightweight registry of loaded/recent Smart Power Taps. No volume block scans are used. */
public final class PowerTapManager {
    private static final Map<ResourceKey<Level>, Map<UUID, BlockPos>> TAPS = new HashMap<>();

    public static void register(ServerLevel level, SmartPowerTapBlockEntity tap) {
        TAPS.computeIfAbsent(level.dimension(), ignored -> new HashMap<>())
                .put(tap.tapId(), tap.getBlockPos().immutable());
    }

    public static void unregister(ServerLevel level, UUID id) {
        Map<UUID, BlockPos> map = TAPS.get(level.dimension());
        if (map != null) map.remove(id);
    }

    public static List<SmartPowerTapBlockEntity> find(ServerLevel level, BlockPos center, int radius) {
        Map<UUID, BlockPos> map = TAPS.computeIfAbsent(level.dimension(), ignored -> new HashMap<>());
        double radiusSq = (double) radius * radius;
        List<SmartPowerTapBlockEntity> result = new ArrayList<>();
        Iterator<Map.Entry<UUID, BlockPos>> iterator = map.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<UUID, BlockPos> entry = iterator.next();
            BlockPos pos = entry.getValue();
            if (!level.hasChunkAt(pos)) continue;
            BlockEntity blockEntity = level.getBlockEntity(pos);
            if (!(blockEntity instanceof SmartPowerTapBlockEntity tap) || !tap.tapId().equals(entry.getKey())) {
                iterator.remove();
                continue;
            }
            if (center.distSqr(pos) <= radiusSq) result.add(tap);
        }
        result.sort((a, b) -> {
            int priority = Integer.compare(b.priority(), a.priority());
            if (priority != 0) return priority;
            int name = a.displayName().compareToIgnoreCase(b.displayName());
            if (name != 0) return name;
            return a.getBlockPos().compareTo(b.getBlockPos());
        });
        return result;
    }

    public static SmartPowerTapBlockEntity findById(ServerLevel level, BlockPos center, int radius, UUID id) {
        for (SmartPowerTapBlockEntity tap : find(level, center, radius)) {
            if (tap.tapId().equals(id)) return tap;
        }
        return null;
    }

    private PowerTapManager() {}
}
''')


write_java("blockentity/SmartPowerTapBlockEntity.java", r'''package dev.afterfall.blockentity;

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
''')


write_java("blockentity/PowerControlPanelBlockEntity.java", r'''package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.power.PowerTapManager;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.List;

/**
 * SCADA-style coordinator. It never transports FE; it only observes Smart Power Taps
 * and applies safe load-shedding/recovery policy within a local radius.
 */
public final class PowerControlPanelBlockEntity extends BlockEntity {
    public static final int CONTROL_RADIUS = 48;
    public static final int UPDATE_INTERVAL_TICKS = 10;
    public static final int CRITICAL_STABLE_REQUIRED_TICKS = 100;

    private boolean criticalDeficit;
    private boolean loadShedActive;
    private boolean recoveryWaiting;
    private int criticalStableTicks;

    public PowerControlPanelBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.POWER_CONTROL_PANEL.get(), pos, state);
    }

    public boolean criticalDeficit() { return criticalDeficit; }
    public boolean loadShedActive() { return loadShedActive; }
    public boolean recoveryWaiting() { return recoveryWaiting; }
    public int criticalStableTicks() { return criticalStableTicks; }

    public static void serverTick(Level level, BlockPos pos, BlockState state, PowerControlPanelBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel)) return;
        if (serverLevel.getGameTime() % UPDATE_INTERVAL_TICKS != 0L) return;
        be.coordinateNow(serverLevel);
    }

    public void coordinateNow(ServerLevel level) {
        List<SmartPowerTapBlockEntity> taps = PowerTapManager.find(level, worldPosition, CONTROL_RADIUS);
        boolean deficitNow = false;
        for (SmartPowerTapBlockEntity tap : taps) {
            if (tap.circuitMode() == SmartPowerTapBlockEntity.CircuitMode.CRITICAL && tap.criticalDeficit()) {
                deficitNow = true;
                break;
            }
        }

        criticalDeficit = deficitNow;
        if (deficitNow) {
            loadShedActive = true;
            recoveryWaiting = true;
            criticalStableTicks = 0;
        } else if (recoveryWaiting) {
            criticalStableTicks = Math.min(CRITICAL_STABLE_REQUIRED_TICKS,
                    criticalStableTicks + UPDATE_INTERVAL_TICKS);
            if (criticalStableTicks >= CRITICAL_STABLE_REQUIRED_TICKS) recoveryWaiting = false;
        }

        long now = level.getGameTime();
        if (criticalDeficit || recoveryWaiting) {
            for (SmartPowerTapBlockEntity tap : taps) {
                tap.applyCoordinator(worldPosition,
                        tap.circuitMode() == SmartPowerTapBlockEntity.CircuitMode.AUX, now);
            }
            setChanged();
            return;
        }

        if (loadShedActive) {
            // Restore one AUX circuit at a time. This prevents the recharge surge itself
            // from starving CRITICAL loads. Future priority tiers can drive this ordering.
            SmartPowerTapBlockEntity granted = null;
            boolean pending = false;
            for (SmartPowerTapBlockEntity tap : taps) {
                if (tap.circuitMode() != SmartPowerTapBlockEntity.CircuitMode.AUX) {
                    tap.applyCoordinator(worldPosition, false, now);
                    continue;
                }
                if (tap.auxState() == SmartPowerTapBlockEntity.AuxState.ACTIVE) {
                    tap.applyCoordinator(worldPosition, false, now);
                    continue;
                }
                pending = true;
                if (granted == null) {
                    granted = tap;
                    tap.applyCoordinator(worldPosition, false, now);
                } else {
                    tap.applyCoordinator(worldPosition, true, now);
                }
            }
            if (!pending) loadShedActive = false;
        } else {
            for (SmartPowerTapBlockEntity tap : taps) tap.applyCoordinator(worldPosition, false, now);
        }
        setChanged();
    }
}
''')


write_java("menu/SmartPowerTapMenu.java", r'''package dev.afterfall.menu;

import dev.afterfall.blockentity.SmartPowerTapBlockEntity;
import dev.afterfall.content.ModMenus;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.SimpleContainerData;
import net.minecraft.world.item.ItemStack;

public final class SmartPowerTapMenu extends AbstractContainerMenu {
    public static final int DATA_COUNT = 10;
    public static final int BUTTON_CRITICAL = 0;
    public static final int BUTTON_AUX = 1;
    public static final int BUTTON_RELAY = 2;

    public static final int D_CIRCUIT = 0;
    public static final int D_RELAY = 1;
    public static final int D_AUX_STATE = 2;
    public static final int D_ENERGY = 3;
    public static final int D_ENERGY_MAX = 4;
    public static final int D_INPUT = 5;
    public static final int D_OUTPUT = 6;
    public static final int D_DEFICIT = 7;
    public static final int D_REARM_PERCENT = 8;
    public static final int D_THROUGHPUT = 9;

    private final SimpleContainerData data = new SimpleContainerData(DATA_COUNT);
    private final BlockPos blockPos;
    private final SmartPowerTapBlockEntity serverTap;
    private String clientName;

    public SmartPowerTapMenu(int containerId, Inventory inventory, RegistryFriendlyByteBuf buf) {
        this(containerId, inventory, buf.readBlockPos(), null, buf.readUtf(32));
    }

    public SmartPowerTapMenu(int containerId, Inventory inventory, BlockPos pos, SmartPowerTapBlockEntity tap) {
        this(containerId, inventory, pos, tap, tap == null ? "Power Tap" : tap.displayName());
    }

    private SmartPowerTapMenu(int containerId, Inventory inventory, BlockPos pos,
                              SmartPowerTapBlockEntity tap, String name) {
        super(ModMenus.SMART_POWER_TAP.get(), containerId);
        blockPos = pos.immutable();
        serverTap = tap;
        clientName = name;
        addDataSlots(data);
        if (tap != null) updateServerData();
    }

    @Override
    public void broadcastChanges() {
        if (serverTap != null) updateServerData();
        super.broadcastChanges();
    }

    private void updateServerData() {
        if (!(serverTap.getLevel() instanceof ServerLevel)) return;
        data.set(D_CIRCUIT, serverTap.circuitMode().ordinal());
        data.set(D_RELAY, serverTap.relayEnabled() ? 1 : 0);
        data.set(D_AUX_STATE, serverTap.auxState().ordinal());
        data.set(D_ENERGY, serverTap.energyStored());
        data.set(D_ENERGY_MAX, serverTap.maxEnergyStored());
        data.set(D_INPUT, serverTap.recentInputPerTick());
        data.set(D_OUTPUT, serverTap.recentOutputPerTick());
        data.set(D_DEFICIT, serverTap.criticalDeficit() ? 1 : 0);
        data.set(D_REARM_PERCENT, SmartPowerTapBlockEntity.AUX_REARM_PERCENT);
        data.set(D_THROUGHPUT, SmartPowerTapBlockEntity.MAX_TRANSFER_PER_TICK);
    }

    @Override
    public boolean clickMenuButton(Player player, int id) {
        if (serverTap == null) return true;
        if (id == BUTTON_CRITICAL) serverTap.setCircuitMode(SmartPowerTapBlockEntity.CircuitMode.CRITICAL);
        else if (id == BUTTON_AUX) serverTap.setCircuitMode(SmartPowerTapBlockEntity.CircuitMode.AUX);
        else if (id == BUTTON_RELAY) serverTap.setRelayEnabled(!serverTap.relayEnabled());
        else return false;
        updateServerData();
        return true;
    }

    public BlockPos blockPos() { return blockPos; }
    public String tapName() { return clientName; }
    public void setClientName(String value) { clientName = value; }
    public int get(int index) { return data.get(index); }

    @Override
    public boolean stillValid(Player player) {
        return player.blockPosition().distSqr(blockPos) <= 64.0D;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        return ItemStack.EMPTY;
    }
}
''')


write_java("menu/PowerControlPanelMenu.java", r'''package dev.afterfall.menu;

import dev.afterfall.blockentity.PowerControlPanelBlockEntity;
import dev.afterfall.content.ModMenus;
import dev.afterfall.network.PowerNetworking;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.item.ItemStack;

import java.util.List;

public final class PowerControlPanelMenu extends AbstractContainerMenu {
    private final BlockPos panelPos;
    private final PowerControlPanelBlockEntity serverPanel;
    private final ServerPlayer serverPlayer;
    private List<PowerNetworking.TapEntry> clientEntries = List.of();
    private boolean clientCriticalDeficit;
    private boolean clientLoadShed;
    private boolean clientRecoveryWaiting;
    private int clientStableTicks;

    public PowerControlPanelMenu(int containerId, Inventory inventory, RegistryFriendlyByteBuf buf) {
        this(containerId, inventory, buf.readBlockPos(), null);
    }

    public PowerControlPanelMenu(int containerId, Inventory inventory, BlockPos pos,
                                 PowerControlPanelBlockEntity panel) {
        super(ModMenus.POWER_CONTROL_PANEL.get(), containerId);
        panelPos = pos.immutable();
        serverPanel = panel;
        serverPlayer = inventory.player instanceof ServerPlayer sp ? sp : null;
    }

    @Override
    public void broadcastChanges() {
        super.broadcastChanges();
        if (serverPanel != null && serverPlayer != null && serverPlayer.tickCount % 10 == 0) {
            PowerNetworking.sendPanelSnapshot(serverPlayer, panelPos);
        }
    }

    public void acceptSnapshot(PowerNetworking.PanelSnapshotPayload payload) {
        if (!panelPos.equals(payload.panelPos())) return;
        clientEntries = List.copyOf(payload.entries());
        clientCriticalDeficit = payload.criticalDeficit();
        clientLoadShed = payload.loadShedActive();
        clientRecoveryWaiting = payload.recoveryWaiting();
        clientStableTicks = payload.stableTicks();
    }

    public BlockPos panelPos() { return panelPos; }
    public List<PowerNetworking.TapEntry> entries() { return clientEntries; }
    public boolean criticalDeficit() { return clientCriticalDeficit; }
    public boolean loadShedActive() { return clientLoadShed; }
    public boolean recoveryWaiting() { return clientRecoveryWaiting; }
    public int stableTicks() { return clientStableTicks; }

    @Override
    public boolean stillValid(Player player) {
        return player.blockPosition().distSqr(panelPos) <= 64.0D;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        return ItemStack.EMPTY;
    }
}
''')


write_java("network/PowerNetworking.java", r'''package dev.afterfall.network;

import dev.afterfall.Afterfall;
import dev.afterfall.blockentity.PowerControlPanelBlockEntity;
import dev.afterfall.blockentity.SmartPowerTapBlockEntity;
import dev.afterfall.menu.PowerControlPanelMenu;
import dev.afterfall.menu.SmartPowerTapMenu;
import dev.afterfall.power.PowerTapManager;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.network.PacketDistributor;
import net.neoforged.neoforge.network.event.RegisterPayloadHandlersEvent;
import net.neoforged.neoforge.network.handling.IPayloadContext;
import net.neoforged.neoforge.network.registration.PayloadRegistrar;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@EventBusSubscriber(modid = Afterfall.MOD_ID, bus = EventBusSubscriber.Bus.MOD)
public final class PowerNetworking {
    public static final int CMD_CRITICAL = 0;
    public static final int CMD_AUX = 1;
    public static final int CMD_ON = 2;
    public static final int CMD_OFF = 3;

    public record TapRenamePayload(BlockPos pos, String name) implements CustomPacketPayload {
        public static final Type<TapRenamePayload> TYPE = new Type<>(
                ResourceLocation.fromNamespaceAndPath(Afterfall.MOD_ID, "tap_rename"));
        public static final StreamCodec<RegistryFriendlyByteBuf, TapRenamePayload> STREAM_CODEC = StreamCodec.of(
                (buf, payload) -> {
                    buf.writeBlockPos(payload.pos());
                    buf.writeUtf(payload.name(), 32);
                },
                buf -> new TapRenamePayload(buf.readBlockPos(), buf.readUtf(32)));
        @Override public Type<? extends CustomPacketPayload> type() { return TYPE; }
    }

    public record PanelCommandPayload(BlockPos panelPos, UUID tapId, int command) implements CustomPacketPayload {
        public static final Type<PanelCommandPayload> TYPE = new Type<>(
                ResourceLocation.fromNamespaceAndPath(Afterfall.MOD_ID, "panel_tap_command"));
        public static final StreamCodec<RegistryFriendlyByteBuf, PanelCommandPayload> STREAM_CODEC = StreamCodec.of(
                (buf, payload) -> {
                    buf.writeBlockPos(payload.panelPos());
                    buf.writeUUID(payload.tapId());
                    buf.writeVarInt(payload.command());
                },
                buf -> new PanelCommandPayload(buf.readBlockPos(), buf.readUUID(), buf.readVarInt()));
        @Override public Type<? extends CustomPacketPayload> type() { return TYPE; }
    }

    public record TapEntry(UUID id, BlockPos pos, String name, int circuit, boolean relay,
                           int auxState, int energy, int maxEnergy, int inputPerTick, int outputPerTick,
                           boolean criticalDeficit, boolean managedByPanel) {}

    public record PanelSnapshotPayload(BlockPos panelPos, boolean criticalDeficit, boolean loadShedActive,
                                       boolean recoveryWaiting, int stableTicks,
                                       List<TapEntry> entries) implements CustomPacketPayload {
        public static final Type<PanelSnapshotPayload> TYPE = new Type<>(
                ResourceLocation.fromNamespaceAndPath(Afterfall.MOD_ID, "panel_snapshot"));
        public static final StreamCodec<RegistryFriendlyByteBuf, PanelSnapshotPayload> STREAM_CODEC = StreamCodec.of(
                PowerNetworking::writeSnapshot, PowerNetworking::readSnapshot);
        @Override public Type<? extends CustomPacketPayload> type() { return TYPE; }
    }

    @SubscribeEvent
    public static void register(RegisterPayloadHandlersEvent event) {
        PayloadRegistrar registrar = event.registrar("092");
        registrar.playToServer(TapRenamePayload.TYPE, TapRenamePayload.STREAM_CODEC, PowerNetworking::handleRename);
        registrar.playToServer(PanelCommandPayload.TYPE, PanelCommandPayload.STREAM_CODEC, PowerNetworking::handlePanelCommand);
        // Handler is common-code-only: IPayloadContext supplies the logical-side Player.
        registrar.playToClient(PanelSnapshotPayload.TYPE, PanelSnapshotPayload.STREAM_CODEC, PowerNetworking::handleSnapshot);
    }

    private static void handleRename(TapRenamePayload payload, IPayloadContext context) {
        Player logicalPlayer = context.player();
        if (!(logicalPlayer instanceof ServerPlayer player)) return;
        if (!(player.containerMenu instanceof SmartPowerTapMenu menu) || !menu.blockPos().equals(payload.pos())) return;
        if (player.blockPosition().distSqr(payload.pos()) > 64.0D) return;
        BlockEntity blockEntity = player.serverLevel().getBlockEntity(payload.pos());
        if (!(blockEntity instanceof SmartPowerTapBlockEntity tap)) return;
        String clean = payload.name().replace("§", "").replaceAll("[\\p{Cntrl}]", "").trim();
        tap.setDisplayName(clean);
    }

    private static void handlePanelCommand(PanelCommandPayload payload, IPayloadContext context) {
        Player logicalPlayer = context.player();
        if (!(logicalPlayer instanceof ServerPlayer player)) return;
        if (!(player.containerMenu instanceof PowerControlPanelMenu menu) || !menu.panelPos().equals(payload.panelPos())) return;
        if (player.blockPosition().distSqr(payload.panelPos()) > 64.0D) return;
        ServerLevel level = player.serverLevel();
        BlockEntity panelEntity = level.getBlockEntity(payload.panelPos());
        if (!(panelEntity instanceof PowerControlPanelBlockEntity panel)) return;
        SmartPowerTapBlockEntity tap = PowerTapManager.findById(level, payload.panelPos(),
                PowerControlPanelBlockEntity.CONTROL_RADIUS, payload.tapId());
        if (tap == null) return;
        switch (payload.command()) {
            case CMD_CRITICAL -> tap.setCircuitMode(SmartPowerTapBlockEntity.CircuitMode.CRITICAL);
            case CMD_AUX -> tap.setCircuitMode(SmartPowerTapBlockEntity.CircuitMode.AUX);
            case CMD_ON -> tap.setRelayEnabled(true);
            case CMD_OFF -> tap.setRelayEnabled(false);
            default -> { return; }
        }
        panel.coordinateNow(level);
        sendPanelSnapshot(player, payload.panelPos());
    }

    private static void handleSnapshot(PanelSnapshotPayload payload, IPayloadContext context) {
        Player player = context.player();
        if (player != null && player.containerMenu instanceof PowerControlPanelMenu menu) {
            menu.acceptSnapshot(payload);
        }
    }

    public static void sendPanelSnapshot(ServerPlayer player, BlockPos panelPos) {
        if (!(player.serverLevel().getBlockEntity(panelPos) instanceof PowerControlPanelBlockEntity panel)) return;
        ServerLevel level = player.serverLevel();
        long now = level.getGameTime();
        List<TapEntry> entries = new ArrayList<>();
        for (SmartPowerTapBlockEntity tap : PowerTapManager.find(level, panelPos,
                PowerControlPanelBlockEntity.CONTROL_RADIUS)) {
            entries.add(new TapEntry(
                    tap.tapId(), tap.getBlockPos().immutable(), tap.displayName(), tap.circuitMode().ordinal(),
                    tap.relayEnabled(), tap.auxState().ordinal(), tap.energyStored(), tap.maxEnergyStored(),
                    tap.recentInputPerTick(), tap.recentOutputPerTick(), tap.criticalDeficit(),
                    tap.managedBy(panelPos, now)));
            if (entries.size() >= 32) break;
        }
        PacketDistributor.sendToPlayer(player, new PanelSnapshotPayload(
                panelPos.immutable(), panel.criticalDeficit(), panel.loadShedActive(), panel.recoveryWaiting(),
                panel.criticalStableTicks(), List.copyOf(entries)));
    }

    private static void writeSnapshot(RegistryFriendlyByteBuf buf, PanelSnapshotPayload payload) {
        buf.writeBlockPos(payload.panelPos());
        buf.writeBoolean(payload.criticalDeficit());
        buf.writeBoolean(payload.loadShedActive());
        buf.writeBoolean(payload.recoveryWaiting());
        buf.writeVarInt(payload.stableTicks());
        int count = Math.min(32, payload.entries().size());
        buf.writeVarInt(count);
        for (int i = 0; i < count; i++) {
            TapEntry entry = payload.entries().get(i);
            buf.writeUUID(entry.id());
            buf.writeBlockPos(entry.pos());
            buf.writeUtf(entry.name(), 32);
            buf.writeVarInt(entry.circuit());
            buf.writeBoolean(entry.relay());
            buf.writeVarInt(entry.auxState());
            buf.writeVarInt(entry.energy());
            buf.writeVarInt(entry.maxEnergy());
            buf.writeVarInt(entry.inputPerTick());
            buf.writeVarInt(entry.outputPerTick());
            buf.writeBoolean(entry.criticalDeficit());
            buf.writeBoolean(entry.managedByPanel());
        }
    }

    private static PanelSnapshotPayload readSnapshot(RegistryFriendlyByteBuf buf) {
        BlockPos panelPos = buf.readBlockPos();
        boolean deficit = buf.readBoolean();
        boolean shed = buf.readBoolean();
        boolean recovery = buf.readBoolean();
        int stable = buf.readVarInt();
        int count = Math.max(0, Math.min(32, buf.readVarInt()));
        List<TapEntry> entries = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            entries.add(new TapEntry(buf.readUUID(), buf.readBlockPos(), buf.readUtf(32), buf.readVarInt(),
                    buf.readBoolean(), buf.readVarInt(), buf.readVarInt(), buf.readVarInt(),
                    buf.readVarInt(), buf.readVarInt(), buf.readBoolean(), buf.readBoolean()));
        }
        return new PanelSnapshotPayload(panelPos, deficit, shed, recovery, stable, List.copyOf(entries));
    }

    private PowerNetworking() {}
}
''')


write_java("client/SmartPowerTapScreen.java", r'''package dev.afterfall.client;

import dev.afterfall.blockentity.SmartPowerTapBlockEntity;
import dev.afterfall.menu.SmartPowerTapMenu;
import dev.afterfall.network.PowerNetworking;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;
import net.neoforged.neoforge.network.PacketDistributor;

public final class SmartPowerTapScreen extends AbstractContainerScreen<SmartPowerTapMenu> {
    private Button criticalButton;
    private Button auxButton;
    private Button relayButton;
    private EditBox nameBox;

    public SmartPowerTapScreen(SmartPowerTapMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title);
        imageWidth = 264;
        imageHeight = 190;
        inventoryLabelY = 10_000;
    }

    @Override
    protected void init() {
        super.init();
        nameBox = new EditBox(font, leftPos + 12, topPos + 38, 170, 18, Component.literal("Circuit name"));
        nameBox.setMaxLength(32);
        nameBox.setValue(menu.tapName());
        addRenderableWidget(nameBox);
        addRenderableWidget(Button.builder(Component.literal("SAVE"), b -> saveName())
                .bounds(leftPos + 188, topPos + 38, 64, 18).build());
        criticalButton = addRenderableWidget(Button.builder(Component.literal("CRITICAL"), b -> sendButton(SmartPowerTapMenu.BUTTON_CRITICAL))
                .bounds(leftPos + 12, topPos + 68, 76, 18).build());
        auxButton = addRenderableWidget(Button.builder(Component.literal("AUX"), b -> sendButton(SmartPowerTapMenu.BUTTON_AUX))
                .bounds(leftPos + 94, topPos + 68, 76, 18).build());
        relayButton = addRenderableWidget(Button.builder(Component.literal("RELAY"), b -> sendButton(SmartPowerTapMenu.BUTTON_RELAY))
                .bounds(leftPos + 176, topPos + 68, 76, 18).build());
    }

    private void saveName() {
        if (nameBox == null) return;
        String value = nameBox.getValue();
        menu.setClientName(value);
        PacketDistributor.sendToServer(new PowerNetworking.TapRenamePayload(menu.blockPos(), value));
    }

    private void sendButton(int id) {
        if (minecraft != null && minecraft.gameMode != null) {
            minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
        }
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        updateButtons();
        renderBackground(graphics, mouseX, mouseY, partialTick);
        super.render(graphics, mouseX, mouseY, partialTick);
        renderTooltip(graphics, mouseX, mouseY);
    }

    private void updateButtons() {
        int circuit = menu.get(SmartPowerTapMenu.D_CIRCUIT);
        if (criticalButton != null) criticalButton.setMessage(Component.literal(circuit == 0 ? "[ CRITICAL ]" : "CRITICAL"));
        if (auxButton != null) auxButton.setMessage(Component.literal(circuit == 1 ? "[ AUX ]" : "AUX"));
        if (relayButton != null) relayButton.setMessage(Component.literal(menu.get(SmartPowerTapMenu.D_RELAY) != 0 ? "RELAY: ON" : "RELAY: OFF"));
    }

    @Override
    protected void renderBg(GuiGraphics graphics, float partialTick, int mouseX, int mouseY) {
        graphics.fill(leftPos, topPos, leftPos + imageWidth, topPos + imageHeight, 0xE614181A);
        graphics.fill(leftPos + 1, topPos + 1, leftPos + imageWidth - 1, topPos + 22, 0xFF242B2E);
        graphics.fill(leftPos + 7, topPos + 94, leftPos + imageWidth - 7, topPos + imageHeight - 8, 0xCC0B0E10);
    }

    @Override
    protected void renderLabels(GuiGraphics graphics, int mouseX, int mouseY) {
        graphics.drawString(font, "AFTERFALL // SMART POWER TAP", 10, 8, 0xFF76D7EA, false);
        int energy = menu.get(SmartPowerTapMenu.D_ENERGY);
        int max = Math.max(1, menu.get(SmartPowerTapMenu.D_ENERGY_MAX));
        int pct = energy * 100 / max;
        String circuit = menu.get(SmartPowerTapMenu.D_CIRCUIT) == 0 ? "CRITICAL" : "AUX";
        String auxState = switch (menu.get(SmartPowerTapMenu.D_AUX_STATE)) {
            case 1 -> "SHED";
            case 2 -> "REARMING";
            default -> "ACTIVE";
        };
        int y = 102;
        graphics.drawString(font, "Circuit: " + circuit + " | Relay: " + (menu.get(SmartPowerTapMenu.D_RELAY) != 0 ? "ON" : "OFF"), 14, y, 0xFFE8E8E8, false);
        graphics.drawString(font, "Buffer: " + energy + " / " + max + " FE (" + pct + "%)", 14, y + 14, 0xFFE8E8E8, false);
        graphics.drawString(font, "Input: " + menu.get(SmartPowerTapMenu.D_INPUT) + " FE/t | Output: " + menu.get(SmartPowerTapMenu.D_OUTPUT) + " FE/t", 14, y + 28, 0xFFE8E8E8, false);
        if (menu.get(SmartPowerTapMenu.D_CIRCUIT) == 1) {
            graphics.drawString(font, "AUX state: " + auxState + " | Rearm: " + menu.get(SmartPowerTapMenu.D_REARM_PERCENT) + "%", 14, y + 42,
                    auxState.equals("ACTIVE") ? 0xFF72E06A : (auxState.equals("REARMING") ? 0xFFFFD166 : 0xFFFF6B6B), false);
        } else {
            graphics.drawString(font, menu.get(SmartPowerTapMenu.D_DEFICIT) != 0 ? "CRITICAL DEFICIT" : "Critical supply stable", 14, y + 42,
                    menu.get(SmartPowerTapMenu.D_DEFICIT) != 0 ? 0xFFFF6B6B : 0xFF72E06A, false);
        }
        graphics.drawString(font, "BACK = GRID | FRONT = LOAD | Max " + menu.get(SmartPowerTapMenu.D_THROUGHPUT) + " FE/t", 14, y + 56, 0xFF9AA4A8, false);
    }
}
''')


write_java("client/PowerControlPanelScreen.java", r'''package dev.afterfall.client;

import dev.afterfall.blockentity.PowerControlPanelBlockEntity;
import dev.afterfall.menu.PowerControlPanelMenu;
import dev.afterfall.network.PowerNetworking;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;
import net.neoforged.neoforge.network.PacketDistributor;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class PowerControlPanelScreen extends AbstractContainerScreen<PowerControlPanelMenu> {
    private static final int ROWS = 6;
    private final List<Button> rowButtons = new ArrayList<>();
    private Button prevButton;
    private Button nextButton;
    private Button criticalButton;
    private Button auxButton;
    private Button onButton;
    private Button offButton;
    private int page;
    private UUID selectedId;

    public PowerControlPanelScreen(PowerControlPanelMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title);
        imageWidth = 340;
        imageHeight = 292;
        inventoryLabelY = 10_000;
    }

    @Override
    protected void init() {
        super.init();
        rowButtons.clear();
        for (int i = 0; i < ROWS; i++) {
            final int row = i;
            rowButtons.add(addRenderableWidget(Button.builder(Component.literal("--"), b -> selectRow(row))
                    .bounds(leftPos + 12, topPos + 54 + i * 24, 316, 20).build()));
        }
        prevButton = addRenderableWidget(Button.builder(Component.literal("<"), b -> page = Math.max(0, page - 1))
                .bounds(leftPos + 12, topPos + 202, 30, 18).build());
        nextButton = addRenderableWidget(Button.builder(Component.literal(">"), b -> page++)
                .bounds(leftPos + 298, topPos + 202, 30, 18).build());
        criticalButton = addRenderableWidget(Button.builder(Component.literal("CRITICAL"), b -> sendSelected(PowerNetworking.CMD_CRITICAL))
                .bounds(leftPos + 12, topPos + 230, 76, 18).build());
        auxButton = addRenderableWidget(Button.builder(Component.literal("AUX"), b -> sendSelected(PowerNetworking.CMD_AUX))
                .bounds(leftPos + 94, topPos + 230, 76, 18).build());
        onButton = addRenderableWidget(Button.builder(Component.literal("ON"), b -> sendSelected(PowerNetworking.CMD_ON))
                .bounds(leftPos + 176, topPos + 230, 70, 18).build());
        offButton = addRenderableWidget(Button.builder(Component.literal("OFF"), b -> sendSelected(PowerNetworking.CMD_OFF))
                .bounds(leftPos + 252, topPos + 230, 76, 18).build());
    }

    private void selectRow(int row) {
        int index = page * ROWS + row;
        List<PowerNetworking.TapEntry> entries = menu.entries();
        if (index >= 0 && index < entries.size()) selectedId = entries.get(index).id();
    }

    private PowerNetworking.TapEntry selected() {
        if (selectedId == null) return null;
        for (PowerNetworking.TapEntry entry : menu.entries()) if (entry.id().equals(selectedId)) return entry;
        return null;
    }

    private void sendSelected(int command) {
        PowerNetworking.TapEntry entry = selected();
        if (entry == null) return;
        PacketDistributor.sendToServer(new PowerNetworking.PanelCommandPayload(menu.panelPos(), entry.id(), command));
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        updateButtons();
        renderBackground(graphics, mouseX, mouseY, partialTick);
        super.render(graphics, mouseX, mouseY, partialTick);
        renderTooltip(graphics, mouseX, mouseY);
    }

    private void updateButtons() {
        List<PowerNetworking.TapEntry> entries = menu.entries();
        int pages = Math.max(1, (entries.size() + ROWS - 1) / ROWS);
        if (page >= pages) page = pages - 1;
        if (page < 0) page = 0;
        for (int row = 0; row < ROWS; row++) {
            int index = page * ROWS + row;
            Button button = rowButtons.get(row);
            if (index >= entries.size()) {
                button.visible = false;
                continue;
            }
            button.visible = true;
            PowerNetworking.TapEntry entry = entries.get(index);
            String circuit = entry.circuit() == 0 ? "CRIT" : "AUX";
            String state = entry.relay() ? "ON" : "OFF";
            if (entry.circuit() == 1) {
                if (entry.auxState() == 1) state += "/SHED";
                else if (entry.auxState() == 2) state += "/REARM";
            }
            String marker = entry.id().equals(selectedId) ? "> " : "  ";
            button.setMessage(Component.literal(marker + entry.name() + " | " + circuit + " | " + state
                    + " | " + entry.outputPerTick() + " FE/t"));
        }
        if (prevButton != null) prevButton.active = page > 0;
        if (nextButton != null) nextButton.active = page + 1 < pages;
        boolean selected = selected() != null;
        if (criticalButton != null) criticalButton.active = selected;
        if (auxButton != null) auxButton.active = selected;
        if (onButton != null) onButton.active = selected;
        if (offButton != null) offButton.active = selected;
    }

    @Override
    protected void renderBg(GuiGraphics graphics, float partialTick, int mouseX, int mouseY) {
        graphics.fill(leftPos, topPos, leftPos + imageWidth, topPos + imageHeight, 0xE614181A);
        graphics.fill(leftPos + 1, topPos + 1, leftPos + imageWidth - 1, topPos + 22, 0xFF242B2E);
        graphics.fill(leftPos + 7, topPos + 28, leftPos + imageWidth - 7, topPos + imageHeight - 8, 0xCC0B0E10);
    }

    @Override
    protected void renderLabels(GuiGraphics graphics, int mouseX, int mouseY) {
        graphics.drawString(font, "AFTERFALL // POWER CONTROL PANEL", 10, 8, 0xFF76D7EA, false);
        String status;
        int statusColor;
        if (menu.criticalDeficit()) {
            status = "CRITICAL DEFICIT - AUX LOAD SHED";
            statusColor = 0xFFFF6B6B;
        } else if (menu.recoveryWaiting()) {
            int remaining = Math.max(0, PowerControlPanelBlockEntity.CRITICAL_STABLE_REQUIRED_TICKS - menu.stableTicks());
            status = "CRITICAL RECOVERY - AUX HOLD " + String.format(java.util.Locale.ROOT, "%.1fs", remaining / 20.0D);
            statusColor = 0xFFFFD166;
        } else if (menu.loadShedActive()) {
            status = "STAGED AUX REARMING";
            statusColor = 0xFFFFD166;
        } else {
            status = "POWER DISTRIBUTION STABLE";
            statusColor = 0xFF72E06A;
        }
        graphics.drawString(font, status, 12, 32, statusColor, false);
        graphics.drawString(font, "Detected taps: " + menu.entries().size() + " | Radius: " + PowerControlPanelBlockEntity.CONTROL_RADIUS + " blocks", 12, 43, 0xFF9AA4A8, false);

        PowerNetworking.TapEntry entry = selected();
        if (entry != null) {
            int pct = entry.maxEnergy() <= 0 ? 0 : entry.energy() * 100 / entry.maxEnergy();
            graphics.drawString(font, entry.name() + " @ " + entry.pos().toShortString(), 50, 207, 0xFFE8E8E8, false);
            graphics.drawString(font, "Buffer " + pct + "% | IN " + entry.inputPerTick() + " FE/t | OUT " + entry.outputPerTick()
                    + " FE/t | " + (entry.managedByPanel() ? "MANAGED" : "NEARBY"), 12, 256,
                    entry.managedByPanel() ? 0xFF72E06A : 0xFF9AA4A8, false);
            if (entry.criticalDeficit()) graphics.drawString(font, "CRITICAL DEFICIT", 12, 270, 0xFFFF6B6B, false);
        } else {
            graphics.drawString(font, "Select a tap to inspect/control it.", 12, 256, 0xFF9AA4A8, false);
        }
    }
}
''')


# Registry/content integration.
replace_java("content/ModBlocks.java",
'''import dev.afterfall.block.SealedPowerFeedthroughBlock;\n''',
'''import dev.afterfall.block.SealedPowerFeedthroughBlock;\nimport dev.afterfall.block.SmartPowerTapBlock;\nimport dev.afterfall.block.PowerControlPanelBlock;\n''')
replace_java("content/ModBlocks.java",
'''    public static final DeferredBlock<SealedPowerFeedthroughBlock> SEALED_POWER_FEEDTHROUGH = BLOCKS.register("sealed_power_feedthrough",\n            () -> new SealedPowerFeedthroughBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(6.0F, 12.0F)\n                    .sound(SoundType.METAL)));\n''',
'''    public static final DeferredBlock<SealedPowerFeedthroughBlock> SEALED_POWER_FEEDTHROUGH = BLOCKS.register("sealed_power_feedthrough",\n            () -> new SealedPowerFeedthroughBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(6.0F, 12.0F)\n                    .sound(SoundType.METAL)));\n\n    public static final DeferredBlock<SmartPowerTapBlock> SMART_POWER_TAP = BLOCKS.register("smart_power_tap",\n            () -> new SmartPowerTapBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.5F, 8.0F)\n                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));\n\n    public static final DeferredBlock<PowerControlPanelBlock> POWER_CONTROL_PANEL = BLOCKS.register("power_control_panel",\n            () -> new PowerControlPanelBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.5F, 8.0F)\n                    .requiresCorrectToolForDrops().sound(SoundType.METAL).lightLevel(state -> 2)));\n''')

replace_java("content/ModBlockEntities.java",
'''import dev.afterfall.blockentity.SealedPowerFeedthroughBlockEntity;\n''',
'''import dev.afterfall.blockentity.SealedPowerFeedthroughBlockEntity;\nimport dev.afterfall.blockentity.SmartPowerTapBlockEntity;\nimport dev.afterfall.blockentity.PowerControlPanelBlockEntity;\n''')
replace_java("content/ModBlockEntities.java",
'''    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<SealedPowerFeedthroughBlockEntity>> SEALED_POWER_FEEDTHROUGH =\n            BLOCK_ENTITY_TYPES.register("sealed_power_feedthrough", () -> BlockEntityType.Builder.of(\n                    SealedPowerFeedthroughBlockEntity::new, ModBlocks.SEALED_POWER_FEEDTHROUGH.get()).build(null));\n''',
'''    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<SealedPowerFeedthroughBlockEntity>> SEALED_POWER_FEEDTHROUGH =\n            BLOCK_ENTITY_TYPES.register("sealed_power_feedthrough", () -> BlockEntityType.Builder.of(\n                    SealedPowerFeedthroughBlockEntity::new, ModBlocks.SEALED_POWER_FEEDTHROUGH.get()).build(null));\n    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<SmartPowerTapBlockEntity>> SMART_POWER_TAP =\n            BLOCK_ENTITY_TYPES.register("smart_power_tap", () -> BlockEntityType.Builder.of(\n                    SmartPowerTapBlockEntity::new, ModBlocks.SMART_POWER_TAP.get()).build(null));\n    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<PowerControlPanelBlockEntity>> POWER_CONTROL_PANEL =\n            BLOCK_ENTITY_TYPES.register("power_control_panel", () -> BlockEntityType.Builder.of(\n                    PowerControlPanelBlockEntity::new, ModBlocks.POWER_CONTROL_PANEL.get()).build(null));\n''')

replace_java("content/ModItems.java",
'''    public static final DeferredItem<BlockItem> SEALED_POWER_FEEDTHROUGH = ITEMS.registerSimpleBlockItem("sealed_power_feedthrough", ModBlocks.SEALED_POWER_FEEDTHROUGH);\n''',
'''    public static final DeferredItem<BlockItem> SEALED_POWER_FEEDTHROUGH = ITEMS.registerSimpleBlockItem("sealed_power_feedthrough", ModBlocks.SEALED_POWER_FEEDTHROUGH);\n    public static final DeferredItem<BlockItem> SMART_POWER_TAP = ITEMS.registerSimpleBlockItem("smart_power_tap", ModBlocks.SMART_POWER_TAP);\n    public static final DeferredItem<BlockItem> POWER_CONTROL_PANEL = ITEMS.registerSimpleBlockItem("power_control_panel", ModBlocks.POWER_CONTROL_PANEL);\n''')

replace_java("content/ModCreativeTabs.java",
'''                        output.accept(ModItems.SEALED_POWER_FEEDTHROUGH.get());\n''',
'''                        output.accept(ModItems.SEALED_POWER_FEEDTHROUGH.get());\n                        output.accept(ModItems.SMART_POWER_TAP.get());\n                        output.accept(ModItems.POWER_CONTROL_PANEL.get());\n''')

replace_java("content/ModCapabilities.java",
'''        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.SEALED_POWER_FEEDTHROUGH.get(),\n                (be, side) -> be.energyStorage(side));\n''',
'''        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.SEALED_POWER_FEEDTHROUGH.get(),\n                (be, side) -> be.energyStorage(side));\n        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.SMART_POWER_TAP.get(),\n                (be, side) -> be.energyStorage(side));\n''')

replace_java("content/ModMenus.java",
'''import dev.afterfall.menu.MachineMenu;\n''',
'''import dev.afterfall.menu.MachineMenu;\nimport dev.afterfall.menu.SmartPowerTapMenu;\nimport dev.afterfall.menu.PowerControlPanelMenu;\n''')
replace_java("content/ModMenus.java",
'''    public static final DeferredHolder<MenuType<?>, MenuType<MachineMenu>> MACHINE = MENUS.register(\n            "machine",\n            () -> IMenuTypeExtension.create(MachineMenu::new)\n    );\n''',
'''    public static final DeferredHolder<MenuType<?>, MenuType<MachineMenu>> MACHINE = MENUS.register(\n            "machine",\n            () -> IMenuTypeExtension.create(MachineMenu::new)\n    );\n    public static final DeferredHolder<MenuType<?>, MenuType<SmartPowerTapMenu>> SMART_POWER_TAP = MENUS.register(\n            "smart_power_tap", () -> IMenuTypeExtension.create(SmartPowerTapMenu::new));\n    public static final DeferredHolder<MenuType<?>, MenuType<PowerControlPanelMenu>> POWER_CONTROL_PANEL = MENUS.register(\n            "power_control_panel", () -> IMenuTypeExtension.create(PowerControlPanelMenu::new));\n''')

replace_java("client/ClientModEvents.java",
'''        event.register(ModMenus.MACHINE.get(), MachineScreen::new);\n''',
'''        event.register(ModMenus.MACHINE.get(), MachineScreen::new);\n        event.register(ModMenus.SMART_POWER_TAP.get(), SmartPowerTapScreen::new);\n        event.register(ModMenus.POWER_CONTROL_PANEL.get(), PowerControlPanelScreen::new);\n''')

# Common right-click opening integration.
replace_java("event/CommonEvents.java",
'''import dev.afterfall.blockentity.EmergencyPowerBankBlockEntity;\n''',
'''import dev.afterfall.blockentity.EmergencyPowerBankBlockEntity;\nimport dev.afterfall.blockentity.SmartPowerTapBlockEntity;\nimport dev.afterfall.blockentity.PowerControlPanelBlockEntity;\n''')
replace_java("event/CommonEvents.java",
'''import dev.afterfall.menu.MachineMenu;\n''',
'''import dev.afterfall.menu.MachineMenu;\nimport dev.afterfall.menu.SmartPowerTapMenu;\nimport dev.afterfall.menu.PowerControlPanelMenu;\n''')
replace_java("event/CommonEvents.java",
'''        if (state.is(ModBlocks.EMERGENCY_POWER_BANK.get()) && event.getHand() == InteractionHand.MAIN_HAND) {\n''',
'''        if (state.is(ModBlocks.SMART_POWER_TAP.get()) && event.getHand() == InteractionHand.MAIN_HAND) {\n            event.setCancellationResult(InteractionResult.SUCCESS);\n            event.setCanceled(true);\n            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel\n                    && serverLevel.getBlockEntity(event.getPos()) instanceof SmartPowerTapBlockEntity tap) {\n                player.openMenu(new SimpleMenuProvider(\n                        (containerId, inventory, menuPlayer) -> new SmartPowerTapMenu(containerId, inventory, event.getPos(), tap),\n                        Component.literal("Smart Power Tap")),\n                        buffer -> { buffer.writeBlockPos(event.getPos()); buffer.writeUtf(tap.displayName(), 32); });\n            }\n            return;\n        }\n\n        if (state.is(ModBlocks.POWER_CONTROL_PANEL.get()) && event.getHand() == InteractionHand.MAIN_HAND) {\n            event.setCancellationResult(InteractionResult.SUCCESS);\n            event.setCanceled(true);\n            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel\n                    && serverLevel.getBlockEntity(event.getPos()) instanceof PowerControlPanelBlockEntity panel) {\n                player.openMenu(new SimpleMenuProvider(\n                        (containerId, inventory, menuPlayer) -> new PowerControlPanelMenu(containerId, inventory, event.getPos(), panel),\n                        Component.literal("Power Control Panel")),\n                        buffer -> buffer.writeBlockPos(event.getPos()));\n            }\n            return;\n        }\n\n        if (state.is(ModBlocks.EMERGENCY_POWER_BANK.get()) && event.getHand() == InteractionHand.MAIN_HAND) {\n''')

# Asset/data files.
write_res("assets/afterfall/blockstates/smart_power_tap.json", r'''{
  "variants": {
    "facing=north": {"model": "afterfall:block/smart_power_tap"},
    "facing=east":  {"model": "afterfall:block/smart_power_tap", "y": 90},
    "facing=south": {"model": "afterfall:block/smart_power_tap", "y": 180},
    "facing=west":  {"model": "afterfall:block/smart_power_tap", "y": 270},
    "facing=up":    {"model": "afterfall:block/smart_power_tap", "x": 270},
    "facing=down":  {"model": "afterfall:block/smart_power_tap", "x": 90}
  }
}
''')
write_res("assets/afterfall/models/block/smart_power_tap.json", r'''{
  "parent": "minecraft:block/orientable",
  "textures": {
    "top": "minecraft:block/iron_block",
    "front": "minecraft:block/observer_front",
    "side": "minecraft:block/smooth_stone"
  }
}
''')
write_res("assets/afterfall/models/item/smart_power_tap.json", r'''{
  "parent": "afterfall:block/smart_power_tap"
}
''')
write_res("data/afterfall/loot_table/blocks/smart_power_tap.json", r'''{
  "type": "minecraft:block",
  "pools": [{
    "rolls": 1,
    "entries": [{"type": "minecraft:item", "name": "afterfall:smart_power_tap"}],
    "conditions": [{"condition": "minecraft:survives_explosion"}]
  }]
}
''')

write_res("assets/afterfall/blockstates/power_control_panel.json", r'''{
  "variants": {
    "facing=north": {"model": "afterfall:block/power_control_panel"},
    "facing=east":  {"model": "afterfall:block/power_control_panel", "y": 90},
    "facing=south": {"model": "afterfall:block/power_control_panel", "y": 180},
    "facing=west":  {"model": "afterfall:block/power_control_panel", "y": 270}
  }
}
''')
write_res("assets/afterfall/models/block/power_control_panel.json", r'''{
  "parent": "minecraft:block/orientable",
  "textures": {
    "top": "minecraft:block/iron_block",
    "front": "minecraft:block/observer_front_on",
    "side": "minecraft:block/polished_deepslate"
  }
}
''')
write_res("assets/afterfall/models/item/power_control_panel.json", r'''{
  "parent": "afterfall:block/power_control_panel"
}
''')
write_res("data/afterfall/loot_table/blocks/power_control_panel.json", r'''{
  "type": "minecraft:block",
  "pools": [{
    "rolls": 1,
    "entries": [{"type": "minecraft:item", "name": "afterfall:power_control_panel"}],
    "conditions": [{"condition": "minecraft:survives_explosion"}]
  }]
}
''')

for lang, additions in {
    "en_us.json": {
        "block.afterfall.smart_power_tap": "Smart Power Tap",
        "block.afterfall.power_control_panel": "Power Control Panel"
    },
    "de_de.json": {
        "block.afterfall.smart_power_tap": "Intelligenter Stromabgriff",
        "block.afterfall.power_control_panel": "Bunker-Stromsteuerung"
    }
}.items():
    path = RES / "assets/afterfall/lang" / lang
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(additions)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("Applied Afterfall 0.9.2 Smart Power Distribution")
