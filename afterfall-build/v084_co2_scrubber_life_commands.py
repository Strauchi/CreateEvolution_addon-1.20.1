from pathlib import Path
import json

root = Path('Afterfall')
src = root / 'src/main/java/dev/afterfall'
res = root / 'src/main/resources'


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'Pattern not found in {path}: {old[:240]!r}')
    path.write_text(text.replace(old, new, 1))


def replace_all(path: Path, old: str, new: str, expected: int):
    text = path.read_text()
    count = text.count(old)
    if count != expected:
        raise SystemExit(f'Expected {expected} occurrence(s) in {path}, found {count}: {old[:220]!r}')
    path.write_text(text.replace(old, new))


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
replace_once(root / 'gradle.properties', 'mod_version=0.8.3.1', 'mod_version=0.8.4')
replace_once(src / 'Afterfall.java', 'Afterfall 0.8.3.1 initialized', 'Afterfall 0.8.4 initialized')


# -----------------------------------------------------------------------------
# CO2 Scrubber block + block entity.
# FRONT/FACING = treated-air output, BACK = return-air input. The machine does
# not move air by itself; AirTreatmentNetwork processes it only while the Main
# Fan is pulling through the sealed treatment path.
# -----------------------------------------------------------------------------
write(src / 'block/Co2ScrubberBlock.java', '''package dev.afterfall.block;

import dev.afterfall.blockentity.Co2ScrubberBlockEntity;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.EntityBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DirectionProperty;

/** Directional powered CO2 treatment edge. FRONT/FACING is treated-air output. */
public final class Co2ScrubberBlock extends Block implements EntityBlock {
    public static final DirectionProperty FACING = BlockStateProperties.FACING;

    public Co2ScrubberBlock(Properties properties) {
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
        return new Co2ScrubberBlockEntity(pos, state);
    }
}
''')

write(src / 'blockentity/Co2ScrubberBlockEntity.java', '''package dev.afterfall.blockentity;

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
''')


# -----------------------------------------------------------------------------
# Registries and FE capability.
# -----------------------------------------------------------------------------
blocks = src / 'content/ModBlocks.java'
replace_once(blocks,
'''import dev.afterfall.block.AirlockControllerBlock;
import dev.afterfall.block.EmergencyGeneratorBlock;''',
'''import dev.afterfall.block.AirlockControllerBlock;
import dev.afterfall.block.Co2ScrubberBlock;
import dev.afterfall.block.EmergencyGeneratorBlock;''')
replace_once(blocks,
'''    public static final DeferredBlock<AirIntakeBlock> AIR_INTAKE_UNIT = BLOCKS.register("air_intake_unit",
            () -> new AirIntakeBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.0F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));
    public static final DeferredBlock<AirlockControllerBlock> AIRLOCK_CONTROLLER''',
'''    public static final DeferredBlock<AirIntakeBlock> AIR_INTAKE_UNIT = BLOCKS.register("air_intake_unit",
            () -> new AirIntakeBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.0F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));
    public static final DeferredBlock<Co2ScrubberBlock> CO2_SCRUBBER = BLOCKS.register("co2_scrubber",
            () -> new Co2ScrubberBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));
    public static final DeferredBlock<AirlockControllerBlock> AIRLOCK_CONTROLLER''')

items = src / 'content/ModItems.java'
replace_once(items,
'''    public static final DeferredItem<BlockItem> AIR_FILTER_UNIT = ITEMS.registerSimpleBlockItem("air_filter_unit", ModBlocks.AIR_FILTER_UNIT);
    public static final DeferredItem<BlockItem> AIR_INTAKE_UNIT''',
'''    public static final DeferredItem<BlockItem> AIR_FILTER_UNIT = ITEMS.registerSimpleBlockItem("air_filter_unit", ModBlocks.AIR_FILTER_UNIT);
    public static final DeferredItem<BlockItem> CO2_SCRUBBER = ITEMS.registerSimpleBlockItem("co2_scrubber", ModBlocks.CO2_SCRUBBER);
    public static final DeferredItem<BlockItem> AIR_INTAKE_UNIT''')

creative = src / 'content/ModCreativeTabs.java'
replace_once(creative,
'''                        output.accept(ModItems.AIR_FILTER_UNIT.get());
                        output.accept(ModItems.AIR_INTAKE_UNIT.get());''',
'''                        output.accept(ModItems.AIR_FILTER_UNIT.get());
                        output.accept(ModItems.CO2_SCRUBBER.get());
                        output.accept(ModItems.AIR_INTAKE_UNIT.get());''')

