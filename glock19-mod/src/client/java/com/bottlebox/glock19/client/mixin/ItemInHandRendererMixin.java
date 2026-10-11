package com.bottlebox.glock19.client.mixin;

import com.mojang.blaze3d.vertex.PoseStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.ItemInHandRenderer;
import net.minecraft.client.renderer.SubmitNodeCollector;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.ItemDisplayContext;
import net.minecraft.world.item.ItemStack;

import com.bottlebox.glock19.ModItems;
import com.bottlebox.glock19.client.GunAnimator;

@Mixin(ItemInHandRenderer.class)
public abstract class ItemInHandRendererMixin {
	@Shadow
	public abstract void renderItem(LivingEntity entity, ItemStack stack, ItemDisplayContext displayContext, PoseStack poseStack, SubmitNodeCollector nodeCollector, int packedLight);

	@Inject(method = "renderItem", at = @At("HEAD"), cancellable = true)
	private void glock19$animateGun(LivingEntity entity, ItemStack stack, ItemDisplayContext displayContext, PoseStack poseStack,
			SubmitNodeCollector nodeCollector, int packedLight, CallbackInfo ci) {
		if (GunAnimator.drawingParts || !displayContext.firstPerson() || !stack.is(ModItems.GLOCK_19)) {
			return;
		}

		float partialTick = Minecraft.getInstance().getDeltaTracker().getGameTimeDeltaPartialTick(false);
		boolean rightHand = displayContext == ItemDisplayContext.FIRST_PERSON_RIGHT_HAND;
		GunAnimator.drawingParts = true;

		try {
			if (GunAnimator.render(stack, entity.level(), rightHand, partialTick, poseStack,
					(part, pose) -> renderItem(entity, part, displayContext, pose, nodeCollector, packedLight))) {
				ci.cancel();
			}
		} finally {
			GunAnimator.drawingParts = false;
		}
	}
}
