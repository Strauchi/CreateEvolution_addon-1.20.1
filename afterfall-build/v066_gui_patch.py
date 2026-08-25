from pathlib import Path

ROOT = Path('Afterfall/src/main/java/dev/afterfall')
RES = Path('Afterfall/src/main/resources')


def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')

# -----------------------------------------------------------------------------
# FilterBank: real three-slot item inventory. Cartridge damage stores wear.
# -----------------------------------------------------------------------------
write('machine/FilterBank.java', r'''package dev.afterfall.machine;

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
''')

# -----------------------------------------------------------------------------
# Air filter / intake: persisted manual enable switch + real FilterBank inventory.
# -----------------------------------------------------------------------------
write('blockentity/AirFilterBlockEntity.java', r'''package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.machine.FilterBank;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomMachineUtil;
import dev.afterfall.room.RoomScanResult;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.Locale;

public final class AirFilterBlockEntity extends BlockEntity {
    public static final double FLOW_M3_PER_SECOND = 24.0D;
    public static final double TARGET_DUST = 0.10D;
    public static final double TARGET_AIRBORNE_MSV_H = 0.05D;
    public static final int ENERGY_CAPACITY = 50_000;
    public static final int ENERGY_PER_SECOND = 640;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private final FilterBank filters = new FilterBank(this::setChanged);
    private boolean enabled = true;

    public AirFilterBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.AIR_FILTER.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public FilterBank filters() { return filters; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }

    public boolean installFilter(ServerPlayer player, ItemStack held) {
        return filters.installFromHeld(player, held);
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, AirFilterBlockEntity blockEntity) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L) return;
        if (!blockEntity.enabled) return;

        RoomScanResult scan = RoomMachineUtil.findSealedAdjacentRoom(serverLevel, pos);
        if (scan == null || !blockEntity.filters.complete()) return;

        boolean wasteland = RoomEnvironmentManager.isWasteland(serverLevel, scan.anchor());
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere atmosphere = saved.getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), serverLevel.getGameTime());

        if (isClean(atmosphere)) return;
        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, blockEntity.energy, ENERGY_PER_SECOND)) return;

        double processedFraction = Math.min(0.35D, FLOW_M3_PER_SECOND / Math.max(1.0D, scan.volume()));
        atmosphere.filterAir(processedFraction, blockEntity.filters.dustEfficiency(), blockEntity.filters.radiationEfficiency());

        int preWear = Math.max(1, (int) Math.ceil(1.0D + atmosphere.dustPercent() / 12.0D));
        int hepaWear = Math.max(1, (int) Math.ceil(1.0D + atmosphere.dustPercent() / 28.0D));
        int radWear = Math.max(1, (int) Math.ceil(1.0D + atmosphere.airborneRadiationPerSecond() * 1800.0D));
        blockEntity.filters.consume(preWear, hepaWear, radWear);
        saved.markChanged();
    }

    public static boolean isClean(RoomAtmosphere atmosphere) {
        return atmosphere.dustPercent() <= TARGET_DUST
                && atmosphere.airborneRadiationPerSecond() * 3600.0D <= TARGET_AIRBORNE_MSV_H;
    }

    public static Component status(ServerLevel level, BlockPos pos) {
        if (!(level.getBlockEntity(pos) instanceof AirFilterBlockEntity be))
            return Component.literal("Air Filter: OFFLINE").withStyle(ChatFormatting.RED);
        if (!be.enabled) return Component.literal("Air Filter: SWITCHED OFF").withStyle(ChatFormatting.GRAY);
        RoomScanResult scan = RoomMachineUtil.findSealedAdjacentRoom(level, pos);
        boolean power = MachinePower.available(level, pos, be.energy, ENERGY_PER_SECOND);
        if (!power) return Component.literal(String.format(Locale.ROOT,
                "Air Filter: OFFLINE - NO POWER | %d/%d FE", be.energy.getEnergyStored(), be.energy.getMaxEnergyStored())).withStyle(ChatFormatting.RED);
        if (scan == null) return Component.literal("Air Filter: ERROR - NO SEALED ROOM").withStyle(ChatFormatting.RED);
        if (!be.filters.complete()) return Component.literal("Air Filter: FILTER MEDIA REQUIRED | " + be.filters.compactStatus()).withStyle(ChatFormatting.RED);

        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        RoomAtmosphere atmosphere = RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland), RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
        String mode = isClean(atmosphere) ? "STANDBY - AIR CLEAN" : "FILTERING";
        ChatFormatting color = isClean(atmosphere) ? ChatFormatting.GREEN : ChatFormatting.YELLOW;
        return Component.literal(String.format(Locale.ROOT,
                "Air Filter: %s | %.0f m³/s | Room %d m³ | Dust %.2f%% | Air Rad %.2f mSv/h | Power %d/%d FE (%s) | %s",
                mode, FLOW_M3_PER_SECOND, scan.volume(), atmosphere.dustPercent(), atmosphere.airborneRadiationPerSecond() * 3600.0D,
                be.energy.getEnergyStored(), be.energy.getMaxEnergyStored(), MachinePower.source(level, pos, be.energy), be.filters.compactStatus())).withStyle(color);
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        filters.load(tag, "Filter", registries);
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        filters.save(tag, "Filter", registries);
        tag.putBoolean("Enabled", enabled);
    }
}
''')

