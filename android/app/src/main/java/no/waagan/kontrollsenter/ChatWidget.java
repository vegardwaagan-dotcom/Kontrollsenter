package no.waagan.kontrollsenter;

import android.content.Context;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

/** Chat-widget (30): de tre siste meldingene, og hurtigsvar til den siste samtalen. */
public class ChatWidget extends KsWidget {
    static final int[] ROWS = {R.id.c1, R.id.c2, R.id.c3};

    int layout() { return R.layout.widget_chat; }

    void fill(Context c, RemoteViews v, JSONObject d) {
        JSONArray a = d.optJSONArray("chat");
        int n = 0;
        String room = null;
        for (int i = 0; a != null && i < a.length() && n < ROWS.length; i++) {
            JSONObject m = a.optJSONObject(i);
            if (m == null) continue;
            if (room == null) room = m.optString("room");
            v.setTextViewText(ROWS[n], m.optString("from") + ": " + m.optString("text"));
            v.setViewVisibility(ROWS[n], View.VISIBLE);
            n++;
        }
        for (int i = n; i < ROWS.length; i++) v.setViewVisibility(ROWS[i], View.GONE);
        if (n == 0) {
            v.setTextViewText(R.id.c1, "Ingen nye meldinger");
            v.setViewVisibility(R.id.c1, View.VISIBLE);
        }
        String r = room == null ? "alle" : room;
        try {
            v.setOnClickPendingIntent(R.id.w_q1, action(c, ChatWidget.class, 31,
                    new JSONObject().put("a", "chat2").put("room", r).put("text", "Kommer! 🏃").toString()));
            v.setOnClickPendingIntent(R.id.w_q2, action(c, ChatWidget.class, 32,
                    new JSONObject().put("a", "chat2").put("room", r).put("text", "5 min til ⏳").toString()));
        } catch (Exception e) {
            // ugyldig JSON – skjer ikke
        }
    }
}
