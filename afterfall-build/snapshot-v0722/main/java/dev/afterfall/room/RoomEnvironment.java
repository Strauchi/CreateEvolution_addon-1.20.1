package dev.afterfall.room;

public record RoomEnvironment(
        RoomScanResult scan,
        double dustPercent,
        double airborneRadiationPerSecond,
        double airQualityPercent,
        double oxygenPercent,
        double co2Percent
) {
    public boolean sealed() { return scan.sealed(); }
    public int volume() { return scan.volume(); }
    public double shieldingFactor() { return scan.shieldingFactor(); }
    public double shieldingPercent() { return scan.shieldingPercent(); }
}
