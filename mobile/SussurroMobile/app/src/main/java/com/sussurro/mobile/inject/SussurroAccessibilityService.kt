package com.sussurro.mobile.inject

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class SussurroAccessibilityService : AccessibilityService() {
    override fun onServiceConnected() {
        super.onServiceConnected()
        INSTANCE = this
    }

    override fun onDestroy() {
        if (INSTANCE === this) INSTANCE = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit
    override fun onInterrupt() = Unit

    companion object {
        @Volatile
        private var INSTANCE: SussurroAccessibilityService? = null

        fun isRunning(): Boolean = INSTANCE != null

        /** Paste clipboard into currently focused editable node. */
        fun pasteIntoFocusedNode(): Boolean {
            val svc = INSTANCE ?: return false
            val root = svc.rootInActiveWindow ?: return false
            val focus = findEditableFocused(root) ?: return false
            return try {
                focus.performAction(AccessibilityNodeInfo.ACTION_PASTE)
            } finally {
                focus.recycle()
                root.recycle()
            }
        }

        private fun findEditableFocused(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            val direct = node.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            if (direct != null && direct.isEditable) return direct
            direct?.recycle()

            for (i in 0 until node.childCount) {
                val child = node.getChild(i) ?: continue
                if (child.isEditable && child.isFocused) return child
                val found = findEditableFocused(child)
                if (found != null) {
                    child.recycle()
                    return found
                }
                child.recycle()
            }
            return null
        }
    }
}
