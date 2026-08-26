from pathlib import Path
import re

ROOT = Path("Afterfall")
SRC = ROOT / "src/main/java/dev/afterfall"
GRADLE = ROOT / "gradle.properties"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not patch {label}")
    return text.replace(old, new, 1)

# -----------------------------------------------------------------------------
# Fallout environment model
# -----------------------------------------------------------------------------
p = SRC / "room/RoomEnvironmentManager.java"
text = p.read_text(encoding="utf-8")
text = replace_once(text,
'''    public static final double WASTELAND_OUTSIDE_DUST = 92.0D;
    public static final double WASTELAND_OUTSIDE_AIRBORNE_MSV_PER_SECOND = 0.013D;
''',
'''    public static final double WASTELAND_OUTSIDE_DUST = 92.0D;
    public static final double WASTELAND_OUTSIDE_AIRBORNE_MSV_PER_SECOND = 0.013D;
    public static final double ELEVATED_FALLOUT_LOAD = 1.5D;
    public static final double SEVERE_FALLOUT_LOAD = 3.0D;

    /**
     * 0.8.5 uses vanilla weather as a deterministic/testable fallout driver in the
     * Wasteland. This can later be replaced by a dedicated Afterfall storm system
     * without changing intake/filter load semantics.
     */
    public enum FalloutCondition {
        NORMAL(1.0D),
        ELEVATED(ELEVATED_FALLOUT_LOAD),
        SEVERE(SEVERE_FALLOUT_LOAD);

        private final double loadMultiplier;
        FalloutCondition(double loadMultiplier) { this.loadMultiplier = loadMultiplier; }
        public double loadMultiplier() { return loadMultiplier; }
    }
''', "RoomEnvironmentManager constants")
text = replace_once(text,
'''    public static double outsideDust(boolean wasteland) { return wasteland ? WASTELAND_OUTSIDE_DUST : 4.0D; }
    public static double outsideAirborneRadiation(boolean wasteland) { return wasteland ? WASTELAND_OUTSIDE_AIRBORNE_MSV_PER_SECOND : 0.0D; }
    public static void invalidate(ServerPlayer player) { CACHE.remove(player.getUUID()); }
''',
'''    public static FalloutCondition falloutCondition(ServerLevel level, BlockPos pos) {
        if (!isWasteland(level, pos)) return FalloutCondition.NORMAL;
        if (level.isThundering()) return FalloutCondition.SEVERE;
        if (level.isRaining()) return FalloutCondition.ELEVATED;
        return FalloutCondition.NORMAL;
    }

    public static double falloutLoadMultiplier(ServerLevel level, BlockPos pos) {
        return falloutCondition(level, pos).loadMultiplier();
    }

    /** Outside concentration presented to an OPEN intake. Dust is already near its
     * percentage ceiling in the Wasteland, so storm severity is represented mainly
     * by contaminant mass/load in the filter model while concentration rises to 100%.
     */
    public static double intakeOutsideDust(ServerLevel level, BlockPos pos) {
        boolean wasteland = isWasteland(level, pos);
        double base = outsideDust(wasteland);
        if (!wasteland) return base;
        return Math.min(100.0D, base + (falloutLoadMultiplier(level, pos) - 1.0D) * 8.0D);
    }

    public static double intakeOutsideAirborneRadiation(ServerLevel level, BlockPos pos) {
        boolean wasteland = isWasteland(level, pos);
        return outsideAirborneRadiation(wasteland) * falloutLoadMultiplier(level, pos);
    }

    public static double outsideDust(boolean wasteland) { return wasteland ? WASTELAND_OUTSIDE_DUST : 4.0D; }
    public static double outsideAirborneRadiation(boolean wasteland) { return wasteland ? WASTELAND_OUTSIDE_AIRBORNE_MSV_PER_SECOND : 0.0D; }
    public static void invalidate(ServerPlayer player) { CACHE.remove(player.getUUID()); }
''', "RoomEnvironmentManager fallout methods")
p.write_text(text, encoding="utf-8")

