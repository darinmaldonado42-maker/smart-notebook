package com.example.verity.client;

import com.example.verity.entity.VerityEntity;
import net.minecraft.client.model.HierarchicalModel;
import com.example.verity.VerityMod;
import net.minecraft.client.model.geom.ModelLayerLocation;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.client.model.geom.PartPose;
import net.minecraft.client.model.geom.builders.CubeListBuilder;
import net.minecraft.client.model.geom.builders.LayerDefinition;
import net.minecraft.client.model.geom.builders.MeshDefinition;
import net.minecraft.client.model.geom.builders.PartDefinition;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.util.Mth;

/**
 * 3D-модель светящегося шара Verity.
 * Наследуется от HierarchicalModel для удобного управления частями модели.
 */
public class VerityModel extends HierarchicalModel<VerityEntity> {
    // Идентификатор слоя модели для рендеринга на клиенте
    public static final ModelLayerLocation VERITY_LAYER = new ModelLayerLocation(
            ResourceLocation.fromNamespaceAndPath(VerityMod.MODID, "verity"), "main"
    );

    private final ModelPart root;
    private final ModelPart orb;

    public VerityModel(ModelPart root) {
        this.root = root;
        this.orb = root.getChild("orb");
    }

    /**
     * Создает структуру модели для рендеринга (описание полигонов и текстурных координат).
     */
    public static LayerDefinition createBodyLayer() {
        MeshDefinition meshdefinition = new MeshDefinition();
        PartDefinition partdefinition = meshdefinition.getRoot();

        // Создаем центральный кубический элемент (orb) размером 8х8х8 пикселей.
        // Смещаем его по умолчанию на высоту 16 пикселей от пола (центр модели).
        partdefinition.addOrReplaceChild("orb", CubeListBuilder.create()
                .texOffs(0, 0)
                .addBox(-4.0F, -4.0F, -4.0F, 8.0F, 8.0F, 8.0F),
                PartPose.offset(0.0F, 16.0F, 0.0F));

        return LayerDefinition.create(meshdefinition, 32, 32);
    }

    @Override
    public ModelPart root() {
        return this.root;
    }

    /**
     * Логика анимации модели. Вызывается каждый кадр рендеринга на клиенте.
     * Отвечает за плавное покачивание шара в воздухе.
     */
    @Override
    public void setupAnim(VerityEntity entity, float limbSwing, float limbSwingAmount, float ageInTicks, float netHeadYaw, float headPitch) {
        // Сбрасываем вращения
        this.orb.xRot = 0.0F;
        this.orb.yRot = 0.0F;
        this.orb.zRot = 0.0F;

        // Эффект плавного покачивания по синусоиде:
        // Используем ageInTicks (который учитывает partialTicks для плавности кадров)
        this.orb.y = 16.0F + Mth.sin(ageInTicks * 0.08F) * 1.5F;

        // Плавное вращение шара вокруг осей для эффекта энергетической левитации
        this.orb.yRot = ageInTicks * 0.05F;
        this.orb.xRot = ageInTicks * 0.02F;
    }
}
