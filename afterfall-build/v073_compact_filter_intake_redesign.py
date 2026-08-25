from pathlib import Path

ROOT = Path('Afterfall')
JAVA = ROOT / 'src/main/java/dev/afterfall'
RES = ROOT / 'src/main/resources'


def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'0.7.3 patch failed: {label} not found in {path}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


write('src/main/java/dev/afterfall/block/AirFilterBlock.java', r'''package dev.afterfall.block;

import dev.afterfall.blockentity.AirFilterBlockEntity;
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

/** Compact directional filter. FRONT/FACING is clean-air output, BACK is dirty-air input. */
public final class AirFilterBlock extends Block implements EntityBlock {
    public static final DirectionProperty FACING = BlockStateProperties.FACING;

    public AirFilterBlock(Properties properties) {
        super(properties);
        registerDefaultState(stateDefinition.any().setValue(FACING, Direction.NORTH));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        // Same convention as the fan: FRONT points toward the installer.
        return defaultBlockState().setValue(FACING, context.getNearestLookingDirection().getOpposite());
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(FACING);
    }

    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
        return new AirFilterBlockEntity(pos, state);
    }

    @Override
    @Nullable
    public <T extends BlockEntity> BlockEntityTicker<T> getTicker(Level level, BlockState state, BlockEntityType<T> type) {
        return level.isClientSide ? null : createTicker(type, ModBlockEntities.AIR_FILTER.get(), AirFilterBlockEntity::serverTick);
    }

    @SuppressWarnings("unchecked")
    private static <E extends BlockEntity, T extends BlockEntity> BlockEntityTicker<T> createTicker(
            BlockEntityType<T> actual, BlockEntityType<E> expected, BlockEntityTicker<? super E> ticker) {
        return actual == expected ? (BlockEntityTicker<T>) ticker : null;
    }
}
''')

write('src/main/java/dev/afterfall/blockentity/AirFilterBlockEntity.java', r'''package dev.afterfall.blockentity;

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
''')

write('src/main/java/dev/afterfall/blockentity/AirIntakeBlockEntity.java', r'''package dev.afterfall.blockentity;

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
''')

# Directional filtered transfer primitive.
room_atmos = JAVA / 'room/RoomAtmosphere.java'
replace_once(room_atmos,
'''    public void exchangeFrom(RoomAtmosphere source, double exchangeFraction) {
        if (source == null || source == this) return;
        double mix = Mth.clamp(exchangeFraction, 0.0D, 1.0D);
        dustPercent = Mth.lerp(mix, dustPercent, source.dustPercent);
        airborneRadiationPerSecond = Mth.lerp(mix, airborneRadiationPerSecond, source.airborneRadiationPerSecond);
        oxygenPercent = Mth.lerp(mix, oxygenPercent, source.oxygenPercent);
        co2Percent = Mth.lerp(mix, co2Percent, source.co2Percent);
    }
''',
'''    public void exchangeFrom(RoomAtmosphere source, double exchangeFraction) {
        if (source == null || source == this) return;
        double mix = Mth.clamp(exchangeFraction, 0.0D, 1.0D);
        dustPercent = Mth.lerp(mix, dustPercent, source.dustPercent);
        airborneRadiationPerSecond = Mth.lerp(mix, airborneRadiationPerSecond, source.airborneRadiationPerSecond);
        oxygenPercent = Mth.lerp(mix, oxygenPercent, source.oxygenPercent);
        co2Percent = Mth.lerp(mix, co2Percent, source.co2Percent);
    }

    /** Directional transfer with dust/radiological filtration applied before air enters this volume. */
    public void exchangeFilteredFrom(RoomAtmosphere source, double exchangeFraction,
                                     double dustEfficiency, double radiationEfficiency) {
        if (source == null || source == this) return;
        double mix = Mth.clamp(exchangeFraction, 0.0D, 1.0D);
        double filteredDust = source.dustPercent * (1.0D - Mth.clamp(dustEfficiency, 0.0D, 1.0D));
        double filteredRadiation = source.airborneRadiationPerSecond
                * (1.0D - Mth.clamp(radiationEfficiency, 0.0D, 1.0D));
        dustPercent = Mth.lerp(mix, dustPercent, filteredDust);
        airborneRadiationPerSecond = Mth.lerp(mix, airborneRadiationPerSecond, filteredRadiation);
        oxygenPercent = Mth.lerp(mix, oxygenPercent, source.oxygenPercent);
        co2Percent = Mth.lerp(mix, co2Percent, source.co2Percent);
    }
''', 'RoomAtmosphere filtered exchange primitive')

