package dev.afterfall.block;

import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.block.state.properties.BlockSetType;

/**
 * Sealed electrically-operated door used by the bunker systems.
 * Using the iron BlockSetType keeps vanilla redstone/iron-door semantics while
 * allowing Afterfall to give the door its own shielding and controller logic.
 */
public final class AfterfallDoorBlock extends DoorBlock {
    public AfterfallDoorBlock(BlockBehaviour.Properties properties) {
        super(BlockSetType.IRON, properties);
    }
}
