package dev.afterfall.command;

import com.mojang.brigadier.arguments.DoubleArgumentType;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.tree.LiteralCommandNode;
import dev.afterfall.blockentity.AirIntakeBlockEntity;
import dev.afterfall.blockentity.VentilationFanBlockEntity;
import dev.afterfall.content.ModAttachments;
import dev.afterfall.radiation.RadiationManager;
import dev.afterfall.radiation.RadiationReading;
import dev.afterfall.room.AirTreatmentNetwork;
import dev.afterfall.room.BiologicalAirManager;
import dev.afterfall.room.RoomAtmosphere;
import dev.afterfall.room.VentilationNetworkScanner;
import dev.afterfall.room.RoomAtmosphereSavedData;
import dev.afterfall.room.RoomEnvironmentManager;
import dev.afterfall.room.RoomScanResult;
import dev.afterfall.room.RoomScanner;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.arguments.EntityArgument;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Mth;
import net.neoforged.neoforge.event.RegisterCommandsEvent;

import java.util.Collection;
import java.util.List;
import java.util.Locale;

/** Operator-only test/debug commands for current and future Afterfall systems. */
public final class AfterfallCommands {
    private static final int ADMIN_PERMISSION_LEVEL = 2;

    public static void register(RegisterCommandsEvent event) {
        var dispatcher = event.getDispatcher();
        LiteralCommandNode<CommandSourceStack> root = dispatcher.register(
                Commands.literal("afterfall")
                        .requires(source -> source.hasPermission(ADMIN_PERMISSION_LEVEL))
                        .executes(ctx -> help(ctx.getSource()))
                        .then(Commands.literal("help").executes(ctx -> help(ctx.getSource())))
                        .then(roomCommands())
                        .then(lifeCommands())
                        .then(playerCommands())
                        .then(radiationCommands())
        );
        dispatcher.register(Commands.literal("af")
                .requires(source -> source.hasPermission(ADMIN_PERMISSION_LEVEL))
                .redirect(root));
    }

    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<CommandSourceStack> roomCommands() {
        return Commands.literal("room")
                .then(Commands.literal("info").executes(ctx -> roomInfo(ctx.getSource())))
                .then(Commands.literal("clean").executes(ctx -> roomPreset(ctx.getSource(), false)))
                .then(Commands.literal("wasteland").executes(ctx -> roomPreset(ctx.getSource(), true)))
                .then(Commands.literal("simulate")
                        .then(Commands.argument("players", IntegerArgumentType.integer(1, 64))
                                .then(Commands.argument("seconds", IntegerArgumentType.integer(1, 86400))
                                        .executes(ctx -> roomSimulate(ctx.getSource(),
                                                IntegerArgumentType.getInteger(ctx, "players"),
                                                IntegerArgumentType.getInteger(ctx, "seconds"))))))
                .then(Commands.literal("set")
                        .then(roomScalar("dust", 0.0D, 100.0D, Scalar.DUST, false))
                        .then(roomScalar("rad", 0.0D, 10000.0D, Scalar.RADIATION, false))
                        .then(roomScalar("o2", 0.0D, RoomAtmosphere.NORMAL_OXYGEN, Scalar.OXYGEN, false))
                        .then(roomScalar("co2", RoomAtmosphere.NORMAL_CO2, 20.0D, Scalar.CO2, false))
                        .then(Commands.literal("all")
                                .then(Commands.argument("dust", DoubleArgumentType.doubleArg(0.0D, 100.0D))
                                        .then(Commands.argument("rad", DoubleArgumentType.doubleArg(0.0D, 10000.0D))
                                                .then(Commands.argument("o2", DoubleArgumentType.doubleArg(0.0D, RoomAtmosphere.NORMAL_OXYGEN))
                                                        .then(Commands.argument("co2", DoubleArgumentType.doubleArg(RoomAtmosphere.NORMAL_CO2, 20.0D))
                                                                .executes(ctx -> roomSetAll(ctx.getSource(),
                                                                        DoubleArgumentType.getDouble(ctx, "dust"),
                                                                        DoubleArgumentType.getDouble(ctx, "rad"),
                                                                        DoubleArgumentType.getDouble(ctx, "o2"),
                                                                        DoubleArgumentType.getDouble(ctx, "co2")))))))))
                .then(Commands.literal("add")
                        .then(roomScalar("dust", -100.0D, 100.0D, Scalar.DUST, true))
                        .then(roomScalar("rad", -10000.0D, 10000.0D, Scalar.RADIATION, true))
                        .then(roomScalar("o2", -20.9D, 20.9D, Scalar.OXYGEN, true))
                        .then(roomScalar("co2", -20.0D, 20.0D, Scalar.CO2, true)));
    }

    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<CommandSourceStack> lifeCommands() {
        return Commands.literal("life")
                .executes(ctx -> lifeInfo(ctx.getSource()))
                .then(Commands.literal("info").executes(ctx -> lifeInfo(ctx.getSource())));
    }

    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<CommandSourceStack> roomScalar(
            String name, double min, double max, Scalar scalar, boolean add) {
        return Commands.literal(name)
                .then(Commands.argument("value", DoubleArgumentType.doubleArg(min, max))
                        .executes(ctx -> roomScalar(ctx.getSource(), scalar,
                                DoubleArgumentType.getDouble(ctx, "value"), add)));
    }

    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<CommandSourceStack> playerCommands() {
        return Commands.literal("player")
                .then(Commands.literal("info")
                        .executes(ctx -> playerInfo(ctx.getSource(), List.of(ctx.getSource().getPlayerOrException())))
                        .then(Commands.argument("targets", EntityArgument.players())
                                .executes(ctx -> playerInfo(ctx.getSource(), EntityArgument.getPlayers(ctx, "targets")))))
                .then(Commands.literal("reset")
                        .executes(ctx -> playerReset(ctx.getSource(), List.of(ctx.getSource().getPlayerOrException())))
                        .then(Commands.argument("targets", EntityArgument.players())
                                .executes(ctx -> playerReset(ctx.getSource(), EntityArgument.getPlayers(ctx, "targets")))))
                .then(playerValueCommands("dose", PlayerValue.DOSE, 0.0D, 5000.0D, 5000.0D))
                .then(playerValueCommands("contamination", PlayerValue.CONTAMINATION, 0.0D, 100.0D, 100.0D));
    }

    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<CommandSourceStack> playerValueCommands(
            String name, PlayerValue type, double setMin, double setMax, double addRange) {
        return Commands.literal(name)
                .then(Commands.literal("set")
                        .then(Commands.argument("value", DoubleArgumentType.doubleArg(setMin, setMax))
                                .executes(ctx -> playerValue(ctx.getSource(), type, false,
                                        DoubleArgumentType.getDouble(ctx, "value"),
                                        List.of(ctx.getSource().getPlayerOrException())))
                                .then(Commands.argument("targets", EntityArgument.players())
                                        .executes(ctx -> playerValue(ctx.getSource(), type, false,
                                                DoubleArgumentType.getDouble(ctx, "value"),
                                                EntityArgument.getPlayers(ctx, "targets"))))))
                .then(Commands.literal("add")
                        .then(Commands.argument("value", DoubleArgumentType.doubleArg(-addRange, addRange))
                                .executes(ctx -> playerValue(ctx.getSource(), type, true,
                                        DoubleArgumentType.getDouble(ctx, "value"),
                                        List.of(ctx.getSource().getPlayerOrException())))
                                .then(Commands.argument("targets", EntityArgument.players())
                                        .executes(ctx -> playerValue(ctx.getSource(), type, true,
                                                DoubleArgumentType.getDouble(ctx, "value"),
                                                EntityArgument.getPlayers(ctx, "targets"))))))
                .then(Commands.literal("clear")
                        .executes(ctx -> playerValue(ctx.getSource(), type, false, 0.0D,
                                List.of(ctx.getSource().getPlayerOrException())))
                        .then(Commands.argument("targets", EntityArgument.players())
                                .executes(ctx -> playerValue(ctx.getSource(), type, false, 0.0D,
                                        EntityArgument.getPlayers(ctx, "targets")))));
    }

    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<CommandSourceStack> radiationCommands() {
        return Commands.literal("radiation")
                .then(Commands.literal("sample")
                        .executes(ctx -> radiationSample(ctx.getSource(), List.of(ctx.getSource().getPlayerOrException())))
                        .then(Commands.argument("targets", EntityArgument.players())
                                .executes(ctx -> radiationSample(ctx.getSource(), EntityArgument.getPlayers(ctx, "targets")))));
    }

