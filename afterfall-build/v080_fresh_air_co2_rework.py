from pathlib import Path

root = Path('Afterfall')


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'{label} pattern not found in {path}')
    path.write_text(text.replace(old, new, 1))

# -----------------------------------------------------------------------------
# Room breathing balance: CO2 becomes the primary enclosed-space constraint.
# -----------------------------------------------------------------------------
room = root / 'src/main/java/dev/afterfall/room/RoomAtmosphere.java'
replace_once(
    room,
    '''    public void consumeBreathingAir() {\n        double volumeScale = 1.0D / Math.max(1.0D, volume);\n        oxygenPercent = Math.max(0.0D, oxygenPercent - 0.35D * volumeScale);\n        co2Percent = Math.min(20.0D, co2Percent + 0.10D * volumeScale);\n    }''',
    '''    public void consumeBreathingAir() {\n        double volumeScale = 1.0D / Math.max(1.0D, volume);\n        // Gameplay-scaled respiration. CO2 should become the first meaningful\n        // closed-room constraint while oxygen falls more gradually. This also\n        // gives demand-controlled fresh-air ventilation a visible equilibrium\n        // instead of pinning both gases to outdoor values.\n        oxygenPercent = Math.max(0.0D, oxygenPercent - 0.14D * volumeScale);\n        co2Percent = Math.min(20.0D, co2Percent + 0.11D * volumeScale);\n    }''',
    'RoomAtmosphere respiration'
)

# -----------------------------------------------------------------------------
# Intake: proportional fresh-air demand and actual variable flow.
# -----------------------------------------------------------------------------
intake = root / 'src/main/java/dev/afterfall/blockentity/AirIntakeBlockEntity.java'
text = intake.read_text()
text = text.replace(
    'import dev.afterfall.room.RoomMachineUtil;\n',
    'import dev.afterfall.room.RoomMachineUtil;\nimport dev.afterfall.room.IntakeNetworkScanner;\n',
    1
)
old_constants = '''    public static final double TARGET_OXYGEN = 20.75D;\n    public static final double TARGET_CO2 = 0.08D;\n    public static final int ENERGY_CAPACITY = 20_000;'''
new_constants = '''    // Fresh-air demand controller. Normal occupied bunkers are intentionally\n    // allowed to settle above outdoor CO2 instead of being clamped to 0.08%.\n    public static final double OXYGEN_DEMAND_START = 20.75D;\n    public static final double CO2_DEMAND_START = 0.10D;\n    public static final double OXYGEN_DEMAND_GAIN = 3.0D; // m3/s per O2 percentage point deficit\n    public static final double CO2_DEMAND_GAIN = 4.0D;    // m3/s per CO2 percentage point excess\n    public static final int ENERGY_CAPACITY = 20_000;'''
if old_constants not in text:
    raise SystemExit('AirIntake constants pattern not found')
