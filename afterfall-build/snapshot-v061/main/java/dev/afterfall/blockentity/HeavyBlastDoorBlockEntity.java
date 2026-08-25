package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
import net.minecraft.core.BlockPos;
import net.minecraft.util.Mth;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;

public final class HeavyBlastDoorBlockEntity extends BlockEntity {
    private float previousProgress;
    private float progress;

    public HeavyBlastDoorBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.HEAVY_BLAST_DOOR.get(), pos, state);
        float initial = state.hasProperty(BlockStateProperties.OPEN) && state.getValue(BlockStateProperties.OPEN) ? 1.0F : 0.0F;
        previousProgress = initial;
        progress = initial;
    }

    public static void tick(Level level, BlockPos pos, BlockState state, HeavyBlastDoorBlockEntity be) {
        if (!level.isClientSide) return;
        be.previousProgress = be.progress;
        float target = state.getValue(BlockStateProperties.OPEN) ? 1.0F : 0.0F;
        float speed = 0.03F;
        if (be.progress < target) be.progress = Math.min(target, be.progress + speed);
        else if (be.progress > target) be.progress = Math.max(target, be.progress - speed);
    }

    public float renderProgress(float partialTick) {
        return Mth.lerp(partialTick, previousProgress, progress);
    }
}
