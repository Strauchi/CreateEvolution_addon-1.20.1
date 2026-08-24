from pathlib import Path

root = Path('Afterfall')

def replace_once(path, old, new, label):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly 1 match, found {count}')
    path.write_text(text.replace(old, new, 1))

props = root / 'gradle.properties'
replace_once(props, 'mod_version=0.5.1', 'mod_version=0.5.2', 'version')

controller = root / 'src/main/java/dev/afterfall/blockentity/AirlockControllerBlockEntity.java'
text = controller.read_text()
if 'DOOR_CLOSE_DELAY_TICKS' not in text:
    text = text.replace(
        '    public static final int MAX_PURGE_TICKS = 600; // 30 s safety watchdog\n',
        '    public static final int MAX_PURGE_TICKS = 600; // 30 s safety watchdog\n'
        '    public static final int DOOR_CLOSE_DELAY_TICKS = 20; // 1.0 s after crossing the doorway\n'
        '    public static final int DOOR_SEAL_SETTLE_TICKS = 12; // 0.6 s after the door actually closes\n',
        1)
if 'private boolean closeActionDone;' not in text:
    text = text.replace('    private UUID requesterId;\n',
                        '    private UUID requesterId;\n    private boolean closeActionDone;\n', 1)
controller.write_text(text)

old_entry = '''            case WAITING_FOR_ENTRY -> {\n                if (requester != null && entryChamberSide != null\n                        && AirlockLogic.isPlayerOnDoorSide(requester, entryDoor, entryChamberSide)) {\n                    transition(level, CycleState.SEALING_ENTRY,\n                            Component.literal("AIRLOCK: OCCUPANT DETECTED - SEALING").withStyle(ChatFormatting.AQUA));\n                } else if (stateTicks >= 200) {\n                    AirlockLogic.setDoorOpen(level, entryDoor, false);\n                    finish(level, Component.literal("AIRLOCK: ENTRY REQUEST TIMED OUT").withStyle(ChatFormatting.GRAY));\n                }\n            }\n            case SEALING_ENTRY -> {\n                AirlockLogic.setDoorOpen(level, entryDoor, false);\n                if (stateTicks >= 12) {\n                    refreshChamber(level);\n                    transition(level, CycleState.PURGING,\n                            Component.literal("AIRLOCK: SEALED - PURGING").withStyle(ChatFormatting.YELLOW));\n                }\n            }\n'''
new_entry = '''            case WAITING_FOR_ENTRY -> {\n                if (requester != null && entryChamberSide != null\n                        && AirlockLogic.isPlayerOnDoorSide(requester, entryDoor, entryChamberSide)) {\n                    transition(level, CycleState.SEALING_ENTRY,\n                            Component.literal("AIRLOCK: OCCUPANT DETECTED - DOOR CLOSING IN 1s").withStyle(ChatFormatting.AQUA));\n                } else if (stateTicks >= 200) {\n                    if (requester != null && AirlockLogic.isPlayerInDoorway(requester, entryDoor)) {\n                        if (stateTicks % 20 == 0) {\n                            notifyRequester(Component.literal("AIRLOCK: DOORWAY OCCUPIED - HOLDING ENTRY DOOR").withStyle(ChatFormatting.YELLOW));\n                        }\n                        return;\n                    }\n                    AirlockLogic.setDoorOpen(level, entryDoor, false);\n                    finish(level, Component.literal("AIRLOCK: ENTRY REQUEST TIMED OUT").withStyle(ChatFormatting.GRAY));\n                }\n            }\n            case SEALING_ENTRY -> {\n                if (!closeActionDone) {\n                    if (stateTicks < DOOR_CLOSE_DELAY_TICKS) return;\n                    if (requester != null && AirlockLogic.isPlayerInDoorway(requester, entryDoor)) {\n                        if (stateTicks % 20 == 0) {\n                            notifyRequester(Component.literal("AIRLOCK: DOORWAY OCCUPIED - HOLDING ENTRY DOOR").withStyle(ChatFormatting.YELLOW));\n                        }\n                        return;\n                    }\n                    AirlockLogic.setDoorOpen(level, entryDoor, false);\n                    closeActionDone = true;\n                    stateTicks = 0;\n                    setChanged();\n                    return;\n                }\n                if (stateTicks >= DOOR_SEAL_SETTLE_TICKS) {\n                    refreshChamber(level);\n                    transition(level, CycleState.PURGING,\n                            Component.literal("AIRLOCK: SEALED - PURGING").withStyle(ChatFormatting.YELLOW));\n                }\n            }\n'''
replace_once(controller, old_entry, new_entry, 'entry close logic')