block_entities = src / 'content/ModBlockEntities.java'
replace_once(block_entities,
'''import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;''',
'''import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.Co2ScrubberBlockEntity;
import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;''')
replace_once(block_entities,
'''    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<AirIntakeBlockEntity>> AIR_INTAKE =
            BLOCK_ENTITY_TYPES.register("air_intake", () -> BlockEntityType.Builder.of(
                    AirIntakeBlockEntity::new, ModBlocks.AIR_INTAKE_UNIT.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<AirlockControllerBlockEntity>> AIRLOCK_CONTROLLER''',
'''    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<AirIntakeBlockEntity>> AIR_INTAKE =
            BLOCK_ENTITY_TYPES.register("air_intake", () -> BlockEntityType.Builder.of(
                    AirIntakeBlockEntity::new, ModBlocks.AIR_INTAKE_UNIT.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<Co2ScrubberBlockEntity>> CO2_SCRUBBER =
            BLOCK_ENTITY_TYPES.register("co2_scrubber", () -> BlockEntityType.Builder.of(
                    Co2ScrubberBlockEntity::new, ModBlocks.CO2_SCRUBBER.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<AirlockControllerBlockEntity>> AIRLOCK_CONTROLLER''')

capabilities = src / 'content/ModCapabilities.java'
replace_once(capabilities,
'''        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.AIR_INTAKE.get(),
                (be, side) -> be.energyStorage());
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.AIRLOCK_CONTROLLER.get(),''',
'''        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.AIR_INTAKE.get(),
                (be, side) -> be.energyStorage());
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.CO2_SCRUBBER.get(),
                (be, side) -> be.energyStorage());
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.AIRLOCK_CONTROLLER.get(),''')


# -----------------------------------------------------------------------------
# Room atmosphere: technical scrubbing removes CO2 without generating O2.
# Capacity is expressed in the same player-equivalent basis as respiration.
# -----------------------------------------------------------------------------
atmosphere = src / 'room/RoomAtmosphere.java'
replace_once(atmosphere,
'''    public void tickPassive(long gameTime) {''',
'''    /**
     * Technical CO2 removal. One player-equivalent removes exactly the CO2 that
     * one resident produces in the gameplay respiration model. No oxygen is made.
     *
     * @return CO2 percentage points removed from this room
     */
    public double scrubCarbonDioxide(double playerEquivalentCapacity, double seconds) {
        double capacity = Math.max(0.0D, playerEquivalentCapacity);
        double duration = Math.max(0.0D, seconds);
        if (capacity <= 0.0D || duration <= 0.0D) return 0.0D;

        double desiredRemoval = 0.11D * capacity * duration / Math.max(1.0D, volume);
        double availableCo2 = Math.max(0.0D, co2Percent - NORMAL_CO2);
        double removedCo2 = Math.min(desiredRemoval, availableCo2);
        if (removedCo2 <= 0.0D) return 0.0D;
        co2Percent = Math.max(NORMAL_CO2, co2Percent - removedCo2);
        return removedCo2;
    }

    public void tickPassive(long gameTime) {''')


# -----------------------------------------------------------------------------
# Fan-driven treatment network: directional scrubbers become real airflow edges.
# They are airtight to RoomScanner, have a finite 18 m3/s per-block capacity and
# only remove CO2 when their block entity has power. Unpowered units still permit
# the Main Fan to move air through the duct stage, but provide no treatment.
# -----------------------------------------------------------------------------
treatment = src / 'room/AirTreatmentNetwork.java'
replace_once(treatment,
'''import dev.afterfall.block.AirFilterBlock;
import dev.afterfall.blockentity.AirFilterBlockEntity;''',
'''import dev.afterfall.block.AirFilterBlock;
import dev.afterfall.block.Co2ScrubberBlock;
import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.Co2ScrubberBlockEntity;''')

replace_once(treatment,
'''        List<IndustrialStage> industrialStages = new ArrayList<>();
        List<TransferStage> transferStages = new ArrayList<>();
        Set<Long> visited = new HashSet<>();
        walk(level, fanInlet, 0, visited, rooms, industrialStages, transferStages);''',
'''        List<IndustrialStage> industrialStages = new ArrayList<>();
        List<TransferStage> transferStages = new ArrayList<>();
        List<ScrubberStage> scrubberStages = new ArrayList<>();
        Set<Long> visited = new HashSet<>();
        walk(level, fanInlet, 0, visited, rooms, industrialStages, transferStages, scrubberStages);''')

