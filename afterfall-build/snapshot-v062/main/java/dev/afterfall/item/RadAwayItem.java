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

public final class RadAwayItem extends Item {
    private static final double DOSE_REMOVAL = 250.0D;
    public RadAwayItem(Properties properties) { super(properties); }

    @Override
    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        if (!level.isClientSide()) {
            double before = player.getData(ModAttachments.RADIATION_DOSE);
            double after = Math.max(0.0D, before - DOSE_REMOVAL);
            player.setData(ModAttachments.RADIATION_DOSE, after);
            player.sendSystemMessage(Component.literal(String.format(Locale.ROOT, "RadAway: %.1f -> %.1f mSv", before, after)).withStyle(ChatFormatting.AQUA));
            if (!player.getAbilities().instabuild) stack.shrink(1);
            player.getCooldowns().addCooldown(this, 100);
        }
        return InteractionResultHolder.sidedSuccess(stack, level.isClientSide());
    }
}
