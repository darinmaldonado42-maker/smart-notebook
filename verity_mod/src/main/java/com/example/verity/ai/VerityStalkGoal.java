package com.example.verity.ai;

import com.example.verity.entity.VerityEntity;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.entity.ai.goal.Goal;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;

import java.util.EnumSet;

/**
 * ИИ-цель для хоррор-фазы "Саботажник" (Доверие < 0).
 * Заставляет моба держать дистанцию, прятаться за спиной игрока и мгновенно
 * исчезать/телепортироваться, если игрок поворачивается и смотрит прямо на него.
 */
public class VerityStalkGoal extends Goal {
    private final VerityEntity verity;
    private Player stalkTarget;
    private int teleportCooldown = 0;

    public VerityStalkGoal(VerityEntity verity) {
        this.verity = verity;
        // Задаем флаги: цель управляет движением и взглядом
        this.setFlags(EnumSet.of(Goal.Flag.MOVE, Goal.Flag.LOOK));
    }

    @Override
    public boolean canUse() {
        // Активно только при доверии < 0
        if (this.verity.getTrustLevel() >= 0) {
            return false;
        }

        Player player = this.verity.getOwner();
        if (player == null || !player.isAlive()) {
            return false;
        }

        return true;
    }

    @Override
    public void start() {
        this.stalkTarget = this.verity.getOwner();
        this.teleportCooldown = 0;
        this.teleportBehindTarget(this.stalkTarget);
    }

    @Override
    public void stop() {
        this.stalkTarget = null;
        this.verity.getNavigation().stop();
    }

    @Override
    public void tick() {
        if (this.stalkTarget == null) return;

        // Поворачиваемся к игроку
        this.verity.getLookControl().setLookAt(this.stalkTarget, 30.0F, 30.0F);

        // Уменьшаем кулдаун телепортации
        if (this.teleportCooldown > 0) {
            this.teleportCooldown--;
        }

        // Проверяем, смотрит ли игрок на Verity
        if (this.isPlayerLookingAtMe(this.stalkTarget) && this.stalkTarget.hasLineOfSight(this.verity)) {
            // Эффект исчезновения (Эндермен)
            this.triggerEvasion();
        }

        // Если моб случайно подошел слишком близко (менее 10 блоков) без взгляда игрока,
        // он тоже плавно перепозиционируется за спину
        double distSq = this.verity.distanceToSqr(this.stalkTarget);
        if (distSq < 100.0D && this.teleportCooldown <= 0) {
            this.teleportBehindTarget(this.stalkTarget);
        }
    }

    /**
     * Математический расчет: смотрит ли игрок непосредственно на хитбокс Verity.
     */
    private boolean isPlayerLookingAtMe(Player player) {
        // Получаем вектор взгляда игрока
        Vec3 lookVec = player.getViewVector(1.0F).normalize();
        
        // Получаем вектор направления от глаз игрока к центру Verity
        Vec3 eyePos = player.getEyePosition(1.0F);
        Vec3 entityCenter = this.verity.position().add(0, this.verity.getBbHeight() / 2.0F, 0);
        Vec3 toEntityVec = entityCenter.subtract(eyePos);
        
        double distance = toEntityVec.length();
        toEntityVec = toEntityVec.normalize();
        
        // Скалярное произведение векторов. Чем ближе к 1.0, тем точнее прицел игрока направлен на моба.
        double dot = lookVec.dot(toEntityVec);
        
        // Погрешность угла обзора. 0.985 соответствует примерно 10 градусам от центра экрана.
        // Ограничиваем дистанцию проверки взгляда в 40 блоков.
        return dot > 0.985D && distance < 40.0D;
    }

    /**
     * Эффектное исчезновение при взгляде.
     */
    private void triggerEvasion() {
        if (this.verity.level() instanceof ServerLevel serverLevel) {
            // Спавним густые частицы портала/дыма на старой позиции
            serverLevel.sendParticles(ParticleTypes.LARGE_SMOKE, 
                    this.verity.getX(), this.verity.getY() + 0.3D, this.verity.getZ(), 
                    15, 0.2D, 0.2D, 0.2D, 0.05D);
            
            // Воспроизводим искаженный звук телепортации эндермена с низким pitch
            serverLevel.playSound(null, this.verity.getX(), this.verity.getY(), this.verity.getZ(),
                    SoundEvents.ENDERMAN_TELEPORT, SoundSource.HOSTILE, 1.2F, 0.3F);
        }

        // Телепортируемся на новую позицию
        this.teleportBehindTarget(this.stalkTarget);
    }

    /**
     * Телепортация за спину игроку на безопасное расстояние (15-25 блоков).
     */
    private void teleportBehindTarget(Player target) {
        this.teleportCooldown = 60; // Устанавливаем кулдаун (3 секунды) перед следующим автоперемещением

        for (int attempts = 0; attempts < 15; attempts++) {
            double distance = 15.0D + this.verity.getRandom().nextDouble() * 10.0D;
            
            // Вычисляем угол за спиной игрока.
            // К направлению взгляда игрока прибавляем 180 градусов (чтобы оказаться сзади)
            // и даем небольшое случайное отклонение в 45 градусов в стороны.
            float targetAngle = target.getYRot() + 180.0F + (this.verity.getRandom().nextFloat() - 0.5F) * 90.0F;
            double radians = Math.toRadians(targetAngle);

            double xOffset = Math.sin(radians) * distance;
            double zOffset = -Math.cos(radians) * distance;
            double yOffset = 1.0D + this.verity.getRandom().nextDouble() * 3.0D; // Немного выше уровня земли

            double destX = target.getX() + xOffset;
            double destY = target.getY() + yOffset;
            double destZ = target.getZ() + zOffset;

            BlockPos targetPos = BlockPos.containing(destX, destY, destZ);
            
            // Проверяем, пусто ли в целевой точке и блоком ниже, чтобы не телепортироваться внутрь стены
            if (this.verity.level().isEmptyBlock(targetPos) && this.verity.level().isEmptyBlock(targetPos.above())) {
                this.verity.teleportTo(destX, destY, destZ);
                this.verity.getNavigation().stop(); // Сбрасываем старый путь полета
                
                // Воспроизводим тихий звук на новой позиции
                this.verity.level().playSound(null, destX, destY, destZ,
                        SoundEvents.ENDERMAN_TELEPORT, SoundSource.HOSTILE, 0.4F, 0.4F);
                break;
            }
        }
    }
}
