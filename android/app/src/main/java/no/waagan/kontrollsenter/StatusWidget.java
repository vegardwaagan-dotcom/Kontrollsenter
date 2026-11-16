package no.waagan.kontrollsenter;

import android.content.Context;
import android.widget.RemoteViews;

import org.json.JSONObject;

/** «Kontrollsenter»: PC-navn, CPU/GPU/strøm og spillet som kjører. */
public class StatusWidget extends KsWidget {
    int layout() { return R.layout.widget; }

    void fill(Context c, RemoteViews v, JSONObject d) {
        v.setTextViewText(R.id.w_name, str(d, "name"));
        v.setTextViewText(R.id.w_cpu, t(d, "cpu_t"));
        v.setTextViewText(R.id.w_gpu, t(d, "gpu_t"));
        v.setTextViewText(R.id.w_watt, d.optInt("watts", 0) + " W");
        String game = str(d, "game");
        v.setTextViewText(R.id.w_sub, !game.isEmpty() ? "🎮 " + game : str(d, "mode_name") + (d.optBoolean("gamemode") ? " · spillmodus" : ""));
    }

    /** Eldre kall fra bakgrunnssjekken. */
    static void refresh(Context c) { refreshAll(c); }
}