    private static int help(CommandSourceStack source) {
        source.sendSuccess(() -> Component.literal("Afterfall admin tools (permission level 2+):"), false);
        source.sendSuccess(() -> Component.literal("/af room info | clean | wasteland | simulate <players> <seconds>"), false);
        source.sendSuccess(() -> Component.literal("/af life [info] - detailed life-support / ventilation diagnostics"), false);
        source.sendSuccess(() -> Component.literal("/af room set <dust|rad|o2|co2> <value> | set all <dust> <rad mSv/h> <o2> <co2>"), false);
        source.sendSuccess(() -> Component.literal("/af room add <dust|rad|o2|co2> <delta>"), false);
        source.sendSuccess(() -> Component.literal("/af player info|reset [targets] | dose/contamination <set|add|clear> ..."), false);
        source.sendSuccess(() -> Component.literal("/af radiation sample [targets]"), false);
        return 1;
    }

    private static RoomContext currentRoom(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        ServerPlayer player = source.getPlayerOrException();
        ServerLevel level = source.getLevel();
        RoomScanResult scan = RoomScanner.scan(level, player.blockPosition());
        if (!scan.sealed()) {
            source.sendFailure(Component.literal("AFTERFALL: current position is not inside a sealed room."));
            return null;
        }
        boolean wasteland = RoomEnvironmentManager.isWasteland(level, scan.anchor());
        RoomAtmosphere atmosphere = RoomAtmosphereSavedData.get(level).getOrCreate(
                scan.anchor().asLong(), scan.volume(),
                RoomEnvironmentManager.outsideDust(wasteland),
                RoomEnvironmentManager.outsideAirborneRadiation(wasteland), level.getGameTime());
        return new RoomContext(level, scan, atmosphere);
    }

