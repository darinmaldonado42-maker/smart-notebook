package com.example.verity;

import com.example.verity.entity.VerityEntity;
import com.example.verity.event.VerityEventHandler;
import com.example.verity.registry.ModEntities;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.object.builder.v1.entity.FabricDefaultAttributeRegistry;

/**
 * Точка входа для общего (серверного/клиентского) кода на Fabric.
 * Реализует интерфейс ModInitializer.
 */
public class VerityMod implements ModInitializer {
    public static final String MODID = "verity";

    @Override
    public void onInitialize() {
        // 1. Регистрация типов сущностей в реестре
        ModEntities.registerEntities();

        // 2. Регистрация базовых характеристик (атрибутов) нашей сущности
        FabricDefaultAttributeRegistry.register(ModEntities.VERITY, VerityEntity.createAttributes());

        // 3. Регистрация игровых событий (слушателей Fabric API)
        VerityEventHandler.registerEvents();
    }
}
