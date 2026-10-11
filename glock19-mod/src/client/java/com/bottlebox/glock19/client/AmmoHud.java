package com.bottlebox.glock19.client;

import net.minecraft.client.DeltaTracker;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;

import com.bottlebox.glock19.ModItems;
import com.bottlebox.glock19.item.GlockItem;

/** Ammo panel shown while a Glock 19 is in the main hand. */
public final class AmmoHud {
	private static final int PANEL = 0xB0101014;
	private static final int BORDER = 0xFF3A3D44;
	private static final int TEXT = 0xFFF2F2F2;
	private static final int DIM = 0xFF9A9EA6;
	private static final int LOW = 0xFFFF5A4E;
	private static final int ACCENT = 0xFFE8B04A;

	private static final int WIDTH = 104;
	private static final int HEIGHT = 34;

	private AmmoHud() {
	}

	public static void render(GuiGraphics graphics, DeltaTracker deltaTracker) {
		Minecraft mc = Minecraft.getInstance();
		LocalPlayer player = mc.player;

		if (player == null || mc.level == null || mc.options.hideGui) {
			return;
		}

		ItemStack stack = player.getMainHandItem();

		if (!stack.is(ModItems.GLOCK_19)) {
			return;
		}

		Font font = mc.font;
		int ammo = GlockItem.getAmmo(stack);
		int reserve = player.hasInfiniteMaterials() ? -1 : GlockItem.countReserve(player);
		boolean reloading = GlockItem.isReloading(stack, mc.level);

		// Bottom left, so the gun in the bottom-right corner stays visible.
		int x = 6;
		int y = graphics.guiHeight() - HEIGHT - 6;

		graphics.fill(x, y, x + WIDTH, y + HEIGHT, PANEL);
		graphics.fill(x, y, x + WIDTH, y + 1, BORDER);
		graphics.fill(x, y + HEIGHT - 1, x + WIDTH, y + HEIGHT, BORDER);
		graphics.fill(x, y, x + 1, y + HEIGHT, BORDER);
		graphics.fill(x + WIDTH - 1, y, x + WIDTH, y + HEIGHT, BORDER);

		graphics.renderItem(stack, x + 5, y + 9);

		// Big magazine count, scaled 2x.
		String mag = String.valueOf(ammo);
		int magColor = ammo == 0 ? LOW : ammo <= 5 ? ACCENT : TEXT;
		graphics.pose().pushMatrix();
		graphics.pose().translate(x + 26, y + 6);
		graphics.pose().scale(2.0F, 2.0F);
		graphics.drawString(font, mag, 0, 0, magColor, true);
		graphics.pose().popMatrix();

		int textX = x + 28 + font.width(mag) * 2;
		graphics.drawString(font, "/ " + GlockItem.MAGAZINE_SIZE, textX, y + 7, DIM, true);
		graphics.drawString(font, reserve < 0 ? "∞" : "+" + reserve, textX, y + 17, DIM, true);

		// Round pips, one per bullet left in the magazine.
		int pipsX = x + 26;
		int pipsY = y + HEIGHT - 6;

		for (int i = 0; i < GlockItem.MAGAZINE_SIZE; i++) {
			int color = i < ammo ? ACCENT : 0xFF2A2C31;
			graphics.fill(pipsX + i * 5, pipsY, pipsX + i * 5 + 3, pipsY + 3, color);
		}

		if (reloading) {
			float progress = GlockItem.reloadProgress(stack, mc.level, deltaTracker.getGameTimeDeltaPartialTick(false));
			int barY = y - 12;
			graphics.fill(x, barY, x + WIDTH, barY + 10, PANEL);
			graphics.fill(x + 1, barY + 1, x + 1 + Math.round((WIDTH - 2) * progress), barY + 9, 0xC0E8B04A);
			graphics.drawCenteredString(font, Component.translatable("hud.glock19.reloading"), x + WIDTH / 2, barY + 1, TEXT);
		} else if (ammo == 0) {
			graphics.drawCenteredString(font, Component.translatable("hud.glock19.press_reload", Glock19Client.RELOAD.getTranslatedKeyMessage()), x + WIDTH / 2, y - 11, LOW);
		}
	}
}