old_exit = '''            case WAITING_FOR_EXIT -> {\n                if (requester != null && exitChamberSide != null\n                        && !AirlockLogic.isPlayerOnDoorSide(requester, exitDoor, exitChamberSide)) {\n                    transition(level, CycleState.SEALING_EXIT,\n                            Component.literal("AIRLOCK: EXIT COMPLETE - CLOSING").withStyle(ChatFormatting.AQUA));\n                } else if (stateTicks >= 200) {\n                    transition(level, CycleState.SEALING_EXIT,\n                            Component.literal("AIRLOCK: EXIT TIMEOUT - CLOSING DOOR").withStyle(ChatFormatting.GRAY));\n                }\n            }\n            case SEALING_EXIT -> {\n                AirlockLogic.setDoorOpen(level, exitDoor, false);\n                if (stateTicks >= 12) {\n                    finish(level, Component.literal("AIRLOCK: CYCLE COMPLETE").withStyle(ChatFormatting.GREEN));\n                }\n            }\n'''
new_exit = '''            case WAITING_FOR_EXIT -> {\n                if (requester != null && exitChamberSide != null\n                        && !AirlockLogic.isPlayerOnDoorSide(requester, exitDoor, exitChamberSide)) {\n                    transition(level, CycleState.SEALING_EXIT,\n                            Component.literal("AIRLOCK: EXIT COMPLETE - DOOR CLOSING IN 1s").withStyle(ChatFormatting.AQUA));\n                } else if (stateTicks >= 200) {\n                    transition(level, CycleState.SEALING_EXIT,\n                            Component.literal("AIRLOCK: EXIT TIMEOUT - SAFE CLOSING").withStyle(ChatFormatting.GRAY));\n                }\n            }\n            case SEALING_EXIT -> {\n                if (!closeActionDone) {\n                    if (stateTicks < DOOR_CLOSE_DELAY_TICKS) return;\n                    if (requester != null && AirlockLogic.isPlayerInDoorway(requester, exitDoor)) {\n                        if (stateTicks % 20 == 0) {\n                            notifyRequester(Component.literal("AIRLOCK: DOORWAY OCCUPIED - HOLDING EXIT DOOR").withStyle(ChatFormatting.YELLOW));\n                        }\n                        return;\n                    }\n                    AirlockLogic.setDoorOpen(level, exitDoor, false);\n                    closeActionDone = true;\n                    stateTicks = 0;\n                    setChanged();\n                    return;\n                }\n                if (stateTicks >= DOOR_SEAL_SETTLE_TICKS) {\n                    finish(level, Component.literal("AIRLOCK: CYCLE COMPLETE").withStyle(ChatFormatting.GREEN));\n                }\n            }\n'''
replace_once(controller, old_exit, new_exit, 'exit close logic')

replace_once(controller,
    '''    private void transition(ServerLevel level, CycleState next, Component message) {\n        cycleState = next;\n        stateTicks = 0;\n        setChanged();\n        notifyRequester(message);\n    }\n''',
    '''    private void transition(ServerLevel level, CycleState next, Component message) {\n        cycleState = next;\n        stateTicks = 0;\n        closeActionDone = false;\n        setChanged();\n        notifyRequester(message);\n    }\n''', 'transition reset')

text = controller.read_text()
text = text.replace('        stateTicks = tag.getInt("StateTicks");\n',
                    '        stateTicks = tag.getInt("StateTicks");\n        closeActionDone = tag.getBoolean("CloseActionDone");\n', 1)
text = text.replace('        tag.putInt("StateTicks", stateTicks);\n',
                    '        tag.putInt("StateTicks", stateTicks);\n        tag.putBoolean("CloseActionDone", closeActionDone);\n', 1)
controller.write_text(text)

logic = root / 'src/main/java/dev/afterfall/blockentity/AirlockLogic.java'
text = logic.read_text()
if 'import net.minecraft.world.phys.AABB;' not in text:
    text = text.replace('import net.minecraft.world.level.block.state.properties.DoubleBlockHalf;\n',
                        'import net.minecraft.world.level.block.state.properties.DoubleBlockHalf;\nimport net.minecraft.world.phys.AABB;\n', 1)
if 'isPlayerInDoorway(ServerPlayer player' not in text:
    marker = '    public static boolean isPlayerOnDoorSide(ServerPlayer player, BlockPos doorPos, Direction side) {'
    helper = '''    public static boolean isPlayerInDoorway(ServerPlayer player, BlockPos doorPos) {\n        if (player == null || doorPos == null) return false;\n        BlockPos lower = lowerDoorPos(player.level(), doorPos);\n        if (lower == null) lower = doorPos;\n        AABB doorway = new AABB(lower.getX(), lower.getY(), lower.getZ(),\n                lower.getX() + 1.0D, lower.getY() + 2.0D, lower.getZ() + 1.0D).inflate(0.08D);\n        return player.getBoundingBox().intersects(doorway);\n    }\n\n'''
    if marker not in text:
        raise RuntimeError('doorway helper marker not found')
    text = text.replace(marker, helper + marker, 1)
logic.write_text(text)
