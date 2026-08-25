from pathlib import Path
import re

ROOT = Path('Afterfall')
JAVA = ROOT / 'src/main/java/dev/afterfall'


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'Expected text not found in {p}: {old[:140]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# Afterfall 0.7.2.2
# - discover all Air Intakes bordering the same sealed mixing plenum
# - cache each intake's ready/actively-ventilating state once per second
# - show summed fresh-air capacity/input in Intake and Main Fan GUIs
# - no changes to room mixing or fan transfer mechanics
# ---------------------------------------------------------------------------

replace_once(ROOT / 'gradle.properties', 'mod_version=0.7.2.1', 'mod_version=0.7.2.2')
replace_once(JAVA / 'Afterfall.java', 'Afterfall 0.7.2.1 initialized', 'Afterfall 0.7.2.2 initialized')

# Cache intake operating state so network diagnostics do not recursively rescan
# the outside connection for every GUI update tick.
replace_once(JAVA / 'blockentity/AirIntakeBlockEntity.java',
'''    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private final FilterBank filters = new FilterBank(this::setChanged);
    private boolean enabled = true;
''',
'''    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private final FilterBank filters = new FilterBank(this::setChanged);
    private boolean enabled = true;
    private long lastTargetRoom = Long.MIN_VALUE;
    private boolean lastNetworkReady = false;
    private boolean lastVentilating = false;
''')

replace_once(JAVA / 'blockentity/AirIntakeBlockEntity.java',
'''    public FilterBank filters() { return filters; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }
''',
'''    public FilterBank filters() { return filters; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { if (this.enabled != enabled) { this.enabled = enabled; setChanged(); } }
    public boolean networkReadyFor(long roomAnchor) { return lastTargetRoom == roomAnchor && lastNetworkReady; }
    public boolean ventilatingRoom(long roomAnchor) { return lastTargetRoom == roomAnchor && lastVentilating; }
''')

replace_once(JAVA / 'blockentity/AirIntakeBlockEntity.java',
'''        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L) return;
        if (!blockEntity.enabled) return;

        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(serverLevel, pos);
        RoomScanResult scan = connection.room();
        if (scan == null || !connection.outsideConnected() || !blockEntity.filters.complete()) return;
''',
'''        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L) return;

        blockEntity.lastTargetRoom = Long.MIN_VALUE;
        blockEntity.lastNetworkReady = false;
        blockEntity.lastVentilating = false;
        if (!blockEntity.enabled) return;

        RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(serverLevel, pos);
        RoomScanResult scan = connection.room();
        if (scan == null) return;
        blockEntity.lastTargetRoom = scan.anchor().asLong();
        if (!connection.outsideConnected() || !blockEntity.filters.complete()) return;
        blockEntity.lastNetworkReady = MachinePower.available(serverLevel, pos, blockEntity.energy, ENERGY_PER_SECOND);
        if (!blockEntity.lastNetworkReady) return;
''')

replace_once(JAVA / 'blockentity/AirIntakeBlockEntity.java',
'''        if (!needsFreshAir(atmosphere)) return;
        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, blockEntity.energy, ENERGY_PER_SECOND)) return;

        double exchangeFraction = Math.min(0.30D, FLOW_M3_PER_SECOND / Math.max(1.0D, scan.volume()));
''',
'''        if (!needsFreshAir(atmosphere)) return;
        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, blockEntity.energy, ENERGY_PER_SECOND)) {
            blockEntity.lastNetworkReady = false;
            return;
        }
        blockEntity.lastVentilating = true;

        double exchangeFraction = Math.min(0.30D, FLOW_M3_PER_SECOND / Math.max(1.0D, scan.volume()));
''')

