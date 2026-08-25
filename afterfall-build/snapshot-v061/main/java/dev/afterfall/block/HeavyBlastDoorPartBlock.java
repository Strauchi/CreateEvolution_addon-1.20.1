package dev.afterfall.block;

import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.RenderShape;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.minecraft.world.level.block.state.properties.DoorHingeSide;
import net.minecraft.world.level.block.state.properties.DoubleBlockHalf;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

/** Invisible structural side cells of the 3x2 blast door. */
public final class HeavyBlastDoorPartBlock extends Block {
    private static final VoxelShape CLOSED_NS = Block.box(0, 0, 2, 16, 16, 14);
    private static final VoxelShape CLOSED_EW = Block.box(2, 0, 0, 14, 16, 16);

    public HeavyBlastDoorPartBlock(Properties properties) {
        super(properties);
        registerDefaultState(stateDefinition.any()
                .setValue(BlockStateProperties.HORIZONTAL_FACING, Direction.NORTH)
                .setValue(BlockStateProperties.DOOR_HINGE, DoorHingeSide.LEFT)
                .setValue(BlockStateProperties.DOUBLE_BLOCK_HALF, DoubleBlockHalf.LOWER)
                .setValue(BlockStateProperties.OPEN, false));
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(BlockStateProperties.HORIZONTAL_FACING, BlockStateProperties.DOOR_HINGE,
                BlockStateProperties.DOUBLE_BLOCK_HALF, BlockStateProperties.OPEN);
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

    private BlockPos centerLower(BlockState state, BlockPos pos) {
        Direction right = state.getValue(BlockStateProperties.HORIZONTAL_FACING).getClockWise();
        DoorHingeSide side = state.getValue(BlockStateProperties.DOOR_HINGE);
        BlockPos center = side == DoorHingeSide.LEFT ? pos.relative(right) : pos.relative(right.getOpposite());
        if (state.getValue(BlockStateProperties.DOUBLE_BLOCK_HALF) == DoubleBlockHalf.UPPER) center = center.below();
        return center;
    }

    @Override
    protected void neighborChanged(BlockState state, Level level, BlockPos pos, Block sourceBlock, BlockPos sourcePos, boolean movedByPiston) {
        BlockPos center = centerLower(state, pos);
        BlockState centerState = level.getBlockState(center);
        if (!centerState.is(ModBlocks.HEAVY_BLAST_DOOR.get())) {
            if (!level.isClientSide) level.removeBlock(pos, false);
            return;
        }
        boolean open = centerState.getValue(BlockStateProperties.OPEN);
        if (state.getValue(BlockStateProperties.OPEN) != open) {
            level.setBlock(pos, state.setValue(BlockStateProperties.OPEN, open), Block.UPDATE_CLIENTS);
        }
    }

    @Override
    protected void onRemove(BlockState state, Level level, BlockPos pos, BlockState newState, boolean movedByPiston) {
        if (!state.is(newState.getBlock()) && !level.isClientSide) {
            BlockPos center = centerLower(state, pos);
            if (level.getBlockState(center).is(ModBlocks.HEAVY_BLAST_DOOR.get())) {
                level.destroyBlock(center, true);
            }
        }
        super.onRemove(state, level, pos, newState, movedByPiston);
    }
}
