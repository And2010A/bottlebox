package com.bottlebox.glock19;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;

import net.minecraft.resources.Identifier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.bottlebox.glock19.item.GlockItem;
import com.bottlebox.glock19.network.ReloadPayload;

public class Glock19Mod implements ModInitializer {
	public static final String MOD_ID = "glock19";
	public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

	@Override
	public void onInitialize() {
		ModComponents.init();
		ModSounds.init();
		ModItems.init();

		PayloadTypeRegistry.playC2S().register(ReloadPayload.TYPE, ReloadPayload.CODEC);
		ServerPlayNetworking.registerGlobalReceiver(ReloadPayload.TYPE, (payload, context) -> GlockItem.tryReload(context.player()));

		LOGGER.info("Glock 19 loaded");
	}

	public static Identifier id(String path) {
		return Identifier.fromNamespaceAndPath(MOD_ID, path);
	}
}
