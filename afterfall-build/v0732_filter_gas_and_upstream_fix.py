from pathlib import Path

root = Path('Afterfall')

# --- Compact filter: keep moving breathing gases until FRONT matches BACK ---
p = root / 'src/main/java/dev/afterfall/blockentity/AirFilterBlockEntity.java'
s = p.read_text()
s = s.replace(
'''        RoomAtmosphere inputAir = atmosphere(serverLevel, input);\n        RoomAtmosphere outputAir = atmosphere(serverLevel, output);\n        if (isClean(outputAir)) return;\n        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, be.energy, ENERGY_PER_SECOND)) return;''',
'''        RoomAtmosphere inputAir = atmosphere(serverLevel, input);\n        RoomAtmosphere outputAir = atmosphere(serverLevel, output);\n        if (!needsProcessing(inputAir, outputAir)) return;\n        if (!MachinePower.consumeOrRedstoneFallback(serverLevel, pos, be.energy, ENERGY_PER_SECOND)) return;''')

needle = '''    public static boolean isClean(RoomAtmosphere atmosphere) {\n        return atmosphere != null\n                && atmosphere.dustPercent() <= TARGET_DUST\n                && atmosphere.airborneRadiationPerSecond() * 3600.0D <= TARGET_AIRBORNE_MSV_H;\n    }\n'''
replacement = needle + '''\n    /**\n     * The compact unit is an air mover as well as a filter. A clean FRONT plenum\n     * must therefore not enter standby while its O2/CO2 still differ materially\n     * from the BACK/mixing plenum.\n     */\n    public static boolean needsProcessing(RoomAtmosphere input, RoomAtmosphere output) {\n        if (input == null || output == null) return false;\n        if (!isClean(output)) return true;\n        return Math.abs(output.oxygenPercent() - input.oxygenPercent()) > 0.05D\n                || Math.abs(output.co2Percent() - input.co2Percent()) > 0.02D;\n    }\n'''
if needle not in s:
    raise SystemExit('AirFilterBlockEntity isClean anchor not found')
s = s.replace(needle, replacement)

s = s.replace(
'''        boolean clean = isClean(outputAir);\n        return Component.literal(String.format(Locale.ROOT,\n                "Compact Filter: %s | BACK %dm³ Dust %.2f%% Rad %.2f | FRONT %dm³ Dust %.2f%% Rad %.2f | %.0f m³/s | %s",\n                clean ? "STANDBY" : "FILTERING", input.volume(), inputAir.dustPercent(),''',
'''        boolean processing = needsProcessing(inputAir, outputAir);\n        return Component.literal(String.format(Locale.ROOT,\n                "Compact Filter: %s | BACK %dm³ Dust %.2f%% Rad %.2f | FRONT %dm³ Dust %.2f%% Rad %.2f | %.0f m³/s | %s",\n                processing ? "FILTERING" : "STANDBY", input.volume(), inputAir.dustPercent(),''')
s = s.replace(
'''                outputAir.airborneRadiationPerSecond() * 3600.0D, FLOW_M3_PER_SECOND, be.filters.compactStatus()))\n                .withStyle(clean ? ChatFormatting.GREEN : ChatFormatting.YELLOW);''',
'''                outputAir.airborneRadiationPerSecond() * 3600.0D, FLOW_M3_PER_SECOND, be.filters.compactStatus()))\n                .withStyle(processing ? ChatFormatting.YELLOW : ChatFormatting.GREEN);''')
p.write_text(s)

# --- Main fan diagnostics: traverse a compact filter based on physical FRONT adjacency ---
p = root / 'src/main/java/dev/afterfall/room/IntakeNetworkScanner.java'
s = p.read_text()
s = s.replace('import dev.afterfall.blockentity.AirFilterBlockEntity;\n',
              'import dev.afterfall.block.AirFilterBlock;\nimport dev.afterfall.blockentity.AirFilterBlockEntity;\n')

old = '''        for (long packed : boundary.filters()) {\n            BlockPos filterPos = BlockPos.of(packed);\n            if (!(level.getBlockEntity(filterPos) instanceof AirFilterBlockEntity filter)) continue;\n            RoomScanResult output = filter.inspectOutput(level);\n            RoomScanResult input = filter.inspectInput(level);\n            if (output == null || input == null) continue;\n            if (output.anchor().asLong() != anchor) continue; // only walk FRONT -> BACK\n            if (input.anchor().equals(output.anchor())) continue;\n            collectUpstream(level, input, depth + 1, visitedRooms, roomAnchors, intakes);\n        }'''
new = '''        for (long packed : boundary.filters()) {\n            BlockPos filterPos = BlockPos.of(packed);\n            if (!(level.getBlockEntity(filterPos) instanceof AirFilterBlockEntity filter)) continue;\n            RoomScanResult input = filter.inspectInput(level);\n            if (input == null || input.anchor().asLong() == anchor) continue;\n            collectUpstream(level, input, depth + 1, visitedRooms, roomAnchors, intakes);\n        }'''
if old not in s:
    raise SystemExit('IntakeNetworkScanner collectUpstream anchor not found')
s = s.replace(old, new)

old = '''                if (level.getBlockState(next).is(ModBlocks.AIR_INTAKE_UNIT.get())) {\n                    intakePositions.add(next.asLong());\n                } else if (level.getBlockState(next).is(ModBlocks.AIR_FILTER_UNIT.get())) {\n                    filterPositions.add(next.asLong());\n                }'''
new = '''                if (level.getBlockState(next).is(ModBlocks.AIR_INTAKE_UNIT.get())) {\n                    intakePositions.add(next.asLong());\n                } else if (level.getBlockState(next).is(ModBlocks.AIR_FILTER_UNIT.get())) {\n                    var filterState = level.getBlockState(next);\n                    // Only expose a compact filter as an upstream edge when this\n                    // room physically touches its FRONT/output face. This is more\n                    // robust than comparing independently scanned room anchors.\n                    if (filterState.hasProperty(AirFilterBlock.FACING)\n                            && next.relative(filterState.getValue(AirFilterBlock.FACING)).equals(current)) {\n                        filterPositions.add(next.asLong());\n                    }\n                }'''
if old not in s:
    raise SystemExit('IntakeNetworkScanner boundary anchor not found')
s = s.replace(old, new)
p.write_text(s)

# --- Machine GUI status: FILTERING also while balancing breathing gases ---
p = root / 'src/main/java/dev/afterfall/menu/MachineMenu.java'
s = p.read_text()
s = s.replace(
'''            else if (!be.filters().complete()) data.set(D_STATUS, 3);\n            else data.set(D_STATUS, AirFilterBlockEntity.isClean(outputAir) ? 5 : 4);''',
'''            else if (!be.filters().complete()) data.set(D_STATUS, 3);\n            else data.set(D_STATUS, AirFilterBlockEntity.needsProcessing(inputAir, outputAir) ? 4 : 5);''')
p.write_text(s)

# version
p = root / 'gradle.properties'
s = p.read_text().replace('mod_version=0.7.3.1', 'mod_version=0.7.3.2')
p.write_text(s)

print('Afterfall 0.7.3.2 filter gas-balance and upstream intake diagnostics fix applied')
