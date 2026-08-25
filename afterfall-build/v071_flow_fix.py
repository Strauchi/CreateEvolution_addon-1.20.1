from pathlib import Path
import re

ROOT = Path('Afterfall')
JAVA = ROOT / 'src/main/java/dev/afterfall'


def write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'Expected text not found in {p}: {old[:160]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# 0.7.1: Main ventilation fans become true directional transfer devices.
# BACK/opposite FACING = inlet plenum, FRONT/FACING = distribution shaft.

write(JAVA / 'room/VentilationNetworkScanner.java', r'''package dev.afterfall.room;

import dev.afterfall.block.AirVentBlock;
import dev.afterfall.block.VentilationFanBlock;
import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayDeque;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Treats a player-built, enclosed air tunnel as a ventilation network. The air
 * cells remain ordinary Minecraft air blocks; vents/fans are airtight boundary
 * blocks and are discovered while flood-filling the shaft volume.
 */
public final class VentilationNetworkScanner {
    public static final int MAX_SHAFT_VOLUME = 8192;

    public static Network scan(ServerLevel level, BlockPos shaftStart) {
        if (!RoomScanner.airCanPass(level, shaftStart)) return null;
        RoomScanResult shaft = RoomScanner.scan(level, shaftStart);
        if (!shaft.sealed()) return new Network(shaft, List.of(), List.of());

        ArrayDeque<BlockPos> queue = new ArrayDeque<>();
        Set<Long> visited = new HashSet<>();
        Set<Long> vents = new HashSet<>();
        Set<Long> fans = new HashSet<>();
        queue.add(shaftStart.immutable());
        visited.add(shaftStart.asLong());

        while (!queue.isEmpty() && visited.size() <= MAX_SHAFT_VOLUME) {
            BlockPos current = queue.removeFirst();
            for (Direction direction : Direction.values()) {
                BlockPos next = current.relative(direction);
                if (RoomScanner.airCanPass(level, next)) {
                    if (visited.add(next.asLong())) queue.addLast(next.immutable());
                    continue;
                }

                BlockState state = level.getBlockState(next);
                if (state.is(ModBlocks.AIR_VENT.get()) && state.hasProperty(AirVentBlock.FACING)) {
                    Direction facing = state.getValue(AirVentBlock.FACING);
                    if (next.relative(facing.getOpposite()).equals(current)) vents.add(next.asLong());
                }
                if (state.is(ModBlocks.VENTILATION_FAN.get()) && state.hasProperty(VentilationFanBlock.FACING)) {
                    Direction facing = state.getValue(VentilationFanBlock.FACING);
                    // FACING is the fan outlet/front. It must point into this shaft.
                    if (next.relative(facing).equals(current)) fans.add(next.asLong());
                }
            }
        }

        List<BlockPos> ventPositions = vents.stream().map(BlockPos::of)
                .sorted(Comparator.comparingLong(BlockPos::asLong)).toList();
        List<BlockPos> fanPositions = fans.stream().map(BlockPos::of)
                .sorted(Comparator.comparingLong(BlockPos::asLong)).toList();
        return new Network(shaft, ventPositions, fanPositions);
    }

    /** Returns the sealed air volume directly behind a directional fan. */
    public static RoomScanResult inletForFan(ServerLevel level, BlockPos fanPos) {
        BlockState state = level.getBlockState(fanPos);
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        BlockPos start = fanPos.relative(facing.getOpposite());
        if (!RoomScanner.airCanPass(level, start)) return null;
        RoomScanResult scan = RoomScanner.scan(level, start);
        return scan.sealed() ? scan : null;
    }

    public static RoomScanResult roomForVent(ServerLevel level, BlockPos ventPos) {
        BlockState state = level.getBlockState(ventPos);
        if (!state.is(ModBlocks.AIR_VENT.get()) || !state.hasProperty(AirVentBlock.FACING)) return null;
        Direction facing = state.getValue(AirVentBlock.FACING);
        BlockPos start = ventPos.relative(facing);
        if (!RoomScanner.airCanPass(level, start)) return null;
        RoomScanResult scan = RoomScanner.scan(level, start);
        return scan.sealed() ? scan : null;
    }

    public static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        return RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
    }

    public record Network(RoomScanResult shaft, List<BlockPos> vents, List<BlockPos> fans) {
        public boolean valid() { return shaft != null && shaft.sealed(); }
        public int supplyVentCount(ServerLevel level) {
            int count = 0;
            for (BlockPos pos : vents) {
                BlockState state = level.getBlockState(pos);
                if (state.is(ModBlocks.AIR_VENT.get()) && !state.getValue(AirVentBlock.RETURN_MODE)) count++;
            }
            return count;
        }
        public int returnVentCount(ServerLevel level) {
            int count = 0;
            for (BlockPos pos : vents) {
                BlockState state = level.getBlockState(pos);
                if (state.is(ModBlocks.AIR_VENT.get()) && state.getValue(AirVentBlock.RETURN_MODE)) count++;
            }
            return count;
        }
    }

    private VentilationNetworkScanner() {}
}
''')

