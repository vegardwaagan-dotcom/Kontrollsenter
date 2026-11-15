package no.waagan.kontrollsenter;

import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

import org.json.JSONObject;

/** Hurtigflis: lagre de siste sekundene av spillet som klipp (som F8 på PC-en). */
public class ClipTile extends TileService {
    @Override
    public void onStartListening() {
        show("Siste minutt", Tile.STATE_INACTIVE);
    }

    @Override
    public void onClick() {
        show("Lagrer …", Tile.STATE_ACTIVE);
        new Thread(() -> {
            try {
                JSONObject r = Net.action(this, new JSONObject().put("a", "clip"));
                show(r.optBoolean("ok") ? "Lagret ✓" : r.optString("msg", "Feil"), Tile.STATE_INACTIVE);
            } catch (Exception e) {
                show("Feil: " + e.getMessage(), Tile.STATE_INACTIVE);
            }
        }).start();
    }

    void show(String sub, int state) {
        Tile t = getQsTile();
        if (t == null) return;
        t.setLabel("Lagre klipp");
        if (Build.VERSION.SDK_INT >= 29) t.setSubtitle(sub);
        t.setState(state);
        t.updateTile();
    }
}
