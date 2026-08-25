from pathlib import Path

ROOT = Path("Afterfall")
JAVA = ROOT / "src/main/java/dev/afterfall"

# Version
gp = ROOT / "gradle.properties"
text = gp.read_text()
text = text.replace("mod_version=0.6.1", "mod_version=0.6.2")
gp.write_text(text)

# Server/client authoritative animation progress.
(JAVA / "blockentity/HeavyBlastDoorBlockEntity.java").write_text(r'''package dev.afterfall.blockentity;

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
''')

(JAVA / "block/HeavyBlastDoorBlock.java").write_text(r'''package dev.afterfall.block;

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

/** 3x2 sliding blast door with animation-aware collision. */
public final class HeavyBlastDoorBlock extends DoorBlock implements EntityBlock {
    private static final VoxelShape CLOSED_NS = Block.box(0, 0, 2, 16, 16, 14);
    private static final VoxelShape CLOSED_EW = Block.box(2, 0, 0, 14, 16, 16);

    public HeavyBlastDoorBlock(Properties properties) { super(BlockSetType.IRON, properties); }

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

    @Override protected RenderShape getRenderShape(BlockState state) { return RenderShape.INVISIBLE; }

    public static BlockPos lowerPos(BlockState state, BlockPos pos) {
        return state.hasProperty(BlockStateProperties.DOUBLE_BLOCK_HALF)
                && state.getValue(BlockStateProperties.DOUBLE_BLOCK_HALF) == DoubleBlockHalf.UPPER
                ? pos.below() : pos;
    }

    @Nullable
    public static HeavyBlastDoorBlockEntity blockEntity(BlockGetter level, BlockPos pos, BlockState state) {
        BlockEntity be = level.getBlockEntity(lowerPos(state, pos));
        return be instanceof HeavyBlastDoorBlockEntity blast ? blast : null;
    }

    public static boolean isFullyClosed(BlockGetter level, BlockPos pos, BlockState state) {
        if (!state.hasProperty(BlockStateProperties.OPEN)) return true;
        if (state.getValue(BlockStateProperties.OPEN)) return false;
        HeavyBlastDoorBlockEntity be = blockEntity(level, pos, state);
        return be == null || be.fullyClosed();
    }

    public static boolean isFullyOpen(BlockGetter level, BlockPos pos, BlockState state) {
        if (!state.hasProperty(BlockStateProperties.OPEN) || !state.getValue(BlockStateProperties.OPEN)) return false;
        HeavyBlastDoorBlockEntity be = blockEntity(level, pos, state);
        return be == null || be.fullyOpen();
    }

    public static boolean passageClear(BlockGetter level, BlockPos pos, BlockState state) {
        HeavyBlastDoorBlockEntity be = blockEntity(level, pos, state);
        if (be == null) return state.hasProperty(BlockStateProperties.OPEN) && state.getValue(BlockStateProperties.OPEN);
        float p = be.progress();
        boolean openingTarget = state.getValue(BlockStateProperties.OPEN);
        return openingTarget ? p >= 0.84F : p > 0.16F;
    }

    @Override
    protected VoxelShape getShape(BlockState state, BlockGetter level, BlockPos pos, CollisionContext context) {
        if (passageClear(level, pos, state)) return Shapes.empty();
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
            BlockPos lower = lowerPos(state, pos);
            Direction facing = state.getValue(BlockStateProperties.HORIZONTAL_FACING);
            Direction right = facing.getClockWise();
            for (int dx : new int[]{-1, 1}) for (int y = 0; y < 2; y++) {
                BlockPos partPos = lower.relative(right, dx).above(y);
                if (level.getBlockState(partPos).is(ModBlocks.HEAVY_BLAST_DOOR_PART.get())) level.removeBlock(partPos, false);
            }
        }
        super.onRemove(state, level, pos, newState, movedByPiston);
    }
}
''')

