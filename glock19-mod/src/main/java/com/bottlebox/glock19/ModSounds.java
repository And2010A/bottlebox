package com.bottlebox.glock19;

import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.sounds.SoundEvent;

public final class ModSounds {
	public static final SoundEvent GLOCK_SHOOT = register("item.glock_19.shoot");
	public static final SoundEvent GLOCK_EMPTY = register("item.glock_19.empty");
	public static final SoundEvent GLOCK_RELOAD = register("item.glock_19.reload");
	public static final SoundEvent BULLET_IMPACT = register("entity.bullet.impact");

	private ModSounds() {
	}

	private static SoundEvent register(String name) {
		Identifier id = Glock19Mod.id(name);
		return Registry.register(BuiltInRegistries.SOUND_EVENT, id, SoundEvent.createVariableRangeEvent(id));
	}

	static void init() {
	}
}
