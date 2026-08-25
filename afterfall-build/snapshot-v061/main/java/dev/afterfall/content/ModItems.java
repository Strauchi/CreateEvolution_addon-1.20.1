package dev.afterfall.content;

import dev.afterfall.Afterfall;
import dev.afterfall.item.DeconKitItem;
import dev.afterfall.item.GeigerCounterItem;
import dev.afterfall.item.RadAwayItem;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.DoubleHighBlockItem;
import net.neoforged.neoforge.registries.DeferredItem;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModItems {
    public static final DeferredRegister.Items ITEMS = DeferredRegister.createItems(Afterfall.MOD_ID);

    public static final DeferredItem<BlockItem> LEAD_COMPOSITE_BLOCK = ITEMS.registerSimpleBlockItem("lead_composite_block", ModBlocks.LEAD_COMPOSITE_BLOCK);
    public static final DeferredItem<BlockItem> RADIOACTIVE_WASTE_BLOCK = ITEMS.registerSimpleBlockItem("radioactive_waste_block", ModBlocks.RADIOACTIVE_WASTE_BLOCK);
    public static final DeferredItem<BlockItem> ASH_BLOCK = ITEMS.registerSimpleBlockItem("ash_block", ModBlocks.ASH_BLOCK);
    public static final DeferredItem<BlockItem> AIR_FILTER_UNIT = ITEMS.registerSimpleBlockItem("air_filter_unit", ModBlocks.AIR_FILTER_UNIT);
    public static final DeferredItem<BlockItem> AIR_INTAKE_UNIT = ITEMS.registerSimpleBlockItem("air_intake_unit", ModBlocks.AIR_INTAKE_UNIT);
    public static final DeferredItem<BlockItem> AIRLOCK_CONTROLLER = ITEMS.registerSimpleBlockItem("airlock_controller", ModBlocks.AIRLOCK_CONTROLLER);
    public static final DeferredItem<BlockItem> AIRLOCK_CALL_PANEL = ITEMS.registerSimpleBlockItem("airlock_call_panel", ModBlocks.AIRLOCK_CALL_PANEL);
    public static final DeferredItem<BlockItem> EMERGENCY_GENERATOR = ITEMS.registerSimpleBlockItem("emergency_generator", ModBlocks.EMERGENCY_GENERATOR);
    public static final DeferredItem<DoubleHighBlockItem> SEALED_AIRLOCK_DOOR = ITEMS.register(
            "sealed_airlock_door", () -> new DoubleHighBlockItem(ModBlocks.SEALED_AIRLOCK_DOOR.get(), new Item.Properties()));
    public static final DeferredItem<DoubleHighBlockItem> HEAVY_BLAST_DOOR = ITEMS.register(
            "heavy_blast_door", () -> new DoubleHighBlockItem(ModBlocks.HEAVY_BLAST_DOOR.get(), new Item.Properties()));

    public static final DeferredItem<GeigerCounterItem> GEIGER_COUNTER = ITEMS.register("geiger_counter", () -> new GeigerCounterItem(new Item.Properties().stacksTo(1)));
    public static final DeferredItem<RadAwayItem> RADAWAY = ITEMS.register("radaway", () -> new RadAwayItem(new Item.Properties().stacksTo(8)));
    public static final DeferredItem<DeconKitItem> DECON_KIT = ITEMS.register("decon_kit", () -> new DeconKitItem(new Item.Properties().stacksTo(8)));
    public static final DeferredItem<Item> PREFILTER_CARTRIDGE = ITEMS.register("prefilter_cartridge", () -> new Item(new Item.Properties().stacksTo(16)));
    public static final DeferredItem<Item> HEPA_FILTER_CARTRIDGE = ITEMS.register("hepa_filter_cartridge", () -> new Item(new Item.Properties().stacksTo(16)));
    public static final DeferredItem<Item> RAD_FILTER_CARTRIDGE = ITEMS.register("rad_filter_cartridge", () -> new Item(new Item.Properties().stacksTo(16)));

    private ModItems() {}
}
