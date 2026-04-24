package com.sussurro.mobile.bubble

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import com.sussurro.mobile.MainActivity
import com.sussurro.mobile.R
import com.sussurro.mobile.audio.AudioRecorder
import com.sussurro.mobile.config.ConfigStore
import com.sussurro.mobile.fallback.FallbackRecognizer
import com.sussurro.mobile.inject.TextInjector
import com.sussurro.mobile.net.TranscriberClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlin.math.abs

class BubbleOverlayService : Service() {

    private lateinit var windowManager: WindowManager
    private lateinit var bubbleView: BubbleView
    private lateinit var layoutParams: WindowManager.LayoutParams

    private lateinit var config: ConfigStore
    private lateinit var recorder: AudioRecorder
    private lateinit var injector: TextInjector
    private lateinit var fallback: FallbackRecognizer

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val uiHandler = Handler(Looper.getMainLooper())
    private var levelTicker: Runnable? = null
    private var inFlight: Job? = null

    override fun onCreate() {
        super.onCreate()
        startInForeground()

        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        config = ConfigStore(this)
        recorder = AudioRecorder(this)
        injector = TextInjector(this)
        fallback = FallbackRecognizer(this)

        bubbleView = BubbleView(this).apply {
            state = BubbleState.IDLE
            statusText = BubbleState.IDLE.label
        }
        attachBubble()
    }

    override fun onDestroy() {
        levelTicker?.let { uiHandler.removeCallbacks(it) }
        inFlight?.cancel()
        runCatching { recorder.cancel() }
        scope.cancel()
        runCatching { windowManager.removeView(bubbleView) }
        super.onDestroy()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY
    override fun onBind(intent: Intent?): IBinder? = null

    // ── overlay ─────────────────────────────────────────────────────────────

    private fun attachBubble() {
        val overlayType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }
        val metrics = resources.displayMetrics
        val bubbleSize = (96 * metrics.density).toInt()
        val totalH = (bubbleSize + 40 * metrics.density).toInt()

        layoutParams = WindowManager.LayoutParams(
            bubbleSize + (120 * metrics.density).toInt(),
            totalH,
            overlayType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        )
        layoutParams.gravity = Gravity.TOP or Gravity.START
        layoutParams.x = if (config.bubbleX >= 0) config.bubbleX else metrics.widthPixels - layoutParams.width - (16 * metrics.density).toInt()
        layoutParams.y = if (config.bubbleY >= 0) config.bubbleY else metrics.heightPixels - layoutParams.height - (160 * metrics.density).toInt()

        val touchHandler = BubbleTouchHandler(
            windowManager = windowManager,
            lp = layoutParams,
            onHoldStart = { startRecording() },
            onHoldEnd = { stopRecordingAndTranscribe() },
            onDragEnd = { x, y -> config.bubbleX = x; config.bubbleY = y },
        )
        bubbleView.setOnTouchListener(touchHandler)

        windowManager.addView(bubbleView, layoutParams)
    }

    // ── flow ────────────────────────────────────────────────────────────────

    private fun startRecording() {
        if (recorder.isRecording) return
        if (!config.isConfigured()) {
            setState(BubbleState.ERROR, "Configure o servidor")
            return
        }
        try {
            recorder.start()
            setState(BubbleState.RECORDING, BubbleState.RECORDING.label)
            startLevelTicker()
        } catch (e: Exception) {
            setState(BubbleState.ERROR, "Mic: ${e.message ?: "falha"}")
        }
    }

    private fun stopRecordingAndTranscribe() {
        stopLevelTicker()
        val file = recorder.stop()
        if (file == null) {
            setState(BubbleState.IDLE, "Curto demais")
            scheduleReturnToIdle()
            return
        }
        inFlight?.cancel()
        inFlight = scope.launch {
            setState(BubbleState.UPLOADING, BubbleState.UPLOADING.label)
            val client = TranscriberClient(config.serverUrl, config.token)

            val result = client.transcribe(file, language = "pt")
            file.delete()

            result.onSuccess { tr ->
                setState(BubbleState.TRANSCRIBING, "Transcrevendo…")
                deliverText(tr.text)
            }.onFailure { err ->
                if (config.fallbackToGoogle && fallback.isAvailable()) {
                    setState(BubbleState.FALLBACK, "Servidor off · fallback…")
                    val fb = fallback.recognize()
                    fb.onSuccess { txt -> deliverText(txt) }
                        .onFailure {
                            setState(BubbleState.ERROR, "Falhou: ${err.message ?: "?"}")
                            scheduleReturnToIdle()
                        }
                } else {
                    setState(BubbleState.ERROR, "Servidor off")
                    scheduleReturnToIdle()
                }
            }
        }
    }