# Machine menu: intake has no cartridge slots; compact filter reports both sides.
menu = JAVA / 'menu/MachineMenu.java'
replace_once(menu, 'public static final int DATA_COUNT = 25;', 'public static final int DATA_COUNT = 28;', 'menu data count')
replace_once(menu,
'''    public static final int D_INTAKE_CAPACITY_X10 = 24;
''',
'''    public static final int D_INTAKE_CAPACITY_X10 = 24;
    public static final int D_INPUT_ROOM_VOLUME = 25;
    public static final int D_INPUT_DUST_X100 = 26;
    public static final int D_INPUT_AIR_RAD_X100 = 27;
''', 'menu directional filter data fields')
replace_once(menu,
'''        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1 : (machineType == TYPE_FAN ? 0 : 3);

        IItemHandler machineHandler = handlerFor(blockEntity, machineType);
        if (machineType == TYPE_GENERATOR) {
            addSlot(new SlotItemHandler(machineHandler, 0, FUEL_SLOT_X, FUEL_SLOT_Y));
        } else if (machineType != TYPE_FAN) {
            for (int i = 0; i < 3; i++) addSlot(new SlotItemHandler(machineHandler, i, FILTER_SLOT_X[i], FILTER_SLOT_Y));
        }
''',
'''        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1
                : ((machineType == TYPE_FAN || machineType == TYPE_INTAKE) ? 0 : 3);

        IItemHandler machineHandler = handlerFor(blockEntity, machineType);
        if (machineType == TYPE_GENERATOR) {
            addSlot(new SlotItemHandler(machineHandler, 0, FUEL_SLOT_X, FUEL_SLOT_Y));
        } else if (machineType == TYPE_FILTER || machineType == TYPE_AIRLOCK) {
            for (int i = 0; i < 3; i++) addSlot(new SlotItemHandler(machineHandler, i, FILTER_SLOT_X[i], FILTER_SLOT_Y));
        }
''', 'menu slot count')
replace_once(menu,
'''        if (blockEntity instanceof AirFilterBlockEntity be) return be.filters();
        if (blockEntity instanceof AirIntakeBlockEntity be) return be.filters();
        if (blockEntity instanceof AirlockControllerBlockEntity be) return be.filters();
        if (blockEntity instanceof EmergencyGeneratorBlockEntity be) return be.inventory();
        if (blockEntity instanceof VentilationFanBlockEntity) return new ItemStackHandler(0);
''',
'''        if (blockEntity instanceof AirFilterBlockEntity be) return be.filters();
        if (blockEntity instanceof AirIntakeBlockEntity) return new ItemStackHandler(0);
        if (blockEntity instanceof AirlockControllerBlockEntity be) return be.filters();
        if (blockEntity instanceof EmergencyGeneratorBlockEntity be) return be.inventory();
        if (blockEntity instanceof VentilationFanBlockEntity) return new ItemStackHandler(0);
''', 'menu intake handler')
replace_once(menu,
'''        if (type == TYPE_GENERATOR) {
            return new ItemStackHandler(1) {
''',
'''        if (type == TYPE_INTAKE || type == TYPE_FAN) return new ItemStackHandler(0);
        if (type == TYPE_GENERATOR) {
            return new ItemStackHandler(1) {
''', 'client fallback handler')