write('blockentity/AirIntakeBlockEntity.java', r'''package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.machine.FilterBank;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomMachineUtil;
import dev.afterfall.room.RoomScanResult;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.Locale;

public final class AirIntakeBlockEntity extends BlockEntity {
    public static final double FLOW_M3_PER_SECOND = 18.0D;
    public static final double TARGET_OXYGEN = 20.75D;
    public static final double TARGET_CO2 = 0.08D;
    public static final int ENERGY_CAPACITY = 40_000;
    public static final int ENERGY_PER_SECOND = 480;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private final FilterBank filters = new FilterBank(this::setChanged);
    private boolean enabled = true;

    public AirIntakeBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.AIR_INTAKE.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public FilterBank filters() { return filters; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }

    public boolean installFilter(ServerPlayer player, ItemStack held) {
        return filters.installFromHeld(player, held);
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, AirIntakeBlockEntity blockEntity) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L) return;
        if (!blockEntity.enabled) return;

        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(serverLevel, pos);
        RoomScanResult scan = connection.room();
        if (scan == null || !connection.outsideConnected() || !blockEntity.filters.complete()) return;

        boolean wasteland = RoomEnvironmentManager.isWasteland(serverLevel, pos);
        double outsideDust = RoomEnvironmentManager.outsideDust(wasteland);
        double outsideAirborne = RoomEnvironmentManager.outsideAirborneRadiation(wasteland);

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere atmosphere = saved.getOrCreate(scan.anchor().asLong(), scan.volume(), outsideDust, outsideAirborne, serverLevel.getGameTime());

        if (!needsFreshAir(atmosphere)) return;
        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, blockEntity.energy, ENERGY_PER_SECOND)) return;

        double exchangeFraction = Math.min(0.30D, FLOW_M3_PER_SECOND / Math.max(1.0D, scan.volume()));
        atmosphere.ventilateFiltered(outsideDust, outsideAirborne, exchangeFraction,
                blockEntity.filters.dustEfficiency(), blockEntity.filters.radiationEfficiency());

        int preWear = Math.max(1, (int) Math.ceil(1.0D + outsideDust / 14.0D));
        int hepaWear = Math.max(1, (int) Math.ceil(1.0D + outsideDust / 32.0D));
        int radWear = Math.max(1, (int) Math.ceil(1.0D + outsideAirborne * 900.0D));
        blockEntity.filters.consume(preWear, hepaWear, radWear);
        saved.markChanged();
    }

    public static boolean needsFreshAir(RoomAtmosphere atmosphere) {
        return atmosphere.oxygenPercent() < TARGET_OXYGEN || atmosphere.co2Percent() > TARGET_CO2;
    }

    public static Component status(ServerLevel level, BlockPos pos) {
        if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity be))
            return Component.literal("Air Intake: OFFLINE").withStyle(ChatFormatting.RED);
        if (!be.enabled) return Component.literal("Air Intake: SWITCHED OFF").withStyle(ChatFormatting.GRAY);
        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, pos);
        if (!MachinePower.available(level, pos, be.energy, ENERGY_PER_SECOND))
            return Component.literal(String.format(Locale.ROOT, "Air Intake: OFFLINE - NO POWER | %d/%d FE",
                    be.energy.getEnergyStored(), be.energy.getMaxEnergyStored())).withStyle(ChatFormatting.RED);
        if (connection.room() == null) return Component.literal("Air Intake: ERROR - NO SEALED ROOM").withStyle(ChatFormatting.RED);
        if (!connection.outsideConnected()) return Component.literal("Air Intake: ERROR - NO OUTSIDE CONNECTION").withStyle(ChatFormatting.RED);
        if (!be.filters.complete()) return Component.literal("Air Intake: FILTER MEDIA REQUIRED | " + be.filters.compactStatus()).withStyle(ChatFormatting.RED);

        RoomScanResult scan = connection.room();
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, pos);
        RoomAtmosphere atmosphere = RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland), RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
        String mode = needsFreshAir(atmosphere) ? "VENTILATING" : "STANDBY - AIR BALANCED";
        ChatFormatting color = needsFreshAir(atmosphere) ? ChatFormatting.YELLOW : ChatFormatting.GREEN;
        return Component.literal(String.format(Locale.ROOT,
                "Air Intake: %s | %.0f m³/s | Room %d m³ | O2 %.2f%% | CO2 %.2f%% | Dust %.2f%% | Power %d/%d FE (%s) | %s",
                mode, FLOW_M3_PER_SECOND, scan.volume(), atmosphere.oxygenPercent(), atmosphere.co2Percent(), atmosphere.dustPercent(),
                be.energy.getEnergyStored(), be.energy.getMaxEnergyStored(), MachinePower.source(level, pos, be.energy), be.filters.compactStatus())).withStyle(color);
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        filters.load(tag, "Filter", registries);
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        filters.save(tag, "Filter", registries);
        tag.putBoolean("Enabled", enabled);
    }
}
''')