replace_once(treatment,
'''        if (transferStages.isEmpty()) transferBottleneck = 0.0D;

        return new Network(List.copyOf(rooms.values()), List.copyOf(industrialStages),
                List.copyOf(transferStages), pre, hepa, rad, transferVents,
                industrialBottleneck, transferBottleneck);''',
'''        if (transferStages.isEmpty()) transferBottleneck = 0.0D;

        int scrubbers = 0;
        double scrubberBottleneck = Double.POSITIVE_INFINITY;
        for (ScrubberStage stage : scrubberStages) {
            scrubbers += stage.scrubberPositions().size();
            scrubberBottleneck = Math.min(scrubberBottleneck, stage.capacity());
        }
        if (scrubberStages.isEmpty()) scrubberBottleneck = 0.0D;

        return new Network(List.copyOf(rooms.values()), List.copyOf(industrialStages),
                List.copyOf(transferStages), List.copyOf(scrubberStages), pre, hepa, rad,
                transferVents, scrubbers, industrialBottleneck, transferBottleneck,
                scrubberBottleneck);''')

replace_once(treatment,
'''    /**
     * Moves atmosphere through passive treatment edges while a powered main fan is
     * running. Deepest/upstream edges are processed first so a serial path such as''',
'''    /** Downstream-facing scrubber diagnostics for the current sealed room. */
    public static ScrubberDiagnostics inspectScrubbers(ServerLevel level, RoomScanResult room) {
        if (!validRoom(level, room)) return ScrubberDiagnostics.EMPTY;
        Boundary boundary = scanBoundary(level, room);
        int units = 0;
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
    }

    /**
     * Moves atmosphere through passive treatment edges while a powered main fan is
     * running. Deepest/upstream edges are processed first so a serial path such as''')

replace_once(treatment,
'''            for (IndustrialStage stage : network.industrialStages()) {''',
'''            for (ScrubberStage stage : network.scrubberStages()) {
                if (stage.depth() != depth) continue;
                double flow = Math.min(requestedFlow, stage.capacity());
                if (flow <= 0.0D || stage.scrubberPositions().isEmpty()) continue;

                RoomAtmosphere source = atmosphere(level, stage.upstream());
                RoomAtmosphere destination = atmosphere(level, stage.downstream());
                double fraction = Math.min(0.35D,
                        flow / Math.max(1.0D, stage.downstream().volume()));
                destination.exchangeFrom(source, fraction);

                double perUnitFlow = Math.min(Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND,
                        flow / Math.max(1, stage.scrubberPositions().size()));
                for (BlockPos scrubberPos : stage.scrubberPositions()) {
                    if (level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber) {
                        scrubber.processScrubbing(level, destination, stage.downstream(), perUnitFlow);
                    }
                }
                changed = true;
            }

            for (IndustrialStage stage : network.industrialStages()) {''')

replace_once(treatment,
'''    private static void walk(ServerLevel level, RoomScanResult downstream, int depth,
                             Set<Long> visited, Map<Long, RoomScanResult> rooms,
                             List<IndustrialStage> industrialStages,
                             List<TransferStage> transferStages) {''',
'''    private static void walk(ServerLevel level, RoomScanResult downstream, int depth,
                             Set<Long> visited, Map<Long, RoomScanResult> rooms,
                             List<IndustrialStage> industrialStages,
                             List<TransferStage> transferStages,
                             List<ScrubberStage> scrubberStages) {''')

replace_all(treatment,
'''            walk(level, input, depth + 1, visited, rooms, industrialStages, transferStages);''',
'''            walk(level, input, depth + 1, visited, rooms, industrialStages, transferStages, scrubberStages);''', 1)
replace_all(treatment,
'''            walk(level, upstream, depth + 1, visited, rooms, industrialStages, transferStages);''',
'''            walk(level, upstream, depth + 1, visited, rooms, industrialStages, transferStages, scrubberStages);''', 2)

replace_once(treatment,
'''        // Passive industrial wall: direction is inferred from distance to the fan.
        for (Bank bank : boundary.banks().values()) {''',
'''        // Powered directional CO2 scrubber. Current room must be its FRONT/output;
        // the room behind the block is traced farther upstream toward RETURN air.
        for (ScrubberBank bank : boundary.scrubberBanks().values()) {
            RoomScanResult upstream = bank.otherRoom();
            if (upstream == null || upstream.anchor().asLong() == downstreamAnchor
                    || visited.contains(upstream.anchor().asLong())) continue;

            ScrubberStage stage = bank.toStage(upstream, downstream, depth);
            if (stage.capacity() <= 0.0D) continue;
            scrubberStages.add(stage);
            walk(level, upstream, depth + 1, visited, rooms, industrialStages, transferStages, scrubberStages);
        }

        // Passive industrial wall: direction is inferred from distance to the fan.
        for (Bank bank : boundary.banks().values()) {''')

