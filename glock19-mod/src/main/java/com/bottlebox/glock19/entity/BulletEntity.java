package com.bottlebox.glock19.entity;

import net.minecraft.core.particles.BlockParticleOption;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.projectile.throwableitemprojectile.ThrowableItemProjectile;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import com.bottlebox.glock19.ModEntities;
import com.bottlebox.glock19.ModItems;
import com.bottlebox.glock19.ModSounds;

/** A 9mm round in flight. Rendered as a bullet with a glowing tracer behind it. */
public class BulletEntity extends ThrowableItemProjectile {
	public static final float DAMAGE = 6.0F;
	private static final int MAX_AGE_TICKS = 40;

	public BulletEntity(EntityType<? extends BulletEntity> type, Level level) {
		super(type, level);
	}

	public BulletEntity(Level level, LivingEntity owner, ItemStack stack) {
		super(ModEntities.BULLET, owner, level, stack);
	}

	@Override
	protected Item getDefaultItem() {
		return ModItems.AMMO_9MM;
	}

	@Override
	protected double getDefaultGravity() {
		// A little drop so long shots arc, far less than an arrow.
		return 0.006;
	}

	@Override
	public void tick() {
		super.tick();

		if (!this.level().isClientSide() && this.tickCount > MAX_AGE_TICKS) {
			this.discard();
		}
	}

	@Override
	protected void onHitEntity(EntityHitResult result) {
		super.onHitEntity(result);

		if (this.level() instanceof ServerLevel level) {
			Entity target = result.getEntity();
			// Let follow-up shots land instead of being eaten by hurt invulnerability.
			target.invulnerableTime = 0;
			target.hurtServer(level, this.damageSources().thrown(this, this.getOwner()), DAMAGE);
			Vec3 at = result.getLocation();
			level.sendParticles(ParticleTypes.DAMAGE_INDICATOR, at.x, at.y, at.z, 4, 0.1, 0.1, 0.1, 0.1);
		}
	}

	@Override
	protected void onHitBlock(BlockHitResult result) {
		super.onHitBlock(result);

		if (this.level() instanceof ServerLevel level) {
			Vec3 at = result.getLocation();
			BlockParticleOption chips = new BlockParticleOption(ParticleTypes.BLOCK, level.getBlockState(result.getBlockPos()));
			level.sendParticles(chips, at.x, at.y, at.z, 10, 0.05, 0.05, 0.05, 0.15);
			level.playSound(null, at.x, at.y, at.z, ModSounds.BULLET_IMPACT, SoundSource.PLAYERS, 0.9F,
					0.9F + this.random.nextFloat() * 0.2F);
		}
	}

	@Override
	protected void onHit(HitResult result) {
		super.onHit(result);

		if (!this.level().isClientSide()) {
			this.discard();
		}
	}
}