# -----------------------------------------------------------------------------
# Emergency generator: real fuel slot, persisted inventory and on/off control.
# -----------------------------------------------------------------------------
write('blockentity/EmergencyGeneratorBlockEntity.java', r'''package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.machine.MachineEnergyStorage;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.energy.IEnergyStorage;
import net.neoforged.neoforge.items.ItemStackHandler;

import java.util.Locale;

public final class EmergencyGeneratorBlockEntity extends BlockEntity {
    public static final int ENERGY_CAPACITY = 100_000;
    public static final int GENERATION_PER_TICK = 80;
    public static final int MAX_OUTPUT_PER_TICK = 400;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 1_000, MAX_OUTPUT_PER_TICK, this::setChanged);
    private final ItemStackHandler inventory = new ItemStackHandler(1) {
        @Override public boolean isItemValid(int slot, ItemStack stack) { return slot == 0 && isFuel(stack); }
        @Override protected void onContentsChanged(int slot) { super.onContentsChanged(slot); EmergencyGeneratorBlockEntity.this.setChanged(); }
    };
    private int burnTicks;
    private boolean enabled = true;

    public EmergencyGeneratorBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.EMERGENCY_GENERATOR.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public ItemStackHandler inventory() { return inventory; }
    public int burnTicks() { return burnTicks; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }

    public static boolean isFuel(ItemStack stack) {
        return stack.is(Items.COAL) || stack.is(Items.CHARCOAL) || stack.is(Items.COAL_BLOCK);
    }

    private static int fuelTicks(ItemStack stack) {
        if (stack.is(Items.COAL) || stack.is(Items.CHARCOAL)) return 1600;
        if (stack.is(Items.COAL_BLOCK)) return 16000;
        return 0;
    }

    /** Legacy quick-load helper retained for compatibility, but GUI is the normal path. */
    public boolean addFuel(ServerPlayer player, ItemStack held) {
        if (!isFuel(held)) return false;
        ItemStack one = held.copy();
        one.setCount(1);
        ItemStack remainder = inventory.insertItem(0, one, false);
        if (!remainder.isEmpty()) return false;
        if (!player.getAbilities().instabuild) held.shrink(1);
        return true;
    }

    private void startFuelIfNeeded() {
        if (!enabled || burnTicks > 0 || energy.getEnergyStored() >= energy.getMaxEnergyStored()) return;
        ItemStack fuel = inventory.getStackInSlot(0);
        int ticks = fuelTicks(fuel);
        if (ticks <= 0) return;
        ItemStack remainder = fuel.copy();
        remainder.shrink(1);
        inventory.setStackInSlot(0, remainder);
        burnTicks = ticks;
        setChanged();
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, EmergencyGeneratorBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || !be.enabled) return;

        be.startFuelIfNeeded();
        if (be.burnTicks > 0 && be.energy.getEnergyStored() < be.energy.getMaxEnergyStored()) {
            be.burnTicks--;
            be.energy.addEnergyInternal(GENERATION_PER_TICK);
            if (be.burnTicks % 20 == 0) be.setChanged();
        }

        if (be.energy.getEnergyStored() <= 0) return;
        int remainingBudget = MAX_OUTPUT_PER_TICK;
        for (Direction direction : Direction.values()) {
            if (remainingBudget <= 0 || be.energy.getEnergyStored() <= 0) break;
            BlockPos targetPos = pos.relative(direction);
            IEnergyStorage target = serverLevel.getCapability(Capabilities.EnergyStorage.BLOCK, targetPos, direction.getOpposite());
            if (target == null || !target.canReceive()) continue;
            int offer = Math.min(remainingBudget, be.energy.getEnergyStored());
            int accepted = target.receiveEnergy(offer, false);
            if (accepted > 0) {
                be.energy.extractEnergy(accepted, false);
                remainingBudget -= accepted;
            }
        }
    }

    public static Component status(ServerLevel level, BlockPos pos) {
        if (!(level.getBlockEntity(pos) instanceof EmergencyGeneratorBlockEntity be))
            return Component.literal("Emergency Generator: OFFLINE").withStyle(ChatFormatting.RED);
        if (!be.enabled) return Component.literal("Emergency Generator: SWITCHED OFF").withStyle(ChatFormatting.GRAY);
        String mode = be.burnTicks > 0 ? "RUNNING" : (be.energy.getEnergyStored() > 0 ? "BUFFERED" : "NO FUEL");
        ChatFormatting color = be.burnTicks > 0 ? ChatFormatting.GREEN : ChatFormatting.YELLOW;
        return Component.literal(String.format(Locale.ROOT,
                "Emergency Generator: %s | %d/%d FE | %.0f FE/t | Fuel %.1f s | Output max %d FE/t",
                mode, be.energy.getEnergyStored(), be.energy.getMaxEnergyStored(), (double) GENERATION_PER_TICK,
                be.burnTicks / 20.0D, MAX_OUTPUT_PER_TICK)).withStyle(color);
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        burnTicks = Math.max(0, tag.getInt("BurnTicks"));
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
        if (tag.contains("Inventory")) inventory.deserializeNBT(registries, tag.getCompound("Inventory"));
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        tag.putInt("BurnTicks", burnTicks);
        tag.putBoolean("Enabled", enabled);
        tag.put("Inventory", inventory.serializeNBT(registries));
    }
}
''')