    private fun deliverText(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) {
            setState(BubbleState.IDLE, "Nada reconhecido")
            scheduleReturnToIdle()
            return
        }
        val injection = injector.inject(trimmed, preferAccessibility = config.useAccessibilityPaste)
        val preview = if (trimmed.length <= 40) trimmed else trimmed.take(37) + "…"
        val label = when (injection) {
            TextInjector.InjectionResult.Pasted -> "✓ $preview"
            TextInjector.InjectionResult.Clipboard -> "📋 $preview"
            TextInjector.InjectionResult.Empty -> "Nada reconhecido"
        }
        setState(BubbleState.IDLE, label)
        scheduleReturnToIdle()
    }

    private fun scheduleReturnToIdle(delayMs: Long = 2500) {
        uiHandler.postDelayed(
            { if (bubbleView.state == BubbleState.IDLE || bubbleView.state == BubbleState.ERROR) {
                bubbleView.statusText = BubbleState.IDLE.label
            } },
            delayMs,
        )
    }

    private fun setState(state: BubbleState, text: String) {
        bubbleView.state = state
        bubbleView.statusText = text
    }

    private fun startLevelTicker() {
        stopLevelTicker()
        val r = object : Runnable {
            override fun run() {
                bubbleView.level = recorder.level()
                uiHandler.postDelayed(this, 80)
            }
        }
        levelTicker = r
        uiHandler.post(r)
    }

    private fun stopLevelTicker() {
        levelTicker?.let { uiHandler.removeCallbacks(it) }
        levelTicker = null
        bubbleView.level = 0f
    }

    // ── foreground notification ─────────────────────────────────────────────

    private fun startInForeground() {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.service_channel_name),
                    NotificationManager.IMPORTANCE_LOW,
                )
            )
        }
        val tapIntent = android.app.PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_IMMUTABLE,
        )
        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(getString(R.string.notification_text_ready))
            .setContentIntent(tapIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                FG_NOTIF_ID,
                notif,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
            )
        } else {
            startForeground(FG_NOTIF_ID, notif)
        }
    }

    // ── touch handling ──────────────────────────────────────────────────────

    private class BubbleTouchHandler(
        private val windowManager: WindowManager,
        private val lp: WindowManager.LayoutParams,
        private val onHoldStart: () -> Unit,
        private val onHoldEnd: () -> Unit,
        private val onDragEnd: (Int, Int) -> Unit,
    ) : View.OnTouchListener {

        private var startX = 0
        private var startY = 0
        private var startRawX = 0f
        private var startRawY = 0f
        private var dragging = false
        private var holding = false
        private var downTime = 0L

        override fun onTouch(v: View, event: MotionEvent): Boolean {
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startX = lp.x
                    startY = lp.y
                    startRawX = event.rawX
                    startRawY = event.rawY
                    dragging = false
                    downTime = System.currentTimeMillis()
                    holding = false
                    v.postDelayed(holdTrigger, HOLD_THRESHOLD_MS)
                    return true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - startRawX
                    val dy = event.rawY - startRawY
                    if (!dragging && (abs(dx) > SLOP || abs(dy) > SLOP)) {
                        dragging = true
                        v.removeCallbacks(holdTrigger)
                        if (holding) {
                            holding = false
                            onHoldEnd()
                        }
                    }
                    if (dragging) {
                        lp.x = (startX + dx).toInt()
                        lp.y = (startY + dy).toInt()
                        runCatching { windowManager.updateViewLayout(v, lp) }
                    }
                    return true
                }
                MotionEvent.ACTION_UP,
                MotionEvent.ACTION_CANCEL -> {
                    v.removeCallbacks(holdTrigger)
                    if (holding) {
                        holding = false
                        onHoldEnd()
                    }
                    if (dragging) {
                        onDragEnd(lp.x, lp.y)
                    }
                    return true
                }
            }
            return false
        }

        private val holdTrigger = Runnable {
            holding = true
            onHoldStart()
        }

        companion object {
            private const val HOLD_THRESHOLD_MS = 180L
            private const val SLOP = 24f
        }
    }

    companion object {
        private const val CHANNEL_ID = "sussurro_overlay"
        private const val FG_NOTIF_ID = 1001

        fun start(context: Context) {
            val intent = Intent(context, BubbleOverlayService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, BubbleOverlayService::class.java))
        }
    }
}