text = text.replace(old_constants, new_constants, 1)
text = text.replace(
    '    private boolean lastVentilating = false;\n',
    '    private boolean lastVentilating = false;\n    private double lastFlowM3PerSecond = 0.0D;\n',
    1
)
text = text.replace(
    '''    public boolean networkReadyFor(long roomAnchor) { return lastTargetRoom == roomAnchor && lastNetworkReady; }\n    public boolean ventilatingRoom(long roomAnchor) { return lastTargetRoom == roomAnchor && lastVentilating; }''',
    '''    public boolean networkReadyFor(long roomAnchor) { return lastTargetRoom == roomAnchor && lastNetworkReady; }\n    public boolean ventilatingRoom(long roomAnchor) { return lastTargetRoom == roomAnchor && lastVentilating; }\n    public long targetRoomAnchor() { return lastTargetRoom; }\n    public double currentFlowM3PerSecond() { return lastFlowM3PerSecond; }''',
    1
)
text = text.replace(
    '''        be.lastTargetRoom = Long.MIN_VALUE;\n        be.lastNetworkReady = false;\n        be.lastVentilating = false;''',
    '''        be.lastTargetRoom = Long.MIN_VALUE;\n        be.lastNetworkReady = false;\n        be.lastVentilating = false;\n        be.lastFlowM3PerSecond = 0.0D;''',
    1
)
old_tick = '''        if (!needsFreshAir(atmosphere)) return;\n        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, be.energy, ENERGY_PER_SECOND)) {\n            be.lastNetworkReady = false;\n            return;\n        }\n        be.lastVentilating = true;\n\n        double exchangeFraction = Math.min(0.30D, FLOW_M3_PER_SECOND / Math.max(1.0D, scan.volume()));\n        atmosphere.ventilateFiltered(outsideDust, outsideAirborne, exchangeFraction,\n                PERMANENT_DUST_EFFICIENCY, PERMANENT_RADIATION_EFFICIENCY);\n        saved.markChanged();\n    }\n\n    public static boolean needsFreshAir(RoomAtmosphere atmosphere) {\n        return atmosphere.oxygenPercent() < TARGET_OXYGEN || atmosphere.co2Percent() > TARGET_CO2;\n    }'''
new_tick = '''        double totalDemand = freshAirDemandM3PerSecond(atmosphere);\n        if (totalDemand <= 0.01D) return;\n\n        // Multiple intakes on the same mixing plenum share the requested make-up\n        // airflow instead of every unit blindly injecting its full 18 m3/s rating.\n        int readyIntakes = Math.max(1, IntakeNetworkScanner.readyIntakeCount(serverLevel, scan));\n        double requestedFlow = Math.min(FLOW_M3_PER_SECOND, totalDemand / readyIntakes);\n        if (requestedFlow <= 0.01D) return;\n\n        int energyCost = Math.max(1, (int) Math.ceil(ENERGY_PER_SECOND\n                * (requestedFlow / FLOW_M3_PER_SECOND)));\n        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, be.energy, energyCost)) {\n            be.lastNetworkReady = false;\n            return;\n        }\n        be.lastVentilating = true;\n        be.lastFlowM3PerSecond = requestedFlow;\n\n        double exchangeFraction = Math.min(0.30D, requestedFlow / Math.max(1.0D, scan.volume()));\n        atmosphere.ventilateFiltered(outsideDust, outsideAirborne, exchangeFraction,\n                PERMANENT_DUST_EFFICIENCY, PERMANENT_RADIATION_EFFICIENCY);\n        saved.markChanged();\n    }\n\n    public static double freshAirDemandM3PerSecond(RoomAtmosphere atmosphere) {\n        if (atmosphere == null) return 0.0D;\n        double co2Demand = Math.max(0.0D,\n                (atmosphere.co2Percent() - CO2_DEMAND_START) * CO2_DEMAND_GAIN);\n        double oxygenDemand = Math.max(0.0D,\n                (OXYGEN_DEMAND_START - atmosphere.oxygenPercent()) * OXYGEN_DEMAND_GAIN);\n        return Math.max(co2Demand, oxygenDemand);\n    }\n\n    public static boolean needsFreshAir(RoomAtmosphere atmosphere) {\n        return freshAirDemandM3PerSecond(atmosphere) > 0.01D;\n    }'''
if old_tick not in text:
    raise SystemExit('AirIntake tick/demand pattern not found')
text = text.replace(old_tick, new_tick, 1)
old_status = '''        boolean active = needsFreshAir(atmosphere);\n        return Component.literal(String.format(Locale.ROOT,\n                "Air Intake: %s | %.0f m³/s | Permanent pre-clean Dust %.0f%% / Rad %.0f%% | Mixing %dm³ | O2 %.2f%% | CO2 %.2f%%",\n                active ? "VENTILATING" : "STANDBY - AIR BALANCED", FLOW_M3_PER_SECOND,\n                PERMANENT_DUST_EFFICIENCY * 100.0D, PERMANENT_RADIATION_EFFICIENCY * 100.0D,\n                scan.volume(), atmosphere.oxygenPercent(), atmosphere.co2Percent()))\n                .withStyle(active ? ChatFormatting.YELLOW : ChatFormatting.GREEN);'''
new_status = '''        boolean active = needsFreshAir(atmosphere);\n        double demand = freshAirDemandM3PerSecond(atmosphere);\n        return Component.literal(String.format(Locale.ROOT,\n                "Air Intake: %s | Flow %.2f/%.0f m³/s | Demand %.2f m³/s | Permanent pre-clean Dust %.0f%% / Rad %.0f%% | Mixing %dm³ | O2 %.2f%% | CO2 %.2f%%",\n                active ? "VENTILATING" : "STANDBY - AIR BALANCED", be.lastFlowM3PerSecond, FLOW_M3_PER_SECOND, demand,\n                PERMANENT_DUST_EFFICIENCY * 100.0D, PERMANENT_RADIATION_EFFICIENCY * 100.0D,\n                scan.volume(), atmosphere.oxygenPercent(), atmosphere.co2Percent()))\n                .withStyle(active ? ChatFormatting.YELLOW : ChatFormatting.GREEN);'''
if old_status not in text:
    raise SystemExit('AirIntake status pattern not found')
