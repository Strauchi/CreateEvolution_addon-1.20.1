package dev.afterfall.content;

import dev.afterfall.Afterfall;
import dev.afterfall.menu.MachineMenu;
import dev.afterfall.menu.SmartPowerTapMenu;
import dev.afterfall.menu.PowerControlPanelMenu;
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
    public static final DeferredHolder<MenuType<?>, MenuType<SmartPowerTapMenu>> SMART_POWER_TAP = MENUS.register(
            "smart_power_tap", () -> IMenuTypeExtension.create(SmartPowerTapMenu::new));
    public static final DeferredHolder<MenuType<?>, MenuType<PowerControlPanelMenu>> POWER_CONTROL_PANEL = MENUS.register(
            "power_control_panel", () -> IMenuTypeExtension.create(PowerControlPanelMenu::new));

    private ModMenus() {}
}