(JAVA / "block/HeavyBlastDoorPartBlock.java").write_text(r'''package dev.afterfall.block;

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
import net.minecraft.world.level.block.state.properties.DoorHingeSide;
import net.minecraft.world.level.block.state.properties.DoubleBlockHalf;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

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

    @Override protected RenderShape getRenderShape(BlockState state) { return RenderShape.INVISIBLE; }

    public BlockPos centerLower(BlockState state, BlockPos pos) {
        Direction right = state.getValue(BlockStateProperties.HORIZONTAL_FACING).getClockWise();
        DoorHingeSide side = state.getValue(BlockStateProperties.DOOR_HINGE);
        BlockPos center = side == DoorHingeSide.LEFT ? pos.relative(right) : pos.relative(right.getOpposite());
        if (state.getValue(BlockStateProperties.DOUBLE_BLOCK_HALF) == DoubleBlockHalf.UPPER) center = center.below();
        return center;
    }

    @Override
    protected VoxelShape getShape(BlockState state, BlockGetter level, BlockPos pos, CollisionContext context) {
        BlockPos center = centerLower(state, pos);
        BlockState master = level.getBlockState(center);
        if (!master.is(ModBlocks.HEAVY_BLAST_DOOR.get())) return Shapes.empty();
        if (HeavyBlastDoorBlock.passageClear(level, center, master)) return Shapes.empty();
        Direction facing = state.getValue(BlockStateProperties.HORIZONTAL_FACING);
        return facing.getAxis() == Direction.Axis.Z ? CLOSED_NS : CLOSED_EW;
    }

    @Override
    protected VoxelShape getCollisionShape(BlockState state, BlockGetter level, BlockPos pos, CollisionContext context) {
        return getShape(state, level, pos, context);
    }

    @Override
    protected void neighborChanged(BlockState state, Level level, BlockPos pos, Block sourceBlock, BlockPos sourcePos, boolean movedByPiston) {
        BlockPos center = centerLower(state, pos);
        if (!level.getBlockState(center).is(ModBlocks.HEAVY_BLAST_DOOR.get()) && !level.isClientSide) level.removeBlock(pos, false);
    }

    @Override
    protected void onRemove(BlockState state, Level level, BlockPos pos, BlockState newState, boolean movedByPiston) {
        if (!state.is(newState.getBlock()) && !level.isClientSide) {
            BlockPos center = centerLower(state, pos);
            if (level.getBlockState(center).is(ModBlocks.HEAVY_BLAST_DOOR.get())) level.destroyBlock(center, true);
        }
        super.onRemove(state, level, pos, newState, movedByPiston);
    }
}
''')

renderer = JAVA / "client/HeavyBlastDoorRenderer.java"
text = renderer.read_text()
old1 = "poseStack.translate(-slide, 0.0D, 0.0D);"
if text.count(old1) != 1:
    raise RuntimeError("Unexpected left renderer translation marker")
text = text.replace(old1, "poseStack.translate(slide, 0.0D, 0.0D);", 1)
right_context = '''poseStack.pushPose();
        rotateToFacing(poseStack, facing);
        poseStack.translate(slide, 0.0D, 0.0D);
        renderModel(poseStack, buffers, rightState, right, packedLight, packedOverlay);'''
right_repl = '''poseStack.pushPose();
        rotateToFacing(poseStack, facing);
        poseStack.translate(-slide, 0.0D, 0.0D);
        renderModel(poseStack, buffers, rightState, right, packedLight, packedOverlay);'''
if right_context not in text:
    raise RuntimeError("Right renderer context missing")
renderer.write_text(text.replace(right_context, right_repl, 1))

room = JAVA / "room/RoomScanner.java"
text = room.read_text()
if "import dev.afterfall.block.HeavyBlastDoorPartBlock;" not in text:
    text = text.replace("import dev.afterfall.content.ModBlocks;\n", "import dev.afterfall.block.HeavyBlastDoorPartBlock;\nimport dev.afterfall.content.ModBlocks;\n")
marker = '''        if (state.isAir()) return true;
        if (!state.getFluidState().isEmpty()) return false;

        if (state.getBlock() instanceof DoorBlock) {'''
