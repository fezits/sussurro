# Sussurro

Clone pessoal do Wispr Flow. Segure `Ctrl+Windows`, fale, solte — a transcrição aparece onde seu cursor estiver. 100% local, usa `faster-whisper`.

> **Documentação técnica:** [ARCHITECTURE.md](ARCHITECTURE.md) tem o mapa de cada função do sistema, lifecycle de "Iniciar/Parar reunião", e onde cada artefato é gravado.

## Requisitos

- Windows 10/11
- Python 3.11+ (testado em 3.14)
- Microfone
- ~2 GB de disco pro modelo `medium`
- (Opcional) GPU NVIDIA com CUDA pra rodar mais rápido

## Instalação

```bash
pip install -r requirements.txt
```

Primeira execução baixa automaticamente o modelo Whisper `medium` (~1.5 GB) em `~/.cache/huggingface/`.

## Uso

```bash
python main.py
```

- Aparece uma bolinha flutuante no canto inferior direito.
- **Segure `Ctrl+Windows`**, fale, **solte**. O texto é colado no campo focado.
- **Arraste** a bolinha pra onde quiser.
- **Clique direito** na bolinha → *Sair*.

### Estados da bolinha

| Cor | Estado |
|---|---|
| Azul | Carregando modelo |
| Cinza (ícone de microfone) | Pronto |
| Vermelho + ondas | Gravando |
| Amarelo + spinner | Transcrevendo |
| Vermelho escuro | Erro (veja o tooltip) |

## Configuração

Edite `config.yaml`:

```yaml
whisper:
  model: medium          # tiny, base, small, medium, large-v3
  language: pt           # deixe null pra auto-detect
  device: auto           # auto, cpu, cuda
  compute_type: auto     # auto, int8, float16, float32
  beam_size: 5
  vad_filter: true       # ignora silêncio

hotkey:
  combo: ctrl+windows    # qualquer combinação suportada pela lib keyboard

overlay:
  size: 72

inject:
  restore_clipboard: true
  trailing_space: true
```

## Problemas comuns

- **Hotkey não dispara** — a lib `keyboard` às vezes precisa de privilégios elevados no Windows. Rode o terminal como administrador.
- **"Erro mic"** — vá em Configurações → Privacidade → Microfone e habilite acesso a apps desktop.
- **Primeira execução travada em "Carregando modelo…"** — está baixando ~1.5 GB. Aguarde alguns minutos.
- **Lento (>5s)** — estamos rodando em CPU. Troque pra modelo `small` ou `base` no `config.yaml`, ou instale CUDA.

## Arquitetura

```
main.py                 Entry point
config.yaml             Config do usuário
src/
  app.py                Orquestrador / state machine
  recorder.py           Captura áudio (sounddevice) + nível RMS
  transcriber.py        Wrapper faster-whisper
  injector.py           Cola via clipboard + Ctrl+V
  hotkey.py             Press-to-talk global (lib keyboard)
  overlay.py            Bolinha Qt always-on-top com waveform
```

## Meeting Mode

Sussurro também transcreve reuniões do Teams/Meet/Zoom em duas trilhas (você + outros), gera sumário e sugere respostas a perguntas direcionadas a você.

### Setup

1. **Pasta `knowledge/`** — edite `knowledge/perfil.md` com sua bio, experiência, skills, valores. Adicione PDFs/MDs em `knowledge/projetos/` ou `knowledge/tecnico/` se quiser.
2. **Crie conta grátis na Groq** em https://groq.com → API Keys → Create API Key. Copie.
3. **Defina a env var** (PowerShell, perpétuo):
   ```powershell
   setx GROQ_API_KEY "<sua-key>"
   ```
   Reinicie o terminal/Sussurro pra a env var aparecer.

### Uso

1. Inicie sua reunião do Teams/Meet/Zoom.
2. **Clique direito na bolinha do Sussurro** → "Iniciar reunião".
3. Janela ao vivo aparece, invisível pra captura de tela.
4. Conforme as pessoas falam, transcrição rola na tela.
5. Quando alguém te faz pergunta, card de sugestão aparece com a resposta.
6. **Ctrl+Q** ou clique direito → "Parar reunião".
7. Saída em `reunioes/YYYY-MM-DD_HH-MM/`: `transcript.txt` + `sumario.md`.

### Atalhos com a janela em foco

- `Esc` — descarta sugestão
- `Enter` — copia sugestão pro clipboard
- `Ctrl+P` — pausa/retoma captura
- `Ctrl+Q` — encerra reunião

### Privacidade

Default usa Groq (Llama 3.3 70B grátis). Sua transcrição vai pra Groq via HTTPS, não é treinada (política deles). Pra 100% local, edite `meeting/meeting_config.yaml`:

```yaml
llm:
  provider: local
  local:
    model_path: models/llm/qwen2.5-7b-instruct-q4_k_m.gguf
```

Depois `pip install llama-cpp-python` e baixe o GGUF de qwen2.5-7b em https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF.

### Limitações

- Só Windows 10 (build 2004+) ou Windows 11 — usa WASAPI loopback e `WDA_EXCLUDEFROMCAPTURE`.
- Falsos positivos/negativos na detecção de pergunta — botão "Forçar sugestão" pra disparar manual.
- Modo entrevistado em entrevista de emprego pode ser considerado fraude no contexto. Use com responsabilidade.
