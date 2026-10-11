package com.bottlebox.glock19.network;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;

import com.bottlebox.glock19.Glock19Mod;

/** Sent by the client when the reload key is pressed. */
public final class ReloadPayload implements CustomPacketPayload {
	public static final ReloadPayload INSTANCE = new ReloadPayload();
	public static final CustomPacketPayload.Type<ReloadPayload> TYPE = new CustomPacketPayload.Type<>(Glock19Mod.id("reload"));
	public static final StreamCodec<RegistryFriendlyByteBuf, ReloadPayload> CODEC = StreamCodec.unit(INSTANCE);

	private ReloadPayload() {
	}

	@Override
	public Type<? extends CustomPacketPayload> type() {
		return TYPE;
	}
}
