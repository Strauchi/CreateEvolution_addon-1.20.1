package dev.afterfall.item;

import dev.afterfall.content.ModAttachments;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import java.util.Locale;

public final class DeconKitItem extends Item {
    private static final double CONTAMINATION_REMOVAL = 80.0D;
    public DeconKitItem(Properties properties) { super(properties); }

    @Override
    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        if (!level.isClientSide()) {
            double before = player.getData(ModAttachments.CONTAMINATION);
            double after = Math.max(0.0D, before - CONTAMINATION_REMOVAL);
            player.setData(ModAttachments.CONTAMINATION, after);
            player.sendSystemMessage(Component.literal(String.format(Locale.ROOT, "Decontamination: %.1f%% -> %.1f%%", before, after)).withStyle(ChatFormatting.BLUE));
            if (!player.getAbilities().instabuild) stack.shrink(1);
            player.getCooldowns().addCooldown(this, 80);
        }
        return InteractionResultHolder.sidedSuccess(stack, level.isClientSide());
    }
}
