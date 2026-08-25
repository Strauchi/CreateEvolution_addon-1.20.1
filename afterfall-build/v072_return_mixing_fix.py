from pathlib import Path
import re

ROOT = Path('Afterfall')
JAVA = ROOT / 'src/main/java/dev/afterfall'


def sub_once(path, pattern, replacement, flags=re.S):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    new, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f'Expected one replacement in {p}, got {count}: {pattern[:100]}')
    p.write_text(new, encoding='utf-8')


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'Expected text not found in {p}: {old[:120]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')

# ---------------------------------------------------------------------------
# Afterfall 0.7.2
# - separate RETURN network on the fan inlet side
# - correct fan diagnostics/current flow
# - robust room-atmosphere mixing when sealed spaces are joined
# - exterior opening invalidates stale clean room air
# ---------------------------------------------------------------------------

replace_once(ROOT / 'gradle.properties', 'mod_version=0.7.1', 'mod_version=0.7.2')

# Unknown newly-connected volume must not inherit a clean anchor for free.
# Explicit known room merges pre-size their mixed atmospheres below, so this
# fallback only represents genuinely unknown/new volume as ambient air.
sub_once(JAVA / 'room/RoomAtmosphere.java',
         r'    public void updateVolume\(int newVolume, double outsideDust, double outsideAirborneRadiation\) \{.*?\n    \}\n\n    public void exchangeFrom',
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

    public void setVolumePreservingComposition(int newVolume) {
        volume = Math.max(1, newVolume);
    }

    public void exchangeFrom''')

# Door merge preparation: after two known atmospheres are mixed, mark both as
# already representing the future combined volume. This prevents the normal
# unknown-volume fallback from contaminating an explicitly known merge twice.
replace_once(JAVA / 'room/RoomAtmosphereSavedData.java',
'''    public void markChanged() { setDirty(); }
''',
'''    public void prepareMergedVolume(long firstRoomId, long secondRoomId, int mergedVolume) {
        RoomAtmosphere first = rooms.get(firstRoomId);
        RoomAtmosphere second = rooms.get(secondRoomId);
        if (first != null) first.setVolumePreservingComposition(mergedVolume);
        if (second != null) second.setVolumePreservingComposition(mergedVolume);
        if (first != null || second != null) setDirty();
    }

    public void markChanged() { setDirty(); }
''')

# Enhance door-opening mixing. Two sealed rooms are volume-weighted before the
# door opens. A sealed room opened directly to an unsealed/outside volume is
# immediately marked as ambient, preventing stale clean air from returning when
# it is closed again.
replace_once(JAVA / 'room/RoomEnvironmentManager.java',
'''import net.minecraft.core.BlockPos;
''',
'''import dev.afterfall.content.ModBlocks;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
''')
replace_once(JAVA / 'room/RoomEnvironmentManager.java',
'''import net.minecraft.util.Mth;
''',
'''import net.minecraft.util.Mth;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DoubleBlockHalf;
''')
sub_once(JAVA / 'room/RoomEnvironmentManager.java',
         r'    public static void equilibrateAcrossClosedDoor\(ServerLevel level, BlockPos doorPos\) \{.*?\n    \}\n\n    public static boolean isWasteland',
'''    public static void equilibrateAcrossClosedDoor(ServerLevel level, BlockPos doorPos) {
        BlockState clicked = level.getBlockState(doorPos);
        if (!(clicked.getBlock() instanceof DoorBlock)) return;

        BlockPos lower = doorPos;
        if (clicked.hasProperty(BlockStateProperties.DOUBLE_BLOCK_HALF)
                && clicked.getValue(BlockStateProperties.DOUBLE_BLOCK_HALF) == DoubleBlockHalf.UPPER) {
            lower = doorPos.below();
        }
        BlockState doorState = level.getBlockState(lower);
        if (!(doorState.getBlock() instanceof DoorBlock)
                || !doorState.hasProperty(BlockStateProperties.HORIZONTAL_FACING)) return;

        Direction facing = doorState.getValue(BlockStateProperties.HORIZONTAL_FACING);
        RoomScanResult firstScan = RoomMachineUtil.scanDoorSide(level, lower, facing);
        RoomScanResult secondScan = RoomMachineUtil.scanDoorSide(level, lower, facing.getOpposite());
        if (firstScan == null || secondScan == null) return;

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(level);
        long gameTime = level.getGameTime();

        if (firstScan.sealed() && secondScan.sealed()) {
            if (firstScan.anchor().equals(secondScan.anchor())) return;

            boolean firstWasteland = isWasteland(level, firstScan.anchor());
            boolean secondWasteland = isWasteland(level, secondScan.anchor());
            saved.getOrCreate(firstScan.anchor().asLong(), firstScan.volume(),
                    outsideDust(firstWasteland), outsideAirborneRadiation(firstWasteland), gameTime);
            saved.getOrCreate(secondScan.anchor().asLong(), secondScan.volume(),
                    outsideDust(secondWasteland), outsideAirborneRadiation(secondWasteland), gameTime);
            saved.equilibrate(firstScan.anchor().asLong(), secondScan.anchor().asLong(), gameTime);

            // Open door cells become part of the joined air volume. Heavy blast doors
            // expose six cells (3x2); normal doors expose two.
            int connectorCells = doorState.is(ModBlocks.HEAVY_BLAST_DOOR.get()) ? 6 : 2;
            saved.prepareMergedVolume(firstScan.anchor().asLong(), secondScan.anchor().asLong(),
                    firstScan.volume() + secondScan.volume() + connectorCells);
            return;
        }

        // Opening a sealed room to an unsealed side means that the saved sealed
        // atmosphere can no longer remain pristine. Gameplay-scale equalization is
        // immediate so closing the room again starts with actual wasteland air.
        RoomScanResult sealedSide = firstScan.sealed() ? firstScan : (secondScan.sealed() ? secondScan : null);
        if (sealedSide != null) {
            boolean wasteland = isWasteland(level, doorPos);
            RoomAtmosphere atmosphere = saved.getOrCreate(sealedSide.anchor().asLong(), sealedSide.volume(),
                    outsideDust(wasteland), outsideAirborneRadiation(wasteland), gameTime);
            atmosphere.exposeToOutside(outsideDust(wasteland), outsideAirborneRadiation(wasteland), 1.0D);
            saved.markChanged();
        }
    }

    public static boolean isWasteland''')

# Main fan: FRONT remains the supply shaft. BACK is now also scanned as a
# complete return/mixing network. RETURN vents on that inlet volume pull room air
# into the mixing plenum before the fan sends it into the supply shaft.
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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

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

    /** FRONT/FACING is the outlet into the distribution/supply shaft. */
    public VentilationNetworkScanner.Network inspectNetwork(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        return VentilationNetworkScanner.scan(level, worldPosition.relative(facing));
    }

    /** BACK/opposite FACING is the sealed mixing plenum / return-network volume. */
    public RoomScanResult inspectInlet(ServerLevel level) {
        return VentilationNetworkScanner.inletForFan(level, worldPosition);
    }

    public VentilationNetworkScanner.Network inspectReturnNetwork(ServerLevel level) {
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.VENTILATION_FAN.get()) || !state.hasProperty(VentilationFanBlock.FACING)) return null;
        Direction facing = state.getValue(VentilationFanBlock.FACING);
        return VentilationNetworkScanner.scan(level, worldPosition.relative(facing.getOpposite()));
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

    public int connectedSupplyVentCount(ServerLevel level) {
        VentilationNetworkScanner.Network network = inspectNetwork(level);
        return network == null || !network.valid() ? 0 : validVentCount(level, network, false, network.shaft().anchor());
    }

    public int connectedReturnVentCount(ServerLevel level) {
        VentilationNetworkScanner.Network network = inspectReturnNetwork(level);
        RoomScanResult inlet = inspectInlet(level);
        return network == null || !network.valid() || inlet == null
                ? 0 : validVentCount(level, network, true, inlet.anchor());
    }

    public double currentSupplyFlow(ServerLevel level) {
        return Math.min(availableNetworkFlow(level), connectedSupplyVentCount(level) * MAX_FLOW_PER_VENT);
    }

    public double currentReturnFlow(ServerLevel level) {
        return Math.min(availableNetworkFlow(level), connectedReturnVentCount(level) * MAX_FLOW_PER_VENT);
    }

    private static int validVentCount(ServerLevel level, VentilationNetworkScanner.Network network,
                                      boolean returnMode, BlockPos networkAnchor) {
        int count = 0;
        for (BlockPos ventPos : network.vents()) {
            BlockState ventState = level.getBlockState(ventPos);
            if (!ventState.is(ModBlocks.AIR_VENT.get())
                    || ventState.getValue(AirVentBlock.RETURN_MODE) != returnMode) continue;
            RoomScanResult room = VentilationNetworkScanner.roomForVent(level, ventPos);
            if (room != null && !room.anchor().equals(networkAnchor)) count++;
        }
        return count;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, VentilationFanBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel) || serverLevel.getGameTime() % 20L != 0L || !be.enabled) return;

        VentilationNetworkScanner.Network supplyNetwork = be.inspectNetwork(serverLevel);
        if (supplyNetwork == null || !supplyNetwork.valid() || supplyNetwork.fans().isEmpty()) return;

        BlockPos leader = supplyNetwork.fans().stream().min(Comparator.comparingLong(BlockPos::asLong)).orElse(pos);
        if (!leader.equals(pos)) return; // one update per shared supply network per second

        List<PoweredFan> powered = new ArrayList<>();
        for (BlockPos fanPos : supplyNetwork.fans()) {
            if (!(serverLevel.getBlockEntity(fanPos) instanceof VentilationFanBlockEntity fan) || !fan.enabled) continue;
            RoomScanResult inlet = fan.inspectInlet(serverLevel);
            if (inlet == null || inlet.anchor().equals(supplyNetwork.shaft().anchor())) continue;
            if (MachinePower.consumeOrRedstoneFallback(serverLevel, fanPos, fan.energy, ENERGY_PER_SECOND)) {
                powered.add(new PoweredFan(fan, fanPos, inlet));
            }
        }
        if (powered.isEmpty()) return;

        RoomAtmosphereSavedData saved = RoomAtmosphereSavedData.get(serverLevel);
        RoomAtmosphere shaftAir = VentilationNetworkScanner.atmosphere(serverLevel, supplyNetwork.shaft());

        // Fans sharing the same BACK plenum form one suction group. RETURN vents
        // bordering that plenum/return shaft feed room air into it before supply air
        // is pushed through the fan. This supports physically separate return shafts.
        Map<Long, List<PoweredFan>> inletGroups = new LinkedHashMap<>();
        for (PoweredFan fan : powered) {
            inletGroups.computeIfAbsent(fan.inlet.anchor().asLong(), ignored -> new ArrayList<>()).add(fan);
        }

        for (List<PoweredFan> group : inletGroups.values()) {
            PoweredFan representative = group.get(0);
            RoomScanResult inlet = representative.inlet;
            RoomAtmosphere inletAir = VentilationNetworkScanner.atmosphere(serverLevel, inlet);
            VentilationNetworkScanner.Network returnNetwork = representative.fan.inspectReturnNetwork(serverLevel);

            if (returnNetwork != null && returnNetwork.valid()) {
                List<VentTarget> returns = collectTargets(serverLevel, returnNetwork, true, inlet.anchor());
                if (!returns.isEmpty()) {
                    double returnCapacity = group.size() * FLOW_M3_PER_SECOND;
                    double perReturnFlow = Math.min(MAX_FLOW_PER_VENT, returnCapacity / returns.size());
                    for (VentTarget target : returns) {
                        RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
                        double fraction = Math.min(0.30D,
                                perReturnFlow / Math.max(1.0D, inlet.volume()));
                        inletAir.exchangeFrom(roomAir, fraction);
                    }
                }
            }

            // Move the resulting return/mixing-plenum composition through the fan
            // into the supply shaft. Multiple fans on one inlet scale throughput.
            double groupFlow = group.size() * FLOW_M3_PER_SECOND;
            double inletFraction = Math.min(1.0D,
                    groupFlow / Math.max(1.0D, supplyNetwork.shaft().volume()));
            shaftAir.exchangeFrom(inletAir, inletFraction);
        }
        saved.markChanged();

        // SUPPLY vents are only read from the FRONT network. RETURN vents belong on
        // the fan's BACK/mixing network and are intentionally ignored here.
        List<VentTarget> supplies = collectTargets(serverLevel, supplyNetwork, false, supplyNetwork.shaft().anchor());
        if (supplies.isEmpty()) return; // shaft priming still happened above

        double totalFlow = powered.size() * FLOW_M3_PER_SECOND;
        double perSupplyFlow = Math.min(MAX_FLOW_PER_VENT, totalFlow / supplies.size());
        for (VentTarget target : supplies) {
            RoomAtmosphere roomAir = VentilationNetworkScanner.atmosphere(serverLevel, target.room);
            double fraction = Math.min(0.30D,
                    perSupplyFlow / Math.max(1.0D, target.room.volume()));
            roomAir.exchangeFrom(shaftAir, fraction);
        }
        saved.markChanged();
    }

    private static List<VentTarget> collectTargets(ServerLevel level, VentilationNetworkScanner.Network network,
                                                    boolean returnMode, BlockPos networkAnchor) {
        List<VentTarget> targets = new ArrayList<>();
        for (BlockPos ventPos : network.vents()) {
            BlockState ventState = level.getBlockState(ventPos);
            if (!ventState.is(ModBlocks.AIR_VENT.get())
                    || ventState.getValue(AirVentBlock.RETURN_MODE) != returnMode) continue;
            RoomScanResult room = VentilationNetworkScanner.roomForVent(level, ventPos);
            if (room == null || room.anchor().equals(networkAnchor)) continue;
            targets.add(new VentTarget(ventPos, room));
        }
        return targets;
    }

    private record PoweredFan(VentilationFanBlockEntity fan, BlockPos pos, RoomScanResult inlet) {}
    private record VentTarget(BlockPos pos, RoomScanResult room) {}

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

# Menu diagnostics: capacity + actual supply/return flow and separate counts.
replace_once(JAVA / 'menu/MachineMenu.java', 'public static final int DATA_COUNT = 18;', 'public static final int DATA_COUNT = 21;')
replace_once(JAVA / 'menu/MachineMenu.java',
'''    public static final int D_ENABLED = 17;
''',
'''    public static final int D_ENABLED = 17;
    public static final int D_RETURN_VENTS = 18;
    public static final int D_SUPPLY_FLOW_X10 = 19;
    public static final int D_RETURN_FLOW_X10 = 20;
''')
sub_once(JAVA / 'menu/MachineMenu.java',
         r'        if \(serverBlockEntity instanceof VentilationFanBlockEntity be\) \{.*?\n            return;\n        \}\n\n        if \(serverBlockEntity instanceof EmergencyGeneratorBlockEntity be\)',
'''        if (serverBlockEntity instanceof VentilationFanBlockEntity be) {
            data.set(D_TYPE, TYPE_FAN);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            VentilationNetworkScanner.Network network = be.inspectNetwork(level);
            RoomScanResult inlet = be.inspectInlet(level);
            int supplyVents = be.connectedSupplyVentCount(level);
            int returnVents = be.connectedReturnVentCount(level);
            data.set(D_EXTRA, supplyVents);
            data.set(D_RETURN_VENTS, returnVents);
            data.set(D_FLOW_X10, scale(be.availableNetworkFlow(level), 10.0D));
            data.set(D_SUPPLY_FLOW_X10, scale(be.currentSupplyFlow(level), 10.0D));
            data.set(D_RETURN_FLOW_X10, scale(be.currentReturnFlow(level), 10.0D));
            if (network != null && network.valid()) {
                RoomAtmosphere shaftAir = atmosphere(level, network.shaft());
                setAtmosphere(network.shaft(), shaftAir);
            }
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (network == null || !network.valid()) data.set(D_STATUS, 30);
            else if (inlet == null || inlet.anchor().equals(network.shaft().anchor())) data.set(D_STATUS, 33);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), VentilationFanBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (supplyVents == 0) data.set(D_STATUS, 31);
            else data.set(D_STATUS, 32);
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be)''')
replace_once(JAVA / 'menu/MachineMenu.java',
'''    public double flow() { return get(D_FLOW_X10) / 10.0D; }
''',
'''    public double flow() { return get(D_FLOW_X10) / 10.0D; }
    public int returnVentCount() { return get(D_RETURN_VENTS); }
    public double supplyFlow() { return get(D_SUPPLY_FLOW_X10) / 10.0D; }
    public double returnFlow() { return get(D_RETURN_FLOW_X10) / 10.0D; }
