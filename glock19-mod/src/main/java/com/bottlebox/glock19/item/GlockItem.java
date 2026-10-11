package com.bottlebox.glock19.item;

import java.util.Optional;

import net.minecraft.core.particles.BlockParticleOption;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import com.bottlebox.glock19.ModComponents;
import com.bottlebox.glock19.ModItems;
import com.bottlebox.glock19.ModSounds;

public class GlockItem extends Item {
	public static final int MAGAZINE_SIZE = 15;
	public static final int RELOAD_TICKS = 32;
	private static final int FIRE_COOLDOWN_TICKS = 3;
	private static final double RANGE = 64.0;
	private static final float DAMAGE = 6.0F;
	private static final float SPREAD = 0.012F;
	private static final float RECOIL_DEGREES = 2.5F;

	/** Client only: game time of the local player's last shot, drives the first-person recoil animation. */
	public static long lastClientShotTime = Long.MIN_VALUE;

	public GlockItem(Properties properties) {
		super(properties);
	}

	public static int getAmmo(ItemStack stack) {
		return stack.getOrDefault(ModComponents.AMMO, 0);
	}

	public static boolean isReloading(ItemStack stack, Level level) {
		return level.getGameTime() < stack.getOrDefault(ModComponents.RELOAD_UNTIL, 0L);
	}

	/** 0 when a reload just started, 1 when it is done. */
	public static float reloadProgress(ItemStack stack, Level level, float partialTick) {
		long until = stack.getOrDefault(ModComponents.RELOAD_UNTIL, 0L);
		float remaining = until - level.getGameTime() - partialTick;
		return 1.0F - Math.max(0.0F, Math.min(1.0F, remaining / RELOAD_TICKS));
	}

	@Override
	public InteractionResult use(Level level, Player player, InteractionHand hand) {
		ItemStack stack = player.getItemInHand(hand);

		if (isReloading(stack, level) || player.getCooldowns().isOnCooldown(stack)) {
			return InteractionResult.FAIL;
		}

		int ammo = getAmmo(stack);

		if (ammo <= 0) {
			if (level instanceof ServerLevel) {
				level.playSound(null, player.getX(), player.getEyeY(), player.getZ(), ModSounds.GLOCK_EMPTY, SoundSource.PLAYERS, 0.8F, 1.0F);
				player.getCooldowns().addCooldown(stack, 8);
			}

			return InteractionResult.FAIL;
		}

		if (level instanceof ServerLevel serverLevel) {
			stack.set(ModComponents.AMMO, ammo - 1);
			player.getCooldowns().addCooldown(stack, FIRE_COOLDOWN_TICKS);
			fire(serverLevel, player);
		} else {
			// Camera kick on the shooter's own client.
			lastClientShotTime = level.getGameTime();
			player.setXRot(player.getXRot() - RECOIL_DEGREES);
			player.setYRot(player.getYRot() + (player.getRandom().nextFloat() - 0.5F) * RECOIL_DEGREES * 0.4F);
		}

		// CONSUME rather than SUCCESS so the arm doesn't do a melee swing.
		return InteractionResult.CONSUME;
	}