# -----------------------------------------------------------------------------
# Intake OPEN / CLOSED / AUTO
# -----------------------------------------------------------------------------
p = SRC / "blockentity/AirIntakeBlockEntity.java"
text = p.read_text(encoding="utf-8")
text = replace_once(text,
'''    public static final int ENERGY_CAPACITY = 20_000;
    public static final int ENERGY_PER_SECOND = 120;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private boolean enabled = true;
''',
'''    public static final int ENERGY_CAPACITY = 20_000;
    public static final int ENERGY_PER_SECOND = 120;
    public static final double AUTO_ISOLATION_LOAD = 2.0D;

    public enum IntakeMode {
        OPEN,
        CLOSED,
        AUTO;

        public IntakeMode next() {
            return switch (this) {
                case OPEN -> CLOSED;
                case CLOSED -> AUTO;
                case AUTO -> OPEN;
            };
        }
    }

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private boolean enabled = true;
    private IntakeMode mode = IntakeMode.AUTO;
''', "AirIntake mode fields")
text = replace_once(text,
'''    private boolean lastVentilating = false;
    private double lastFlowM3PerSecond = 0.0D;
''',
'''    private boolean lastVentilating = false;
    private double lastFlowM3PerSecond = 0.0D;
    private double lastFalloutLoadMultiplier = 1.0D;
''', "AirIntake fallout diagnostic field")
text = replace_once(text,
'''    public MachineEnergyStorage energyStorage() { return energy; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }
    public boolean networkReadyFor(long roomAnchor) { return lastTargetRoom == roomAnchor && lastNetworkReady; }
    public boolean ventilatingRoom(long roomAnchor) { return lastTargetRoom == roomAnchor && lastVentilating; }
    public long targetRoomAnchor() { return lastTargetRoom; }
    public double currentFlowM3PerSecond() { return lastFlowM3PerSecond; }
''',
'''    public MachineEnergyStorage energyStorage() { return energy; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }
    public IntakeMode mode() { return mode; }
    public void cycleMode() { mode = mode.next(); setChanged(); }
    public boolean networkReadyFor(long roomAnchor) { return lastTargetRoom == roomAnchor && lastNetworkReady; }
    public boolean ventilatingRoom(long roomAnchor) { return lastTargetRoom == roomAnchor && lastVentilating; }
    public long targetRoomAnchor() { return lastTargetRoom; }
    public double currentFlowM3PerSecond() { return lastFlowM3PerSecond; }
    public double currentFalloutLoadMultiplier() { return lastFalloutLoadMultiplier; }

    public boolean acceptsOutsideAir(ServerLevel level, BlockPos pos) {
        if (!enabled) return false;
        return switch (mode) {
            case OPEN -> true;
            case CLOSED -> false;
            case AUTO -> RoomEnvironmentManager.falloutLoadMultiplier(level, pos) < AUTO_ISOLATION_LOAD;
        };
    }

    public boolean autoIsolated(ServerLevel level, BlockPos pos) {
        return mode == IntakeMode.AUTO
                && RoomEnvironmentManager.falloutLoadMultiplier(level, pos) >= AUTO_ISOLATION_LOAD;
    }
''', "AirIntake mode methods")
text = replace_once(text,
'''        be.lastTargetRoom = Long.MIN_VALUE;
        be.lastNetworkReady = false;
        be.lastVentilating = false;
        be.lastFlowM3PerSecond = 0.0D;
        if (!be.enabled) return;
''',
'''        be.lastTargetRoom = Long.MIN_VALUE;
        be.lastNetworkReady = false;
        be.lastVentilating = false;
        be.lastFlowM3PerSecond = 0.0D;
        be.lastFalloutLoadMultiplier = RoomEnvironmentManager.falloutLoadMultiplier(serverLevel, pos);
        if (!be.acceptsOutsideAir(serverLevel, pos)) return;
''', "AirIntake serverTick mode gate")
text = replace_once(text,
'''        boolean wasteland = RoomEnvironmentManager.isWasteland(serverLevel, pos);
        double outsideDust = RoomEnvironmentManager.outsideDust(wasteland);
        double outsideAirborne = RoomEnvironmentManager.outsideAirborneRadiation(wasteland);
''',
'''        double outsideDust = RoomEnvironmentManager.intakeOutsideDust(serverLevel, pos);
        double outsideAirborne = RoomEnvironmentManager.intakeOutsideAirborneRadiation(serverLevel, pos);
''', "AirIntake storm outside values")

