package com.sussurro.mobile.net

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

/** Finds a server advertised via mDNS as _sussurro._tcp. */
class ServerDiscovery(private val context: Context) {
    suspend fun discover(timeoutMs: Long = 3000): String? = withTimeoutOrNull(timeoutMs) {
        suspendCancellableCoroutine { cont ->
            val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
            var resolved = false

            val resolveListener = object : NsdManager.ResolveListener {
                override fun onServiceResolved(info: NsdServiceInfo) {
                    if (resolved) return
                    resolved = true
                    val host = info.host?.hostAddress ?: return
                    val port = info.port
                    if (cont.isActive) cont.resume("http://$host:$port")
                }

                override fun onResolveFailed(info: NsdServiceInfo, errorCode: Int) {
                    if (cont.isActive && !resolved) cont.resume(null)
                }
            }

            val discoveryListener = object : NsdManager.DiscoveryListener {
                override fun onStartDiscoveryFailed(t: String, err: Int) {
                    if (cont.isActive) cont.resume(null)
                }

                override fun onStopDiscoveryFailed(t: String, err: Int) = Unit
                override fun onDiscoveryStarted(serviceType: String) = Unit
                override fun onDiscoveryStopped(serviceType: String) = Unit

                override fun onServiceFound(info: NsdServiceInfo) {
                    if (info.serviceType.contains("_sussurro")) {
                        @Suppress("DEPRECATION")
                        nsd.resolveService(info, resolveListener)
                    }
                }

                override fun onServiceLost(info: NsdServiceInfo) = Unit
            }

            nsd.discoverServices("_sussurro._tcp.", NsdManager.PROTOCOL_DNS_SD, discoveryListener)

            cont.invokeOnCancellation {
                runCatching { nsd.stopServiceDiscovery(discoveryListener) }
            }
        }
    }
}
