from pathlib import Path
import re

ROOT = Path("Afterfall")
COMMANDS = ROOT / "src/main/java/dev/afterfall/command/AfterfallCommands.java"
GRADLE = ROOT / "gradle.properties"

text = COMMANDS.read_text(encoding="utf-8")

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
    }'''

life_pattern = re.compile(
    r"    private static int lifeInfo\(CommandSourceStack source\).*?\n    }\n\n    private static ChatFormatting oxygenColor",
    re.S,
)
match = life_pattern.search(text)
if not match:
    raise SystemExit("Could not locate lifeInfo method for 0.8.4.2")
text = text[:match.start()] + life_method + "\n\n    private static ChatFormatting oxygenColor" + text[match.end():]
COMMANDS.write_text(text, encoding="utf-8")

gradle = GRADLE.read_text(encoding="utf-8")
gradle, count = re.subn(r"(?m)^mod_version=.*$", "mod_version=0.8.4.2", gradle, count=1)
if count != 1:
    raise SystemExit("Could not update mod_version")
GRADLE.write_text(gradle, encoding="utf-8")
print("Applied Afterfall 0.8.4.2 life UI polish")
