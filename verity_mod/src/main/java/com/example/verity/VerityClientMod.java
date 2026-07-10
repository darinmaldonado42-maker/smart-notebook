package com.example.verity;

import com.example.verity.client.VerityModel;
import com.example.verity.client.VerityRenderer;
import com.example.verity.registry.ModEntities;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.rendering.v1.EntityModelLayerRegistry;
import net.fabricmc.fabric.api.client.rendering.v1.EntityRendererRegistry;

/**
 * Точка входа для клиентской части мода на Fabric.
 * Реализует интерфейс ClientModInitializer.
 */
public class VerityClientMod implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        // 1. Привязка рендерера к сущности на стороне клиента
        EntityRendererRegistry.register(ModEntities.VERITY, VerityRenderer::new);

        // 2. Регистрация слоев 3D-модели для запекания сетки
        EntityModelLayerRegistry.registerModelLayer(VerityModel.VERITY_LAYER, VerityModel::createBodyLayer);
    }
}
