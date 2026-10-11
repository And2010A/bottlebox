package com.bottlebox.glock19.item;

import net.minecraft.core.component.DataComponents;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.HumanoidArm;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import com.bottlebox.glock19.Glock19Mod;
import com.bottlebox.glock19.ModComponents;
import com.bottlebox.glock19.ModItems;
import com.bottlebox.glock19.ModSounds;
import com.bottlebox.glock19.entity.BulletEntity;

public class GlockItem extends Item {
	public static final int MAGAZINE_SIZE = 15;
	public static final int RELOAD_TICKS = 32;
	private static final int FIRE_COOLDOWN_TICKS = 3;
	private static final double RANGE = 64.0;
	/** Blocks per tick: slow enough that the tracer is visible in flight. */
	private static final float BULLET_SPEED = 3.5F;
	private static final float BULLET_INACCURACY = 0.4F;
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
			return InteractionResult.CONSUME;
		}

		// Camera kick on the shooter's own client.
		lastClientShotTime = level.getGameTime();
		player.setXRot(player.getXRot() - RECOIL_DEGREES);
		player.setYRot(player.getYRot() + (player.getRandom().nextFloat() - 0.5F) * RECOIL_DEGREES * 0.4F);

		// The use packet has already gone to the server. A success here would make vanilla play its
		// lower-and-raise "item used" bob over our own recoil animation, so report no result instead.
		return InteractionResult.FAIL;
	}

	private static void fire(ServerLevel level, Player player) {
		Vec3 eye = player.getEyePosition();
		Vec3 look = player.getViewVector(1.0F);

		// Aim at whatever is under the crosshair, so the bullet converges on it from the muzzle.
		Vec3 far = eye.add(look.scale(RANGE));
		BlockHitResult aimHit = level.clip(new ClipContext(eye, far, ClipContext.Block.COLLIDER, ClipContext.Fluid.NONE, player));
		Vec3 aim = aimHit.getType() == HitResult.Type.MISS ? far : aimHit.getLocation();

		// The muzzle sits forward, to the gun-hand side and a little below the eyes.
		float side = player.getMainArm() == HumanoidArm.RIGHT ? 1.0F : -1.0F;
		Vec3 right = new Vec3(-look.z, 0.0, look.x).normalize().scale(side);
		Vec3 muzzle = eye.add(look.scale(0.6)).add(right.scale(0.22)).add(0.0, -0.16, 0.0);
		Vec3 direction = aim.subtract(muzzle).normalize();

		ItemStack round = new ItemStack(ModItems.AMMO_9MM);
		round.set(DataComponents.ITEM_MODEL, Glock19Mod.id("bullet"));
		BulletEntity bullet = new BulletEntity(level, player, round);
		bullet.setPos(muzzle);
		bullet.shoot(direction.x, direction.y, direction.z, BULLET_SPEED, BULLET_INACCURACY);
		level.addFreshEntity(bullet);

		level.playSound(null, player.getX(), player.getEyeY(), player.getZ(), ModSounds.GLOCK_SHOOT, SoundSource.PLAYERS, 1.6F,
				0.95F + player.getRandom().nextFloat() * 0.1F);
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
