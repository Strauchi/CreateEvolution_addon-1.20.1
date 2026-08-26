package dev.afterfall.blockentity;

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
