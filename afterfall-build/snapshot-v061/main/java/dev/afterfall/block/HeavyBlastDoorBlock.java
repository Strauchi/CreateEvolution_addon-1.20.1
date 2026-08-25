package dev.afterfall.block;

import dev.afterfall.blockentity.HeavyBlastDoorBlockEntity;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.EntityBlock;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.RenderShape;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityTicker;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.minecraft.world.level.block.state.properties.DoorHingeSide;
import net.minecraft.world.level.block.state.properties.DoubleBlockHalf;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

import javax.annotation.Nullable;

/** 3x2 electrically-operated sliding blast door. The center column remains a DoorBlock
 * for compatibility with the existing airlock controller; invisible side parts provide
 * the full three-block seal while a BER renders the authored Blockbench model. */
public final class HeavyBlastDoorBlock extends DoorBlock implements EntityBlock {
    private static final VoxelShape CLOSED_NS = Block.box(0, 0, 2, 16, 16, 14);
    private static final VoxelShape CLOSED_EW = Block.box(2, 0, 0, 14, 16, 16);

    public HeavyBlastDoorBlock(Properties properties) {
        super(BlockSetType.IRON, properties);
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        BlockState state = super.getStateForPlacement(context);
        if (state == null) return null;
        BlockPos center = context.getClickedPos();
        Direction right = state.getValue(BlockStateProperties.HORIZONTAL_FACING).getClockWise();
        for (int dx : new int[]{-1, 1}) {
            for (int y = 0; y < 2; y++) {
                BlockPos p = center.relative(right, dx).above(y);
                if (!context.getLevel().getBlockState(p).canBeReplaced(context)) return null;
            }
        }
        return state;
    }

    @Override
    public void setPlacedBy(Level level, BlockPos pos, BlockState state, @Nullable LivingEntity placer, ItemStack stack) {
        super.setPlacedBy(level, pos, state, placer, stack);
        if (level.isClientSide) return;
        Direction facing = state.getValue(BlockStateProperties.HORIZONTAL_FACING);
        Direction right = facing.getClockWise();
        boolean open = state.getValue(BlockStateProperties.OPEN);
        for (int dx : new int[]{-1, 1}) {
            DoorHingeSide side = dx < 0 ? DoorHingeSide.LEFT : DoorHingeSide.RIGHT;
            for (int y = 0; y < 2; y++) {
                DoubleBlockHalf half = y == 0 ? DoubleBlockHalf.LOWER : DoubleBlockHalf.UPPER;
                BlockPos partPos = pos.relative(right, dx).above(y);
                BlockState part = ModBlocks.HEAVY_BLAST_DOOR_PART.get().defaultBlockState()
                        .setValue(BlockStateProperties.HORIZONTAL_FACING, facing)
                        .setValue(BlockStateProperties.DOOR_HINGE, side)
                        .setValue(BlockStateProperties.DOUBLE_BLOCK_HALF, half)
                        .setValue(BlockStateProperties.OPEN, open);
                level.setBlock(partPos, part, Block.UPDATE_ALL);
            }
        }
    }

    @Override
    protected RenderShape getRenderShape(BlockState state) {
        return RenderShape.INVISIBLE;
    }

    @Override
    protected VoxelShape getShape(BlockState state, BlockGetter level, BlockPos pos, CollisionContext context) {
        if (state.getValue(BlockStateProperties.OPEN)) return Shapes.empty();
        Direction facing = state.getValue(BlockStateProperties.HORIZONTAL_FACING);
        return facing.getAxis() == Direction.Axis.Z ? CLOSED_NS : CLOSED_EW;
    }

    @Override
    protected VoxelShape getCollisionShape(BlockState state, BlockGetter level, BlockPos pos, CollisionContext context) {
        return getShape(state, level, pos, context);
    }

    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
        if (state.getValue(BlockStateProperties.DOUBLE_BLOCK_HALF) != DoubleBlockHalf.LOWER) return null;
        return new HeavyBlastDoorBlockEntity(pos, state);
    }

    @Nullable
    @Override
    @SuppressWarnings("unchecked")
    public <T extends BlockEntity> BlockEntityTicker<T> getTicker(Level level, BlockState state, BlockEntityType<T> type) {
        if (type != ModBlockEntities.HEAVY_BLAST_DOOR.get()
                || state.getValue(BlockStateProperties.DOUBLE_BLOCK_HALF) != DoubleBlockHalf.LOWER) return null;
        return (lvl, pos, st, be) -> HeavyBlastDoorBlockEntity.tick(lvl, pos, st, (HeavyBlastDoorBlockEntity) be);
    }

    @Override
    protected void onRemove(BlockState state, Level level, BlockPos pos, BlockState newState, boolean movedByPiston) {
        if (!state.is(newState.getBlock())) {
            BlockPos lower = state.getValue(BlockStateProperties.DOUBLE_BLOCK_HALF) == DoubleBlockHalf.UPPER ? pos.below() : pos;
            Direction facing = state.getValue(BlockStateProperties.HORIZONTAL_FACING);
            Direction right = facing.getClockWise();
            for (int dx : new int[]{-1, 1}) {
                for (int y = 0; y < 2; y++) {
                    BlockPos partPos = lower.relative(right, dx).above(y);
                    if (level.getBlockState(partPos).is(ModBlocks.HEAVY_BLAST_DOOR_PART.get())) {
                        level.removeBlock(partPos, false);
                    }
                }
            }
        }
        super.onRemove(state, level, pos, newState, movedByPiston);
    }
}
