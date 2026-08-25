from pathlib import Path

root = Path('Afterfall')
src = root / 'src/main/java/dev/afterfall'


def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'Pattern not found in {path}: {old[:180]!r}')
    path.write_text(text.replace(old, new, 1))


# -----------------------------------------------------------------------------
# Biological air: retain theoretical capacity, but also track the actual last
# one-second CO2 removal / O2 production produced by gameplay.
# -----------------------------------------------------------------------------
biological = src / 'room/BiologicalAirManager.java'
replace_once(biological,
'''    private static final Map<ServerLevel, Map<Long, CachedRoom>> CACHE = new WeakHashMap<>();

    public static void tick(MinecraftServer server) {''',
'''    private static final Map<ServerLevel, Map<Long, CachedRoom>> CACHE = new WeakHashMap<>();
    private static final Map<ServerLevel, Map<Long, RateSample>> LAST_RATES = new WeakHashMap<>();

    public static void tick(MinecraftServer server) {''')

replace_once(biological,
'''    private static void tickLevel(ServerLevel level) {
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
        long gameTime = level.getGameTime();
        boolean changed = false;

        for (long roomId : saved.roomIds()) {
            BlockPos anchor = BlockPos.of(roomId);
            if (!level.hasChunkAt(anchor)) continue;

            RoomAtmosphere atmosphere = saved.get(roomId);
            if (atmosphere == null) continue;

            CachedRoom cached = cachedRoom(level, roomId, atmosphere.volume(), gameTime);
            if (!cached.valid()) continue;

            Snapshot snapshot = evaluate(level, cached);
            if (snapshot.activeCapacity() <= 0.0D) continue;

            if (atmosphere.photosynthesize(snapshot.activeCapacity(), 1.0D) > 0.0D) {
                changed = true;
            }
        }

        if (changed) saved.markChanged();
    }''',
'''    private static void tickLevel(ServerLevel level) {
        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
        Map<Long, RateSample> rates = LAST_RATES.computeIfAbsent(level, ignored -> new HashMap<>());
        long gameTime = level.getGameTime();
        boolean changed = false;

        for (long roomId : saved.roomIds()) {
            BlockPos anchor = BlockPos.of(roomId);
            if (!level.hasChunkAt(anchor)) continue;

            RoomAtmosphere atmosphere = saved.get(roomId);
            if (atmosphere == null) continue;

            CachedRoom cached = cachedRoom(level, roomId, atmosphere.volume(), gameTime);
            if (!cached.valid()) continue;

            Snapshot snapshot = evaluate(level, cached);
            double potentialCo2 = 0.002D * snapshot.activeCapacity()
                    / Math.max(1.0D, atmosphere.volume());
            double beforeO2 = atmosphere.oxygenPercent();
            double removedCo2 = atmosphere.photosynthesize(snapshot.activeCapacity(), 1.0D);
            double producedO2 = Math.max(0.0D, atmosphere.oxygenPercent() - beforeO2);

            rates.put(roomId, new RateSample(potentialCo2,
                    Math.max(0.0D, removedCo2), producedO2, gameTime));

            if (removedCo2 > 0.0D || producedO2 > 0.0D) {
                changed = true;
            }
        }

        if (changed) saved.markChanged();
    }''')

replace_once(biological,
'''        return cached.valid() ? evaluate(level, cached) : Snapshot.EMPTY;
    }

    /**
     * Invalidate only cached rooms whose air-space bounds are close to a changed''',
'''        return cached.valid() ? evaluate(level, cached) : Snapshot.EMPTY;
    }

    /**
     * Returns the current theoretical biological rate plus the actual rate measured
     * during the most recent one-second biological tick. Actual values deliberately
     * become zero when the sample is stale, avoiding misleading diagnostics after a
     * room unload or topology change.
     */
    public static RateSample inspectRate(ServerLevel level, RoomScanResult scan) {
        if (scan == null || !scan.sealed()) return RateSample.EMPTY;

        Snapshot snapshot = inspect(level, scan);
        double potentialCo2 = 0.002D * snapshot.activeCapacity()
                / Math.max(1.0D, scan.volume());

        Map<Long, RateSample> levelRates = LAST_RATES.get(level);
        RateSample last = levelRates == null ? null : levelRates.get(scan.anchor().asLong());
        long gameTime = level.getGameTime();
        if (last == null || gameTime - last.sampledAt() > 40L) {
            return new RateSample(potentialCo2, 0.0D, 0.0D, gameTime);
        }
        return new RateSample(potentialCo2, last.actualCo2PerSecond(),
                last.actualO2PerSecond(), last.sampledAt());
    }

    /**
     * Invalidate only cached rooms whose air-space bounds are close to a changed''')

