package no.waagan.kontrollsenter;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/** Gir andre apper (Messenger, Snap, Disk …) lesetilgang til et skjermbilde/klipp vi nettopp hentet fra PC-en.
 *  Bare filer i cache/del, bare lesing, og bare til appen brukeren velger i delemenyen. */
public class ShareProvider extends ContentProvider {
    public static final String AUTH = "no.waagan.kontrollsenter.share";

    static File dir(android.content.Context c) {
        File d = new File(c.getCacheDir(), "del");
        d.mkdirs();
        return d;
    }

    static String mime(String name) {
        String n = name.toLowerCase();
        if (n.endsWith(".png")) return "image/png";
        if (n.endsWith(".jpg") || n.endsWith(".jpeg")) return "image/jpeg";
        if (n.endsWith(".webp")) return "image/webp";
        if (n.endsWith(".gif")) return "image/gif";
        if (n.endsWith(".mkv")) return "video/x-matroska";
        if (n.endsWith(".webm")) return "video/webm";
        if (n.endsWith(".mov")) return "video/quicktime";
        return "video/mp4";
    }

    private File file(Uri uri) throws FileNotFoundException {
        String n = uri.getLastPathSegment();
        if (n == null || n.contains("/") || n.startsWith(".")) throw new FileNotFoundException();
        File f = new File(dir(getContext()), n);
        if (!f.isFile()) throw new FileNotFoundException(n);
        return f;
    }

    @Override public boolean onCreate() { return true; }

    @Override public String getType(Uri uri) { return mime(String.valueOf(uri.getLastPathSegment())); }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (mode.contains("w")) throw new FileNotFoundException("bare lesing");
        return ParcelFileDescriptor.open(file(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Cursor query(Uri uri, String[] proj, String sel, String[] args, String sort) {
        MatrixCursor c = new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
        try {
            File f = file(uri);
            c.addRow(new Object[]{f.getName(), f.length()});
        } catch (FileNotFoundException e) {
            // tom
        }
        return c;
    }

    @Override public Uri insert(Uri uri, ContentValues v) { return null; }
    @Override public int delete(Uri uri, String s, String[] a) { return 0; }
    @Override public int update(Uri uri, ContentValues v, String s, String[] a) { return 0; }
}
