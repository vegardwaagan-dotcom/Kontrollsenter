package no.waagan.kontrollsenter;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONObject;

/** Felles for alle widgetene på hjemmeskjermen: én henting fra PC-en (/api/widgets) tegner alle. */
abstract class KsWidget extends AppWidgetProvider {
    static final String ACT = "no.waagan.kontrollsenter.WIDGET_ACTION";
    static final Class<?>[] ALL = {StatusWidget.class, TempWidget.class, QuickWidget.class, FamilyWidget.class,
            BatteryWidget.class, PlaytimeWidget.class, PickWidget.class, GameWidget.class, ChatWidget.class};

    abstract int layout();

    abstract void fill(Context c, RemoteViews v, JSONObject d);

    @Override
    public void onUpdate(Context c, AppWidgetManager m, int[] ids) {
        PendingResult pr = goAsync();
        new Thread(() -> {
            try {
                refreshAll(c);
            } finally {
                pr.finish();
            }
        }).start();
    }

    @Override
    public void onReceive(Context c, Intent i) {
        if (ACT.equals(i.getAction())) {                       // en knapp i widgeten
            PendingResult pr = goAsync();
            new Thread(() -> {
                try {
                    Net.action(c, new JSONObject(i.getStringExtra("body")));
                    Thread.sleep(700);
                } catch (Exception e) {
                    // vises som «svarer ikke» ved neste oppdatering
                } finally {
                    refreshAll(c);
                    pr.finish();
                }
            }).start();
            return;
        }
        super.onReceive(c, i);
    }

    /** Hent data én gang og tegn alle widgetene (kalles også fra bakgrunnssjekken). */
    static void refreshAll(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        boolean any = false;
        for (Class<?> k : ALL) if (m.getAppWidgetIds(new ComponentName(c, k)).length > 0) any = true;
        if (!any) return;
        JSONObject d = null;
        String err = null;
        try {
            d = Net.widgets(c);
        } catch (Exception e) {
            err = e.getMessage();
        }
        for (Class<?> k : ALL) {
            int[] ids = m.getAppWidgetIds(new ComponentName(c, k));
            if (ids.length == 0) continue;
            KsWidget w;
            try {
                w = (KsWidget) k.getDeclaredConstructor().newInstance();
            } catch (Exception e) {
                continue;
            }
            for (int id : ids) {
                RemoteViews v = new RemoteViews(c.getPackageName(), w.layout());
                v.setOnClickPendingIntent(R.id.w_root, open(c));
                if (d != null) {
                    v.setViewVisibility(R.id.w_err, View.GONE);
                    try {
                        w.fill(c, v, d);
                    } catch (Exception e) {
                        v.setViewVisibility(R.id.w_err, View.VISIBLE);
                        v.setTextViewText(R.id.w_err, "Feil: " + e.getMessage());
                    }
                } else {
                    v.setViewVisibility(R.id.w_err, View.VISIBLE);
                    v.setTextViewText(R.id.w_err, "PC-en svarer ikke" + (err != null && !err.isEmpty() ? " – " + err : ""));
                }
                m.updateAppWidget(id, v);
            }
        }
    }

    static PendingIntent open(Context c) {
        Intent i = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return PendingIntent.getActivity(c, 3, i, PendingIntent.FLAG_IMMUTABLE);
    }

    static PendingIntent action(Context c, Class<?> k, int req, String body) {
        Intent i = new Intent(c, k).setAction(ACT).putExtra("body", body);
        return PendingIntent.getBroadcast(c, req, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    static String t(JSONObject d, String key) {
        Object o = d.opt(key);
        if (o instanceof Number) return Math.round(((Number) o).doubleValue()) + "°";
        return "–";
    }

    static String str(JSONObject d, String key) {
        String s = d.optString(key, "");
        return "null".equals(s) ? "" : s;
    }
}