# Fast plenum-local intake discovery. The flood fill only walks the already
# sealed room and checks its boundary for intake blocks. Operational state comes
# from the once-per-second cache above, avoiding expensive repeated room scans.
write(JAVA / 'room/IntakeNetworkScanner.java', r'''package dev.afterfall.room;

import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;

import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Set;

/** Aggregates all outside-air intakes bordering one sealed mixing plenum. */
public final class IntakeNetworkScanner {
    public static Stats inspect(ServerLevel level, RoomScanResult room) {
        if (room == null || !room.sealed() || !RoomScanner.airCanPass(level, room.anchor())) return Stats.EMPTY;

        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> intakePositions = new HashSet<>();
        queue.add(room.anchor().immutable());
        visited.add(room.anchor().asLong());

        while (!queue.isEmpty() && visited.size() <= RoomScanner.MAX_ROOM_VOLUME) {
            BlockPos current = queue.removeFirst();
            for (Direction direction : Direction.values()) {
                BlockPos next = current.relative(direction);
                if (RoomScanner.airCanPass(level, next)) {
                    if (visited.add(next.asLong())) queue.addLast(next.immutable());
                    continue;
                }
                if (level.getBlockState(next).is(ModBlocks.AIR_INTAKE_UNIT.get())) {
                    intakePositions.add(next.asLong());
                }
            }
        }

        int ready = 0;
        int active = 0;
        long anchor = room.anchor().asLong();
        for (long packed : intakePositions) {
            if (!(level.getBlockEntity(BlockPos.of(packed)) instanceof AirIntakeBlockEntity intake)) continue;
            if (intake.networkReadyFor(anchor)) ready++;
            if (intake.ventilatingRoom(anchor)) active++;
        }

        return new Stats(intakePositions.size(), ready, active);
    }

    public record Stats(int totalIntakes, int readyIntakes, int activeIntakes) {
        public static final Stats EMPTY = new Stats(0, 0, 0);
        public double readyCapacity() { return readyIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }
        public double currentInput() { return activeIntakes * AirIntakeBlockEntity.FLOW_M3_PER_SECOND; }
    }

    private IntakeNetworkScanner() {}
}
''')

# Menu data: total intakes, ready intakes, current fresh-air input, ready capacity.
replace_once(JAVA / 'menu/MachineMenu.java',
'''import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomMachineUtil;
''',
'''import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.IntakeNetworkScanner;
import dev.afterfall.room.RoomMachineUtil;
''')

replace_once(JAVA / 'menu/MachineMenu.java',
'''    public static final int DATA_COUNT = 21;
''',
'''    public static final int DATA_COUNT = 25;
''')

replace_once(JAVA / 'menu/MachineMenu.java',
'''    public static final int D_RETURN_FLOW_X10 = 20;
''',
'''    public static final int D_RETURN_FLOW_X10 = 20;
    public static final int D_INTAKE_TOTAL = 21;
    public static final int D_INTAKE_READY = 22;
    public static final int D_INTAKE_INPUT_X10 = 23;
    public static final int D_INTAKE_CAPACITY_X10 = 24;
''')

replace_once(JAVA / 'menu/MachineMenu.java',
'''            if (scan != null && get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {
''',
'''            if (scan != null) {
                if (get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
                setIntakeStats(IntakeNetworkScanner.inspect(level, scan));
            }
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {
''')

replace_once(JAVA / 'menu/MachineMenu.java',
'''            data.set(D_RETURN_FLOW_X10, scale(be.currentReturnFlow(level), 10.0D));
            if (network != null && network.valid()) {
''',
'''            data.set(D_RETURN_FLOW_X10, scale(be.currentReturnFlow(level), 10.0D));
            if (inlet != null) setIntakeStats(IntakeNetworkScanner.inspect(level, inlet));
            if (network != null && network.valid()) {
''')

