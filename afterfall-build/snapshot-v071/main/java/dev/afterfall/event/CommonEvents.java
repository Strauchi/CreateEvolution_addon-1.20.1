package dev.afterfall.event;

import dev.afterfall.blockentity.AirFilterBlockEntity;
import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.blockentity.AirlockControllerBlockEntity;
import dev.afterfall.blockentity.AirlockLogic;
import dev.afterfall.blockentity.EmergencyGeneratorBlockEntity;
import dev.afterfall.blockentity.VentilationFanBlockEntity;
import dev.afterfall.block.AirVentBlock;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.content.ModItems;
import dev.afterfall.menu.MachineMenu;
import dev.afterfall.radiation.RadiationManager;
import dev.afterfall.radiation.RadiationReading;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.VentilationNetworkScanner;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.SimpleMenuProvider;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;
import net.neoforged.neoforge.event.tick.PlayerTickEvent;

import java.util.Locale;

public final class CommonEvents {
    public static void onPlayerTick(PlayerTickEvent.Post event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;
        if (player.tickCount % 20 != 0) return;

        RadiationManager.tickSecond(player);
        boolean holdingCounter = player.getMainHandItem().is(ModItems.GEIGER_COUNTER.get())
                || player.getOffhandItem().is(ModItems.GEIGER_COUNTER.get());
        if (holdingCounter) {
            RadiationReading reading = RadiationManager.sample(player);
            String environment = reading.room().sealed()
                    ? String.format(Locale.ROOT, "SEALED %dm³ | Air %.0f%% | O2 %.1f%% | Shield %.0f%%",
                    reading.room().volume(), reading.room().airQualityPercent(),
                    reading.room().oxygenPercent(), reading.shieldingPercent())
                    : "OPEN AIR | Shield 0%";
            player.displayClientMessage(Component.literal(String.format(Locale.ROOT,
                    "☢ %.1f mSv/h | %s", reading.totalRatePerHour(), environment)), true);
        }
    }

    public static void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {
        BlockState state = event.getLevel().getBlockState(event.getPos());


        if (state.is(ModBlocks.AIR_VENT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                if (player.isShiftKeyDown()) {
                    boolean newReturn = !state.getValue(AirVentBlock.RETURN_MODE);
                    serverLevel.setBlock(event.getPos(), state.setValue(AirVentBlock.RETURN_MODE, newReturn), 3);
                    player.displayClientMessage(Component.literal("AIR VENT: MODE = " + (newReturn ? "RETURN" : "SUPPLY"))
                            .withStyle(newReturn ? ChatFormatting.AQUA : ChatFormatting.GREEN), true);
                } else {
                    var facing = state.getValue(AirVentBlock.FACING);
                    BlockPos shaftStart = event.getPos().relative(facing.getOpposite());
                    var network = VentilationNetworkScanner.scan(serverLevel, shaftStart);
                    RoomScanResult room = VentilationNetworkScanner.roomForVent(serverLevel, event.getPos());
                    String shaft = network != null && network.valid() ? network.shaft().volume() + "m³ SEALED" : "NOT SEALED";
                    String roomText = room != null ? room.volume() + "m³ SEALED" : "NO SEALED ROOM";
                    player.displayClientMessage(Component.literal("AIR VENT: "
                            + (state.getValue(AirVentBlock.RETURN_MODE) ? "RETURN" : "SUPPLY")
                            + " | Facing " + facing.getName().toUpperCase(Locale.ROOT)
                            + " | Shaft " + shaft + " | Room " + roomText).withStyle(ChatFormatting.AQUA), true);
                }
            }
            return;
        }

        if (state.is(ModBlocks.VENTILATION_FAN.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof VentilationFanBlockEntity fan) {
                    openMachineMenu(player, event.getPos(), fan, Component.literal("Ventilation Fan"));
                }
            }
            return;
        }

