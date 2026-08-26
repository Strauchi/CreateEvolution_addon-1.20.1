package dev.afterfall.content;

import com.mojang.serialization.Codec;
import dev.afterfall.Afterfall;
import net.neoforged.neoforge.attachment.AttachmentType;
import net.neoforged.neoforge.registries.DeferredRegister;
import net.neoforged.neoforge.registries.NeoForgeRegistries;
import java.util.function.Supplier;

public final class ModAttachments {
    public static final DeferredRegister<AttachmentType<?>> ATTACHMENTS =
            DeferredRegister.create(NeoForgeRegistries.ATTACHMENT_TYPES, Afterfall.MOD_ID);

    public static final Supplier<AttachmentType<Double>> RADIATION_DOSE = ATTACHMENTS.register(
            "radiation_dose",
            () -> AttachmentType.builder(() -> 0.0D).serialize(Codec.DOUBLE).copyOnDeath().build()
    );

    public static final Supplier<AttachmentType<Double>> CONTAMINATION = ATTACHMENTS.register(
            "contamination",
            () -> AttachmentType.builder(() -> 0.0D).serialize(Codec.DOUBLE).copyOnDeath().build()
    );

    private ModAttachments() {}
}
