package net.strauchi.testmod.Item;

import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.ItemStack;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.RegistryObject;
import net.strauchi.testmod.TestMod;

public class ModCreateModeTabs {
    public static final DeferredRegister<CreativeModeTab> CREATIVE_MODE_TABS =
            DeferredRegister.create(Registries.CREATIVE_MODE_TAB, TestMod.MOD_ID);

    public static final RegistryObject<CreativeModeTab> TEST_TAB = CREATIVE_MODE_TABS.register("testmod_tab",
            () -> CreativeModeTab.builder().icon(() -> new ItemStack(ModItem.Heated_Diamond.get()))
                    .title(Component.translatable("creativetab.testmod_tab"))
                    .displayItems((itemDisplayParameters, output) -> {
                        output.accept(ModItem.Heated_Diamond.get());
                        output.accept(ModItem.Graphite.get());
                    })
                    .build());

    public static void register(IEventBus eventBus) {
        CREATIVE_MODE_TABS.register(eventBus);
    }


}