replace_once(treatment,
'''        Set<Long> compactFilters = new HashSet<>();
        Set<Long> inspectedTransferVents = new HashSet<>();
        Map<Long, BankBuilder> builders = new LinkedHashMap<>();
        Map<Long, TransferBankBuilder> transferBuilders = new LinkedHashMap<>();''',
'''        Set<Long> compactFilters = new HashSet<>();
        Set<Long> inspectedTransferVents = new HashSet<>();
        Map<Long, BankBuilder> builders = new LinkedHashMap<>();
        Map<Long, TransferBankBuilder> transferBuilders = new LinkedHashMap<>();
        Map<Long, ScrubberBankBuilder> scrubberBuilders = new LinkedHashMap<>();''')

replace_once(treatment,
'''                if (state.is(ModBlocks.TRANSFER_VENT.get())) {''',
'''                if (state.is(ModBlocks.CO2_SCRUBBER.get())) {
                    if (!state.hasProperty(Co2ScrubberBlock.FACING)) continue;
                    Direction facing = state.getValue(Co2ScrubberBlock.FACING);
                    // The current/downstream room must touch the scrubber FRONT.
                    if (!next.relative(facing).equals(current)) continue;
                    BlockPos farSide = next.relative(facing.getOpposite());
                    if (!RoomScanner.airCanPass(level, farSide)) continue;
                    RoomScanResult other = RoomScanner.scan(level, farSide);
                    if (!other.sealed() || other.anchor().equals(room.anchor())) continue;

                    long otherAnchor = other.anchor().asLong();
                    scrubberBuilders.computeIfAbsent(otherAnchor,
                            ignored -> new ScrubberBankBuilder(other)).add(next);
                    continue;
                }

                if (state.is(ModBlocks.TRANSFER_VENT.get())) {''')

replace_once(treatment,
'''        Map<Long, TransferBank> transferBanks = new LinkedHashMap<>();
        for (Map.Entry<Long, TransferBankBuilder> entry : transferBuilders.entrySet()) {
            transferBanks.put(entry.getKey(), entry.getValue().build());
        }
        return new Boundary(compactFilters, banks, transferBanks);''',
'''        Map<Long, TransferBank> transferBanks = new LinkedHashMap<>();
        for (Map.Entry<Long, TransferBankBuilder> entry : transferBuilders.entrySet()) {
            transferBanks.put(entry.getKey(), entry.getValue().build());
        }
        Map<Long, ScrubberBank> scrubberBanks = new LinkedHashMap<>();
        for (Map.Entry<Long, ScrubberBankBuilder> entry : scrubberBuilders.entrySet()) {
            scrubberBanks.put(entry.getKey(), entry.getValue().build());
        }
        return new Boundary(compactFilters, banks, transferBanks, scrubberBanks);''')

replace_once(treatment,
'''    public record TransferDiagnostics(int connectedRooms, int ventCount,
                                      double totalCapacity, double maxOxygenDelta,
                                      double maxCo2Delta) {
        public static final TransferDiagnostics EMPTY =
                new TransferDiagnostics(0, 0, 0.0D, 0.0D, 0.0D);
    }

    public enum FilterType {''',
'''    public record TransferDiagnostics(int connectedRooms, int ventCount,
                                      double totalCapacity, double maxOxygenDelta,
                                      double maxCo2Delta) {
        public static final TransferDiagnostics EMPTY =
                new TransferDiagnostics(0, 0, 0.0D, 0.0D, 0.0D);
    }

    public record ScrubberDiagnostics(int units, int readyUnits, int activeUnits,
                                      double flowCapacity, double nominalPlayerEquivalent,
                                      double actualPlayerEquivalent, double co2RemovedPerSecond) {
        public static final ScrubberDiagnostics EMPTY =
                new ScrubberDiagnostics(0, 0, 0, 0.0D, 0.0D, 0.0D, 0.0D);
    }

    public enum FilterType {''')

replace_once(treatment,
'''    private static final class TransferBankBuilder {
        private final RoomScanResult otherRoom;
        private final Set<Long> vents = new HashSet<>();

        private TransferBankBuilder(RoomScanResult otherRoom) {
            this.otherRoom = otherRoom;
        }

        private void add(BlockPos pos) {
            vents.add(pos.asLong());
        }

        private TransferBank build() {
            return new TransferBank(otherRoom, vents.size());
        }
    }

    private record Boundary(Set<Long> compactFilters, Map<Long, Bank> banks,
                            Map<Long, TransferBank> transferBanks) {}''',
'''    private static final class TransferBankBuilder {
        private final RoomScanResult otherRoom;
        private final Set<Long> vents = new HashSet<>();

        private TransferBankBuilder(RoomScanResult otherRoom) {
            this.otherRoom = otherRoom;
        }

        private void add(BlockPos pos) {
            vents.add(pos.asLong());
        }

        private TransferBank build() {
            return new TransferBank(otherRoom, vents.size());
        }
    }

    private static final class ScrubberBankBuilder {
        private final RoomScanResult otherRoom;
        private final Set<Long> scrubbers = new HashSet<>();

        private ScrubberBankBuilder(RoomScanResult otherRoom) {
            this.otherRoom = otherRoom;
        }

        private void add(BlockPos pos) {
            scrubbers.add(pos.asLong());
        }

        private ScrubberBank build() {
            List<BlockPos> positions = scrubbers.stream().map(BlockPos::of).toList();
            return new ScrubberBank(otherRoom, positions);
        }
    }

    private record Boundary(Set<Long> compactFilters, Map<Long, Bank> banks,
                            Map<Long, TransferBank> transferBanks,
                            Map<Long, ScrubberBank> scrubberBanks) {}''')

