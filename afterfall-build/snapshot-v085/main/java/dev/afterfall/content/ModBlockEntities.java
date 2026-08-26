package dev.afterfall.content;

import dev.afterfall.Afterfall;
import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.Co2ScrubberBlockEntity;
import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;
import dev.afterfall.blockentity.HeavyBlastDoorBlockEntity;
import dev.afterfall.blockentity.VentilationFanBlockEntity;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModBlockEntities {
    public static final DeferredRegister<BlockEntityType<?>> BLOCK_ENTITY_TYPES =
            DeferredRegister.create(Registries.BLOCK_ENTITY_TYPE, Afterfall.MOD_ID);

    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<AirFilterBlockEntity>> AIR_FILTER =
            BLOCK_ENTITY_TYPES.register("air_filter", () -> BlockEntityType.Builder.of(
                    AirFilterBlockEntity::new, ModBlocks.AIR_FILTER_UNIT.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<AirIntakeBlockEntity>> AIR_INTAKE =
            BLOCK_ENTITY_TYPES.register("air_intake", () -> BlockEntityType.Builder.of(
                    AirIntakeBlockEntity::new, ModBlocks.AIR_INTAKE_UNIT.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<Co2ScrubberBlockEntity>> CO2_SCRUBBER =
            BLOCK_ENTITY_TYPES.register("co2_scrubber", () -> BlockEntityType.Builder.of(
                    Co2ScrubberBlockEntity::new, ModBlocks.CO2_SCRUBBER.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<AirlockControllerBlockEntity>> AIRLOCK_CONTROLLER =
            BLOCK_ENTITY_TYPES.register("airlock_controller", () -> BlockEntityType.Builder.of(
                    AirlockControllerBlockEntity::new, ModBlocks.AIRLOCK_CONTROLLER.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<EmergencyGeneratorBlockEntity>> EMERGENCY_GENERATOR =
            BLOCK_ENTITY_TYPES.register("emergency_generator", () -> BlockEntityType.Builder.of(
                    EmergencyGeneratorBlockEntity::new, ModBlocks.EMERGENCY_GENERATOR.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<HeavyBlastDoorBlockEntity>> HEAVY_BLAST_DOOR =
            BLOCK_ENTITY_TYPES.register("heavy_blast_door", () -> BlockEntityType.Builder.of(
                    HeavyBlastDoorBlockEntity::new, ModBlocks.HEAVY_BLAST_DOOR.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<VentilationFanBlockEntity>> VENTILATION_FAN =
            BLOCK_ENTITY_TYPES.register("ventilation_fan", () -> BlockEntityType.Builder.of(
                    VentilationFanBlockEntity::new, ModBlocks.VENTILATION_FAN.get()).build(null));

    private ModBlockEntities() {}
}
