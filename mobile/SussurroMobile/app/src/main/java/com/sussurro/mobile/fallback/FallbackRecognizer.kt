package com.sussurro.mobile.fallback

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine

/** Uses Android's built-in on-device speech recognizer as a fallback when the server is unreachable. */
class FallbackRecognizer(private val context: Context) {
    fun isAvailable(): Boolean = SpeechRecognizer.isRecognitionAvailable(context)

    suspend fun recognize(): Result<String> = suspendCancellableCoroutine { cont ->
        if (!isAvailable()) {
            cont.resume(Result.failure(IllegalStateException("SpeechRecognizer indisponível")))
            return@suspendCancellableCoroutine
        }
        val recognizer = SpeechRecognizer.createSpeechRecognizer(context)
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }

        val listener = object : RecognitionListener {
            override fun onResults(results: Bundle?) {
                val best = results
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull()
                    .orEmpty()
                recognizer.destroy()
                if (cont.isActive) cont.resume(Result.success(best))
            }

            override fun onError(error: Int) {
                recognizer.destroy()
                if (cont.isActive) cont.resume(
                    Result.failure(RuntimeException("SpeechRecognizer erro $error"))
                )
            }

            override fun onReadyForSpeech(params: Bundle?) = Unit
            override fun onBeginningOfSpeech() = Unit
            override fun onRmsChanged(rmsdB: Float) = Unit
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = Unit
            override fun onPartialResults(partialResults: Bundle?) = Unit
            override fun onEvent(eventType: Int, params: Bundle?) = Unit
        }

        recognizer.setRecognitionListener(listener)
        recognizer.startListening(intent)

        cont.invokeOnCancellation {
            runCatching { recognizer.cancel() }
            runCatching { recognizer.destroy() }
        }
    }
}
