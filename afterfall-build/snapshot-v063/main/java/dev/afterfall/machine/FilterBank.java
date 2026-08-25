package dev.afterfall.machine;

import dev.afterfall.content.ModItems;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;

import java.util.Locale;

public final class FilterBank {
    public static final int MAX_PREFILTER = 36_000;
    public static final int MAX_HEPA = 48_000;
    public static final int MAX_RAD = 42_000;

    private int prefilter;
    private int hepa;
    private int radiological;
    private final Runnable onChanged;

    public FilterBank(Runnable onChanged) {
        this.onChanged = onChanged == null ? () -> {} : onChanged;
    }

    public boolean complete() {
        return prefilter > 0 && hepa > 0 && radiological > 0;
    }

    public boolean installFromHeld(ServerPlayer player, ItemStack stack) {
        if (stack.is(ModItems.PREFILTER_CARTRIDGE.get())) {
            prefilter = MAX_PREFILTER;
        } else if (stack.is(ModItems.HEPA_FILTER_CARTRIDGE.get())) {
            hepa = MAX_HEPA;
        } else if (stack.is(ModItems.RAD_FILTER_CARTRIDGE.get())) {
            radiological = MAX_RAD;
        } else {
            return false;
        }
        if (!player.getAbilities().instabuild) stack.shrink(1);
        onChanged.run();
        return true;
    }

    public void consume(int preWear, int hepaWear, int radWear) {
        int oldPre = prefilter;
        int oldHepa = hepa;
        int oldRad = radiological;
        prefilter = Math.max(0, prefilter - Math.max(0, preWear));
        hepa = Math.max(0, hepa - Math.max(0, hepaWear));
        radiological = Math.max(0, radiological - Math.max(0, radWear));
        if (oldPre != prefilter || oldHepa != hepa || oldRad != radiological) onChanged.run();
    }

    public double prefilterFraction() { return prefilter / (double) MAX_PREFILTER; }
    public double hepaFraction() { return hepa / (double) MAX_HEPA; }
    public double radiologicalFraction() { return radiological / (double) MAX_RAD; }

    public int prefilterPercent() { return (int) Math.round(prefilterFraction() * 100.0D); }
    public int hepaPercent() { return (int) Math.round(hepaFraction() * 100.0D); }
    public int radiologicalPercent() { return (int) Math.round(radiologicalFraction() * 100.0D); }

    public double dustEfficiency() {
        return 0.90D + 0.095D * Math.min(prefilterFraction(), hepaFraction());
    }

    public double radiationEfficiency() {
        return 0.82D + 0.175D * Math.min(hepaFraction(), radiologicalFraction());
    }

    public double minimumFraction() {
        return Math.min(prefilterFraction(), Math.min(hepaFraction(), radiologicalFraction()));
    }

    public String conditionLabel() {
        if (!complete()) return "EXHAUSTED";
        double minimum = minimumFraction();
        if (minimum < 0.15D) return "CRITICAL";
        if (minimum < 0.35D) return "DEGRADED";
        return "OK";
    }

    public String compactStatus() {
        return String.format(Locale.ROOT, "Pre %.3f%% | HEPA %.3f%% | RAD %.3f%%",
                prefilterFraction() * 100.0D, hepaFraction() * 100.0D, radiologicalFraction() * 100.0D);
    }

    public String efficiencyStatus() {
        return String.format(Locale.ROOT, "%s | Dust eff %.3f%% | Rad eff %.3f%%",
                conditionLabel(), dustEfficiency() * 100.0D, radiationEfficiency() * 100.0D);
    }

    public void save(CompoundTag tag, String prefix) {
        tag.putInt(prefix + "PreFilter", prefilter);
        tag.putInt(prefix + "Hepa", hepa);
        tag.putInt(prefix + "Radiological", radiological);
    }

    public void load(CompoundTag tag, String prefix) {
        prefilter = Math.max(0, Math.min(MAX_PREFILTER, tag.getInt(prefix + "PreFilter")));
        hepa = Math.max(0, Math.min(MAX_HEPA, tag.getInt(prefix + "Hepa")));
        radiological = Math.max(0, Math.min(MAX_RAD, tag.getInt(prefix + "Radiological")));
    }
}
