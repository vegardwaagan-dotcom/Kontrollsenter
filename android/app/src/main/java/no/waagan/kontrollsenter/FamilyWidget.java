package no.waagan.kontrollsenter;

import android.content.Context;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

/** «Familien»: hva de andre PC-ene spiller, og «Middag!» til alle. */
public class FamilyWidget extends KsWidget {
    static final int[] ROWS = {R.id.f1, R.id.f2, R.id.f3, R.id.f4, R.id.f5};

    int layout() { return R.layout.widget_family; }

    void fill(Context c, RemoteViews v, JSONObject d) {
        JSONArray pcs = d.optJSONArray("pcs");
        int n = 0;
        for (int i = 0; pcs != null && i < pcs.length() && n < ROWS.length; i++) {
            JSONObject p = pcs.optJSONObject(i);
            if (p == null) continue;
            boolean on = p.optBoolean("on");
            String game = p.optString("game", "");
            String what = !on ? "av" : (!game.isEmpty() && !"null".equals(game) ? "🎮 " + game : "på");
            if (on && !p.isNull("t")) what += "  ·  " + Math.round(p.optDouble("t")) + "°";
            v.setTextViewText(ROWS[n], (on ? "🟢  " : "⚫  ") + p.optString("name") + (p.optBoolean("me") ? " (denne)" : "") + "   " + what);
            v.setViewVisibility(ROWS[n], View.VISIBLE);
            n++;
        }
        for (int i = n; i < ROWS.length; i++) v.setViewVisibility(ROWS[i], View.GONE);
        v.setOnClickPendingIntent(R.id.w_dinner, action(c, FamilyWidget.class, 21, "{\"a\":\"dinner\",\"to\":\"*\"}"));
    }
}
