package dev.afterfall.radiation;

import dev.afterfall.room.RoomEnvironment;

public record RadiationReading(
        double externalGammaRatePerSecond,
        double hotspotRatePerSecond,
        double airborneRatePerSecond,
        double contaminationRatePerSecond,
        double shieldingFactor,
        boolean skyExposed,
        boolean wasteland,
        RoomEnvironment room
) {
    public double totalRatePerSecond() {
        return externalGammaRatePerSecond + hotspotRatePerSecond + airborneRatePerSecond + contaminationRatePerSecond;
    }

    public double totalRatePerHour() { return totalRatePerSecond() * 3600.0D; }
    public double shieldingPercent() { return (1.0D - shieldingFactor) * 100.0D; }
}
