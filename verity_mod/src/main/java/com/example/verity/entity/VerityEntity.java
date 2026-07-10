package com.example.verity.entity;

import com.example.verity.ai.VerityFollowGoal;
import com.example.verity.ai.VerityStalkGoal;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.BlockParticleOption;
import net.minecraft.core.particles.DustParticleOptions;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.network.chat.Component;
import net.minecraft.network.syncher.EntityDataAccessor;
import net.minecraft.network.syncher.EntityDataSerializers;
import net.minecraft.network.syncher.SynchedEntityData;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.SimpleContainer;
import net.minecraft.world.SimpleMenuProvider;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.MoverType;
import net.minecraft.world.entity.PathfinderMob;
import net.minecraft.world.entity.ai.attributes.AttributeSupplier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.ai.control.FlyingMoveControl;
import net.minecraft.world.entity.ai.goal.LookAtPlayerGoal;
import net.minecraft.world.entity.ai.goal.WaterAvoidingRandomFlyingGoal;
import net.minecraft.world.entity.ai.navigation.FlyingPathNavigation;
import net.minecraft.world.entity.ai.navigation.PathNavigation;
import net.minecraft.world.entity.animal.Animal;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ChestMenu;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;
import org.joml.Vector3f;

import java.util.Optional;
import java.util.UUID;

/**
 * Сущность Verity — ИИ-друг с инвентарем, летающей физикой, системой доверия,
 * способностью физически добывать блоки, атаковать врагов и кормить животных.
 */
public class VerityEntity extends PathfinderMob {
    
    private static final EntityDataAccessor<Integer> TRUST_LEVEL = SynchedEntityData.defineId(VerityEntity.class, EntityDataSerializers.INT);
    private static final EntityDataAccessor<Optional<UUID>> OWNER_UUID = SynchedEntityData.defineId(VerityEntity.class, EntityDataSerializers.OPTIONAL_UUID);

    // Собственный инвентарь Verity на 27 слотов (как у одиночного сундука)
    private final SimpleContainer inventory = new SimpleContainer(27);

    // Переменные для задачи добычи блоков
    private BlockPos targetBlockPos = null;
    private Block targetBlockType = null;
    private int mineTicks = 0;

    // Переменные для задачи атаки и убийства мобов
    private LivingEntity attackTarget = null;
    private int attackTicks = 0;

    // Переменные для задачи кормления животных
    private Animal feedTarget = null;
    private ItemStack feedFoodItem = ItemStack.EMPTY;
    private int feedTicks = 0;

    // Очередь атаки для убийства мобов по цепочке
    private final java.util.List<LivingEntity> attackQueue = new java.util.ArrayList<>();

    public VerityEntity(EntityType<? extends PathfinderMob> type, Level level) {
        super(type, level);
        this.moveControl = new FlyingMoveControl(this, 20, true);
        this.setNoGravity(true);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Mob.createMobAttributes()
                .add(Attributes.MAX_HEALTH, 20.0D)
                .add(Attributes.FLYING_SPEED, 0.6D)
                .add(Attributes.MOVEMENT_SPEED, 0.25D)
                .add(Attributes.FOLLOW_RANGE, 48.0D);
    }

    @Override
    protected void registerGoals() {
        this.goalSelector.addGoal(1, new VerityFollowGoal(this));
        this.goalSelector.addGoal(1, new VerityStalkGoal(this));
        this.goalSelector.addGoal(2, new WaterAvoidingRandomFlyingGoal(this, 1.0D));
        this.goalSelector.addGoal(3, new LookAtPlayerGoal(this, Player.class, 8.0F));
    }

    @Override
    protected PathNavigation createNavigation(Level level) {
        FlyingPathNavigation nav = new FlyingPathNavigation(this, level);
        nav.setCanOpenDoors(false);
        nav.setCanPassDoors(false);
        nav.setCanFloat(true);
        return nav;
    }

    @Override
    protected void defineSynchedData(SynchedEntityData.Builder builder) {
        super.defineSynchedData(builder);
        builder.define(TRUST_LEVEL, 100);
        builder.define(OWNER_UUID, Optional.empty());
    }

    public int getTrustLevel() {
        return this.entityData.get(TRUST_LEVEL);
    }

    public void setTrustLevel(int trust) {
        this.entityData.set(TRUST_LEVEL, trust);
    }

    public Optional<UUID> getOwnerUUID() {
        return this.entityData.get(OWNER_UUID);
    }

    public void setOwnerUUID(UUID uuid) {
        this.entityData.set(OWNER_UUID, Optional.ofNullable(uuid));
    }

