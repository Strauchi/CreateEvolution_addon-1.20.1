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

import java.util.Locale;

public final class EmergencyGeneratorBlockEntity extends BlockEntity {
    public static final int ENERGY_CAPACITY = 100_000;
    public static final int GENERATION_PER_TICK = 80;
    public static final int MAX_OUTPUT_PER_TICK = 400;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(
            ENERGY_CAPACITY, 1_000, MAX_OUTPUT_PER_TICK, this::setChanged);
    private int burnTicks;

    public EmergencyGeneratorBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.EMERGENCY_GENERATOR.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public int burnTicks() { return burnTicks; }

    public boolean addFuel(ServerPlayer player, ItemStack held) {
        int ticks;
        if (held.is(Items.COAL) || held.is(Items.CHARCOAL)) ticks = 1600;
        else if (held.is(Items.COAL_BLOCK)) ticks = 16000;
        else return false;

        burnTicks = Math.min(72_000, burnTicks + ticks);
        if (!player.getAbilities().instabuild) held.shrink(1);
        setChanged();
        return true;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, EmergencyGeneratorBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel)) return;

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
        if (!(level.getBlockEntity(pos) instanceof EmergencyGeneratorBlockEntity be)) {
            return Component.literal("Emergency Generator: OFFLINE").withStyle(ChatFormatting.RED);
        }
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
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        tag.putInt("BurnTicks", burnTicks);
    }
}