old_filter_menu = '''        if (serverBlockEntity instanceof AirFilterBlockEntity be) {
            data.set(D_TYPE, TYPE_FILTER);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_FLOW_X10, scale(AirFilterBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomScanResult scan = RoomMachineUtil.findSealedAdjacentRoom(level, blockPos);
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirFilterBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!be.filters().complete()) data.set(D_STATUS, 3);
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirFilterBlockEntity.isClean(atmosphere) ? 5 : 4);
                setAtmosphere(scan, atmosphere);
            }
            if (scan != null && get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }
'''
new_filter_menu = '''        if (serverBlockEntity instanceof AirFilterBlockEntity be) {
            data.set(D_TYPE, TYPE_FILTER);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_FLOW_X10, scale(AirFilterBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomScanResult input = be.inspectInput(level);
            RoomScanResult output = be.inspectOutput(level);
            RoomAtmosphere inputAir = input == null ? null : atmosphere(level, input);
            RoomAtmosphere outputAir = output == null ? null : atmosphere(level, output);
            if (input != null && inputAir != null) {
                data.set(D_INPUT_ROOM_VOLUME, input.volume());
                data.set(D_INPUT_DUST_X100, scale(inputAir.dustPercent(), 100.0D));
                data.set(D_INPUT_AIR_RAD_X100, scale(inputAir.airborneRadiationPerSecond() * 3600.0D, 100.0D));
            }
            if (output != null && outputAir != null) setAtmosphere(output, outputAir);

            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirFilterBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (input == null) data.set(D_STATUS, 34);
            else if (output == null) data.set(D_STATUS, 35);
            else if (input.anchor().equals(output.anchor())) data.set(D_STATUS, 36);
            else if (!be.filters().complete()) data.set(D_STATUS, 3);
            else data.set(D_STATUS, AirFilterBlockEntity.isClean(outputAir) ? 5 : 4);
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }
'''
replace_once(menu, old_filter_menu, new_filter_menu, 'directional compact filter menu')

old_intake_menu = '''        if (serverBlockEntity instanceof AirIntakeBlockEntity be) {
            data.set(D_TYPE, TYPE_INTAKE);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_FLOW_X10, scale(AirIntakeBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, blockPos);
            RoomScanResult scan = connection.room();
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirIntakeBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!be.filters().complete()) data.set(D_STATUS, 3);
            else if (!connection.outsideConnected()) data.set(D_STATUS, 6);
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirIntakeBlockEntity.needsFreshAir(atmosphere) ? 7 : 5);
                setAtmosphere(scan, atmosphere);
            }
            if (scan != null) {
                if (get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
                setIntakeStats(IntakeNetworkScanner.inspect(level, scan));
            }
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }
'''
new_intake_menu = '''        if (serverBlockEntity instanceof AirIntakeBlockEntity be) {
            data.set(D_TYPE, TYPE_INTAKE);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            data.set(D_PRE, scale(AirIntakeBlockEntity.PERMANENT_DUST_EFFICIENCY * 100.0D, 10.0D));
            data.set(D_RAD, scale(AirIntakeBlockEntity.PERMANENT_RADIATION_EFFICIENCY * 100.0D, 10.0D));
            data.set(D_FLOW_X10, scale(AirIntakeBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, blockPos);
            RoomScanResult scan = connection.room();
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirIntakeBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!connection.outsideConnected()) data.set(D_STATUS, 6);
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirIntakeBlockEntity.needsFreshAir(atmosphere) ? 7 : 5);
                setAtmosphere(scan, atmosphere);
            }
            if (scan != null) {
                if (get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
                setIntakeStats(IntakeNetworkScanner.inspect(level, scan));
            }
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }
'''
replace_once(menu, old_intake_menu, new_intake_menu, 'permanent intake menu')
replace_once(menu,
'''    public double intakeCapacity() { return get(D_INTAKE_CAPACITY_X10) / 10.0D; }
''',
'''    public double intakeCapacity() { return get(D_INTAKE_CAPACITY_X10) / 10.0D; }
    public int inputRoomVolume() { return get(D_INPUT_ROOM_VOLUME); }
    public double inputDustPercent() { return get(D_INPUT_DUST_X100) / 100.0D; }
    public double inputAirRadiation() { return get(D_INPUT_AIR_RAD_X100) / 100.0D; }
''', 'menu directional filter getters')
replace_once(menu,
'''            } else if (machineType != TYPE_GENERATOR && machineType != TYPE_FAN) {
''',
'''            } else if (machineType == TYPE_FILTER || machineType == TYPE_AIRLOCK) {
''', 'quick move excludes intake')

