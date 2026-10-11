package com.bottlebox.glock19.client;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;

import net.minecraft.client.renderer.SubmitNodeCollector;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.client.renderer.entity.ThrownItemRenderer;
import net.minecraft.client.renderer.entity.state.ThrownItemRenderState;
import net.minecraft.client.renderer.state.CameraRenderState;
import net.minecraft.client.renderer.texture.OverlayTexture;

import com.bottlebox.glock19.entity.BulletEntity;

/**
 * Draws the bullet model pointing along its flight path (like an arrow) instead of facing the camera,
 * at full brightness so the tracer glows.
 */
public class BulletRenderer extends ThrownItemRenderer<BulletEntity> {
	public BulletRenderer(EntityRendererProvider.Context context) {
		super(context, 1.0F, true);
	}

	@Override
	public ThrownItemRenderState createRenderState() {
		return new State();
	}

	@Override
	public void extractRenderState(BulletEntity entity, ThrownItemRenderState state, float partialTick) {
		super.extractRenderState(entity, state, partialTick);
		State bullet = (State) state;
		bullet.yRot = entity.getYRot(partialTick);
		bullet.xRot = entity.getXRot(partialTick);
	}

	@Override
	public void submit(ThrownItemRenderState state, PoseStack poseStack, SubmitNodeCollector nodeCollector, CameraRenderState camera) {
		State bullet = (State) state;
		poseStack.pushPose();
		// The model points along +x, so turn it the same way vanilla turns arrows.
		poseStack.mulPose(Axis.YP.rotationDegrees(bullet.yRot - 90.0F));
		poseStack.mulPose(Axis.ZP.rotationDegrees(bullet.xRot));
		state.item.submit(poseStack, nodeCollector, state.lightCoords, OverlayTexture.NO_OVERLAY, state.outlineColor);
		poseStack.popPose();
	}

	public static class State extends ThrownItemRenderState {
		public float yRot;
		public float xRot;
	}
}
