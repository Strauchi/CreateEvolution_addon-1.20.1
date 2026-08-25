from pathlib import Path
import json

ROOT = Path('Afterfall')
JAVA = ROOT / 'src/main/java/dev/afterfall'
RES = ROOT / 'src/main/resources'


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'Expected text not found in {p}: {old[:120]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# 0.7.0: 6-axis air vents + FE ventilation fan + tunnel-as-duct network.
# ---------------------------------------------------------------------------

write(JAVA / 'block/AirVentBlock.java', r'''package dev.afterfall.block;

import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.level.block.state.properties.DirectionProperty;

public final class AirVentBlock extends Block {
    public static final DirectionProperty FACING = BlockStateProperties.FACING;
    public static final BooleanProperty RETURN_MODE = BooleanProperty.create("return");

    public AirVentBlock(Properties properties) {
        super(properties);
        registerDefaultState(stateDefinition.any()
                .setValue(FACING, Direction.NORTH)
                .setValue(RETURN_MODE, false));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        // Front faces the installer. Standing inside a room and looking up therefore
        // places a ceiling vent with FACING=DOWN; looking down gives FACING=UP.
        return defaultBlockState()
                .setValue(FACING, context.getNearestLookingDirection().getOpposite())
                .setValue(RETURN_MODE, false);
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(FACING, RETURN_MODE);
    }
}
''')

write(JAVA / 'block/VentilationFanBlock.java', r'''package dev.afterfall.block;

import dev.afterfall.blockentity.VentilationFanBlockEntity;
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

public final class VentilationFanBlock extends Block implements EntityBlock {
    public static final DirectionProperty FACING = BlockStateProperties.FACING;

    public VentilationFanBlock(Properties properties) {
        super(properties);
        registerDefaultState(stateDefinition.any().setValue(FACING, Direction.NORTH));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        // The fan front points toward the installer / into the ventilation shaft.
        return defaultBlockState().setValue(FACING, context.getNearestLookingDirection().getOpposite());
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(FACING);
    }

    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
        return new VentilationFanBlockEntity(pos, state);
    }

    @Override
    @Nullable
    public <T extends BlockEntity> BlockEntityTicker<T> getTicker(Level level, BlockState state, BlockEntityType<T> type) {
        return level.isClientSide ? null : createTicker(type, ModBlockEntities.VENTILATION_FAN.get(), VentilationFanBlockEntity::serverTick);
    }

    @SuppressWarnings("unchecked")
    private static <E extends BlockEntity, T extends BlockEntity> BlockEntityTicker<T> createTicker(
            BlockEntityType<T> actual, BlockEntityType<E> expected, BlockEntityTicker<? super E> ticker) {
        return actual == expected ? (BlockEntityTicker<T>) ticker : null;
    }
}
''')

