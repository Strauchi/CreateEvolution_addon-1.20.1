package dev.afterfall.room;

import net.minecraft.util.Mth;

public final class RoomAtmosphere {
    public static final double NORMAL_OXYGEN = 20.9D;
    public static final double NORMAL_CO2 = 0.04D;

    private int volume;
    private double dustPercent;
    private double airborneRadiationPerSecond;
    private double oxygenPercent;
    private double co2Percent;
    private long lastUpdateGameTime;

    public RoomAtmosphere(int volume, double dustPercent, double airborneRadiationPerSecond, long lastUpdateGameTime) {
        this(volume, dustPercent, airborneRadiationPerSecond, NORMAL_OXYGEN, NORMAL_CO2, lastUpdateGameTime);
    }

    public RoomAtmosphere(int volume, double dustPercent, double airborneRadiationPerSecond,
                          double oxygenPercent, double co2Percent, long lastUpdateGameTime) {
        this.volume = Math.max(1, volume);
        this.dustPercent = Mth.clamp(dustPercent, 0.0D, 100.0D);
        this.airborneRadiationPerSecond = Math.max(0.0D, airborneRadiationPerSecond);
        this.oxygenPercent = Mth.clamp(oxygenPercent, 0.0D, NORMAL_OXYGEN);
        this.co2Percent = Mth.clamp(co2Percent, NORMAL_CO2, 20.0D);
        this.lastUpdateGameTime = lastUpdateGameTime;
    }

    public int volume() { return volume; }
    public double dustPercent() { return dustPercent; }
    public double airborneRadiationPerSecond() { return airborneRadiationPerSecond; }
    public double oxygenPercent() { return oxygenPercent; }
    public double co2Percent() { return co2Percent; }
    public long lastUpdateGameTime() { return lastUpdateGameTime; }

    public void updateVolume(int newVolume, double outsideDust, double outsideAirborneRadiation) {
        // Geometry alone never creates dirty or clean air. Actual atmospheric
        // transitions (outside opening, room merge, fan transfer) are handled
        // explicitly by their topology events.
        volume = Math.max(1, newVolume);
    }

    public void setVolumePreservingComposition(int newVolume) {
        volume = Math.max(1, newVolume);
    }

    public void exchangeFrom(RoomAtmosphere source, double exchangeFraction) {
        if (source == null || source == this) return;
        double mix = Mth.clamp(exchangeFraction, 0.0D, 1.0D);
        dustPercent = Mth.lerp(mix, dustPercent, source.dustPercent);
        airborneRadiationPerSecond = Mth.lerp(mix, airborneRadiationPerSecond, source.airborneRadiationPerSecond);
        oxygenPercent = Mth.lerp(mix, oxygenPercent, source.oxygenPercent);
        co2Percent = Mth.lerp(mix, co2Percent, source.co2Percent);
    }

    /** Directional transfer with dust/radiological filtration applied before air enters this volume. */
    public void exchangeFilteredFrom(RoomAtmosphere source, double exchangeFraction,
                                     double dustEfficiency, double radiationEfficiency) {
        if (source == null || source == this) return;
        double mix = Mth.clamp(exchangeFraction, 0.0D, 1.0D);
        double filteredDust = source.dustPercent * (1.0D - Mth.clamp(dustEfficiency, 0.0D, 1.0D));
        double filteredRadiation = source.airborneRadiationPerSecond
                * (1.0D - Mth.clamp(radiationEfficiency, 0.0D, 1.0D));
        dustPercent = Mth.lerp(mix, dustPercent, filteredDust);
        airborneRadiationPerSecond = Mth.lerp(mix, airborneRadiationPerSecond, filteredRadiation);
        oxygenPercent = Mth.lerp(mix, oxygenPercent, source.oxygenPercent);
        co2Percent = Mth.lerp(mix, co2Percent, source.co2Percent);
    }