    public Player getOwner() {
        return this.getOwnerUUID()
                .map(uuid -> this.level().getPlayerByUUID(uuid))
                .orElse(null);
    }

    public SimpleContainer getInventory() {
        return this.inventory;
    }

    /**
     * Задать цель для физической добычи блока.
     */
    public void setTargetBlock(BlockPos pos, Block block) {
        this.targetBlockPos = pos;
        this.targetBlockType = block;
        this.mineTicks = 0;
        
        // Сбрасываем другие цели
        this.attackTarget = null;
        this.feedTarget = null;
    }

    public BlockPos getTargetBlockPos() {
        return this.targetBlockPos;
    }

    /**
     * Задать цель для атаки моба.
     */
    public void setAttackTarget(LivingEntity target) {
        this.attackTarget = target;
        this.attackTicks = 0;
        
        // Сбрасываем другие цели
        this.targetBlockPos = null;
        this.feedTarget = null;
    }

    /**
     * Задать очередь целей для последовательной атаки.
     */
    public void setAttackQueue(java.util.List<LivingEntity> targets) {
        this.attackQueue.clear();
        this.attackQueue.addAll(targets);
        this.attackTarget = null;
    }

    /**
     * Задать цель для кормления животного.
     */
    public void setFeedTarget(Animal target, ItemStack food) {
        this.feedTarget = target;
        this.feedFoodItem = food;
        this.feedTicks = 0;
        
        // Сбрасываем другие цели
        this.targetBlockPos = null;
        this.attackTarget = null;
    }

    /**
     * Взаимодействие игрока с Верити.
     * Shift + ПКМ открывает её инвентарь на 27 слотов.
     */
    @Override
    protected InteractionResult mobInteract(Player player, InteractionHand hand) {
        if (!this.level().isClientSide) {
            if (this.getOwnerUUID().isEmpty()) {
                this.setOwnerUUID(player.getUUID());
                player.sendSystemMessage(Component.literal("§e[Verity] Привет! Теперь я летаю с тобой."));
                this.level().playSound(null, this.getX(), this.getY(), this.getZ(),
                        SoundEvents.EXPERIENCE_ORB_PICKUP, SoundSource.NEUTRAL, 1.0F, 1.2F);
                return InteractionResult.SUCCESS;
            } else if (player.getUUID().equals(this.getOwnerUUID().orElse(null))) {
                if (player.isShiftKeyDown()) {
                    player.openMenu(new SimpleMenuProvider((containerId, playerInventory, p) -> {
                        return ChestMenu.threeRows(containerId, playerInventory, this.inventory);
                    }, Component.literal("Инвентарь Verity")));
                    return InteractionResult.SUCCESS;
                } else {
                    player.sendSystemMessage(Component.literal("§e[Verity] Привет, друг! (Зажми Shift + ПКМ, чтобы открыть мой рюкзак)"));
                    return InteractionResult.SUCCESS;
                }
            }
        }
        return super.mobInteract(player, hand);
    }