write(JAVA / 'room/VentilationNetworkScanner.java', r'''package dev.afterfall.room;

import dev.afterfall.block.AirVentBlock;
import dev.afterfall.block.VentilationFanBlock;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Treats a player-built, enclosed air tunnel as a ventilation network. The air
 * cells remain ordinary Minecraft air blocks; vents/fans are airtight boundary
 * blocks and are discovered while flood-filling the shaft volume.
 */
public final class VentilationNetworkScanner {
    public static final int MAX_SHAFT_VOLUME = 8192;

    public static Network scan(ServerLevel level, BlockPos shaftStart) {
        if (!RoomScanner.airCanPass(level, shaftStart)) return null;
        RoomScanResult shaft = RoomScanner.scan(level, shaftStart);
        if (!shaft.sealed()) return new Network(shaft, List.of(), List.of());

        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> vents = new HashSet<>();
        Set<Long> fans = new HashSet<>();
        queue.add(shaftStart.immutable());
        visited.add(shaftStart.asLong());

        while (!queue.isEmpty() && visited.size() <= MAX_SHAFT_VOLUME) {
            BlockPos current = queue.removeFirst();
            for (Direction direction : Direction.values()) {
                BlockPos next = current.relative(direction);
                if (RoomScanner.airCanPass(level, next)) {
                    if (visited.add(next.asLong())) queue.addLast(next.immutable());
                    continue;
                }

                BlockState state = level.getBlockState(next);
                if (state.is(ModBlocks.AIR_VENT.get()) && state.hasProperty(AirVentBlock.FACING)) {
                    Direction facing = state.getValue(AirVentBlock.FACING);
                    if (next.relative(facing.getOpposite()).equals(current)) vents.add(next.asLong());
                }
                if (state.is(ModBlocks.VENTILATION_FAN.get()) && state.hasProperty(VentilationFanBlock.FACING)) {
                    Direction facing = state.getValue(VentilationFanBlock.FACING);
                    if (next.relative(facing).equals(current)) fans.add(next.asLong());
                }
            }
        }

        List<BlockPos> ventPositions = vents.stream().map(BlockPos::of)
                .sorted(Comparator.comparingLong(BlockPos::asLong)).toList();
        List<BlockPos> fanPositions = fans.stream().map(BlockPos::of)
                .sorted(Comparator.comparingLong(BlockPos::asLong)).toList();
        return new Network(shaft, ventPositions, fanPositions);
    }

    public static RoomScanResult roomForVent(ServerLevel level, BlockPos ventPos) {
        BlockState state = level.getBlockState(ventPos);
        if (!state.is(ModBlocks.AIR_VENT.get()) || !state.hasProperty(AirVentBlock.FACING)) return null;
        Direction facing = state.getValue(AirVentBlock.FACING);
        BlockPos start = ventPos.relative(facing);
        if (!RoomScanner.airCanPass(level, start)) return null;
        RoomScanResult scan = RoomScanner.scan(level, start);
        return scan.sealed() ? scan : null;
    }

    public static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        return RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
    }

    public record Network(RoomScanResult shaft, List<BlockPos> vents, List<BlockPos> fans) {
        public boolean valid() { return shaft != null && shaft.sealed(); }
        public int supplyVentCount(ServerLevel level) {
            int count = 0;
            for (BlockPos pos : vents) {
                BlockState state = level.getBlockState(pos);
                if (state.is(ModBlocks.AIR_VENT.get()) && !state.getValue(AirVentBlock.RETURN_MODE)) count++;
            }
            return count;
        }
        public int returnVentCount(ServerLevel level) {
            int count = 0;
            for (BlockPos pos : vents) {
                BlockState state = level.getBlockState(pos);
                if (state.is(ModBlocks.AIR_VENT.get()) && state.getValue(AirVentBlock.RETURN_MODE)) count++;
            }
            return count;
        }
    }

    private VentilationNetworkScanner() {}
}
''')

