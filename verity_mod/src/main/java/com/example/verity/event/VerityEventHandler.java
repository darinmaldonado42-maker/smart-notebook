package com.example.verity.event;

import com.example.verity.api.VerityChatAPI;
import com.example.verity.entity.VerityEntity;
import net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.message.v1.ServerMessageEvents;
import net.fabricmc.fabric.api.event.player.PlayerBlockBreakEvents;
import net.fabricmc.fabric.api.event.player.UseBlockCallback;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.util.RandomSource;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.damagesource.DamageTypes;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;

/**
 * Обработчик игровых событий для Fabric.
 * Регистрирует коллбэки через Fabric API для реализации падения доверия, саботажа,
 * галлюцинаций, а также живого диалога с ИИ-другом.
 */
public class VerityEventHandler {

    /**
     * Поиск активной сущности Verity, привязанной к данному игроку на сервере.
     */
    public static VerityEntity getVerityForPlayer(Player player) {
        if (player.level().isClientSide) return null;
        if (player.level() instanceof ServerLevel serverLevel) {
            for (net.minecraft.world.entity.Entity entity : serverLevel.getAllEntities()) {
                if (entity instanceof VerityEntity verity) {
                    if (verity.getOwnerUUID().isPresent() && verity.getOwnerUUID().get().equals(player.getUUID())) {
                        return verity;
                    }
                }
            }
        }
        return null;
    }