replace_once(treatment,
'''    private record TransferBank(RoomScanResult otherRoom, int ventCount) {
        private TransferStage toStage(RoomScanResult upstream, RoomScanResult downstream, int depth) {
            return new TransferStage(upstream, downstream, ventCount,
                    ventCount * TRANSFER_CAPACITY_PER_BLOCK, depth);
        }
    }

    public record IndustrialStage''',
'''    private record TransferBank(RoomScanResult otherRoom, int ventCount) {
        private TransferStage toStage(RoomScanResult upstream, RoomScanResult downstream, int depth) {
            return new TransferStage(upstream, downstream, ventCount,
                    ventCount * TRANSFER_CAPACITY_PER_BLOCK, depth);
        }
    }

    private record ScrubberBank(RoomScanResult otherRoom, List<BlockPos> scrubberPositions) {
        private ScrubberStage toStage(RoomScanResult upstream, RoomScanResult downstream, int depth) {
            return new ScrubberStage(upstream, downstream, scrubberPositions,
                    scrubberPositions.size() * Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND, depth);
        }
    }

    public record IndustrialStage''')

replace_once(treatment,
'''    public record TransferStage(RoomScanResult upstream, RoomScanResult downstream,
                                int ventCount, double capacity, int depth) {}

    public record TransferConnection''',
'''    public record TransferStage(RoomScanResult upstream, RoomScanResult downstream,
                                int ventCount, double capacity, int depth) {}

    public record ScrubberStage(RoomScanResult upstream, RoomScanResult downstream,
                                List<BlockPos> scrubberPositions, double capacity, int depth) {}

    public record TransferConnection''')

replace_once(treatment,
'''    public record Network(List<RoomScanResult> rooms, List<IndustrialStage> industrialStages,
                          List<TransferStage> transferStages,
                          int preBlocks, int hepaBlocks, int radBlocks, int transferVentCount,
                          double bottleneckCapacity, double transferBottleneckCapacity) {
        public static final Network EMPTY = new Network(List.of(), List.of(), List.of(),
                0, 0, 0, 0, 0.0D, 0.0D);

        public boolean hasIndustrialStages() { return !industrialStages.isEmpty(); }
        public boolean hasTransferStages() { return !transferStages.isEmpty(); }

        /** Minimum passive capacity in the traced serial treatment path. */
        public double passiveBottleneckCapacity() {
            double cap = Double.POSITIVE_INFINITY;
            if (hasIndustrialStages() && bottleneckCapacity > 0.0D) cap = Math.min(cap, bottleneckCapacity);
            if (hasTransferStages() && transferBottleneckCapacity > 0.0D) cap = Math.min(cap, transferBottleneckCapacity);
            return Double.isFinite(cap) ? cap : 0.0D;
        }
    }''',
'''    public record Network(List<RoomScanResult> rooms, List<IndustrialStage> industrialStages,
                          List<TransferStage> transferStages, List<ScrubberStage> scrubberStages,
                          int preBlocks, int hepaBlocks, int radBlocks, int transferVentCount,
                          int scrubberCount, double bottleneckCapacity,
                          double transferBottleneckCapacity, double scrubberBottleneckCapacity) {
        public static final Network EMPTY = new Network(List.of(), List.of(), List.of(), List.of(),
                0, 0, 0, 0, 0, 0.0D, 0.0D, 0.0D);

        public boolean hasIndustrialStages() { return !industrialStages.isEmpty(); }
        public boolean hasTransferStages() { return !transferStages.isEmpty(); }
        public boolean hasScrubberStages() { return !scrubberStages.isEmpty(); }

        /** Minimum airflow capacity in the traced serial treatment path. */
        public double passiveBottleneckCapacity() {
            double cap = Double.POSITIVE_INFINITY;
            if (hasIndustrialStages() && bottleneckCapacity > 0.0D) cap = Math.min(cap, bottleneckCapacity);
            if (hasTransferStages() && transferBottleneckCapacity > 0.0D) cap = Math.min(cap, transferBottleneckCapacity);
            if (hasScrubberStages() && scrubberBottleneckCapacity > 0.0D) cap = Math.min(cap, scrubberBottleneckCapacity);
            return Double.isFinite(cap) ? cap : 0.0D;
        }
    }''')


