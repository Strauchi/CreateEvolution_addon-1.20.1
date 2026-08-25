package dev.afterfall.menu;

import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.AirlockLogic;
import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;
import dev.afterfall.blockentity.VentilationFanBlockEntity;
import dev.afterfall.content.ModItems;
import dev.afterfall.content.ModMenus;
import dev.afterfall.machine.FilterBank;
import dev.afterfall.machine.MachinePower;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomMachineUtil;
import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.VentilationNetworkScanner;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.SimpleContainerData;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.neoforged.neoforge.items.IItemHandler;
import net.neoforged.neoforge.items.ItemStackHandler;
import net.neoforged.neoforge.items.SlotItemHandler;

public final class MachineMenu extends AbstractContainerMenu {
    public static final int DATA_COUNT = 18;

    public static final int TYPE_FILTER = 0;
    public static final int TYPE_INTAKE = 1;
    public static final int TYPE_AIRLOCK = 2;
    public static final int TYPE_GENERATOR = 3;
    public static final int TYPE_FAN = 4;

    public static final int BUTTON_POWER = 0;
    public static final int BUTTON_ACTION = 1;

    public static final int D_TYPE = 0;
    public static final int D_ENERGY = 1;
    public static final int D_ENERGY_MAX = 2;
    public static final int D_STATUS = 3;
    public static final int D_PRE = 4;
    public static final int D_HEPA = 5;
    public static final int D_RAD = 6;
    public static final int D_ROOM_VOLUME = 7;
    public static final int D_DUST_X100 = 8;
    public static final int D_AIR_RAD_X100 = 9;
    public static final int D_O2_X100 = 10;
    public static final int D_CO2_X100 = 11;
    public static final int D_AIR_QUALITY_X10 = 12;
    public static final int D_FLOW_X10 = 13;
    public static final int D_EXTRA = 14;
    public static final int D_POWER_SOURCE = 15;
    public static final int D_FILTER_CONDITION = 16;
    public static final int D_ENABLED = 17;

    public static final int FILTER_SLOT_Y = 95;
    public static final int[] FILTER_SLOT_X = {24, 104, 184};
    public static final int FUEL_SLOT_X = 24;
    public static final int FUEL_SLOT_Y = 95;
    public static final int PLAYER_INV_X = 41;
    public static final int PLAYER_INV_Y = 220;
    public static final int HOTBAR_Y = 280;

    private final SimpleContainerData data = new SimpleContainerData(DATA_COUNT);
    private final BlockPos blockPos;
    private final BlockEntity serverBlockEntity;
    private final int machineType;
    private final int machineSlotCount;

    public MachineMenu(int containerId, Inventory inventory, RegistryFriendlyByteBuf buf) {
        this(containerId, inventory, buf.readBlockPos(), null, buf.readVarInt());
    }

    public MachineMenu(int containerId, Inventory inventory, BlockPos pos, BlockEntity blockEntity) {
        this(containerId, inventory, pos, blockEntity, typeOf(blockEntity));
    }

