from pathlib import Path
import json

ROOT = Path("Afterfall")


def replace_one(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old[:180]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
replace_one(ROOT / "gradle.properties", "mod_version=0.8.5.3\n", "mod_version=0.9.0\n")

# -----------------------------------------------------------------------------
# Emergency Power Bank block: horizontal FRONT is the critical output, BACK is
# charge input. The remaining four faces are auxiliary output ports.
# -----------------------------------------------------------------------------
write(ROOT / "src/main/java/dev/afterfall/block/EmergencyPowerBankBlock.java", r'''package dev.afterfall.block;

import dev.afterfall.blockentity.EmergencyPowerBankBlockEntity;
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

/**
 * Directional bunker UPS / reserve bank.
 * FRONT = critical output, BACK = charging input, remaining faces = auxiliary output.
 */
public final class EmergencyPowerBankBlock extends Block implements EntityBlock {
    public static final DirectionProperty FACING = BlockStateProperties.HORIZONTAL_FACING;

    public EmergencyPowerBankBlock(Properties properties) {
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
        return new EmergencyPowerBankBlockEntity(pos, state);
    }
}
''')

write(ROOT / "src/main/java/dev/afterfall/blockentity/EmergencyPowerBankBlockEntity.java", r'''package dev.afterfall.blockentity;

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
''')

# -----------------------------------------------------------------------------
# Registries / content
# -----------------------------------------------------------------------------
blocks = ROOT / "src/main/java/dev/afterfall/content/ModBlocks.java"
replace_one(blocks,
    "import dev.afterfall.block.EmergencyGeneratorBlock;\n",
    "import dev.afterfall.block.EmergencyGeneratorBlock;\nimport dev.afterfall.block.EmergencyPowerBankBlock;\n")
replace_one(blocks,
    "    public static final DeferredBlock<EmergencyGeneratorBlock> EMERGENCY_GENERATOR = BLOCKS.register(\"emergency_generator\",\n"
    "            () -> new EmergencyGeneratorBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 8.0F)\n"
    "                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));\n\n",
    "    public static final DeferredBlock<EmergencyGeneratorBlock> EMERGENCY_GENERATOR = BLOCKS.register(\"emergency_generator\",\n"
    "            () -> new EmergencyGeneratorBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 8.0F)\n"
    "                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));\n\n"
    "    public static final DeferredBlock<EmergencyPowerBankBlock> EMERGENCY_POWER_BANK = BLOCKS.register(\"emergency_power_bank\",\n"
    "            () -> new EmergencyPowerBankBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)\n"
    "                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));\n\n")

entities = ROOT / "src/main/java/dev/afterfall/content/ModBlockEntities.java"
replace_one(entities,
    "import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;\n",
    "import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;\nimport dev.afterfall.blockentity.EmergencyPowerBankBlockEntity;\n")
replace_one(entities,
    "    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<EmergencyGeneratorBlockEntity>> EMERGENCY_GENERATOR =\n"
    "            BLOCK_ENTITY_TYPES.register(\"emergency_generator\", () -> BlockEntityType.Builder.of(\n"
    "                    EmergencyGeneratorBlockEntity::new, ModBlocks.EMERGENCY_GENERATOR.get()).build(null));\n",
    "    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<EmergencyGeneratorBlockEntity>> EMERGENCY_GENERATOR =\n"
    "            BLOCK_ENTITY_TYPES.register(\"emergency_generator\", () -> BlockEntityType.Builder.of(\n"
    "                    EmergencyGeneratorBlockEntity::new, ModBlocks.EMERGENCY_GENERATOR.get()).build(null));\n"
    "    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<EmergencyPowerBankBlockEntity>> EMERGENCY_POWER_BANK =\n"
    "            BLOCK_ENTITY_TYPES.register(\"emergency_power_bank\", () -> BlockEntityType.Builder.of(\n"
    "                    EmergencyPowerBankBlockEntity::new, ModBlocks.EMERGENCY_POWER_BANK.get()).build(null));\n")

items = ROOT / "src/main/java/dev/afterfall/content/ModItems.java"
replace_one(items,
    "    public static final DeferredItem<BlockItem> EMERGENCY_GENERATOR = ITEMS.registerSimpleBlockItem(\"emergency_generator\", ModBlocks.EMERGENCY_GENERATOR);\n",
    "    public static final DeferredItem<BlockItem> EMERGENCY_GENERATOR = ITEMS.registerSimpleBlockItem(\"emergency_generator\", ModBlocks.EMERGENCY_GENERATOR);\n"
    "    public static final DeferredItem<BlockItem> EMERGENCY_POWER_BANK = ITEMS.registerSimpleBlockItem(\"emergency_power_bank\", ModBlocks.EMERGENCY_POWER_BANK);\n")

creative = ROOT / "src/main/java/dev/afterfall/content/ModCreativeTabs.java"
replace_one(creative,
    "                        output.accept(ModItems.EMERGENCY_GENERATOR.get());\n",
    "                        output.accept(ModItems.EMERGENCY_GENERATOR.get());\n"
    "                        output.accept(ModItems.EMERGENCY_POWER_BANK.get());\n")

caps = ROOT / "src/main/java/dev/afterfall/content/ModCapabilities.java"
replace_one(caps,
    "        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.EMERGENCY_GENERATOR.get(),\n"
    "                (be, side) -> be.energyStorage());\n",
    "        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.EMERGENCY_GENERATOR.get(),\n"
    "                (be, side) -> be.energyStorage());\n"
    "        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.EMERGENCY_POWER_BANK.get(),\n"
    "                (be, side) -> be.energyStorage(side));\n")

# -----------------------------------------------------------------------------
# Interaction: right-click opens the shared machine GUI.
# -----------------------------------------------------------------------------
events = ROOT / "src/main/java/dev/afterfall/event/CommonEvents.java"
replace_one(events,
    "import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;\n",
    "import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;\nimport dev.afterfall.blockentity.EmergencyPowerBankBlockEntity;\n")
replace_one(events,
    "        if (state.is(ModBlocks.EMERGENCY_GENERATOR.get()) && event.getHand() == InteractionHand.MAIN_HAND) {\n",
    "        if (state.is(ModBlocks.EMERGENCY_POWER_BANK.get()) && event.getHand() == InteractionHand.MAIN_HAND) {\n"
    "            event.setCancellationResult(InteractionResult.SUCCESS);\n"
    "            event.setCanceled(true);\n"
    "            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel\n"
    "                    && serverLevel.getBlockEntity(event.getPos()) instanceof EmergencyPowerBankBlockEntity bank) {\n"
    "                openMachineMenu(player, event.getPos(), bank, Component.literal(\"Emergency Power Bank\"));\n"
    "            }\n"
    "            return;\n"
    "        }\n\n"
    "        if (state.is(ModBlocks.EMERGENCY_GENERATOR.get()) && event.getHand() == InteractionHand.MAIN_HAND) {\n")

# -----------------------------------------------------------------------------
# Machine menu: first-class power-bank machine type + synchronized power telemetry.
# -----------------------------------------------------------------------------
menu = ROOT / "src/main/java/dev/afterfall/menu/MachineMenu.java"
replace_one(menu,
    "import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;\n",
    "import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;\nimport dev.afterfall.blockentity.EmergencyPowerBankBlockEntity;\n")
replace_one(menu, "    public static final int DATA_COUNT = 54;\n", "    public static final int DATA_COUNT = 62;\n")
replace_one(menu,
    "    public static final int TYPE_SCRUBBER = 5;\n",
    "    public static final int TYPE_SCRUBBER = 5;\n    public static final int TYPE_POWER_BANK = 6;\n")
replace_one(menu,
    "    public static final int BUTTON_SCRUBBER_AUTO = 7;\n",
    "    public static final int BUTTON_SCRUBBER_AUTO = 7;\n"
    "    public static final int BUTTON_POWERBANK_AUTO = 8;\n"
    "    public static final int BUTTON_POWERBANK_CRITICAL = 9;\n"
    "    public static final int BUTTON_POWERBANK_ALL = 10;\n")
replace_one(menu,
    "    public static final int D_SCRUBBER_FRESH_CAPACITY_X10 = 53;\n",
    "    public static final int D_SCRUBBER_FRESH_CAPACITY_X10 = 53;\n"
    "    public static final int D_POWERBANK_MODE = 54;\n"
    "    public static final int D_POWERBANK_RESERVE_PERCENT = 55;\n"
    "    public static final int D_POWERBANK_CRITICAL_OUT = 56;\n"
    "    public static final int D_POWERBANK_AUX_OUT = 57;\n"
    "    public static final int D_POWERBANK_CRITICAL_CAP = 58;\n"
    "    public static final int D_POWERBANK_AUX_CAP = 59;\n"
    "    public static final int D_POWERBANK_RUNTIME_SECONDS = 60;\n"
    "    public static final int D_POWERBANK_AUX_AVAILABLE = 61;\n")
replace_one(menu,
    "        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1\n"
    "                : ((machineType == TYPE_FAN || machineType == TYPE_INTAKE || machineType == TYPE_SCRUBBER) ? 0 : 3);\n",
    "        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1\n"
    "                : ((machineType == TYPE_FAN || machineType == TYPE_INTAKE || machineType == TYPE_SCRUBBER\n"
    "                || machineType == TYPE_POWER_BANK) ? 0 : 3);\n")
replace_one(menu,
    "        if (blockEntity instanceof Co2ScrubberBlockEntity) return TYPE_SCRUBBER;\n"
    "        return TYPE_FILTER;\n",
    "        if (blockEntity instanceof Co2ScrubberBlockEntity) return TYPE_SCRUBBER;\n"
    "        if (blockEntity instanceof EmergencyPowerBankBlockEntity) return TYPE_POWER_BANK;\n"
    "        return TYPE_FILTER;\n")
replace_one(menu,
    "        if (blockEntity instanceof Co2ScrubberBlockEntity) return new ItemStackHandler(0);\n"
    "        if (type == TYPE_INTAKE || type == TYPE_FAN || type == TYPE_SCRUBBER) return new ItemStackHandler(0);\n",
    "        if (blockEntity instanceof Co2ScrubberBlockEntity) return new ItemStackHandler(0);\n"
    "        if (blockEntity instanceof EmergencyPowerBankBlockEntity) return new ItemStackHandler(0);\n"
    "        if (type == TYPE_INTAKE || type == TYPE_FAN || type == TYPE_SCRUBBER || type == TYPE_POWER_BANK) return new ItemStackHandler(0);\n")

bank_update = r'''
        if (serverBlockEntity instanceof EmergencyPowerBankBlockEntity be) {
            data.set(D_TYPE, TYPE_POWER_BANK);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.internalEnergy().getEnergyStored(), be.internalEnergy().getMaxEnergyStored());
            data.set(D_POWERBANK_MODE, be.mode().ordinal());
            data.set(D_POWERBANK_RESERVE_PERCENT, EmergencyPowerBankBlockEntity.RESERVE_PERCENT);
            data.set(D_POWERBANK_CRITICAL_OUT, be.recentCriticalOutputPerTick());
            data.set(D_POWERBANK_AUX_OUT, be.recentAuxiliaryOutputPerTick());
            data.set(D_POWERBANK_CRITICAL_CAP, EmergencyPowerBankBlockEntity.MAX_CRITICAL_OUTPUT_PER_TICK);
            data.set(D_POWERBANK_AUX_CAP, EmergencyPowerBankBlockEntity.MAX_AUX_OUTPUT_PER_TICK);
            data.set(D_POWERBANK_RUNTIME_SECONDS, be.estimatedRuntimeSeconds());
            data.set(D_POWERBANK_AUX_AVAILABLE, be.auxiliaryAllowed() ? 1 : 0);
            data.set(D_INPUT_ROOM_VOLUME, be.recentInputPerTick()); // reused only as FE/t charge telemetry in this panel

            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (be.internalEnergy().getEnergyStored() <= 0) data.set(D_STATUS, 45);
            else if (be.mode() == EmergencyPowerBankBlockEntity.PowerMode.CRITICAL) data.set(D_STATUS, 44);
            else if (be.reserveActive()) data.set(D_STATUS, 43);
            else data.set(D_STATUS, 42);
            data.set(D_POWER_SOURCE, 3);
            return;
        }

'''
replace_one(menu,
    "        if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) {\n",
    bank_update + "        if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) {\n")
replace_one(menu,
    "            else if (serverBlockEntity instanceof Co2ScrubberBlockEntity be) be.setEnabled(!be.enabled());\n"
    "            else if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {\n",
    "            else if (serverBlockEntity instanceof Co2ScrubberBlockEntity be) be.setEnabled(!be.enabled());\n"
    "            else if (serverBlockEntity instanceof EmergencyPowerBankBlockEntity be) be.setEnabled(!be.enabled());\n"
    "            else if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {\n")

bank_buttons = r'''
        if (serverBlockEntity instanceof EmergencyPowerBankBlockEntity be) {
            EmergencyPowerBankBlockEntity.PowerMode requested = switch (id) {
                case BUTTON_POWERBANK_AUTO -> EmergencyPowerBankBlockEntity.PowerMode.AUTO;
                case BUTTON_POWERBANK_CRITICAL -> EmergencyPowerBankBlockEntity.PowerMode.CRITICAL;
                case BUTTON_POWERBANK_ALL -> EmergencyPowerBankBlockEntity.PowerMode.ALL;
                default -> null;
            };
            if (requested != null) {
                be.setMode(requested);
                updateServerData();
                return true;
            }
        }

'''
replace_one(menu,
    "        if (serverBlockEntity instanceof Co2ScrubberBlockEntity be) {\n"
    "            Co2ScrubberBlockEntity.ScrubberMode requested = switch (id) {\n",
    bank_buttons + "        if (serverBlockEntity instanceof Co2ScrubberBlockEntity be) {\n"
    "            Co2ScrubberBlockEntity.ScrubberMode requested = switch (id) {\n")
replace_one(menu,
    "    public double scrubberFreshCapacity() { return get(D_SCRUBBER_FRESH_CAPACITY_X10) / 10.0D; }\n",
    "    public double scrubberFreshCapacity() { return get(D_SCRUBBER_FRESH_CAPACITY_X10) / 10.0D; }\n"
    "    public int powerBankMode() { return get(D_POWERBANK_MODE); }\n"
    "    public int powerBankReservePercent() { return get(D_POWERBANK_RESERVE_PERCENT); }\n"
    "    public int powerBankCriticalOut() { return get(D_POWERBANK_CRITICAL_OUT); }\n"
    "    public int powerBankAuxOut() { return get(D_POWERBANK_AUX_OUT); }\n"
    "    public int powerBankCriticalCap() { return get(D_POWERBANK_CRITICAL_CAP); }\n"
    "    public int powerBankAuxCap() { return get(D_POWERBANK_AUX_CAP); }\n"
    "    public int powerBankRuntimeSeconds() { return get(D_POWERBANK_RUNTIME_SECONDS); }\n"
    "    public boolean powerBankAuxAvailable() { return get(D_POWERBANK_AUX_AVAILABLE) != 0; }\n"
    "    public int powerBankInputPerTick() { return get(D_INPUT_ROOM_VOLUME); }\n")

# -----------------------------------------------------------------------------
# Machine screen: dedicated power control panel with explicit physical bus model.
# -----------------------------------------------------------------------------
screen = ROOT / "src/main/java/dev/afterfall/client/MachineScreen.java"
replace_one(screen,
    "    private Button scrubberAutoButton;\n",
    "    private Button scrubberAutoButton;\n"
    "    private Button powerBankAutoButton;\n"
    "    private Button powerBankCriticalButton;\n"
    "    private Button powerBankAllButton;\n")
replace_one(screen,
    "        } else if (menu.machineType() == MachineMenu.TYPE_SCRUBBER) {\n"
    "            scrubberScrubButton = addRenderableWidget(Button.builder(Component.literal(\"SCRUB\"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_SCRUB))\n"
    "                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());\n"
    "            scrubberBypassButton = addRenderableWidget(Button.builder(Component.literal(\"BYPASS\"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_BYPASS))\n"
    "                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());\n"
    "            scrubberAutoButton = addRenderableWidget(Button.builder(Component.literal(\"AUTO\"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_AUTO))\n"
    "                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());\n"
    "        }\n",
    "        } else if (menu.machineType() == MachineMenu.TYPE_SCRUBBER) {\n"
    "            scrubberScrubButton = addRenderableWidget(Button.builder(Component.literal(\"SCRUB\"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_SCRUB))\n"
    "                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());\n"
    "            scrubberBypassButton = addRenderableWidget(Button.builder(Component.literal(\"BYPASS\"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_BYPASS))\n"
    "                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());\n"
    "            scrubberAutoButton = addRenderableWidget(Button.builder(Component.literal(\"AUTO\"), b -> sendButton(MachineMenu.BUTTON_SCRUBBER_AUTO))\n"
    "                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());\n"
    "        } else if (menu.machineType() == MachineMenu.TYPE_POWER_BANK) {\n"
    "            powerBankAutoButton = addRenderableWidget(Button.builder(Component.literal(\"AUTO\"), b -> sendButton(MachineMenu.BUTTON_POWERBANK_AUTO))\n"
    "                    .bounds(leftPos + 12, topPos + 88, 68, 18).build());\n"
    "            powerBankCriticalButton = addRenderableWidget(Button.builder(Component.literal(\"CRITICAL\"), b -> sendButton(MachineMenu.BUTTON_POWERBANK_CRITICAL))\n"
    "                    .bounds(leftPos + 86, topPos + 88, 68, 18).build());\n"
    "            powerBankAllButton = addRenderableWidget(Button.builder(Component.literal(\"ALL\"), b -> sendButton(MachineMenu.BUTTON_POWERBANK_ALL))\n"
    "                    .bounds(leftPos + 160, topPos + 88, 68, 18).build());\n"
    "        }\n")
replace_one(screen,
    "        if (scrubberScrubButton != null) {\n"
    "            scrubberScrubButton.setMessage(Component.literal(menu.scrubberMode() == 0 ? \"[ SCRUB ]\" : \"SCRUB\"));\n"
    "            scrubberBypassButton.setMessage(Component.literal(menu.scrubberMode() == 1 ? \"[ BYPASS ]\" : \"BYPASS\"));\n"
    "            scrubberAutoButton.setMessage(Component.literal(menu.scrubberMode() == 2 ? \"[ AUTO ]\" : \"AUTO\"));\n"
    "        }\n",
    "        if (scrubberScrubButton != null) {\n"
    "            scrubberScrubButton.setMessage(Component.literal(menu.scrubberMode() == 0 ? \"[ SCRUB ]\" : \"SCRUB\"));\n"
    "            scrubberBypassButton.setMessage(Component.literal(menu.scrubberMode() == 1 ? \"[ BYPASS ]\" : \"BYPASS\"));\n"
    "            scrubberAutoButton.setMessage(Component.literal(menu.scrubberMode() == 2 ? \"[ AUTO ]\" : \"AUTO\"));\n"
    "        }\n"
    "        if (powerBankAutoButton != null) {\n"
    "            powerBankAutoButton.setMessage(Component.literal(menu.powerBankMode() == 0 ? \"[ AUTO ]\" : \"AUTO\"));\n"
    "            powerBankCriticalButton.setMessage(Component.literal(menu.powerBankMode() == 1 ? \"[ CRITICAL ]\" : \"CRITICAL\"));\n"
    "            powerBankAllButton.setMessage(Component.literal(menu.powerBankMode() == 2 ? \"[ ALL ]\" : \"ALL\"));\n"
    "        }\n")
replace_one(screen,
    "        } else if (menu.machineType() == MachineMenu.TYPE_SCRUBBER) {\n"
    "            renderScrubber(graphics);\n"
    "        } else {\n",
    "        } else if (menu.machineType() == MachineMenu.TYPE_SCRUBBER) {\n"
    "            renderScrubber(graphics);\n"
    "        } else if (menu.machineType() == MachineMenu.TYPE_POWER_BANK) {\n"
    "            renderPowerBank(graphics);\n"
    "        } else {\n")

render_bank = r'''    private void renderPowerBank(GuiGraphics graphics) {
        String mode = switch (menu.powerBankMode()) {
            case 1 -> "CRITICAL";
            case 2 -> "ALL";
            default -> "AUTO";
        };
        String auxState = menu.powerBankAuxAvailable() ? "ENABLED" : "SHED";
        int auxColor = menu.powerBankAuxAvailable() ? 0xFF66C477 : 0xFFE1B45A;
        int runtime = menu.powerBankRuntimeSeconds();
        String runtimeText = runtime < 0 ? "-- (no measured load)"
                : String.format(Locale.ROOT, "%dm %02ds", runtime / 60, runtime % 60);

        graphics.drawString(font, "BUNKER UPS // PHYSICAL LOAD PRIORITY", 12, 111, 0xFF8EC9D1, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Mode %s | Reserve floor %d%%",
                mode, menu.powerBankReservePercent()), 12, 124, 0xFFD3DDDF, false);
        graphics.drawString(font, "Ports: BACK charge | FRONT critical | SIDES auxiliary",
                12, 137, 0xFF9DB7BD, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Charge input: %,d / %,d FE/t",
                menu.powerBankInputPerTick(), 2000), 12, 150, 0xFF9DB7BD, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Critical bus: %,d / %,d FE/t",
                menu.powerBankCriticalOut(), menu.powerBankCriticalCap()), 12, 163,
                menu.powerBankCriticalOut() > 0 ? 0xFF66C477 : 0xFF7F9298, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Aux bus: %,d / %,d FE/t | %s",
                menu.powerBankAuxOut(), menu.powerBankAuxCap(), auxState), 12, 176, auxColor, false);
        graphics.drawString(font, "Runtime at measured load: " + runtimeText,
                12, 189, runtime >= 0 ? 0xFFE1B45A : 0xFF7F9298, false);
    }

'''
replace_one(screen,
    "    private void renderGenerator(GuiGraphics graphics) {\n",
    render_bank + "    private void renderGenerator(GuiGraphics graphics) {\n")
replace_one(screen,
    "            case MachineMenu.TYPE_SCRUBBER -> \"AFTERFALL // CO2 SCRUBBER\";\n"
    "            default -> \"AFTERFALL // COMPACT AIR FILTRATION UNIT\";\n",
    "            case MachineMenu.TYPE_SCRUBBER -> \"AFTERFALL // CO2 SCRUBBER\";\n"
    "            case MachineMenu.TYPE_POWER_BANK -> \"AFTERFALL // EMERGENCY POWER BANK\";\n"
    "            default -> \"AFTERFALL // COMPACT AIR FILTRATION UNIT\";\n")
replace_one(screen,
    "            case 41 -> \"AUTO BYPASS - FRESH AIR AVAILABLE\";\n"
    "            default -> \"INITIALIZING\";\n",
    "            case 41 -> \"AUTO BYPASS - FRESH AIR AVAILABLE\";\n"
    "            case 42 -> \"NORMAL DISTRIBUTION\";\n"
    "            case 43 -> \"RESERVE ACTIVE - AUX LOAD SHED\";\n"
    "            case 44 -> \"CRITICAL BUS ONLY\";\n"
    "            case 45 -> \"RESERVE EMPTY\";\n"
    "            default -> \"INITIALIZING\";\n")
replace_one(screen,
    "        if (status == 5 || status == 8 || status == 9 || status == 16 || status == 32\n"
    "                || status == 40 || status == 41) return 0xFF66C477;\n",
    "        if (status == 5 || status == 8 || status == 9 || status == 16 || status == 32\n"
    "                || status == 40 || status == 41 || status == 42) return 0xFF66C477;\n")
replace_one(screen,
    "        if (status == 4 || status == 7 || status == 31 || status == 39\n"
    "                || (menu.machineType() == MachineMenu.TYPE_AIRLOCK && status >= 20)) return 0xFFE1B45A;\n",
    "        if (status == 4 || status == 7 || status == 31 || status == 39 || status == 43 || status == 44\n"
    "                || (menu.machineType() == MachineMenu.TYPE_AIRLOCK && status >= 20)) return 0xFFE1B45A;\n")

# -----------------------------------------------------------------------------
# Resources / presentation
# -----------------------------------------------------------------------------
write(ROOT / "src/main/resources/assets/afterfall/blockstates/emergency_power_bank.json", '''{
  "variants": {
    "facing=north": {"model": "afterfall:block/emergency_power_bank"},
    "facing=east":  {"model": "afterfall:block/emergency_power_bank", "y": 90},
    "facing=south": {"model": "afterfall:block/emergency_power_bank", "y": 180},
    "facing=west":  {"model": "afterfall:block/emergency_power_bank", "y": 270}
  }
}
''')
write(ROOT / "src/main/resources/assets/afterfall/models/block/emergency_power_bank.json", '''{
  "parent": "minecraft:block/orientable",
  "textures": {
    "top": "minecraft:block/iron_block",
    "front": "minecraft:block/observer_front",
    "side": "minecraft:block/smooth_stone"
  }
}
''')
write(ROOT / "src/main/resources/assets/afterfall/models/item/emergency_power_bank.json", '''{
  "parent": "afterfall:block/emergency_power_bank"
}
''')
write(ROOT / "src/main/resources/data/afterfall/loot_table/blocks/emergency_power_bank.json", '''{
  "type": "minecraft:block",
  "pools": [{
    "rolls": 1,
    "entries": [{"type": "minecraft:item", "name": "afterfall:emergency_power_bank"}],
    "conditions": [{"condition": "minecraft:survives_explosion"}]
  }]
}
''')

for lang_name, label in [("en_us.json", "Emergency Power Bank"), ("de_de.json", "Notstrom-Energiespeicher")]:
    lang_path = ROOT / "src/main/resources/assets/afterfall/lang" / lang_name
    data = json.loads(lang_path.read_text(encoding="utf-8"))
    data["block.afterfall.emergency_power_bank"] = label
    lang_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("Applied Afterfall 0.9.0 Power Infrastructure patch")
