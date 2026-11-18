package no.waagan.kontrollsenter;

import android.content.Context;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

/** «Spillstatus»: hva som spilles nå, FPS og temperaturer – og hva de andre i huset spiller. */
public class GameWidget extends KsWidget {
    int layout() { return R.layout.widget_game; }

    void fill(Context c, RemoteViews v, JSONObject d) {
        String game = d.isNull("game") ? "" : d.optString("game", "");
        v.setTextViewText(R.id.w_game, game.isEmpty() ? "Ingen spill nå" : "🎮 " + game);
        v.setTextViewText(R.id.w_fps, d.isNull("fps") || !d.has("fps") ? "–" : String.valueOf(d.optInt("fps")));
        v.setTextViewText(R.id.w_cpu, t(d, "cpu_t"));
        v.setTextViewText(R.id.w_gpu, t(d, "gpu_t"));
        int sec = d.optInt("play_s", 0);
        StringBuilder sub = new StringBuilder("Spilt i dag " + sec / 3600 + " t " + sec % 3600 / 60 + " min");
        JSONArray pcs = d.optJSONArray("pcs");
        for (int i = 0; pcs != null && i < pcs.length(); i++) {
            JSONObject p = pcs.optJSONObject(i);
            if (p == null || p.optBoolean("me")) continue;
            String g = p.isNull("game") ? "" : p.optString("game", "");
            if (p.optBoolean("on") && !g.isEmpty() && !"null".equals(g)) sub.append(" · ").append(p.optString("name")).append(": ").append(g);
        }
        v.setTextViewText(R.id.w_sub, sub.toString());
    }
}