# -----------------------------------------------------------------------------
# Interaction: normal right-click reports scrubber status; sneak-right-click
# toggles it. No GUI or consumable is introduced in 0.8.4.
# -----------------------------------------------------------------------------
events = src / 'event/CommonEvents.java'
replace_once(events,
'''import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.AirlockLogic;''',
'''import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.AirlockLogic;
import dev.afterfall.blockentity.Co2ScrubberBlockEntity;''')
replace_once(events,
'''        if (state.is(ModBlocks.AIR_FILTER_UNIT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {''',
'''        if (state.is(ModBlocks.CO2_SCRUBBER.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel
                    && serverLevel.getBlockEntity(event.getPos()) instanceof Co2ScrubberBlockEntity scrubber) {
                if (player.isShiftKeyDown()) {
                    scrubber.setEnabled(!scrubber.enabled());
                    player.displayClientMessage(Component.literal("CO2 SCRUBBER: "
                            + (scrubber.enabled() ? "ENABLED" : "DISABLED"))
                            .withStyle(scrubber.enabled() ? ChatFormatting.GREEN : ChatFormatting.GRAY), true);
                } else {
                    player.displayClientMessage(Co2ScrubberBlockEntity.status(serverLevel, event.getPos()), true);
                }
            }
            return;
        }

        if (state.is(ModBlocks.AIR_FILTER_UNIT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {''')


# -----------------------------------------------------------------------------
# Commands: /af room info returns room/environment data only. Detailed life
# support diagnostics move to /af life and /af life info.
# -----------------------------------------------------------------------------
commands = src / 'command/AfterfallCommands.java'
replace_once(commands,
'''                        .then(roomCommands())
                        .then(playerCommands())''',
'''                        .then(roomCommands())
                        .then(lifeCommands())
                        .then(playerCommands())''')

replace_once(commands,
'''    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<CommandSourceStack> roomScalar(''',
'''    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<CommandSourceStack> lifeCommands() {
        return Commands.literal("life")
                .executes(ctx -> lifeInfo(ctx.getSource()))
                .then(Commands.literal("info").executes(ctx -> lifeInfo(ctx.getSource())));
    }

    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<CommandSourceStack> roomScalar(''')

replace_once(commands,
'''        source.sendSuccess(() -> Component.literal("/af room info | clean | wasteland | simulate <players> <seconds>"), false);
        source.sendSuccess(() -> Component.literal("/af room set <dust|rad|o2|co2> <value> | set all <dust> <rad mSv/h> <o2> <co2>"), false);''',
'''        source.sendSuccess(() -> Component.literal("/af room info | clean | wasteland | simulate <players> <seconds>"), false);
        source.sendSuccess(() -> Component.literal("/af life [info] - detailed life-support / ventilation diagnostics"), false);
        source.sendSuccess(() -> Component.literal("/af room set <dust|rad|o2|co2> <value> | set all <dust> <rad mSv/h> <o2> <co2>"), false);''')

