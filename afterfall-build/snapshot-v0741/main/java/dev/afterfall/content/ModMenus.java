package dev.afterfall.content;

import dev.afterfall.Afterfall;
import dev.afterfall.menu.MachineMenu;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.inventory.MenuType;
import net.neoforged.neoforge.common.extensions.IMenuTypeExtension;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModMenus {
    public static final DeferredRegister<MenuType<?>> MENUS =
            DeferredRegister.create(Registries.MENU, Afterfall.MOD_ID);

    public static final DeferredHolder<MenuType<?>, MenuType<MachineMenu>> MACHINE = MENUS.register(
            "machine",
            () -> IMenuTypeExtension.create(MachineMenu::new)
    );

    private ModMenus() {}
}