write(JAVA / 'blockentity/VentilationFanBlockEntity.java', r'''package dev.afterfall.blockentity;

import dev.afterfall.block.AirVentBlock;
import dev.afterfall.block.VentilationFanBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.VentilationNetworkScanner;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class VentilationFanBlockEntity extends BlockEntity {
    public static final int ENERGY_CAPACITY = 80_000;
    public static final int ENERGY_PER_SECOND = 800;
    public static final double FLOW_M3_PER_SECOND = 48.0D;
    public static final double MAX_FLOW_PER_VENT = 18.0D;

    private final MachineEnergyStorage energy = new MachineEnergyStorage(
            ENERGY_CAPACITY, 4_000, 0, this::setChanged);
    private boolean enabled = true;

    public VentilationFanBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.VENTILATION_FAN.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public boolean enabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; setChanged(); }

    /** FRONT/FACING is the outlet into the distribution shaft. */
    public VentilationNetworkScanner.Network inspectNetwork(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        return VentilationNetworkScanner.scan(level, worldPosition.relative(facing));
    }

    /** BACK/opposite FACING is the sealed inlet plenum/source volume. */
    public RoomScanResult inspectInlet(ServerLevel level) {
        return VentilationNetworkScanner.inletForFan(level, worldPosition);
    }

    public double availableNetworkFlow(ServerLevel level) {
        VentilationNetworkScanner.Network network = inspectNetwork(level);
        if (network == null || !network.valid()) return 0.0D;
        int availableFans = 0;
        for (BlockPos fanPos : network.fans()) {
            if (level.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan
                    && fan.enabled && fan.inspectInlet(level) != null
                    && MachinePower.available(level, fanPos, fan.energy, ENERGY_PER_SECOND)) {
                availableFans++;
            }
        }
        return availableFans * FLOW_M3_PER_SECOND;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, VentilationFanBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L || !be.enabled) return;

        VentilationNetworkScanner.Network network = be.inspectNetwork(serverLevel);
        if (network == null || !network.valid() || network.fans().isEmpty()) return;

        BlockPos leader = network.fans().stream().min(Comparator.comparingLong(BlockPos::asLong)).orElse(pos);
        if (!leader.equals(pos)) return; // one network update per second, even with multiple fans

        List<PoweredFan> powered = new ArrayList<>();
        for (BlockPos fanPos : network.fans()) {
            if (!(serverLevel.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan) || !fan.enabled) continue;
            RoomScanResult inlet = fan.inspectInlet(serverLevel);
            if (inlet == null || inlet.anchor().equals(network.shaft().anchor())) continue;
            if (MachinePower.consumeOrRedstoneFallback(serverLevel, fanPos, fan.energy, ENERGY_PER_SECOND)) {
                powered.add(new PoweredFan(fanPos, inlet));
            }
        }
        if (powered.isEmpty()) return;

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere shaftAir = VentilationNetworkScanner.atmosphere(serverLevel, network.shaft());

        // 0.7.1: Fans now physically move composition from their sealed BACK/inlet
        // plenum into the FRONT/distribution shaft. 0.7.0 only powered vent exchange,
        // leaving the prefiltered inlet room and downstream shaft as unrelated atmospheres.
        for (PoweredFan fan : powered) {
            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, fan.inlet);
            double inletFraction = Math.min(1.0D,
                    FLOW_M3_PER_SECOND / Math.max(1.0D, network.shaft().volume()));
            shaftAir.exchangeFrom(inletAir, inletFraction);
        }
        saved.markChanged();

        // The fan must be able to prime/clean a shaft before any room vents exist.
        if (network.vents().isEmpty()) return;

        List<VentTarget> targets = new ArrayList<>();
        for (BlockPos ventPos : network.vents()) {
            BlockState ventState = serverLevel.getBlockState(ventPos);
            if (!ventState.is(ModBlocks.AIR_VENT.get())) continue;
            RoomScanResult room = VentilationNetworkScanner.roomForVent(serverLevel, ventPos);
            if (room == null || room.anchor().equals(network.shaft().anchor())) continue;
            boolean returnMode = ventState.getValue(AirVentBlock.RETURN_MODE);
            targets.add(new VentTarget(ventPos, room, returnMode));
        }
        if (targets.isEmpty()) return;

        double totalFlow = powered.size() * FLOW_M3_PER_SECOND;
        double perVentFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / Math.max(1, targets.size()));

        // Return air is mixed into the shaft first, then the resulting central air
        // is distributed through supply vents. Pressure/mass balance remains 0.8 work.
        for (VentTarget target : targets) {
            if (!target.returnMode) continue;
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double fraction = Math.min(0.30D, perVentFlow / Math.max(1.0D, network.shaft().volume()));
            shaftAir.exchangeFrom(roomAir, fraction);
        }
        for (VentTarget target : targets) {
            if (target.returnMode) continue;
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double fraction = Math.min(0.30D, perVentFlow / Math.max(1.0D, target.room.volume()));
            roomAir.exchangeFrom(shaftAir, fraction);
        }
        saved.markChanged();
    }

    private record PoweredFan(BlockPos pos, RoomScanResult inlet) {}
    private record VentTarget(BlockPos pos, RoomScanResult room, boolean returnMode) {}

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        enabled = !tag.contains("Enabled") || tag.getBoolean("Enabled");
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        tag.putBoolean("Enabled", enabled);
    }
}
''')

