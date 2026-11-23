package no.waagan.kontrollsenter;

import android.content.Context;
import android.widget.RemoteViews;

import org.json.JSONObject;

/** «Kalender»: i dag (dato og uke), dagens hendelser og neste røde dag – fra kalenderen på PC-en. */
public class CalendarWidget extends KsWidget {
    int layout() { return R.layout.widget_calendar; }

    void fill(Context c, RemoteViews v, JSONObject d) {
        v.setTextViewText(R.id.w_big, str(d, "cal_date"));
        String today = str(d, "cal_today");
        v.setTextViewText(R.id.w_today, today.isEmpty() ? "Ingenting i dag" : today);
        v.setTextViewText(R.id.w_sub, str(d, "cal_red"));
        v.setTextViewText(R.id.w_name, str(d, "name"));
    }
}
