package com.bottlebox.glock19.client;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;

import net.minecraft.core.component.DataComponents;
import net.minecraft.resources.Identifier;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;

import com.bottlebox.glock19.Glock19Mod;
import com.bottlebox.glock19.item.GlockItem;

/**
 * First-person reload and recoil animation. The gun is drawn as three item models (frame, slide,
 * magazine) that share one display transform, so each can be moved on its own.
 */
public final class GunAnimator {
	private static final Identifier FRAME = Glock19Mod.id("glock_19_frame");
	private static final Identifier SLIDE = Glock19Mod.id("glock_19_slide");
	private static final Identifier MAGAZINE = Glock19Mod.id("glock_19_mag");

	/** One model unit in hand space: 1/16 block times the first-person display scale. */
	private static final float UNIT = 0.55F / 16.0F;
	/** Model -x (towards the shooter) ends up as +z in hand space after the display rotation. */
	private static final float GRIP_SIN = 0.383F;
	private static final float GRIP_COS = 0.924F;
	private static final float RECOIL_TICKS = 5.0F;

	/** Set while the parts are being drawn, so the mixin doesn't animate them again. */
	public static boolean drawingParts;

	@FunctionalInterface
	public interface PartRenderer {
		void render(ItemStack part, PoseStack poseStack);
	}

	private GunAnimator() {
	}

	/** Draws the animated gun. Returns false when idle, so the caller draws the plain model instead. */
	public static boolean render(ItemStack stack, Level level, boolean rightHand, float partialTick, PoseStack poseStack, PartRenderer renderer) {
		float reload = GlockItem.isReloading(stack, level) ? GlockItem.reloadProgress(stack, level, partialTick) : -1.0F;
		float sinceShot = level.getGameTime() - GlockItem.lastClientShotTime + partialTick;
		float recoil = sinceShot >= 0 && sinceShot < RECOIL_TICKS ? square(1.0F - sinceShot / RECOIL_TICKS) : 0.0F;

		if (reload < 0.0F && recoil <= 0.0F) {
			return false;
		}

		float tilt = 0.0F;
		float magOut = 0.0F;
		float seatBump = 0.0F;
		float slideBack = 0.0F;

		if (reload >= 0.0F) {
			// Timeline matches the reload sound: release, drop, insert, seat, rack, snap.
			tilt = ramp(reload, 0.0F, 0.12F) * (1.0F - ramp(reload, 0.82F, 1.0F));
			magOut = reload < 0.27F
					? 16.0F * square(ramp(reload, 0.03F, 0.25F))
					: 11.0F * (1.0F - easeOut(ramp(reload, 0.28F, 0.42F)));
			seatBump = ramp(reload, 0.41F, 0.44F) * (1.0F - ramp(reload, 0.44F, 0.52F));
			slideBack = 2.8F * easeOut(ramp(reload, 0.62F, 0.72F)) * (1.0F - ramp(reload, 0.74F, 0.77F));
		}

		slideBack = Math.max(slideBack, 2.6F * recoil);
		float side = rightHand ? 1.0F : -1.0F;

		poseStack.pushPose();
		poseStack.translate(side * -0.08F * tilt, 0.05F * tilt + 0.03F * seatBump, 0.06F * recoil);
		poseStack.mulPose(Axis.ZP.rotationDegrees(side * 30.0F * tilt));
		poseStack.mulPose(Axis.XP.rotationDegrees(14.0F * tilt + 9.0F * recoil + 4.0F * seatBump));

		renderer.render(part(stack, FRAME), poseStack);

		poseStack.pushPose();
		poseStack.translate(0.0F, 0.0F, side * slideBack * UNIT);
		renderer.render(part(stack, SLIDE), poseStack);
		poseStack.popPose();

		if (magOut < 15.5F) {
			// The magazine travels along the raked grip: down and back towards the shooter.
			poseStack.pushPose();
			poseStack.translate(0.0F, -magOut * GRIP_COS * UNIT, side * magOut * GRIP_SIN * UNIT);
			renderer.render(part(stack, MAGAZINE), poseStack);
			poseStack.popPose();
		}

		poseStack.popPose();
		return true;
	}

	private static ItemStack part(ItemStack stack, Identifier model) {
		ItemStack part = stack.copy();
		part.set(DataComponents.ITEM_MODEL, model);
		return part;
	}

	/** 0 before start, 1 after end, smoothstep between. */
	private static float ramp(float t, float start, float end) {
		float x = Math.max(0.0F, Math.min(1.0F, (t - start) / (end - start)));
		return x * x * (3.0F - 2.0F * x);
	}

	private static float easeOut(float x) {
		return 1.0F - square(1.0F - x);
	}

	private static float square(float x) {
		return x * x;
	}
}
