package com.bottlebox.glock19.client;

import com.mojang.blaze3d.platform.InputConstants;
import org.lwjgl.glfw.GLFW;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElementRegistry;
import net.fabricmc.fabric.api.client.rendering.v1.hud.VanillaHudElements;

import net.minecraft.client.KeyMapping;

import com.bottlebox.glock19.Glock19Mod;
import com.bottlebox.glock19.network.ReloadPayload;

public class Glock19Client implements ClientModInitializer {
	public static final KeyMapping.Category CATEGORY = KeyMapping.Category.register(Glock19Mod.id("glock19"));
	public static final KeyMapping RELOAD = KeyBindingHelper.registerKeyBinding(
			new KeyMapping("key.glock19.reload", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_R, CATEGORY));

	@Override
	public void onInitializeClient() {
		ClientTickEvents.END_CLIENT_TICK.register(client -> {
			while (RELOAD.consumeClick()) {
				if (client.getConnection() != null) {
					ClientPlayNetworking.send(ReloadPayload.INSTANCE);
				}
			}
		});

		HudElementRegistry.attachElementAfter(VanillaHudElements.HOTBAR, Glock19Mod.id("ammo_hud"), AmmoHud::render);
	}
}
