package com.bottlebox.glock19;

import com.mojang.serialization.Codec;

import net.minecraft.core.Registry;
import net.minecraft.core.component.DataComponentType;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.util.ExtraCodecs;

public final class ModComponents {
	/** Rounds currently in the magazine. */
	public static final DataComponentType<Integer> AMMO = register("ammo",
			DataComponentType.<Integer>builder().persistent(ExtraCodecs.NON_NEGATIVE_INT).networkSynchronized(ByteBufCodecs.VAR_INT).build());

	/** Game time at which the current reload finishes; the gun can't fire before then. */
	public static final DataComponentType<Long> RELOAD_UNTIL = register("reload_until",
			DataComponentType.<Long>builder().persistent(Codec.LONG).networkSynchronized(ByteBufCodecs.VAR_LONG).build());

	private ModComponents() {
	}

	private static <T> DataComponentType<T> register(String name, DataComponentType<T> type) {
		return Registry.register(BuiltInRegistries.DATA_COMPONENT_TYPE, Glock19Mod.id(name), type);
	}

	static void init() {
	}
}
