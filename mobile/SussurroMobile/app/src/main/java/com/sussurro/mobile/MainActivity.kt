package com.sussurro.mobile

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sussurro.mobile.bubble.BubbleOverlayService
import com.sussurro.mobile.config.ConfigStore
import com.sussurro.mobile.inject.SussurroAccessibilityService
import com.sussurro.mobile.net.ServerDiscovery
import com.sussurro.mobile.net.TranscriberClient
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Color(0xFF7CC4FF))) {
                SussurroConfigScreen()
            }
        }
    }
}

@Composable
private fun SussurroConfigScreen() {
    val context = LocalContext.current
    val config = remember { ConfigStore(context) }
    val scope = rememberCoroutineScope()

    var serverUrl by remember { mutableStateOf(config.serverUrl) }
    var token by remember { mutableStateOf(config.token) }
    var useA11y by remember { mutableStateOf(config.useAccessibilityPaste) }
    var useFallback by remember { mutableStateOf(config.fallbackToGoogle) }
    var statusMessage by remember { mutableStateOf<String?>(null) }

    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    val notifPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    val overlayLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {}

    Surface(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(Color(0xFF101014))
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                "Sussurro",
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF7CC4FF),
            )
            Text(
                "Ditado por voz via servidor Whisper",
                fontSize = 14.sp,
                color = Color(0xFFB0B0C0),
            )

            Spacer(Modifier.height(4.dp))

            SectionCard(title = "Servidor") {
                OutlinedTextField(
                    value = serverUrl,
                    onValueChange = { serverUrl = it },
                    label = { Text("URL do servidor") },
                    placeholder = { Text("http://192.168.0.100:8765") },
                    singleLine = true,
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = KeyboardType.Uri),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = token,
                    onValueChange = { token = it },
                    label = { Text("Token") },
                    placeholder = { Text("cole o token do server") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = {
                        config.serverUrl = serverUrl
                        config.token = token
                        statusMessage = "Salvo"
                    }) { Text("Salvar") }

                    OutlinedButton(onClick = {
                        scope.launch {
                            statusMessage = "Procurando servidor na rede…"
                            val url = ServerDiscovery(context).discover()
                            statusMessage = if (url != null) {
                                serverUrl = url
                                config.serverUrl = url
                                "Encontrado: $url"
                            } else {
                                "Nada encontrado via mDNS"
                            }
                        }
                    }) { Text("Descobrir") }

                    OutlinedButton(onClick = {
                        scope.launch {
                            statusMessage = "Testando…"
                            val ok = TranscriberClient(serverUrl.ifBlank { config.serverUrl }, token).health()
                            statusMessage = if (ok.getOrDefault(false)) "OK — servidor respondendo" else "Falhou: ${ok.exceptionOrNull()?.message ?: "sem resposta"}"
                        }
                    }) { Text("Testar") }
                }
            }

            SectionCard(title = "Comportamento") {
                LabeledSwitch(
                    label = "Colar automaticamente via Acessibilidade",
                    checked = useA11y,
                    onChange = { useA11y = it; config.useAccessibilityPaste = it },
                )
                LabeledSwitch(
                    label = "Fallback para reconhecimento do Google quando offline",
                    checked = useFallback,
                    onChange = { useFallback = it; config.fallbackToGoogle = it },
                )
            }

            SectionCard(title = "Permissões") {
                PermissionRow(
                    label = "Microfone",
                    grantedText = "Necessário para gravar sua voz",
                ) { micPermission.launch(Manifest.permission.RECORD_AUDIO) }

                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    PermissionRow(
                        label = "Notificações",
                        grantedText = "Para o serviço em segundo plano",
                    ) { notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS) }
                }

                PermissionRow(
                    label = "Sobreposição (overlay)",
                    grantedText = if (Settings.canDrawOverlays(context)) "Concedida" else "Necessária para a bolinha flutuante",
                ) {
                    val intent = Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:${context.packageName}"),
                    )
                    overlayLauncher.launch(intent)
                }

                PermissionRow(
                    label = "Acessibilidade (opcional)",
                    grantedText = if (SussurroAccessibilityService.isRunning()) "Ativa" else "Para colar no campo focado",
                ) {
                    context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                }
            }

            SectionCard(title = "Bubble") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = {
                            config.serverUrl = serverUrl
                            config.token = token
                            if (!Settings.canDrawOverlays(context)) {
                                Toast.makeText(context, "Conceda permissão de overlay primeiro", Toast.LENGTH_SHORT).show()
                                return@Button
                            }
                            if (!config.isConfigured()) {
                                Toast.makeText(context, "Configure URL + token", Toast.LENGTH_SHORT).show()
                                return@Button
                            }
                            BubbleOverlayService.start(context)
                            Toast.makeText(context, "Bubble ativa", Toast.LENGTH_SHORT).show()
                        },
                    ) { Text("Ativar bubble") }

                    OutlinedButton(onClick = { BubbleOverlayService.stop(context) }) {
                        Text("Desativar")
                    }
                }
                Text(
                    "Mantenha a bolinha pressionada para falar. Solte para transcrever.",
                    fontSize = 12.sp,
                    color = Color(0xFF9090A0),
                )
            }

            statusMessage?.let {
                Text(
                    it,
                    color = Color(0xFF7CC4FF),
                    modifier = Modifier.fillMaxWidth(),
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF17171E)),
    ) {
        Column(
            Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, fontWeight = FontWeight.SemiBold, color = Color.White, fontSize = 16.sp)
            content()
        }
    }
}

@Composable
private fun LabeledSwitch(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(label, modifier = Modifier.weight(1f), color = Color.White, fontSize = 14.sp)
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
private fun PermissionRow(label: String, grantedText: String, onClick: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, color = Color.White, fontSize = 14.sp)
            Text(grantedText, color = Color(0xFF9090A0), fontSize = 12.sp)
        }
        OutlinedButton(onClick = onClick) { Text("Abrir") }
    }
}
