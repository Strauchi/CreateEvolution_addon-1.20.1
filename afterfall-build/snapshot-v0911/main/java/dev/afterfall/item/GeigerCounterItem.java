package dev.afterfall.item;

import dev.afterfall.content.ModAttachments;
import dev.afterfall.radiation.RadiationManager;
import dev.afterfall.radiation.RadiationReading;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;

import java.util.Locale;

public final class GeigerCounterItem extends Item {
    public GeigerCounterItem(Properties properties) { super(properties); }

    @Override
    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        if (!level.isClientSide() && player instanceof ServerPlayer serverPlayer) {
            RadiationReading reading = RadiationManager.sample(serverPlayer);
            double dose = serverPlayer.getData(ModAttachments.RADIATION_DOSE);
            double contamination = serverPlayer.getData(ModAttachments.CONTAMINATION);

            serverPlayer.sendSystemMessage(Component.literal("--- Afterfall Geiger Counter ---").withStyle(ChatFormatting.DARK_GREEN));
            serverPlayer.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                    "Radiation: %.1f mSv/h", reading.totalRatePerHour())).withStyle(rateColor(reading.totalRatePerHour())));
            serverPlayer.sendSystemMessage(Component.literal(String.format(Locale.ROOT, "Absorbed dose: %.1f mSv", dose)));
            serverPlayer.sendSystemMessage(Component.literal(String.format(Locale.ROOT, "Player contamination: %.1f%%", contamination)));

            if (reading.room().sealed()) {
                serverPlayer.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                        "Room: SEALED | Volume: %d m³", reading.room().volume())).withStyle(ChatFormatting.GREEN));
                serverPlayer.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                        "Structural shielding: %.0f%%", reading.shieldingPercent())));
                serverPlayer.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                        "Air quality: %.0f%% | Radioactive dust: %.1f%%",
                        reading.room().airQualityPercent(), reading.room().dustPercent())));
                serverPlayer.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                        "Oxygen: %.2f%% | CO2: %.2f%%",
                        reading.room().oxygenPercent(), reading.room().co2Percent())));
                serverPlayer.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                        "Airborne radiation: %.1f mSv/h", reading.room().airborneRadiationPerSecond() * 3600.0D)));
            } else {
                String suffix = reading.room().scan().exceededScanLimit() ? " (open / too large)" : " (connected to outside)";
                serverPlayer.sendSystemMessage(Component.literal("Room: UNSEALED" + suffix).withStyle(ChatFormatting.RED));
                serverPlayer.sendSystemMessage(Component.literal("Structural shielding: 0%"));
                serverPlayer.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                        "Outside air quality: %.0f%% | Radioactive dust: %.1f%%",
                        reading.room().airQualityPercent(), reading.room().dustPercent())));
            }
        }
        return InteractionResultHolder.sidedSuccess(stack, level.isClientSide());
    }

    private static ChatFormatting rateColor(double ratePerHour) {
        if (ratePerHour >= 1000.0D) return ChatFormatting.DARK_RED;
        if (ratePerHour >= 250.0D) return ChatFormatting.RED;
        if (ratePerHour >= 75.0D) return ChatFormatting.GOLD;
        if (ratePerHour >= 20.0D) return ChatFormatting.YELLOW;
        return ChatFormatting.GREEN;
    }
}