old_room_info = '''    private static int roomInfo(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;

        double radHour = room.air.airborneRadiationPerSecond() * 3600.0D;
        double demand = AirIntakeBlockEntity.freshAirDemandM3PerSecond(room.air);
        BiologicalAirManager.Snapshot bio = BiologicalAirManager.inspect(room.level, room.scan);
        BiologicalAirManager.RateSample bioRate = BiologicalAirManager.inspectRate(room.level, room.scan);
        AirTreatmentNetwork.TransferDiagnostics transfer =
                AirTreatmentNetwork.inspectTransfers(room.level, room.scan);
        VentilationNetworkScanner.RoomVentDiagnostics roomVents =
                VentilationNetworkScanner.inspectRoomVents(room.level, room.scan);
        VentilationFanBlockEntity.RoomFlowSample flow =
                VentilationFanBlockEntity.inspectRoomFlow(room.level, room.scan);

        int occupants = roomOccupants(room.level, room.scan);
        double actualBioSupport = bioRate.actualCo2PerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double ventilationO2Support = flow.oxygenAddedPerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.14D;
        double ventilationCo2Support = flow.co2RemovedPerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double ventilationSupport = Math.max(ventilationO2Support, ventilationCo2Support);
        double netLocalSupport = actualBioSupport + ventilationSupport - occupants;
        boolean co2Available = room.air.co2Percent() > RoomAtmosphere.NORMAL_CO2 + 0.000001D;

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "ROOM %dm³ | Dust %.2f%% | Air Rad %.2f mSv/h | O2 %.2f%% | CO2 %.2f%% | Air %.1f%% | Fresh demand %.2f m³/s",
                room.scan.volume(), room.air.dustPercent(), radHour, room.air.oxygenPercent(),
                room.air.co2Percent(), room.air.airQualityPercent(), demand)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Biological: %d plant blocks | Capacity %.1f | Active %.1f | Light %.0f%% | Theoretical support %.2f player-eq",
                bio.plantBlocks(), bio.nominalCapacity(), bio.activeCapacity(),
                bio.lightUtilization() * 100.0D, bio.supportedPlayers())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Bio rate: Potential CO2 -%.4f%%/min | Actual CO2 -%.4f%%/min | Actual O2 +%.4f%%/min | CO2 available %s",
                bioRate.potentialCo2PerSecond() * 60.0D,
                bioRate.actualCo2PerSecond() * 60.0D,
                bioRate.actualO2PerSecond() * 60.0D,
                co2Available ? "YES" : "NO")), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Ventilation: Supply %.2f m³/s (%d vent) | Return %.2f m³/s (%d vent) | Fresh share %.2f m³/s | Recirc %.2f m³/s",
                flow.supplyM3PerSecond(), roomVents.supplyVents(),
                flow.returnM3PerSecond(), roomVents.returnVents(),
                flow.freshAirM3PerSecond(), flow.recirculatedM3PerSecond())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Vent gas: O2 +%.4f%%/min | CO2 -%.4f%%/min",
                flow.oxygenAddedPerSecond() * 60.0D,
                flow.co2RemovedPerSecond() * 60.0D)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Passive transfer: %d connected room(s) | %d Transfer Vent(s) | %.1f m³/s | Max dO2 %.3f%% | Max dCO2 %.3f%%",
                transfer.connectedRooms(), transfer.ventCount(), transfer.totalCapacity(),
                transfer.maxOxygenDelta(), transfer.maxCo2Delta())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Life support (local): Respiration %.2f player-eq | Bio actual %.2f | Vent actual %.2f | Net %+.2f",
                (double) occupants, actualBioSupport, ventilationSupport, netLocalSupport)), false);

        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()), false);
        return 1;
    }
'''
new_room_info = '''    private static int roomInfo(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;

        double radHour = room.air.airborneRadiationPerSecond() * 3600.0D;
        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "ROOM %dm³ | Dust %.2f%% | Air Rad %.2f mSv/h | O2 %.2f%% | CO2 %.2f%% | Air %.1f%%",
                room.scan.volume(), room.air.dustPercent(), radHour, room.air.oxygenPercent(),
                room.air.co2Percent(), room.air.airQualityPercent())), false);
        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()
                + " | Detailed systems: /af life"), false);
        return 1;
    }

    private static int lifeInfo(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;

        double demand = AirIntakeBlockEntity.freshAirDemandM3PerSecond(room.air);
        BiologicalAirManager.Snapshot bio = BiologicalAirManager.inspect(room.level, room.scan);
        BiologicalAirManager.RateSample bioRate = BiologicalAirManager.inspectRate(room.level, room.scan);
        AirTreatmentNetwork.TransferDiagnostics transfer =
                AirTreatmentNetwork.inspectTransfers(room.level, room.scan);
        AirTreatmentNetwork.ScrubberDiagnostics scrubber =
                AirTreatmentNetwork.inspectScrubbers(room.level, room.scan);
        VentilationNetworkScanner.RoomVentDiagnostics roomVents =
                VentilationNetworkScanner.inspectRoomVents(room.level, room.scan);
        VentilationFanBlockEntity.RoomFlowSample flow =
                VentilationFanBlockEntity.inspectRoomFlow(room.level, room.scan);

        int occupants = roomOccupants(room.level, room.scan);
        double actualBioSupport = bioRate.actualCo2PerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double ventilationO2Support = flow.oxygenAddedPerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.14D;
        double ventilationCo2Support = flow.co2RemovedPerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double ventilationSupport = Math.max(ventilationO2Support, ventilationCo2Support);
        double netCo2Support = actualBioSupport + scrubber.actualPlayerEquivalent()
                + ventilationCo2Support - occupants;
        boolean co2Available = room.air.co2Percent() > RoomAtmosphere.NORMAL_CO2 + 0.000001D;

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "LIFE %dm³ | O2 %.2f%% | CO2 %.3f%% | Air %.1f%% | Fresh demand %.2f m³/s",
                room.scan.volume(), room.air.oxygenPercent(), room.air.co2Percent(),
                room.air.airQualityPercent(), demand)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Biological: %d plants | Capacity %.1f | Active %.1f | Light %.0f%% | Theoretical %.2f player-eq",
                bio.plantBlocks(), bio.nominalCapacity(), bio.activeCapacity(),
                bio.lightUtilization() * 100.0D, bio.supportedPlayers())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Bio rate: Potential CO2 -%.4f%%/min | Actual CO2 -%.4f%%/min | Actual O2 +%.4f%%/min | CO2 available %s",
                bioRate.potentialCo2PerSecond() * 60.0D,
                bioRate.actualCo2PerSecond() * 60.0D,
                bioRate.actualO2PerSecond() * 60.0D,
                co2Available ? "YES" : "NO")), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "CO2 scrubber: %d unit(s) | Ready %d | Active %d | Flow cap %.1f m³/s | Nominal %.2f | Actual %.2f player-eq | CO2 -%.4f%%/min",
                scrubber.units(), scrubber.readyUnits(), scrubber.activeUnits(), scrubber.flowCapacity(),
                scrubber.nominalPlayerEquivalent(), scrubber.actualPlayerEquivalent(),
                scrubber.co2RemovedPerSecond() * 60.0D)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Ventilation: Supply %.2f m³/s (%d vent) | Return %.2f m³/s (%d vent) | Fresh %.2f m³/s | Recirc %.2f m³/s",
                flow.supplyM3PerSecond(), roomVents.supplyVents(),
                flow.returnM3PerSecond(), roomVents.returnVents(),
                flow.freshAirM3PerSecond(), flow.recirculatedM3PerSecond())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Vent gas: O2 +%.4f%%/min | CO2 -%.4f%%/min | O2 support %.2f | CO2 support %.2f player-eq",
                flow.oxygenAddedPerSecond() * 60.0D,
                flow.co2RemovedPerSecond() * 60.0D,
                ventilationO2Support, ventilationCo2Support)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Passive transfer: %d connected room(s) | %d Transfer Vent(s) | %.1f m³/s | Max dO2 %.3f%% | Max dCO2 %.3f%%",
                transfer.connectedRooms(), transfer.ventCount(), transfer.totalCapacity(),
                transfer.maxOxygenDelta(), transfer.maxCo2Delta())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "CO2 balance (local): Respiration %.2f | Bio %.2f | Scrubber %.2f | Vent %.2f | Net %+.2f player-eq",
                (double) occupants, actualBioSupport, scrubber.actualPlayerEquivalent(),
                ventilationCo2Support, netCo2Support)), false);
        source.sendSuccess(() -> Component.literal("Note: CO2 Scrubber removes CO2 only; it does not generate O2."), false);
        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()), false);
        return 1;
    }
'''
replace_once(commands, old_room_info, new_room_info)


