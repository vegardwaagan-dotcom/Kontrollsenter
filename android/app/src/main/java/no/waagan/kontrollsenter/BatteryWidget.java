package no.waagan.kontrollsenter;

import android.content.Context;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

/** «Batterier»: mus, tastatur og hodesett. */
public class BatteryWidget extends KsWidget {
    static final int[][] ROWS = {{R.id.b1, R.id.b1n, R.id.b1p, R.id.b1v}, {R.id.b2, R.id.b2n, R.id.b2p, R.id.b2v},
            {R.id.b3, R.id.b3n, R.id.b3p, R.id.b3v}};

    int layout() { return R.layout.widget_battery; }

    void fill(Context c, RemoteViews v, JSONObject d) {
        JSONArray b = d.optJSONArray("batteries");
        int n = b == null ? 0 : Math.min(b.length(), ROWS.length);
        for (int i = 0; i < ROWS.length; i++) {
            if (i >= n) {
                v.setViewVisibility(ROWS[i][0], View.GONE);
                continue;
            }
            JSONObject x = b.optJSONObject(i);
            String kind = x.optString("kind");
            String icon = "headset".equals(kind) ? "🎧" : "keyboard".equals(kind) ? "⌨️" : "🖱️";
            v.setViewVisibility(ROWS[i][0], View.VISIBLE);
            v.setTextViewText(ROWS[i][1], icon + "  " + x.optString("name"));
            boolean has = x.has("pct") && !x.isNull("pct");
            int pct = has ? x.optInt("pct") : 0;
            v.setProgressBar(ROWS[i][2], 100, has ? pct : (x.optBoolean("charging") || x.optBoolean("full") ? 100 : 0), false);
            boolean chg = x.optBoolean("charging"), full = x.optBoolean("full");
            v.setTextViewText(ROWS[i][3], (chg ? "⚡ " : full ? "🔌 " : "") + (has ? pct + " %" : chg ? "lader" : "av"));
            v.setTextColor(ROWS[i][3], chg || full ? 0xFF57E389 : 0xFFFFFFFF);
        }
        v.setViewVisibility(R.id.w_none, n == 0 ? View.VISIBLE : View.GONE);
    }
}