        if (state.is(ModBlocks.AIRLOCK_CALL_PANEL.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                AirlockLogic.ControllerLink link = AirlockLogic.findControllerForPanel(serverLevel, event.getPos());
                if (link == null) {
                    player.displayClientMessage(Component.literal("AIRLOCK PANEL: NO CONTROLLER FOUND").withStyle(ChatFormatting.RED), true);
                    return;
                }
                BlockEntity blockEntity = serverLevel.getBlockEntity(link.controller());
                if (blockEntity instanceof AirlockControllerBlockEntity controller) {
                    controller.requestCycle(serverLevel, link.door(), player);
                } else {
                    player.displayClientMessage(Component.literal("AIRLOCK PANEL: CONTROLLER OFFLINE").withStyle(ChatFormatting.RED), true);
                }
            }
            return;
        }

        if (state.is(ModBlocks.AIR_FILTER_UNIT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof AirFilterBlockEntity filter && isFilterCartridge(player.getMainHandItem())) {
                    if (filter.installFilter(player, player.getMainHandItem())) {
                        player.displayClientMessage(Component.literal("Air Filter: cartridge installed | " + filter.filters().compactStatus())
                                .withStyle(ChatFormatting.GREEN), true);
                    }
                } else if (blockEntity instanceof AirFilterBlockEntity filter) {
                    openMachineMenu(player, event.getPos(), filter, Component.literal("Air Filtration Unit"));
                }
            }
            return;
        }

        if (state.is(ModBlocks.AIR_INTAKE_UNIT.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof AirIntakeBlockEntity intake && isFilterCartridge(player.getMainHandItem())) {
                    if (intake.installFilter(player, player.getMainHandItem())) {
                        player.displayClientMessage(Component.literal("Air Intake: cartridge installed | " + intake.filters().compactStatus())
                                .withStyle(ChatFormatting.GREEN), true);
                    }
                } else if (blockEntity instanceof AirIntakeBlockEntity intake) {
                    openMachineMenu(player, event.getPos(), intake, Component.literal("Air Intake Unit"));
                }
            }
            return;
        }

        if (state.is(ModBlocks.AIRLOCK_CONTROLLER.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);

            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof AirlockControllerBlockEntity controller) {
                    if (isFilterCartridge(player.getMainHandItem())) {
                        if (controller.installFilter(player, player.getMainHandItem())) {
                            player.displayClientMessage(Component.literal("Airlock: cartridge installed | " + controller.filters().compactStatus())
                                    .withStyle(ChatFormatting.GREEN), true);
                        }
                    } else if (!player.isShiftKeyDown()) {
                        controller.requestFromController(serverLevel, player);
                        player.displayClientMessage(controller.shortCycleStatus(serverLevel), true);
                    } else {
                        openMachineMenu(player, event.getPos(), controller, Component.literal("Airlock Controller"));
                    }
                }
            }
            return;
        }


        if (state.is(ModBlocks.EMERGENCY_GENERATOR.get()) && event.getHand() == InteractionHand.MAIN_HAND) {
            event.setCancellationResult(InteractionResult.SUCCESS);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player && event.getLevel() instanceof ServerLevel serverLevel) {
                BlockEntity blockEntity = serverLevel.getBlockEntity(event.getPos());
                if (blockEntity instanceof EmergencyGeneratorBlockEntity generator) {
                    openMachineMenu(player, event.getPos(), generator, Component.literal("Emergency Generator"));
                }
            }
            return;
        }

        if (!(state.getBlock() instanceof DoorBlock)) return;
        var controllerPos = AirlockLogic.findControllerForDoor(event.getLevel(), event.getPos());
        if (controllerPos != null && event.getLevel() instanceof ServerLevel serverLevel) {
            BlockEntity blockEntity = serverLevel.getBlockEntity(controllerPos);
            if (blockEntity instanceof AirlockControllerBlockEntity controller && controller.isBusy()) {
                event.setCancellationResult(InteractionResult.FAIL);
                event.setCanceled(true);
                if (event.getEntity() instanceof ServerPlayer player) {
                    player.displayClientMessage(Component.literal("Airlock automatic cycle active: manual door control locked."), true);
                }
                return;
            }
        }

        if (!state.hasProperty(BlockStateProperties.OPEN) || state.getValue(BlockStateProperties.OPEN)) return;

        if (controllerPos != null && AirlockLogic.otherLinkedDoorOpen(event.getLevel(), controllerPos, event.getPos())) {
            event.setCancellationResult(InteractionResult.FAIL);
            event.setCanceled(true);
            if (event.getEntity() instanceof ServerPlayer player) {
                player.displayClientMessage(Component.literal("Airlock interlock: close the other door first."), true);
            }
            return;
        }

        if (event.getLevel() instanceof ServerLevel serverLevel) {
            RoomEnvironmentManager.equilibrateAcrossClosedDoor(serverLevel, event.getPos());
            if (event.getEntity() instanceof ServerPlayer player) {
                RoomEnvironmentManager.invalidate(player);
                if (controllerPos != null) {
                    AirlockLogic.AirlockStatus status = AirlockLogic.inspectStatus(serverLevel, controllerPos);
                    player.displayClientMessage(AirlockControllerBlockEntity.shortStatus(status), true);
                }
            }
        }
    }

    private static void openMachineMenu(ServerPlayer player, net.minecraft.core.BlockPos pos, BlockEntity blockEntity,
                                        Component title) {
        player.openMenu(new SimpleMenuProvider(
                (containerId, inventory, menuPlayer) -> new MachineMenu(containerId, inventory, pos, blockEntity),
                title), buffer -> { buffer.writeBlockPos(pos); buffer.writeVarInt(MachineMenu.typeOf(blockEntity)); });
    }

    private static void sendControllerDiagnostics(ServerPlayer player, ServerLevel level, net.minecraft.core.BlockPos pos,
                                                  AirlockControllerBlockEntity controller) {
        AirlockLogic.AirlockStatus status = AirlockLogic.inspectStatus(level, pos);
        player.sendSystemMessage(Component.literal("--- Afterfall Airlock Controller ---").withStyle(ChatFormatting.DARK_AQUA));
        player.sendSystemMessage(Component.literal("Automatic cycle: " + controller.cycleLabel())
                .withStyle(controller.isBusy() ? ChatFormatting.YELLOW : ChatFormatting.GREEN));
        player.sendSystemMessage(controller.isBusy()
                ? controller.shortCycleStatus(level)
                : AirlockControllerBlockEntity.shortStatus(status));
        if (status.hasAtmosphere()) {
            player.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                    "Air quality: %.1f%% | Dust: %.2f%% | Airborne radiation: %.2f mSv/h",
                    status.atmosphere().airQualityPercent(),
                    status.atmosphere().dustPercent(),
                    status.atmosphere().airborneRadiationPerSecond() * 3600.0D)));
            player.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                    "Oxygen: %.2f%% | CO2: %.2f%% | Volume: %d m³",
                    status.atmosphere().oxygenPercent(),
                    status.atmosphere().co2Percent(),
                    status.scan().volume())));
        }
        player.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                "Power: %d/%d FE | Source: %s", controller.energyStorage().getEnergyStored(),
                controller.energyStorage().getMaxEnergyStored(),
                dev.afterfall.machine.MachinePower.source(level, pos, controller.energyStorage())))
                .withStyle(status.powered() ? ChatFormatting.GREEN : ChatFormatting.RED));
        player.sendSystemMessage(Component.literal("Filters: " + controller.filters().compactStatus()
                        + " | Condition: " + controller.filters().conditionLabel())
                .withStyle(controller.filters().complete() ? ChatFormatting.GREEN : ChatFormatting.RED));
        if (controller.cycleState() == AirlockControllerBlockEntity.CycleState.PURGING) {
            player.sendSystemMessage(Component.literal(String.format(Locale.ROOT,
                    "Purge timer: %.1f / %.1f s", controller.stateTicks() / 20.0D,
                    AirlockControllerBlockEntity.MAX_PURGE_TICKS / 20.0D)).withStyle(ChatFormatting.GRAY));
        }
        player.sendSystemMessage(Component.literal("Tip: right-click = automatic cycle, sneak + right-click = diagnostics")
                .withStyle(ChatFormatting.GRAY));
    }

    private static boolean isFilterCartridge(ItemStack stack) {
        return stack.is(ModItems.PREFILTER_CARTRIDGE.get())
                || stack.is(ModItems.HEPA_FILTER_CARTRIDGE.get())
                || stack.is(ModItems.RAD_FILTER_CARTRIDGE.get());
    }

    private CommonEvents() {}
}
