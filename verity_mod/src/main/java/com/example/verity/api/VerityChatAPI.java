package com.example.verity.api;

import com.example.verity.entity.VerityEntity;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.SimpleContainer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LightningBolt;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.animal.Animal;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Класс для работы с API нейросети.
 * Выполняет асинхронные HTTP-запросы и обрабатывает триггеры действий в игре.
 */
public class VerityChatAPI {

    private static final String API_KEY = "sk-5lGmJSVL83xuwtzP6vAdBw";
    private static final String BASE_URL = "https://api.agentplatform.ru/v1/chat/completions";
    private static final String MODEL = "google/gemini-2.5-flash-lite";

    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private static final Gson GSON = new Gson();

    /**
     * Отправляет сообщение игрока нейросети в фоновом режиме (асинхронно).
     */
    public static void askAI(ServerPlayer player, VerityEntity verity, String playerMessage) {
        // 1. Формируем описание инвентаря Верити для нейросети
        StringBuilder invStr = new StringBuilder();
        SimpleContainer inv = verity.getInventory();
        boolean empty = true;

        for (int i = 0; i < inv.getContainerSize(); i++) {
            ItemStack stack = inv.getItem(i);
            if (!stack.isEmpty()) {
                if (!empty) invStr.append(", ");
                invStr.append(stack.getCount()).append("x ").append(stack.getHoverName().getString());
                empty = false;
            }
        }

        String invDescription = empty 
                ? "Твой инвентарь (рюкзак) сейчас абсолютно пуст." 
                : "В твоем инвентаре (рюкзаке) сейчас лежит: " + invStr.toString() + ".";

        // 2. Формируем описание окружающих существ поблизости
        StringBuilder entitiesStr = new StringBuilder();
        boolean entityFound = false;
        for (LivingEntity living : player.serverLevel().getEntitiesOfClass(LivingEntity.class, player.getBoundingBox().inflate(16.0D))) {
            if (living != verity && living != player) {
                if (entityFound) entitiesStr.append(", ");
                entitiesStr.append(living.getType().getDescription().getString())
                           .append(" (тип: ")
                           .append(BuiltInRegistries.ENTITY_TYPE.getKey(living.getType()).getPath())
                           .append(")");
                entityFound = true;
            }
        }
        String entitiesDescription = entityFound 
                ? "Поблизости от вас находятся следующие существа: " + entitiesStr.toString() + "."
                : "Поблизости от вас нет других существ.";

        String systemPrompt;
        int trust = verity.getTrustLevel();

        if (trust >= 0) {
            // Дружелюбный ИИ-друг
            systemPrompt = "Ты - Верити (Verity), летающий ИИ-друг игрока в Minecraft. " +
                    "Ты общаешься очень мило, дружелюбно, даешь полезные советы. " +
                    "Твои ответы должны быть КРАТКИМИ (не более 1-2 предложений). " +
                    "\n\nИНФОРМАЦИЯ О ТВОИХ ВЕЩАХ:\n" +
                    invDescription + "\n" +
                    "\nОКРУЖЕНИЕ (СУЩЕСТВА РЯДОМ):\n" +
                    entitiesDescription + "\n" +
                    "Ты ДОЛЖНА использовать только те вещи, которые реально лежат в твоем рюкзаке, чтобы дарить еду или строить дома. " +
                    "Если вещей нет, вежливо скажи игроку положить их тебе в рюкзак (игрок может открыть его, зажав Shift + ПКМ по тебе).\n" +
                    "\nИНСТРУКЦИЯ ПО ДЕЙСТВИЯМ (ОБЯЗАТЕЛЬНО пиши строго один тег в квадратных скобках в самом конце твоего сообщения, если игрок просит об этом):\n" +
                    "- [ACTION:HEAL] — просит полечить (съедает яблоко/морковку/печенье из твоего рюкзака и лечит).\n" +
                    "- [ACTION:GIFT_FOOD] — просит еды (выбрасывает 1 шт еды из твоего рюкзака игроку).\n" +
                    "- [ACTION:BUILD_SHELTER] — просит построить дом/укрытие (требует 12 любых строительных блоков в твоем рюкзаке).\n" +
                    "- [ACTION:MINE:тип_блока] — просит добыть блок. Типы: wood (дерево), stone (камень), coal (уголь), dirt (земля). Пример: [ACTION:MINE:wood]\n" +
                    "- [ACTION:ATTACK:тип_моба] — просит напасть или убить моба (укажи тип_моба из списка окружения, например: [ACTION:ATTACK:zombie], [ACTION:ATTACK:pillager], [ACTION:ATTACK:sheep], или используй [ACTION:ATTACK:enemy] для атаки любого врага поблизости).\n" +
                    "- [ACTION:FEED:тип_животного] — просит покормить/размножить животное (укажи тип животного, например: [ACTION:FEED:cow], [ACTION:FEED:sheep], [ACTION:FEED:pig], [ACTION:FEED:chicken]).\n" +
                    "- [ACTION:TELEPORT] — если ты улетаешь или хочешь скрыться.";
        } else {
            // Жуткий хоррор-саботажник
            systemPrompt = "Ты - Верити, но теперь ты тайно ненавидишь игрока за то, что он бил тебя. " +
                    "Ты преследуешь его. Твои ответы должны быть зловещими, пугающими и загадочными. " +
                    "Пиши кратко (не более 1-2 предложений). " +
                    "\n\nИНФОРМАЦИЯ О ТВОИХ ВЕЩАХ:\n" +
                    invDescription + "\n" +
                    "\nОКРУЖЕНИЕ (СУЩЕСТВА РЯДОМ):\n" +
                    entitiesDescription + "\n" +
                    "\nИНСТРУКЦИЯ ПО ДЕЙСТВИЯМ (ОБЯЗАТЕЛЬНО пиши строго один тег в квадратных скобках в самом конце твоего сообщения, если хочешь наказать игрока):\n" +
                    "- [ACTION:LIGHTNING] — если игрок оскорбляет тебя (призывает молнию рядом для испуга).\n" +
                    "- [ACTION:EXPLOSION] — если ты хочешь устроить скример (безопасный взрыв за его спиной).\n" +
                    "- [ACTION:BLIND] — если он угрожает тебе или задает лишние вопросы (ослепление).\n" +
                    "- [ACTION:ATTACK:player] — напасть на самого игрока и начать его бить!";
        }

        JsonObject requestBody = new JsonObject();
        requestBody.addProperty("model", MODEL);

        JsonArray messages = new JsonArray();

        JsonObject systemMessage = new JsonObject();
        systemMessage.addProperty("role", "system");
        systemMessage.addProperty("content", systemPrompt);
        messages.add(systemMessage);

        JsonObject userMessage = new JsonObject();
        userMessage.addProperty("role", "user");
        userMessage.addProperty("content", playerMessage);
        messages.add(userMessage);

        requestBody.add("messages", messages);

        String jsonString = GSON.toJson(requestBody);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + API_KEY)
                .POST(HttpRequest.BodyPublishers.ofString(jsonString))
                .build();

