package no.waagan.kontrollsenter;

import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

import org.json.JSONObject;

/** Hurtigflis (også fra låseskjermen): demp lyden på PC-en av/på. */
public class MuteTile extends TileService {
    @Override
    public void onStartListening() {
        new Thread(() -> {
            try {
                boolean m = Net.widgets(this).optBoolean("mute");
                show(m, m ? "Dempet" : "Lyd på");
            } catch (Exception e) {
                show(false, "PC-en svarer ikke");
            }
        }).start();
    }

    @Override
    public void onClick() {
        Tile t = getQsTile();
        boolean mute = t != null && t.getState() != Tile.STATE_ACTIVE;
        new Thread(() -> {
            try {
                Net.action(this, new JSONObject().put("a", "volume").put("mute", mute));
                show(mute, mute ? "Dempet" : "Lyd på");
            } catch (Exception e) {
                show(!mute, "Feil: " + e.getMessage());
            }
        }).start();
    }

    void show(boolean on, String sub) {
        Tile t = getQsTile();
        if (t == null) return;
        t.setLabel("Demp PC-en");
        if (Build.VERSION.SDK_INT >= 29) t.setSubtitle(sub);
        t.setState(on ? Tile.STATE_ACTIVE : Tile.STATE_INACTIVE);
        t.updateTile();
    }
}
