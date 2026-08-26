package dev.afterfall.network;

import dev.afterfall.Afterfall;
import dev.afterfall.blockentity.PowerControlPanelBlockEntity;
import dev.afterfall.blockentity.SmartPowerTapBlockEntity;
import dev.afterfall.menu.PowerControlPanelMenu;
import dev.afterfall.menu.SmartPowerTapMenu;
import dev.afterfall.power.PowerTapManager;
import net.minecraft.core.BlockPos;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.network.PacketDistributor;
import net.neoforged.neoforge.network.event.RegisterPayloadHandlersEvent;
import net.neoforged.neoforge.network.handling.IPayloadContext;
import net.neoforged.neoforge.network.registration.PayloadRegistrar;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@EventBusSubscriber(modid = Afterfall.MOD_ID, bus = EventBusSubscriber.Bus.MOD)
public final class PowerNetworking {
    public static final int CMD_CRITICAL = 0;
    public static final int CMD_AUX = 1;
    public static final int CMD_ON = 2;
    public static final int CMD_OFF = 3;

    public record TapRenamePayload(BlockPos pos, String name) implements CustomPacketPayload {
        public static final Type<TapRenamePayload> TYPE = new Type<>(
                ResourceLocation.fromNamespaceAndPath(Afterfall.MOD_ID, "tap_rename"));
        public static final StreamCodec<RegistryFriendlyByteBuf, TapRenamePayload> STREAM_CODEC = StreamCodec.of(
                (buf, payload) -> {
                    buf.writeBlockPos(payload.pos());
                    buf.writeUtf(payload.name(), 32);
                },
                buf -> new TapRenamePayload(buf.readBlockPos(), buf.readUtf(32)));
        @Override public Type<? extends CustomPacketPayload> type() { return TYPE; }
    }

    public record PanelCommandPayload(BlockPos panelPos, UUID tapId, int command) implements CustomPacketPayload {
        public static final Type<PanelCommandPayload> TYPE = new Type<>(
                ResourceLocation.fromNamespaceAndPath(Afterfall.MOD_ID, "panel_tap_command"));
        public static final StreamCodec<RegistryFriendlyByteBuf, PanelCommandPayload> STREAM_CODEC = StreamCodec.of(
                (buf, payload) -> {
                    buf.writeBlockPos(payload.panelPos());
                    buf.writeUUID(payload.tapId());
                    buf.writeVarInt(payload.command());
                },
                buf -> new PanelCommandPayload(buf.readBlockPos(), buf.readUUID(), buf.readVarInt()));
        @Override public Type<? extends CustomPacketPayload> type() { return TYPE; }
    }

    public record TapEntry(UUID id, BlockPos pos, String name, int circuit, boolean relay,
                           int auxState, int energy, int maxEnergy, int inputPerTick, int outputPerTick,
                           boolean criticalDeficit, boolean managedByPanel) {}

    public record PanelSnapshotPayload(BlockPos panelPos, boolean criticalDeficit, boolean loadShedActive,
                                       boolean recoveryWaiting, int stableTicks,
                                       List<TapEntry> entries) implements CustomPacketPayload {
        public static final Type<PanelSnapshotPayload> TYPE = new Type<>(
                ResourceLocation.fromNamespaceAndPath(Afterfall.MOD_ID, "panel_snapshot"));
        public static final StreamCodec<RegistryFriendlyByteBuf, PanelSnapshotPayload> STREAM_CODEC = StreamCodec.of(
                PowerNetworking::writeSnapshot, PowerNetworking::readSnapshot);
        @Override public Type<? extends CustomPacketPayload> type() { return TYPE; }
    }

    @SubscribeEvent
    public static void register(RegisterPayloadHandlersEvent event) {
        PayloadRegistrar registrar = event.registrar("092");
        registrar.playToServer(TapRenamePayload.TYPE, TapRenamePayload.STREAM_CODEC, PowerNetworking::handleRename);
        registrar.playToServer(PanelCommandPayload.TYPE, PanelCommandPayload.STREAM_CODEC, PowerNetworking::handlePanelCommand);
        // Handler is common-code-only: IPayloadContext supplies the logical-side Player.
        registrar.playToClient(PanelSnapshotPayload.TYPE, PanelSnapshotPayload.STREAM_CODEC, PowerNetworking::handleSnapshot);
    }

    private static void handleRename(TapRenamePayload payload, IPayloadContext context) {
        Player logicalPlayer = context.player();
        if (!(logicalPlayer instanceof ServerPlayer player)) return;
        if (!(player.containerMenu instanceof SmartPowerTapMenu menu) || !menu.blockPos().equals(payload.pos())) return;
        if (player.blockPosition().distSqr(payload.pos()) > 64.0D) return;
        BlockEntity blockEntity = player.serverLevel().getBlockEntity(payload.pos());
        if (!(blockEntity instanceof SmartPowerTapBlockEntity tap)) return;
        String clean = payload.name().replace("§", "").replaceAll("[\\p{Cntrl}]", "").trim();
        tap.setDisplayName(clean);
    }