# -----------------------------------------------------------------------------
# Interactive menu with real machine slots + player inventory + server buttons.
# -----------------------------------------------------------------------------
write('menu/MachineMenu.java', r'''package dev.afterfall.menu;

import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.AirlockLogic;
import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;
import dev.afterfall.content.ModItems;
import dev.afterfall.content.ModMenus;
import dev.afterfall.machine.FilterBank;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomMachineUtil;
import dev.afterfall.room.RoomScanResult;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.SimpleContainerData;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.neoforged.neoforge.items.IItemHandler;
import net.neoforged.neoforge.items.ItemStackHandler;
import net.neoforged.neoforge.items.SlotItemHandler;

public final class MachineMenu extends AbstractContainerMenu {
    public static final int DATA_COUNT = 18;

    public static final int TYPE_FILTER = 0;
    public static final int TYPE_INTAKE = 1;
    public static final int TYPE_AIRLOCK = 2;
    public static final int TYPE_GENERATOR = 3;

    public static final int BUTTON_POWER = 0;
    public static final int BUTTON_ACTION = 1;

    public static final int D_TYPE = 0;
    public static final int D_ENERGY = 1;
    public static final int D_ENERGY_MAX = 2;
    public static final int D_STATUS = 3;
    public static final int D_PRE = 4;
    public static final int D_HEPA = 5;
    public static final int D_RAD = 6;
    public static final int D_ROOM_VOLUME = 7;
    public static final int D_DUST_X100 = 8;
    public static final int D_AIR_RAD_X100 = 9;
    public static final int D_O2_X100 = 10;
    public static final int D_CO2_X100 = 11;
    public static final int D_AIR_QUALITY_X10 = 12;
    public static final int D_FLOW_X10 = 13;
    public static final int D_EXTRA = 14;
    public static final int D_POWER_SOURCE = 15;
    public static final int D_FILTER_CONDITION = 16;
    public static final int D_ENABLED = 17;

    public static final int FILTER_SLOT_Y = 95;
    public static final int[] FILTER_SLOT_X = {24, 104, 184};
    public static final int FUEL_SLOT_X = 24;
    public static final int FUEL_SLOT_Y = 95;
    public static final int PLAYER_INV_X = 41;
    public static final int PLAYER_INV_Y = 220;
    public static final int HOTBAR_Y = 280;

    private final SimpleContainerData data = new SimpleContainerData(DATA_COUNT);
    private final BlockPos blockPos;
    private final BlockEntity serverBlockEntity;
    private final int machineType;
    private final int machineSlotCount;

    public MachineMenu(int containerId, Inventory inventory, RegistryFriendlyByteBuf buf) {
        this(containerId, inventory, buf.readBlockPos(), null, buf.readVarInt());
    }

    public MachineMenu(int containerId, Inventory inventory, BlockPos pos, BlockEntity blockEntity) {
        this(containerId, inventory, pos, blockEntity, typeOf(blockEntity));
    }

    private MachineMenu(int containerId, Inventory inventory, BlockPos pos, BlockEntity blockEntity, int machineType) {
        super(ModMenus.MACHINE.get(), containerId);
        this.blockPos = pos.immutable();
        this.serverBlockEntity = blockEntity;
        this.machineType = machineType;
        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1 : 3;

        IItemHandler machineHandler = handlerFor(blockEntity, machineType);
        if (machineType == TYPE_GENERATOR) {
            addSlot(new SlotItemHandler(machineHandler, 0, FUEL_SLOT_X, FUEL_SLOT_Y));
        } else {
            for (int i = 0; i < 3; i++) addSlot(new SlotItemHandler(machineHandler, i, FILTER_SLOT_X[i], FILTER_SLOT_Y));
        }

        // Player inventory 3x9 + hotbar.
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                addSlot(new Slot(inventory, col + row * 9 + 9,
                        PLAYER_INV_X + col * 18, PLAYER_INV_Y + row * 18));
            }
        }
        for (int col = 0; col < 9; col++) {
            addSlot(new Slot(inventory, col, PLAYER_INV_X + col * 18, HOTBAR_Y));
        }

        addDataSlots(data);
        if (serverBlockEntity != null) updateServerData();
    }

    public static int typeOf(BlockEntity blockEntity) {
        if (blockEntity instanceof AirIntakeBlockEntity) return TYPE_INTAKE;
        if (blockEntity instanceof AirlockControllerBlockEntity) return TYPE_AIRLOCK;
        if (blockEntity instanceof EmergencyGeneratorBlockEntity) return TYPE_GENERATOR;
        return TYPE_FILTER;
    }

    private static IItemHandler handlerFor(BlockEntity blockEntity, int type) {
        if (blockEntity instanceof AirFilterBlockEntity be) return be.filters();
        if (blockEntity instanceof AirIntakeBlockEntity be) return be.filters();
        if (blockEntity instanceof AirlockControllerBlockEntity be) return be.filters();
        if (blockEntity instanceof EmergencyGeneratorBlockEntity be) return be.inventory();
        if (type == TYPE_GENERATOR) {
            return new ItemStackHandler(1) {
                @Override public boolean isItemValid(int slot, ItemStack stack) {
                    return slot == 0 && EmergencyGeneratorBlockEntity.isFuel(stack);
                }
            };
        }
        return new FilterBank(null);
    }

    @Override
    public void broadcastChanges() {
        if (serverBlockEntity != null) updateServerData();
        super.broadcastChanges();
    }

    private void updateServerData() {
        if (!(serverBlockEntity.getLevel() instanceof ServerLevel level)) return;
        for (int i = 0; i < DATA_COUNT; i++) data.set(i, 0);

        if (serverBlockEntity instanceof AirFilterBlockEntity be) {
            data.set(D_TYPE, TYPE_FILTER);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_FLOW_X10, scale(AirFilterBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomScanResult scan = RoomMachineUtil.findSealedAdjacentRoom(level, blockPos);
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirFilterBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!be.filters().complete()) data.set(D_STATUS, 3);
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirFilterBlockEntity.isClean(atmosphere) ? 5 : 4);
                setAtmosphere(scan, atmosphere);
            }
            if (scan != null && get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof AirIntakeBlockEntity be) {
            data.set(D_TYPE, TYPE_INTAKE);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_FLOW_X10, scale(AirIntakeBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, blockPos);
            RoomScanResult scan = connection.room();
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirIntakeBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!be.filters().complete()) data.set(D_STATUS, 3);
            else if (!connection.outsideConnected()) data.set(D_STATUS, 6);
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirIntakeBlockEntity.needsFreshAir(atmosphere) ? 7 : 5);
                setAtmosphere(scan, atmosphere);
            }
            if (scan != null && get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {
            data.set(D_TYPE, TYPE_AIRLOCK);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_EXTRA, be.cycleState().ordinal());
            AirlockLogic.AirlockStatus status = AirlockLogic.inspectStatus(level, blockPos);
            data.set(D_STATUS, !be.enabled() ? 17 : airlockStatusCode(be, status));
            if (status.hasAtmosphere()) setAtmosphere(status.scan(), status.atmosphere());
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) {
            data.set(D_TYPE, TYPE_GENERATOR);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            data.set(D_STATUS, !be.enabled() ? 17 : (be.burnTicks() > 0 ? 8 : (be.energyStorage().getEnergyStored() > 0 ? 9 : 10)));
            data.set(D_FLOW_X10, EmergencyGeneratorBlockEntity.GENERATION_PER_TICK * 10);
            data.set(D_EXTRA, be.burnTicks());
            data.set(D_POWER_SOURCE, 3);
        }
    }

    private int airlockStatusCode(AirlockControllerBlockEntity be, AirlockLogic.AirlockStatus status) {
        if (be.isBusy()) return 20 + be.cycleState().ordinal();
        return switch (status.type()) {
            case NOT_CONFIGURED -> 11;
            case DOOR_OPEN -> 12;
            case NO_SEALED_CHAMBER -> 13;
            case CHAMBER_TOO_LARGE -> 14;
            case UNSAFE_NO_POWER -> 1;
            case FILTER_REQUIRED -> 3;
            case SAFE -> 16;
            default -> 15;
        };
    }

    @Override
    public boolean clickMenuButton(Player player, int id) {
        if (!(player instanceof ServerPlayer serverPlayer) || serverBlockEntity == null
                || !(serverBlockEntity.getLevel() instanceof ServerLevel level)) return false;

        if (id == BUTTON_POWER) {
            if (serverBlockEntity instanceof AirFilterBlockEntity be) be.setEnabled(!be.enabled());
            else if (serverBlockEntity instanceof AirIntakeBlockEntity be) be.setEnabled(!be.enabled());
            else if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) be.setEnabled(!be.enabled());
            else if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {
                if (!be.setEnabled(!be.enabled())) {
                    serverPlayer.displayClientMessage(Component.literal("AIRLOCK: CANNOT POWER OFF DURING ACTIVE CYCLE"), true);
                    return false;
                }
            } else return false;
            updateServerData();
            return true;
        }

        if (id == BUTTON_ACTION && serverBlockEntity instanceof AirlockControllerBlockEntity be) {
            if (!be.enabled()) {
                serverPlayer.displayClientMessage(Component.literal("AIRLOCK: CONTROLLER IS SWITCHED OFF"), true);
                return false;
            }
            return be.requestFromController(level, serverPlayer);
        }
        return false;
    }

    private void setEnergy(int stored, int max) {
        data.set(D_ENERGY, stored / 10);
        data.set(D_ENERGY_MAX, Math.max(1, max / 10));
    }

    private void setFilters(double pre, double hepa, double rad, String condition) {
        data.set(D_PRE, scale(pre * 100.0D, 10.0D));
        data.set(D_HEPA, scale(hepa * 100.0D, 10.0D));
        data.set(D_RAD, scale(rad * 100.0D, 10.0D));
        data.set(D_FILTER_CONDITION, switch (condition) {
            case "EXHAUSTED" -> 3;
            case "CRITICAL" -> 2;
            case "DEGRADED" -> 1;
            default -> 0;
        });
    }

    private void setAtmosphere(RoomScanResult scan, RoomAtmosphere atmosphere) {
        data.set(D_ROOM_VOLUME, scan.volume());
        data.set(D_DUST_X100, scale(atmosphere.dustPercent(), 100.0D));
        data.set(D_AIR_RAD_X100, scale(atmosphere.airborneRadiationPerSecond() * 3600.0D, 100.0D));
        data.set(D_O2_X100, scale(atmosphere.oxygenPercent(), 100.0D));
        data.set(D_CO2_X100, scale(atmosphere.co2Percent(), 100.0D));
        data.set(D_AIR_QUALITY_X10, scale(atmosphere.airQualityPercent(), 10.0D));
    }

    private static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        return RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland), RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
    }

    private static int powerSource(ServerLevel level, BlockPos pos, dev.afterfall.machine.MachineEnergyStorage storage) {
        String source = MachinePower.source(level, pos, storage);
        if ("FE".equals(source)) return 1;
        if (source.startsWith("REDSTONE")) return 2;
        return 0;
    }

    private static int scale(double value, double multiplier) {
        return (int) Math.round(Math.max(0.0D, Math.min(2_000_000.0D, value * multiplier)));
    }

    public BlockPos blockPos() { return blockPos; }
    public int machineType() { return machineType; }
    public int machineSlotCount() { return machineSlotCount; }
    public int get(int index) { return data.get(index); }
    public boolean enabled() { return get(D_ENABLED) != 0; }
    public double prePercent() { return get(D_PRE) / 10.0D; }
    public double hepaPercent() { return get(D_HEPA) / 10.0D; }
    public double radPercent() { return get(D_RAD) / 10.0D; }
    public double dustPercent() { return get(D_DUST_X100) / 100.0D; }
    public double airRadiation() { return get(D_AIR_RAD_X100) / 100.0D; }
    public double oxygenPercent() { return get(D_O2_X100) / 100.0D; }
    public double co2Percent() { return get(D_CO2_X100) / 100.0D; }
    public double airQuality() { return get(D_AIR_QUALITY_X10) / 10.0D; }
    public double flow() { return get(D_FLOW_X10) / 10.0D; }

    @Override
    public boolean stillValid(Player player) {
        return player.distanceToSqr(blockPos.getX() + 0.5D, blockPos.getY() + 0.5D, blockPos.getZ() + 0.5D) <= 64.0D;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        Slot slot = getSlot(index);
        if (!slot.hasItem()) return ItemStack.EMPTY;
        ItemStack stack = slot.getItem();
        ItemStack original = stack.copy();
        int playerStart = machineSlotCount;
        int playerEnd = playerStart + 36;

        if (index < machineSlotCount) {
            if (!moveItemStackTo(stack, playerStart, playerEnd, true)) return ItemStack.EMPTY;
        } else {
            boolean movedToMachine = false;
            if (machineType == TYPE_GENERATOR && EmergencyGeneratorBlockEntity.isFuel(stack)) {
                movedToMachine = moveItemStackTo(stack, 0, 1, false);
            } else if (machineType != TYPE_GENERATOR) {
                int target = FilterBank.slotFor(stack);
                if (target >= 0) movedToMachine = moveItemStackTo(stack, target, target + 1, false);
            }
            if (!movedToMachine) {
                int mainEnd = playerStart + 27;
                if (index < mainEnd) {
                    if (!moveItemStackTo(stack, mainEnd, playerEnd, false)) return ItemStack.EMPTY;
                } else {
                    if (!moveItemStackTo(stack, playerStart, mainEnd, false)) return ItemStack.EMPTY;
                }
            }
        }

        if (stack.isEmpty()) slot.set(ItemStack.EMPTY); else slot.setChanged();
        if (stack.getCount() == original.getCount()) return ItemStack.EMPTY;
        slot.onTake(player, stack);
        return original;
    }
}
''')

