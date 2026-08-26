from pathlib import Path

ROOT = Path("Afterfall")
JAVA = ROOT / "src/main/java/dev/afterfall"


def write(rel: str, content: str) -> None:
    path = JAVA / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


props = ROOT / "gradle.properties"
text = props.read_text(encoding="utf-8")
if "mod_version=0.9.1.1" not in text:
    raise SystemExit("Expected exact 0.9.1.1 source snapshot")
props.write_text(text.replace("mod_version=0.9.1.1", "mod_version=0.9.1.2"), encoding="utf-8")


write("block/SealedPowerFeedthroughBlock.java", r'''package dev.afterfall.block;

import dev.afterfall.blockentity.SealedPowerFeedthroughBlockEntity;
import dev.afterfall.content.ModBlockEntities;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.EntityBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.BlockEntityTicker;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import org.jetbrains.annotations.Nullable;

/**
 * Airtight FE wall penetration.
 * The two opposite faces on the FACING axis are both FE input/output terminals.
 * Placement follows the player's look direction, matching other directional
 * Afterfall machines rather than the clicked surface.
 */
public final class SealedPowerFeedthroughBlock extends Block implements EntityBlock {
    public static final DirectionProperty FACING = BlockStateProperties.FACING;

    public SealedPowerFeedthroughBlock(Properties properties) {
        super(properties);
        registerDefaultState(stateDefinition.any().setValue(FACING, Direction.NORTH));
    }

    @Override
    public BlockState getStateForPlacement(BlockPlaceContext context) {
        return defaultBlockState().setValue(FACING, context.getNearestLookingDirection().getOpposite());
    }

    @Override
    protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
        builder.add(FACING);
    }

    @Override
    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {
        return new SealedPowerFeedthroughBlockEntity(pos, state);
    }

    @Override
    @Nullable
    public <T extends BlockEntity> BlockEntityTicker<T> getTicker(Level level, BlockState state, BlockEntityType<T> type) {
        return level.isClientSide ? null
                : createTicker(type, ModBlockEntities.SEALED_POWER_FEEDTHROUGH.get(), SealedPowerFeedthroughBlockEntity::serverTick);
    }

    @SuppressWarnings("unchecked")
    private static <E extends BlockEntity, T extends BlockEntity> BlockEntityTicker<T> createTicker(
            BlockEntityType<T> actual, BlockEntityType<E> expected, BlockEntityTicker<? super E> ticker) {
        return actual == expected ? (BlockEntityTicker<T>) ticker : null;
    }
}
''')


