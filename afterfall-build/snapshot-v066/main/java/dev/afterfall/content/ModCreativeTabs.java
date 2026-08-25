package dev.afterfall.content;

import dev.afterfall.Afterfall;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.CreativeModeTab;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModCreativeTabs {
    public static final DeferredRegister<CreativeModeTab> TABS = DeferredRegister.create(Registries.CREATIVE_MODE_TAB, Afterfall.MOD_ID);

    public static final DeferredHolder<CreativeModeTab, CreativeModeTab> AFTERFALL_TAB = TABS.register(
            "afterfall",
            () -> CreativeModeTab.builder()
                    .title(Component.translatable("itemGroup.afterfall"))
                    .icon(() -> ModItems.GEIGER_COUNTER.get().getDefaultInstance())
                    .displayItems((parameters, output) -> {
                        output.accept(ModItems.GEIGER_COUNTER.get());
                        output.accept(ModItems.RADAWAY.get());
                        output.accept(ModItems.DECON_KIT.get());
                        output.accept(ModItems.LEAD_COMPOSITE_BLOCK.get());
                        output.accept(ModItems.RADIOACTIVE_WASTE_BLOCK.get());
                        output.accept(ModItems.ASH_BLOCK.get());
                        output.accept(ModItems.AIR_FILTER_UNIT.get());
                        output.accept(ModItems.AIR_INTAKE_UNIT.get());
                        output.accept(ModItems.AIRLOCK_CONTROLLER.get());
                        output.accept(ModItems.AIRLOCK_CALL_PANEL.get());
                        output.accept(ModItems.PREFILTER_CARTRIDGE.get());
                        output.accept(ModItems.HEPA_FILTER_CARTRIDGE.get());
                        output.accept(ModItems.RAD_FILTER_CARTRIDGE.get());
                        output.accept(ModItems.EMERGENCY_GENERATOR.get());
                        output.accept(ModItems.SEALED_AIRLOCK_DOOR.get());
                        output.accept(ModItems.HEAVY_BLAST_DOOR.get());
                    }).build()
    );

    private ModCreativeTabs() {}
}
