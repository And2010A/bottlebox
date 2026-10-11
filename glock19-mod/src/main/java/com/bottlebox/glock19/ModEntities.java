package com.bottlebox.glock19;

import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;

import com.bottlebox.glock19.entity.BulletEntity;

public final class ModEntities {
	private static final ResourceKey<EntityType<?>> BULLET_KEY = ResourceKey.create(Registries.ENTITY_TYPE, Glock19Mod.id("bullet"));

	public static final EntityType<BulletEntity> BULLET = Registry.register(BuiltInRegistries.ENTITY_TYPE, BULLET_KEY,
			EntityType.Builder.<BulletEntity>of(BulletEntity::new, MobCategory.MISC)
					.sized(0.1F, 0.1F)
					.clientTrackingRange(8)
					.updateInterval(1)
					.build(BULLET_KEY));

	private ModEntities() {
	}

	static void init() {
	}
}