    /**
     * Логика тиков сущности. Вызывается 20 раз в секунду.
     */
    @Override
    public void tick() {
        super.tick();

        int trust = this.getTrustLevel();

        if (this.level().isClientSide) {
            // Эффекты частиц на стороне клиента
            if (trust > 50) {
                if (this.random.nextFloat() < 0.15F) {
                    this.level().addParticle(ParticleTypes.WAX_OFF, 
                            this.getRandomX(0.5D), this.getRandomY(), this.getRandomZ(0.5D), 
                            0.0D, 0.02D, 0.0D);
                }
            } else if (trust < 0) {
                if (this.random.nextFloat() < 0.25F) {
                    DustParticleOptions redDust = new DustParticleOptions(new Vector3f(0.8F, 0.0F, 0.0F), 1.2F);
                    this.level().addParticle(redDust, 
                            this.getRandomX(0.5D), this.getRandomY(), this.getRandomZ(0.5D), 
                            0.0D, -0.01D, 0.0D);
                }
            }
        } else {
            // СЕРВЕРНАЯ ЧАСТЬ:
            ServerLevel serverLevel = (ServerLevel) this.level();

            // 1. Физическая добыча блока, если цель задана
            if (this.targetBlockPos != null && this.targetBlockType != null) {
                BlockState state = this.level().getBlockState(this.targetBlockPos);
                if (state.is(this.targetBlockType)) {
                    double distSq = this.distanceToSqr(Vec3.atCenterOf(this.targetBlockPos));
                    
                    if (distSq > 5.0D) {
                        this.getNavigation().moveTo(this.targetBlockPos.getX(), this.targetBlockPos.getY(), this.targetBlockPos.getZ(), 1.0D);
                    } else {
                        this.getNavigation().stop();
                        this.mineTicks++;

                        if (this.mineTicks % 5 == 0) {
                            serverLevel.sendParticles(new BlockParticleOption(ParticleTypes.BLOCK, state),
                                    this.targetBlockPos.getX() + 0.5D, this.targetBlockPos.getY() + 0.5D, this.targetBlockPos.getZ() + 0.5D,
                                    6, 0.1D, 0.1D, 0.1D, 0.05D);
                            this.level().playSound(null, this.targetBlockPos, 
                                    state.getSoundType().getHitSound(), SoundSource.BLOCKS, 0.6F, 1.0F);
                        }

                        if (this.mineTicks >= 40) {
                            ItemStack drop = new ItemStack(state.getBlock().asItem());
                            if (!drop.isEmpty()) {
                                this.inventory.addItem(drop);
                            }
                            
                            this.level().destroyBlock(this.targetBlockPos, false);
                            this.level().playSound(null, this.targetBlockPos, 
                                    state.getSoundType().getBreakSound(), SoundSource.BLOCKS, 1.0F, 1.0F);

                            Player owner = this.getOwner();
                            if (owner != null) {
                                owner.sendSystemMessage(Component.literal("§e[Verity] Я успешно добыла блок " + state.getBlock().getName().getString() + " и положила в рюкзак!"));
                            }

                            this.targetBlockPos = null;
                            this.targetBlockType = null;
                            this.mineTicks = 0;
                        }
                    }
                } else {
                    this.targetBlockPos = null;
                    this.targetBlockType = null;
                    this.mineTicks = 0;
                }
            }

            // 2. Задача атаки и убийства мобов (по цепочке или одиночно)
            if (this.attackTarget == null || !this.attackTarget.isAlive()) {
                // Если текущей цели нет или она погибла, пробуем взять следующую из очереди
                while (!this.attackQueue.isEmpty()) {
                    LivingEntity next = this.attackQueue.remove(0);
                    if (next != null && next.isAlive()) {
                        this.setAttackTarget(next);
                        break;
                    }
                }
            }

            if (this.attackTarget != null) {
                if (this.attackTarget.isAlive()) {
                    double distSq = this.distanceToSqr(this.attackTarget);
                    
                    // Постоянно летим к цели со скоростью 1.1 для высокой маневренности
                    this.getNavigation().moveTo(this.attackTarget, 1.1D);
                    this.attackTicks++;

                    // Атакуем, если цель в радиусе 3 блоков (distSq <= 9.0)
                    if (distSq <= 9.0D) {
                        // Атакуем раз в 15 тиков (0.75 сек)
                        if (this.attackTicks % 15 == 0) {
                            this.attackTarget.hurt(this.damageSources().mobAttack(this), 4.0F); // 4 единицы урона (2 сердца)
                            
                            // Эффект кругового удара
                            serverLevel.sendParticles(ParticleTypes.SWEEP_ATTACK, 
                                    this.attackTarget.getX(), this.attackTarget.getY() + 0.5D, this.attackTarget.getZ(), 
                                    1, 0.0D, 0.0D, 0.0D, 0.0D);
                            
                            this.level().playSound(null, this.getX(), this.getY(), this.getZ(), 
                                    SoundEvents.BLAZE_HURT, SoundSource.HOSTILE, 1.0F, 1.4F);
                        }
                    }
                } else {
                    // Цель погибла
                    Player owner = this.getOwner();
                    if (owner != null) {
                        owner.sendSystemMessage(Component.literal("§e[Verity] Цель " + this.attackTarget.getName().getString() + " успешно уничтожена!"));
                    }
                    this.attackTarget = null;
                    this.attackTicks = 0;
                }
            }

            // 3. Задача кормления животных
            if (this.feedTarget != null) {
                if (this.feedTarget.isAlive() && !this.feedTarget.isInLove()) {
                    double distSq = this.distanceToSqr(this.feedTarget);
                    
                    // Летим к животному
                    this.getNavigation().moveTo(this.feedTarget, 1.0D);
                    
                    // Кормим, если подошли ближе 3 блоков (distSq <= 9.0)
                    if (distSq <= 9.0D) {
                        // Забираем 1 штуку еды из инвентаря
                        boolean foodConsumed = false;
                        for (int i = 0; i < this.inventory.getContainerSize(); i++) {
                            ItemStack stack = this.inventory.getItem(i);
                            if (!stack.isEmpty() && stack.getItem() == this.feedFoodItem.getItem()) {
                                stack.shrink(1);
                                foodConsumed = true;
                                break;
                            }
                        }

                        if (foodConsumed) {
                            // Переводим животное в режим размножения
                            this.feedTarget.setInLove(null);
                            
                            // Спавним сердечки над животным
                            serverLevel.sendParticles(ParticleTypes.HEART, 
                                    this.feedTarget.getX(), this.feedTarget.getY() + 0.8D, this.feedTarget.getZ(), 
                                    8, 0.3D, 0.3D, 0.3D, 0.0D);
                            
                            this.level().playSound(null, this.feedTarget.getX(), this.feedTarget.getY(), this.feedTarget.getZ(), 
                                    SoundEvents.GENERIC_EAT, SoundSource.NEUTRAL, 1.0F, 1.0F);

                            Player owner = this.getOwner();
                            if (owner != null) {
                                owner.sendSystemMessage(Component.literal("§e[Verity] Я успешно покормила животное (" + this.feedTarget.getName().getString() + ")!"));
                            }
                        }

                        // Сброс цели
                        this.feedTarget = null;
                        this.feedFoodItem = ItemStack.EMPTY;
                        this.feedTicks = 0;
                    }
                } else {
                    // Животное уже накормлено или погибло
                    this.feedTarget = null;
                    this.feedFoodItem = ItemStack.EMPTY;
                    this.feedTicks = 0;
                }
            }

            // 4. Хоррор-фаза: Генерация искаженных жутких звуков
            if (trust < 0) {
                if (this.random.nextFloat() < 0.005F) {
                    float lowPitch = 0.2F + this.random.nextFloat() * 0.2F;
                    this.level().playSound(null, this.getX(), this.getY(), this.getZ(),
                            SoundEvents.ENDERMAN_AMBIENT, SoundSource.HOSTILE, 0.8F, lowPitch);
                }
            }
        }
    }