    public void equilibrateWith(RoomAtmosphere other, long gameTime) {
        if (other == null || other == this) return;

        tickPassive(gameTime);
        other.tickPassive(gameTime);

        double totalVolume = Math.max(1.0D, (double) volume + other.volume);
        double thisWeight = volume / totalVolume;
        double otherWeight = other.volume / totalVolume;

        double mixedDust = dustPercent * thisWeight + other.dustPercent * otherWeight;
        double mixedAirborne = airborneRadiationPerSecond * thisWeight
                + other.airborneRadiationPerSecond * otherWeight;
        double mixedOxygen = oxygenPercent * thisWeight + other.oxygenPercent * otherWeight;
        double mixedCo2 = co2Percent * thisWeight + other.co2Percent * otherWeight;

        setComposition(mixedDust, mixedAirborne, mixedOxygen, mixedCo2);
        other.setComposition(mixedDust, mixedAirborne, mixedOxygen, mixedCo2);
    }

    public void setComposition(double dust, double airborneRadiation, double oxygen, double co2) {
        dustPercent = Mth.clamp(dust, 0.0D, 100.0D);
        airborneRadiationPerSecond = Math.max(0.0D, airborneRadiation);
        oxygenPercent = Mth.clamp(oxygen, 0.0D, NORMAL_OXYGEN);
        co2Percent = Mth.clamp(co2, NORMAL_CO2, 20.0D);
    }

    public void exposeToOutside(double outsideDust, double outsideAirborneRadiation, double exchangeFraction) {
        double mix = Mth.clamp(exchangeFraction, 0.0D, 1.0D);
        dustPercent = Mth.lerp(mix, dustPercent, outsideDust);
        airborneRadiationPerSecond = Mth.lerp(mix, airborneRadiationPerSecond, outsideAirborneRadiation);
        oxygenPercent = Mth.lerp(mix, oxygenPercent, NORMAL_OXYGEN);
        co2Percent = Mth.lerp(mix, co2Percent, NORMAL_CO2);
    }

    public void ventilateFiltered(double outsideDust, double outsideAirborneRadiation, double exchangeFraction,
                                  double dustEfficiency, double radiationEfficiency) {
        double mix = Mth.clamp(exchangeFraction, 0.0D, 1.0D);
        double filteredDust = outsideDust * (1.0D - Mth.clamp(dustEfficiency, 0.0D, 1.0D));
        double filteredRadiation = outsideAirborneRadiation * (1.0D - Mth.clamp(radiationEfficiency, 0.0D, 1.0D));
        dustPercent = Mth.lerp(mix, dustPercent, filteredDust);
        airborneRadiationPerSecond = Mth.lerp(mix, airborneRadiationPerSecond, filteredRadiation);
        oxygenPercent = Mth.lerp(mix, oxygenPercent, NORMAL_OXYGEN);
        co2Percent = Mth.lerp(mix, co2Percent, NORMAL_CO2);
    }

    public void filterAir(double processedFraction, double dustEfficiency, double radiationEfficiency) {
        double fraction = Mth.clamp(processedFraction, 0.0D, 1.0D);
        dustPercent *= 1.0D - fraction * Mth.clamp(dustEfficiency, 0.0D, 1.0D);
        airborneRadiationPerSecond *= 1.0D - fraction * Mth.clamp(radiationEfficiency, 0.0D, 1.0D);
    }

    /**
     * Replaces only the breathing-gas fraction of the room with clean make-up air.
     * Dust and airborne radiation are intentionally left untouched; those are handled
     * by the closed-loop filter bank before make-up air is admitted.
     */
    public void refreshBreathingAir(double exchangeFraction) {
        double mix = Mth.clamp(exchangeFraction, 0.0D, 1.0D);
        oxygenPercent = Mth.lerp(mix, oxygenPercent, NORMAL_OXYGEN);
        co2Percent = Mth.lerp(mix, co2Percent, NORMAL_CO2);
    }

