package dev.afterfall.blockentity;

import dev.afterfall.content.ModAttachments;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.machine.FilterBank;
import dev.afterfall.machine.MachineEnergyStorage;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomMachineUtil;
import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.RoomScanner;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Mth;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.List;
import java.util.Locale;
import java.util.UUID;

public final class AirlockControllerBlockEntity extends BlockEntity {
    public static final int ENERGY_CAPACITY = 40_000;
    public static final int ENERGY_PER_PURGE_STEP = 300;
    public static final int ENERGY_PER_DOOR_OPERATION = 80;
    public static final int MAX_PURGE_TICKS = 20 * 30;

    public enum CycleState {
        IDLE,
        PREPARING_ENTRY,
        WAITING_FOR_ENTRY,
        SEALING_ENTRY,
        PURGING,
        OPENING_EXIT,
        WAITING_FOR_EXIT,
        SEALING_EXIT
    }

    private final MachineEnergyStorage energy = new MachineEnergyStorage(ENERGY_CAPACITY, 2_000, 0, this::setChanged);
    private final FilterBank filters = new FilterBank(this::setChanged);

    private AirlockLogic.StatusType lastStatus;
    private CycleState cycleState = CycleState.IDLE;
    private int stateTicks;
    private BlockPos entryDoor;
    private BlockPos exitDoor;
    private BlockPos chamberAnchor;
    private Direction entryChamberSide;
    private Direction exitChamberSide;
    private UUID requesterId;
    private boolean closeActionDone;