text = text.replace(old_status, new_status, 1)
intake.write_text(text)

# -----------------------------------------------------------------------------
# Intake network diagnostics: actual flow, aggregate demand and sharing count.
# -----------------------------------------------------------------------------
scanner = root / 'src/main/java/dev/afterfall/room/IntakeNetworkScanner.java'
text = scanner.read_text()
text = text.replace(
    'import dev.afterfall.content.ModBlocks;\n',
    'import dev.afterfall.content.ModBlocks;\nimport dev.afterfall.machine.MachinePower;\n',
    1
)
text = text.replace(
    '''        Boundary boundary = scanBoundary(level, room);\n        return statsFor(level, boundary.intakes(), Set.of(room.anchor().asLong()));''',
    '''        Boundary boundary = scanBoundary(level, room);\n        return statsFor(level, boundary.intakes(), Set.of(room.anchor().asLong()),\n                Set.of(room.anchor().asLong()));''',
    1
)
old_upstream = '''        Set<Long> roomAnchors = new HashSet<>();\n        Set<Long> intakes = new HashSet<>();\n        for (RoomScanResult treatmentRoom : treatment.rooms()) {\n            roomAnchors.add(treatmentRoom.anchor().asLong());\n            intakes.addAll(scanBoundary(level, treatmentRoom).intakes());\n        }\n        return statsFor(level, intakes, roomAnchors);\n    }\n\n    private static Stats statsFor(ServerLevel level, Set<Long> intakePositions, Set<Long> roomAnchors) {\n        int ready = 0;\n        int active = 0;\n        for (long packed : intakePositions) {\n            if (!(level.getBlockEntity(BlockPos.of(packed)) instanceof AirIntakeBlockEntity intake)) continue;\n            boolean intakeReady = false;\n            boolean intakeActive = false;\n            for (long anchor : roomAnchors) {\n                if (!intakeReady && intake.networkReadyFor(anchor)) intakeReady = true;\n                if (!intakeActive && intake.ventilatingRoom(anchor)) intakeActive = true;\n                if (intakeReady && intakeActive) break;\n            }\n            if (intakeReady) ready++;\n            if (intakeActive) active++;\n        }\n        return new Stats(intakePositions.size(), ready, active);\n    }'''
new_upstream = '''        Set<Long> roomAnchors = new HashSet<>();\n        Set<Long> intakeRoomAnchors = new HashSet<>();\n        Set<Long> intakes = new HashSet<>();\n        for (RoomScanResult treatmentRoom : treatment.rooms()) {\n            long anchor = treatmentRoom.anchor().asLong();\n            roomAnchors.add(anchor);\n            Boundary boundary = scanBoundary(level, treatmentRoom);\n            if (!boundary.intakes().isEmpty()) intakeRoomAnchors.add(anchor);\n            intakes.addAll(boundary.intakes());\n        }\n        return statsFor(level, intakes, roomAnchors, intakeRoomAnchors);\n    }\n\n    /** Number of currently usable intakes directly feeding this mixing room. */\n    public static int readyIntakeCount(ServerLevel level, RoomScanResult room) {\n        if (!validRoom(level, room)) return 0;\n        int ready = 0;\n        for (long packed : scanBoundary(level, room).intakes()) {\n            BlockPos pos = BlockPos.of(packed);\n            if (!(level.getBlockEntity(pos) instanceof AirIntakeBlockEntity intake) || !intake.enabled()) continue;\n            RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, pos);\n            if (connection.room() == null || !connection.room().anchor().equals(room.anchor())\n                    || !connection.outsideConnected()) continue;\n            if (MachinePower.available(level, pos, intake.energyStorage(), AirIntakeBlockEntity.ENERGY_PER_SECOND)) ready++;\n        }\n        return ready;\n    }\n\n    private static Stats statsFor(ServerLevel level, Set<Long> intakePositions, Set<Long> roomAnchors,\n                                  Set<Long> intakeRoomAnchors) {\n        int ready = 0;\n        int active = 0;\n        double currentInput = 0.0D;\n        for (long packed : intakePositions) {\n            if (!(level.getBlockEntity(BlockPos.of(packed)) instanceof AirIntakeBlockEntity intake)) continue;\n            boolean intakeReady = false;\n            boolean intakeActive = false;\n            for (long anchor : roomAnchors) {\n                if (!intakeReady && intake.networkReadyFor(anchor)) intakeReady = true;\n                if (!intakeActive && intake.ventilatingRoom(anchor)) intakeActive = true;\n                if (intakeReady && intakeActive) break;\n            }\n            if (intakeReady) ready++;\n            if (intakeActive) active++;\n            if (roomAnchors.contains(intake.targetRoomAnchor())) {\n                currentInput += intake.currentFlowM3PerSecond();\n            }\n        }\n\n        double demand = 0.0D;\n        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);\n        for (long anchor : intakeRoomAnchors) {\n            RoomAtmosphere atmosphere = saved.get(anchor);\n            if (atmosphere != null) demand += AirIntakeBlockEntity.freshAirDemandM3PerSecond(atmosphere);\n        }\n        return new Stats(intakePositions.size(), ready, active, currentInput, demand);\n    }'''
if old_upstream not in text:
    raise SystemExit('IntakeNetworkScanner upstream/stats pattern not found')