    /**
     * Регистрирует все слушатели событий Fabric API.
     */
    public static void registerEvents() {
        
        // 1. Событие получения урона (ServerLivingEntityEvents.ALLOW_DAMAGE)
        ServerLivingEntityEvents.ALLOW_DAMAGE.register((entity, source, amount) -> {
            if (entity instanceof VerityEntity verity) {
                // Если урон нанес игрок (напрямую или стрелой)
                if (source.getEntity() instanceof Player player) {
                    int currentTrust = verity.getTrustLevel();
                    int newTrust = Math.max(-100, currentTrust - 35);
                    verity.setTrustLevel(newTrust);
                    
                    // Привязываем сущность к атаковавшему
                    verity.setOwnerUUID(player.getUUID());

                    if (verity.level() instanceof ServerLevel serverLevel) {
                        serverLevel.sendParticles(ParticleTypes.ANGRY_VILLAGER, 
                                verity.getX(), verity.getY() + 0.3D, verity.getZ(), 
                                5, 0.1D, 0.1D, 0.1D, 0.0D);
                    }
                    
                    verity.level().playSound(null, verity.getX(), verity.getY(), verity.getZ(),
                            SoundEvents.BLAZE_HURT, SoundSource.HOSTILE, 1.0F, 0.4F);

                    // Реакция Верити в чате на удар
                    if (player instanceof ServerPlayer serverPlayer) {
                        if (newTrust >= 0) {
                            serverPlayer.sendSystemMessage(Component.literal("§e[Verity] Ой! За что? Я же твой друг..."));
                        } else {
                            serverPlayer.sendSystemMessage(Component.literal("§4[Verity] §kТЫ ПОЖАЛЕЕШЬ ОБ ЭТОМ."));
                        }
                    }
                } 
                // Урон от магии/огня/взрывов
                else if (source.is(DamageTypes.IN_FIRE) || source.is(DamageTypes.MAGIC) || source.is(DamageTypes.INDIRECT_MAGIC) || source.is(DamageTypes.EXPLOSION)) {
                    int currentTrust = verity.getTrustLevel();
                    verity.setTrustLevel(Math.max(-100, currentTrust - 20));
                }
            }
            return true; // Разрешаем нанесение урона
        });

        // 2. Событие клика блоком (для фиксации попытки застроить сущность)
        UseBlockCallback.EVENT.register((player, level, hand, hitResult) -> {
            if (!level.isClientSide() && player instanceof ServerPlayer serverPlayer) {
                ItemStack stack = player.getItemInHand(hand);
                
                if (stack.getItem() instanceof BlockItem) {
                    VerityEntity verity = getVerityForPlayer(serverPlayer);
                    if (verity != null) {
                        BlockPos targetPos = hitResult.getBlockPos().relative(hitResult.getDirection());
                        double distSq = verity.distanceToSqr(Vec3.atCenterOf(targetPos));
                        
                        if (distSq < 9.0D) {
                            int currentTrust = verity.getTrustLevel();
                            verity.setTrustLevel(Math.max(-100, currentTrust - 5));

                            if (verity.level() instanceof ServerLevel serverLevel) {
                                serverLevel.sendParticles(ParticleTypes.ANGRY_VILLAGER, 
                                        verity.getX(), verity.getY() + 0.3D, verity.getZ(), 
                                        2, 0.1D, 0.1D, 0.1D, 0.0D);
                            }
                        }
                    }
                }
            }
            return InteractionResult.PASS;
        });

        // 3. Событие разрушения блоков (для саботажа алмазной руды)
        PlayerBlockBreakEvents.BEFORE.register((level, player, pos, state, blockEntity) -> {
            if (level.isClientSide() || player == null) return true;

            if (state.is(Blocks.DIAMOND_ORE) || state.is(Blocks.DEEPSLATE_DIAMOND_ORE)) {
                VerityEntity verity = getVerityForPlayer(player);
                
                if (verity != null && verity.getTrustLevel() < 0) {
                    RandomSource random = player.getRandom();
                    if (random.nextFloat() < 0.5F) { // 50% шанс
                        
                        level.setBlock(pos, Blocks.AIR.defaultBlockState(), 3);
                        Block.popResource(level, pos, new ItemStack(Items.DIRT));

                        String scaryMsg = getScaryMessage(random);
                        player.sendSystemMessage(Component.literal(scaryMsg));

                        level.playSound(null, pos, SoundEvents.GRAVEL_BREAK, SoundSource.BLOCKS, 1.2F, 0.5F);

                        return false;
                    }
                }
            }
            return true;
        });

        // 4. Потиковое событие сервера (саботаж инвентаря и галлюцинации)
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            for (ServerPlayer player : server.getPlayerList().getPlayers()) {
                if (player.tickCount % 20 != 0) continue;

                VerityEntity verity = getVerityForPlayer(player);
                if (verity == null || verity.getTrustLevel() >= 0) continue;

                if (player.tickCount % 1200 == 0) {
                    swapRandomInventorySlots(player);
                }

                if (player.getRandom().nextFloat() < 0.008F) {
                    triggerPhantomSound(player);
                }
            }
        });

        // 5. Событие отправки сообщения в чат (Диалоги с ИИ-другом)
        ServerMessageEvents.CHAT_MESSAGE.register((message, sender, params) -> {
            String chatText = message.signedContent().trim();
            String lowerText = chatText.toLowerCase();

            // Проверяем, обращается ли игрок к Верити по имени
            if (lowerText.startsWith("верити") || lowerText.startsWith("verity")) {
                VerityEntity verity = getVerityForPlayer(sender);
                
                if (verity != null) {
                    // Очищаем сообщение от префикса «Верити» и знаков препинания
                    String query = chatText;
                    if (lowerText.startsWith("верити")) {
                        query = chatText.substring(6).replaceAll("^[\\s,?!.:;]+", "");
                    } else if (lowerText.startsWith("verity")) {
                        query = chatText.substring(6).replaceAll("^[\\s,?!.:;]+", "");
                    }

                    if (!query.isEmpty()) {
                        // Асинхронно опрашиваем нейросеть
                        VerityChatAPI.askAI(sender, verity, query);
                    } else {
                        // Если игрок просто написал «Верити»
                        String greeting = verity.getTrustLevel() < 0 ? "§4[Verity] ...Чего тебе?" : "§e[Verity] Да? Я слушаю тебя, мой друг!";
                        sender.sendSystemMessage(Component.literal(greeting));
                    }
                }
            }
        });
    }

    /**
     * Логика перемешивания вещей.
     */
    private static void swapRandomInventorySlots(Player player) {
        var inventory = player.getInventory();
        int slotA = player.getRandom().nextInt(36);
        int slotB = player.getRandom().nextInt(36);

        if (slotA != slotB) {
            ItemStack stackA = inventory.getItem(slotA);
            ItemStack stackB = inventory.getItem(slotB);

            inventory.setItem(slotA, stackB);
            inventory.setItem(slotB, stackA);

            player.playNotifySound(SoundEvents.ITEM_PICKUP, SoundSource.PLAYERS, 0.8F, 0.3F);
            player.sendSystemMessage(Component.literal("§4[Verity] §oТвои вещи лежат не на своих местах..."));
        }
    }

    /**
     * Создание фантомного звука.
     */
    private static void triggerPhantomSound(Player player) {
        Vec3 lookVec = player.getViewVector(1.0F);
        Vec3 soundPos = player.position().subtract(lookVec.scale(2.5D)).add(0, 1.0D, 0);

        int choice = player.getRandom().nextInt(3);
        net.minecraft.sounds.SoundEvent sound = SoundEvents.CREEPER_PRIMED;
        float volume = 0.9F;
        float pitch = 0.8F + player.getRandom().nextFloat() * 0.3F;

        if (choice == 1) {
            sound = SoundEvents.WOOD_BREAK;
            volume = 1.0F;
        } else if (choice == 2) {
            sound = SoundEvents.ZOMBIE_BREAK_WOODEN_DOOR;
            volume = 0.6F;
        }

        player.playNotifySound(sound, SoundSource.AMBIENT, volume, pitch);
    }

    /**
     * Зловещие реплики.
     */
    private static String getScaryMessage(RandomSource random) {
        String[] messages = {
            "§4[Verity] §4Ты думал, что богатство спасет тебя?",
            "§4[Verity] §kГРЯЗЬ§r§4 — единственное, что ты заслуживаешь.",
            "§4[Verity] §4Я вижу каждое твое движение. Алмазы тебе больше не понадобятся.",
            "§4[Verity] §4Твоя жадность делает тебя слабым."
        };
        return messages[random.nextInt(messages.length)];
    }
}
