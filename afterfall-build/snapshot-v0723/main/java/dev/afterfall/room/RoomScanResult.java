package dev.afterfall.room;

import net.minecraft.core.BlockPos;

public record RoomScanResult(
        boolean sealed,
        int volume,
        BlockPos anchor,
        double shieldingFactor,
        int boundaryFaces,
        boolean exceededScanLimit
) {
    public static RoomScanResult open(int scannedVolume, BlockPos anchor, boolean exceededScanLimit) {
        return new RoomScanResult(false, scannedVolume, anchor, 1.0D, 0, exceededScanLimit);
    }

    public double shieldingPercent() {
        return (1.0D - shieldingFactor) * 100.0D;
    }
}
