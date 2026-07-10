package com.example.verity.ai;

import com.example.verity.entity.VerityEntity;
import net.minecraft.world.entity.ai.goal.Goal;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;

import java.util.EnumSet;

/**
 * ИИ-цель для дружелюбной фазы (Доверие > 50).
 * Шар плавно следует за своим владельцем на уровне его глаз (Y + 1.5).
 */
public class VerityFollowGoal extends Goal {
    private final VerityEntity verity;
    private Player owner;

    public VerityFollowGoal(VerityEntity verity) {
        this.verity = verity;
        // Задаем флаги: цель управляет движением моба и его поворотом головы
        this.setFlags(EnumSet.of(Goal.Flag.MOVE, Goal.Flag.LOOK));
    }

    /**
     * Проверка: может ли ИИ-цель начать выполняться.
     */
    @Override
    public boolean canUse() {
        // Цель активна только если доверие выше 50
        if (this.verity.getTrustLevel() <= 50) {
            return false;
        }

        Player player = this.verity.getOwner();
        if (player == null || !player.isAlive()) {
            return false;
        }

        double distSq = this.verity.distanceToSqr(player);
        
        // Если сущность отстала очень далеко (например, игрок телепортировался), телепортируем её сразу
        if (distSq > 400.0D) {
            this.verity.teleportTo(player.getX(), player.getY() + 1.5D, player.getZ());
            return false;
        }

        // Начинаем следовать, если игрок отошел дальше 3 блоков
        return distSq > 9.0D;
    }

    /**
     * Проверка: продолжать ли выполнять цель в следующем тике.
     */
    @Override
    public boolean canContinueToUse() {
        if (this.verity.getTrustLevel() <= 50) {
            return false;
        }
        if (this.owner == null || !this.owner.isAlive()) {
            return false;
        }
        // Продолжаем двигаться, пока мы не приблизимся к владельцу на 2 блока
        return this.verity.distanceToSqr(this.owner) > 4.0D;
    }

    @Override
    public void start() {
        this.owner = this.verity.getOwner();
    }

    @Override
    public void stop() {
        this.owner = null;
        this.verity.getNavigation().stop();
    }

    /**
     * Основная логика тика движения.
     */
    @Override
    public void tick() {
        if (this.owner == null) return;

        // Заставляем шар всегда смотреть на лицо игрока
        this.verity.getLookControl().setLookAt(this.owner, 10.0F, (float) this.verity.getMaxHeadXRot());

        // Вычисляем целевую позицию: Y + 1.5 блока от ног игрока (уровень глаз)
        Vec3 targetPos = new Vec3(this.owner.getX(), this.owner.getY() + 1.5D, this.owner.getZ());

        double distSq = this.verity.distanceToSqr(this.owner);
        if (distSq > 16.0D) {
            // Если игрок сравнительно далеко, используем стандартную навигацию 3D-полета
            this.verity.getNavigation().moveTo(targetPos.x, targetPos.y, targetPos.z, 1.25D);
        } else {
            // Если игрок близко (от 2 до 4 блоков), плавно левитируем рядом, минуя тяжелый поиск пути.
            // Подталкиваем вектор скорости сущности к целевой точке над головой игрока.
            Vec3 motion = this.verity.getDeltaMovement();
            Vec3 direction = targetPos.subtract(this.verity.position());
            if (direction.lengthSqr() > 0.01D) {
                // Плавное притяжение
                direction = direction.normalize().scale(0.08D);
                this.verity.setDeltaMovement(motion.add(direction));
            }
        }
    }
}