	private static void fire(ServerLevel level, Player player) {
		Vec3 start = player.getEyePosition();
		Vec3 direction = player.getViewVector(1.0F).add(
				player.getRandom().triangle(0.0, SPREAD),
				player.getRandom().triangle(0.0, SPREAD),
				player.getRandom().triangle(0.0, SPREAD)).normalize();
		Vec3 end = start.add(direction.scale(RANGE));

		BlockHitResult blockHit = level.clip(new ClipContext(start, end, ClipContext.Block.COLLIDER, ClipContext.Fluid.NONE, player));

		if (blockHit.getType() != HitResult.Type.MISS) {
			end = blockHit.getLocation();
		}

		Entity target = null;
		double closest = Double.MAX_VALUE;
		AABB searchBox = new AABB(start, end).inflate(1.0);

		for (Entity entity : level.getEntities(player, searchBox, e -> e.isPickable() && !e.isSpectator() && e.isAlive())) {
			Optional<Vec3> hit = entity.getBoundingBox().inflate(entity.getPickRadius() + 0.1).clip(start, end);

			if (hit.isPresent()) {
				double distance = start.distanceToSqr(hit.get());

				if (distance < closest) {
					closest = distance;
					target = entity;
				}
			}
		}

		Vec3 muzzle = start.add(direction.scale(0.9)).add(0.0, -0.15, 0.0);
		level.sendParticles(ParticleTypes.SMOKE, muzzle.x, muzzle.y, muzzle.z, 3, 0.02, 0.02, 0.02, 0.01);
		level.playSound(null, player.getX(), player.getEyeY(), player.getZ(), ModSounds.GLOCK_SHOOT, SoundSource.PLAYERS, 1.6F,
				0.95F + player.getRandom().nextFloat() * 0.1F);

		if (target != null) {
			// Let follow-up shots land instead of being eaten by hurt invulnerability.
			target.invulnerableTime = 0;
			target.hurtServer(level, level.damageSources().playerAttack(player), DAMAGE);
			Vec3 at = target.getBoundingBox().getCenter();
			level.sendParticles(ParticleTypes.DAMAGE_INDICATOR, at.x, at.y, at.z, 4, 0.15, 0.15, 0.15, 0.1);
		} else if (blockHit.getType() == HitResult.Type.BLOCK) {
			Vec3 at = blockHit.getLocation();
			BlockParticleOption dust = new BlockParticleOption(ParticleTypes.BLOCK, level.getBlockState(blockHit.getBlockPos()));
			level.sendParticles(dust, at.x, at.y, at.z, 8, 0.05, 0.05, 0.05, 0.1);
			level.sendParticles(ParticleTypes.SMOKE, at.x, at.y, at.z, 2, 0.02, 0.02, 0.02, 0.01);
		}
	}

	/** Server side: refill the magazine in the main hand from 9mm rounds in the inventory. */
	public static void tryReload(ServerPlayer player) {
		ItemStack stack = player.getMainHandItem();

		if (!stack.is(ModItems.GLOCK_19)) {
			return;
		}

		Level level = player.level();
		int ammo = getAmmo(stack);

		if (isReloading(stack, level) || ammo >= MAGAZINE_SIZE) {
			return;
		}

		int needed = MAGAZINE_SIZE - ammo;
		int loaded = player.hasInfiniteMaterials() ? needed : takeRounds(player, needed);

		if (loaded == 0) {
			player.displayClientMessage(Component.translatable("message.glock19.no_ammo"), true);
			level.playSound(null, player.getX(), player.getEyeY(), player.getZ(), ModSounds.GLOCK_EMPTY, SoundSource.PLAYERS, 0.8F, 1.0F);
			return;
		}

		stack.set(ModComponents.AMMO, ammo + loaded);
		stack.set(ModComponents.RELOAD_UNTIL, level.getGameTime() + RELOAD_TICKS);
		player.getCooldowns().addCooldown(stack, RELOAD_TICKS);
		level.playSound(null, player.getX(), player.getEyeY(), player.getZ(), ModSounds.GLOCK_RELOAD, SoundSource.PLAYERS, 1.0F, 1.0F);
	}

	private static int takeRounds(Player player, int wanted) {
		int taken = 0;

		for (int i = 0; i < player.getInventory().getContainerSize() && taken < wanted; i++) {
			ItemStack slot = player.getInventory().getItem(i);

			if (slot.is(ModItems.AMMO_9MM)) {
				int take = Math.min(wanted - taken, slot.getCount());
				slot.shrink(take);
				taken += take;
			}
		}

		return taken;
	}

	/** Counts loose 9mm rounds, for the HUD. */
	public static int countReserve(Player player) {
		int total = 0;

		for (int i = 0; i < player.getInventory().getContainerSize(); i++) {
			ItemStack slot = player.getInventory().getItem(i);

			if (slot.is(ModItems.AMMO_9MM)) {
				total += slot.getCount();
			}
		}

		return total;
	}

	@Override
	public boolean allowComponentsUpdateAnimation(Player player, InteractionHand hand, ItemStack oldStack, ItemStack newStack) {
		// Ammo changes every shot; don't play the re-equip bob each time.
		return false;
	}
}