replace_once(biological,
'''    public record Snapshot(int plantBlocks, double nominalCapacity, double activeCapacity,
                           double lightUtilization, double supportedPlayers) {
        public static final Snapshot EMPTY = new Snapshot(0, 0.0D, 0.0D, 0.0D, 0.0D);
    }

    private record CachedRoom''',
'''    public record Snapshot(int plantBlocks, double nominalCapacity, double activeCapacity,
                           double lightUtilization, double supportedPlayers) {
        public static final Snapshot EMPTY = new Snapshot(0, 0.0D, 0.0D, 0.0D, 0.0D);
    }

    /** Rates are percentage points per second; multiply by 60 for command output. */
    public record RateSample(double potentialCo2PerSecond, double actualCo2PerSecond,
                             double actualO2PerSecond, long sampledAt) {
        public static final RateSample EMPTY = new RateSample(0.0D, 0.0D, 0.0D, Long.MIN_VALUE);
    }

    private record CachedRoom''')

# -----------------------------------------------------------------------------
# Transfer Vent diagnostics: local connected-room count, aggregate parallel
# capacity, and maximum current gas-composition deltas across direct neighbours.
# This is observation-only and does not change the 18 m3/s/block gameplay value.
# -----------------------------------------------------------------------------
network = src / 'room/AirTreatmentNetwork.java'
replace_once(network,
'''        return new Network(List.copyOf(rooms.values()), List.copyOf(industrialStages),
                List.copyOf(transferStages), pre, hepa, rad, transferVents,
                industrialBottleneck, transferBottleneck);
    }

    /**
     * Moves atmosphere through passive treatment edges while a powered main fan is''',
'''        return new Network(List.copyOf(rooms.values()), List.copyOf(industrialStages),
                List.copyOf(transferStages), pre, hepa, rad, transferVents,
                industrialBottleneck, transferBottleneck);
    }

    /**
     * Local Transfer Vent diagnostics for operator balancing. Since Transfer Vents
     * are physically undirected, composition deltas are reported as absolute maxima
     * across directly connected sealed rooms.
     */
    public static TransferDiagnostics inspectTransfers(ServerLevel level, RoomScanResult room) {
        if (!validRoom(level, room)) return TransferDiagnostics.EMPTY;

        Boundary boundary = scanBoundary(level, room);
        RoomAtmosphere local = atmosphere(level, room);
        int vents = 0;
        double maxO2Delta = 0.0D;
        double maxCo2Delta = 0.0D;

        for (TransferBank bank : boundary.transferBanks().values()) {
            vents += bank.ventCount();
            RoomAtmosphere other = atmosphere(level, bank.otherRoom());
            maxO2Delta = Math.max(maxO2Delta,
                    Math.abs(local.oxygenPercent() - other.oxygenPercent()));
            maxCo2Delta = Math.max(maxCo2Delta,
                    Math.abs(local.co2Percent() - other.co2Percent()));
        }

        return new TransferDiagnostics(boundary.transferBanks().size(), vents,
                vents * TRANSFER_CAPACITY_PER_BLOCK, maxO2Delta, maxCo2Delta);
    }

    /**
     * Moves atmosphere through passive treatment edges while a powered main fan is''')

replace_once(network,
'''    public enum FilterType {''',
'''    public record TransferDiagnostics(int connectedRooms, int ventCount,
                                      double totalCapacity, double maxOxygenDelta,
                                      double maxCo2Delta) {
        public static final TransferDiagnostics EMPTY =
                new TransferDiagnostics(0, 0, 0.0D, 0.0D, 0.0D);
    }

    public enum FilterType {''')

# -----------------------------------------------------------------------------
# /af room info: expose biological rates, Transfer Vent state, and a current
# room-local life-support balance. Fresh correction is based on real current
# intake flow and the current O2/CO2 error; biological balance uses the actual
# measured CO2 removal from the most recent biological tick.
# -----------------------------------------------------------------------------
commands = src / 'command/AfterfallCommands.java'
replace_once(commands,
'''import dev.afterfall.radiation.RadiationReading;
import dev.afterfall.room.BiologicalAirManager;
import dev.afterfall.room.RoomAtmosphere;''',
'''import dev.afterfall.radiation.RadiationReading;
import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.BiologicalAirManager;
import dev.afterfall.room.IntakeNetworkScanner;
import dev.afterfall.room.RoomAtmosphere;''')

