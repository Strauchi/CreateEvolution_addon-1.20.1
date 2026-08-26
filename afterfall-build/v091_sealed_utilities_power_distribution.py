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
replace_one(ROOT / "gradle.properties", "mod_version=0.9.0\n", "mod_version=0.9.1\n")

# -----------------------------------------------------------------------------
# Sealed Power Feedthrough
# -----------------------------------------------------------------------------
write(ROOT / "src/main/java/dev/afterfall/block/SealedPowerFeedthroughBlock.java", r'''package dev.afterfall.block;

import dev.afterfall.blockentity.SealedPowerFeedthroughBlockEntity;
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
 * Airtight FE wall penetration.
 * FRONT (FACING) = FE output; BACK = FE input; remaining faces expose no FE.
 */
public final class SealedPowerFeedthroughBlock extends Block implements EntityBlock {
    public static final DirectionProperty FACING = BlockStateProperties.FACING;

    public SealedPowerFeedthroughBlock(Properties properties) {
        super(properties);
        registerDefaultState(stateDefinition.any().setValue(FACING, Direction.NORTH));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        return defaultBlockState().setValue(FACING, context.getClickedFace());
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(FACING);
    }

    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
        return new SealedPowerFeedthroughBlockEntity(pos, state);
    }
}
''')

write(ROOT / "src/main/java/dev/afterfall/blockentity/SealedPowerFeedthroughBlockEntity.java", r'''package dev.afterfall.blockentity;

import dev.afterfall.block.SealedPowerFeedthroughBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachineEnergyStorage;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.energy.IEnergyStorage;
import org.jetbrains.annotations.Nullable;

/** Generic FE bridge through an airtight bunker wall. */
public final class SealedPowerFeedthroughBlockEntity extends BlockEntity {
    public static final int BUFFER_CAPACITY = 8_000;
    public static final int MAX_TRANSFER_PER_TICK = 8_000;

    private final MachineEnergyStorage buffer = new MachineEnergyStorage(
            BUFFER_CAPACITY, MAX_TRANSFER_PER_TICK, MAX_TRANSFER_PER_TICK, this::setChanged);

    private final IEnergyStorage inputPort = new IEnergyStorage() {
        @Override public int receiveEnergy(int maxReceive, boolean simulate) { return buffer.receiveEnergy(maxReceive, simulate); }
        @Override public int extractEnergy(int maxExtract, boolean simulate) { return 0; }
        @Override public int getEnergyStored() { return buffer.getEnergyStored(); }
        @Override public int getMaxEnergyStored() { return buffer.getMaxEnergyStored(); }
        @Override public boolean canExtract() { return false; }
        @Override public boolean canReceive() { return buffer.getEnergyStored() < buffer.getMaxEnergyStored(); }
    };

    private final IEnergyStorage outputPort = new IEnergyStorage() {
        @Override public int receiveEnergy(int maxReceive, boolean simulate) { return 0; }
        @Override public int extractEnergy(int maxExtract, boolean simulate) { return buffer.extractEnergy(maxExtract, simulate); }
        @Override public int getEnergyStored() { return buffer.getEnergyStored(); }
        @Override public int getMaxEnergyStored() { return buffer.getMaxEnergyStored(); }
        @Override public boolean canExtract() { return buffer.getEnergyStored() > 0; }
        @Override public boolean canReceive() { return false; }
    };

    public SealedPowerFeedthroughBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.SEALED_POWER_FEEDTHROUGH.get(), pos, state);
    }

    public MachineEnergyStorage internalBuffer() { return buffer; }

    @Nullable
    public IEnergyStorage energyStorage(@Nullable Direction side) {
        if (side == null) return null;
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.SEALED_POWER_FEEDTHROUGH.get())
                || !state.hasProperty(SealedPowerFeedthroughBlock.FACING)) return null;
        Direction front = state.getValue(SealedPowerFeedthroughBlock.FACING);
        if (side == front) return outputPort;
        if (side == front.getOpposite()) return inputPort;
        return null;
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        buffer.setEnergyStored(tag.getInt("Energy"));
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", buffer.getEnergyStored());
    }
}
''')

