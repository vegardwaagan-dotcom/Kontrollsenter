package no.waagan.kontrollsenter;

import android.content.Context;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONObject;

/** «Spilletid i dag»: tid spilt, grensen og hvor mye som er brukt. */
public class PlaytimeWidget extends KsWidget {
    int layout() { return R.layout.widget_playtime; }

    void fill(Context c, RemoteViews v, JSONObject d) {
        int s = d.optInt("play_s", 0);
        v.setTextViewText(R.id.w_big, (s / 3600) + " t " + ((s % 3600) / 60) + " min");
        double lim = d.isNull("limit_h") ? 0 : d.optDouble("limit_h", 0);
        if (lim > 0) {
            v.setViewVisibility(R.id.w_bar, View.VISIBLE);
            v.setProgressBar(R.id.w_bar, 1000, (int) Math.min(1000, s / (lim * 3600) * 1000), false);
            v.setTextViewText(R.id.w_sub, "Grense i dag: " + (lim == Math.floor(lim) ? String.valueOf((int) lim) : String.valueOf(lim)) + " t");
        } else {
            v.setViewVisibility(R.id.w_bar, View.GONE);
            String top = str(d, "top_game");
            v.setTextViewText(R.id.w_sub, top.isEmpty() ? "Ingen grense i dag" : "Mest: " + top);
        }
        v.setTextViewText(R.id.w_name, str(d, "name"));
    }
}
