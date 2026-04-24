package com.sussurro.mobile.bubble

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.util.TypedValue
import android.view.View
import kotlin.math.PI
import kotlin.math.sin

class BubbleView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textAlign = Paint.Align.CENTER
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        textSize = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_SP,
            11f,
            context.resources.displayMetrics,
        )
    }

    var state: BubbleState = BubbleState.IDLE
        set(value) {
            field = value
            invalidate()
        }

    var statusText: String = BubbleState.IDLE.label
        set(value) {
            field = value
            invalidate()
        }

    var level: Float = 0f
        set(value) {
            field = value.coerceIn(0f, 1f)
        }

    private var phase = 0f

    private val tick = object : Runnable {
        override fun run() {
            phase += 0.09f
            if (phase > (PI * 2).toFloat()) phase -= (PI * 2).toFloat()
            invalidate()
            postOnAnimationDelayed(this, 33)
        }
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        postOnAnimation(tick)
    }

    override fun onDetachedFromWindow() {
        removeCallbacks(tick)
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        val w = width.toFloat()
        val h = height.toFloat()
        val orbD = minOf(w, h * 0.66f)
        val cx = w / 2f
        val cy = orbD / 2f + 6f
        val baseR = orbD / 2f - 6f

        val (dark, light) = colorsFor(state)

        var pulse = 0f
        val lvl = level
        when (state) {
            BubbleState.RECORDING -> pulse = 0.12f * (0.5f + 0.5f * sin(phase * 2f))
            BubbleState.UPLOADING,
            BubbleState.TRANSCRIBING,
            BubbleState.FALLBACK -> pulse = 0.08f * (0.5f + 0.5f * sin(phase * 3f))
            else -> pulse = 0f
        }
        val r = baseR * (1f + pulse * 0.5f + lvl * 0.12f)

        paint.style = Paint.Style.FILL
        paint.shader = RadialGradient(
            cx,
            cy,
            r * 1.6f,
            Color.argb(110, Color.red(light), Color.green(light), Color.blue(light)),
            Color.argb(0, 0, 0, 0),
            Shader.TileMode.CLAMP,
        )
        canvas.drawCircle(cx, cy, r * 1.6f, paint)

        paint.shader = RadialGradient(
            cx - r * 0.3f,
            cy - r * 0.3f,
            r * 1.4f,
            light,
            dark,
            Shader.TileMode.CLAMP,
        )
        canvas.drawCircle(cx, cy, r, paint)
        paint.shader = null

        when (state) {
            BubbleState.RECORDING -> drawWave(canvas, cx, cy, r, lvl)
            BubbleState.UPLOADING,
            BubbleState.TRANSCRIBING,
            BubbleState.FALLBACK -> drawSpinner(canvas, cx, cy, r)
            else -> drawMic(canvas, cx, cy, r)
        }

        drawLabel(canvas, w, orbD)
    }

    private fun drawWave(canvas: Canvas, cx: Float, cy: Float, r: Float, lvl: Float) {
        paint.color = Color.argb(230, 255, 255, 255)
        paint.style = Paint.Style.FILL
        val bars = 7
        val spacing = r * 0.22f
        val maxH = r * 1.2f
        val minH = r * 0.18f
        for (i in 0 until bars) {
            val p = phase * 3f + i * 0.9f
            val osc = 0.5f + 0.5f * sin(p)
            val target = minH + (maxH - minH) * (0.3f + 0.7f * lvl) * osc
            val x = cx + (i - (bars - 1) / 2f) * spacing
            val rect = RectF(
                x - spacing * 0.3f,
                cy - target / 2f,
                x + spacing * 0.3f,
                cy + target / 2f,
            )
            canvas.drawRoundRect(rect, spacing * 0.3f, spacing * 0.3f, paint)
        }
    }

    private fun drawSpinner(canvas: Canvas, cx: Float, cy: Float, r: Float) {
        paint.style = Paint.Style.STROKE
        paint.color = Color.argb(230, 255, 255, 255)
        paint.strokeWidth = maxOf(3f, r * 0.12f)
        paint.strokeCap = Paint.Cap.ROUND
        val arcR = r * 0.55f
        val rect = RectF(cx - arcR, cy - arcR, cx + arcR, cy + arcR)
        val start = (-Math.toDegrees(phase.toDouble())).toFloat()
        canvas.drawArc(rect, start, 270f, false, paint)
        paint.style = Paint.Style.FILL
    }

    private fun drawMic(canvas: Canvas, cx: Float, cy: Float, r: Float) {
        paint.color = Color.argb(225, 255, 255, 255)
        paint.style = Paint.Style.FILL
        val bodyW = r * 0.55f
        val bodyH = r * 0.85f
        val rect = RectF(
            cx - bodyW / 2f,
            cy - bodyH / 2f - r * 0.1f,
            cx + bodyW / 2f,
            cy + bodyH / 2f - r * 0.1f,
        )
        canvas.drawRoundRect(rect, bodyW / 2f, bodyW / 2f, paint)

        paint.style = Paint.Style.STROKE
        paint.strokeWidth = maxOf(2f, r * 0.08f)
        paint.strokeCap = Paint.Cap.ROUND
        val arcR = r * 0.72f
        val arcRect = RectF(cx - arcR, cy - arcR * 0.3f, cx + arcR, cy + arcR * 0.9f)
        canvas.drawArc(arcRect, 20f, 140f, false, paint)
        canvas.drawLine(cx, cy + arcR * 0.65f, cx, cy + arcR * 0.9f, paint)
        paint.style = Paint.Style.FILL
    }

    private fun drawLabel(canvas: Canvas, totalW: Float, orbBottom: Float) {
        val text = statusText
        if (text.isBlank()) return
        val padX = 14f
        val padY = 5f
        val metrics = textPaint.fontMetrics
        val textW = textPaint.measureText(text)
        val labelW = (textW + padX * 2f).coerceAtMost(totalW - 8f)
        val labelH = (-metrics.top + metrics.bottom) + padY * 2f

        val left = (totalW - labelW) / 2f
        val top = orbBottom + 6f
        val rect = RectF(left, top, left + labelW, top + labelH)

        paint.color = Color.argb(220, 20, 20, 26)
        paint.style = Paint.Style.FILL
        canvas.drawRoundRect(rect, labelH / 2f, labelH / 2f, paint)

        canvas.drawText(
            text,
            rect.centerX(),
            rect.centerY() - (metrics.ascent + metrics.descent) / 2f,
            textPaint,
        )
    }

    private fun colorsFor(state: BubbleState): Pair<Int, Int> = when (state) {
        BubbleState.IDLE -> Color.rgb(80, 80, 90) to Color.rgb(140, 140, 155)
        BubbleState.RECORDING -> Color.rgb(220, 50, 60) to Color.rgb(255, 90, 100)
        BubbleState.UPLOADING -> Color.rgb(80, 120, 200) to Color.rgb(130, 170, 255)
        BubbleState.TRANSCRIBING -> Color.rgb(230, 170, 30) to Color.rgb(255, 210, 80)
        BubbleState.FALLBACK -> Color.rgb(200, 120, 30) to Color.rgb(240, 170, 70)
        BubbleState.ERROR -> Color.rgb(150, 30, 30) to Color.rgb(200, 60, 60)
    }
}
