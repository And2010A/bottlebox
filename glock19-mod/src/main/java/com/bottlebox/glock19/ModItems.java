package com.bottlebox.glock19;

import java.util.function.Function;

import net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents;

import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.world.item.Item;

import com.bottlebox.glock19.item.GlockItem;

public final class ModItems {
	public static final Item GLOCK_19 = register("glock_19", GlockItem::new, new Item.Properties()
			.stacksTo(1)
			.component(ModComponents.AMMO, GlockItem.MAGAZINE_SIZE)
			.component(ModComponents.RELOAD_UNTIL, 0L));

	public static final Item AMMO_9MM = register("ammo_9mm", Item::new, new Item.Properties());

	private ModItems() {
	}

	private static Item register(String name, Function<Item.Properties, Item> factory, Item.Properties properties) {
		ResourceKey<Item> key = ResourceKey.create(Registries.ITEM, Glock19Mod.id(name));
		return Registry.register(BuiltInRegistries.ITEM, key, factory.apply(properties.setId(key)));
	}

	static void init() {
		ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.COMBAT).register(entries -> {
			entries.accept(GLOCK_19);
			entries.accept(AMMO_9MM);
		});
	}
}
