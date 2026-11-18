package no.waagan.kontrollsenter;

import android.app.Activity;
import android.app.AlertDialog;
import android.appwidget.AppWidgetManager;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Velg de fire flisene når «Velg selv»-widgeten legges på hjemskjermen (eller trykk lenge → Innstillinger). */
public class PickConfig extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        int id = getIntent().getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID);
        setResult(RESULT_CANCELED, new Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id));
        List<String> cur = new ArrayList<>(Arrays.asList(PickWidget.choice(this)));
        boolean[] on = new boolean[PickWidget.KEYS.length];
        for (int i = 0; i < on.length; i++) on[i] = cur.contains(PickWidget.KEYS[i]);
        List<String> picked = new ArrayList<>(cur);
        new AlertDialog.Builder(this)
                .setTitle("Velg fire fliser")
                .setMultiChoiceItems(PickWidget.NAMES, on, (d, i, checked) -> {
                    String k = PickWidget.KEYS[i];
                    if (checked) { if (!picked.contains(k)) picked.add(k); } else picked.remove(k);
                })
                .setPositiveButton("Lagre", (d, w) -> {
                    while (picked.size() > 4) picked.remove(0);
                    for (String k : PickWidget.DEFAULT) if (picked.size() < 4 && !picked.contains(k)) picked.add(k);
                    getSharedPreferences("ks", 0).edit().putString("pick_tiles", String.join(",", picked)).apply();
                    if (picked.size() > 4) Toast.makeText(this, "Bare de fire siste brukes", Toast.LENGTH_SHORT).show();
                    setResult(RESULT_OK, new Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id));
                    new Thread(() -> KsWidget.refreshAll(this)).start();
                    finish();
                })
                .setNegativeButton("Avbryt", (d, w) -> finish())
                .setOnCancelListener(d -> finish())
                .show();
    }
}