status_pattern = re.compile(r'''    public static Component status\(ServerLevel level, BlockPos pos\) \{.*?\n    \}\n\n    @Override\n    public void loadAdditional''', re.S)
status_replacement = '''    public static Component status(ServerLevel level, BlockPos pos) {
        if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity be))
            return Component.literal("Air Intake: OFFLINE").withStyle(ChatFormatting.RED);

        RoomEnvironmentManager.FalloutCondition fallout = RoomEnvironmentManager.falloutCondition(level, pos);
        double load = fallout.loadMultiplier();
        double outsideDust = RoomEnvironmentManager.intakeOutsideDust(level, pos);
        double outsideRadHour = RoomEnvironmentManager.intakeOutsideAirborneRadiation(level, pos) * 3600.0D;
        String environmental = String.format(Locale.ROOT,
                " | Fallout %s %.0f%% | Outside Dust %.0f%% / Rad %.1f mSv/h",
                fallout.name(), load * 100.0D, outsideDust, outsideRadHour);

        if (!be.enabled) return Component.literal("Air Intake: DISABLED | Mode " + be.mode + environmental)
                .withStyle(ChatFormatting.GRAY);
        if (be.mode == IntakeMode.CLOSED) return Component.literal("Air Intake: ISOLATED | Mode CLOSED" + environmental)
                .withStyle(ChatFormatting.GRAY);
        if (be.autoIsolated(level, pos)) return Component.literal("Air Intake: AUTO ISOLATED - SEVERE FALLOUT" + environmental)
                .withStyle(ChatFormatting.RED);

        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, pos);
        if (!MachinePower.available(level, pos, be.energy, ENERGY_PER_SECOND))
            return Component.literal(String.format(Locale.ROOT, "Air Intake: OFFLINE - NO POWER | Mode %s | %d/%d FE%s",
                    be.mode, be.energy.getEnergyStored(), be.energy.getMaxEnergyStored(), environmental)).withStyle(ChatFormatting.RED);
        if (connection.room() == null) return Component.literal("Air Intake: ERROR - NO SEALED MIXING ROOM | Mode " + be.mode + environmental)
                .withStyle(ChatFormatting.RED);
        if (!connection.outsideConnected()) return Component.literal("Air Intake: ERROR - NO OUTSIDE CONNECTION | Mode " + be.mode + environmental)
                .withStyle(ChatFormatting.RED);

        RoomScanResult scan = connection.room();
        RoomAtmosphere atmosphere = RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                outsideDust, RoomEnvironmentManager.intakeOutsideAirborneRadiation(level, pos), level.getGameTime());
        double demand = freshAirDemandM3PerSecond(atmosphere);
        boolean active = be.lastVentilating;
        return Component.literal(String.format(Locale.ROOT,
                "Air Intake: %s | Mode %s | Flow %.2f/%.0f m³/s | Demand %.2f m³/s%s",
                active ? "VENTILATING" : "STANDBY", be.mode,
                be.lastFlowM3PerSecond, FLOW_M3_PER_SECOND, demand, environmental))
                .withStyle(active ? ChatFormatting.YELLOW : ChatFormatting.GREEN);
    }

    @Override
    public void loadAdditional'''
text, count = status_pattern.subn(status_replacement, text, count=1)
if count != 1:
    raise SystemExit("Could not replace AirIntake status")
