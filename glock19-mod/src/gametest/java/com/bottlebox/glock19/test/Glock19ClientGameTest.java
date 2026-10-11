package com.bottlebox.glock19.test;

import org.lwjgl.glfw.GLFW;
import org.spongepowered.asm.mixin.MixinEnvironment;

import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.gametest.v1.context.TestSingleplayerContext;

import net.minecraft.client.CameraType;
import net.minecraft.client.gui.screens.worldselection.WorldCreationUiState;

/** Screenshots the gun in first and third person, firing and mid-reload. */
public class Glock19ClientGameTest implements FabricClientGameTest {
	@Override
	public void runTest(ClientGameTestContext context) {
		// Fails the run if any mixin can't find its target.
		MixinEnvironment.getCurrentEnvironment().audit();

		try (TestSingleplayerContext world = context.worldBuilder()
				.adjustSettings(creator -> creator.setGameMode(WorldCreationUiState.SelectedGameMode.SURVIVAL))
				.create()) {
			world.getServer().runCommand("time set noon");
			world.getServer().runCommand("weather clear");
			world.getServer().runCommand("execute as @a at @s run tp @s ~ ~ ~ 0 0");
			world.getServer().runCommand("item replace entity @a hotbar.0 with glock19:glock_19");
			world.getServer().runCommand("give @a glock19:ammo_9mm 32");
			world.getClientWorld().waitForChunksRender();
			context.waitTicks(20);

			context.takeScreenshot("fp_idle");

			context.getInput().pressMouse(GLFW.GLFW_MOUSE_BUTTON_RIGHT);
			context.waitTick();
			context.takeScreenshot("fp_recoil");
			context.waitTicks(10);

			context.getInput().pressKey(GLFW.GLFW_KEY_R);
			context.waitTicks(7);
			context.takeScreenshot("fp_reload_mag_out");
			context.waitTicks(5);
			context.takeScreenshot("fp_reload_mag_in");
			context.waitTicks(10);
			context.takeScreenshot("fp_reload_slide");
			context.waitTicks(20);

			// Armor stands show the third-person hold from the side and at an angle.
			world.getServer().runCommand("execute at @p run summon armor_stand ~-1 ~ ~3 {ShowArms:1b,NoGravity:1b,Rotation:[90f,0f],"
					+ "equipment:{mainhand:{id:\"glock19:glock_19\",count:1}}}");
			world.getServer().runCommand("execute at @p run summon armor_stand ~1.5 ~ ~3.5 {ShowArms:1b,NoGravity:1b,Rotation:[135f,0f],"
					+ "equipment:{mainhand:{id:\"glock19:glock_19\",count:1}}}");
			world.getServer().runCommand("execute as @a at @s run tp @s ~ ~ ~ 0 15");
			context.waitTicks(5);
			context.takeScreenshot("tp_armor_stands");
			world.getServer().runCommand("execute as @a at @s run tp @s ~ ~ ~ 0 0");

			setCamera(context, CameraType.THIRD_PERSON_FRONT);
			context.takeScreenshot("tp_front");
			setCamera(context, CameraType.THIRD_PERSON_BACK);
			context.takeScreenshot("tp_back");
			setCamera(context, CameraType.FIRST_PERSON);
		}
	}

	private static void setCamera(ClientGameTestContext context, CameraType type) {
		context.runOnClient(client -> client.options.setCameraType(type));
		context.waitTicks(2);
	}
}