# -----------------------------------------------------------------------------
# Screen: fixed energy layout, real slots, player inventory, ON/OFF + airlock action.
# -----------------------------------------------------------------------------
write('client/MachineScreen.java', r'''package dev.afterfall.client;

import dev.afterfall.menu.MachineMenu;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;

import java.util.Locale;

public final class MachineScreen extends AbstractContainerScreen<MachineMenu> {
    private static final int PANEL_W = 244;
    private static final int PANEL_H = 304;
    private Button powerButton;
    private Button actionButton;

    public MachineScreen(MachineMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title);
        this.imageWidth = PANEL_W;
        this.imageHeight = PANEL_H;
        this.inventoryLabelY = 10_000;
    }

    @Override
    protected void init() {
        super.init();
        powerButton = addRenderableWidget(Button.builder(Component.literal("POWER"), b -> sendButton(MachineMenu.BUTTON_POWER))
                .bounds(leftPos + 166, topPos + 26, 66, 18).build());
        if (menu.machineType() == MachineMenu.TYPE_AIRLOCK) {
            actionButton = addRenderableWidget(Button.builder(Component.literal("START CYCLE"), b -> sendButton(MachineMenu.BUTTON_ACTION))
                    .bounds(leftPos + 166, topPos + 48, 66, 18).build());
        }
    }

    private void sendButton(int id) {
        if (minecraft != null && minecraft.gameMode != null) {
            minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
        }
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        updateButtons();
        renderBackground(graphics, mouseX, mouseY, partialTick);
        super.render(graphics, mouseX, mouseY, partialTick);
        renderTooltip(graphics, mouseX, mouseY);
    }

    private void updateButtons() {
        if (powerButton != null) {
            powerButton.setMessage(Component.literal(menu.enabled() ? "POWER: ON" : "POWER: OFF"));
            powerButton.active = !(menu.machineType() == MachineMenu.TYPE_AIRLOCK && menu.get(MachineMenu.D_STATUS) >= 20 && menu.enabled());
        }
        if (actionButton != null) {
            boolean busy = menu.get(MachineMenu.D_STATUS) >= 20;
            actionButton.setMessage(Component.literal(busy ? "CYCLE BUSY" : "PURGE/CYCLE"));
            actionButton.active = menu.enabled() && !busy;
        }
    }

    @Override
    protected void renderBg(GuiGraphics graphics, float partialTick, int mouseX, int mouseY) {
        int x = leftPos;
        int y = topPos;
        graphics.fill(x, y, x + imageWidth, y + imageHeight, 0xE614181A);
        graphics.fill(x + 1, y + 1, x + imageWidth - 1, y + 22, 0xFF242B2E);
        graphics.fill(x + 7, y + 30, x + imageWidth - 7, y + imageHeight - 8, 0xCC0B0E10);

        drawEnergyBar(graphics, x + 12, y + 75, 140, 9);

        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            drawSlotBox(graphics, x + MachineMenu.FUEL_SLOT_X, y + MachineMenu.FUEL_SLOT_Y);
        } else {
            for (int i = 0; i < 3; i++) drawSlotBox(graphics, x + MachineMenu.FILTER_SLOT_X[i], y + MachineMenu.FILTER_SLOT_Y);
            drawFilterBar(graphics, x + 12, y + 116, 60, menu.prePercent());
            drawFilterBar(graphics, x + 92, y + 116, 60, menu.hepaPercent());
            drawFilterBar(graphics, x + 172, y + 116, 60, menu.radPercent());
        }

        // Player inventory slot backgrounds.
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                drawSlotBox(graphics, x + MachineMenu.PLAYER_INV_X + col * 18, y + MachineMenu.PLAYER_INV_Y + row * 18);
            }
        }
        for (int col = 0; col < 9; col++) drawSlotBox(graphics, x + MachineMenu.PLAYER_INV_X + col * 18, y + MachineMenu.HOTBAR_Y);
    }

    @Override
    protected void renderLabels(GuiGraphics graphics, int mouseX, int mouseY) {
        graphics.drawString(font, machineTitle(), 9, 8, 0xFFE8ECEE, false);
        graphics.drawString(font, statusText(), 12, 29, statusColor(), false);

        int stored = menu.get(MachineMenu.D_ENERGY) * 10;
        int max = Math.max(10, menu.get(MachineMenu.D_ENERGY_MAX) * 10);
        graphics.drawString(font, String.format(Locale.ROOT, "Energy: %,d / %,d FE", stored, max), 12, 50, 0xFFB7C4C8, false);
        graphics.drawString(font, "Source: " + powerSource(), 12, 63, 0xFF829399, false);

        if (menu.machineType() == MachineMenu.TYPE_GENERATOR) {
            renderGenerator(graphics);
        } else {
            renderFilters(graphics);
        }
        graphics.drawString(font, "INVENTORY", 12, 207, 0xFF7F9298, false);
    }

    private void renderFilters(GuiGraphics graphics) {
        graphics.drawString(font, "Pre-Filter", 12, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, "HEPA", 92, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, "RAD", 172, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.prePercent()), 12, 126, filterColor(menu.prePercent()), false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.hepaPercent()), 92, 126, filterColor(menu.hepaPercent()), false);
        graphics.drawString(font, String.format(Locale.ROOT, "%.1f%%", menu.radPercent()), 172, 126, filterColor(menu.radPercent()), false);
        graphics.drawString(font, "Filter condition: " + filterCondition(), 12, 140, filterConditionColor(), false);

        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        if (volume > 0) {
            graphics.drawString(font, "Room: " + volume + " m³", 12, 155, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 124, 155, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 12, 168, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 124, 168, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%%", menu.oxygenPercent()), 12, 181, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "CO2: %.2f%%", menu.co2Percent()), 124, 181, 0xFFD3DDDF, false);
        }
        if (menu.machineType() == MachineMenu.TYPE_FILTER || menu.machineType() == MachineMenu.TYPE_INTAKE) {
            graphics.drawString(font, String.format(Locale.ROOT, "Rated airflow: %.1f m³/s", menu.flow()), 12, 194, 0xFF7F9298, false);
        } else if (menu.machineType() == MachineMenu.TYPE_AIRLOCK) {
            graphics.drawString(font, "Cycle: " + airlockCycle(), 12, 194, 0xFF7F9298, false);
        }
    }

    private void renderGenerator(GuiGraphics graphics) {
        graphics.drawString(font, "Fuel", 12, 86, 0xFFAAB6B9, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Generation: %.0f FE/t", menu.flow()), 54, 96, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Burn remaining: %.1f s", menu.get(MachineMenu.D_EXTRA) / 20.0D), 54, 109, 0xFFD3DDDF, false);
        graphics.drawString(font, "Accepted: coal / charcoal / coal block", 12, 130, 0xFF7F9298, false);
        graphics.drawString(font, "Fuel is consumed automatically from the slot.", 12, 143, 0xFF7F9298, false);
    }

    private void drawSlotBox(GuiGraphics graphics, int x, int y) {
        graphics.fill(x - 1, y - 1, x + 17, y + 17, 0xFF4A5255);
        graphics.fill(x, y, x + 16, y + 16, 0xFF171B1D);
    }

    private void drawEnergyBar(GuiGraphics graphics, int x, int y, int width, int height) {
        int stored = menu.get(MachineMenu.D_ENERGY);
        int max = Math.max(1, menu.get(MachineMenu.D_ENERGY_MAX));
        int fill = (int) Math.round(width * Math.min(1.0D, stored / (double) max));
        graphics.fill(x, y, x + width, y + height, 0xFF24282A);
        if (fill > 0) graphics.fill(x + 1, y + 1, x + Math.max(1, fill - 1), y + height - 1, 0xFFB7C05C);
    }

    private void drawFilterBar(GuiGraphics graphics, int x, int y, int width, double percent) {
        int fill = (int) Math.round(width * Math.max(0.0D, Math.min(100.0D, percent)) / 100.0D);
        graphics.fill(x, y, x + width, y + 7, 0xFF24282A);
        int color = percent < 10.0D ? 0xFFC84C4C : percent < 25.0D ? 0xFFD79747 : 0xFF6FAE78;
        if (fill > 0) graphics.fill(x + 1, y + 1, x + Math.max(1, fill - 1), y + 6, color);
    }

    private String machineTitle() {
        return switch (menu.machineType()) {
            case MachineMenu.TYPE_INTAKE -> "AFTERFALL // AIR INTAKE UNIT";
            case MachineMenu.TYPE_AIRLOCK -> "AFTERFALL // AIRLOCK CONTROLLER";
            case MachineMenu.TYPE_GENERATOR -> "AFTERFALL // EMERGENCY GENERATOR";
            default -> "AFTERFALL // AIR FILTRATION UNIT";
        };
    }

    private String statusText() {
        int status = menu.get(MachineMenu.D_STATUS);
        if (status >= 20) return "CYCLE: " + airlockCycle();
        return switch (status) {
            case 1 -> "OFFLINE - NO POWER";
            case 2 -> "ERROR - NO SEALED ROOM";
            case 3 -> "FILTER MEDIA REQUIRED";
            case 4 -> "FILTERING";
            case 5 -> "STANDBY";
            case 6 -> "ERROR - NO OUTSIDE CONNECTION";
            case 7 -> "VENTILATING";
            case 8 -> "RUNNING";
            case 9 -> "BUFFERED";
            case 10 -> "NO FUEL";
            case 11 -> "NOT CONFIGURED";
            case 12 -> "DOOR OPEN / INTERLOCK";
            case 13 -> "CHAMBER NOT SEALED";
            case 14 -> "CHAMBER TOO LARGE";
            case 15 -> "UNSAFE - READY TO PURGE";
            case 16 -> "SAFE TO OPEN";
            case 17 -> "SWITCHED OFF";
            default -> "INITIALIZING";
        };
    }

    private int statusColor() {
        int status = menu.get(MachineMenu.D_STATUS);
        if (status == 17) return 0xFF8A979B;
        if (status == 5 || status == 8 || status == 9 || status == 16) return 0xFF66C477;
        if (status == 4 || status == 7 || status >= 20) return 0xFFE1B45A;
        return 0xFFDF6262;
    }

    private String powerSource() {
        return switch (menu.get(MachineMenu.D_POWER_SOURCE)) {
            case 1 -> "FE";
            case 2 -> "REDSTONE LEGACY";
            case 3 -> "INTERNAL";
            default -> "NONE";
        };
    }

    private String filterCondition() {
        return switch (menu.get(MachineMenu.D_FILTER_CONDITION)) {
            case 1 -> "DEGRADED";
            case 2 -> "CRITICAL";
            case 3 -> "EXHAUSTED";
            default -> "OK";
        };
    }

    private int filterConditionColor() {
        return switch (menu.get(MachineMenu.D_FILTER_CONDITION)) {
            case 1 -> 0xFFE1B45A;
            case 2, 3 -> 0xFFDF6262;
            default -> 0xFF66C477;
        };
    }

    private int filterColor(double percent) {
        return percent < 10.0D ? 0xFFDF6262 : percent < 25.0D ? 0xFFE1B45A : 0xFF66C477;
    }

    private String airlockCycle() {
        int state = menu.get(MachineMenu.D_EXTRA);
        String[] labels = {"IDLE", "PREPARING ENTRY", "WAITING FOR ENTRY", "SEALING ENTRY", "PURGING", "OPENING EXIT", "WAITING FOR EXIT", "SEALING EXIT"};
        return state >= 0 && state < labels.length ? labels[state] : "UNKNOWN";
    }
}
''')

