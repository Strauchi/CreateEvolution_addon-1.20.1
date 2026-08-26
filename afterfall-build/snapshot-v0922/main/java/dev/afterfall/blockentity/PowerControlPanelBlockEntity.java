package dev.afterfall.blockentity;

import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.power.PowerTapManager;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.List;

/**
 * SCADA-style coordinator. It never transports FE; it only observes Smart Power Taps
 * and applies safe load-shedding/recovery policy within a local radius.
 */
public final class PowerControlPanelBlockEntity extends BlockEntity {
    public static final int CONTROL_RADIUS = 48;
    public static final int UPDATE_INTERVAL_TICKS = 10;
    public static final int CRITICAL_STABLE_REQUIRED_TICKS = 100;

    private boolean criticalDeficit;
    private boolean loadShedActive;
    private boolean recoveryWaiting;
    private int criticalStableTicks;

    public PowerControlPanelBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.POWER_CONTROL_PANEL.get(), pos, state);
    }

    public boolean criticalDeficit() { return criticalDeficit; }
    public boolean loadShedActive() { return loadShedActive; }
    public boolean recoveryWaiting() { return recoveryWaiting; }
    public int criticalStableTicks() { return criticalStableTicks; }

    public static void serverTick(Level level, BlockPos pos, BlockState state, PowerControlPanelBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel)) return;
        if (serverLevel.getGameTime() % UPDATE_INTERVAL_TICKS != 0L) return;
        be.coordinateNow(serverLevel);
    }

    public void coordinateNow(ServerLevel level) {
        List<SmartPowerTapBlockEntity> taps = PowerTapManager.find(level, worldPosition, CONTROL_RADIUS);
        boolean deficitNow = false;
        for (SmartPowerTapBlockEntity tap : taps) {
            if (tap.circuitMode() == SmartPowerTapBlockEntity.CircuitMode.CRITICAL && tap.criticalDeficit()) {
                deficitNow = true;
                break;
            }
        }

        criticalDeficit = deficitNow;
        if (deficitNow) {
            loadShedActive = true;
            recoveryWaiting = true;
            criticalStableTicks = 0;
        } else if (recoveryWaiting) {
            criticalStableTicks = Math.min(CRITICAL_STABLE_REQUIRED_TICKS,
                    criticalStableTicks + UPDATE_INTERVAL_TICKS);
            if (criticalStableTicks >= CRITICAL_STABLE_REQUIRED_TICKS) recoveryWaiting = false;
        }

        long now = level.getGameTime();
        if (criticalDeficit || recoveryWaiting) {
            for (SmartPowerTapBlockEntity tap : taps) {
                tap.applyCoordinator(worldPosition,
                        tap.circuitMode() == SmartPowerTapBlockEntity.CircuitMode.AUX, now);
            }
            setChanged();
            return;
        }

        if (loadShedActive) {
            // Restore one AUX circuit at a time. This prevents the recharge surge itself
            // from starving CRITICAL loads. Future priority tiers can drive this ordering.
            SmartPowerTapBlockEntity granted = null;
            boolean pending = false;
            for (SmartPowerTapBlockEntity tap : taps) {
                if (tap.circuitMode() != SmartPowerTapBlockEntity.CircuitMode.AUX) {
                    tap.applyCoordinator(worldPosition, false, now);
                    continue;
                }
                if (tap.auxState() == SmartPowerTapBlockEntity.AuxState.ACTIVE) {
                    tap.applyCoordinator(worldPosition, false, now);
                    continue;
                }
                pending = true;
                if (granted == null) {
                    granted = tap;
                    tap.applyCoordinator(worldPosition, false, now);
                } else {
                    tap.applyCoordinator(worldPosition, true, now);
                }
            }
            if (!pending) loadShedActive = false;
        } else {
            for (SmartPowerTapBlockEntity tap : taps) tap.applyCoordinator(worldPosition, false, now);
        }
        setChanged();
    }
}