# Fan GUI/data: require a sealed inlet, but allow shaft priming with zero vents.
menu = JAVA / 'menu/MachineMenu.java'
replace_once(menu,
'''            VentilationNetworkScanner.Network network = be.inspectNetwork(level);
            if (network != null && network.valid()) {
                RoomAtmosphere shaftAir = atmosphere(level, network.shaft());
                setAtmosphere(network.shaft(), shaftAir);
                data.set(D_EXTRA, network.vents().size());
                data.set(D_FLOW_X10, scale(be.availableNetworkFlow(level), 10.0D));
            }
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (network == null || !network.valid()) data.set(D_STATUS, 30);
            else if (network.vents().isEmpty()) data.set(D_STATUS, 31);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), VentilationFanBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else data.set(D_STATUS, 32);''',
'''            VentilationNetworkScanner.Network network = be.inspectNetwork(level);
            RoomScanResult inlet = be.inspectInlet(level);
            if (network != null && network.valid()) {
                RoomAtmosphere shaftAir = atmosphere(level, network.shaft());
                setAtmosphere(network.shaft(), shaftAir);
                data.set(D_EXTRA, network.vents().size());
                data.set(D_FLOW_X10, scale(be.availableNetworkFlow(level), 10.0D));
            }
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (network == null || !network.valid()) data.set(D_STATUS, 30);
            else if (inlet == null || inlet.anchor().equals(network.shaft().anchor())) data.set(D_STATUS, 33);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), VentilationFanBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (network.vents().isEmpty()) data.set(D_STATUS, 31);
            else data.set(D_STATUS, 32);''')

screen = JAVA / 'client/MachineScreen.java'
replace_once(screen,
'''        graphics.drawString(font, "Fan front must face into the sealed shaft.", 12, 194, 0xFF7F9298, false);''',
'''        graphics.drawString(font, "BACK = sealed inlet | FRONT = sealed shaft", 12, 194, 0xFF7F9298, false);''')
replace_once(screen,
'''            case 31 -> "STANDBY - NO CONNECTED VENTS";
            case 32 -> "CIRCULATING";''',
'''            case 31 -> "PRIMING SHAFT - NO VENTS";
            case 32 -> "CIRCULATING";
            case 33 -> "ERROR - NO SEALED INLET";''')
replace_once(screen,
'''        if (status == 4 || status == 7 || status >= 20) return 0xFFE1B45A;''',
'''        if (status == 4 || status == 7 || status == 31 || status >= 20) return 0xFFE1B45A;''')

# Bump version from the exact 0.7.0 snapshot.
props = ROOT / 'gradle.properties'
text = props.read_text(encoding='utf-8')
text, n = re.subn(r'(?m)^mod_version=.*$', 'mod_version=0.7.1', text, count=1)
if n != 1:
    raise RuntimeError('mod_version not found')
props.write_text(text, encoding='utf-8')

# Update startup log if the literal is present.
afterfall = JAVA / 'Afterfall.java'
text = afterfall.read_text(encoding='utf-8')
text = text.replace('Afterfall 0.7.0 initialized', 'Afterfall 0.7.1 initialized')
text = text.replace('Afterfall 0.6.0 initialized', 'Afterfall 0.7.1 initialized')
afterfall.write_text(text, encoding='utf-8')

print('Afterfall 0.7.1 directional ventilation flow fix applied')
