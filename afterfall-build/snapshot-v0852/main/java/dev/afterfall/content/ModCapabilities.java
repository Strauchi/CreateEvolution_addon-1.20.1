package dev.afterfall.content;

import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.capabilities.RegisterCapabilitiesEvent;

public final class ModCapabilities {
    public static void register(RegisterCapabilitiesEvent event) {
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.AIR_FILTER.get(),
                (be, side) -> be.energyStorage());
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.AIR_INTAKE.get(),
                (be, side) -> be.energyStorage());
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.CO2_SCRUBBER.get(),
                (be, side) -> be.energyStorage());
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.AIRLOCK_CONTROLLER.get(),
                (be, side) -> be.energyStorage());
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.EMERGENCY_GENERATOR.get(),
                (be, side) -> be.energyStorage());
        event.registerBlockEntity(Capabilities.EnergyStorage.BLOCK, ModBlockEntities.VENTILATION_FAN.get(),
                (be, side) -> be.energyStorage());
    }

    private ModCapabilities() {}
}
