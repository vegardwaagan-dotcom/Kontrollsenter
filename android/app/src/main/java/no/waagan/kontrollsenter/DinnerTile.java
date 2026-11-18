package no.waagan.kontrollsenter;

import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

import org.json.JSONObject;

/** Hurtigflis (også fra låseskjermen): send «Middag!» til alle PC-ene i huset. */
public class DinnerTile extends TileService {
    @Override
    public void onStartListening() {
        show("Send til alle PC-ene");
    }

    @Override
    public void onClick() {
        show("Sender …");
        new Thread(() -> {
            try {
                Net.action(this, new JSONObject().put("a", "dinner"));
                show("Sendt ✓");
            } catch (Exception e) {
                show("PC-en svarer ikke");
            }
        }).start();
    }

    void show(String sub) {
        Tile t = getQsTile();
        if (t == null) return;
        t.setLabel("Middag!");
        if (Build.VERSION.SDK_INT >= 29) t.setSubtitle(sub);
        t.setState(Tile.STATE_INACTIVE);
        t.updateTile();
    }
}
