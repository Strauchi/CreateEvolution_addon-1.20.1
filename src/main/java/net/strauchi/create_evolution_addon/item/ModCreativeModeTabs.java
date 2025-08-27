package net.strauchi.create_evolution_addon.item;

import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.ItemStack;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.RegistryObject;
import net.strauchi.create_evolution_addon.CreateEvolutionAddon;

public class ModCreativeModeTabs {
    public static final DeferredRegister<CreativeModeTab> CREATIVE_MODE_TABS =
            DeferredRegister.create(Registries.CREATIVE_MODE_TAB, CreateEvolutionAddon.MOD_ID);

    public static final RegistryObject<CreativeModeTab> TEST_TAB =
            CREATIVE_MODE_TABS.register("create_evolution_addon_tab", () ->
                    CreativeModeTab.builder()
                            .title(Component.translatable("itemGroup.create_evolution_addon.create_evolution_addon_tab"))
                            .icon(() -> new ItemStack(ModItems.HEATED_DIAMOND.get()))
                            .displayItems((params, output) -> {
                                output.accept(ModItems.HEATED_DIAMOND.get());
                                output.accept(ModItems.GRAPHITE.get());
                                output.accept(ModItems.OBSIDIAN_SANDPAPER.get());
                            })
                            .build()
            );

    public static void register(IEventBus eventBus) {
        CREATIVE_MODE_TABS.register(eventBus);
    }
}
