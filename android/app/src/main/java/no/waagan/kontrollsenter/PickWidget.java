package no.waagan.kontrollsenter;

import android.content.Context;
import android.content.SharedPreferences;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

/** «Velg selv»: fire fliser du velger når du legger widgeten på hjemskjermen. */
public class PickWidget extends KsWidget {
    static final String[] KEYS = {"cpu", "gpu", "watt", "ping", "price", "weather", "play", "kwh", "battery", "event"};
    static final String[] NAMES = {"CPU-temperatur", "GPU-temperatur", "Strømforbruk", "Ping", "Strømpris nå", "Været",
            "Spilt i dag", "Strøm i dag (kWh)", "Batteri (mus/headset)", "Neste avtale"};
    static final String[] DEFAULT = {"cpu", "gpu", "price", "weather"};
    static final int[][] CELLS = {{R.id.p1n, R.id.p1v}, {R.id.p2n, R.id.p2v}, {R.id.p3n, R.id.p3v}, {R.id.p4n, R.id.p4v}};

    int layout() { return R.layout.widget_pick; }

    static String[] choice(Context c) {
        SharedPreferences p = c.getSharedPreferences("ks", 0);
        String s = p.getString("pick_tiles", "");
        return s.isEmpty() ? DEFAULT : s.split(",");
    }

    static String label(String k) {
        for (int i = 0; i < KEYS.length; i++) if (KEYS[i].equals(k)) return NAMES[i];
        return k;
    }

    static String value(JSONObject d, String k) {
        switch (k) {
            case "cpu": return t(d, "cpu_t");
            case "gpu": return t(d, "gpu_t");
            case "watt": return d.optInt("watts", 0) + " W";
            case "ping": return d.isNull("ping_ms") || !d.has("ping_ms") ? "–" : d.optInt("ping_ms") + " ms";
            case "price": return d.isNull("price_now") || !d.has("price_now") ? "–" : String.format("%.2f kr", d.optDouble("price_now"));
            case "weather": return d.has("weather") ? str(d, "weather") : "–";
            case "play": {
                int s = d.optInt("play_s", 0);
                return (s / 3600) + " t " + (s % 3600 / 60) + " m";
            }
            case "kwh": return d.has("kwh") ? d.optDouble("kwh") + " kWh" : "–";
            case "battery": {
                JSONArray b = d.optJSONArray("batteries");
                if (b == null || b.length() == 0) return "–";
                JSONObject x = b.optJSONObject(0);
                boolean chg = x.optBoolean("charging");
                return (chg ? "⚡" : "") + (x.isNull("pct") ? "av" : x.optInt("pct") + " %");
            }
            case "event": return d.has("next_event") ? str(d, "next_event") : "–";
        }
        return "–";
    }

    void fill(Context c, RemoteViews v, JSONObject d) {
        String[] ch = choice(c);
        for (int i = 0; i < CELLS.length; i++) {
            String k = i < ch.length ? ch[i] : DEFAULT[i];
            v.setTextViewText(CELLS[i][0], label(k).toUpperCase());
            v.setTextViewText(CELLS[i][1], value(d, k));
        }
        v.setTextViewText(R.id.w_title, str(d, "name"));
    }
}