text = replace_once(text,
'''        energy.setEnergyStored(tag.getInt("Energy"));
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
''',
'''        energy.setEnergyStored(tag.getInt("Energy"));
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
        if (tag.contains("Mode")) {
            try { mode = IntakeMode.valueOf(tag.getString("Mode")); }
            catch (IllegalArgumentException ignored) { mode = IntakeMode.AUTO; }
        } else {
            mode = IntakeMode.AUTO;
        }
''', "AirIntake load mode")
text = replace_once(text,
'''        tag.putInt("Energy", energy.getEnergyStored());
        tag.putBoolean("Enabled", enabled);
''',
'''        tag.putInt("Energy", energy.getEnergyStored());
        tag.putBoolean("Enabled", enabled);
        tag.putString("Mode", mode.name());
''', "AirIntake save mode")
p.write_text(text, encoding="utf-8")

# -----------------------------------------------------------------------------
# Intake network: mode-aware readiness + active fallout load
# -----------------------------------------------------------------------------
p = SRC / "room/IntakeNetworkScanner.java"
text = p.read_text(encoding="utf-8")
text = replace_once(text, "import java.util.HashSet;\nimport java.util.Set;\n",
                    "import java.util.HashSet;\nimport java.util.List;\nimport java.util.Set;\n", "IntakeNetworkScanner List import")
text = replace_once(text,
'''            if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity intake) || !intake.enabled()) continue;
''',
'''            if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity intake)
                    || !intake.acceptsOutsideAir(level, pos)) continue;
''', "Intake ready mode gate")
insert_marker = '''    private static Stats statsFor(ServerLevel level, Set<Long> intakePositions, Set<Long> roomAnchors,
'''
insert_code = '''    /**
     * Highest active fallout mass-load multiplier feeding the specified treatment
     * rooms. Closed/AUTO-isolated intakes contribute nothing because no outside air
     * is entering the recirculation loop.
     */
    public static double activeFalloutLoadMultiplier(ServerLevel level, List<RoomScanResult> rooms) {
        if (rooms == null || rooms.isEmpty()) return 1.0D;
        double max = 1.0D;
        Set<Long> inspected = new HashSet<>();
        for (RoomScanResult room : rooms) {
            if (!validRoom(level, room)) continue;
            for (long packed : scanBoundary(level, room).intakes()) {
                if (!inspected.add(packed)) continue;
                BlockPos pos = BlockPos.of(packed);
                if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity intake)) continue;
                if (intake.currentFlowM3PerSecond() <= 0.01D) continue;
                max = Math.max(max, intake.currentFalloutLoadMultiplier());
            }
        }
        return max;
    }

'''
text = replace_once(text, insert_marker, insert_code + insert_marker, "Intake active fallout helper")
p.write_text(text, encoding="utf-8")

# -----------------------------------------------------------------------------
# Industrial filter contaminant-load model
# -----------------------------------------------------------------------------
p = SRC / "room/AirTreatmentNetwork.java"
text = p.read_text(encoding="utf-8")
text = replace_once(text,
'''    public static final double PRE_DUST_EFFICIENCY = 0.70D;
    public static final double HEPA_DUST_EFFICIENCY = 0.95D;
    public static final double RAD_AIRBORNE_EFFICIENCY = 0.98D;
''',
'''    public static final double PRE_DUST_EFFICIENCY = 0.70D;
    public static final double HEPA_DUST_EFFICIENCY = 0.95D;
    public static final double RAD_AIRBORNE_EFFICIENCY = 0.98D;

    // Abstract contaminant mass-load capacities. These are deliberately separate
    // from m³/s airflow capacity: permanent filter walls do not break when
    // overloaded, but their effective removal efficiency falls above 100% load.
    public static final double PRE_DUST_LOAD_CAPACITY_PER_BLOCK = 700.0D;
    public static final double HEPA_DUST_LOAD_CAPACITY_PER_BLOCK = 300.0D;
    public static final double RAD_LOAD_CAPACITY_PER_BLOCK = 300.0D;
''', "AirTreatment load constants")