write("blockentity/SealedPowerFeedthroughBlockEntity.java", r'''package dev.afterfall.blockentity;

import dev.afterfall.block.SealedPowerFeedthroughBlock;
import dev.afterfall.content.ModBlockEntities;
import dev.afterfall.content.ModBlocks;
import dev.afterfall.machine.MachineEnergyStorage;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.energy.IEnergyStorage;
import org.jetbrains.annotations.Nullable;

/**
 * Airtight, genuinely bidirectional FE bridge.
 *
 * 0.9.1/0.9.1.1 exposed a shared passive buffer on both terminals. That made
 * the feedthrough look like a storage endpoint to two separate cable networks,
 * but nothing actually relayed energy from one network to the other.
 *
 * 0.9.1.2 uses two directional transit buffers. Energy received on the FACING
 * terminal can only leave through the opposite terminal, and vice versa. Each
 * server tick the feedthrough actively pushes both transit buffers into the
 * corresponding opposite neighbor. Cable mods can therefore either push into
 * the feedthrough or pull from its other terminal; no second input/output block
 * is required and energy cannot immediately bounce back to its source side.
 */
public final class SealedPowerFeedthroughBlockEntity extends BlockEntity {
    public static final int BUFFER_CAPACITY_PER_DIRECTION = 8_000;
    public static final int MAX_TRANSFER_PER_TICK = 8_000;

    /** Energy that entered through FACING and is travelling to FACING.opposite(). */
    private final MachineEnergyStorage facingToOpposite = new MachineEnergyStorage(
            BUFFER_CAPACITY_PER_DIRECTION, MAX_TRANSFER_PER_TICK, MAX_TRANSFER_PER_TICK, this::setChanged);

    /** Energy that entered through FACING.opposite() and is travelling to FACING. */
    private final MachineEnergyStorage oppositeToFacing = new MachineEnergyStorage(
            BUFFER_CAPACITY_PER_DIRECTION, MAX_TRANSFER_PER_TICK, MAX_TRANSFER_PER_TICK, this::setChanged);

    private final IEnergyStorage facingPort = new TerminalPort(true);
    private final IEnergyStorage oppositePort = new TerminalPort(false);

    public SealedPowerFeedthroughBlockEntity(BlockPos pos, BlockState state) {
        super(ModBlockEntities.SEALED_POWER_FEEDTHROUGH.get(), pos, state);
    }

    /** Total FE currently in transit in both directions. */
    public int bufferedEnergy() {
        return facingToOpposite.getEnergyStored() + oppositeToFacing.getEnergyStored();
    }

    /**
     * Only the two axial faces expose FE. Both are simultaneously input/output.
     * The four side faces remain electrically isolated.
     */
    @Nullable
    public IEnergyStorage energyStorage(@Nullable Direction side) {
        if (side == null) return null;
        BlockState state = getBlockState();
        if (!state.is(ModBlocks.SEALED_POWER_FEEDTHROUGH.get())
                || !state.hasProperty(SealedPowerFeedthroughBlock.FACING)) return null;

        Direction facing = state.getValue(SealedPowerFeedthroughBlock.FACING);
        if (side == facing) return facingPort;
        if (side == facing.getOpposite()) return oppositePort;
        return null;
    }

    /**
     * Active relay stage. Anything inserted on one terminal is offered only to
     * the opposite adjacent FE endpoint. This is the part the old passive-buffer
     * implementation was missing.
     */
    public static void serverTick(Level level, BlockPos pos, BlockState state, SealedPowerFeedthroughBlockEntity be) {
        if (!(level instanceof ServerLevel serverLevel)) return;
        if (!state.is(ModBlocks.SEALED_POWER_FEEDTHROUGH.get())
                || !state.hasProperty(SealedPowerFeedthroughBlock.FACING)) return;

        Direction facing = state.getValue(SealedPowerFeedthroughBlock.FACING);

        // FE received on FACING exits through the opposite physical terminal.
        be.pushTransit(serverLevel, pos, facing.getOpposite(), be.facingToOpposite);

        // FE received on the opposite terminal exits through FACING.
        be.pushTransit(serverLevel, pos, facing, be.oppositeToFacing);
    }

    private void pushTransit(ServerLevel level, BlockPos pos, Direction outputDirection, MachineEnergyStorage transit) {
        int stored = transit.getEnergyStored();
        if (stored <= 0) return;

        BlockPos targetPos = pos.relative(outputDirection);
        IEnergyStorage target = level.getCapability(
                Capabilities.EnergyStorage.BLOCK,
                targetPos,
                outputDirection.getOpposite());
        if (target == null) return;

        int offer = Math.min(MAX_TRANSFER_PER_TICK, stored);
        int acceptedSimulation = target.receiveEnergy(offer, true);
        if (acceptedSimulation <= 0) return;

        int extracted = transit.extractEnergy(acceptedSimulation, false);
        if (extracted <= 0) return;

        int accepted = target.receiveEnergy(extracted, false);
        if (accepted < extracted) {
            // Never destroy FE if the destination changed between simulation and commit.
            transit.addEnergyInternal(extracted - Math.max(0, accepted));
        }
    }

    /**
     * A terminal is deliberately asymmetric internally while remaining fully
     * bidirectional externally: receive() places FE into the transit buffer going
     * away from this side; extract() exposes only FE that arrived from the other side.
     */
    private final class TerminalPort implements IEnergyStorage {
        private final boolean isFacingTerminal;

        private TerminalPort(boolean isFacingTerminal) {
            this.isFacingTerminal = isFacingTerminal;
        }

        private MachineEnergyStorage inboundTransit() {
            return isFacingTerminal ? facingToOpposite : oppositeToFacing;
        }

        private MachineEnergyStorage outboundTransit() {
            return isFacingTerminal ? oppositeToFacing : facingToOpposite;
        }

        @Override
        public int receiveEnergy(int maxReceive, boolean simulate) {
            return inboundTransit().receiveEnergy(maxReceive, simulate);
        }

        @Override
        public int extractEnergy(int maxExtract, boolean simulate) {
            return outboundTransit().extractEnergy(maxExtract, simulate);
        }

        @Override
        public int getEnergyStored() {
            return outboundTransit().getEnergyStored();
        }

        @Override
        public int getMaxEnergyStored() {
            return BUFFER_CAPACITY_PER_DIRECTION;
        }

        @Override
        public boolean canExtract() {
            return outboundTransit().getEnergyStored() > 0;
        }

        @Override
        public boolean canReceive() {
            return inboundTransit().getEnergyStored() < BUFFER_CAPACITY_PER_DIRECTION;
        }
    }

    @Override
    public void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);

        if (tag.contains("FacingToOpposite") || tag.contains("OppositeToFacing")) {
            facingToOpposite.setEnergyStored(tag.getInt("FacingToOpposite"));
            oppositeToFacing.setEnergyStored(tag.getInt("OppositeToFacing"));
        } else {
            // Preserve any FE left in the old 0.9.1.x single-buffer implementation.
            facingToOpposite.setEnergyStored(tag.getInt("Energy"));
            oppositeToFacing.setEnergyStored(0);
        }
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        tag.putInt("FacingToOpposite", facingToOpposite.getEnergyStored());
        tag.putInt("OppositeToFacing", oppositeToFacing.getEnergyStored());
    }
}
''')

print("Applied Afterfall 0.9.1.2 active bidirectional sealed power feedthrough bridge")