    private static void handlePanelCommand(PanelCommandPayload payload, IPayloadContext context) {
        Player logicalPlayer = context.player();
        if (!(logicalPlayer instanceof ServerPlayer player)) return;
        if (!(player.containerMenu instanceof PowerControlPanelMenu menu) || !menu.panelPos().equals(payload.panelPos())) return;
        if (player.blockPosition().distSqr(payload.panelPos()) > 64.0D) return;
        ServerLevel level = player.serverLevel();
        BlockEntity panelEntity = level.getBlockEntity(payload.panelPos());
        if (!(panelEntity instanceof PowerControlPanelBlockEntity panel)) return;
        SmartPowerTapBlockEntity tap = PowerTapManager.findById(level, payload.panelPos(),
                PowerControlPanelBlockEntity.CONTROL_RADIUS, payload.tapId());
        if (tap == null) return;
        switch (payload.command()) {
            case CMD_CRITICAL -> tap.setCircuitMode(SmartPowerTapBlockEntity.CircuitMode.CRITICAL);
            case CMD_AUX -> tap.setCircuitMode(SmartPowerTapBlockEntity.CircuitMode.AUX);
            case CMD_ON -> tap.setRelayEnabled(true);
            case CMD_OFF -> tap.setRelayEnabled(false);
            default -> { return; }
        }
        panel.coordinateNow(level);
        sendPanelSnapshot(player, payload.panelPos());
    }

    private static void handleSnapshot(PanelSnapshotPayload payload, IPayloadContext context) {
        Player player = context.player();
        if (player != null && player.containerMenu instanceof PowerControlPanelMenu menu) {
            menu.acceptSnapshot(payload);
        }
    }

    public static void sendPanelSnapshot(ServerPlayer player, BlockPos panelPos) {
        if (!(player.serverLevel().getBlockEntity(panelPos) instanceof PowerControlPanelBlockEntity panel)) return;
        ServerLevel level = player.serverLevel();
        long now = level.getGameTime();
        List<TapEntry> entries = new ArrayList<>();
        for (SmartPowerTapBlockEntity tap : PowerTapManager.find(level, panelPos,
                PowerControlPanelBlockEntity.CONTROL_RADIUS)) {
            entries.add(new TapEntry(
                    tap.tapId(), tap.getBlockPos().immutable(), tap.displayName(), tap.circuitMode().ordinal(),
                    tap.relayEnabled(), tap.auxState().ordinal(), tap.energyStored(), tap.maxEnergyStored(),
                    tap.recentInputPerTick(), tap.recentOutputPerTick(), tap.criticalDeficit(),
                    tap.managedBy(panelPos, now)));
            if (entries.size() >= 32) break;
        }
        PacketDistributor.sendToPlayer(player, new PanelSnapshotPayload(
                panelPos.immutable(), panel.criticalDeficit(), panel.loadShedActive(), panel.recoveryWaiting(),
                panel.criticalStableTicks(), List.copyOf(entries)));
    }

    private static void writeSnapshot(RegistryFriendlyByteBuf buf, PanelSnapshotPayload payload) {
        buf.writeBlockPos(payload.panelPos());
        buf.writeBoolean(payload.criticalDeficit());
        buf.writeBoolean(payload.loadShedActive());
        buf.writeBoolean(payload.recoveryWaiting());
        buf.writeVarInt(payload.stableTicks());
        int count = Math.min(32, payload.entries().size());
        buf.writeVarInt(count);
        for (int i = 0; i < count; i++) {
            TapEntry entry = payload.entries().get(i);
            buf.writeUUID(entry.id());
            buf.writeBlockPos(entry.pos());
            buf.writeUtf(entry.name(), 32);
            buf.writeVarInt(entry.circuit());
            buf.writeBoolean(entry.relay());
            buf.writeVarInt(entry.auxState());
            buf.writeVarInt(entry.energy());
            buf.writeVarInt(entry.maxEnergy());
            buf.writeVarInt(entry.inputPerTick());
            buf.writeVarInt(entry.outputPerTick());
            buf.writeBoolean(entry.criticalDeficit());
            buf.writeBoolean(entry.managedByPanel());
        }
    }

    private static PanelSnapshotPayload readSnapshot(RegistryFriendlyByteBuf buf) {
        BlockPos panelPos = buf.readBlockPos();
        boolean deficit = buf.readBoolean();
        boolean shed = buf.readBoolean();
        boolean recovery = buf.readBoolean();
        int stable = buf.readVarInt();
        int count = Math.max(0, Math.min(32, buf.readVarInt()));
        List<TapEntry> entries = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            entries.add(new TapEntry(buf.readUUID(), buf.readBlockPos(), buf.readUtf(32), buf.readVarInt(),
                    buf.readBoolean(), buf.readVarInt(), buf.readVarInt(), buf.readVarInt(),
                    buf.readVarInt(), buf.readVarInt(), buf.readBoolean(), buf.readBoolean()));
        }
        return new PanelSnapshotPayload(panelPos, deficit, shed, recovery, stable, List.copyOf(entries));
    }

    private PowerNetworking() {}
}
