package com.sussurro.mobile.audio

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import java.io.File

class AudioRecorder(private val context: Context) {
    private var recorder: MediaRecorder? = null
    private var outputFile: File? = null

    val isRecording: Boolean get() = recorder != null

    /** Start recording into a temp file. Returns the path being written. */
    fun start(): File {
        stop()

        val dir = File(context.cacheDir, "audio").apply { mkdirs() }
        val file = File(dir, "rec_${System.currentTimeMillis()}.m4a")
        outputFile = file

        val rec = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }
        rec.setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
        rec.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        rec.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
        rec.setAudioChannels(1)
        rec.setAudioSamplingRate(16000)
        rec.setAudioEncodingBitRate(32_000)
        rec.setOutputFile(file.absolutePath)
        rec.prepare()
        rec.start()
        recorder = rec
        return file
    }

    /** Current input amplitude (0f..1f) used by the bubble waveform. */
    fun level(): Float {
        val rec = recorder ?: return 0f
        return try {
            @Suppress("DEPRECATION")
            val amp = rec.maxAmplitude
            // MediaRecorder gives 0..32767; empirically 3000+ is "speaking"
            (amp.coerceAtLeast(0) / 12000f).coerceIn(0f, 1f)
        } catch (_: Exception) {
            0f
        }
    }

    /** Stop recording and return the produced file (or null on empty/failure). */
    fun stop(): File? {
        val rec = recorder ?: return null
        recorder = null
        return try {
            rec.stop()
            rec.release()
            val f = outputFile
            if (f != null && f.exists() && f.length() > 128) f else null
        } catch (_: Exception) {
            runCatching { rec.release() }
            null
        } finally {
            outputFile = null
        }
    }

    fun cancel() {
        val rec = recorder ?: return
        recorder = null
        runCatching { rec.stop() }
        runCatching { rec.release() }
        runCatching { outputFile?.delete() }
        outputFile = null
    }
}