text = text.replace(old_upstream, new_upstream, 1)
old_record = '''    public record Stats(int totalIntakes, int readyIntakes, int activeIntakes) {\n        public static final Stats EMPTY = new Stats(0, 0, 0);\n        public double readyCapacity() { return readyIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }\n        public double currentInput() { return activeIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }\n    }'''
new_record = '''    public record Stats(int totalIntakes, int readyIntakes, int activeIntakes,\n                        double currentInput, double freshAirDemand) {\n        public static final Stats EMPTY = new Stats(0, 0, 0, 0.0D, 0.0D);\n        public double readyCapacity() { return readyIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }\n    }'''
if old_record not in text:
    raise SystemExit('IntakeNetworkScanner Stats record pattern not found')
text = text.replace(old_record, new_record, 1)
scanner.write_text(text)

# -----------------------------------------------------------------------------
# Menu sync: expose fresh-air demand to intake/fan screens.
# -----------------------------------------------------------------------------
menu = root / 'src/main/java/dev/afterfall/menu/MachineMenu.java'
text = menu.read_text()
text = text.replace('public static final int DATA_COUNT = 32;', 'public static final int DATA_COUNT = 33;', 1)
text = text.replace(
    '    public static final int D_IND_CAPACITY_X10 = 31;\n',
    '    public static final int D_IND_CAPACITY_X10 = 31;\n    public static final int D_INTAKE_DEMAND_X10 = 32;\n',
    1
)
text = text.replace(
    '''        data.set(D_INTAKE_INPUT_X10, scale(stats.currentInput(), 10.0D));\n        data.set(D_INTAKE_CAPACITY_X10, scale(stats.readyCapacity(), 10.0D));''',
    '''        data.set(D_INTAKE_INPUT_X10, scale(stats.currentInput(), 10.0D));\n        data.set(D_INTAKE_CAPACITY_X10, scale(stats.readyCapacity(), 10.0D));\n        data.set(D_INTAKE_DEMAND_X10, scale(stats.freshAirDemand(), 10.0D));''',
    1
)
text = text.replace(
    '    public double intakeCapacity() { return get(D_INTAKE_CAPACITY_X10) / 10.0D; }\n',
    '    public double intakeCapacity() { return get(D_INTAKE_CAPACITY_X10) / 10.0D; }\n    public double intakeDemand() { return get(D_INTAKE_DEMAND_X10) / 10.0D; }\n',
    1
)
menu.write_text(text)

