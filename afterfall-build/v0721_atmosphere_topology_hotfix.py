from pathlib import Path
import re

ROOT = Path('Afterfall')
JAVA = ROOT / 'src/main/java/dev/afterfall'


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'Expected text not found in {p}: {old[:160]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# ---------------------------------------------------------------------------
# Afterfall 0.7.2.1
# Room-atmosphere topology hotfix:
# - generic room volume changes NEVER imply outside-air contamination
# - block removal explicitly distinguishes internal expansion, room merge,
#   and a real opening to an unsealed/outside volume
# - remove the old player-scan 28% unsealed-air heuristic
# ---------------------------------------------------------------------------

replace_once(ROOT / 'gradle.properties', 'mod_version=0.7.2', 'mod_version=0.7.2.1')

# Generic geometry changes must preserve composition. A removed interior block,
# new alcove, resized shaft, etc. is not an atmospheric source by itself.
replace_once(JAVA / 'room/RoomAtmosphere.java',
'''    public void updateVolume(int newVolume, double outsideDust, double outsideAirborneRadiation) {
        int targetVolume = Math.max(1, newVolume);
        if (targetVolume > volume) {
            double oldVolume = Math.max(1.0D, volume);
            double addedVolume = targetVolume - volume;
            double total = oldVolume + addedVolume;
            dustPercent = (dustPercent * oldVolume + outsideDust * addedVolume) / total;
            airborneRadiationPerSecond = (airborneRadiationPerSecond * oldVolume
                    + Math.max(0.0D, outsideAirborneRadiation) * addedVolume) / total;
            oxygenPercent = (oxygenPercent * oldVolume + NORMAL_OXYGEN * addedVolume) / total;
            co2Percent = (co2Percent * oldVolume + NORMAL_CO2 * addedVolume) / total;
        }
        volume = targetVolume;
    }
''',
'''    public void updateVolume(int newVolume, double outsideDust, double outsideAirborneRadiation) {
        // Geometry alone never creates dirty or clean air. Actual atmospheric
        // transitions (outside opening, room merge, fan transfer) are handled
        // explicitly by their topology events.
        volume = Math.max(1, newVolume);
    }
''')

# RoomEnvironmentManager needs package-level access when it computes a weighted
# merge across every distinct sealed volume touching a removed barrier block.
replace_once(JAVA / 'room/RoomAtmosphere.java',
             '    private void setComposition(double dust, double airborneRadiation, double oxygen, double co2) {',
             '    void setComposition(double dust, double airborneRadiation, double oxygen, double co2) {')

# Remove the old generic "player entered unsealed scan" mutation. An unsealed
# scan may be outside, but it can also be a scan limit, a temporarily enlarged
# interior, or another topology transition. Concrete events own contamination.
replace_once(JAVA / 'room/RoomEnvironmentManager.java',
'''        if (!scan.sealed()) {
            Long previousRoom = LAST_SEALED_ROOM.remove(player.getUUID());
            if (previousRoom != null) {
                RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
                RoomAtmosphere previous = saved.get(previousRoom);
                if (previous != null) {
                    // Opening a previously sealed room causes a fast initial exchange with outside air.
                    previous.exposeToOutside(outsideDust, outsideAirborne, 0.28D);
                    saved.markChanged();
                }
            }
            return new RoomEnvironment(scan, outsideDust, outsideAirborne,
                    Mth.clamp(100.0D - outsideDust * 0.8D, 0.0D, 100.0D),
                    RoomAtmosphere.NORMAL_OXYGEN, RoomAtmosphere.NORMAL_CO2);
        }

        LAST_SEALED_ROOM.put(player.getUUID(), scan.anchor().asLong());
''',
'''        if (!scan.sealed()) {
            return new RoomEnvironment(scan, outsideDust, outsideAirborne,
                    Mth.clamp(100.0D - outsideDust * 0.8D, 0.0D, 100.0D),
                    RoomAtmosphere.NORMAL_OXYGEN, RoomAtmosphere.NORMAL_CO2);
        }

''')
replace_once(JAVA / 'room/RoomEnvironmentManager.java',
             '    private static final Map<UUID, Long> LAST_SEALED_ROOM = new HashMap<>();\n', '')

