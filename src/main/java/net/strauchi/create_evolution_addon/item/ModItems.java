package net.strauchi.create_evolution_addon.item;

import com.simibubi.create.content.equipment.sandPaper.SandPaperItem;
import net.minecraft.world.item.Item;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;
import net.strauchi.create_evolution_addon.CreateEvolutionAddon;

public class ModItems {
    public static final DeferredRegister<Item> ITEMS =
            DeferredRegister.create(ForgeRegistries.ITEMS, CreateEvolutionAddon.MOD_ID);

    public static final RegistryObject<Item> GRAPHITE = ITEMS.register("graphite",
            () -> new Item(new Item.Properties()));
    public static final RegistryObject<Item> HEATED_DIAMOND = ITEMS.register("heated_diamond",
            () -> new Item(new Item.Properties()));
    public static final RegistryObject<Item> OBSIDIAN_SANDPAPER = ITEMS.register("obsidian_sandpaper",
            () -> new SandPaperItem(new Item.Properties().stacksTo(1).durability(4096)));

    public static void register(IEventBus eventBus) {
        ITEMS.register(eventBus);
    }

}
