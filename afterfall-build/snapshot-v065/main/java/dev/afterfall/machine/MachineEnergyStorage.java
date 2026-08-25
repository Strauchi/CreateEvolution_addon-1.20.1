package dev.afterfall.machine;

import net.neoforged.neoforge.energy.IEnergyStorage;

public final class MachineEnergyStorage implements IEnergyStorage {
    private final int capacity;
    private final int maxReceive;
    private final int maxExtract;
    private final Runnable onChanged;
    private int energy;

    public MachineEnergyStorage(int capacity, int maxReceive, int maxExtract, Runnable onChanged) {
        this.capacity = Math.max(0, capacity);
        this.maxReceive = Math.max(0, maxReceive);
        this.maxExtract = Math.max(0, maxExtract);
        this.onChanged = onChanged == null ? () -> {} : onChanged;
    }

    @Override
    public int receiveEnergy(int maxReceive, boolean simulate) {
        if (!canReceive() || maxReceive <= 0) return 0;
        int received = Math.min(this.capacity - this.energy, Math.min(this.maxReceive, maxReceive));
        if (!simulate && received > 0) {
            this.energy += received;
            onChanged.run();
        }
        return received;
    }

    @Override
    public int extractEnergy(int maxExtract, boolean simulate) {
        if (!canExtract() || maxExtract <= 0) return 0;
        int extracted = Math.min(this.energy, Math.min(this.maxExtract, maxExtract));
        if (!simulate && extracted > 0) {
            this.energy -= extracted;
            onChanged.run();
        }
        return extracted;
    }

    public boolean consume(int amount) {
        if (amount <= 0) return true;
        if (energy < amount) return false;
        energy -= amount;
        onChanged.run();
        return true;
    }

    public int addEnergyInternal(int amount) {
        if (amount <= 0) return 0;
        int added = Math.min(amount, capacity - energy);
        if (added > 0) {
            energy += added;
            onChanged.run();
        }
        return added;
    }

    public void setEnergyStored(int energy) {
        int clamped = Math.max(0, Math.min(capacity, energy));
        if (this.energy != clamped) {
            this.energy = clamped;
            onChanged.run();
        }
    }

    @Override public int getEnergyStored() { return energy; }
    @Override public int getMaxEnergyStored() { return capacity; }
    @Override public boolean canExtract() { return maxExtract > 0; }
    @Override public boolean canReceive() { return maxReceive > 0; }
}