# Add a topology-aware pre-break handler. BreakEvent fires while the barrier is
# still present, so every neighboring air region can still be scanned separately.
replace_once(JAVA / 'room/RoomEnvironmentManager.java',
'''    public static boolean isWasteland(ServerLevel level, BlockPos pos) {
''',
'''    /**
     * Called before a solid barrier block is removed. Because the block still
     * exists at this point, adjacent air regions can be classified independently:
     *
     *  - one sealed region only: internal room expansion, preserve composition
     *  - two or more sealed regions: volume-weighted room merge
     *  - sealed region + unsealed region: real opening to ambient/outside air
     */
    public static void prepareForBarrierBreak(ServerLevel level, BlockPos barrierPos) {
        if (RoomScanner.airCanPass(level, barrierPos)) return;

        Map<Long, RoomScanResult> sealedRooms = new java.util.LinkedHashMap<>();
        boolean touchesUnsealed = false;

        for (Direction direction : Direction.values()) {
            BlockPos start = barrierPos.relative(direction);
            if (!RoomScanner.airCanPass(level, start)) continue;

            RoomScanResult scan = RoomScanner.scan(level, start);
            if (scan.sealed()) {
                sealedRooms.putIfAbsent(scan.anchor().asLong(), scan);
            } else {
                touchesUnsealed = true;
            }
        }

        if (sealedRooms.isEmpty()) return;

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
        long gameTime = level.getGameTime();

        if (touchesUnsealed) {
            boolean wasteland = isWasteland(level, barrierPos);
            double ambientDust = outsideDust(wasteland);
            double ambientRadiation = outsideAirborneRadiation(wasteland);
            for (RoomScanResult scan : sealedRooms.values()) {
                RoomAtmosphere atmosphere = saved.getOrCreate(scan.anchor().asLong(), scan.volume(),
                        ambientDust, ambientRadiation, gameTime);
                atmosphere.exposeToOutside(ambientDust, ambientRadiation, 1.0D);
            }
            saved.markChanged();
            return;
        }

        if (sealedRooms.size() < 2) return;

        java.util.ArrayList<RoomAtmosphere> atmospheres = new java.util.ArrayList<>();
        double totalVolume = 0.0D;
        double weightedDust = 0.0D;
        double weightedRadiation = 0.0D;
        double weightedOxygen = 0.0D;
        double weightedCo2 = 0.0D;
        int mergedVolume = 1; // the removed barrier cell becomes part of the air volume

        for (RoomScanResult scan : sealedRooms.values()) {
            boolean wasteland = isWasteland(level, scan.anchor());
            RoomAtmosphere atmosphere = saved.getOrCreate(scan.anchor().asLong(), scan.volume(),
                    outsideDust(wasteland), outsideAirborneRadiation(wasteland), gameTime);
            atmosphere.tickPassive(gameTime);

            double volume = Math.max(1.0D, scan.volume());
            totalVolume += volume;
            weightedDust += atmosphere.dustPercent() * volume;
            weightedRadiation += atmosphere.airborneRadiationPerSecond() * volume;
            weightedOxygen += atmosphere.oxygenPercent() * volume;
            weightedCo2 += atmosphere.co2Percent() * volume;
            mergedVolume += scan.volume();
            atmospheres.add(atmosphere);
        }

        if (totalVolume <= 0.0D) return;

        double mixedDust = weightedDust / totalVolume;
        double mixedRadiation = weightedRadiation / totalVolume;
        double mixedOxygen = weightedOxygen / totalVolume;
        double mixedCo2 = weightedCo2 / totalVolume;

        for (RoomAtmosphere atmosphere : atmospheres) {
            atmosphere.setComposition(mixedDust, mixedRadiation, mixedOxygen, mixedCo2);
            // Whichever old anchor survives the flood-fill after the block breaks
            // already represents the complete merged region. This prevents a
            // second artificial volume adjustment on the next sample.
            atmosphere.setVolumePreservingComposition(mergedVolume);
        }
        saved.markChanged();
    }

    public static boolean isWasteland(ServerLevel level, BlockPos pos) {
''')

# Hook NeoForge's pre-break event into the room topology logic.
replace_once(JAVA / 'event/CommonEvents.java',
'''import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;
''',
'''import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;
import net.neoforged.neoforge.event.level.BlockEvent;
''')
replace_once(JAVA / 'event/CommonEvents.java',
'''public final class CommonEvents {
    public static void onPlayerTick(PlayerTickEvent.Post event) {
''',
'''public final class CommonEvents {
    public static void onBlockBreak(BlockEvent.BreakEvent event) {
        if (event.isCanceled() || !(event.getLevel() instanceof ServerLevel serverLevel)) return;
        RoomEnvironmentManager.prepareForBarrierBreak(serverLevel, event.getPos());
        if (event.getPlayer() instanceof ServerPlayer player) RoomEnvironmentManager.invalidate(player);
    }

    public static void onPlayerTick(PlayerTickEvent.Post event) {
''')

# Register the block topology event and update the startup version marker.
replace_once(JAVA / 'Afterfall.java',
'''        NeoForge.EVENT_BUS.addListener(CommonEvents::onPlayerTick);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onRightClickBlock);
        LOGGER.info("Afterfall 0.7.2 initialized");
''',
'''        NeoForge.EVENT_BUS.addListener(CommonEvents::onPlayerTick);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onRightClickBlock);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onBlockBreak);
        LOGGER.info("Afterfall 0.7.2.1 initialized");
''')

print('Afterfall 0.7.2.1 atmosphere topology hotfix applied')
