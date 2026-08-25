package dev.afterfall.machine;

import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;

public final class MachinePower {
    public static boolean consumeOrRedstoneFallback(ServerLevel level, BlockPos pos, MachineEnergyStorage energy, int amount) {
        if (energy.consume(amount)) return true;
        return level.hasNeighborSignal(pos);
    }

    public static boolean available(ServerLevel level, BlockPos pos, MachineEnergyStorage energy, int amount) {
        return energy.getEnergyStored() >= Math.max(1, amount) || level.hasNeighborSignal(pos);
    }

    public static String source(ServerLevel level, BlockPos pos, MachineEnergyStorage energy) {
        if (energy.getEnergyStored() > 0) return "FE";
        if (level.hasNeighborSignal(pos)) return "REDSTONE FALLBACK";
        return "NONE";
    }

    private MachinePower() {}
}
