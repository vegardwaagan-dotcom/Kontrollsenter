package no.waagan.kontrollsenter;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import org.json.JSONObject;

/** Widget på hjemmeskjermen: PC-ens temperaturer, last, watt og spillet som kjører. */
public class StatusWidget extends AppWidgetProvider {
    @Override
    public void onUpdate(Context c, AppWidgetManager m, int[] ids) {
        PendingResult pr = goAsync();
        new Thread(() -> {
            try {
                refresh(c);
            } finally {
                pr.finish();
            }
        }).start();
    }

    /** Hent status og tegn alle widgetene (kalles også fra bakgrunnssjekken hvert 15. minutt). */
    static void refresh(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        int[] ids = m.getAppWidgetIds(new ComponentName(c, StatusWidget.class));
        if (ids.length == 0) return;
        String title, line1, line2;
        try {
            JSONObject s = Net.status(c);
            JSONObject cpu = s.optJSONObject("cpu");
            JSONObject gpu = s.optJSONObject("gpu");
            title = s.optString("name", "PC");
            line1 = "CPU " + temp(cpu == null ? null : cpu.opt("temp")) + "  ·  GPU " + temp(gpu == null ? null : gpu.opt("temp"))
                    + "  ·  " + s.optInt("watts", 0) + " W";
            String game = s.optString("game", "");
            line2 = (!game.isEmpty() && !"null".equals(game)) ? "🎮 " + game
                    : "Last " + (cpu == null ? 0 : cpu.optInt("load", 0)) + " %"
                    + (s.optBoolean("gamemode") ? "  ·  spillmodus" : "");
        } catch (Exception e) {
            title = Net.active(c).optString("name", "Kontrollsenter");
            line1 = "Svarer ikke";
            line2 = e.getMessage() == null ? "" : e.getMessage();
        }
        String time = new java.text.SimpleDateFormat("HH:mm", java.util.Locale.ROOT).format(new java.util.Date());
        for (int id : ids) {
            RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget);
            v.setTextViewText(R.id.w_title, title);
            v.setTextViewText(R.id.w_line1, line1);
            v.setTextViewText(R.id.w_line2, line2 + "   " + time);
            Intent open = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            v.setOnClickPendingIntent(R.id.w_root, PendingIntent.getActivity(c, 3, open, PendingIntent.FLAG_IMMUTABLE));
            m.updateAppWidget(id, v);
        }
    }

    static String temp(Object t) {
        if (t instanceof Number) return Math.round(((Number) t).doubleValue()) + "°";
        return "–";
    }
}
