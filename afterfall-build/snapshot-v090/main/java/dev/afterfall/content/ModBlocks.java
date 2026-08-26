package dev.afterfall.content;

import dev.afterfall.Afterfall;
import dev.afterfall.block.AirFilterBlock;
import dev.afterfall.block.AirIntakeBlock;
import dev.afterfall.block.AirlockControllerBlock;
import dev.afterfall.block.Co2ScrubberBlock;
import dev.afterfall.block.EmergencyGeneratorBlock;
import dev.afterfall.block.EmergencyPowerBankBlock;
import dev.afterfall.block.AfterfallDoorBlock;
import dev.afterfall.block.HeavyBlastDoorBlock;
import dev.afterfall.block.HeavyBlastDoorPartBlock;
import dev.afterfall.block.AirVentBlock;
import dev.afterfall.block.VentilationFanBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.SoundType;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.material.MapColor;
import net.neoforged.neoforge.registries.DeferredBlock;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModBlocks {
    public static final DeferredRegister.Blocks BLOCKS = DeferredRegister.createBlocks(Afterfall.MOD_ID);

    public static final DeferredBlock<Block> LEAD_COMPOSITE_BLOCK = BLOCKS.registerSimpleBlock(
            "lead_composite_block", BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL));
    public static final DeferredBlock<Block> RADIOACTIVE_WASTE_BLOCK = BLOCKS.registerSimpleBlock(
            "radioactive_waste_block", BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_LIGHT_GREEN).strength(2.5F, 4.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL).lightLevel(state -> 4));
    public static final DeferredBlock<Block> ASH_BLOCK = BLOCKS.registerSimpleBlock(
            "ash_block", BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(0.6F).sound(SoundType.SAND));

    public static final DeferredBlock<AirFilterBlock> AIR_FILTER_UNIT = BLOCKS.register("air_filter_unit",
            () -> new AirFilterBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.0F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));
    public static final DeferredBlock<AirIntakeBlock> AIR_INTAKE_UNIT = BLOCKS.register("air_intake_unit",
            () -> new AirIntakeBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.0F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));
    public static final DeferredBlock<Co2ScrubberBlock> CO2_SCRUBBER = BLOCKS.register("co2_scrubber",
            () -> new Co2ScrubberBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));
    public static final DeferredBlock<AirlockControllerBlock> AIRLOCK_CONTROLLER = BLOCKS.register("airlock_controller",
            () -> new AirlockControllerBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.0F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));
    public static final DeferredBlock<Block> AIRLOCK_CALL_PANEL = BLOCKS.registerSimpleBlock("airlock_call_panel",
            BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL).lightLevel(state -> 2));

    public static final DeferredBlock<AfterfallDoorBlock> SEALED_AIRLOCK_DOOR = BLOCKS.register("sealed_airlock_door",
            () -> new AfterfallDoorBlock(BlockBehaviour.Properties.ofFullCopy(Blocks.IRON_DOOR).strength(6.0F, 12.0F)));

    public static final DeferredBlock<HeavyBlastDoorBlock> HEAVY_BLAST_DOOR = BLOCKS.register("heavy_blast_door",
            () -> new HeavyBlastDoorBlock(BlockBehaviour.Properties.ofFullCopy(Blocks.IRON_DOOR).strength(10.0F, 24.0F)));

    public static final DeferredBlock<HeavyBlastDoorPartBlock> HEAVY_BLAST_DOOR_PART = BLOCKS.register("heavy_blast_door_part",
            () -> new HeavyBlastDoorPartBlock(BlockBehaviour.Properties.ofFullCopy(Blocks.IRON_BLOCK)
                    .strength(10.0F, 24.0F).noOcclusion()));

    public static final DeferredBlock<EmergencyGeneratorBlock> EMERGENCY_GENERATOR = BLOCKS.register("emergency_generator",
            () -> new EmergencyGeneratorBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 8.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    public static final DeferredBlock<EmergencyPowerBankBlock> EMERGENCY_POWER_BANK = BLOCKS.register("emergency_power_bank",
            () -> new EmergencyPowerBankBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    public static final DeferredBlock<AirVentBlock> AIR_VENT = BLOCKS.register("air_vent",
            () -> new AirVentBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(3.5F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    // Passive, orientation-free room-to-room airflow grille. It remains airtight
    // to the RoomScanner; the ventilation graph moves air through it only while a
    // powered main fan is pulling across two distinct sealed rooms.
    public static final DeferredBlock<Block> TRANSFER_VENT = BLOCKS.registerSimpleBlock("transfer_vent",
            BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(3.5F, 7.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL));

    public static final DeferredBlock<VentilationFanBlock> VENTILATION_FAN = BLOCKS.register("ventilation_fan",
            () -> new VentilationFanBlock(BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL)));

    // Passive industrial filter media. These blocks deliberately have no facing,
    // block entity, GUI, FE storage or durability. Airflow direction is inferred
    // from the fan and the sealed plenums on both sides of a complete filter wall.
    public static final DeferredBlock<Block> INDUSTRIAL_PRE_FILTER = BLOCKS.registerSimpleBlock(
            "industrial_pre_filter", BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_GRAY).strength(4.5F, 8.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL));
    public static final DeferredBlock<Block> INDUSTRIAL_HEPA_FILTER = BLOCKS.registerSimpleBlock(
            "industrial_hepa_filter", BlockBehaviour.Properties.of().mapColor(MapColor.QUARTZ).strength(4.5F, 8.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL));
    public static final DeferredBlock<Block> INDUSTRIAL_RAD_FILTER = BLOCKS.registerSimpleBlock(
            "industrial_rad_filter", BlockBehaviour.Properties.of().mapColor(MapColor.COLOR_BROWN).strength(5.0F, 9.0F)
                    .requiresCorrectToolForDrops().sound(SoundType.METAL));

    private ModBlocks() {}
}
