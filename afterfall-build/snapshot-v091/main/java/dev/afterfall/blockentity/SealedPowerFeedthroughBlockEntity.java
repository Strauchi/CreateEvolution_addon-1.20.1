package dev.afterfall.blockentity;

import dev.afterfall.block.SealedPowerFeedthroughBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachineEnergyStorage;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.energy.IEnergyStorage;
import org.jetbrains.annotations.Nullable;

/** Generic FE bridge through an airtight bunker wall. */
public final class SealedPowerFeedthroughBlockEntity extends BlockEntity {
    public static final int BUFFER_CAPACITY = 8_000;
    public static final int MAX_TRANSFER_PER_TICK = 8_000;

    private final MachineEnergyStorage buffer = new MachineEnergyStorage(
            BUFFER_CAPACITY, MAX_TRANSFER_PER_TICK, MAX_TRANSFER_PER_TICK, this::setChanged);

    private final IEnergyStorage inputPort = new IEnergyStorage() {
        @Override public int receiveEnergy(int maxReceive, boolean simulate) { return buffer.receiveEnergy(maxReceive, simulate); }
        @Override public int extractEnergy(int maxExtract, boolean simulate) { return 0; }
        @Override public int getEnergyStored() { return buffer.getEnergyStored(); }
        @Override public int getMaxEnergyStored() { return buffer.getMaxEnergyStored(); }
        @Override public boolean canExtract() { return false; }
        @Override public boolean canReceive() { return buffer.getEnergyStored() < buffer.getMaxEnergyStored(); }
    };

    private final IEnergyStorage outputPort = new IEnergyStorage() {
        @Override public int receiveEnergy(int maxReceive, boolean simulate) { return 0; }
        @Override public int extractEnergy(int maxExtract, boolean simulate) { return buffer.extractEnergy(maxExtract, simulate); }
        @Override public int getEnergyStored() { return buffer.getEnergyStored(); }
        @Override public int getMaxEnergyStored() { return buffer.getMaxEnergyStored(); }
        @Override public boolean canExtract() { return buffer.getEnergyStored() > 0; }
        @Override public boolean canReceive() { return false; }
    };

    public SealedPowerFeedthroughBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.SEALED_POWER_FEEDTHROUGH.get(), pos, state);
    }

    public MachineEnergyStorage internalBuffer() { return buffer; }

    @Nullable
    public IEnergyStorage energyStorage(@Nullable Direction side) {
        if (side == null) return null;
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.SEALED_POWER_FEEDTHROUGH.get())
                || !state.hasProperty(SealedPowerFeedthroughBlock.FACING)) return null;
        Direction front = state.getValue(SealedPowerFeedthroughBlock.FACING);
        if (side == front) return outputPort;
        if (side == front.getOpposite()) return inputPort;
        return null;
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        buffer.setEnergyStored(tag.getInt("Energy"));
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", buffer.getEnergyStored());
    }
}
