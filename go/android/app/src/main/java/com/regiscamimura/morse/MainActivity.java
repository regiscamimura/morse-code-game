package com.regiscamimura.morse;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;

import com.regiscamimura.morse.mobile.EbitenView;
import com.regiscamimura.morse.mobile.Mobile;
import com.regiscamimura.morse.mobile.URLOpener;

public class MainActivity extends Activity {
    private GameView view;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Mobile.setDataDir(getFilesDir().getAbsolutePath());
        Mobile.setURLOpener(new URLOpener() {
            @Override
            public void openURL(String url) {
                runOnUiThread(() -> openInBrowser(url));
            }
        });
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        view = new GameView(this);
        setContentView(view);
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

    /** Turns Back into the game's ESC, and logs a crash in the Go game instead of failing silently. */
    private static class GameView extends EbitenView {
        GameView(Activity activity) {
            super(activity);
        }

        /** Back is the game's ESC: it leaves a mission or the free practice. */
        @Override
        public boolean onKeyDown(int keyCode, KeyEvent e) {
            if (keyCode == KeyEvent.KEYCODE_BACK) {
                return super.onKeyDown(KeyEvent.KEYCODE_ESCAPE, new KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ESCAPE));
            }
            return super.onKeyDown(keyCode, e);
        }

        @Override
        public boolean onKeyUp(int keyCode, KeyEvent e) {
            if (keyCode == KeyEvent.KEYCODE_BACK) {
                return super.onKeyUp(KeyEvent.KEYCODE_ESCAPE, new KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ESCAPE));
            }
            return super.onKeyUp(keyCode, e);
        }

        @Override
        protected void onErrorOnGameUpdate(Exception e) {
            Log.e("morse", "game stopped", e);
            super.onErrorOnGameUpdate(e);
        }
    }
}