write(JAVA / 'blockentity/VentilationFanBlockEntity.java', r'''package dev.afterfall.blockentity;

import dev.afterfall.block.AirVentBlock;
import dev.afterfall.block.VentilationFanBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.VentilationNetworkScanner;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class VentilationFanBlockEntity extends BlockEntity {
    public static final int ENERGY_CAPACITY = 80_000;
    public static final int ENERGY_PER_SECOND = 800;
    public static final double FLOW_M3_PER_SECOND = 48.0D;
    public static final double MAX_FLOW_PER_VENT = 18.0D;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(
            ENERGY_CAPACITY, 4_000, 0, this::setChanged);
    private boolean enabled = true;

    public VentilationFanBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.VENTILATION_FAN.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; setChanged(); }

    public VentilationNetworkScanner.Network inspectNetwork(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        return VentilationNetworkScanner.scan(level, worldPosition.relative(facing));
    }

    public double availableNetworkFlow(ServerLevel level) {
        VentilationNetworkScanner.Network network = inspectNetwork(level);
        if (network == null || !network.valid()) return 0.0D;
        int availableFans = 0;
        for (BlockPos fanPos : network.fans()) {
            if (level.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan
                    && fan.enabled && MachinePower.available(level, fanPos, fan.energy, ENERGY_PER_SECOND)) {
                availableFans++;
            }
        }
        return availableFans * FLOW_M3_PER_SECOND;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, VentilationFanBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L || !be.enabled) return;

        VentilationNetworkScanner.Network network = be.inspectNetwork(serverLevel);
        if (network == null || !network.valid() || network.vents().isEmpty() || network.fans().isEmpty()) return;

        BlockPos leader = network.fans().stream().min(Comparator.comparingLong(BlockPos::asLong)).orElse(pos);
        if (!leader.equals(pos)) return; // one network update per second, even with multiple fans

        List<VentTarget> targets = new ArrayList<>();
        for (BlockPos ventPos : network.vents()) {
            BlockState ventState = serverLevel.getBlockState(ventPos);
            if (!ventState.is(ModBlocks.AIR_VENT.get())) continue;
            RoomScanResult room = VentilationNetworkScanner.roomForVent(serverLevel, ventPos);
            if (room == null || room.anchor().equals(network.shaft().anchor())) continue;
            boolean returnMode = ventState.getValue(AirVentBlock.RETURN_MODE);
            targets.add(new VentTarget(ventPos, room, returnMode));
        }
        if (targets.isEmpty()) return;

        int poweredFans = 0;
        for (BlockPos fanPos : network.fans()) {
            if (!(serverLevel.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan) || !fan.enabled) continue;
            if (MachinePower.consumeOrRedstoneFallback(serverLevel, fanPos, fan.energy, ENERGY_PER_SECOND)) poweredFans++;
        }
        if (poweredFans <= 0) return;

        double totalFlow = poweredFans * FLOW_M3_PER_SECOND;
        double perVentFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / Math.max(1, targets.size()));
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere shaftAir = VentilationNetworkScanner.atmosphere(serverLevel, network.shaft());

        // Return air is mixed into the shaft first; supply vents then distribute the
        // resulting central air mixture. Pressure/mass balance is intentionally deferred
        // to 0.8, but composition and rated volumetric flow already matter here.
        for (VentTarget target : targets) {
            if (!target.returnMode) continue;
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double fraction = Math.min(0.30D, perVentFlow / Math.max(1.0D, network.shaft().volume()));
            shaftAir.exchangeFrom(roomAir, fraction);
        }
        for (VentTarget target : targets) {
            if (target.returnMode) continue;
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double fraction = Math.min(0.30D, perVentFlow / Math.max(1.0D, target.room.volume()));
            roomAir.exchangeFrom(shaftAir, fraction);
        }
        saved.markChanged();
    }

    private record VentTarget(BlockPos pos, RoomScanResult room, boolean returnMode) {}

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

# Room atmosphere gains a directed composition exchange primitive used by vents.
replace_once(JAVA / 'room/RoomAtmosphere.java',
'''    public void equilibrateWith(RoomAtmosphere other, long gameTime) {''',
'''    public void exchangeFrom(RoomAtmosphere source, double exchangeFraction) {
        if (source == null || source == this) return;
        double mix = Mth.clamp(exchangeFraction, 0.0D, 1.0D);
        dustPercent = Mth.lerp(mix, dustPercent, source.dustPercent);
        airborneRadiationPerSecond = Mth.lerp(mix, airborneRadiationPerSecond, source.airborneRadiationPerSecond);
        oxygenPercent = Mth.lerp(mix, oxygenPercent, source.oxygenPercent);
        co2Percent = Mth.lerp(mix, co2Percent, source.co2Percent);
    }

    public void equilibrateWith(RoomAtmosphere other, long gameTime) {''')

# Register blocks.
replace_once(JAVA / 'content/ModBlocks.java',
'''import dev.afterfall.block.HeavyBlastDoorPartBlock;''',
'''import dev.afterfall.block.HeavyBlastDoorPartBlock;
import dev.afterfall.block.AirVentBlock;
import dev.afterfall.block.VentilationFanBlock;''')
replace_once(JAVA / 'content/ModBlocks.java',
'''    public static final DeferredBlock<EmergencyGeneratorBlock> EMERGENCY_GENERATOR = BLOCKS.register("emergency_generator",
            () -> new EmergencyGeneratorBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 8.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));
''',
'''    public static final DeferredBlock<EmergencyGeneratorBlock> EMERGENCY_GENERATOR = BLOCKS.register("emergency_generator",
            () -> new EmergencyGeneratorBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 8.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    public static final DeferredBlock<AirVentBlock> AIR_VENT = BLOCKS.register("air_vent",
            () -> new AirVentBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(3.5F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    public static final DeferredBlock<VentilationFanBlock> VENTILATION_FAN = BLOCKS.register("ventilation_fan",
            () -> new VentilationFanBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));
''')

# Items and creative tab.
replace_once(JAVA / 'content/ModItems.java',
'''    public static final DeferredItem<BlockItem> EMERGENCY_GENERATOR = ITEMS.registerSimpleBlockItem("emergency_generator", ModBlocks.EMERGENCY_GENERATOR);''',
'''    public static final DeferredItem<BlockItem> EMERGENCY_GENERATOR = ITEMS.registerSimpleBlockItem("emergency_generator", ModBlocks.EMERGENCY_GENERATOR);
    public static final DeferredItem<BlockItem> AIR_VENT = ITEMS.registerSimpleBlockItem("air_vent", ModBlocks.AIR_VENT);
    public static final DeferredItem<BlockItem> VENTILATION_FAN = ITEMS.registerSimpleBlockItem("ventilation_fan", ModBlocks.VENTILATION_FAN);''')
replace_once(JAVA / 'content/ModCreativeTabs.java',
'''                        output.accept(ModItems.EMERGENCY_GENERATOR.get());''',
'''                        output.accept(ModItems.EMERGENCY_GENERATOR.get());
                        output.accept(ModItems.AIR_VENT.get());
                        output.accept(ModItems.VENTILATION_FAN.get());''')

# Block entity + FE capability.
replace_once(JAVA / 'content/ModBlockEntities.java',
'''import dev.afterfall.blockentity.HeavyBlastDoorBlockEntity;''',
'''import dev.afterfall.blockentity.HeavyBlastDoorBlockEntity;
import dev.afterfall.blockentity.VentilationFanBlockEntity;''')
replace_once(JAVA / 'content/ModBlockEntities.java',
'''    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<HeavyBlastDoorBlockEntity>> HEAVY_BLAST_DOOR =
            BLOCK_ENTITY_TYPES.register("heavy_blast_door", () -> BlockEntityType.Builder.of(
                    HeavyBlastDoorBlockEntity::new, ModBlocks.HEAVY_BLAST_DOOR.get()).build(null));
''',
'''    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<HeavyBlastDoorBlockEntity>> HEAVY_BLAST_DOOR =
            BLOCK_ENTITY_TYPES.register("heavy_blast_door", () -> BlockEntityType.Builder.of(
                    HeavyBlastDoorBlockEntity::new, ModBlocks.HEAVY_BLAST_DOOR.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<VentilationFanBlockEntity>> VENTILATION_FAN =
            BLOCK_ENTITY_TYPES.register("ventilation_fan", () -> BlockEntityType.Builder.of(
                    VentilationFanBlockEntity::new, ModBlocks.VENTILATION_FAN.get()).build(null));
''')
replace_once(JAVA / 'content/ModCapabilities.java',
'''        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.EMERGENCY_GENERATOR.get(),
                (be, side) -> be.energyStorage());''',
'''        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.EMERGENCY_GENERATOR.get(),
                (be, side) -> be.energyStorage());
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.VENTILATION_FAN.get(),
                (be, side) -> be.energyStorage());''')

# Vents/fans are explicitly airtight boundaries even when later custom models are thin.
replace_once(JAVA / 'room/RoomScanner.java',
'''        if (state.is(ModBlocks.HEAVY_BLAST_DOOR_PART.get())''',
'''        if (state.is(ModBlocks.AIR_VENT.get()) || state.is(ModBlocks.VENTILATION_FAN.get())) return false;

        if (state.is(ModBlocks.HEAVY_BLAST_DOOR_PART.get())''')
replace_once(JAVA / 'room/RoomScanner.java',
'''        if (state.is(ModBlocks.AIR_INTAKE_UNIT.get())) return 0.42D;''',
'''        if (state.is(ModBlocks.AIR_INTAKE_UNIT.get())) return 0.42D;
        if (state.is(ModBlocks.VENTILATION_FAN.get())) return 0.34D;
        if (state.is(ModBlocks.AIR_VENT.get())) return 0.48D;''')

# ---------------------------------------------------------------------------
# Machine GUI: add a no-slot fan dashboard using the existing interface.
# ---------------------------------------------------------------------------
menu = JAVA / 'menu/MachineMenu.java'
replace_once(menu,
'''import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;''',
'''import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;
import dev.afterfall.blockentity.VentilationFanBlockEntity;''')
replace_once(menu,
'''import dev.afterfall.room.RoomScanResult;''',
'''import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.VentilationNetworkScanner;''')
replace_once(menu,
'''    public static final int TYPE_GENERATOR = 3;''',
'''    public static final int TYPE_GENERATOR = 3;
    public static final int TYPE_FAN = 4;''')
replace_once(menu,
'''        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1 : 3;''',
'''        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1 : (machineType == TYPE_FAN ? 0 : 3);''')
replace_once(menu,
'''        if (machineType == TYPE_GENERATOR) {
            addSlot(new SlotItemHandler(machineHandler, 0, FUEL_SLOT_X, FUEL_SLOT_Y));
        } else {
            for (int i = 0; i < 3; i++) addSlot(new SlotItemHandler(machineHandler, i, FILTER_SLOT_X[i], FILTER_SLOT_Y));
        }''',
'''        if (machineType == TYPE_GENERATOR) {
            addSlot(new SlotItemHandler(machineHandler, 0, FUEL_SLOT_X, FUEL_SLOT_Y));
        } else if (machineType != TYPE_FAN) {
            for (int i = 0; i < 3; i++) addSlot(new SlotItemHandler(machineHandler, i, FILTER_SLOT_X[i], FILTER_SLOT_Y));
        }''')
replace_once(menu,
'''        if (blockEntity instanceof EmergencyGeneratorBlockEntity) return TYPE_GENERATOR;''',
'''        if (blockEntity instanceof EmergencyGeneratorBlockEntity) return TYPE_GENERATOR;
        if (blockEntity instanceof VentilationFanBlockEntity) return TYPE_FAN;''')
replace_once(menu,
'''        if (blockEntity instanceof EmergencyGeneratorBlockEntity be) return be.inventory();''',
'''        if (blockEntity instanceof EmergencyGeneratorBlockEntity be) return be.inventory();
        if (blockEntity instanceof VentilationFanBlockEntity) return new ItemStackHandler(0);''')

fan_data = r'''
        if (serverBlockEntity instanceof VentilationFanBlockEntity be) {
            data.set(D_TYPE, TYPE_FAN);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            VentilationNetworkScanner.Network network = be.inspectNetwork(level);
            if (network != null && network.valid()) {
                RoomAtmosphere shaftAir = atmosphere(level, network.shaft());
                setAtmosphere(network.shaft(), shaftAir);
                data.set(D_EXTRA, network.vents().size());
                data.set(D_FLOW_X10, scale(be.availableNetworkFlow(level), 10.0D));
            }
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (network == null || !network.valid()) data.set(D_STATUS, 30);
            else if (network.vents().isEmpty()) data.set(D_STATUS, 31);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), VentilationFanBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else data.set(D_STATUS, 32);
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

'''
replace_once(menu,
'''        if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) {''',
fan_data + '''        if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) {''')
replace_once(menu,
'''            else if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) be.setEnabled(!be.enabled());''',
'''            else if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) be.setEnabled(!be.enabled());
            else if (serverBlockEntity instanceof VentilationFanBlockEntity be) be.setEnabled(!be.enabled());''')
replace_once(menu,
'''            } else if (machineType != TYPE_GENERATOR) {
                int target = FilterBank.slotFor(stack);''',
'''            } else if (machineType != TYPE_GENERATOR && machineType != TYPE_FAN) {
                int target = FilterBank.slotFor(stack);''')

# Screen: fan gets no filter slots and shows shaft/network diagnostics.
screen = JAVA / 'client/MachineScreen.java'
replace_once(screen,
'''        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            drawSlotBox(graphics, x + MachineMenu.FUEL_SLOT_X, y + MachineMenu.FUEL_SLOT_Y);
        } else {
            for (int i = 0; i < 3; i++) drawSlotBox(graphics, x + MachineMenu.FILTER_SLOT_X[i], y + MachineMenu.FILTER_SLOT_Y);
            drawFilterBar(graphics, x + 12, y + 116, 60, menu.prePercent());
            drawFilterBar(graphics, x + 92, y + 116, 60, menu.hepaPercent());
            drawFilterBar(graphics, x + 172, y + 116, 60, menu.radPercent());
        }''',
'''        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            drawSlotBox(graphics, x + MachineMenu.FUEL_SLOT_X, y + MachineMenu.FUEL_SLOT_Y);
        } else if (menu.machineType() != MachineMenu.TYPE_FAN) {
            for (int i = 0; i < 3; i++) drawSlotBox(graphics, x + MachineMenu.FILTER_SLOT_X[i], y + MachineMenu.FILTER_SLOT_Y);
            drawFilterBar(graphics, x + 12, y + 116, 60, menu.prePercent());
            drawFilterBar(graphics, x + 92, y + 116, 60, menu.hepaPercent());
            drawFilterBar(graphics, x + 172, y + 116, 60, menu.radPercent());
        }''')
replace_once(screen,
'''        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            renderGenerator(graphics);
        } else {
            renderFilters(graphics);
        }''',
'''        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            renderGenerator(graphics);
        } else if (menu.machineType() == MachineMenu.TYPE_FAN) {
            renderFan(graphics);
        } else {
            renderFilters(graphics);
        }''')
replace_once(screen,
'''    private void renderGenerator(GuiGraphics graphics) {''',
r'''    private void renderFan(GuiGraphics graphics) {
        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        graphics.drawString(font, "Ventilation shaft", 12, 88, 0xFFAAB6B9, false);
        graphics.drawString(font, "Shaft volume: " + volume + " m³", 12, 106, 0xFFD3DDDF, false);
        graphics.drawString(font, "Connected vents: " + menu.get(MachineMenu.D_EXTRA), 12, 119, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Available network flow: %.1f m³/s", menu.flow()), 12, 132, 0xFFD3DDDF, false);
        if (volume > 0) {
            graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 12, 151, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 124, 151, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%%", menu.oxygenPercent()), 12, 164, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "CO2: %.2f%%", menu.co2Percent()), 124, 164, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 12, 177, 0xFFD3DDDF, false);
        }
        graphics.drawString(font, "Fan front must face into the sealed shaft.", 12, 194, 0xFF7F9298, false);
    }

    private void renderGenerator(GuiGraphics graphics) {''')
replace_once(screen,
'''            case MachineMenu.TYPE_GENERATOR -> "AFTERFALL // EMERGENCY GENERATOR";''',
'''            case MachineMenu.TYPE_GENERATOR -> "AFTERFALL // EMERGENCY GENERATOR";
            case MachineMenu.TYPE_FAN -> "AFTERFALL // VENTILATION FAN";''')
replace_once(screen,
'''            case 17 -> "SWITCHED OFF";''',
'''            case 17 -> "SWITCHED OFF";
            case 30 -> "ERROR - SHAFT NOT SEALED";
            case 31 -> "STANDBY - NO CONNECTED VENTS";
            case 32 -> "CIRCULATING";''')
replace_once(screen,
'''        if (status == 5 || status == 8 || status == 9 || status == 16) return 0xFF66C477;''',
'''        if (status == 5 || status == 8 || status == 9 || status == 16 || status == 32) return 0xFF66C477;''')

# Right-click behavior for vents/fan and diagnostics.
events = JAVA / 'event/CommonEvents.java'
replace_once(events,
'''import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;''',
'''import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;
import dev.afterfall.blockentity.VentilationFanBlockEntity;
import dev.afterfall.block.AirVentBlock;''')
replace_once(events,
'''import dev.afterfall.room.RoomEnvironmentManager;''',
'''import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.VentilationNetworkScanner;''')
vent_events = r'''
        if (state.is(ModBlocks.AIR_VENT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                if (player.isShiftKeyDown()) {
                    boolean newReturn = !state.getValue(AirVentBlock.RETURN_MODE);
                    serverLevel.setBlock(event.getPos(), state.setValue(AirVentBlock.RETURN_MODE, newReturn), 3);
                    player.displayClientMessage(Component.literal("AIR VENT: MODE = " + (newReturn ? "RETURN" : "SUPPLY"))
                            .withStyle(newReturn ? ChatFormatting.AQUA : ChatFormatting.GREEN), true);
                } else {
                    var facing = state.getValue(AirVentBlock.FACING);
                    BlockPos shaftStart = event.getPos().relative(facing.getOpposite());
                    var network = VentilationNetworkScanner.scan(serverLevel, shaftStart);
                    RoomScanResult room = VentilationNetworkScanner.roomForVent(serverLevel, event.getPos());
                    String shaft = network != null && network.valid() ? network.shaft().volume() + "m³ SEALED" : "NOT SEALED";
                    String roomText = room != null ? room.volume() + "m³ SEALED" : "NO SEALED ROOM";
                    player.displayClientMessage(Component.literal("AIR VENT: "
                            + (state.getValue(AirVentBlock.RETURN_MODE) ? "RETURN" : "SUPPLY")
                            + " | Facing " + facing.getName().toUpperCase(Locale.ROOT)
                            + " | Shaft " + shaft + " | Room " + roomText).withStyle(ChatFormatting.AQUA), true);
                }
            }
            return;
        }

        if (state.is(ModBlocks.VENTILATION_FAN.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof VentilationFanBlockEntity fan) {
                    openMachineMenu(player, event.getPos(), fan, Component.literal("Ventilation Fan"));
                }
            }
            return;
        }

'''
replace_once(events,
'''        if (state.is(ModBlocks.AIRLOCK_CALL_PANEL.get()) && event.getHand() == InteractionHand.MAIN_HAND) {''',
vent_events + '''        if (state.is(ModBlocks.AIRLOCK_CALL_PANEL.get()) && event.getHand() == InteractionHand.MAIN_HAND) {''')
# Missing BlockPos import for vent diagnostics.
replace_once(events,
'''import net.minecraft.ChatFormatting;''',
'''import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;''')

# Versions and log label.
props = ROOT / 'gradle.properties'
text = props.read_text(encoding='utf-8')
import re
text = re.sub(r'^mod_version=.*$', 'mod_version=0.7.0', text, flags=re.M)
props.write_text(text, encoding='utf-8')
replace_once(JAVA / 'Afterfall.java', 'Afterfall 0.6.0 initialized', 'Afterfall 0.7.0 initialized')

# ---------------------------------------------------------------------------
# Placeholder assets. Custom Blockbench models will replace these after testing.
# ---------------------------------------------------------------------------

def directional_variants(model, include_return=False):
    rotations = {
        'north': {},
        'east': {'y': 90},
        'south': {'y': 180},
        'west': {'y': 270},
        'up': {'x': 270},
        'down': {'x': 90},
    }
    variants = {}
    for facing, rotation in rotations.items():
        returns = [False, True] if include_return else [None]
        for ret in returns:
            key = f'facing={facing}' + (f',return={str(ret).lower()}' if ret is not None else '')
            entry = {'model': model, 'uvlock': True}
            entry.update(rotation)
            variants[key] = entry
    return {'variants': variants}

write(RES / 'assets/afterfall/blockstates/air_vent.json', json.dumps(
    directional_variants('afterfall:block/air_vent', True), indent=2))
write(RES / 'assets/afterfall/blockstates/ventilation_fan.json', json.dumps(
    directional_variants('afterfall:block/ventilation_fan', False), indent=2))

write(RES / 'assets/afterfall/models/block/air_vent.json', json.dumps({
    'parent': 'minecraft:block/orientable',
    'textures': {
        'front': 'minecraft:block/iron_trapdoor',
        'side': 'minecraft:block/iron_block',
        'top': 'minecraft:block/smooth_stone'
    }
}, indent=2))
write(RES / 'assets/afterfall/models/block/ventilation_fan.json', json.dumps({
    'parent': 'minecraft:block/orientable',
    'textures': {
        'front': 'minecraft:block/dispenser_front',
        'side': 'minecraft:block/iron_block',
        'top': 'minecraft:block/polished_andesite'
    }
}, indent=2))
write(RES / 'assets/afterfall/models/item/air_vent.json', json.dumps({'parent':'afterfall:block/air_vent'}, indent=2))
write(RES / 'assets/afterfall/models/item/ventilation_fan.json', json.dumps({'parent':'afterfall:block/ventilation_fan'}, indent=2))

for name in ['air_vent', 'ventilation_fan']:
    loot = {
        'type':'minecraft:block',
        'pools':[{
            'bonus_rolls':0.0,
            'conditions':[{'condition':'minecraft:survives_explosion'}],
            'entries':[{'type':'minecraft:item','name':f'afterfall:{name}'}],
            'rolls':1.0
        }],
        'random_sequence':f'afterfall:blocks/{name}'
    }
    write(RES / f'data/afterfall/loot_table/blocks/{name}.json', json.dumps(loot, separators=(',',':')))

for lang_file, additions in [
    ('en_us.json', {
        'block.afterfall.air_vent':'Air Vent',
        'block.afterfall.ventilation_fan':'Main Ventilation Fan'
    }),
    ('de_de.json', {
        'block.afterfall.air_vent':'Lüftungsventil',
        'block.afterfall.ventilation_fan':'Hauptlüfter'
    })
]:
    p = RES / 'assets/afterfall/lang' / lang_file
    data = json.loads(p.read_text(encoding='utf-8'))
    data.update(additions)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print('Afterfall 0.7.0 ventilation patch applied')
