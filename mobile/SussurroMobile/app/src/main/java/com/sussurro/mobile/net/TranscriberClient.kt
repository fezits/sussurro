package com.sussurro.mobile.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

class TranscriberClient(
    private val baseUrl: String,
    private val token: String,
) {
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(4, TimeUnit.SECONDS)
        .callTimeout(60, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    private fun normalizedUrl(path: String): String {
        val base = baseUrl.trimEnd('/')
        return "$base$path"
    }

    suspend fun health(): Result<Boolean> = withContext(Dispatchers.IO) {
        runCatching {
            val req = Request.Builder()
                .url(normalizedUrl("/health"))
                .get()
                .build()
            client.newCall(req).execute().use { resp ->
                resp.isSuccessful
            }
        }
    }

    suspend fun transcribe(file: File, language: String? = null): Result<TranscriptionResult> =
        withContext(Dispatchers.IO) {
            runCatching {
                val mime = when {
                    file.name.endsWith(".ogg", true) -> "audio/ogg"
                    file.name.endsWith(".m4a", true) -> "audio/mp4"
                    file.name.endsWith(".aac", true) -> "audio/aac"
                    file.name.endsWith(".wav", true) -> "audio/wav"
                    else -> "application/octet-stream"
                }
                val body = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart(
                        "audio",
                        file.name,
                        file.asRequestBody(mime.toMediaTypeOrNull()),
                    )
                    .apply { if (!language.isNullOrBlank()) addFormDataPart("language", language) }
                    .build()

                val req = Request.Builder()
                    .url(normalizedUrl("/transcribe"))
                    .header("Authorization", "Bearer $token")
                    .post(body)
                    .build()

                client.newCall(req).execute().use { resp ->
                    val payload = resp.body?.string().orEmpty()
                    if (!resp.isSuccessful) {
                        error("HTTP ${resp.code}: ${payload.take(200)}")
                    }
                    val json = JSONObject(payload)
                    TranscriptionResult(
                        text = json.optString("text"),
                        ms = json.optInt("ms", 0),
                    )
                }
            }
        }
}

data class TranscriptionResult(val text: String, val ms: Int)
