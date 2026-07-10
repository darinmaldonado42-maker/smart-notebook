package com.example.verity.client;

import com.example.verity.VerityMod;
import com.example.verity.entity.VerityEntity;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.client.renderer.entity.MobRenderer;
import net.minecraft.resources.ResourceLocation;
import org.jetbrains.annotations.Nullable;

/**
 * Рендерер сущности Verity.
 * Отвечает за отрисовку модели в мире, смену текстур на основе уровня доверия
 * и создание постоянного эффекта свечения (Glow).
 */
public class VerityRenderer extends MobRenderer<VerityEntity, VerityModel> {
    
    // Текстуры для разных фаз состояния
    private static final ResourceLocation FRIENDLY_TEXTURE = ResourceLocation.fromNamespaceAndPath(VerityMod.MODID, "textures/entity/verity_friendly.png");
    private static final ResourceLocation HORROR_TEXTURE = ResourceLocation.fromNamespaceAndPath(VerityMod.MODID, "textures/entity/verity_horror.png");

    public VerityRenderer(EntityRendererProvider.Context context) {
        // Привязываем модель и устанавливаем радиус тени под шаром в 0.3 блока
        super(context, new VerityModel(context.bakeLayer(VerityModel.VERITY_LAYER)), 0.3F);
    }

    /**
     * Возвращает текстуру сущности в зависимости от её состояния (уровня доверия).
     */
    @Override
    public ResourceLocation getTextureLocation(VerityEntity entity) {
        return entity.getTrustLevel() < 0 ? HORROR_TEXTURE : FRIENDLY_TEXTURE;
    }

    /**
     * Переопределение типа рендеринга.
     * Используем RenderType.eyes(), который отключает стандартные тени Minecraft для текстуры
     * и заставляет шар светиться в темноте (как глаза Эндермена), имитируя чистую парящую энергию.
     */
    @Nullable
    @Override
    protected RenderType getRenderType(VerityEntity entity, boolean bodyVisible, boolean translucent, boolean glowing) {
        ResourceLocation texture = this.getTextureLocation(entity);
        // Делаем текстуру полностью самосветящейся (эмиссионной)
        return RenderType.eyes(texture);
    }
}
