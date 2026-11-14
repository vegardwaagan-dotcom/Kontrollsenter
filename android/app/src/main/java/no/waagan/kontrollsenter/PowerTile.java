package no.waagan.kontrollsenter;

import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

import org.json.JSONObject;

/** Hurtigflis i nedtrekksmenyen: bytt strømmodus på PC-en (Strømsparing → Balansert → Max Ytelse). */
public class PowerTile extends TileService {
    static final String[] MODES = {"power-saver", "balanced", "performance"};
    static final String[] NAMES = {"Strømsparing", "Balansert", "Max Ytelse"};

    @Override
    public void onStartListening() {
        new Thread(() -> {
            String sub;
            try {
                JSONObject p = Net.status(this).optJSONObject("power");
                String act = p == null ? "" : p.optString("active");
                sub = name(act);
            } catch (Exception e) {
                sub = "PC-en svarer ikke";
            }
            show(sub, Tile.STATE_ACTIVE);
        }).start();
    }

    @Override
    public void onClick() {
        new Thread(() -> {
            try {
                JSONObject p = Net.status(this).optJSONObject("power");
                String act = p == null ? "" : p.optString("active");
                int i = 0;
                for (int k = 0; k < MODES.length; k++) if (MODES[k].equals(act)) i = (k + 1) % MODES.length;
                Net.action(this, new JSONObject().put("a", "power").put("mode", MODES[i]));
                show(NAMES[i], Tile.STATE_ACTIVE);
            } catch (Exception e) {
                show("Feil: " + e.getMessage(), Tile.STATE_INACTIVE);
            }
        }).start();
    }

    static String name(String key) {
        for (int k = 0; k < MODES.length; k++) if (MODES[k].equals(key)) return NAMES[k];
        return "–";
    }

    void show(String sub, int state) {
        Tile t = getQsTile();
        if (t == null) return;
        t.setLabel("Strømmodus");
        if (Build.VERSION.SDK_INT >= 29) t.setSubtitle(sub);
        else t.setLabel("Strøm: " + sub);
        t.setState(state);
        t.updateTile();
    }
}