# -----------------------------------------------------------------------------
# Small textual migrations/patches in the remaining source.
# -----------------------------------------------------------------------------

# Filter cartridges become single-stack damageable items; damage = used filter life.
p = ROOT / 'content/ModItems.java'
s = p.read_text(encoding='utf-8')
if 'import dev.afterfall.machine.FilterBank;' not in s:
    s = s.replace('import dev.afterfall.item.RadAwayItem;\n', 'import dev.afterfall.item.RadAwayItem;\nimport dev.afterfall.machine.FilterBank;\n')
s = s.replace('new Item(new Item.Properties().stacksTo(16)))', 'new Item(new Item.Properties().durability(FilterBank.MAX_PREFILTER)))', 1)
s = s.replace('new Item(new Item.Properties().stacksTo(16)))', 'new Item(new Item.Properties().durability(FilterBank.MAX_HEPA)))', 1)
s = s.replace('new Item(new Item.Properties().stacksTo(16)))', 'new Item(new Item.Properties().durability(FilterBank.MAX_RAD)))', 1)
p.write_text(s, encoding='utf-8')

# Airlock: enable switch, new FilterBank serialization, disabled requests.
p = ROOT / 'blockentity/AirlockControllerBlockEntity.java'
s = p.read_text(encoding='utf-8')
s = s.replace('private final FilterBank filters = new FilterBank(this::setChanged);\n',
              'private final FilterBank filters = new FilterBank(this::setChanged);\n    private boolean enabled = true;\n')