process_pattern = re.compile(r'''    public static double processPassive\(ServerLevel level, Network network, double requestedFlow\) \{.*?\n    \}\n\n    /\*\* Compatibility alias''', re.S)
process_replacement = '''    public static ProcessResult processPassiveDetailed(ServerLevel level, Network network, double requestedFlow) {
        if (network == null || requestedFlow <= 0.0D)
            return new ProcessResult(requestedFlow, 0.0D, 0.0D, 0);

        boolean changed = false;
        double maxDustLoadRatio = 0.0D;
        double maxRadiationLoadRatio = 0.0D;
        double falloutDustLoad = IntakeNetworkScanner.activeFalloutLoadMultiplier(level, network.rooms());

        for (int depth = MAX_DEPTH; depth >= 0; depth--) {
            for (TransferStage stage : network.transferStages()) {
                if (stage.depth() != depth) continue;
                double flow = Math.min(requestedFlow, stage.capacity());
                if (flow <= 0.0D) continue;

                RoomAtmosphere source = atmosphere(level, stage.upstream());
                RoomAtmosphere destination = atmosphere(level, stage.downstream());
                double fraction = Math.min(0.35D,
                        flow / Math.max(1.0D, stage.downstream().volume()));
                destination.exchangeFrom(source, fraction);
                changed = true;
            }

            for (ScrubberStage stage : network.scrubberStages()) {
                if (stage.depth() != depth) continue;
                double flow = Math.min(requestedFlow, stage.capacity());
                if (flow <= 0.0D || stage.scrubberPositions().isEmpty()) continue;

                RoomAtmosphere source = atmosphere(level, stage.upstream());
                RoomAtmosphere destination = atmosphere(level, stage.downstream());
                double fraction = Math.min(0.35D,
                        flow / Math.max(1.0D, stage.downstream().volume()));
                destination.exchangeFrom(source, fraction);

                double perUnitFlow = Math.min(Co2ScrubberBlockEntity.FLOW_M3_PER_SECOND,
                        flow / Math.max(1, stage.scrubberPositions().size()));
                for (BlockPos scrubberPos : stage.scrubberPositions()) {
                    if (level.getBlockEntity(scrubberPos) instanceof Co2ScrubberBlockEntity scrubber) {
                        scrubber.processScrubbing(level, destination, stage.downstream(), perUnitFlow);
                    }
                }
                changed = true;
            }

            for (IndustrialStage stage : network.industrialStages()) {
                if (stage.depth() != depth) continue;
                double flow = Math.min(requestedFlow, stage.capacity());
                if (flow <= 0.0D) continue;

                RoomAtmosphere source = atmosphere(level, stage.upstream());
                RoomAtmosphere destination = atmosphere(level, stage.downstream());
                double fraction = Math.min(0.35D,
                        flow / Math.max(1.0D, stage.downstream().volume()));

                double dustLoadRatio = stage.dustLoadCapacity() <= 0.0D ? 0.0D
                        : source.dustPercent() * flow * falloutDustLoad / stage.dustLoadCapacity();
                double radiationLoadRatio = stage.radiationLoadCapacity() <= 0.0D ? 0.0D
                        : source.airborneRadiationPerSecond() * 3600.0D * flow / stage.radiationLoadCapacity();
                maxDustLoadRatio = Math.max(maxDustLoadRatio, dustLoadRatio);
                maxRadiationLoadRatio = Math.max(maxRadiationLoadRatio, radiationLoadRatio);

                destination.exchangeFilteredFrom(source, fraction,
                        loadAdjustedEfficiency(stage.dustEfficiency(), dustLoadRatio),
                        loadAdjustedEfficiency(stage.radiationEfficiency(), radiationLoadRatio));
                changed = true;
            }
        }

        if (changed) RoomAtmosphereSavedData.get(level).markChanged();
        double bottleneck = network.passiveBottleneckCapacity();
        double effectiveFlow = bottleneck > 0.0D ? Math.min(requestedFlow, bottleneck) : requestedFlow;
        return new ProcessResult(effectiveFlow, maxDustLoadRatio, maxRadiationLoadRatio,
                network.industrialStages().size());
    }

    public static double processPassive(ServerLevel level, Network network, double requestedFlow) {
        return processPassiveDetailed(level, network, requestedFlow).effectiveFlow();
    }

    private static double loadAdjustedEfficiency(double baseEfficiency, double loadRatio) {
        if (baseEfficiency <= 0.0D || loadRatio <= 1.0D) return baseEfficiency;
        return baseEfficiency / loadRatio;
    }

    /** Compatibility alias'''
