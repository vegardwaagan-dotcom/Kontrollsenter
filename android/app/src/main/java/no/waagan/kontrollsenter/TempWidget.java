package no.waagan.kontrollsenter;

import android.content.Context;
import android.widget.RemoteViews;

import org.json.JSONObject;

/** «Temperaturer»: CPU, GPU og strøm i store tall, og strømforbruket i dag. */
public class TempWidget extends KsWidget {
    int layout() { return R.layout.widget_temp; }

    void fill(Context c, RemoteViews v, JSONObject d) {
        v.setTextViewText(R.id.w_cpu, t(d, "cpu_t"));
        v.setTextViewText(R.id.w_gpu, t(d, "gpu_t"));
        v.setTextViewText(R.id.w_watt, d.optInt("watts", 0) + " W");
        v.setTextViewText(R.id.w_sub, d.has("kwh") ? "I dag " + d.optDouble("kwh") + " kWh · " + d.optDouble("kr") + " kr" : str(d, "name"));
    }
}
