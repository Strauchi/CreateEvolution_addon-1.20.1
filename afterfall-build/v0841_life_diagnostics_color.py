from pathlib import Path
import re

ROOT = Path("Afterfall")
COMMANDS = ROOT / "src/main/java/dev/afterfall/command/AfterfallCommands.java"
GRADLE = ROOT / "gradle.properties"

text = COMMANDS.read_text(encoding="utf-8")

needle = "import net.minecraft.commands.arguments.EntityArgument;\n"
if "import net.minecraft.ChatFormatting;" not in text:
    if needle not in text:
        raise SystemExit("Could not find EntityArgument import anchor")
    text = text.replace(needle, "import net.minecraft.ChatFormatting;\n" + needle, 1)

room_method = r'''    private static int roomInfo(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
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
    }'''

life_method = r'''    private static int lifeInfo(CommandSourceStack source) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
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

        var header = Component.literal("[LIFE SUPPORT] ")
                .withStyle(ChatFormatting.AQUA).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(room.scan.volume() + " m³").withStyle(ChatFormatting.WHITE))
                .append(Component.literal("  |  O2 ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.2f%%", room.air.oxygenPercent()))
                        .withStyle(oxygenColor(room.air.oxygenPercent())))
                .append(Component.literal("  |  CO2 ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.3f%%", room.air.co2Percent()))
                        .withStyle(co2Color(room.air.co2Percent())))
                .append(Component.literal("  |  Air ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%.1f%%", room.air.airQualityPercent()))
                        .withStyle(qualityColor(room.air.airQualityPercent())));
        source.sendSuccess(() -> header, false);

        var bioLine = Component.literal("[BIO] ")
                .withStyle(bio.plantBlocks() > 0 ? ChatFormatting.GREEN : ChatFormatting.DARK_GRAY)
                .withStyle(ChatFormatting.BOLD)
                .append(Component.literal(String.format(Locale.ROOT,
                        "%d plants | Capacity %.1f | Active %.1f | Light %.0f%% | Theoretical %.2f player-eq",
                        bio.plantBlocks(), bio.nominalCapacity(), bio.activeCapacity(),
                        bio.lightUtilization() * 100.0D, bio.supportedPlayers())).withStyle(ChatFormatting.GRAY));
        source.sendSuccess(() -> bioLine, false);

        var bioRateLine = Component.literal("      Rate  ").withStyle(ChatFormatting.DARK_GRAY)
                .append(Component.literal(String.format(Locale.ROOT, "Potential CO2 -%.4f%%/min",
                        bioRate.potentialCo2PerSecond() * 60.0D)).withStyle(ChatFormatting.GRAY))
                .append(Component.literal("  |  ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "Actual CO2 -%.4f%%/min",
                        bioRate.actualCo2PerSecond() * 60.0D))
                        .withStyle(bioRate.actualCo2PerSecond() > 0.0D ? ChatFormatting.GREEN : ChatFormatting.GRAY))
                .append(Component.literal("  |  ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "O2 +%.4f%%/min",
                        bioRate.actualO2PerSecond() * 60.0D))
                        .withStyle(bioRate.actualO2PerSecond() > 0.0D ? ChatFormatting.GREEN : ChatFormatting.GRAY))
                .append(Component.literal("  |  CO2 available ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(co2Available ? "YES" : "NO")
                        .withStyle(co2Available ? ChatFormatting.GREEN : ChatFormatting.YELLOW));
        source.sendSuccess(() -> bioRateLine, false);

        ChatFormatting scrubberColor = scrubber.activeUnits() > 0 ? ChatFormatting.AQUA
                : (scrubber.units() > 0 ? ChatFormatting.YELLOW : ChatFormatting.DARK_GRAY);
        var scrubberLine = Component.literal("[SCRUBBER] ").withStyle(scrubberColor).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(String.format(Locale.ROOT,
                        "%d unit(s) | Ready %d | Active %d | Flow %.1f m³/s | Nominal %.2f | Actual %.2f player-eq | CO2 -%.4f%%/min | O2 +0",
                        scrubber.units(), scrubber.readyUnits(), scrubber.activeUnits(), scrubber.flowCapacity(),
                        scrubber.nominalPlayerEquivalent(), scrubber.actualPlayerEquivalent(),
                        scrubber.co2RemovedPerSecond() * 60.0D)).withStyle(ChatFormatting.GRAY));
        source.sendSuccess(() -> scrubberLine, false);

        ChatFormatting ventColor = flow.supplyM3PerSecond() > 0.0D || flow.returnM3PerSecond() > 0.0D
                ? ChatFormatting.BLUE : ChatFormatting.DARK_GRAY;
        var ventilationLine = Component.literal("[VENT] ").withStyle(ventColor).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(String.format(Locale.ROOT,
                        "Supply %.2f m³/s (%d) | Return %.2f m³/s (%d) | Fresh %.2f | Recirc %.2f | Demand %.2f m³/s",
                        flow.supplyM3PerSecond(), roomVents.supplyVents(),
                        flow.returnM3PerSecond(), roomVents.returnVents(),
                        flow.freshAirM3PerSecond(), flow.recirculatedM3PerSecond(), demand))
                        .withStyle(ChatFormatting.GRAY));
        source.sendSuccess(() -> ventilationLine, false);

        var ventGasLine = Component.literal("       Gas  ").withStyle(ChatFormatting.DARK_GRAY)
                .append(Component.literal(String.format(Locale.ROOT, "O2 +%.4f%%/min (%.2f eq)",
                        flow.oxygenAddedPerSecond() * 60.0D, ventilationO2Support))
                        .withStyle(ventilationO2Support > 0.0D ? ChatFormatting.GREEN : ChatFormatting.GRAY))
                .append(Component.literal("  |  ").withStyle(ChatFormatting.DARK_GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "CO2 -%.4f%%/min (%.2f eq)",
                        flow.co2RemovedPerSecond() * 60.0D, ventilationCo2Support))
                        .withStyle(ventilationCo2Support > 0.0D ? ChatFormatting.GREEN : ChatFormatting.GRAY));
        source.sendSuccess(() -> ventGasLine, false);

        ChatFormatting transferColor = transfer.ventCount() > 0 ? ChatFormatting.DARK_AQUA : ChatFormatting.DARK_GRAY;
        var transferLine = Component.literal("[TRANSFER] ").withStyle(transferColor).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(String.format(Locale.ROOT,
                        "%d room(s) | %d vent(s) | %.1f m³/s | Max dO2 %.3f%% | Max dCO2 %.3f%%",
                        transfer.connectedRooms(), transfer.ventCount(), transfer.totalCapacity(),
                        transfer.maxOxygenDelta(), transfer.maxCo2Delta())).withStyle(ChatFormatting.GRAY));
        source.sendSuccess(() -> transferLine, false);

        var o2Balance = Component.literal("[O2 BAL] ").withStyle(ChatFormatting.BLUE).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(String.format(Locale.ROOT,
                        "Respiration %.2f | Bio %.2f | Vent %.2f | Net ",
                        (double) occupants, biologicalO2Support, ventilationO2Support)).withStyle(ChatFormatting.GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%+.2f player-eq", netO2Support))
                        .withStyle(balanceColor(netO2Support)));
        source.sendSuccess(() -> o2Balance, false);

        var co2Balance = Component.literal("[CO2 BAL] ").withStyle(ChatFormatting.GOLD).withStyle(ChatFormatting.BOLD)
                .append(Component.literal(String.format(Locale.ROOT,
                        "Respiration %.2f | Bio %.2f | Scrubber %.2f | Vent %.2f | Net ",
                        (double) occupants, biologicalCo2Support, scrubber.actualPlayerEquivalent(),
                        ventilationCo2Support)).withStyle(ChatFormatting.GRAY))
                .append(Component.literal(String.format(Locale.ROOT, "%+.2f player-eq", netCo2Support))
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
    }'''

room_pattern = re.compile(
    r"    private static int roomInfo\(CommandSourceStack source\).*?\n    }\n\n    private static int lifeInfo",
    re.S,
)
match = room_pattern.search(text)
if not match:
    raise SystemExit("Could not locate roomInfo method")
text = text[:match.start()] + room_method + "\n\n    private static int lifeInfo" + text[match.end():]

life_pattern = re.compile(
    r"    private static int lifeInfo\(CommandSourceStack source\).*?\n    }\n\n    private static int roomOccupants",
    re.S,
)
match = life_pattern.search(text)
if not match:
    raise SystemExit("Could not locate lifeInfo method")
text = text[:match.start()] + life_method + "\n\n    private static int roomOccupants" + text[match.end():]

COMMANDS.write_text(text, encoding="utf-8")

gradle = GRADLE.read_text(encoding="utf-8")
old = "mod_version=0.8.4"
new = "mod_version=0.8.4.1"
if old not in gradle:
    raise SystemExit("Expected 0.8.4 mod_version not found")
gradle = gradle.replace(old, new, 1)
GRADLE.write_text(gradle, encoding="utf-8")

print("Applied Afterfall 0.8.4.1 life-support diagnostics + color UI patch")