replace_once(commands,
'''    private static int roomInfo(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;
        double radHour = room.air.airborneRadiationPerSecond() * 3600.0D;
        double demand = AirIntakeBlockEntity.freshAirDemandM3PerSecond(room.air);
        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "ROOM %dm³ | Dust %.2f%% | Air Rad %.2f mSv/h | O2 %.2f%% | CO2 %.2f%% | Air %.1f%% | Fresh demand %.2f m³/s",
                room.scan.volume(), room.air.dustPercent(), radHour, room.air.oxygenPercent(),
                room.air.co2Percent(), room.air.airQualityPercent(), demand)), false);
        BiologicalAirManager.Snapshot bio = BiologicalAirManager.inspect(room.level, room.scan);
        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Biological: %d plant blocks | Plant capacity %.1f | Active %.1f | Light %.0f%% | Support %.2f player-eq",
                bio.plantBlocks(), bio.nominalCapacity(), bio.activeCapacity(),
                bio.lightUtilization() * 100.0D, bio.supportedPlayers())), false);
        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()), false);
        return 1;
    }''',
'''    private static int roomInfo(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;

        double radHour = room.air.airborneRadiationPerSecond() * 3600.0D;
        double demand = AirIntakeBlockEntity.freshAirDemandM3PerSecond(room.air);
        BiologicalAirManager.Snapshot bio = BiologicalAirManager.inspect(room.level, room.scan);
        BiologicalAirManager.RateSample bioRate = BiologicalAirManager.inspectRate(room.level, room.scan);
        AirTreatmentNetwork.TransferDiagnostics transfer =
                AirTreatmentNetwork.inspectTransfers(room.level, room.scan);
        IntakeNetworkScanner.Stats fresh = IntakeNetworkScanner.inspectUpstream(room.level, room.scan);

        int occupants = roomOccupants(room.level, room.scan);
        double actualBioSupport = bioRate.actualCo2PerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double freshSupport = freshCorrectionPlayerEquivalent(room.air, fresh.currentInput());
        double netSupport = actualBioSupport + freshSupport - occupants;
        boolean co2Available = room.air.co2Percent() > RoomAtmosphere.NORMAL_CO2 + 0.000001D;

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "ROOM %dm³ | Dust %.2f%% | Air Rad %.2f mSv/h | O2 %.2f%% | CO2 %.2f%% | Air %.1f%% | Fresh demand %.2f m³/s",
                room.scan.volume(), room.air.dustPercent(), radHour, room.air.oxygenPercent(),
                room.air.co2Percent(), room.air.airQualityPercent(), demand)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Biological: %d plant blocks | Capacity %.1f | Active %.1f | Light %.0f%% | Theoretical support %.2f player-eq",
                bio.plantBlocks(), bio.nominalCapacity(), bio.activeCapacity(),
                bio.lightUtilization() * 100.0D, bio.supportedPlayers())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Bio rate: Potential CO2 -%.4f%%/min | Actual CO2 -%.4f%%/min | Actual O2 +%.4f%%/min | CO2 available %s",
                bioRate.potentialCo2PerSecond() * 60.0D,
                bioRate.actualCo2PerSecond() * 60.0D,
                bioRate.actualO2PerSecond() * 60.0D,
                co2Available ? "YES" : "NO")), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Transfer: %d connected room(s) | %d vent(s) | %.1f m³/s | Max dO2 %.3f%% | Max dCO2 %.3f%%",
                transfer.connectedRooms(), transfer.ventCount(), transfer.totalCapacity(),
                transfer.maxOxygenDelta(), transfer.maxCo2Delta())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Life support: Respiration %.2f player-eq | Bio actual %.2f | Fresh correction %.2f | Net %+.2f | Fresh input %.2f m³/s",
                (double) occupants, actualBioSupport, freshSupport, netSupport, fresh.currentInput())), false);

        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()), false);
        return 1;
    }

    private static int roomOccupants(ServerLevel level, RoomScanResult room) {
        int occupants = 0;
        for (ServerPlayer player : level.players()) {
            RoomScanResult playerRoom = RoomScanner.scan(level, player.blockPosition());
            if (playerRoom.sealed() && playerRoom.anchor().equals(room.anchor())) occupants++;
        }
        return occupants;
    }

    /**
     * Converts the currently delivered fresh-air correction into the same
     * player-equivalent scale as respiration. This is an instantaneous diagnostic,
     * not a new control input and does not alter intake behaviour.
     */
    private static double freshCorrectionPlayerEquivalent(RoomAtmosphere atmosphere, double flowM3PerSecond) {
        double flow = Math.max(0.0D, flowM3PerSecond);
        double oxygenEquivalent = flow
                * Math.max(0.0D, RoomAtmosphere.NORMAL_OXYGEN - atmosphere.oxygenPercent()) / 0.14D;
        double co2Equivalent = flow
                * Math.max(0.0D, atmosphere.co2Percent() - RoomAtmosphere.NORMAL_CO2) / 0.11D;
        return Math.max(oxygenEquivalent, co2Equivalent);
    }''')

# Version/log identity.
afterfall = src / 'Afterfall.java'
replace_once(afterfall, 'LOGGER.info("Afterfall 0.8.2 initialized");',
             'LOGGER.info("Afterfall 0.8.3 initialized");')

props = root / 'gradle.properties'
replace_once(props, 'mod_version=0.8.2', 'mod_version=0.8.3')

print('Applied Afterfall 0.8.3 greenhouse life-support integration patch')
