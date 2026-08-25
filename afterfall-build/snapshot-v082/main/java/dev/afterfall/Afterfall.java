package dev.afterfall;

import com.mojang.logging.LogUtils;
import dev.afterfall.command.AfterfallCommands;
import dev.afterfall.content.ModAttachments;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModCreativeTabs;
import dev.afterfall.content.ModCapabilities;
import dev.afterfall.content.ModItems;
import dev.afterfall.content.ModMenus;
import dev.afterfall.event.CommonEvents;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import org.slf4j.Logger;

@Mod(Afterfall.MOD_ID)
public final class Afterfall {
    public static final String MOD_ID = "afterfall";
    public static final Logger LOGGER = LogUtils.getLogger();

    public Afterfall(IEventBus modBus, ModContainer container) {
        ModBlocks.BLOCKS.register(modBus);
        ModBlockEntities.BLOCK_ENTITY_TYPES.register(modBus);
        ModItems.ITEMS.register(modBus);
        ModMenus.MENUS.register(modBus);
        ModAttachments.ATTACHMENTS.register(modBus);
        ModCreativeTabs.TABS.register(modBus);
        modBus.addListener(ModCapabilities::register);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onServerTick);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onPlayerTick);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onRightClickBlock);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onBlockBreak);
        NeoForge.EVENT_BUS.addListener(CommonEvents::onBlockPlace);
        NeoForge.EVENT_BUS.addListener(AfterfallCommands::register);
        LOGGER.info("Afterfall 0.8.2 initialized");
    }
}