s = s.replace('public int stateTicks() { return stateTicks; }\n',
              '''public int stateTicks() { return stateTicks; }\n    public boolean enabled() { return enabled; }\n    public boolean setEnabled(boolean enabled) {\n        if (!enabled && isBusy()) return false;\n        if (this.enabled != enabled) { this.enabled = enabled; setChanged(); }\n        return true;\n    }\n''')
s = s.replace('public boolean requestCycle(ServerLevel level, BlockPos requestedEntryDoor, ServerPlayer requester) {\n        if (isBusy()) {',
              'public boolean requestCycle(ServerLevel level, BlockPos requestedEntryDoor, ServerPlayer requester) {\n        if (!enabled) { requester.displayClientMessage(Component.literal("AIRLOCK: CONTROLLER SWITCHED OFF").withStyle(ChatFormatting.RED), true); return false; }\n        if (isBusy()) {')
s = s.replace('public boolean requestFromController(ServerLevel level, ServerPlayer requester) {\n        if (isBusy()) {',
              'public boolean requestFromController(ServerLevel level, ServerPlayer requester) {\n        if (!enabled) { requester.displayClientMessage(Component.literal("AIRLOCK: CONTROLLER SWITCHED OFF").withStyle(ChatFormatting.RED), true); return false; }\n        if (isBusy()) {')