replacement = '''        if (state.isAir()) return true;
        if (!state.getFluidState().isEmpty()) return false;

        if (state.is(ModBlocks.HEAVY_BLAST_DOOR_PART.get())
                && state.getBlock() instanceof HeavyBlastDoorPartBlock part) {
            BlockPos center = part.centerLower(state, pos);
            BlockState master = level.getBlockState(center);
            return !master.is(ModBlocks.HEAVY_BLAST_DOOR.get())
                    || (master.hasProperty(BlockStateProperties.OPEN) && master.getValue(BlockStateProperties.OPEN));
        }

        if (state.getBlock() instanceof DoorBlock) {'''
if marker not in text:
    raise RuntimeError("RoomScanner marker missing")
room.write_text(text.replace(marker, replacement, 1))

logic = JAVA / "blockentity/AirlockLogic.java"
text = logic.read_text()
if "import dev.afterfall.block.HeavyBlastDoorBlock;" not in text:
    text = text.replace("import dev.afterfall.content.ModBlocks;\n", "import dev.afterfall.block.HeavyBlastDoorBlock;\nimport dev.afterfall.content.ModBlocks;\n")
old = '''    public static boolean isDoorOpen(Level level, BlockPos lowerDoor) {
        BlockState state = level.getBlockState(lowerDoor);
        return state.getBlock() instanceof DoorBlock
                && state.hasProperty(BlockStateProperties.OPEN)
                && state.getValue(BlockStateProperties.OPEN);
    }'''
new = '''    public static boolean isDoorOpen(Level level, BlockPos lowerDoor) {
        BlockState state = level.getBlockState(lowerDoor);
        if (state.is(ModBlocks.HEAVY_BLAST_DOOR.get())) {
            return !HeavyBlastDoorBlock.isFullyClosed(level, lowerDoor, state);
        }
        return state.getBlock() instanceof DoorBlock
                && state.hasProperty(BlockStateProperties.OPEN)
                && state.getValue(BlockStateProperties.OPEN);
    }

    public static boolean isDoorFullyOpen(Level level, BlockPos lowerDoor) {
        BlockState state = level.getBlockState(lowerDoor);
        if (state.is(ModBlocks.HEAVY_BLAST_DOOR.get())) {
            return HeavyBlastDoorBlock.isFullyOpen(level, lowerDoor, state);
        }
        return state.getBlock() instanceof DoorBlock
                && state.hasProperty(BlockStateProperties.OPEN)
                && state.getValue(BlockStateProperties.OPEN);
    }'''
if old not in text:
    raise RuntimeError("AirlockLogic marker missing")
logic.write_text(text.replace(old, new, 1))

controller = JAVA / "blockentity/AirlockControllerBlockEntity.java"
text = controller.read_text()
old = '''            case PREPARING_ENTRY -> {
                forceBothClosed(level);
                if (stateTicks >= 10) {'''
new = '''            case PREPARING_ENTRY -> {
                forceBothClosed(level);
                if (stateTicks >= 10 && AirlockLogic.hasTwoLinkedClosedDoors(level, worldPosition)) {'''
if old not in text: raise RuntimeError("PREPARING_ENTRY marker missing")
text = text.replace(old, new, 1)
old = '''                if (stateTicks >= 12) {
                    refreshChamber(level);
                    transition(level, CycleState.PURGING,'''
new = '''                if (!AirlockLogic.isDoorOpen(level, entryDoor)) {
                    refreshChamber(level);
                    transition(level, CycleState.PURGING,'''
if old not in text: raise RuntimeError("SEALING_ENTRY marker missing")
text = text.replace(old, new, 1)
old = '''                if (stateTicks >= 12) {
                    finish(level, Component.literal("AIRLOCK: CYCLE COMPLETE").withStyle(ChatFormatting.GREEN));
                }'''
new = '''                if (!AirlockLogic.isDoorOpen(level, exitDoor)) {
                    finish(level, Component.literal("AIRLOCK: CYCLE COMPLETE").withStyle(ChatFormatting.GREEN));
                }'''
if old not in text: raise RuntimeError("SEALING_EXIT marker missing")
controller.write_text(text.replace(old, new, 1))

print("Applied Afterfall 0.6.2 blast-door fixes")
