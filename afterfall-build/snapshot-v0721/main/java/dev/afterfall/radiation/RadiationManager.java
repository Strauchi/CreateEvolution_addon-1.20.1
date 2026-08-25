package dev.afterfall.radiation;

import dev.afterfall.content.ModAttachments;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.room.RoomEnvironment;
import dev.afterfall.room.RoomEnvironmentManager;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Mth;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.level.Level;

public final class RadiationManager {
    private static final int HOTSPOT_RADIUS = 8;

    // Outdoor wasteland radiation is split into penetrating gamma and radioactive
    // particles suspended in the air. A sealed room only shields the external gamma;
    // trapped dirty air remains dangerous until it is filtered later by bunker machinery.
    private static final double WASTELAND_GAMMA_MSV_PER_SECOND = 0.022D;
    private static final double WASTELAND_AIRBORNE_MSV_PER_SECOND = 0.013D;
    private static final double HOTSPOT_STRENGTH_MSV_PER_SECOND = 0.85D;

    public static RadiationReading sample(ServerPlayer player) {
        ServerLevel level = player.serverLevel();
        BlockPos playerPos = player.blockPosition();
        if (!Level.OVERWORLD.equals(level.dimension())) {
            RoomEnvironment room = RoomEnvironmentManager.sample(player, false);
            return new RadiationReading(0.0D, 0.0D, 0.0D, contaminationInternalRate(player),
                    room.shieldingFactor(), false, false, room);
        }

        boolean wasteland = RoomEnvironmentManager.isWasteland(level, playerPos);
        RoomEnvironment room = RoomEnvironmentManager.sample(player, wasteland);
        boolean skyExposed = level.canSeeSky(playerPos.above());

        double shielding = room.sealed() ? room.shieldingFactor() : 1.0D;
        double externalGamma = wasteland ? WASTELAND_GAMMA_MSV_PER_SECOND * shielding : 0.0D;
        double airborne = wasteland
                ? (room.sealed() ? room.airborneRadiationPerSecond() : WASTELAND_AIRBORNE_MSV_PER_SECOND)
                : room.airborneRadiationPerSecond();
        double hotspot = calculateHotspotRate(level, playerPos) * shielding;
        double internal = contaminationInternalRate(player);

        return new RadiationReading(externalGamma, hotspot, airborne, internal, shielding, skyExposed, wasteland, room);
    }

    public static void tickSecond(ServerPlayer player) {
        RadiationReading reading = sample(player);
        double dose = player.getData(ModAttachments.RADIATION_DOSE);
        dose = Mth.clamp(dose + reading.totalRatePerSecond(), 0.0D, 5000.0D);
        player.setData(ModAttachments.RADIATION_DOSE, dose);

        double contamination = player.getData(ModAttachments.CONTAMINATION);
        double contaminationGain = 0.0D;

        // Radioactive dust is now room-aware. An airtight bunker prevents new outdoor
        // dust from entering, but whatever dust is already trapped in the room can
        // still contaminate the player until an air filtration system removes it.
        if (reading.wasteland()) {
            double dustFraction = reading.room().dustPercent() / 100.0D;
            contaminationGain += reading.room().sealed() ? 0.010D * dustFraction : 0.035D;
            if (!reading.room().sealed() && player.serverLevel().isRainingAt(player.blockPosition().above())) {
                contaminationGain += 0.09D;
            }
        }

        if (reading.hotspotRatePerSecond() > 0.05D) {
            contaminationGain += Math.min(0.35D, reading.hotspotRatePerSecond() * 0.18D);
        }
        if (contaminationGain > 0.0D) {
            contamination = Mth.clamp(contamination + contaminationGain, 0.0D, 100.0D);
            player.setData(ModAttachments.CONTAMINATION, contamination);
        }

        RoomEnvironmentManager.consumeBreathingAir(player, reading.room());
        applyAirQualityEffects(player, reading.room());
        applyRadiationSickness(player, dose);
    }

    private static double contaminationInternalRate(ServerPlayer player) {
        double contamination = player.getData(ModAttachments.CONTAMINATION);
        return (contamination / 100.0D) * 0.08D;
    }

    private static double calculateHotspotRate(ServerLevel level, BlockPos center) {
        double total = 0.0D;
        for (BlockPos pos : BlockPos.betweenClosed(
                center.offset(-HOTSPOT_RADIUS, -4, -HOTSPOT_RADIUS),
                center.offset(HOTSPOT_RADIUS, 4, HOTSPOT_RADIUS))) {
            if (!level.getBlockState(pos).is(ModBlocks.RADIOACTIVE_WASTE_BLOCK.get())) continue;
            double dx = pos.getX() - center.getX();
            double dy = pos.getY() - center.getY();
            double dz = pos.getZ() - center.getZ();
            double distanceSquared = dx * dx + dy * dy + dz * dz;
            total += HOTSPOT_STRENGTH_MSV_PER_SECOND / (1.0D + distanceSquared * 0.28D);
        }
        return Math.min(total, 4.0D);
    }


    private static void applyAirQualityEffects(ServerPlayer player, RoomEnvironment room) {
        if (!room.sealed()) return;
        double oxygen = room.oxygenPercent();
        double co2 = room.co2Percent();
        if (oxygen < 17.0D || co2 > 2.5D) {
            player.addEffect(new MobEffectInstance(MobEffects.WEAKNESS, 60, 0, true, false, true));
        }
        if (oxygen < 14.0D || co2 > 4.0D) {
            player.addEffect(new MobEffectInstance(MobEffects.DIG_SLOWDOWN, 60, 0, true, false, true));
            player.addEffect(new MobEffectInstance(MobEffects.CONFUSION, 100, 0, true, false, true));
        }
        if ((oxygen < 10.0D || co2 > 7.0D) && player.tickCount % 40 == 0) {
            player.hurt(player.damageSources().drown(), 1.0F);
        }
    }

    private static void applyRadiationSickness(ServerPlayer player, double dose) {
        if (dose >= 150.0D) player.addEffect(new MobEffectInstance(MobEffects.HUNGER, 60, 0, true, false, true));
        if (dose >= 300.0D) player.addEffect(new MobEffectInstance(MobEffects.WEAKNESS, 60, 0, true, false, true));
        if (dose >= 600.0D) {
            player.addEffect(new MobEffectInstance(MobEffects.DIG_SLOWDOWN, 60, 0, true, false, true));
            player.addEffect(new MobEffectInstance(MobEffects.CONFUSION, 100, 0, true, false, true));
        }
        if (dose >= 900.0D && player.tickCount % 100 == 0) player.hurt(player.damageSources().magic(), 1.0F);
        if (dose >= 1400.0D && player.tickCount % 40 == 0) player.hurt(player.damageSources().magic(), 2.0F);
    }

    private RadiationManager() {}
}