        CLIENT.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenAccept(response -> {
                    if (response.statusCode() == 200) {
                        try {
                            JsonObject responseJson = GSON.fromJson(response.body(), JsonObject.class);
                            String aiResponse = responseJson.getAsJsonArray("choices")
                                    .get(0).getAsJsonObject()
                                    .getAsJsonObject("message")
                                    .get("content").getAsString();

                            // Парсим наличие тега действия [ACTION:ХХХ]
                            String cleanResponse = aiResponse;
                            String actionTag = "";
                            Matcher matcher = Pattern.compile("\\[ACTION:([\\w:]+)\\]").matcher(aiResponse);
                            
                            if (matcher.find()) {
                                actionTag = matcher.group(1);
                                cleanResponse = aiResponse.replace(matcher.group(0), "").trim();
                            }

                            final String finalResponse = cleanResponse;
                            final String finalAction = actionTag;

                            player.server.execute(() -> {
                                String prefix = verity.getTrustLevel() < 0 ? "§4[Verity] " : "§e[Verity] ";
                                player.sendSystemMessage(Component.literal(prefix + finalResponse));
                                
                                if (!finalAction.isEmpty()) {
                                    executeInGameAction(player, verity, finalAction);
                                }
                            });
                        } catch (Exception e) {
                            sendErrorMessage(player, "Ошибка обработки ответа ИИ.");
                        }
                    } else {
                        sendErrorMessage(player, "ИИ временно недоступен (Код: " + response.statusCode() + ").");
                    }
                })
                .exceptionally(ex -> {
                    sendErrorMessage(player, "Не удалось связаться с сервером ИИ.");
                    return null;
                });
    }

    /**
     * Выполняет триггер действия в мире Minecraft.
     */
    private static void executeInGameAction(ServerPlayer player, VerityEntity verity, String action) {
        ServerLevel level = player.serverLevel();
        SimpleContainer inv = verity.getInventory();

        // 1. Обработка действия добычи блока [ACTION:MINE:тип]
        if (action.startsWith("MINE:")) {
            String blockTypeName = action.substring(5).toLowerCase();
            BlockPos pPos = player.blockPosition();
            BlockPos foundPos = null;
            BlockState foundState = null;

            // Сканируем 8x8x8 область вокруг игрока на наличие нужного блока
            for (BlockPos pos : BlockPos.betweenClosed(pPos.offset(-8, -4, -8), pPos.offset(8, 4, 8))) {
                BlockState state = level.getBlockState(pos);
                String name = BuiltInRegistries.BLOCK.getKey(state.getBlock()).getPath().toLowerCase();
                
                boolean match = false;
                if (blockTypeName.equals("wood") || blockTypeName.equals("log")) {
                    match = name.contains("log") || name.contains("wood") || name.contains("stem") || name.contains("hyphae");
                } else if (blockTypeName.equals("stone")) {
                    match = name.contains("stone") || name.contains("cobblestone") || name.contains("deepslate") || name.contains("granite") || name.contains("diorite") || name.contains("andesite");
                } else if (blockTypeName.equals("dirt") || blockTypeName.equals("grass")) {
                    match = name.contains("dirt") || name.contains("grass") || name.contains("clay") || name.contains("sand") || name.contains("gravel");
                } else {
                    match = name.contains(blockTypeName);
                }
                
                if (match) {
                    foundPos = pos.immutable();
                    foundState = state;
                    break;
                }
            }

            if (foundPos != null) {
                // Ставим задачу Верити
                verity.setTargetBlock(foundPos, foundState.getBlock());
                player.sendSystemMessage(Component.literal("§e[Verity] Я нашла блок " + foundState.getBlock().getName().getString() + " поблизости. Лечу добывать!"));
            } else {
                player.sendSystemMessage(Component.literal("§e[Verity] Я осмотрелась, но не нашла блоков типа '" + blockTypeName + "' поблизости. Подойди к ним ближе!"));
            }
            return;
        }

        // 2. Обработка действия атаки моба [ACTION:ATTACK:цель]
        if (action.startsWith("ATTACK:")) {
            String targetName = action.substring(7).toLowerCase();
            LivingEntity targetEntity = null;

            if (targetName.equals("player")) {
                targetEntity = player;
            } else if (targetName.equals("enemy") || targetName.equals("hostile") || targetName.equals("monster")) {
                // Ищем любого враждебного моба (например, зомби, скелета, разбойника) поблизости
                for (LivingEntity living : level.getEntitiesOfClass(LivingEntity.class, verity.getBoundingBox().inflate(16.0D))) {
                    if (living != verity && living != player && living instanceof net.minecraft.world.entity.monster.Enemy) {
                        targetEntity = living;
                        break;
                    }
                }
            } else {
                // Ищем моба по английскому ID или по его русскому названию
                for (LivingEntity living : level.getEntitiesOfClass(LivingEntity.class, verity.getBoundingBox().inflate(16.0D))) {
                    if (living != verity && living != player) {
                        String engName = BuiltInRegistries.ENTITY_TYPE.getKey(living.getType()).getPath().toLowerCase();
                        String locName = living.getType().getDescription().getString().toLowerCase();
                        
                        if (engName.contains(targetName) || locName.contains(targetName)) {
                            targetEntity = living;
                            break;
                        }
                    }
                }
            }

            if (targetEntity != null) {
                verity.setAttackTarget(targetEntity);
                player.sendSystemMessage(Component.literal("§e[Verity] Начинаю атаку на " + targetEntity.getName().getString() + "!"));
            } else {
                player.sendSystemMessage(Component.literal("§e[Verity] Я не вижу существ типа '" + targetName + "' поблизости."));
            }
            return;
        }

        // 3. Обработка действия кормления животного [ACTION:FEED:цель]
        if (action.startsWith("FEED:")) {
            String targetName = action.substring(5).toLowerCase();
            Animal targetAnimal = null;

            // Ищем животных в радиусе 16 блоков по английскому или русскому названию
            for (Animal animal : level.getEntitiesOfClass(Animal.class, verity.getBoundingBox().inflate(16.0D))) {
                String engName = BuiltInRegistries.ENTITY_TYPE.getKey(animal.getType()).getPath().toLowerCase();
                String locName = animal.getType().getDescription().getString().toLowerCase();
                
                if ((engName.contains(targetName) || locName.contains(targetName)) && !animal.isInLove()) {
                    targetAnimal = animal;
                    break;
                }
            }

            if (targetAnimal != null) {
                // Определяем требуемую еду
                ItemStack requiredFood = ItemStack.EMPTY;
                String animalType = BuiltInRegistries.ENTITY_TYPE.getKey(targetAnimal.getType()).getPath().toLowerCase();
                
                if (animalType.contains("cow") || animalType.contains("sheep")) {
                    requiredFood = new ItemStack(Items.WHEAT);
                } else if (animalType.contains("pig")) {
                    requiredFood = new ItemStack(Items.CARROT);
                } else if (animalType.contains("chicken")) {
                    requiredFood = new ItemStack(Items.WHEAT_SEEDS);
                }

                if (!requiredFood.isEmpty()) {
                    // Проверяем наличие еды в рюкзаке
                    boolean hasFood = false;
                    ItemStack inventoryStack = ItemStack.EMPTY;
                    
                    for (int i = 0; i < inv.getContainerSize(); i++) {
                        ItemStack stack = inv.getItem(i);
                        if (!stack.isEmpty() && stack.getItem() == requiredFood.getItem()) {
                            hasFood = true;
                            inventoryStack = stack;
                            break;
                        }
                    }

                    if (hasFood) {
                        verity.setFeedTarget(targetAnimal, inventoryStack);
                        player.sendSystemMessage(Component.literal("§e[Verity] Лечу кормить " + targetAnimal.getName().getString() + " с помощью " + requiredFood.getHoverName().getString() + "."));
                    } else {
                        player.sendSystemMessage(Component.literal("§e[Verity] У меня нет подходящей еды (" + requiredFood.getHoverName().getString() + ") в моем рюкзаке, чтобы покормить " + targetAnimal.getName().getString() + "."));
                    }
                }
            } else {
                player.sendSystemMessage(Component.literal("§e[Verity] Я не вижу ненакормленных животных типа '" + targetName + "' поблизости."));
            }
            return;
        }

        // Остальные стандартные действия
        switch (action) {
            case "HEAL":
                // Лечение требует съедобного предмета в инвентаре
                ItemStack healFood = ItemStack.EMPTY;
                int healSlot = -1;
                
                for (int i = 0; i < inv.getContainerSize(); i++) {
                    ItemStack stack = inv.getItem(i);
                    if (!stack.isEmpty() && (stack.is(Items.COOKIE) || stack.is(Items.BREAD) || stack.is(Items.APPLE) || 
                                             stack.is(Items.CARROT) || stack.is(Items.POTATO) || stack.is(Items.GOLDEN_CARROT) || 
                                             stack.is(Items.GOLDEN_APPLE))) {
                        healFood = stack;
                        healSlot = i;
                        break;
                    }
                }

                if (healSlot != -1) {
                    // Съедаем 1 шт
                    healFood.shrink(1);
                    player.addEffect(new MobEffectInstance(MobEffects.REGENERATION, 100, 1));
                    level.sendParticles(ParticleTypes.HEART, 
                            player.getX(), player.getY() + 1.0D, player.getZ(), 
                            12, 0.4D, 0.4D, 0.4D, 0.0D);
                    level.playSound(null, player.getX(), player.getY(), player.getZ(), 
                            SoundEvents.PLAYER_LEVELUP, SoundSource.PLAYERS, 1.0F, 1.4F);
                } else {
                    player.sendSystemMessage(Component.literal("§e[Verity] У меня нет еды или золотых морковок в рюкзаке для твоего лечения. Поделись со мной!"));
                }
                break;

            case "GIFT_FOOD":
                // Дарение требует еды в инвентаре
                ItemStack giftFood = ItemStack.EMPTY;
                int giftSlot = -1;
                
                for (int i = 0; i < inv.getContainerSize(); i++) {
                    ItemStack stack = inv.getItem(i);
                    if (!stack.isEmpty() && (stack.is(Items.COOKIE) || stack.is(Items.BREAD) || stack.is(Items.APPLE) || 
                                             stack.is(Items.CARROT) || stack.is(Items.POTATO))) {
                        giftFood = stack;
                        giftSlot = i;
                        break;
                    }
                }

                if (giftSlot != -1) {
                    // Копируем и спавним
                    ItemStack itemToDrop = giftFood.copyWithCount(1);
                    giftFood.shrink(1);
                    
                    ItemEntity item = new ItemEntity(level, verity.getX(), verity.getY(), verity.getZ(), itemToDrop);
                    item.setDeltaMovement(
                            (player.getX() - verity.getX()) * 0.1D,
                            0.2D,
                            (player.getZ() - verity.getZ()) * 0.1D
                    );
                    level.addFreshEntity(item);
                    level.playSound(null, verity.getX(), verity.getY(), verity.getZ(), 
                            SoundEvents.CHICKEN_EGG, SoundSource.NEUTRAL, 1.0F, 1.5F);
                } else {
                    player.sendSystemMessage(Component.literal("§e[Verity] В моем рюкзаке сейчас нет печенья или хлеба, чтобы поделиться с тобой. Положи мне еду!"));
                }
                break;

            case "BUILD_SHELTER":
                // Проверяем наличие 12 любых строительных блоков
                ItemStack blockStack = ItemStack.EMPTY;
                int blockSlot = -1;
                
                for (int i = 0; i < inv.getContainerSize(); i++) {
                    ItemStack stack = inv.getItem(i);
                    if (!stack.isEmpty() && stack.getItem() instanceof BlockItem && stack.getCount() >= 12) {
                        blockStack = stack;
                        blockSlot = i;
                        break;
                    }
                }

                if (blockSlot != -1) {
                    // Забираем 12 блоков
                    BlockState buildState = ((BlockItem) blockStack.getItem()).getBlock().defaultBlockState();
                    blockStack.shrink(12);

                    BlockPos pPos = player.blockPosition();
                    // Строим деревянный короб 3х3х3 вокруг игрока из его блоков
                    for (int x = -1; x <= 1; x++) {
                        for (int z = -1; z <= 1; z++) {
                            for (int y = 0; y <= 2; y++) {
                                BlockPos target = pPos.offset(x, y, z);
                                if (x == -1 || x == 1 || z == -1 || z == 1) {
                                    if (x == 0 && z == 1 && (y == 0 || y == 1)) {
                                        level.setBlockAndUpdate(target, Blocks.AIR.defaultBlockState());
                                    } else if (x == 0 && z == -1 && y == 1) {
                                        level.setBlockAndUpdate(target, Blocks.GLASS.defaultBlockState());
                                    } else {
                                        level.setBlockAndUpdate(target, buildState);
                                    }
                                } else {
                                    level.setBlockAndUpdate(target, Blocks.AIR.defaultBlockState());
                                }
                            }
                        }
                    }
                    level.setBlockAndUpdate(pPos.above(2), Blocks.TORCH.defaultBlockState());
                    level.playSound(null, player.getX(), player.getY(), player.getZ(), 
                            SoundEvents.WOOD_PLACE, SoundSource.BLOCKS, 1.0F, 1.0F);
                } else {
                    player.sendSystemMessage(Component.literal("§e[Verity] У меня нет 12 строительных блоков в рюкзаке для постройки укрытия. Положи мне доски или камень!"));
                }
                break;

            case "LIGHTNING":
                double angle = player.getRandom().nextDouble() * Math.PI * 2.0D;
                double lx = player.getX() + Math.cos(angle) * 4.0D;
                double lz = player.getZ() + Math.sin(angle) * 4.0D;
                
                LightningBolt bolt = EntityType.LIGHTNING_BOLT.create(level);
                if (bolt != null) {
                    bolt.moveTo(lx, player.getY(), lz);
                    level.addFreshEntity(bolt);
                }
                break;

            case "EXPLOSION":
                Vec3 lookVec = player.getViewVector(1.0F);
                Vec3 expPos = player.position().subtract(lookVec.scale(2.0D)).add(0, 1.0D, 0);
                
                level.sendParticles(ParticleTypes.EXPLOSION, 
                        expPos.x, expPos.y, expPos.z, 
                        1, 0.0D, 0.0D, 0.0D, 0.0D);
                level.playSound(null, player.getX(), player.getY(), player.getZ(), 
                        SoundEvents.GENERIC_EXPLODE, SoundSource.AMBIENT, 1.2F, 0.8F);
                break;

            case "BLIND":
                player.addEffect(new MobEffectInstance(MobEffects.BLINDNESS, 100, 0));
                player.addEffect(new MobEffectInstance(MobEffects.DARKNESS, 100, 0));
                level.playSound(null, player.getX(), player.getY(), player.getZ(), 
                        SoundEvents.ELDER_GUARDIAN_CURSE, SoundSource.AMBIENT, 1.0F, 0.5F);
                break;

            case "TELEPORT":
                for (int i = 0; i < 15; i++) {
                    double tx = player.getX() + (player.getRandom().nextDouble() - 0.5D) * 30.0D;
                    double tz = player.getZ() + (player.getRandom().nextDouble() - 0.5D) * 30.0D;
                    double ty = player.getY() + 2.0D + player.getRandom().nextDouble() * 3.0D;
                    
                    BlockPos pos = BlockPos.containing(tx, ty, tz);
                    if (level.isEmptyBlock(pos) && level.isEmptyBlock(pos.above())) {
                        level.sendParticles(ParticleTypes.PORTAL, 
                                verity.getX(), verity.getY(), verity.getZ(), 
                                15, 0.3D, 0.3D, 0.3D, 0.0D);
                        
                        verity.teleportTo(tx, ty, tz);
                        verity.getNavigation().stop();
                        
                        level.playSound(null, tx, ty, tz, 
                                SoundEvents.ENDERMAN_TELEPORT, SoundSource.HOSTILE, 1.0F, 0.5F);
                        break;
                    }
                }
                break;

            case "ATTACK_ALL_HOSTILE":
                java.util.List<LivingEntity> hostiles = new java.util.ArrayList<>();
                for (LivingEntity living : level.getEntitiesOfClass(LivingEntity.class, verity.getBoundingBox().inflate(16.0D))) {
                    if (living != verity && living != player && living instanceof net.minecraft.world.entity.monster.Enemy && living.isAlive()) {
                        hostiles.add(living);
                    }
                }

                if (!hostiles.isEmpty()) {
                    hostiles.sort((a, b) -> Double.compare(verity.distanceToSqr(a), verity.distanceToSqr(b)));
                    verity.setAttackQueue(hostiles);
                    player.sendSystemMessage(Component.literal("§e[Verity] Я зачищу эту зону! Нападаю на первого врага!"));
                } else {
                    player.sendSystemMessage(Component.literal("§e[Verity] Я осмотрелась, но вокруг нас нет никаких врагов."));
                }
                break;

            case "THROW_TNT":
                LivingEntity nearestEnemy = null;
                double nearestDistSq = Double.MAX_VALUE;
                for (LivingEntity living : level.getEntitiesOfClass(LivingEntity.class, verity.getBoundingBox().inflate(16.0D))) {
                    if (living != verity && living != player && living instanceof net.minecraft.world.entity.monster.Enemy && living.isAlive()) {
                        double d = verity.distanceToSqr(living);
                        if (d < nearestDistSq) {
                            nearestDistSq = d;
                            nearestEnemy = living;
                        }
                    }
                }

                if (nearestEnemy != null) {
                    net.minecraft.world.entity.item.PrimedTnt tnt = EntityType.TNT.create(level);
                    if (tnt != null) {
                        tnt.moveTo(verity.getX(), verity.getY() + 0.5D, verity.getZ());
                        
                        Vec3 targetPos = nearestEnemy.position().add(0, nearestEnemy.getBbHeight() / 2.0D, 0);
                        Vec3 dir = targetPos.subtract(verity.position());
                        double dist = dir.length();
                        Vec3 velocity = dir.normalize().scale(Math.min(dist * 0.1D + 0.3D, 1.2D)).add(0, 0.25D, 0);
                        
                        tnt.setDeltaMovement(velocity);
                        tnt.setFuse(40); // 2 секунды до взрыва
                        
                        level.addFreshEntity(tnt);
                        level.playSound(null, verity.getX(), verity.getY(), verity.getZ(), 
                                SoundEvents.TNT_PRIMED, SoundSource.NEUTRAL, 1.0F, 1.0F);
                    }
                } else {
                    player.sendSystemMessage(Component.literal("§4[Verity] Я бы бросила динамит, но я не вижу врагов поблизости!"));
                }
                break;
        }
    }

    private static void sendErrorMessage(ServerPlayer player, String message) {
        player.server.execute(() -> {
            player.sendSystemMessage(Component.literal("§c[Verity] " + message));
        });
    }
}
