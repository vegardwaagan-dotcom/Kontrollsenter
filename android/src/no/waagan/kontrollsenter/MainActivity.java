package no.waagan.kontrollsenter;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import java.net.Inet4Address;
import java.net.InetAddress;

/**
 * Kontrollsenter for Android: startsiden (assets/start.html) finner PC-ene med Kontrollsenter på hjemmenettet,
 * og kontrollpanelet lastes fra PC-en selv (http://PC:27100/app/) – så appen får nye funksjoner hver gang
 * Kontrollsenter på PC-en oppdateres.
 */
public class MainActivity extends Activity {
    static final String START = "file:///android_asset/start.html";
    private WebView web;
    private FrameLayout root;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        root = new FrameLayout(this);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);

        // Kant til kant (Android 15): hold innholdet unna statuslinjen, navigasjonen, kamerahullet og tastaturet
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            root.setOnApplyWindowInsetsListener((v, ins) -> {
                Insets i = ins.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()
                        | WindowInsets.Type.ime());
                v.setPadding(i.left, i.top, i.right, i.bottom);
                return WindowInsets.CONSUMED;
            });
        }
        applyTheme();

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setBuiltInZoomControls(false);
        s.setSupportZoom(false);
        web.addJavascriptInterface(new Bridge(), "KS");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                String sc = u.getScheme();
                // bare egne sider: startsiden i appen og Kontrollsenter på PC-er i hjemmenettet
                return !("file".equals(sc) || ("http".equals(sc) && isLocal(u.getHost())));
            }
        });
        if (saved != null) {
            web.restoreState(saved);
        } else {
            web.loadUrl(START);
        }
    }

    static boolean isLocal(String host) {
        if (host == null) return false;
        if (host.endsWith(".local") || host.equals("localhost") || !host.contains(".")) return true;
        return host.matches("^(10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[01])\\.|127\\.)[\\d.]+$");
    }

    private boolean night() {
        return (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                == Configuration.UI_MODE_NIGHT_YES;
    }

    private void applyTheme() {
        boolean dark = night();
        int bg = dark ? Color.rgb(0x1e, 0x1e, 0x24) : Color.rgb(0xf4, 0xf4, 0xf7);
        root.setBackgroundColor(bg);
        web.setBackgroundColor(bg);
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {
                int light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                        | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                c.setSystemBarsAppearance(dark ? 0 : light, light);
            }
        } else {
            getWindow().setStatusBarColor(bg);
            getWindow().setNavigationBarColor(bg);
            if (!dark) {
                getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
            }
        }
    }

    @Override
    public void onConfigurationChanged(Configuration c) {
        super.onConfigurationChanged(c);
        applyTheme();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        web.resumeTimers();
    }

    @Override
    protected void onPause() {
        web.onPause();                  // ingen henting i bakgrunnen – sparer batteri
        web.pauseTimers();
        super.onPause();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        String url = web.getUrl();
        if (url != null && url.startsWith("http")) {
            web.loadUrl(START + "?hjem=1");          // fra en PC: tilbake til PC-listen
        } else if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    /** Tilgjengelig for sidene som window.KS – bare ufarlige funksjoner. */
    class Bridge {
        @JavascriptInterface
        public void home() {
            runOnUiThread(() -> web.loadUrl(START + "?hjem=1"));
        }

        /** IPv4-adressen og nettmasken på Wi-Fi/Ethernet, f.eks. «192.168.1.23/24». */
        @JavascriptInterface
        public String subnet() {
            try {
                ConnectivityManager cm = getSystemService(ConnectivityManager.class);
                Network n = cm.getActiveNetwork();
                LinkProperties lp = n == null ? null : cm.getLinkProperties(n);
                if (lp == null) return "";
                for (LinkAddress la : lp.getLinkAddresses()) {
                    InetAddress a = la.getAddress();
                    if (a instanceof Inet4Address && !a.isLoopbackAddress()) {
                        return a.getHostAddress() + "/" + la.getPrefixLength();
                    }
                }
            } catch (Exception e) {
                // ingen nettverkstilgang – siden lar deg skrive inn adressen selv
            }
            return "";
        }

        /** Navnet på enheten (f.eks. «Galaxy Tab S11 Ultra») – brukes som forslag ved paring. */
        @JavascriptInterface
        public String model() {
            String n = null;
            try {
                n = Settings.Global.getString(getContentResolver(), "device_name");
            } catch (Exception e) {
                // bruk modellnavnet
            }
            return (n != null && !n.isEmpty()) ? n : (Build.MANUFACTURER + " " + Build.MODEL);
        }

        @JavascriptInterface
        public String version() {
            try {
                return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
            } catch (Exception e) {
                return "";
            }
        }
    }
}