# GUI: no cartridge slots for intake; dedicated intake panel; directional compact-filter diagnostics.
screen = JAVA / 'client/MachineScreen.java'
replace_once(screen,
'''        } else if (menu.machineType() != MachineMenu.TYPE_FAN) {
            for (int i = 0; i < 3; i++) drawSlotBox(graphics, x + MachineMenu.FILTER_SLOT_X[i], y + MachineMenu.FILTER_SLOT_Y);
            drawFilterBar(graphics, x + 12, y + 116, 60, menu.prePercent());
            drawFilterBar(graphics, x + 92, y + 116, 60, menu.hepaPercent());
            drawFilterBar(graphics, x + 172, y + 116, 60, menu.radPercent());
        }
''',
'''        } else if (menu.machineType() == MachineMenu.TYPE_FILTER || menu.machineType() == MachineMenu.TYPE_AIRLOCK) {
            for (int i = 0; i < 3; i++) drawSlotBox(graphics, x + MachineMenu.FILTER_SLOT_X[i], y + MachineMenu.FILTER_SLOT_Y);
            drawFilterBar(graphics, x + 12, y + 116, 60, menu.prePercent());
            drawFilterBar(graphics, x + 92, y + 116, 60, menu.hepaPercent());
            drawFilterBar(graphics, x + 172, y + 116, 60, menu.radPercent());
        }
''', 'screen intake slots')
replace_once(screen,
'''        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            renderGenerator(graphics);
        } else if (menu.machineType() == MachineMenu.TYPE_FAN) {
            renderFan(graphics);
        } else {
            renderFilters(graphics);
        }
''',
'''        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            renderGenerator(graphics);
        } else if (menu.machineType() == MachineMenu.TYPE_FAN) {
            renderFan(graphics);
        } else if (menu.machineType() == MachineMenu.TYPE_INTAKE) {
            renderIntake(graphics);
        } else {
            renderFilters(graphics);
        }
''', 'screen intake renderer selection')

start = screen.read_text(encoding='utf-8').index('    private void renderFilters(GuiGraphics graphics) {')
end = screen.read_text(encoding='utf-8').index('    private void renderFan(GuiGraphics graphics) {')
text = screen.read_text(encoding='utf-8')
replacement = r'''    private void renderFilters(GuiGraphics graphics) {
        graphics.drawString(font, "Pre-Filter", 12, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, "HEPA", 92, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, "RAD", 172, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.prePercent()), 12, 126, filterColor(menu.prePercent()), false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.hepaPercent()), 92, 126, filterColor(menu.hepaPercent()), false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.radPercent()), 172, 126, filterColor(menu.radPercent()), false);
        graphics.drawString(font, "Filter condition: " + filterCondition(), 12, 140, filterConditionColor(), false);

        if (menu.machineType() == MachineMenu.TYPE_FILTER) {
            graphics.drawString(font, String.format(Locale.ROOT, "BACK input: %d m³ | Dust %.2f%%",
                    menu.inputRoomVolume(), menu.inputDustPercent()), 12, 154, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Input Air Rad: %.2f mSv/h", menu.inputAirRadiation()),
                    12, 167, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "FRONT output: %d m³ | Air %.1f%%",
                    menu.get(MachineMenu.D_ROOM_VOLUME), menu.airQuality()), 12, 180, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust %.2f%% | Rad %.2f | Flow %.1f m³/s",
                    menu.dustPercent(), menu.airRadiation(), menu.flow()), 12, 193, 0xFF9DB7BD, false);
            return;
        }

        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        if (volume > 0) {
            graphics.drawString(font, "Room: " + volume + " m³", 12, 155, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 124, 155, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 12, 168, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 124, 168, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%%", menu.oxygenPercent()), 12, 181, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "CO2: %.2f%%", menu.co2Percent()), 124, 181, 0xFFD3DDDF, false);
        }
        graphics.drawString(font, "Cycle: " + airlockCycle(), 12, 194, 0xFF7F9298, false);
    }

    private void renderIntake(GuiGraphics graphics) {
        graphics.drawString(font, "Permanent outside-air pre-cleaner", 12, 88, 0xFFAAB6B9, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Dust removal %.0f%% | Rad aerosol %.0f%%",
                menu.prePercent(), menu.radPercent()), 12, 103, 0xFF9DB7BD, false);
        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        graphics.drawString(font, "Mixing room: " + volume + " m³", 12, 121, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 124, 121, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 12, 136, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 124, 136, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%% | CO2: %.2f%%", menu.oxygenPercent(), menu.co2Percent()),
                12, 151, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Network %d/%d ready | Fresh %.1f/%.1f m³/s",
                menu.intakeReady(), menu.intakeTotal(), menu.intakeInput(), menu.intakeCapacity()),
                12, 174, 0xFF9DB7BD, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Rated fresh-air flow: %.1f m³/s", menu.flow()),
                12, 193, 0xFF7F9298, false);
    }

'''
screen.write_text(text[:start] + replacement + text[end:], encoding='utf-8')
replace_once(screen,
'''            case 33 -> "ERROR - NO SEALED INLET";
''',
'''            case 33 -> "ERROR - NO SEALED INLET";
            case 34 -> "ERROR - NO SEALED BACK INPUT";
            case 35 -> "ERROR - NO SEALED FRONT OUTPUT";
            case 36 -> "ERROR - INPUT = OUTPUT VOLUME";
''', 'screen compact filter statuses')
replace_once(screen,
'''            default -> "AFTERFALL // AIR FILTRATION UNIT";
''',
'''            default -> "AFTERFALL // COMPACT AIR FILTRATION UNIT";
''', 'compact filter title')