text, count = process_pattern.subn(process_replacement, text, count=1)
if count != 1:
    raise SystemExit("Could not replace AirTreatment processPassive")

text = replace_once(text,
'''    public record ScrubberDiagnostics(int units, int readyUnits, int activeUnits,
                                      double flowCapacity, double nominalPlayerEquivalent,
                                      double actualPlayerEquivalent, double co2RemovedPerSecond) {
        public static final ScrubberDiagnostics EMPTY =
                new ScrubberDiagnostics(0, 0, 0, 0.0D, 0.0D, 0.0D, 0.0D);
    }
''',
'''    public record ScrubberDiagnostics(int units, int readyUnits, int activeUnits,
                                      double flowCapacity, double nominalPlayerEquivalent,
                                      double actualPlayerEquivalent, double co2RemovedPerSecond) {
        public static final ScrubberDiagnostics EMPTY =
                new ScrubberDiagnostics(0, 0, 0, 0.0D, 0.0D, 0.0D, 0.0D);
    }

    public record ProcessResult(double effectiveFlow, double maxDustLoadRatio,
                                double maxRadiationLoadRatio, int industrialStages) {}
''', "AirTreatment ProcessResult")
text = replace_once(text,
'''    public record IndustrialStage(RoomScanResult upstream, RoomScanResult downstream,
                                  int preBlocks, int hepaBlocks, int radBlocks,
                                  double capacity, double dustEfficiency,
                                  double radiationEfficiency, int depth) {}
''',
'''    public record IndustrialStage(RoomScanResult upstream, RoomScanResult downstream,
                                  int preBlocks, int hepaBlocks, int radBlocks,
                                  double capacity, double dustEfficiency,
                                  double radiationEfficiency, int depth) {
        public double dustLoadCapacity() {
            return preBlocks * PRE_DUST_LOAD_CAPACITY_PER_BLOCK
                    + hepaBlocks * HEPA_DUST_LOAD_CAPACITY_PER_BLOCK;
        }
        public double radiationLoadCapacity() {
            return radBlocks * RAD_LOAD_CAPACITY_PER_BLOCK;
        }
    }
''', "IndustrialStage load capacities")
p.write_text(text, encoding="utf-8")

