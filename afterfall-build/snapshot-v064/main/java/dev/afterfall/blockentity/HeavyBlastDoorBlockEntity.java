package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
import net.minecraft.core.BlockPos;
import net.minecraft.util.Mth;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;

public final class HeavyBlastDoorBlockEntity extends BlockEntity {
    public static final float SPEED_PER_TICK = 0.03F;

    private float previousProgress;
    private float progress;

    public HeavyBlastDoorBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.HEAVY_BLAST_DOOR.get(), pos, state);
        float initial = state.hasProperty(BlockStateProperties.OPEN)
                && state.getValue(BlockStateProperties.OPEN) ? 1.0F : 0.0F;
        previousProgress = initial;
        progress = initial;
    }

    public static void tick(Level level, BlockPos pos, BlockState state, HeavyBlastDoorBlockEntity be) {
        be.previousProgress = be.progress;
        float target = state.getValue(BlockStateProperties.OPEN) ? 1.0F : 0.0F;
        if (be.progress < target) be.progress = Math.min(target, be.progress + SPEED_PER_TICK);
        else if (be.progress > target) be.progress = Math.max(target, be.progress - SPEED_PER_TICK);
    }

    public float progress() { return progress; }
    public boolean fullyClosed() { return progress <= 0.015F; }
    public boolean fullyOpen() { return progress >= 0.985F; }

    public float renderProgress(float partialTick) {
        return Mth.lerp(partialTick, previousProgress, progress);
    }
}
