package no.waagan.kontrollsenter;

import android.content.Context;
import android.widget.RemoteViews;

import org.json.JSONObject;

/** «Hurtigknapper»: spillmodus, lagre klipp, lås PC-en og demp lyden. Spillmodus og Demp blir lilla når de er på. */
public class QuickWidget extends KsWidget {
    int layout() { return R.layout.widget_quick; }

    void fill(Context c, RemoteViews v, JSONObject d) {
        boolean gm = d.optBoolean("gamemode");
        v.setInt(R.id.q1, "setBackgroundResource", gm ? R.drawable.widget_btn_on : R.drawable.widget_btn);
        v.setOnClickPendingIntent(R.id.q1, action(c, QuickWidget.class, 11, "{\"a\":\"gamemode\",\"on\":" + !gm + "}"));
        v.setOnClickPendingIntent(R.id.q2, action(c, QuickWidget.class, 12, "{\"a\":\"clip\"}"));
        v.setOnClickPendingIntent(R.id.q3, action(c, QuickWidget.class, 13, "{\"a\":\"system\",\"do\":\"lock\"}"));
        boolean mute = d.optBoolean("mute");
        v.setInt(R.id.q4, "setBackgroundResource", mute ? R.drawable.widget_btn_on : R.drawable.widget_btn);
        v.setOnClickPendingIntent(R.id.q4, action(c, QuickWidget.class, 14, "{\"a\":\"volume\",\"mute\":" + !mute + "}"));
        v.setTextViewText(R.id.w_name, str(d, "name"));
    }
}