# -----------------------------------------------------------------------------
# GUI: show actual fresh-air flow, available capacity and atmospheric demand.
# -----------------------------------------------------------------------------
screen = root / 'src/main/java/dev/afterfall/client/MachineScreen.java'
text = screen.read_text()
old_intake_ui = '''        graphics.drawString(font, String.format(Locale.ROOT, "Network %d/%d ready | Fresh %.1f/%.1f m³/s",\n                menu.intakeReady(), menu.intakeTotal(), menu.intakeInput(), menu.intakeCapacity()),\n                12, 174, 0xFF9DB7BD, false);\n        graphics.drawString(font, String.format(Locale.ROOT, "Rated fresh-air flow: %.1f m³/s", menu.flow()),\n                12, 193, 0xFF7F9298, false);'''
new_intake_ui = '''        graphics.drawString(font, String.format(Locale.ROOT, "Fresh: %.1f / %.1f m³/s",\n                menu.intakeInput(), menu.intakeCapacity()), 12, 174, 0xFF9DB7BD, false);\n        graphics.drawString(font, String.format(Locale.ROOT, "Demand %.1f m³/s | Network %d/%d ready",\n                menu.intakeDemand(), menu.intakeReady(), menu.intakeTotal()),\n                12, 193, 0xFF7F9298, false);'''
if old_intake_ui not in text:
    raise SystemExit('MachineScreen intake UI pattern not found')
text = text.replace(old_intake_ui, new_intake_ui, 1)
old_fan_ui = '''        graphics.drawString(font, String.format(Locale.ROOT, "Fresh intake: %.1f/%.1f m³/s (%d/%d ready)",\n                menu.intakeInput(), menu.intakeCapacity(), menu.intakeReady(), menu.intakeTotal()),\n                12, 153, 0xFF9DB7BD, false);\n        graphics.drawString(font, String.format(Locale.ROOT, "Industrial P:%d H:%d R:%d",\n                menu.industrialPreBlocks(), menu.industrialHepaBlocks(), menu.industrialRadBlocks()),\n                12, 166, 0xFF9DB7BD, false);'''
new_fan_ui = '''        graphics.drawString(font, String.format(Locale.ROOT, "Fresh %.1f/%.1f | Demand %.1f m³/s",\n                menu.intakeInput(), menu.intakeCapacity(), menu.intakeDemand()),\n                12, 153, 0xFF9DB7BD, false);\n        graphics.drawString(font, String.format(Locale.ROOT, "Intakes %d/%d | Industrial P:%d H:%d R:%d",\n                menu.intakeReady(), menu.intakeTotal(), menu.industrialPreBlocks(),\n                menu.industrialHepaBlocks(), menu.industrialRadBlocks()),\n                12, 166, 0xFF9DB7BD, false);'''
if old_fan_ui not in text:
    raise SystemExit('MachineScreen fan fresh-air UI pattern not found')
text = text.replace(old_fan_ui, new_fan_ui, 1)
screen.write_text(text)

# Version metadata.
props = root / 'gradle.properties'
p = props.read_text()
if 'mod_version=0.7.4.1\n' not in p:
    raise SystemExit('Expected 0.7.4.1 base version not found')
props.write_text(p.replace('mod_version=0.7.4.1\n', 'mod_version=0.8.0\n', 1))

main = root / 'src/main/java/dev/afterfall/Afterfall.java'
m = main.read_text()
if 'Afterfall 0.7.4.1 initialized' not in m:
    raise SystemExit('Expected Afterfall 0.7.4.1 logger version not found')
main.write_text(m.replace('Afterfall 0.7.4.1 initialized', 'Afterfall 0.8.0 initialized', 1))

print('Afterfall 0.8.0 fresh-air / CO2 demand rework applied')