s = s.replace('private void tickCycle(ServerLevel level) {\n        if (cycleState == CycleState.IDLE) {',
              'private void tickCycle(ServerLevel level) {\n        if (!enabled && cycleState == CycleState.IDLE) return;\n        if (cycleState == CycleState.IDLE) {')
s = s.replace('filters.load(tag, "Filter");', 'filters.load(tag, "Filter", registries);')
s = s.replace('filters.save(tag, "Filter");', 'filters.save(tag, "Filter", registries);')
s = s.replace('energy.setEnergyStored(tag.getInt("Energy"));\n        filters.load(tag, "Filter", registries);',
              'energy.setEnergyStored(tag.getInt("Energy"));\n        filters.load(tag, "Filter", registries);\n        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");')
s = s.replace('tag.putInt("Energy", energy.getEnergyStored());\n        filters.save(tag, "Filter", registries);',
              'tag.putInt("Energy", energy.getEnergyStored());\n        filters.save(tag, "Filter", registries);\n        tag.putBoolean("Enabled", enabled);')
p.write_text(s, encoding='utf-8')

# Menu opening now sends machine type. Generator always opens its real fuel-slot GUI.
p = ROOT / 'event/CommonEvents.java'
s = p.read_text(encoding='utf-8')
old_gen = '''                if (blockEntity instanceof EmergencyGeneratorBlockEntity generator) {\n                    if (generator.addFuel(player, player.getMainHandItem())) {\n                        player.displayClientMessage(Component.literal("Emergency Generator: fuel added").withStyle(ChatFormatting.GREEN), true);\n                    } else {\n                        openMachineMenu(player, event.getPos(), generator, Component.literal("Emergency Generator"));\n                    }\n                }'''
new_gen = '''                if (blockEntity instanceof EmergencyGeneratorBlockEntity generator) {\n                    openMachineMenu(player, event.getPos(), generator, Component.literal("Emergency Generator"));\n                }'''
if old_gen not in s:
    raise SystemExit('Generator interaction block not found')
s = s.replace(old_gen, new_gen)
s = s.replace('title), buffer -> buffer.writeBlockPos(pos));',
              'title), buffer -> { buffer.writeBlockPos(pos); buffer.writeVarInt(MachineMenu.typeOf(blockEntity)); });')
p.write_text(s, encoding='utf-8')

# Version.
gp = Path('Afterfall/gradle.properties')
g = gp.read_text(encoding='utf-8')
g = g.replace('mod_version=0.6.5', 'mod_version=0.6.6').replace('mod_version=0.6.4', 'mod_version=0.6.6')
gp.write_text(g, encoding='utf-8')

print('Applied Afterfall 0.6.6 interactive GUI/inventory patch')
