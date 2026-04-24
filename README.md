# Sussurro

Clone pessoal do Wispr Flow. Segure `Ctrl+Windows`, fale, solte — a transcrição aparece onde seu cursor estiver. 100% local, usa `faster-whisper`.

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
