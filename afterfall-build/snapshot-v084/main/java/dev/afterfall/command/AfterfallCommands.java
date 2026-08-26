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
        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "ROOM %dm³ | Dust %.2f%% | Air Rad %.2f mSv/h | O2 %.2f%% | CO2 %.2f%% | Air %.1f%%",
                room.scan.volume(), room.air.dustPercent(), radHour, room.air.oxygenPercent(),
                room.air.co2Percent(), room.air.airQualityPercent())), false);
        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()
                + " | Detailed systems: /af life"), false);
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
        double actualBioSupport = bioRate.actualCo2PerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double ventilationO2Support = flow.oxygenAddedPerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.14D;
        double ventilationCo2Support = flow.co2RemovedPerSecond()
                * Math.max(1.0D, room.scan.volume()) / 0.11D;
        double ventilationSupport = Math.max(ventilationO2Support, ventilationCo2Support);
        double netCo2Support = actualBioSupport + scrubber.actualPlayerEquivalent()
                + ventilationCo2Support - occupants;
        boolean co2Available = room.air.co2Percent() > RoomAtmosphere.NORMAL_CO2 + 0.000001D;

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "LIFE %dm³ | O2 %.2f%% | CO2 %.3f%% | Air %.1f%% | Fresh demand %.2f m³/s",
                room.scan.volume(), room.air.oxygenPercent(), room.air.co2Percent(),
                room.air.airQualityPercent(), demand)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Biological: %d plants | Capacity %.1f | Active %.1f | Light %.0f%% | Theoretical %.2f player-eq",
                bio.plantBlocks(), bio.nominalCapacity(), bio.activeCapacity(),
                bio.lightUtilization() * 100.0D, bio.supportedPlayers())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Bio rate: Potential CO2 -%.4f%%/min | Actual CO2 -%.4f%%/min | Actual O2 +%.4f%%/min | CO2 available %s",
                bioRate.potentialCo2PerSecond() * 60.0D,
                bioRate.actualCo2PerSecond() * 60.0D,
                bioRate.actualO2PerSecond() * 60.0D,
                co2Available ? "YES" : "NO")), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "CO2 scrubber: %d unit(s) | Ready %d | Active %d | Flow cap %.1f m³/s | Nominal %.2f | Actual %.2f player-eq | CO2 -%.4f%%/min",
                scrubber.units(), scrubber.readyUnits(), scrubber.activeUnits(), scrubber.flowCapacity(),
                scrubber.nominalPlayerEquivalent(), scrubber.actualPlayerEquivalent(),
                scrubber.co2RemovedPerSecond() * 60.0D)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Ventilation: Supply %.2f m³/s (%d vent) | Return %.2f m³/s (%d vent) | Fresh %.2f m³/s | Recirc %.2f m³/s",
                flow.supplyM3PerSecond(), roomVents.supplyVents(),
                flow.returnM3PerSecond(), roomVents.returnVents(),
                flow.freshAirM3PerSecond(), flow.recirculatedM3PerSecond())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Vent gas: O2 +%.4f%%/min | CO2 -%.4f%%/min | O2 support %.2f | CO2 support %.2f player-eq",
                flow.oxygenAddedPerSecond() * 60.0D,
                flow.co2RemovedPerSecond() * 60.0D,
                ventilationO2Support, ventilationCo2Support)), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "Passive transfer: %d connected room(s) | %d Transfer Vent(s) | %.1f m³/s | Max dO2 %.3f%% | Max dCO2 %.3f%%",
                transfer.connectedRooms(), transfer.ventCount(), transfer.totalCapacity(),
                transfer.maxOxygenDelta(), transfer.maxCo2Delta())), false);

        source.sendSuccess(() -> Component.literal(String.format(Locale.ROOT,
                "CO2 balance (local): Respiration %.2f | Bio %.2f | Scrubber %.2f | Vent %.2f | Net %+.2f player-eq",
                (double) occupants, actualBioSupport, scrubber.actualPlayerEquivalent(),
                ventilationCo2Support, netCo2Support)), false);
        source.sendSuccess(() -> Component.literal("Note: CO2 Scrubber removes CO2 only; it does not generate O2."), false);
        source.sendSuccess(() -> Component.literal("Anchor: " + room.scan.anchor().toShortString()), false);
        return 1;
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