# Registries
blocks = ROOT / "src/main/java/dev/afterfall/content/ModBlocks.java"
replace_one(blocks,
    "import dev.afterfall.block.EmergencyPowerBankBlock;\n",
    "import dev.afterfall.block.EmergencyPowerBankBlock;\nimport dev.afterfall.block.SealedPowerFeedthroughBlock;\n")
replace_one(blocks,
    "    public static final DeferredBlock<EmergencyPowerBankBlock> EMERGENCY_POWER_BANK = BLOCKS.register(\"emergency_power_bank\",\n"
    "            () -> new EmergencyPowerBankBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)\n"
    "                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));\n\n",
    "    public static final DeferredBlock<EmergencyPowerBankBlock> EMERGENCY_POWER_BANK = BLOCKS.register(\"emergency_power_bank\",\n"
    "            () -> new EmergencyPowerBankBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)\n"
    "                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));\n\n"
    "    public static final DeferredBlock<SealedPowerFeedthroughBlock> SEALED_POWER_FEEDTHROUGH = BLOCKS.register(\"sealed_power_feedthrough\",\n"
    "            () -> new SealedPowerFeedthroughBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(6.0F, 12.0F)\n"
    "                    .sound(SoundType.METAL)));\n\n")

entities = ROOT / "src/main/java/dev/afterfall/content/ModBlockEntities.java"
replace_one(entities,
    "import dev.afterfall.blockentity.EmergencyPowerBankBlockEntity;\n",
    "import dev.afterfall.blockentity.EmergencyPowerBankBlockEntity;\nimport dev.afterfall.blockentity.SealedPowerFeedthroughBlockEntity;\n")
replace_one(entities,
    "    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<EmergencyPowerBankBlockEntity>> EMERGENCY_POWER_BANK =\n"
    "            BLOCK_ENTITY_TYPES.register(\"emergency_power_bank\", () -> BlockEntityType.Builder.of(\n"
    "                    EmergencyPowerBankBlockEntity::new, ModBlocks.EMERGENCY_POWER_BANK.get()).build(null));\n",
    "    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<EmergencyPowerBankBlockEntity>> EMERGENCY_POWER_BANK =\n"
    "            BLOCK_ENTITY_TYPES.register(\"emergency_power_bank\", () -> BlockEntityType.Builder.of(\n"
    "                    EmergencyPowerBankBlockEntity::new, ModBlocks.EMERGENCY_POWER_BANK.get()).build(null));\n"
    "    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<SealedPowerFeedthroughBlockEntity>> SEALED_POWER_FEEDTHROUGH =\n"
    "            BLOCK_ENTITY_TYPES.register(\"sealed_power_feedthrough\", () -> BlockEntityType.Builder.of(\n"
    "                    SealedPowerFeedthroughBlockEntity::new, ModBlocks.SEALED_POWER_FEEDTHROUGH.get()).build(null));\n")

items = ROOT / "src/main/java/dev/afterfall/content/ModItems.java"
replace_one(items,
    "    public static final DeferredItem<BlockItem> EMERGENCY_POWER_BANK = ITEMS.registerSimpleBlockItem(\"emergency_power_bank\", ModBlocks.EMERGENCY_POWER_BANK);\n",
    "    public static final DeferredItem<BlockItem> EMERGENCY_POWER_BANK = ITEMS.registerSimpleBlockItem(\"emergency_power_bank\", ModBlocks.EMERGENCY_POWER_BANK);\n"
    "    public static final DeferredItem<BlockItem> SEALED_POWER_FEEDTHROUGH = ITEMS.registerSimpleBlockItem(\"sealed_power_feedthrough\", ModBlocks.SEALED_POWER_FEEDTHROUGH);\n")

