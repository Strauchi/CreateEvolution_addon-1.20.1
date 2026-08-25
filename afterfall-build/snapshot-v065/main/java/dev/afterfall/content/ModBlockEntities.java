package dev.afterfall.content;

import dev.afterfall.Afterfall;
import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;
import dev.afterfall.blockentity.HeavyBlastDoorBlockEntity;
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
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<AirlockControllerBlockEntity>> AIRLOCK_CONTROLLER =
            BLOCK_ENTITY_TYPES.register("airlock_controller", () -> BlockEntityType.Builder.of(
                    AirlockControllerBlockEntity::new, ModBlocks.AIRLOCK_CONTROLLER.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<EmergencyGeneratorBlockEntity>> EMERGENCY_GENERATOR =
            BLOCK_ENTITY_TYPES.register("emergency_generator", () -> BlockEntityType.Builder.of(
                    EmergencyGeneratorBlockEntity::new, ModBlocks.EMERGENCY_GENERATOR.get()).build(null));
    public static final DeferredHolder<BlockEntityType<?>, BlockEntityType<HeavyBlastDoorBlockEntity>> HEAVY_BLAST_DOOR =
            BLOCK_ENTITY_TYPES.register("heavy_blast_door", () -> BlockEntityType.Builder.of(
                    HeavyBlastDoorBlockEntity::new, ModBlocks.HEAVY_BLAST_DOOR.get()).build(null));

    private ModBlockEntities() {}
}
