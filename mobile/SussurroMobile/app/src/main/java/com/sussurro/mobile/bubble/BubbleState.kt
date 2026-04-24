package com.sussurro.mobile.bubble

enum class BubbleState(val label: String) {
    IDLE("Pronto"),
    RECORDING("Gravando…"),
    UPLOADING("Enviando…"),
    TRANSCRIBING("Transcrevendo…"),
    FALLBACK("Usando fallback…"),
    ERROR("Erro"),
}