creative = ROOT / "src/main/java/dev/afterfall/content/ModCreativeTabs.java"
replace_one(creative,
    "                        output.accept(ModItems.EMERGENCY_POWER_BANK.get());\n",
    "                        output.accept(ModItems.EMERGENCY_POWER_BANK.get());\n"
    "                        output.accept(ModItems.SEALED_POWER_FEEDTHROUGH.get());\n")

caps = ROOT / "src/main/java/dev/afterfall/content/ModCapabilities.java"
replace_one(caps,
    "        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.EMERGENCY_POWER_BANK.get(),\n"
    "                (be, side) -> be.energyStorage(side));\n",
    "        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.EMERGENCY_POWER_BANK.get(),\n"
    "                (be, side) -> be.energyStorage(side));\n"
    "        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.SEALED_POWER_FEEDTHROUGH.get(),\n"
    "                (be, side) -> be.energyStorage(side));\n")

# Explicit bunker shielding value. Full collision already seals room flood-fill.
scanner = ROOT / "src/main/java/dev/afterfall/room/RoomScanner.java"
replace_one(scanner,
    "        if (state.is(ModBlocks.AIRLOCK_CONTROLLER.get())) return 0.16D;\n",
    "        if (state.is(ModBlocks.AIRLOCK_CONTROLLER.get())) return 0.16D;\n"
    "        if (state.is(ModBlocks.SEALED_POWER_FEEDTHROUGH.get())) return 0.10D;\n")

# Resources
write(ROOT / "src/main/resources/assets/afterfall/blockstates/sealed_power_feedthrough.json", '''{
  "variants": {
    "facing=north": {"model": "afterfall:block/sealed_power_feedthrough"},
    "facing=east":  {"model": "afterfall:block/sealed_power_feedthrough", "y": 90},
    "facing=south": {"model": "afterfall:block/sealed_power_feedthrough", "y": 180},
    "facing=west":  {"model": "afterfall:block/sealed_power_feedthrough", "y": 270},
    "facing=up":    {"model": "afterfall:block/sealed_power_feedthrough", "x": 270},
    "facing=down":  {"model": "afterfall:block/sealed_power_feedthrough", "x": 90}
  }
}
''')
write(ROOT / "src/main/resources/assets/afterfall/models/block/sealed_power_feedthrough.json", '''{
  "parent": "minecraft:block/cube",
  "textures": {
    "particle": "minecraft:block/iron_block",
    "down": "minecraft:block/iron_block",
    "up": "minecraft:block/iron_block",
    "north": "minecraft:block/observer_front",
    "south": "minecraft:block/observer_back",
    "east": "minecraft:block/smooth_stone",
    "west": "minecraft:block/smooth_stone"
  }
}
''')
write(ROOT / "src/main/resources/assets/afterfall/models/item/sealed_power_feedthrough.json", '''{
  "parent": "afterfall:block/sealed_power_feedthrough"
}
''')
write(ROOT / "src/main/resources/data/afterfall/loot_table/blocks/sealed_power_feedthrough.json", '''{
  "type": "minecraft:block",
  "pools": [{
    "rolls": 1,
    "entries": [{"type": "minecraft:item", "name": "afterfall:sealed_power_feedthrough"}],
    "conditions": [{"condition": "minecraft:survives_explosion"}]
  }]
}
''')

for lang_name, label in [("en_us.json", "Sealed Power Feedthrough"), ("de_de.json", "Abgedichtete Stromdurchführung")]:
    lang_path = ROOT / "src/main/resources/assets/afterfall/lang" / lang_name
    data = json.loads(lang_path.read_text(encoding="utf-8"))
    data["block.afterfall.sealed_power_feedthrough"] = label
    lang_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("Applied Afterfall 0.9.1 Sealed Utilities & Power Distribution patch")
