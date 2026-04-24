# Sussurro Mobile

App Android que grava sua voz e transcreve usando o servidor Whisper rodando no seu PC. Bolinha flutuante em cima de qualquer app, igual desktop.

## Fluxo

1. Seu PC roda [`server/server.py`](../server/server.py) (Whisper local, expõe HTTP).
2. Celular conecta no servidor via Wi-Fi local (descoberta mDNS ou IP manual) ou Cloudflare Tunnel (redes externas).
3. Você segura a bolinha flutuante, fala, solta. Áudio vai pro servidor, volta como texto, cola no campo focado.

## Passo a passo de uso

### 1. Rodar o servidor no PC

```bash
cd c:/Projetos/Sussurro
python -m server.server
```

Na primeira execução ele gera um token em [`server/server_token.txt`](../server/server_token.txt) e imprime no console algo como:

```
============================================================
 SUSSURRO SERVER
============================================================
 Model      : small (cpu)
 Port       : 8765
 Token      : 7JINc6lOIcJa_hVf29pPDKae5eK9j9o3
 ...
 Reachable at:
   http://192.168.0.15:8765
============================================================
```

Anote o **token** e o **IP local**.

### 2. Instalar o APK no celular

**No emulator (Android Studio):**
```bash
adb install -r mobile/SussurroMobile/app/build/outputs/apk/debug/app-debug.apk
```

**Num celular real via USB:**
1. Celular → Configurações → Sobre → toca 7× em "Número da versão" (ativa modo dev)
2. Opções do desenvolvedor → **Depuração USB: ON**
3. Plugue no PC, aceite o prompt
4. `adb install -r ...`

**Manual (sem adb):** copie o `.apk` pro celular, abra o arquivo, aceite "instalar de fonte desconhecida".

### 3. Configurar no app

1. Abra o app "Sussurro" no celular.
2. **URL do servidor**: cole `http://<ip-do-pc>:8765` OU toque em **Descobrir** (mDNS na Wi-Fi) OU cole a URL do Cloudflare Tunnel.
3. **Token**: cole o token do `server_token.txt`.
4. Toque **Salvar** → **Testar** (deve aparecer "OK — servidor respondendo").

### 4. Conceder permissões

Role até "Permissões" e toque **Abrir** em cada uma:
- **Microfone** — prompt padrão, aceita.
- **Notificações** (Android 13+) — idem.
- **Sobreposição (overlay)** — abre configuração do sistema, ative "Permitir exibição sobre outros apps" pro Sussurro.
- **Acessibilidade (opcional)** — sem ela o texto cai no clipboard e você cola manualmente; com ela cola automático no campo focado.

### 5. Ativar a bubble

Toque **Ativar bubble**. A bolinha cinza aparece no canto da tela, mesmo fora do app.

Uso:
- **Toque e segure** na bolinha — fica vermelha com ondas, gravando.
- **Solte** — fica azul "Enviando…", amarelo "Transcrevendo…", e cola o texto onde seu cursor estiver.
- **Arraste** a bolinha pra qualquer lugar da tela — posição é memorizada.
- Sem servidor / offline + fallback ativado → fica laranja "Usando fallback" e usa o reconhecimento do Google.

## Estados da bolinha

| Cor | Estado |
|---|---|
| Cinza (microfone) | Pronto |
| Vermelho + ondas | Gravando |
| Azul + spinner | Enviando pro servidor |
| Amarelo + spinner | Whisper transcrevendo |
| Laranja + spinner | Fallback Google ativo |
| Vermelho escuro | Erro (texto no label explica) |

## Usar fora da Wi-Fi (Cloudflare Tunnel)

Quando estiver fora de casa, o celular não alcança seu IP local `192.168.x.x`. Solução:

1. Instala [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) no PC.
2. Com o servidor rodando, abre outro terminal e:
   ```bash
   cloudflared tunnel --url http://localhost:8765
   ```
3. Ele imprime uma URL tipo `https://random-name-123.trycloudflare.com`.
4. Cola essa URL no campo **URL do servidor** no app (mantém o mesmo token).
5. Pronto — funciona de qualquer lugar. A URL muda a cada reinício do cloudflared (pra URL fixa precisa de domínio na Cloudflare).

## Build manual do APK

```bash
cd mobile/SussurroMobile
./gradlew.bat assembleDebug
# APK em app/build/outputs/apk/debug/app-debug.apk
```

Requer Android Studio instalado (pra SDK + JDK). O `local.properties` aponta pro SDK em `C:/Users/NOETCOMP-1448/AppData/Local/Android/Sdk` — edite se o caminho for diferente no seu PC.

## Estrutura

```
mobile/SussurroMobile/
├── app/src/main/
│   ├── AndroidManifest.xml
│   ├── java/com/sussurro/mobile/
│   │   ├── MainActivity.kt              # Tela de config (Compose)
│   │   ├── bubble/
│   │   │   ├── BubbleOverlayService.kt  # Foreground service, state machine
│   │   │   ├── BubbleView.kt            # Orb desenhado + waveform + label
│   │   │   └── BubbleState.kt
│   │   ├── audio/AudioRecorder.kt       # MediaRecorder AAC/16k/mono
│   │   ├── net/
│   │   │   ├── TranscriberClient.kt     # OkHttp multipart
│   │   │   └── ServerDiscovery.kt       # mDNS via NsdManager
│   │   ├── fallback/FallbackRecognizer.kt  # Google SpeechRecognizer
│   │   ├── inject/
│   │   │   ├── TextInjector.kt          # Clipboard + paste via A11y
│   │   │   └── SussurroAccessibilityService.kt
│   │   └── config/ConfigStore.kt        # SharedPreferences
│   └── res/…
├── build.gradle.kts
├── settings.gradle.kts
└── gradlew / gradlew.bat
```

## Limitações conhecidas

- **Qualidade do áudio no emulator** usa o mic do PC — suficiente pra testes de fluxo, mas qualidade real só em celular físico.
- **Acessibilidade** pra colar automático: o Android força o usuário a ativar manualmente (e mostra um aviso sério sobre segurança). Sem ela, cai no clipboard + notificação.
- **Cloudflare Tunnel gratuito (`trycloudflare.com`)** gera URL nova a cada reinício. Pra URL fixa, precisa ter um domínio na Cloudflare.