# -----------------------------------------------------------------------------
# Fan records actual filter load with the room-flow diagnostic sample
# -----------------------------------------------------------------------------
p = SRC / "blockentity/VentilationFanBlockEntity.java"
text = p.read_text(encoding="utf-8")
text = replace_once(text,
'''    private static void recordRoomFlow(ServerLevel level, RoomScanResult room,
                                       double supplyFlow, double returnFlow, double freshFlow,
                                       double oxygenAdded, double co2Removed) {
''',
'''    private static void recordRoomFlow(ServerLevel level, RoomScanResult room,
                                       double supplyFlow, double returnFlow, double freshFlow,
                                       double oxygenAdded, double co2Removed,
                                       int filterStages, double dustFilterLoadRatio,
                                       double radiationFilterLoadRatio) {
''', "Fan recordRoomFlow signature")
text = replace_once(text,
'''                previous.oxygenAddedPerSecond() + Math.max(0.0D, oxygenAdded),
                previous.co2RemovedPerSecond() + Math.max(0.0D, co2Removed),
                gameTime));
''',
'''                previous.oxygenAddedPerSecond() + Math.max(0.0D, oxygenAdded),
                previous.co2RemovedPerSecond() + Math.max(0.0D, co2Removed),
                Math.max(previous.filterStages(), Math.max(0, filterStages)),
                Math.max(previous.maxDustFilterLoadRatio(), Math.max(0.0D, dustFilterLoadRatio)),
                Math.max(previous.maxRadiationFilterLoadRatio(), Math.max(0.0D, radiationFilterLoadRatio)),
                gameTime));
''', "Fan diagnostic record values")
text = replace_once(text,
'''                    recordRoomFlow(serverLevel, target.room, 0.0D, perReturnFlow, 0.0D, 0.0D, 0.0D);
''',
'''                    recordRoomFlow(serverLevel, target.room, 0.0D, perReturnFlow, 0.0D,
                            0.0D, 0.0D, 0, 0.0D, 0.0D);
''', "Fan return flow call")
text = replace_once(text,
'''        double deliveredFlow = 0.0D;
        double deliveredFreshFlow = 0.0D;
''',
'''        double deliveredFlow = 0.0D;
        double deliveredFreshFlow = 0.0D;
        int deliveredFilterStages = 0;
        double deliveredDustFilterLoad = 0.0D;
        double deliveredRadiationFilterLoad = 0.0D;
''', "Fan delivered filter diagnostics")
text = replace_once(text,
'''            double effectiveFlow = AirTreatmentNetwork.processPassive(serverLevel, treatment, groupFlow);
            deliveredFreshFlow += Math.min(Math.max(0.0D, groupFreshInput), effectiveFlow);
''',
'''            AirTreatmentNetwork.ProcessResult treatmentResult =
                    AirTreatmentNetwork.processPassiveDetailed(serverLevel, treatment, groupFlow);
            double effectiveFlow = treatmentResult.effectiveFlow();
            deliveredFilterStages = Math.max(deliveredFilterStages, treatmentResult.industrialStages());
            deliveredDustFilterLoad = Math.max(deliveredDustFilterLoad, treatmentResult.maxDustLoadRatio());
            deliveredRadiationFilterLoad = Math.max(deliveredRadiationFilterLoad, treatmentResult.maxRadiationLoadRatio());
            deliveredFreshFlow += Math.min(Math.max(0.0D, groupFreshInput), effectiveFlow);
''', "Fan detailed treatment processing")
text = replace_once(text,
'''            recordRoomFlow(serverLevel, target.room, perSupplyFlow, 0.0D, perSupplyFresh,
                    Math.max(0.0D, roomAir.oxygenPercent() - beforeO2),
                    Math.max(0.0D, beforeCo2 - roomAir.co2Percent()));
''',
'''            recordRoomFlow(serverLevel, target.room, perSupplyFlow, 0.0D, perSupplyFresh,
                    Math.max(0.0D, roomAir.oxygenPercent() - beforeO2),
                    Math.max(0.0D, beforeCo2 - roomAir.co2Percent()),
                    deliveredFilterStages, deliveredDustFilterLoad, deliveredRadiationFilterLoad);
''', "Fan supply flow call")
text = replace_once(text,
'''    public record RoomFlowSample(double supplyM3PerSecond, double returnM3PerSecond,
                                 double freshAirM3PerSecond, double oxygenAddedPerSecond,
                                 double co2RemovedPerSecond, long sampledAt) {
''',
'''    public record RoomFlowSample(double supplyM3PerSecond, double returnM3PerSecond,
                                 double freshAirM3PerSecond, double oxygenAddedPerSecond,
                                 double co2RemovedPerSecond, int filterStages,
                                 double maxDustFilterLoadRatio, double maxRadiationFilterLoadRatio,
                                 long sampledAt) {
''', "Fan RoomFlowSample fields")
text = replace_once(text,
'''            return new RoomFlowSample(0.0D, 0.0D, 0.0D, 0.0D, 0.0D, time);
''',
'''            return new RoomFlowSample(0.0D, 0.0D, 0.0D, 0.0D, 0.0D,
                    0, 0.0D, 0.0D, time);
''', "Fan RoomFlowSample empty")
p.write_text(text, encoding="utf-8")

