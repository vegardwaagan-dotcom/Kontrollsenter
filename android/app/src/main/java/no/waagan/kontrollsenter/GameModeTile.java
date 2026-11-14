package no.waagan.kontrollsenter;

import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

import org.json.JSONObject;

/** Hurtigflis: spillmodus på PC-en av/på (max ytelse, viftekurve, overlay, varsler av). */
public class GameModeTile extends TileService {
    @Override
    public void onStartListening() {
        new Thread(() -> {
            try {
                boolean on = Net.status(this).optBoolean("gamemode");
                show(on, on ? "På" : "Av");
            } catch (Exception e) {
                show(false, "PC-en svarer ikke");
            }
        }).start();
    }

    @Override
    public void onClick() {
        Tile t = getQsTile();
        boolean on = t != null && t.getState() != Tile.STATE_ACTIVE;
        new Thread(() -> {
            try {
                Net.action(this, new JSONObject().put("a", "gamemode").put("on", on));
                show(on, on ? "På" : "Av");
            } catch (Exception e) {
                show(!on, "Feil: " + e.getMessage());
            }
        }).start();
    }

    void show(boolean on, String sub) {
        Tile t = getQsTile();
        if (t == null) return;
        t.setLabel("Spillmodus");
        if (Build.VERSION.SDK_INT >= 29) t.setSubtitle(sub);
        t.setState(on ? Tile.STATE_ACTIVE : Tile.STATE_INACTIVE);
        t.updateTile();
    }
}
