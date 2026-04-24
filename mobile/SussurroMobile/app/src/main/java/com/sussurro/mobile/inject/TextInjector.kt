package com.sussurro.mobile.inject

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.sussurro.mobile.MainActivity
import com.sussurro.mobile.R

class TextInjector(private val context: Context) {
    private val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager

    /**
     * Copy to clipboard and try to paste. If the Accessibility service is bound,
     * that paste is immediate. Otherwise shows a notification inviting the user
     * to paste manually.
     */
    fun inject(text: String, preferAccessibility: Boolean): InjectionResult {
        if (text.isBlank()) return InjectionResult.Empty
        val payload = if (text.endsWith(" ")) text else "$text "

        clipboard.setPrimaryClip(ClipData.newPlainText("Sussurro", payload))

        if (preferAccessibility && SussurroAccessibilityService.isRunning()) {
            val pasted = SussurroAccessibilityService.pasteIntoFocusedNode()
            if (pasted) return InjectionResult.Pasted
        }

        showClipboardNotification(payload.trim())
        return InjectionResult.Clipboard
    }

    private fun showClipboardNotification(preview: String) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CLIP_CHANNEL_ID,
                "Sussurro clipboard",
                NotificationManager.IMPORTANCE_LOW,
            )
            nm.createNotificationChannel(channel)
        }

        val tapIntent = Intent(context, MainActivity::class.java)
        val pending = PendingIntent.getActivity(
            context,
            0,
            tapIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val notif = NotificationCompat.Builder(context, CLIP_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(R.string.copied_to_clipboard))
            .setContentText(preview)
            .setStyle(NotificationCompat.BigTextStyle().bigText(preview))
            .setContentIntent(pending)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        nm.notify(NOTIF_ID, notif)
    }

    enum class InjectionResult { Pasted, Clipboard, Empty }

    companion object {
        private const val CLIP_CHANNEL_ID = "sussurro_clipboard"
        private const val NOTIF_ID = 42
    }
}