# Intake no longer accepts cartridges by interaction.
events = JAVA / 'event/CommonEvents.java'
old_intake_event = '''        if (state.is(ModBlocks.AIR_INTAKE_UNIT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof AirIntakeBlockEntity intake && isFilterCartridge(player.getMainHandItem())) {
                    if (intake.installFilter(player, player.getMainHandItem())) {
                        player.displayClientMessage(Component.literal("Air Intake: cartridge installed | " + intake.filters().compactStatus())
                                .withStyle(ChatFormatting.GREEN), true);
                    }
                } else if (blockEntity instanceof AirIntakeBlockEntity intake) {
                    openMachineMenu(player, event.getPos(), intake, Component.literal("Air Intake Unit"));
                }
            }
            return;
        }
'''
new_intake_event = '''        if (state.is(ModBlocks.AIR_INTAKE_UNIT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof AirIntakeBlockEntity intake) {
                    openMachineMenu(player, event.getPos(), intake, Component.literal("Air Intake Unit"));
                }
            }
            return;
        }
'''
replace_once(events, old_intake_event, new_intake_event, 'intake interaction')

# Six-axis blockstate for compact filter (NORTH model is FRONT).
write('src/main/resources/assets/afterfall/blockstates/air_filter_unit.json', r'''{
  "variants": {
    "facing=north": {"model": "afterfall:block/air_filter_unit", "uvlock": true},
    "facing=east":  {"model": "afterfall:block/air_filter_unit", "uvlock": true, "y": 90},
    "facing=south": {"model": "afterfall:block/air_filter_unit", "uvlock": true, "y": 180},
    "facing=west":  {"model": "afterfall:block/air_filter_unit", "uvlock": true, "y": 270},
    "facing=up":    {"model": "afterfall:block/air_filter_unit", "uvlock": true, "x": 270},
    "facing=down":  {"model": "afterfall:block/air_filter_unit", "uvlock": true, "x": 90}
  }
}
''')

# Version markers.
gradle = ROOT / 'gradle.properties'
replace_once(gradle, 'mod_version=0.7.2.3', 'mod_version=0.7.3', 'gradle version')
afterfall = JAVA / 'Afterfall.java'
replace_once(afterfall, 'Afterfall 0.7.2.3 initialized', 'Afterfall 0.7.3 initialized', 'startup version')

print('Afterfall 0.7.3 compact filter + permanent intake redesign applied')