''')

# Fan GUI: don't interpret fan status codes as airlock cycle states, and show
# explicit supply/return diagnostics so the player can tell whether circulation
# is actually occurring.
sub_once(JAVA / 'client/MachineScreen.java',
         r'    private void renderFan\(GuiGraphics graphics\) \{.*?\n    \}\n\n    private void renderGenerator',
'''    private void renderFan(GuiGraphics graphics) {
        int volume = menu.get(MachineMenu.D_ROOM_VOLUME);
        graphics.drawString(font, "Ventilation shaft", 12, 88, 0xFFAAB6B9, false);
        graphics.drawString(font, "Supply shaft: " + volume + " m³", 12, 103, 0xFFD3DDDF, false);
        graphics.drawString(font, "Supply vents: " + menu.get(MachineMenu.D_EXTRA)
                + " | Return vents: " + menu.returnVentCount(), 12, 116, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Fan capacity: %.1f m³/s", menu.flow()), 12, 129, 0xFFD3DDDF, false);
        graphics.drawString(font, String.format(Locale.ROOT, "Supply flow: %.1f | Return flow: %.1f m³/s",
                menu.supplyFlow(), menu.returnFlow()), 12, 142, 0xFFD3DDDF, false);
        if (volume > 0) {
            graphics.drawString(font, String.format(Locale.ROOT, "Air Quality: %.1f%%", menu.airQuality()), 12, 158, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Dust: %.2f%%", menu.dustPercent()), 124, 158, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "O2: %.2f%%", menu.oxygenPercent()), 12, 171, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "CO2: %.2f%%", menu.co2Percent()), 124, 171, 0xFFD3DDDF, false);
            graphics.drawString(font, String.format(Locale.ROOT, "Air Rad: %.2f mSv/h", menu.airRadiation()), 12, 184, 0xFFD3DDDF, false);
        }
        graphics.drawString(font, "BACK = return/mixing | FRONT = supply", 12, 197, 0xFF7F9298, false);
    }

    private void renderGenerator''')
replace_once(JAVA / 'client/MachineScreen.java',
'''        if (status >= 20) return "CYCLE: " + airlockCycle();
''',
'''        if (menu.machineType() == MachineMenu.TYPE_AIRLOCK && status >= 20) return "CYCLE: " + airlockCycle();
''')
replace_once(JAVA / 'client/MachineScreen.java',
'''        if (status == 4 || status == 7 || status == 31 || status >= 20) return 0xFFE1B45A;
''',
'''        if (status == 4 || status == 7 || status == 31
                || (menu.machineType() == MachineMenu.TYPE_AIRLOCK && status >= 20)) return 0xFFE1B45A;
''')

# Keep startup log version useful while testing.
replace_once(JAVA / 'Afterfall.java', 'Afterfall 0.6.0 initialized', 'Afterfall 0.7.2 initialized')

print('Afterfall 0.7.2 return-network + atmosphere-mixing patch applied')