    private static int roomInfo(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;

        double radHour = room.air.airborneRadiationPerSecond() * 3600.0D;
        double airQuality = room.air.airQualityPercent();

        var header = Component.literal("[ROOM] ")
                .withStyle(ChatFormatting.AQUA).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(room.scan.volume() + " m³").withStyle(ChatFormatting.WHITE))
                .append(Component.literal("  |  Air quality ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.1f%%", airQuality))
                        .withStyle(qualityColor(airQuality)));
        source.sendSuccess(() -> header, false);

        var gases = Component.literal("Atmosphere  ").withStyle(ChatFormatting.BLUE)
                .append(Component.literal("O2 ").withStyle(ChatFormatting.GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.2f%%", room.air.oxygenPercent()))
                        .withStyle(oxygenColor(room.air.oxygenPercent())))
                .append(Component.literal("  |  CO2 ").withStyle(ChatFormatting.GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.3f%%", room.air.co2Percent()))
                        .withStyle(co2Color(room.air.co2Percent())));
        source.sendSuccess(() -> gases, false);

        var contamination = Component.literal("Contamination  ").withStyle(ChatFormatting.GOLD)
                .append(Component.literal("Dust ").withStyle(ChatFormatting.GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.2f%%", room.air.dustPercent()))
                        .withStyle(dustColor(room.air.dustPercent())))
                .append(Component.literal("  |  Air Rad ").withStyle(ChatFormatting.GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.2f mSv/h", radHour))
                        .withStyle(radiationColor(radHour)));
        source.sendSuccess(() -> contamination, false);

        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()
                + "  |  Detailed systems: /af life").withStyle(ChatFormatting.DARK_GRAY), false);
        return 1;
    }

    private static int lifeInfo(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;

        double demand = AirIntakeBlockEntity.freshAirDemandM3PerSecond(room.air);
        BiologicalAirManager.Snapshot bio = BiologicalAirManager.inspect(room.level, room.scan);
        BiologicalAirManager.RateSample bioRate = BiologicalAirManager.inspectRate(room.level, room.scan);
        AirTreatmentNetwork.TransferDiagnostics transfer =
                AirTreatmentNetwork.inspectTransfers(room.level, room.scan);
        AirTreatmentNetwork.ScrubberDiagnostics scrubber =
                AirTreatmentNetwork.inspectScrubbers(room.level, room.scan);
        VentilationNetworkScanner.RoomVentDiagnostics roomVents =
                VentilationNetworkScanner.inspectRoomVents(room.level, room.scan);
        VentilationFanBlockEntity.RoomFlowSample flow =
                VentilationFanBlockEntity.inspectRoomFlow(room.level, room.scan);

        int occupants = roomOccupants(room.level, room.scan);
        double volume = Math.max(1.0D, room.scan.volume());
        double biologicalO2Support = bioRate.actualO2PerSecond() * volume / 0.14D;
        double biologicalCo2Support = bioRate.actualCo2PerSecond() * volume / 0.11D;
        double ventilationO2Support = flow.oxygenAddedPerSecond() * volume / 0.14D;
        double ventilationCo2Support = flow.co2RemovedPerSecond() * volume / 0.11D;
        double netO2Support = biologicalO2Support + ventilationO2Support - occupants;
        double netCo2Support = biologicalCo2Support + scrubber.actualPlayerEquivalent()
                + ventilationCo2Support - occupants;
        boolean co2Available = room.air.co2Percent() > RoomAtmosphere.NORMAL_CO2 + 0.000001D;

        var header = Component.literal("[LIFE] ")
                .withStyle(ChatFormatting.AQUA).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(room.scan.volume() + " m³").withStyle(ChatFormatting.WHITE))
                .append(Component.literal(" | O2 ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.2f%%", room.air.oxygenPercent()))
                        .withStyle(oxygenColor(room.air.oxygenPercent())))
                .append(Component.literal(" | CO2 ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.3f%%", room.air.co2Percent()))
                        .withStyle(co2Color(room.air.co2Percent())))
                .append(Component.literal(" | Air ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.1f%%", room.air.airQualityPercent()))
                        .withStyle(qualityColor(room.air.airQualityPercent())));
        source.sendSuccess(() -> header, false);

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
            source.sendSuccess(() -> Component.literal("[BIO] None").withStyle(ChatFormatting.DARK_GRAY), false);
        } else {
            var bioLine = Component.literal("[BIO] ").withStyle(ChatFormatting.GREEN).withStyle(ChatFormatting.BOLD)
                    .append(Component.literal(String.format(Locale.ROOT,
                            "%d plants | Active %.1f/%.1f | Light %.0f%% | %.2f eq",
                            bio.plantBlocks(), bio.activeCapacity(), bio.nominalCapacity(),
                            bio.lightUtilization() * 100.0D, bio.supportedPlayers())).withStyle(ChatFormatting.GRAY));
            source.sendSuccess(() -> bioLine, false);

            var bioRateLine = Component.literal("      ")
                    .append(Component.literal(String.format(Locale.ROOT, "CO2 -%.4f%%/min",
                            bioRate.actualCo2PerSecond() * 60.0D))
                            .withStyle(bioRate.actualCo2PerSecond() > 0.0D ? ChatFormatting.GREEN : ChatFormatting.GRAY))
                    .append(Component.literal(" | ").withStyle(ChatFormatting.DARK_GRAY))
                    .append(Component.literal(String.format(Locale.ROOT, "O2 +%.4f%%/min",
                            bioRate.actualO2PerSecond() * 60.0D))
                            .withStyle(bioRate.actualO2PerSecond() > 0.0D ? ChatFormatting.GREEN : ChatFormatting.GRAY))
                    .append(Component.literal(" | CO2 ").withStyle(ChatFormatting.DARK_GRAY))
                    .append(Component.literal(co2Available ? "AVAILABLE" : "LOW")
                            .withStyle(co2Available ? ChatFormatting.GREEN : ChatFormatting.YELLOW));
            source.sendSuccess(() -> bioRateLine, false);
        }

        if (scrubber.units() <= 0) {
            source.sendSuccess(() -> Component.literal("[SCRUBBER] None").withStyle(ChatFormatting.DARK_GRAY), false);
        } else {
            ChatFormatting scrubberColor = scrubber.activeUnits() > 0 ? ChatFormatting.AQUA : ChatFormatting.YELLOW;
            var scrubberLine = Component.literal("[SCRUBBER] ").withStyle(scrubberColor).withStyle(ChatFormatting.BOLD)
                    .append(Component.literal(String.format(Locale.ROOT,
                            "%d unit(s) | Ready %d | Active %d | %.2f/%.2f eq",
                            scrubber.units(), scrubber.readyUnits(), scrubber.activeUnits(),
                            scrubber.actualPlayerEquivalent(), scrubber.nominalPlayerEquivalent()))
                            .withStyle(ChatFormatting.GRAY));
            source.sendSuccess(() -> scrubberLine, false);
            source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                    "      Flow %.1f m³/s | CO2 -%.4f%%/min | O2 +0",
                    scrubber.flowCapacity(), scrubber.co2RemovedPerSecond() * 60.0D))
                    .withStyle(ChatFormatting.GRAY), false);
        }

        ChatFormatting ventColor = flow.supplyM3PerSecond() > 0.0D || flow.returnM3PerSecond() > 0.0D
                ? ChatFormatting.BLUE : ChatFormatting.DARK_GRAY;
        var ventilationLine = Component.literal("[VENT] ").withStyle(ventColor).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(String.format(Locale.ROOT,
                        "Supply %.1f (%d) | Return %.1f (%d) | Fresh %.2f | Recirc %.2f m³/s",
                        flow.supplyM3PerSecond(), roomVents.supplyVents(),
                        flow.returnM3PerSecond(), roomVents.returnVents(),
                        flow.freshAirM3PerSecond(), flow.recirculatedM3PerSecond()))
                        .withStyle(ChatFormatting.GRAY));
        source.sendSuccess(() -> ventilationLine, false);

        var ventGasLine = Component.literal("      Gas  ").withStyle(ChatFormatting.DARK_GRAY)
                .append(Component.literal(String.format(Locale.ROOT, "O2 +%.4f%%/min (%.2f eq)",
                        flow.oxygenAddedPerSecond() * 60.0D, ventilationO2Support))
                        .withStyle(ventilationO2Support > 0.0D ? ChatFormatting.GREEN : ChatFormatting.GRAY))
                .append(Component.literal(" | ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "CO2 -%.4f%%/min (%.2f eq)",
                        flow.co2RemovedPerSecond() * 60.0D, ventilationCo2Support))
                        .withStyle(ventilationCo2Support > 0.0D ? ChatFormatting.GREEN : ChatFormatting.GRAY));
        source.sendSuccess(() -> ventGasLine, false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
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
            source.sendSuccess(() -> Component.literal("[TRANSFER] None").withStyle(ChatFormatting.DARK_GRAY), false);
        } else {
            var transferLine = Component.literal("[TRANSFER] ").withStyle(ChatFormatting.DARK_AQUA).withStyle(ChatFormatting.BOLD)
                    .append(Component.literal(String.format(Locale.ROOT,
                            "%d room(s) | %d vent(s) | %.1f m³/s",
                            transfer.connectedRooms(), transfer.ventCount(), transfer.totalCapacity()))
                            .withStyle(ChatFormatting.GRAY));
            source.sendSuccess(() -> transferLine, false);
            source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                    "      Max delta O2 %.3f%% | CO2 %.3f%%",
                    transfer.maxOxygenDelta(), transfer.maxCo2Delta())).withStyle(ChatFormatting.GRAY), false);
        }

        var o2Balance = Component.literal("[O2 BAL] ").withStyle(ChatFormatting.BLUE).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(String.format(Locale.ROOT,
                        "Load %.2f | Supply %.2f | Net ",
                        (double) occupants, biologicalO2Support + ventilationO2Support)).withStyle(ChatFormatting.GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%+.2f eq", netO2Support))
                        .withStyle(balanceColor(netO2Support)));
        source.sendSuccess(() -> o2Balance, false);

        var co2Balance = Component.literal("[CO2 BAL] ").withStyle(ChatFormatting.GOLD).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(String.format(Locale.ROOT,
                        "Load %.2f | Removal %.2f | Net ",
                        (double) occupants, biologicalCo2Support + scrubber.actualPlayerEquivalent() + ventilationCo2Support))
                        .withStyle(ChatFormatting.GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%+.2f eq", netCo2Support))
                        .withStyle(balanceColor(netCo2Support)));
        source.sendSuccess(() -> co2Balance, false);

        final String status;
        final ChatFormatting statusColor;
        boolean o2Limited = netO2Support < -0.05D;
        boolean co2Limited = netCo2Support < -0.05D;
        if (o2Limited && co2Limited) {
            status = "O2 + CO2 LIMITED";
            statusColor = ChatFormatting.RED;
        } else if (o2Limited) {
            status = "O2 LIMITED";
            statusColor = ChatFormatting.RED;
        } else if (co2Limited) {
            status = "CO2 LIMITED";
            statusColor = ChatFormatting.RED;
        } else if (occupants == 0) {
            status = "NO LOCAL RESPIRATION LOAD";
            statusColor = ChatFormatting.GRAY;
        } else {
            status = "LOCAL LIFE SUPPORT SUPPORTED";
            statusColor = ChatFormatting.GREEN;
        }

        var statusLine = Component.literal("[STATUS] ").withStyle(statusColor).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(status).withStyle(statusColor));
        source.sendSuccess(() -> statusLine, false);
        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString())
                .withStyle(ChatFormatting.DARK_GRAY), false);
        return 1;
    }

    private static ChatFormatting oxygenColor(double oxygen) {
        if (oxygen >= 20.0D) return ChatFormatting.GREEN;
        if (oxygen >= 18.5D) return ChatFormatting.YELLOW;
        return ChatFormatting.RED;
    }

    private static ChatFormatting co2Color(double co2) {
        if (co2 <= 0.5D) return ChatFormatting.GREEN;
        if (co2 <= 1.5D) return ChatFormatting.YELLOW;
        return ChatFormatting.RED;
    }

    private static ChatFormatting qualityColor(double quality) {
        if (quality >= 90.0D) return ChatFormatting.GREEN;
        if (quality >= 70.0D) return ChatFormatting.YELLOW;
        return ChatFormatting.RED;
    }

    private static ChatFormatting dustColor(double dust) {
        if (dust <= 1.0D) return ChatFormatting.GREEN;
        if (dust <= 5.0D) return ChatFormatting.YELLOW;
        return ChatFormatting.RED;
    }

    private static ChatFormatting radiationColor(double radHour) {
        if (radHour <= 0.10D) return ChatFormatting.GREEN;
        if (radHour <= 1.0D) return ChatFormatting.YELLOW;
        return ChatFormatting.RED;
    }

    private static ChatFormatting balanceColor(double netSupport) {
        if (netSupport > 0.05D) return ChatFormatting.GREEN;
        if (netSupport >= -0.05D) return ChatFormatting.YELLOW;
        return ChatFormatting.RED;
    }

    private static int roomOccupants(ServerLevel level, RoomScanResult room) {
        int occupants = 0;
        for (ServerPlayer player : level.players()) {
            RoomScanResult playerRoom = RoomScanner.scan(level, player.blockPosition());
            if (playerRoom.sealed() && playerRoom.anchor().equals(room.anchor())) occupants++;
        }
        return occupants;
    }

    private static int roomPreset(CommandSourceStack source, boolean wasteland)
            throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;
        if (wasteland) {
            room.air.setComposition(RoomEnvironmentManager.WASTELAND_OUTSIDE_DUST,
                    RoomEnvironmentManager.WASTELAND_OUTSIDE_AIRBORNE_MSV_PER_SECOND,
                    RoomAtmosphere.NORMAL_OXYGEN, RoomAtmosphere.NORMAL_CO2);
        } else {
            room.air.setComposition(0.0D, 0.0D, RoomAtmosphere.NORMAL_OXYGEN, RoomAtmosphere.NORMAL_CO2);
        }
        RoomAtmosphereSavedData.get(room.level).markChanged();
        source.sendSuccess(() -> Component.literal(wasteland
                ? "AFTERFALL: room set to WASTELAND AIR preset."
                : "AFTERFALL: room set to CLEAN AIR preset."), true);
        return roomInfo(source);
    }

    private static int roomSetAll(CommandSourceStack source, double dust, double radHour, double o2, double co2)
            throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;
        room.air.setComposition(dust, radHour / 3600.0D, o2, co2);
        RoomAtmosphereSavedData.get(room.level).markChanged();
        return roomInfo(source);
    }

    private static int roomScalar(CommandSourceStack source, Scalar scalar, double value, boolean add)
            throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;
        double dust = room.air.dustPercent();
        double radHour = room.air.airborneRadiationPerSecond() * 3600.0D;
        double o2 = room.air.oxygenPercent();
        double co2 = room.air.co2Percent();
        switch (scalar) {
            case DUST -> dust = add ? dust + value : value;
            case RADIATION -> radHour = add ? radHour + value : value;
            case OXYGEN -> o2 = add ? o2 + value : value;
            case CO2 -> co2 = add ? co2 + value : value;
        }
        room.air.setComposition(Mth.clamp(dust, 0.0D, 100.0D),
                Math.max(0.0D, radHour) / 3600.0D,
                Mth.clamp(o2, 0.0D, RoomAtmosphere.NORMAL_OXYGEN),
                Mth.clamp(co2, RoomAtmosphere.NORMAL_CO2, 20.0D));
        RoomAtmosphereSavedData.get(room.level).markChanged();
        return roomInfo(source);
    }

    private static int roomSimulate(CommandSourceStack source, int occupants, int seconds)
            throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        RoomContext room = currentRoom(source);
        if (room == null) return 0;
        room.air.simulateBreathing(occupants, seconds);
        RoomAtmosphereSavedData.get(room.level).markChanged();
        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "AFTERFALL: simulated %d occupant(s) breathing for %d s.", occupants, seconds)), true);
        return roomInfo(source);
    }

    private static int playerInfo(CommandSourceStack source, Collection<ServerPlayer> targets) {
        for (ServerPlayer target : targets) {
            double dose = target.getData(ModAttachments.RADIATION_DOSE);
            double contamination = target.getData(ModAttachments.CONTAMINATION);
            RadiationReading reading = RadiationManager.sample(target);
            source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                    "%s | Dose %.2f mSv | Contamination %.2f%% | Rate %.2f mSv/h",
                    target.getName().getString(), dose, contamination, reading.totalRatePerHour())), false);
        }
        return targets.size();
    }

    private static int playerReset(CommandSourceStack source, Collection<ServerPlayer> targets) {
        for (ServerPlayer target : targets) {
            target.setData(ModAttachments.RADIATION_DOSE, 0.0D);
            target.setData(ModAttachments.CONTAMINATION, 0.0D);
        }
        source.sendSuccess(() -> Component.literal("AFTERFALL: reset dose + contamination for " + targets.size() + " player(s)."), true);
        return targets.size();
    }

    private static int playerValue(CommandSourceStack source, PlayerValue type, boolean add, double value,
                                   Collection<ServerPlayer> targets) {
        for (ServerPlayer target : targets) {
            if (type == PlayerValue.DOSE) {
                double current = target.getData(ModAttachments.RADIATION_DOSE);
                target.setData(ModAttachments.RADIATION_DOSE,
                        Mth.clamp(add ? current + value : value, 0.0D, 5000.0D));
            } else {
                double current = target.getData(ModAttachments.CONTAMINATION);
                target.setData(ModAttachments.CONTAMINATION,
                        Mth.clamp(add ? current + value : value, 0.0D, 100.0D));
            }
        }
        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "AFTERFALL: %s %s %.2f for %d player(s).",
                type == PlayerValue.DOSE ? "dose" : "contamination", add ? "changed by" : "set to", value, targets.size())), true);
        return targets.size();
    }

    private static int radiationSample(CommandSourceStack source, Collection<ServerPlayer> targets) {
        for (ServerPlayer target : targets) {
            RadiationReading r = RadiationManager.sample(target);
            source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                    "%s RAD | Total %.2f | Gamma %.2f | Hotspot %.2f | Air %.2f | Internal %.2f mSv/h | Shield %.1f%%",
                    target.getName().getString(), r.totalRatePerHour(),
                    r.externalGammaRatePerSecond() * 3600.0D,
                    r.hotspotRatePerSecond() * 3600.0D,
                    r.airborneRatePerSecond() * 3600.0D,
                    r.contaminationRatePerSecond() * 3600.0D,
                    r.shieldingPercent())), false);
        }
        return targets.size();
    }

    private enum Scalar { DUST, RADIATION, OXYGEN, CO2 }
    private enum PlayerValue { DOSE, CONTAMINATION }
    private record RoomContext(ServerLevel level, RoomScanResult scan, RoomAtmosphere air) {}

    private AfterfallCommands() {}
}
