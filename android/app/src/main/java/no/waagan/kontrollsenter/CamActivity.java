package no.waagan.kontrollsenter;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
import android.graphics.Matrix;
import android.graphics.Rect;
import android.graphics.RectF;
import android.graphics.SurfaceTexture;
import android.graphics.YuvImage;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.Image;
import android.media.ImageReader;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Size;
import android.view.Gravity;
import android.view.Surface;
import android.view.TextureView;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.ByteBuffer;
import java.util.Arrays;

/**
 * Mobilen som webkamera: viser kameraet og sender JPEG-bilder (ca. 12 per sekund) til PC-en appen er koblet til
 * (POST /api/phonecam). På PC-en kan bildet brukes i talekanalene i chatten, i et eget vindu, eller som vanlig
 * webkamera i andre programmer (Linux, v4l2loopback).
 */
public class CamActivity extends Activity {
    private static final int W = 640, H = 480, QUALITY = 70;
    private static final long MIN_GAP_MS = 80;            // høyst ~12 bilder/s

    private TextureView view;
    private TextView status;
    private String base, token, device;
    private boolean front = false;
    private CameraDevice cam;
    private CameraCaptureSession session;
    private ImageReader reader;
    private HandlerThread camThread, netThread;
    private Handler camHandler, netHandler;
    private int sensor = 90;
    private volatile byte[] pending;
    private volatile boolean sending = false, running = false;
    private long lastFrame = 0;
    private int sent = 0, failed = 0;
    private long statT = 0;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        base = getIntent().getStringExtra("base");
        token = getIntent().getStringExtra("token");
        device = android.os.Build.MODEL;
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(0xFF000000);
        view = new TextureView(this);
        root.addView(view, new FrameLayout.LayoutParams(-1, -1));
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(24, 16, 24, 16);
        bar.setBackgroundColor(0x99000000);
        status = new TextView(this);
        status.setTextColor(0xFFFFFFFF);
        status.setText("Starter kameraet …");
        bar.addView(status, new LinearLayout.LayoutParams(0, -2, 1));
        Button flip = new Button(this);
        flip.setText("🔄 Bytt kamera");
        flip.setOnClickListener(v -> { front = !front; restart(); });
        bar.addView(flip);
        Button stop = new Button(this);
        stop.setText("⏹ Stopp");
        stop.setOnClickListener(v -> finish());
        bar.addView(stop);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        root.addView(bar, lp);
        setContentView(root);
        if (base == null || token == null) {
            status.setText("Åpne mobilkameraet fra Chat i appen");
            return;
        }
        netThread = new HandlerThread("ks-kamera-nett");
        netThread.start();
        netHandler = new Handler(netThread.getLooper());
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (base == null) return;
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, 7);
            return;
        }
        start();
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] p, int[] r) {
        if (code == 7 && r.length > 0 && r[0] == PackageManager.PERMISSION_GRANTED) start();
        else status.setText("Appen fikk ikke bruke kameraet – gi tillatelse under Innstillinger → Apper");
    }

    @Override
    protected void onPause() {
        stopCamera();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        stopCamera();
        if (netThread != null) netThread.quitSafely();
        super.onDestroy();
    }

    private void restart() {
        stopCamera();
        start();
    }

    private void start() {
        if (running) return;
        running = true;
        camThread = new HandlerThread("ks-kamera");
        camThread.start();
        camHandler = new Handler(camThread.getLooper());
        if (view.isAvailable()) open();
        else view.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
            public void onSurfaceTextureAvailable(SurfaceTexture s, int w, int h) { open(); }
            public void onSurfaceTextureSizeChanged(SurfaceTexture s, int w, int h) { transform(); }
            public boolean onSurfaceTextureDestroyed(SurfaceTexture s) { return true; }
            public void onSurfaceTextureUpdated(SurfaceTexture s) { }
        });
    }

    private void stopCamera() {
        running = false;
        try { if (session != null) session.close(); } catch (Exception ignored) { }
        try { if (cam != null) cam.close(); } catch (Exception ignored) { }
        try { if (reader != null) reader.close(); } catch (Exception ignored) { }
        session = null; cam = null; reader = null;
        if (camThread != null) { camThread.quitSafely(); camThread = null; }
    }

    private void open() {
        CameraManager cm = (CameraManager) getSystemService(CAMERA_SERVICE);
        try {
            String id = null;
            for (String c : cm.getCameraIdList()) {
                Integer f = cm.getCameraCharacteristics(c).get(CameraCharacteristics.LENS_FACING);
                if (f != null && f == (front ? CameraCharacteristics.LENS_FACING_FRONT
                        : CameraCharacteristics.LENS_FACING_BACK)) { id = c; break; }
            }
            if (id == null) id = cm.getCameraIdList()[0];
            CameraCharacteristics ch = cm.getCameraCharacteristics(id);
            Integer so = ch.get(CameraCharacteristics.SENSOR_ORIENTATION);
            sensor = so == null ? 90 : so;
            StreamConfigurationMap map = ch.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            Size size = pick(map.getOutputSizes(ImageFormat.YUV_420_888), W, H);
            reader = ImageReader.newInstance(size.getWidth(), size.getHeight(), ImageFormat.YUV_420_888, 3);
            reader.setOnImageAvailableListener(this::onImage, camHandler);
            SurfaceTexture st = view.getSurfaceTexture();
            st.setDefaultBufferSize(size.getWidth(), size.getHeight());
            runOnUiThread(this::transform);
            final Surface preview = new Surface(st);
            cm.openCamera(id, new CameraDevice.StateCallback() {
                public void onOpened(CameraDevice d) {
                    cam = d;
                    try {
                        CaptureRequest.Builder rb = d.createCaptureRequest(CameraDevice.TEMPLATE_RECORD);
                        rb.addTarget(preview);
                        rb.addTarget(reader.getSurface());
                        d.createCaptureSession(Arrays.asList(preview, reader.getSurface()),
                                new CameraCaptureSession.StateCallback() {
                                    public void onConfigured(CameraCaptureSession s) {
                                        session = s;
                                        try { s.setRepeatingRequest(rb.build(), null, camHandler); }
                                        catch (CameraAccessException e) { say("Kameraet svarer ikke: " + e.getMessage()); }
                                        say("Sender til PC-en …");
                                    }
                                    public void onConfigureFailed(CameraCaptureSession s) { say("Kameraet kunne ikke startes"); }
                                }, camHandler);
                    } catch (CameraAccessException e) { say("Kameraet svarer ikke: " + e.getMessage()); }
                }
                public void onDisconnected(CameraDevice d) { d.close(); }
                public void onError(CameraDevice d, int e) { d.close(); say("Kamerafeil " + e + " – er det i bruk av en annen app?"); }
            }, camHandler);
        } catch (CameraAccessException | RuntimeException e) {
            say("Fikk ikke åpnet kameraet: " + e.getMessage());
        }
    }

    private static Size pick(Size[] sizes, int w, int h) {
        Size best = sizes[0];
        long want = (long) w * h, bd = Long.MAX_VALUE;
        for (Size s : sizes) {
            long d = Math.abs((long) s.getWidth() * s.getHeight() - want);
            if (s.getWidth() * 3 == s.getHeight() * 4 || s.getWidth() * 9 == s.getHeight() * 16) d /= 2;
            if (d < bd) { bd = d; best = s; }
        }
        return best;
    }

    /** Forhåndsvisningen riktig vei (fra Googles Camera2-eksempel). */
    private void transform() {
        if (reader == null) return;
        int rot = getWindowManager().getDefaultDisplay().getRotation();
        int vw = view.getWidth(), vh = view.getHeight();
        Matrix m = new Matrix();
        RectF vr = new RectF(0, 0, vw, vh);
        RectF br = new RectF(0, 0, reader.getHeight(), reader.getWidth());
        float cx = vr.centerX(), cy = vr.centerY();
        if (rot == Surface.ROTATION_90 || rot == Surface.ROTATION_270) {
            br.offset(cx - br.centerX(), cy - br.centerY());
            m.setRectToRect(vr, br, Matrix.ScaleToFit.FILL);
            float sc = Math.max((float) vh / reader.getHeight(), (float) vw / reader.getWidth());
            m.postScale(sc, sc, cx, cy);
            m.postRotate(90 * (rot - 2), cx, cy);
        } else if (rot == Surface.ROTATION_180) {
            m.postRotate(180, cx, cy);
        }
        view.setTransform(m);
    }

    /** Hvor mye PC-en må rotere bildet for at det skal stå riktig vei. */
    private int rotation() {
        int r = getWindowManager().getDefaultDisplay().getRotation();
        int deg = r == Surface.ROTATION_90 ? 90 : r == Surface.ROTATION_180 ? 180 : r == Surface.ROTATION_270 ? 270 : 0;
        return front ? (sensor + deg) % 360 : (sensor - deg + 360) % 360;
    }

    private void onImage(ImageReader r) {
        Image img = r.acquireLatestImage();
        if (img == null) return;
        try {
            long now = System.currentTimeMillis();
            if (sending || now - lastFrame < MIN_GAP_MS) return;
            lastFrame = now;
            byte[] nv21 = toNv21(img);
            YuvImage y = new YuvImage(nv21, ImageFormat.NV21, img.getWidth(), img.getHeight(), null);
            ByteArrayOutputStream out = new ByteArrayOutputStream(64 * 1024);
            y.compressToJpeg(new Rect(0, 0, img.getWidth(), img.getHeight()), QUALITY, out);
            pending = out.toByteArray();
            final int rot = rotation();
            sending = true;
            netHandler.post(() -> send(rot));
        } catch (RuntimeException e) {
            say("Feil: " + e.getMessage());
        } finally {
            img.close();
        }
    }

    private static byte[] toNv21(Image img) {
        int w = img.getWidth(), h = img.getHeight();
        byte[] out = new byte[w * h * 3 / 2];
        Image.Plane[] p = img.getPlanes();
        ByteBuffer yb = p[0].getBuffer();
        int ys = p[0].getRowStride(), pos = 0;
        for (int row = 0; row < h; row++) {
            yb.position(row * ys);
            yb.get(out, pos, w);
            pos += w;
        }
        ByteBuffer ub = p[1].getBuffer(), vb = p[2].getBuffer();
        int us = p[1].getRowStride(), up = p[1].getPixelStride();
        int vs = p[2].getRowStride(), vp = p[2].getPixelStride();
        for (int row = 0; row < h / 2; row++) {
            for (int col = 0; col < w / 2; col++) {
                out[pos++] = vb.get(row * vs + col * vp);
                out[pos++] = ub.get(row * us + col * up);
            }
        }
        return out;
    }

    private void send(int rot) {
        byte[] data = pending;
        HttpURLConnection c = null;
        try {
            URL u = new URL(base + "/api/phonecam?k=" + URLEncoder.encode(token, "UTF-8") + "&rot=" + rot
                    + "&dev=" + URLEncoder.encode(device == null ? "" : device, "UTF-8"));
            c = (HttpURLConnection) u.openConnection();
            c.setConnectTimeout(3000);
            c.setReadTimeout(4000);
            c.setDoOutput(true);
            c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type", "image/jpeg");
            c.setFixedLengthStreamingMode(data.length);
            try (OutputStream o = c.getOutputStream()) { o.write(data); }
            int code = c.getResponseCode();
            c.getInputStream().close();
            if (code == 200) sent++; else failed++;
        } catch (Exception e) {
            failed++;
            if (failed % 10 == 1) say("PC-en svarer ikke (" + e.getClass().getSimpleName() + ") – prøver igjen …");
        } finally {
            if (c != null) c.disconnect();
            sending = false;
        }
        long now = System.currentTimeMillis();
        if (now - statT > 2000) {
            float fps = sent * 1000f / Math.max(1, now - statT);
            if (statT > 0 && sent > 0) say(String.format("📷 Sender til PC-en · %.0f bilder/s", fps));
            statT = now;
            sent = 0;
        }
    }

    private void say(String t) {
        runOnUiThread(() -> status.setText(t));
    }
}
