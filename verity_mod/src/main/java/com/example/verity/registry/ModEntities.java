package com.example.verity.registry;

import com.example.verity.VerityMod;
import com.example.verity.entity.VerityEntity;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;

/**
 * Класс регистрации сущностей для Fabric.
 * Использует встроенный реестр Minecraft (BuiltInRegistries).
 */
public class ModEntities {
    // Храним ссылку на зарегистрированный тип нашей сущности
    public static EntityType<VerityEntity> VERITY;

    /**
     * Регистрирует все сущности мода в ванильном реестре.
     */
    public static void registerEntities() {
        VERITY = Registry.register(
                BuiltInRegistries.ENTITY_TYPE,
                ResourceLocation.fromNamespaceAndPath(VerityMod.MODID, "verity"),
                EntityType.Builder.of(VerityEntity::new, MobCategory.CREATURE)
                        .sized(0.6F, 0.6F)         // Размер хитбокса
                        .clientTrackingRange(10)   // Дистанция видимости
                        .fireImmune()              // Огнеупорность
                        .build("verity")
        );
    }
}