replace_once(JAVA / 'menu/MachineMenu.java',
'''    private void setAtmosphere(RoomScanResult scan, RoomAtmosphere atmosphere) {
''',
'''    private void setIntakeStats(IntakeNetworkScanner.Stats stats) {
        data.set(D_INTAKE_TOTAL, stats.totalIntakes());
        data.set(D_INTAKE_READY, stats.readyIntakes());
        data.set(D_INTAKE_INPUT_X10, scale(stats.currentInput(), 10.0D));
        data.set(D_INTAKE_CAPACITY_X10, scale(stats.readyCapacity(), 10.0D));
    }

    private void setAtmosphere(RoomScanResult scan, RoomAtmosphere atmosphere) {
''')

replace_once(JAVA / 'menu/MachineMenu.java',
'''    public double returnFlow() { return get(D_RETURN_FLOW_X10) / 10.0D; }
''',
'''    public double returnFlow() { return get(D_RETURN_FLOW_X10) / 10.0D; }
    public int intakeTotal() { return get(D_INTAKE_TOTAL); }
    public int intakeReady() { return get(D_INTAKE_READY); }
    public double intakeInput() { return get(D_INTAKE_INPUT_X10) / 10.0D; }
    public double intakeCapacity() { return get(D_INTAKE_CAPACITY_X10) / 10.0D; }
''')

# GUI: Intake shows network aggregate instead of only the single-block rating.
# Fan shows the aggregate fresh-air contribution on its BACK/mixing plenum.
replace_once(JAVA / 'client/MachineScreen.java',
'''        if (menu.machineType() == MachineMenu.TYPE_FILTER || menu.machineType() == MachineMenu.TYPE_INTAKE) {
            graphics.drawString(font, String.format(Locale.ROOT, "Rated airflow: %.1f m³/s", menu.flow()), 12, 194, 0xFF7F9298, false);
        } else if (menu.machineType() == MachineMenu.TYPE_AIRLOCK) {
''',
'''        if (menu.machineType() == MachineMenu.TYPE_INTAKE) {
            graphics.drawString(font, String.format(Locale.ROOT, "Network %d/%d ready | Fresh %.1f/%.1f m³/s",
                    menu.intakeReady(), menu.intakeTotal(), menu.intakeInput(), menu.intakeCapacity()),
                    12, 194, 0xFF7F9298, false);
        } else if (menu.machineType() == MachineMenu.TYPE_FILTER) {
            graphics.drawString(font, String.format(Locale.ROOT, "Rated airflow: %.1f m³/s", menu.flow()), 12, 194, 0xFF7F9298, false);
        } else if (menu.machineType() == MachineMenu.TYPE_AIRLOCK) {
''')

replace_once(JAVA / 'client/MachineScreen.java',
'''        graphics.drawString(font, String.format(Locale.ROOT, "Supply flow: %.1f | Return flow: %.1f m³/s",
                menu.supplyFlow(), menu.returnFlow()), 12, 142, 0xFFD3DDDF, false);
        if (volume > 0) {
            graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 12, 158, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 124, 158, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%%", menu.oxygenPercent()), 12, 171, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "CO2: %.2f%%", menu.co2Percent()), 124, 171, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 12, 184, 0xFFD3DDDF, false);
        }
        graphics.drawString(font, "BACK = return/mixing | FRONT = supply", 12, 197, 0xFF7F9298, false);
''',
'''        graphics.drawString(font, String.format(Locale.ROOT, "Supply flow: %.1f | Return flow: %.1f m³/s",
                menu.supplyFlow(), menu.returnFlow()), 12, 140, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Fresh intake: %.1f/%.1f m³/s (%d/%d ready)",
                menu.intakeInput(), menu.intakeCapacity(), menu.intakeReady(), menu.intakeTotal()),
                12, 153, 0xFF9DB7BD, false);
        if (volume > 0) {
            graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 12, 166, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 124, 166, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%%", menu.oxygenPercent()), 12, 179, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "CO2: %.2f%%", menu.co2Percent()), 124, 179, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 12, 192, 0xFFD3DDDF, false);
        }
''')

print('Afterfall 0.7.2.2 multi-intake network diagnostics patch applied')
