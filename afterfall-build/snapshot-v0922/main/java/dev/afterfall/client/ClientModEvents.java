package dev.afterfall.client;

import dev.afterfall.Afterfall;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModMenus;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.EntityRenderersEvent;
import net.neoforged.neoforge.client.event.RegisterMenuScreensEvent;

@EventBusSubscriber(modid = Afterfall.MOD_ID, bus = EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
public final class ClientModEvents {
    @SubscribeEvent
    public static void registerScreens(RegisterMenuScreensEvent event) {
        event.register(ModMenus.MACHINE.get(), MachineScreen::new);
        event.register(ModMenus.SMART_POWER_TAP.get(), SmartPowerTapScreen::new);
        event.register(ModMenus.POWER_CONTROL_PANEL.get(), PowerControlPanelScreen::new);
    }

    @SubscribeEvent
    public static void registerRenderers(EntityRenderersEvent.RegisterRenderers event) {
        event.registerBlockEntityRenderer(ModBlockEntities.HEAVY_BLAST_DOOR.get(), HeavyBlastDoorRenderer::new);
    }

    private ClientModEvents() {}
}
