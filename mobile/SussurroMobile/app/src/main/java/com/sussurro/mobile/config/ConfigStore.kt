package com.sussurro.mobile.config

import android.content.Context
import android.content.SharedPreferences

class ConfigStore(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString(KEY_SERVER_URL, "") ?: ""
        set(value) = prefs.edit().putString(KEY_SERVER_URL, value.trim()).apply()

    var token: String
        get() = prefs.getString(KEY_TOKEN, "") ?: ""
        set(value) = prefs.edit().putString(KEY_TOKEN, value.trim()).apply()

    var bubbleX: Int
        get() = prefs.getInt(KEY_BUBBLE_X, -1)
        set(value) = prefs.edit().putInt(KEY_BUBBLE_X, value).apply()

    var bubbleY: Int
        get() = prefs.getInt(KEY_BUBBLE_Y, -1)
        set(value) = prefs.edit().putInt(KEY_BUBBLE_Y, value).apply()

    var useAccessibilityPaste: Boolean
        get() = prefs.getBoolean(KEY_USE_A11Y, true)
        set(value) = prefs.edit().putBoolean(KEY_USE_A11Y, value).apply()

    var fallbackToGoogle: Boolean
        get() = prefs.getBoolean(KEY_FALLBACK, true)
        set(value) = prefs.edit().putBoolean(KEY_FALLBACK, value).apply()

    fun isConfigured(): Boolean = serverUrl.isNotBlank() && token.isNotBlank()

    companion object {
        private const val PREFS_NAME = "sussurro_prefs"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_TOKEN = "server_token"
        private const val KEY_BUBBLE_X = "bubble_x"
        private const val KEY_BUBBLE_Y = "bubble_y"
        private const val KEY_USE_A11Y = "use_a11y"
        private const val KEY_FALLBACK = "fallback_google"
    }
}
