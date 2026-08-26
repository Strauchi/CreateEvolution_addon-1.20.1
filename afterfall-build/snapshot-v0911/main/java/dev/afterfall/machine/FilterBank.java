package dev.afterfall.machine;

import dev.afterfall.content.ModItems;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.items.ItemStackHandler;

import java.util.Locale;

public final class FilterBank extends ItemStackHandler {
    public static final int SLOT_PREFILTER = 0;
    public static final int SLOT_HEPA = 1;
    public static final int SLOT_RAD = 2;

    public static final int MAX_PREFILTER = 36_000;
    public static final int MAX_HEPA = 48_000;
    public static final int MAX_RAD = 42_000;

    private final Runnable onChangedCallback;

    public FilterBank(Runnable onChanged) {
        super(3);
        this.onChangedCallback = onChanged == null ? () -> {} : onChanged;
    }

    @Override
    public boolean isItemValid(int slot, ItemStack stack) {
        return switch (slot) {
            case SLOT_PREFILTER -> stack.is(ModItems.PREFILTER_CARTRIDGE.get());
            case SLOT_HEPA -> stack.is(ModItems.HEPA_FILTER_CARTRIDGE.get());
            case SLOT_RAD -> stack.is(ModItems.RAD_FILTER_CARTRIDGE.get());
            default -> false;
        };
    }

    @Override
    public int getSlotLimit(int slot) {
        return 1;
    }

    @Override
    protected void onContentsChanged(int slot) {
        super.onContentsChanged(slot);
        onChangedCallback.run();
    }

    public static int slotFor(ItemStack stack) {
        if (stack.is(ModItems.PREFILTER_CARTRIDGE.get())) return SLOT_PREFILTER;
        if (stack.is(ModItems.HEPA_FILTER_CARTRIDGE.get())) return SLOT_HEPA;
        if (stack.is(ModItems.RAD_FILTER_CARTRIDGE.get())) return SLOT_RAD;
        return -1;
    }

    public boolean complete() {
        return remaining(SLOT_PREFILTER) > 0 && remaining(SLOT_HEPA) > 0 && remaining(SLOT_RAD) > 0;
    }

    public boolean installFromHeld(ServerPlayer player, ItemStack stack) {
        int slot = slotFor(stack);
        if (slot < 0 || !getStackInSlot(slot).isEmpty()) return false;
        ItemStack one = stack.copy();
        one.setCount(1);
        setStackInSlot(slot, one);
        if (!player.getAbilities().instabuild) stack.shrink(1);
        return true;
    }

    public void consume(int preWear, int hepaWear, int radWear) {
        consumeSlot(SLOT_PREFILTER, preWear);
        consumeSlot(SLOT_HEPA, hepaWear);
        consumeSlot(SLOT_RAD, radWear);
    }

    private void consumeSlot(int slot, int wear) {
        if (wear <= 0) return;
        ItemStack stack = getStackInSlot(slot);
        if (stack.isEmpty()) return;
        int max = stack.getMaxDamage();
        if (max <= 0) return;
        int damage = Math.min(max, stack.getDamageValue() + wear);
        if (damage >= max) {
            setStackInSlot(slot, ItemStack.EMPTY);
        } else {
            ItemStack changed = stack.copy();
            changed.setDamageValue(damage);
            setStackInSlot(slot, changed);
        }
    }

    private int remaining(int slot) {
        ItemStack stack = getStackInSlot(slot);
        if (stack.isEmpty()) return 0;
        int max = stack.getMaxDamage();
        if (max <= 0) return 0;
        return Math.max(0, max - stack.getDamageValue());
    }

    private double fraction(int slot) {
        ItemStack stack = getStackInSlot(slot);
        if (stack.isEmpty() || stack.getMaxDamage() <= 0) return 0.0D;
        return Math.max(0.0D, Math.min(1.0D,
                (stack.getMaxDamage() - stack.getDamageValue()) / (double) stack.getMaxDamage()));
    }

    public double prefilterFraction() { return fraction(SLOT_PREFILTER); }
    public double hepaFraction() { return fraction(SLOT_HEPA); }
    public double radiologicalFraction() { return fraction(SLOT_RAD); }

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
        return String.format(Locale.ROOT, "Pre %.1f%% | HEPA %.1f%% | RAD %.1f%%",
                prefilterFraction() * 100.0D, hepaFraction() * 100.0D, radiologicalFraction() * 100.0D);
    }

    public String efficiencyStatus() {
        return String.format(Locale.ROOT, "%s | Dust eff %.2f%% | Rad eff %.2f%%",
                conditionLabel(), dustEfficiency() * 100.0D, radiationEfficiency() * 100.0D);
    }

    public void save(CompoundTag tag, String prefix, HolderLookup.Provider registries) {
        tag.put(prefix + "Inventory", serializeNBT(registries));
    }

    public void load(CompoundTag tag, String prefix, HolderLookup.Provider registries) {
        if (tag.contains(prefix + "Inventory")) {
            deserializeNBT(registries, tag.getCompound(prefix + "Inventory"));
            return;
        }

        // Migration from 0.5.x/0.6.5 integer-only filter storage.
        loadLegacySlot(SLOT_PREFILTER, ModItems.PREFILTER_CARTRIDGE.get(), MAX_PREFILTER,
                tag.getInt(prefix + "PreFilter"));
        loadLegacySlot(SLOT_HEPA, ModItems.HEPA_FILTER_CARTRIDGE.get(), MAX_HEPA,
                tag.getInt(prefix + "Hepa"));
        loadLegacySlot(SLOT_RAD, ModItems.RAD_FILTER_CARTRIDGE.get(), MAX_RAD,
                tag.getInt(prefix + "Radiological"));
    }

    private void loadLegacySlot(int slot, Item item, int max, int remaining) {
        remaining = Math.max(0, Math.min(max, remaining));
        if (remaining <= 0) {
            setStackInSlot(slot, ItemStack.EMPTY);
            return;
        }
        ItemStack stack = new ItemStack(item);
        stack.setDamageValue(Math.max(0, Math.min(stack.getMaxDamage() - 1, max - remaining)));
        setStackInSlot(slot, stack);
    }
}