# -----------------------------------------------------------------------------
# Assets / loot / localization. Vanilla textures keep the patch text-only and
# avoid adding binary art in this systems-focused release.
# -----------------------------------------------------------------------------
write(res / 'assets/afterfall/blockstates/co2_scrubber.json', '''{
  "variants": {
    "facing=north": {"model": "afterfall:block/co2_scrubber", "uvlock": true},
    "facing=east":  {"model": "afterfall:block/co2_scrubber", "uvlock": true, "y": 90},
    "facing=south": {"model": "afterfall:block/co2_scrubber", "uvlock": true, "y": 180},
    "facing=west":  {"model": "afterfall:block/co2_scrubber", "uvlock": true, "y": 270},
    "facing=up":    {"model": "afterfall:block/co2_scrubber", "uvlock": true, "x": 270},
    "facing=down":  {"model": "afterfall:block/co2_scrubber", "uvlock": true, "x": 90}
  }
}
''')
write(res / 'assets/afterfall/models/block/co2_scrubber.json', '''{
  "parent": "minecraft:block/orientable",
  "textures": {
    "top": "minecraft:block/iron_block",
    "front": "minecraft:block/blast_furnace_front",
    "side": "minecraft:block/smooth_stone"
  }
}
''')
write(res / 'assets/afterfall/models/item/co2_scrubber.json',
      '{"parent":"afterfall:block/co2_scrubber"}\n')
write(res / 'data/afterfall/loot_table/blocks/co2_scrubber.json',
      '{"type":"minecraft:block","pools":[{"bonus_rolls":0.0,"conditions":[{"condition":"minecraft:survives_explosion"}],"entries":[{"type":"minecraft:item","name":"afterfall:co2_scrubber"}],"rolls":1.0}],"random_sequence":"afterfall:blocks/co2_scrubber"}\n')

for language, label in [('en_us.json', 'CO2 Scrubber'), ('de_de.json', 'CO2-Wäscher')]:
    path = res / 'assets/afterfall/lang' / language
    data = json.loads(path.read_text())
    data['block.afterfall.co2_scrubber'] = label
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

print('Afterfall 0.8.4 CO2 Scrubber + Life Commands patch applied')