    @Override
    public void travel(Vec3 travelVector) {
        if (this.isControlledByLocalInstance()) {
            if (this.isInWater()) {
                this.moveRelative(0.02F, travelVector);
                this.move(MoverType.SELF, this.getDeltaMovement());
                this.setDeltaMovement(this.getDeltaMovement().scale(0.8D));
            } else if (this.isInLava()) {
                this.moveRelative(0.02F, travelVector);
                this.move(MoverType.SELF, this.getDeltaMovement());
                this.setDeltaMovement(this.getDeltaMovement().scale(0.5D));
            } else {
                this.moveRelative(this.getSpeed(), travelVector);
                this.move(MoverType.SELF, this.getDeltaMovement());
                this.setDeltaMovement(this.getDeltaMovement().scale(0.8D));
            }
        }
        this.calculateEntityAnimation(false);
    }

    @Override
    public boolean causeFallDamage(float fallDistance, float damageMultiplier, DamageSource damageSource) {
        return false;
    }

    @Override
    protected void checkFallDamage(double y, boolean onGround, BlockState state, BlockPos pos) {
    }

    // Сохранение данных в NBT (включая инвентарь)
    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        tag.putInt("trust_level", this.getTrustLevel());
        if (this.getOwnerUUID().isPresent()) {
            tag.putUUID("Owner", this.getOwnerUUID().get());
        }

        ListTag listTag = new ListTag();
        for (int i = 0; i < this.inventory.getContainerSize(); i++) {
            ItemStack stack = this.inventory.getItem(i);
            if (!stack.isEmpty()) {
                CompoundTag slotTag = new CompoundTag();
                slotTag.putByte("Slot", (byte) i);
                CompoundTag itemData = (CompoundTag) stack.save(this.registryAccess());
                slotTag.put("Item", itemData);
                listTag.add(slotTag);
            }
        }
        tag.put("Inventory", listTag);
    }

    // Загрузка данных из NBT (включая инвентарь)
    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        if (tag.contains("trust_level")) {
            this.setTrustLevel(tag.getInt("trust_level"));
        }
        if (tag.hasUUID("Owner")) {
            this.setOwnerUUID(tag.getUUID("Owner"));
        }

        if (tag.contains("Inventory")) {
            ListTag listTag = tag.getList("Inventory", 10);
            this.inventory.clearContent();
            for (int i = 0; i < listTag.size(); i++) {
                CompoundTag slotTag = listTag.getCompound(i);
                int slot = slotTag.getByte("Slot") & 255;
                if (slot >= 0 && slot < this.inventory.getContainerSize()) {
                    CompoundTag itemData = slotTag.getCompound("Item");
                    this.inventory.setItem(slot, ItemStack.parse(this.registryAccess(), itemData).orElse(ItemStack.EMPTY));
                }
            }
        }
    }
}