# -----------------------------------------------------------------------------
# Intake interaction: sneak-right-click cycles OPEN/CLOSED/AUTO
# -----------------------------------------------------------------------------
p = SRC / "event/CommonEvents.java"
text = p.read_text(encoding="utf-8")
text = replace_once(text,
'''                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof AirIntakeBlockEntity intake) {
                    openMachineMenu(player, event.getPos(), intake, Component.literal("Air Intake Unit"));
                }
''',
'''                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof AirIntakeBlockEntity intake) {
                    if (player.isShiftKeyDown()) {
                        intake.cycleMode();
                        player.displayClientMessage(AirIntakeBlockEntity.status(serverLevel, event.getPos()), true);
                    } else {
                        openMachineMenu(player, event.getPos(), intake, Component.literal("Air Intake Unit"));
                    }
                }
''', "CommonEvents intake mode interaction")
p.write_text(text, encoding="utf-8")

# -----------------------------------------------------------------------------
# /af life: ambient fallout and actual supplying-filter load
# -----------------------------------------------------------------------------
p = SRC / "command/AfterfallCommands.java"
text = p.read_text(encoding="utf-8")
header_marker = '''        source.sendSuccess(() -> header, false);

        if (bio.plantBlocks() <= 0) {
'''
header_add = '''        source.sendSuccess(() -> header, false);

        if (RoomEnvironmentManager.isWasteland(room.level, room.scan.anchor())) {
            RoomEnvironmentManager.FalloutCondition fallout =
                    RoomEnvironmentManager.falloutCondition(room.level, room.scan.anchor());
            ChatFormatting falloutColor = switch (fallout) {
                case NORMAL -> ChatFormatting.GRAY;
                case ELEVATED -> ChatFormatting.YELLOW;
                case SEVERE -> ChatFormatting.RED;
            };
            source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                    "[FALLOUT] %s | Ambient load %.0f%%",
                    fallout.name(), fallout.loadMultiplier() * 100.0D))
                    .withStyle(falloutColor).withStyle(ChatFormatting.BOLD), false);
        }

        if (bio.plantBlocks() <= 0) {
'''
# Replace the second occurrence (roomInfo also has source.sendSuccess header); anchor
# includes bio so it is unique to lifeInfo.
text = replace_once(text, header_marker, header_add, "life fallout line")
filter_marker = '''        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "      Fresh demand %.2f m³/s", demand)).withStyle(ChatFormatting.DARK_GRAY), false);

        if (transfer.ventCount() <= 0) {
'''
filter_add = '''        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "      Fresh demand %.2f m³/s", demand)).withStyle(ChatFormatting.DARK_GRAY), false);

        if (flow.filterStages() > 0) {
            double maxFilterLoad = Math.max(flow.maxDustFilterLoadRatio(), flow.maxRadiationFilterLoadRatio());
            ChatFormatting filterColor = maxFilterLoad > 1.0D ? ChatFormatting.RED
                    : (maxFilterLoad >= 0.75D ? ChatFormatting.YELLOW : ChatFormatting.GREEN);
            String filterState = maxFilterLoad > 1.0D ? "OVERLOAD" : "OK";
            var filterLine = Component.literal("[FILTER] ").withStyle(filterColor).withStyle(ChatFormatting.BOLD)
                    .append(Component.literal(String.format(Locale.ROOT,
                            "%d stage(s) | Dust %.0f%% | Rad %.0f%% | %s",
                            flow.filterStages(), flow.maxDustFilterLoadRatio() * 100.0D,
                            flow.maxRadiationFilterLoadRatio() * 100.0D, filterState))
                            .withStyle(filterColor));
            source.sendSuccess(() -> filterLine, false);
        }

        if (transfer.ventCount() <= 0) {
'''
text = replace_once(text, filter_marker, filter_add, "life filter load line")
p.write_text(text, encoding="utf-8")

# Version
gradle = GRADLE.read_text(encoding="utf-8")
gradle, count = re.subn(r"(?m)^mod_version=.*$", "mod_version=0.8.5", gradle, count=1)
if count != 1:
    raise SystemExit("Could not update mod_version")
GRADLE.write_text(gradle, encoding="utf-8")

print("Applied Afterfall 0.8.5 Intake Isolation + Fallout Load")
