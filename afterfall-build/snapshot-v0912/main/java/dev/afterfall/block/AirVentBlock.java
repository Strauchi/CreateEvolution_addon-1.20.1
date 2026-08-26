package dev.afterfall.block;

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
