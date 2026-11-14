package com.regiscamimura.morse;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.DisplayCutout;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.FrameLayout;

import com.regiscamimura.morse.mobile.EbitenView;
import com.regiscamimura.morse.mobile.Mobile;

public class MainActivity extends Activity {
    /** morse.Ink, the game's first background; the game repaints the strip beside a camera cutout to match. */
    private static final int INK = 0xFF0A0C16;

    private GameView view;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Mobile.setDataDir(getFilesDir().getAbsolutePath());
        Mobile.setURLOpener(url -> runOnUiThread(() -> openInBrowser(url)));
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setVolumeControlStream(AudioManager.STREAM_MUSIC); // the volume keys set the game's sound, even when it's quiet, not the ringer
        view = new GameView(this);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(INK);
        Mobile.setBackdropPainter(argb -> runOnUiThread(() -> root.setBackgroundColor(argb)));
        root.addView(view);
        keepClearOfDisplayCutout(root);
        setContentView(root);
    }

    /** Android 15 and later draw under a camera cutout, which sits at the game's side when the phone is turned. */
    private void keepClearOfDisplayCutout(View root) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            return;
        }
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            DisplayCutout cutout = insets.getDisplayCutout();
            if (cutout == null) {
                v.setPadding(0, 0, 0, 0);
            } else {
                v.setPadding(cutout.getSafeInsetLeft(), cutout.getSafeInsetTop(), cutout.getSafeInsetRight(), cutout.getSafeInsetBottom());
            }
            return insets;
        });
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            hideSystemBars();
        }
    }


    /** Opens url in the phone's browser; without one, the game's screen still shows the address. */
    private void openInBrowser(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (ActivityNotFoundException e) {
            Log.w("morse", "no browser for " + url);
        }
    }

    /** Full screen: the navigation bar would cover the game's bottom row. Swiping brings it back. */
    @SuppressWarnings("deprecation")
    private void hideSystemBars() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController controller = getWindow().getInsetsController();
            controller.hide(WindowInsets.Type.systemBars());
            controller.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        view.suspendGame();
    }

    @Override
    protected void onResume() {
        super.onResume();
        view.resumeGame();
    }

    /** Turns Back into the game's ESC, leaves the system keys to Android, and logs a crash in the Go game. */
    private static class GameView extends EbitenView {
        GameView(Activity activity) {
            super(activity);
        }

        /** Back is the game's ESC: it leaves a mission or the free practice. Volume and the other system
         *  keys go to Android: EbitenView would keep every first press and pass on only a held key's repeats. */
        @Override
        public boolean dispatchKeyEvent(KeyEvent e) {
            if (e.getKeyCode() == KeyEvent.KEYCODE_BACK) {
                return super.dispatchKeyEvent(new KeyEvent(e.getAction(), KeyEvent.KEYCODE_ESCAPE));
            }
            return !e.isSystem() && super.dispatchKeyEvent(e);
        }

        @Override
        protected void onErrorOnGameUpdate(Exception e) {
            Log.e("morse", "game stopped", e);
            super.onErrorOnGameUpdate(e);
        }
    }
}