    private MachineMenu(int containerId, Inventory inventory, BlockPos pos, BlockEntity blockEntity, int machineType) {
        super(ModMenus.MACHINE.get(), containerId);
        this.blockPos = pos.immutable();
        this.serverBlockEntity = blockEntity;
        this.machineType = machineType;
        this.machineSlotCount = machineType == TYPE_GENERATOR ? 1 : (machineType == TYPE_FAN ? 0 : 3);

        IItemHandler machineHandler = handlerFor(blockEntity, machineType);
        if (machineType == TYPE_GENERATOR) {
            addSlot(new SlotItemHandler(machineHandler, 0, FUEL_SLOT_X, FUEL_SLOT_Y));
        } else if (machineType != TYPE_FAN) {
            for (int i = 0; i < 3; i++) addSlot(new SlotItemHandler(machineHandler, i, FILTER_SLOT_X[i], FILTER_SLOT_Y));
        }

        // Player inventory 3x9 + hotbar.
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                addSlot(new Slot(inventory, col + row * 9 + 9,
                        PLAYER_INV_X + col * 18, PLAYER_INV_Y + row * 18));
            }
        }
        for (int col = 0; col < 9; col++) {
            addSlot(new Slot(inventory, col, PLAYER_INV_X + col * 18, HOTBAR_Y));
        }

        addDataSlots(data);
        if (serverBlockEntity != null) updateServerData();
    }

    public static int typeOf(BlockEntity blockEntity) {
        if (blockEntity instanceof AirIntakeBlockEntity) return TYPE_INTAKE;
        if (blockEntity instanceof AirlockControllerBlockEntity) return TYPE_AIRLOCK;
        if (blockEntity instanceof EmergencyGeneratorBlockEntity) return TYPE_GENERATOR;
        if (blockEntity instanceof VentilationFanBlockEntity) return TYPE_FAN;
        return TYPE_FILTER;
    }

    private static IItemHandler handlerFor(BlockEntity blockEntity, int type) {
        if (blockEntity instanceof AirFilterBlockEntity be) return be.filters();
        if (blockEntity instanceof AirIntakeBlockEntity be) return be.filters();
        if (blockEntity instanceof AirlockControllerBlockEntity be) return be.filters();
        if (blockEntity instanceof EmergencyGeneratorBlockEntity be) return be.inventory();
        if (blockEntity instanceof VentilationFanBlockEntity) return new ItemStackHandler(0);
        if (type == TYPE_GENERATOR) {
            return new ItemStackHandler(1) {
                @Override public boolean isItemValid(int slot, ItemStack stack) {
                    return slot == 0 && EmergencyGeneratorBlockEntity.isFuel(stack);
                }
            };
        }
        return new FilterBank(null);
    }

    @Override
    public void broadcastChanges() {
        if (serverBlockEntity != null) updateServerData();
        super.broadcastChanges();
    }

    private void updateServerData() {
        if (!(serverBlockEntity.getLevel() instanceof ServerLevel level)) return;
        for (int i = 0; i < DATA_COUNT; i++) data.set(i, 0);

        if (serverBlockEntity instanceof AirFilterBlockEntity be) {
            data.set(D_TYPE, TYPE_FILTER);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_FLOW_X10, scale(AirFilterBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomScanResult scan = RoomMachineUtil.findSealedAdjacentRoom(level, blockPos);
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirFilterBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!be.filters().complete()) data.set(D_STATUS, 3);
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirFilterBlockEntity.isClean(atmosphere) ? 5 : 4);
                setAtmosphere(scan, atmosphere);
            }
            if (scan != null && get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof AirIntakeBlockEntity be) {
            data.set(D_TYPE, TYPE_INTAKE);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_FLOW_X10, scale(AirIntakeBlockEntity.FLOW_M3_PER_SECOND, 10.0D));
            RoomMachineUtil.IntakeConnection connection = RoomMachineUtil.findIntakeConnection(level, blockPos);
            RoomScanResult scan = connection.room();
            if (!be.enabled()) data.set(D_STATUS, 17);
            else if (!MachinePower.available(level, blockPos, be.energyStorage(), AirIntakeBlockEntity.ENERGY_PER_SECOND)) data.set(D_STATUS, 1);
            else if (scan == null) data.set(D_STATUS, 2);
            else if (!be.filters().complete()) data.set(D_STATUS, 3);
            else if (!connection.outsideConnected()) data.set(D_STATUS, 6);
            else {
                RoomAtmosphere atmosphere = atmosphere(level, scan);
                data.set(D_STATUS, AirIntakeBlockEntity.needsFreshAir(atmosphere) ? 7 : 5);
                setAtmosphere(scan, atmosphere);
            }
            if (scan != null && get(D_ROOM_VOLUME) == 0) setAtmosphere(scan, atmosphere(level, scan));
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {
            data.set(D_TYPE, TYPE_AIRLOCK);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            setFilters(be.filters().prefilterFraction(), be.filters().hepaFraction(), be.filters().radiologicalFraction(), be.filters().conditionLabel());
            data.set(D_EXTRA, be.cycleState().ordinal());
            AirlockLogic.AirlockStatus status = AirlockLogic.inspectStatus(level, blockPos);
            data.set(D_STATUS, !be.enabled() ? 17 : airlockStatusCode(be, status));
            if (status.hasAtmosphere()) setAtmosphere(status.scan(), status.atmosphere());
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }


        if (serverBlockEntity instanceof VentilationFanBlockEntity be) {
            data.set(D_TYPE, TYPE_FAN);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            VentilationNetworkScanner.Network network = be.inspectNetwork(level);
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
            else data.set(D_STATUS, 32);
            data.set(D_POWER_SOURCE, powerSource(level, blockPos, be.energyStorage()));
            return;
        }

        if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) {
            data.set(D_TYPE, TYPE_GENERATOR);
            data.set(D_ENABLED, be.enabled() ? 1 : 0);
            setEnergy(be.energyStorage().getEnergyStored(), be.energyStorage().getMaxEnergyStored());
            data.set(D_STATUS, !be.enabled() ? 17 : (be.burnTicks() > 0 ? 8 : (be.energyStorage().getEnergyStored() > 0 ? 9 : 10)));
            data.set(D_FLOW_X10, EmergencyGeneratorBlockEntity.GENERATION_PER_TICK * 10);
            data.set(D_EXTRA, be.burnTicks());
            data.set(D_POWER_SOURCE, 3);
        }
    }

    private int airlockStatusCode(AirlockControllerBlockEntity be, AirlockLogic.AirlockStatus status) {
        if (be.isBusy()) return 20 + be.cycleState().ordinal();
        return switch (status.type()) {
            case NOT_CONFIGURED -> 11;
            case DOOR_OPEN -> 12;
            case NO_SEALED_CHAMBER -> 13;
            case CHAMBER_TOO_LARGE -> 14;
            case UNSAFE_NO_POWER -> 1;
            case FILTER_REQUIRED -> 3;
            case SAFE -> 16;
            default -> 15;
        };
    }

    @Override
    public boolean clickMenuButton(Player player, int id) {
        if (!(player instanceof ServerPlayer serverPlayer) || serverBlockEntity == null
                || !(serverBlockEntity.getLevel() instanceof ServerLevel level)) return false;

        if (id == BUTTON_POWER) {
            if (serverBlockEntity instanceof AirFilterBlockEntity be) be.setEnabled(!be.enabled());
            else if (serverBlockEntity instanceof AirIntakeBlockEntity be) be.setEnabled(!be.enabled());
            else if (serverBlockEntity instanceof EmergencyGeneratorBlockEntity be) be.setEnabled(!be.enabled());
            else if (serverBlockEntity instanceof VentilationFanBlockEntity be) be.setEnabled(!be.enabled());
            else if (serverBlockEntity instanceof AirlockControllerBlockEntity be) {
                if (!be.setEnabled(!be.enabled())) {
                    serverPlayer.displayClientMessage(Component.literal("AIRLOCK: CANNOT POWER OFF DURING ACTIVE CYCLE"), true);
                    return false;
                }
            } else return false;
            updateServerData();
            return true;
        }

        if (id == BUTTON_ACTION && serverBlockEntity instanceof AirlockControllerBlockEntity be) {
            if (!be.enabled()) {
                serverPlayer.displayClientMessage(Component.literal("AIRLOCK: CONTROLLER IS SWITCHED OFF"), true);
                return false;
            }
            return be.requestFromController(level, serverPlayer);
        }
        return false;
    }

    private void setEnergy(int stored, int max) {
        data.set(D_ENERGY, stored / 10);
        data.set(D_ENERGY_MAX, Math.max(1, max / 10));
    }

    private void setFilters(double pre, double hepa, double rad, String condition) {
        data.set(D_PRE, scale(pre * 100.0D, 10.0D));
        data.set(D_HEPA, scale(hepa * 100.0D, 10.0D));
        data.set(D_RAD, scale(rad * 100.0D, 10.0D));
        data.set(D_FILTER_CONDITION, switch (condition) {
            case "EXHAUSTED" -> 3;
            case "CRITICAL" -> 2;
            case "DEGRADED" -> 1;
            default -> 0;
        });
    }

    private void setAtmosphere(RoomScanResult scan, RoomAtmosphere atmosphere) {
        data.set(D_ROOM_VOLUME, scan.volume());
        data.set(D_DUST_X100, scale(atmosphere.dustPercent(), 100.0D));
        data.set(D_AIR_RAD_X100, scale(atmosphere.airborneRadiationPerSecond() * 3600.0D, 100.0D));
        data.set(D_O2_X100, scale(atmosphere.oxygenPercent(), 100.0D));
        data.set(D_CO2_X100, scale(atmosphere.co2Percent(), 100.0D));
        data.set(D_AIR_QUALITY_X10, scale(atmosphere.airQualityPercent(), 10.0D));
    }

    private static RoomAtmosphere atmosphere(ServerLevel level, RoomScanResult scan) {
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        return RoomAtmosphereSavedData.get(level).getOrCreate(scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland), RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
    }

    private static int powerSource(ServerLevel level, BlockPos pos, dev.afterfall.machine.MachineEnergyStorage storage) {
        String source = MachinePower.source(level, pos, storage);
        if ("FE".equals(source)) return 1;
        if (source.startsWith("REDSTONE")) return 2;
        return 0;
    }

    private static int scale(double value, double multiplier) {
        return (int) Math.round(Math.max(0.0D, Math.min(2_000_000.0D, value * multiplier)));
    }

    public BlockPos blockPos() { return blockPos; }
    public int machineType() { return machineType; }
    public int machineSlotCount() { return machineSlotCount; }
    public int get(int index) { return data.get(index); }
    public boolean enabled() { return get(D_ENABLED) != 0; }
    public double prePercent() { return get(D_PRE) / 10.0D; }
    public double hepaPercent() { return get(D_HEPA) / 10.0D; }
    public double radPercent() { return get(D_RAD) / 10.0D; }
    public double dustPercent() { return get(D_DUST_X100) / 100.0D; }
    public double airRadiation() { return get(D_AIR_RAD_X100) / 100.0D; }
    public double oxygenPercent() { return get(D_O2_X100) / 100.0D; }
    public double co2Percent() { return get(D_CO2_X100) / 100.0D; }
    public double airQuality() { return get(D_AIR_QUALITY_X10) / 10.0D; }
    public double flow() { return get(D_FLOW_X10) / 10.0D; }

    @Override
    public boolean stillValid(Player player) {
        return player.distanceToSqr(blockPos.getX() + 0.5D, blockPos.getY() + 0.5D, blockPos.getZ() + 0.5D) <= 64.0D;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        Slot slot = getSlot(index);
        if (!slot.hasItem()) return ItemStack.EMPTY;
        ItemStack stack = slot.getItem();
        ItemStack original = stack.copy();
        int playerStart = machineSlotCount;
        int playerEnd = playerStart + 36;

        if (index < machineSlotCount) {
            if (!moveItemStackTo(stack, playerStart, playerEnd, true)) return ItemStack.EMPTY;
        } else {
            boolean movedToMachine = false;
            if (machineType == TYPE_GENERATOR && EmergencyGeneratorBlockEntity.isFuel(stack)) {
                movedToMachine = moveItemStackTo(stack, 0, 1, false);
            } else if (machineType != TYPE_GENERATOR && machineType != TYPE_FAN) {
                int target = FilterBank.slotFor(stack);
                if (target >= 0) movedToMachine = moveItemStackTo(stack, target, target + 1, false);
            }
            if (!movedToMachine) {
                int mainEnd = playerStart + 27;
                if (index < mainEnd) {
                    if (!moveItemStackTo(stack, mainEnd, playerEnd, false)) return ItemStack.EMPTY;
                } else {
                    if (!moveItemStackTo(stack, playerStart, mainEnd, false)) return ItemStack.EMPTY;
                }
            }
        }

        if (stack.isEmpty()) slot.set(ItemStack.EMPTY); else slot.setChanged();
        if (stack.getCount() == original.getCount()) return ItemStack.EMPTY;
        slot.onTake(player, stack);
        return original;
    }
}