    public AirlockControllerBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.AIRLOCK_CONTROLLER.get(), pos, state);
    }

    public MachineEnergyStorage energyStorage() { return energy; }
    public FilterBank filters() { return filters; }
    public boolean isBusy() { return cycleState != CycleState.IDLE; }
    public CycleState cycleState() { return cycleState; }
    public int stateTicks() { return stateTicks; }

    public boolean installFilter(ServerPlayer player, ItemStack held) {
        return filters.installFromHeld(player, held);
    }

    public boolean hasPowerAvailable(ServerLevel level) {
        return MachinePower.available(level, worldPosition, energy, ENERGY_PER_PURGE_STEP);
    }

    private boolean consumePower(ServerLevel level, int amount) {
        return MachinePower.consumeOrRedstoneFallback(level, worldPosition, energy, amount);
    }

    public boolean requestCycle(ServerLevel level, BlockPos requestedEntryDoor, ServerPlayer requester) {
        if (isBusy()) {
            requester.displayClientMessage(Component.literal("AIRLOCK: BUSY - " + cycleLabel()).withStyle(ChatFormatting.YELLOW), true);
            return false;
        }
        if (!hasPowerAvailable(level)) {
            requester.displayClientMessage(Component.literal("AIRLOCK: NO POWER").withStyle(ChatFormatting.RED), true);
            return false;
        }
        if (!filters.complete()) {
            requester.displayClientMessage(Component.literal("AIRLOCK: FILTER MEDIA REQUIRED | " + filters.compactStatus()).withStyle(ChatFormatting.RED), true);
            return false;
        }

        List<BlockPos> doors = AirlockLogic.findTwoDoors(level, worldPosition);
        BlockPos entry = AirlockLogic.lowerDoorPos(level, requestedEntryDoor);
        if (doors.size() != 2 || entry == null || !doors.contains(entry)) {
            requester.displayClientMessage(Component.literal("AIRLOCK: NOT CONFIGURED - TWO LINKED DOORS REQUIRED").withStyle(ChatFormatting.RED), true);
            return false;
        }

        BlockPos exit = doors.get(0).equals(entry) ? doors.get(1) : doors.get(0);
        AirlockLogic.setDoorOpen(level, doors.get(0), false);
        AirlockLogic.setDoorOpen(level, doors.get(1), false);

        RoomScanResult chamber = RoomMachineUtil.findSealedAdjacentRoom(level, worldPosition);
        if (chamber == null || chamber.volume() > AirlockLogic.MAX_AIRLOCK_VOLUME) {
            requester.displayClientMessage(Component.literal(chamber == null
                    ? "AIRLOCK: CHAMBER NOT SEALED"
                    : "AIRLOCK: CHAMBER TOO LARGE").withStyle(ChatFormatting.RED), true);
            return false;
        }

        Direction entrySide = AirlockLogic.chamberSideForDoor(level, entry, chamber.anchor());
        Direction exitSide = AirlockLogic.chamberSideForDoor(level, exit, chamber.anchor());
        if (entrySide == null || exitSide == null) {
            requester.displayClientMessage(Component.literal("AIRLOCK: DOOR ORIENTATION COULD NOT BE RESOLVED").withStyle(ChatFormatting.RED), true);
            return false;
        }

        this.entryDoor = entry;
        this.exitDoor = exit;
        this.chamberAnchor = chamber.anchor();
        this.entryChamberSide = entrySide;
        this.exitChamberSide = exitSide;
        this.requesterId = requester.getUUID();
        transition(level, CycleState.PREPARING_ENTRY,
                Component.literal("AIRLOCK: REQUEST ACCEPTED - PREPARING ENTRY").withStyle(ChatFormatting.AQUA));
        return true;
    }

    public boolean requestFromController(ServerLevel level, ServerPlayer requester) {
        if (isBusy()) {
            requester.displayClientMessage(Component.literal("AIRLOCK: " + cycleLabel()).withStyle(ChatFormatting.YELLOW), true);
            return false;
        }
        if (!hasPowerAvailable(level)) {
            requester.displayClientMessage(Component.literal("AIRLOCK: NO POWER").withStyle(ChatFormatting.RED), true);
            return false;
        }
        if (!filters.complete()) {
            requester.displayClientMessage(Component.literal("AIRLOCK: FILTER MEDIA REQUIRED | " + filters.compactStatus()).withStyle(ChatFormatting.RED), true);
            return false;
        }

        List<BlockPos> doors = AirlockLogic.findTwoDoors(level, worldPosition);
        if (doors.size() != 2) {
            requester.displayClientMessage(Component.literal("AIRLOCK: NOT CONFIGURED - TWO LINKED DOORS REQUIRED").withStyle(ChatFormatting.RED), true);
            return false;
        }
        AirlockLogic.setDoorOpen(level, doors.get(0), false);
        AirlockLogic.setDoorOpen(level, doors.get(1), false);
        RoomScanResult chamber = RoomMachineUtil.findSealedAdjacentRoom(level, worldPosition);
        if (chamber == null || chamber.volume() > AirlockLogic.MAX_AIRLOCK_VOLUME) {
            requester.displayClientMessage(Component.literal("AIRLOCK: CHAMBER NOT READY").withStyle(ChatFormatting.RED), true);
            return false;
        }

        RoomScanResult playerScan = RoomScanner.scan(level, requester.blockPosition());
        boolean playerInside = playerScan.sealed() && playerScan.anchor().equals(chamber.anchor());
        if (!playerInside) {
            BlockPos nearest = AirlockLogic.closestLinkedDoor(level, worldPosition, requester.blockPosition());
            return nearest != null && requestCycle(level, nearest, requester);
        }

        BlockPos targetExit = chooseDoorByLook(requester, doors);
        BlockPos other = doors.get(0).equals(targetExit) ? doors.get(1) : doors.get(0);
        Direction exitSide = AirlockLogic.chamberSideForDoor(level, targetExit, chamber.anchor());
        Direction entrySide = AirlockLogic.chamberSideForDoor(level, other, chamber.anchor());
        if (exitSide == null || entrySide == null) return false;

        this.entryDoor = other;
        this.exitDoor = targetExit;
        this.chamberAnchor = chamber.anchor();
        this.entryChamberSide = entrySide;
        this.exitChamberSide = exitSide;
        this.requesterId = requester.getUUID();
        transition(level, CycleState.PURGING,
                Component.literal("AIRLOCK: CYCLE STARTED - PURGING").withStyle(ChatFormatting.YELLOW));
        return true;
    }

    private BlockPos chooseDoorByLook(ServerPlayer player, List<BlockPos> doors) {
        BlockPos best = doors.get(0);
        double bestScore = -Double.MAX_VALUE;
        var look = player.getLookAngle();
        for (BlockPos door : doors) {
            double dx = door.getX() + 0.5D - player.getX();
            double dy = door.getY() + 1.0D - player.getEyeY();
            double dz = door.getZ() + 0.5D - player.getZ();
            double len = Math.sqrt(dx * dx + dy * dy + dz * dz);
            if (len <= 0.0001D) continue;
            double score = (dx * look.x + dy * look.y + dz * look.z) / len;
            if (score > bestScore) {
                bestScore = score;
                best = door;
            }
        }
        return best;
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, AirlockControllerBlockEntity blockEntity) {
        if (!(level instanceof ServerLevel serverLevel)) return;
        blockEntity.tickCycle(serverLevel);
    }

    private void tickCycle(ServerLevel level) {
        if (cycleState == CycleState.IDLE) {
            if (level.getGameTime() % 20L == 0L) {
                AirlockLogic.AirlockStatus status = AirlockLogic.inspectStatus(level, worldPosition);
                if (lastStatus != status.type()) {
                    lastStatus = status.type();
                    notifyNearbyPlayers(level, worldPosition, status);
                }
            }
            return;
        }

        stateTicks++;
        ServerPlayer requester = requester();

        switch (cycleState) {
            case PREPARING_ENTRY -> {
                forceBothClosed(level);
                if (stateTicks >= 10) {
                    if (!consumePower(level, ENERGY_PER_DOOR_OPERATION)) {
                        notifyRequester(Component.literal("AIRLOCK: WAITING FOR POWER").withStyle(ChatFormatting.RED));
                        return;
                    }
                    AirlockLogic.prepareDoorOpening(level, worldPosition, entryDoor, 0.72D);
                    AirlockLogic.setDoorOpen(level, entryDoor, true);
                    transition(level, CycleState.WAITING_FOR_ENTRY,
                            Component.literal("AIRLOCK: ENTRY OPEN - ENTER CHAMBER").withStyle(ChatFormatting.GREEN));
                }
            }
            case WAITING_FOR_ENTRY -> {
                if (requester != null && entryChamberSide != null
                        && AirlockLogic.isPlayerOnDoorSide(requester, entryDoor, entryChamberSide)) {
                    transition(level, CycleState.SEALING_ENTRY,
                            Component.literal("AIRLOCK: OCCUPANT DETECTED - DOOR CLOSING IN 1s").withStyle(ChatFormatting.AQUA));
                } else if (stateTicks >= 200) {
                    if (requester != null && AirlockLogic.isPlayerInDoorway(requester, entryDoor)) {
                        if (stateTicks % 20 == 0) {
                            notifyRequester(Component.literal("AIRLOCK: DOORWAY OCCUPIED - HOLDING ENTRY DOOR").withStyle(ChatFormatting.YELLOW));
                        }
                        return;
                    }
                    AirlockLogic.setDoorOpen(level, entryDoor, false);
                    finish(level, Component.literal("AIRLOCK: ENTRY REQUEST TIMED OUT").withStyle(ChatFormatting.GRAY));
                }
            }
            case SEALING_ENTRY -> {
                if (!closeActionDone) {
                    if (stateTicks < 20) return;
                    if (requester != null && AirlockLogic.isPlayerInDoorway(requester, entryDoor)) {
                        if (stateTicks % 20 == 0) {
                            notifyRequester(Component.literal("AIRLOCK: DOORWAY OCCUPIED - HOLDING ENTRY DOOR").withStyle(ChatFormatting.YELLOW));
                        }
                        return;
                    }
                    AirlockLogic.setDoorOpen(level, entryDoor, false);
                    closeActionDone = true;
                    stateTicks = 0;
                    setChanged();
                    return;
                }
                if (stateTicks >= 12) {
                    refreshChamber(level);
                    transition(level, CycleState.PURGING,
                            Component.literal("AIRLOCK: SEALED - PURGING").withStyle(ChatFormatting.YELLOW));
                }
            }
            case PURGING -> {
                forceBothClosed(level);
                if (stateTicks % 5 == 0) spawnPurgeParticles(level);

                // A purge must never be able to deadlock the controller forever.
                if (stateTicks >= MAX_PURGE_TICKS) {
                    AirlockLogic.AirlockStatus status = AirlockLogic.inspectStatus(level, worldPosition);
                    String detail = status.hasAtmosphere()
                            ? String.format(Locale.ROOT, "Dust %.3f%% | Air Rad %.3f mSv/h",
                            status.atmosphere().dustPercent(),
                            status.atmosphere().airborneRadiationPerSecond() * 3600.0D)
                            : "chamber unavailable";
                    finish(level, Component.literal("AIRLOCK: PURGE ABORTED - SAFETY TARGET NOT REACHED | " + detail)
                            .withStyle(ChatFormatting.RED));
                    return;
                }

                if (level.getGameTime() % 10L == 0L) {
                    if (!filters.complete()) {
                        notifyRequester(Component.literal("AIRLOCK: PURGE PAUSED - FILTER EXHAUSTED | " + filters.compactStatus()).withStyle(ChatFormatting.RED));
                        return;
                    }
                    if (!consumePower(level, ENERGY_PER_PURGE_STEP)) {
                        notifyRequester(Component.literal("AIRLOCK: PURGE PAUSED - NO POWER").withStyle(ChatFormatting.RED));
                        return;
                    }
                    AirlockLogic.AirlockStatus status = AirlockLogic.inspectStatus(level, worldPosition);
                    if (status.hasAtmosphere()) {
                        purgeAtmosphere(level, status.scan(), status.atmosphere());
                        status = AirlockLogic.inspectStatus(level, worldPosition);
                        if (status.safe()) {
                            transition(level, CycleState.OPENING_EXIT,
                                    Component.literal("AIRLOCK: SAFE - OPENING EXIT").withStyle(ChatFormatting.GREEN));
                        } else if (stateTicks % 40 == 0) {
                            notifyRequester(shortCycleStatus(level));
                        }
                    }
                }
            }
            case OPENING_EXIT -> {
                forceBothClosed(level);
                if (stateTicks >= 10) {
                    if (!consumePower(level, ENERGY_PER_DOOR_OPERATION)) {
                        notifyRequester(Component.literal("AIRLOCK: WAITING FOR POWER").withStyle(ChatFormatting.RED));
                        return;
                    }
                    AirlockLogic.prepareDoorOpening(level, worldPosition, exitDoor, 0.72D);
                    AirlockLogic.setDoorOpen(level, exitDoor, true);
                    transition(level, CycleState.WAITING_FOR_EXIT,
                            Component.literal("AIRLOCK: EXIT OPEN").withStyle(ChatFormatting.GREEN));
                }
            }
            case WAITING_FOR_EXIT -> {
                if (requester != null && exitChamberSide != null
                        && !AirlockLogic.isPlayerOnDoorSide(requester, exitDoor, exitChamberSide)) {
                    transition(level, CycleState.SEALING_EXIT,
                            Component.literal("AIRLOCK: EXIT COMPLETE - DOOR CLOSING IN 1s").withStyle(ChatFormatting.AQUA));
                } else if (stateTicks >= 200) {
                    transition(level, CycleState.SEALING_EXIT,
                            Component.literal("AIRLOCK: EXIT TIMEOUT - SAFE CLOSING").withStyle(ChatFormatting.GRAY));
                }
            }
            case SEALING_EXIT -> {
                if (!closeActionDone) {
                    if (stateTicks < 20) return;
                    if (requester != null && AirlockLogic.isPlayerInDoorway(requester, exitDoor)) {
                        if (stateTicks % 20 == 0) {
                            notifyRequester(Component.literal("AIRLOCK: DOORWAY OCCUPIED - HOLDING EXIT DOOR").withStyle(ChatFormatting.YELLOW));
                        }
                        return;
                    }
                    AirlockLogic.setDoorOpen(level, exitDoor, false);
                    closeActionDone = true;
                    stateTicks = 0;
                    setChanged();
                    return;
                }
                if (stateTicks >= 12) {
                    finish(level, Component.literal("AIRLOCK: CYCLE COMPLETE").withStyle(ChatFormatting.GREEN));
                }
            }
            case IDLE -> {}
        }
    }

    private void purgeAtmosphere(ServerLevel level, RoomScanResult scan, RoomAtmosphere atmosphere) {
        double fraction = Math.min(0.45D, 45.0D / Math.max(1.0D, scan.volume()));
        double dustBefore = atmosphere.dustPercent();
        double airborneBefore = atmosphere.airborneRadiationPerSecond();

        // Purging is a closed-loop scrub. The old implementation continuously mixed
        // filtered wasteland air into the chamber. Once a radiological cartridge had
        // even tiny wear, that created a contamination floor right around the SAFE
        // threshold and could leave the state machine in PURGING forever.
        atmosphere.filterAir(fraction, filters.dustEfficiency(), filters.radiationEfficiency());
        atmosphere.refreshBreathingAir(Math.min(0.20D, fraction * 0.35D));
        RoomAtmosphereSavedData.get(level).markChanged();

        int preWear = Math.max(1, (int) Math.ceil(1.0D + dustBefore / 15.0D));
        int hepaWear = Math.max(1, (int) Math.ceil(1.0D + dustBefore / 30.0D));
        int radWear = Math.max(1, (int) Math.ceil(1.0D + airborneBefore * 1500.0D));
        filters.consume(preWear, hepaWear, radWear);

        for (ServerPlayer player : level.players()) {
            RoomScanResult playerRoom = RoomScanner.scan(level, player.blockPosition());
            if (!playerRoom.sealed() || !playerRoom.anchor().equals(scan.anchor())) continue;
            double contamination = player.getData(ModAttachments.CONTAMINATION);
            player.setData(ModAttachments.CONTAMINATION, Mth.clamp(contamination - 1.4D, 0.0D, 100.0D));
        }
    }

    private void spawnPurgeParticles(ServerLevel level) {
        boolean foundOccupant = false;
        if (chamberAnchor != null) {
            for (ServerPlayer player : level.players()) {
                RoomScanResult playerRoom = RoomScanner.scan(level, player.blockPosition());
                if (!playerRoom.sealed() || !playerRoom.anchor().equals(chamberAnchor)) continue;
                foundOccupant = true;
                level.sendParticles(ParticleTypes.CLOUD,
                        player.getX(), player.getY() + 1.0D, player.getZ(),
                        9, 0.85D, 0.75D, 0.85D, 0.025D);
                level.sendParticles(ParticleTypes.WHITE_ASH,
                        player.getX(), player.getY() + 1.1D, player.getZ(),
                        6, 0.9D, 0.8D, 0.9D, 0.01D);
            }
        }
        if (!foundOccupant) {
            level.sendParticles(ParticleTypes.CLOUD,
                    worldPosition.getX() + 0.5D, worldPosition.getY() + 0.8D, worldPosition.getZ() + 0.5D,
                    5, 0.7D, 0.5D, 0.7D, 0.02D);
        }
    }

    private void refreshChamber(ServerLevel level) {
        RoomScanResult scan = RoomMachineUtil.findSealedAdjacentRoom(level, worldPosition);
        if (scan != null) chamberAnchor = scan.anchor();
    }

    private void forceBothClosed(ServerLevel level) {
        if (entryDoor != null) AirlockLogic.setDoorOpen(level, entryDoor, false);
        if (exitDoor != null) AirlockLogic.setDoorOpen(level, exitDoor, false);
    }

    private ServerPlayer requester() {
        if (!(level instanceof ServerLevel serverLevel) || requesterId == null) return null;
        ServerPlayer player = serverLevel.getServer().getPlayerList().getPlayer(requesterId);
        return player != null && player.serverLevel() == serverLevel ? player : null;
    }

    private void transition(ServerLevel level, CycleState next, Component message) {
        cycleState = next;
        stateTicks = 0;
        closeActionDone = false;
        setChanged();
        notifyRequester(message);
    }

    private void finish(ServerLevel level, Component message) {
        forceBothClosed(level);
        notifyRequester(message);
        cycleState = CycleState.IDLE;
        stateTicks = 0;
        entryDoor = null;
        exitDoor = null;
        chamberAnchor = null;
        entryChamberSide = null;
        exitChamberSide = null;
        requesterId = null;
        lastStatus = null;
        setChanged();
    }

    private void notifyRequester(Component component) {
        ServerPlayer player = requester();
        if (player != null) player.displayClientMessage(component, true);
    }

    public double stateSeconds() {
        return stateTicks / 20.0D;
    }

    public String cycleLabel() {
        return switch (cycleState) {
            case IDLE -> "STANDBY";
            case PREPARING_ENTRY -> "PREPARING ENTRY";
            case WAITING_FOR_ENTRY -> "ENTRY OPEN";
            case SEALING_ENTRY -> "SEALING ENTRY";
            case PURGING -> "PURGING";
            case OPENING_EXIT -> "OPENING EXIT";
            case WAITING_FOR_EXIT -> "EXIT OPEN";
            case SEALING_EXIT -> "SEALING EXIT";
        };
    }

    public Component shortCycleStatus(ServerLevel level) {
        if (cycleState == CycleState.IDLE) return shortStatus(AirlockLogic.inspectStatus(level, worldPosition));
        AirlockLogic.AirlockStatus status = AirlockLogic.inspectStatus(level, worldPosition);
        if (cycleState == CycleState.PURGING && status.hasAtmosphere()) {
            return Component.literal(String.format(Locale.ROOT,
                    "AIRLOCK: PURGING %.1fs/30.0s | Dust %.3f%% | Air Rad %.3f mSv/h | %s",
                    stateSeconds(),
                    status.atmosphere().dustPercent(),
                    status.atmosphere().airborneRadiationPerSecond() * 3600.0D,
                    filters.compactStatus())).withStyle(ChatFormatting.YELLOW);
        }
        return Component.literal("AIRLOCK: " + cycleLabel()).withStyle(ChatFormatting.AQUA);
    }

    private static void notifyNearbyPlayers(ServerLevel level, BlockPos pos, AirlockLogic.AirlockStatus status) {
        for (ServerPlayer player : level.players()) {
            if (player.blockPosition().distSqr(pos) > 100.0D) continue;
            player.displayClientMessage(shortStatus(status), true);
        }
    }

    public static Component shortStatus(AirlockLogic.AirlockStatus status) {
        return switch (status.type()) {
            case SAFE -> Component.literal(String.format(Locale.ROOT,
                    "AIRLOCK: SAFE TO OPEN | Dust %.2f%% | Air Rad %.2f mSv/h",
                    status.atmosphere().dustPercent(),
                    status.atmosphere().airborneRadiationPerSecond() * 3600.0D)).withStyle(ChatFormatting.GREEN);
            case PURGING -> Component.literal(String.format(Locale.ROOT,
                    "AIRLOCK: PURGING | Dust %.2f%% | Air Rad %.2f mSv/h",
                    status.atmosphere().dustPercent(),
                    status.atmosphere().airborneRadiationPerSecond() * 3600.0D)).withStyle(ChatFormatting.YELLOW);
            case FILTER_REQUIRED -> Component.literal("AIRLOCK: FILTER MEDIA REQUIRED").withStyle(ChatFormatting.RED);
            case UNSAFE_NO_POWER -> Component.literal(String.format(Locale.ROOT,
                    "AIRLOCK: UNSAFE - NO POWER | Dust %.2f%%",
                    status.atmosphere().dustPercent())).withStyle(ChatFormatting.RED);
            case DOOR_OPEN -> Component.literal("AIRLOCK: DOOR OPEN - INTERLOCK ACTIVE").withStyle(ChatFormatting.GOLD);
            case NOT_CONFIGURED -> Component.literal("AIRLOCK: NOT CONFIGURED - TWO DOORS REQUIRED").withStyle(ChatFormatting.RED);
            case NO_SEALED_CHAMBER -> Component.literal("AIRLOCK: CHAMBER NOT SEALED").withStyle(ChatFormatting.RED);
            case CHAMBER_TOO_LARGE -> Component.literal("AIRLOCK: CHAMBER TOO LARGE").withStyle(ChatFormatting.RED);
        };
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        energy.setEnergyStored(tag.getInt("Energy"));
        filters.load(tag, "Filter");
        try {
            cycleState = CycleState.valueOf(tag.getString("CycleState"));
        } catch (IllegalArgumentException ex) {
            cycleState = CycleState.IDLE;
        }
        stateTicks = tag.getInt("StateTicks");
        closeActionDone = tag.getBoolean("CloseActionDone");
        if (tag.contains("EntryDoor")) entryDoor = BlockPos.of(tag.getLong("EntryDoor"));
        if (tag.contains("ExitDoor")) exitDoor = BlockPos.of(tag.getLong("ExitDoor"));
        if (tag.contains("ChamberAnchor")) chamberAnchor = BlockPos.of(tag.getLong("ChamberAnchor"));
        entryChamberSide = Direction.byName(tag.getString("EntrySide"));
        exitChamberSide = Direction.byName(tag.getString("ExitSide"));
        if (tag.hasUUID("Requester")) requesterId = tag.getUUID("Requester");
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("Energy", energy.getEnergyStored());
        filters.save(tag, "Filter");
        tag.putString("CycleState", cycleState.name());
        tag.putInt("StateTicks", stateTicks);
        tag.putBoolean("CloseActionDone", closeActionDone);
        if (entryDoor != null) tag.putLong("EntryDoor", entryDoor.asLong());
        if (exitDoor != null) tag.putLong("ExitDoor", exitDoor.asLong());
        if (chamberAnchor != null) tag.putLong("ChamberAnchor", chamberAnchor.asLong());
        if (entryChamberSide != null) tag.putString("EntrySide", entryChamberSide.getName());
        if (exitChamberSide != null) tag.putString("ExitSide", exitChamberSide.getName());
        if (requesterId != null) tag.putUUID("Requester", requesterId);
    }
}
