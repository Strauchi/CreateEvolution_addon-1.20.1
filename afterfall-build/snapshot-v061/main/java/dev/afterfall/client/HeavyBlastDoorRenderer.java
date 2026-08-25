package dev.afterfall.client;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import com.mojang.math.Axis;
import dev.afterfall.blockentity.HeavyBlastDoorBlockEntity;
import dev.afterfall.content.ModBlocks;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.block.BlockRenderDispatcher;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.client.resources.model.BakedModel;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.minecraft.world.level.block.state.properties.DoorHingeSide;
import net.neoforged.neoforge.client.model.data.ModelData;

public final class HeavyBlastDoorRenderer implements BlockEntityRenderer<HeavyBlastDoorBlockEntity> {
    private final BlockRenderDispatcher dispatcher;

    public HeavyBlastDoorRenderer(BlockEntityRendererProvider.Context context) {
        this.dispatcher = context.getBlockRenderDispatcher();
    }

    @Override
    public void render(HeavyBlastDoorBlockEntity be, float partialTick, PoseStack poseStack,
                       MultiBufferSource buffers, int packedLight, int packedOverlay) {
        BlockState state = be.getBlockState();
        if (!state.hasProperty(BlockStateProperties.HORIZONTAL_FACING)) return;
        Direction facing = state.getValue(BlockStateProperties.HORIZONTAL_FACING);
        float p = be.renderProgress(partialTick);
        float eased = p * p * (3.0F - 2.0F * p);
        float slide = 1.5F * eased;

        BakedModel frame = dispatcher.getBlockModel(state);
        BlockState leftState = ModBlocks.HEAVY_BLAST_DOOR_PART.get().defaultBlockState()
                .setValue(BlockStateProperties.DOOR_HINGE, DoorHingeSide.LEFT);
        BlockState rightState = ModBlocks.HEAVY_BLAST_DOOR_PART.get().defaultBlockState()
                .setValue(BlockStateProperties.DOOR_HINGE, DoorHingeSide.RIGHT);
        BakedModel left = dispatcher.getBlockModel(leftState);
        BakedModel right = dispatcher.getBlockModel(rightState);

        poseStack.pushPose();
        rotateToFacing(poseStack, facing);
        renderModel(poseStack, buffers, state, frame, packedLight, packedOverlay);
        poseStack.popPose();

        poseStack.pushPose();
        rotateToFacing(poseStack, facing);
        poseStack.translate(-slide, 0.0D, 0.0D);
        renderModel(poseStack, buffers, leftState, left, packedLight, packedOverlay);
        poseStack.popPose();

        poseStack.pushPose();
        rotateToFacing(poseStack, facing);
        poseStack.translate(slide, 0.0D, 0.0D);
        renderModel(poseStack, buffers, rightState, right, packedLight, packedOverlay);
        poseStack.popPose();
    }

    private static void rotateToFacing(PoseStack stack, Direction facing) {
        float degrees = switch (facing) {
            case NORTH -> 0.0F;
            case EAST -> -90.0F;
            case SOUTH -> 180.0F;
            case WEST -> 90.0F;
            default -> 0.0F;
        };
        stack.translate(0.5D, 0.0D, 0.5D);
        stack.mulPose(Axis.YP.rotationDegrees(degrees));
        stack.translate(-0.5D, 0.0D, -0.5D);
    }

    private void renderModel(PoseStack stack, MultiBufferSource buffers, BlockState state,
                             BakedModel model, int packedLight, int packedOverlay) {
        RenderType renderType = RenderType.solid();
        VertexConsumer consumer = buffers.getBuffer(renderType);
        dispatcher.getModelRenderer().renderModel(stack.last(), consumer, state, model,
                1.0F, 1.0F, 1.0F, packedLight, packedOverlay, ModelData.EMPTY, renderType);
    }

    @Override
    public boolean shouldRenderOffScreen(HeavyBlastDoorBlockEntity be) {
        return true;
    }
}