    public void consumeBreathingAir() {
        simulateBreathing(1, 1);
    }

    /** Admin/testing helper using the exact same gameplay-scaled respiration model. */
    public void simulateBreathing(int occupants, int seconds) {
        double exposure = Math.max(0, occupants) * Math.max(0, seconds)
                / Math.max(1.0D, volume);
        oxygenPercent = Math.max(0.0D, oxygenPercent - 0.14D * exposure);
        co2Percent = Math.min(20.0D, co2Percent + 0.11D * exposure);
    }

    /**
     * Biological closed-loop treatment. CO2 is the limiting reactant: plants never
     * pull below normal atmospheric CO2 and O2 production is coupled to the amount
     * of CO2 that was actually consumed.
     *
     * @return CO2 percentage points removed from this room
     */
    public double photosynthesize(double activePlantCapacity, double seconds) {
        double capacity = Math.max(0.0D, activePlantCapacity);
        double duration = Math.max(0.0D, seconds);
        if (capacity <= 0.0D || duration <= 0.0D) return 0.0D;

        double desiredCo2Removal = 0.002D * capacity * duration / Math.max(1.0D, volume);
        double availableCo2 = Math.max(0.0D, co2Percent - NORMAL_CO2);
        double removedCo2 = Math.min(desiredCo2Removal, availableCo2);
        if (removedCo2 <= 0.0D) return 0.0D;

        co2Percent = Math.max(NORMAL_CO2, co2Percent - removedCo2);
        // Ratio mirrors the gameplay respiration model: 0.14 O2 consumed for every
        // 0.11 CO2 produced. This makes 55 active plant units one resident-equivalent.
        oxygenPercent = Math.min(NORMAL_OXYGEN, oxygenPercent + removedCo2 * (0.14D / 0.11D));
        return removedCo2;
    }

    /**
     * Technical CO2 removal. One player-equivalent removes exactly the CO2 that
     * one resident produces in the gameplay respiration model. No oxygen is made.
     *
     * @return CO2 percentage points removed from this room
     */
    public double scrubCarbonDioxide(double playerEquivalentCapacity, double seconds) {
        double capacity = Math.max(0.0D, playerEquivalentCapacity);
        double duration = Math.max(0.0D, seconds);
        if (capacity <= 0.0D || duration <= 0.0D) return 0.0D;

        double desiredRemoval = 0.11D * capacity * duration / Math.max(1.0D, volume);
        double availableCo2 = Math.max(0.0D, co2Percent - NORMAL_CO2);
        double removedCo2 = Math.min(desiredRemoval, availableCo2);
        if (removedCo2 <= 0.0D) return 0.0D;
        co2Percent = Math.max(NORMAL_CO2, co2Percent - removedCo2);
        return removedCo2;
    }

    public void tickPassive(long gameTime) {
        long elapsedTicks = Math.max(0L, gameTime - lastUpdateGameTime);
        double seconds = Math.min(30.0D, elapsedTicks / 20.0D);
        if (seconds > 0.0D) {
            dustPercent = Math.max(0.0D, dustPercent - 0.008D * seconds);
            airborneRadiationPerSecond = Math.max(0.0D, airborneRadiationPerSecond - 0.0000015D * seconds);
        }
        lastUpdateGameTime = gameTime;
    }

    public double airQualityPercent() {
        double radiationPenalty = Math.min(100.0D, airborneRadiationPerSecond * 3600.0D * 0.5D);
        double oxygenPenalty = Math.max(0.0D, (18.5D - oxygenPercent) * 12.0D);
        double co2Penalty = Math.max(0.0D, (co2Percent - 0.5D) * 10.0D);
        return Mth.clamp(100.0D - dustPercent * 0.70D - radiationPenalty * 0.15D
                - oxygenPenalty - co2Penalty, 0.0D, 100.0D);
    }
}
