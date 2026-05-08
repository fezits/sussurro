# Sussurro Meeting Mode — Design Spec

**Data:** 2026-04-28
**Autor:** Fernando Braidatto
**Status:** Aprovado em discussão; pendente revisão escrita

## 1. Objetivo

Adicionar ao Sussurro um modo de transcrição ao vivo de reuniões online (Teams, Meet, Zoom) com:

- Captura simultânea do áudio do sistema (outras pessoas) e do microfone (você).
- Transcrição em duas trilhas separadas com identificação de quem falou.
- Janela ao vivo mostrando o diálogo em tempo real, **invisível** quando você compartilha tela.
- Detecção automática de perguntas direcionadas a você, com sugestão de resposta gerada por LLM.
- Sugestão usa um classificador que distingue pergunta **pessoal** (responde com base no seu perfil), **técnica** (responde com conhecimento do LLM) ou **híbrida** (combina os dois).
- Sumário automático ao final da reunião.

O ditado por hotkey existente (`Ctrl+Win`) continua funcionando em paralelo, sem mudanças.

## 2. Não-objetivos

- Não fazer "speaker diarization" entre múltiplas pessoas remotas — todas as vozes do canal "Eles" entram como um único speaker.
- Não editar transcrição na janela ao vivo (v1). Edição manual posterior nos arquivos `.txt`.
- Não traduzir entre idiomas. Português apenas (mesma config do ditado).
- Não publicar/sincronizar reuniões em nuvem. Tudo local em `reunioes/`.
- Não suportar gravação de chamada telefônica do celular. Mobile fica fora do escopo desta v1.

## 3. Decisões de design

| Decisão | Escolha | Motivo |
|---|---|---|
| Captura "Eles" | WASAPI loopback via `pyaudiowpatch` | API nativa do Windows, sem precisar de drivers virtuais (VB-Cable, etc) |
| Captura "Você" | `sounddevice` (já usado pelo ditado) | Já existe e funciona |
| VAD | `silero-vad` (ONNX, ~2 MB) | Detecta fim de turno; usado também por `faster-whisper` |
| Transcrição | `faster-whisper` modelo `small` | Reusa modelo já baixado (464 MB) |
| LLM principal | Groq + Llama 3.3 70B | Tier grátis 6k req/dia, latência ~0.5s, qualidade alta, política sem treino |
| LLM classificador | Groq + Llama 3.1 8B Instant | Mesmo provider, ~200ms, suficiente pra escolha A/B/C |
| LLM fallback local | Qwen 2.5 7B Instruct (GGUF Q4_K_M) | Melhor compacto pt-BR, opt-in (4.5 GB de download) |
| Embeddings RAG | `paraphrase-multilingual-MiniLM-L12-v2` | Multilíngue, leve (120 MB), CPU-friendly |
| Storage do índice RAG | `numpy.savez` em `knowledge/.index.npz` | Sem dependência de banco vetorial; reindexa só se hash mudar |
| Invisibilidade da janela | `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` | API nativa Windows 10 2004+/11 |
| UI | Qt (PySide6) | Mesmo stack do desktop atual |
| Coexistência com ditado | Mic é compartilhável; controllers separados | Sem race condition |

## 4. Fluxo de uso

1. Usuário está numa reunião do Teams.
2. Clique direito na bolinha do Sussurro → **"Iniciar reunião"** (item novo no menu de contexto).
3. Bolinha muda visual pra modo `REC` (vermelho contínuo, não pulsando).
4. Janela ao vivo abre, posicionada onde foi deixada na última vez (default: canto superior direito).
5. Janela é invisível pra qualquer software de captura de tela (Teams, Zoom, OBS, Meet, Discord).
6. Conforme as pessoas falam, turnos transcritos aparecem na janela em duas cores.
7. Quando o sistema detecta que **alguém fez uma pergunta a você**, dispara o pipeline:
   - Classifica pergunta (pessoal/técnica/híbrida) — ~200ms
   - Recupera contexto do RAG se aplicável — ~50ms
   - Gera resposta — ~1-1.5s
   - Card de sugestão aparece no topo da janela colorido por tipo (amarelo/azul/roxo)
8. Usuário lê a sugestão, adapta com sua voz, clica `✓ Usar` (copia ao clipboard) ou `✕` (descarta), ou ignora (some em 90s).
9. Ao clicar **"Parar reunião"** (na janela ou na bolinha), sistema salva:
   - `reunioes/{timestamp}/transcript.txt` — diálogo com timestamps
   - `reunioes/{timestamp}/sumario.md` — gerado pelo LLM
   - `reunioes/{timestamp}/audio.wav` — opcional (config `save_raw_wav`)
10. Janela fecha. Bolinha volta ao modo idle.

## 5. Arquitetura

### 5.1 Estrutura de arquivos

```
c:/Projetos/Sussurro/
├── src/                       # existente, ditado desktop
├── server/                    # existente, server HTTP do mobile
├── meeting/                   # NOVO
│   ├── __init__.py
│   ├── controller.py          # State machine: idle/recording/paused/stopped
│   ├── audio/
│   │   ├── system_capture.py  # WASAPI loopback ("Eles")
│   │   ├── mic_capture.py     # Mic ("Você") — wrapper sobre src/recorder.py
│   │   └── vad.py             # silero-vad wrapper, detecta fim de turno
│   ├── transcribe/
│   │   ├── pipeline.py        # 2 filas (eles/você), workers paralelos
│   │   └── turn.py            # dataclass Turn{speaker, start, end, text}
│   ├── intelligence/
│   │   ├── question_detector.py   # heurísticas: ?, palavras-chave, prosódia
│   │   ├── classifier.py          # pessoal / técnica / híbrida
│   │   ├── llm_client.py          # Groq / Anthropic / OpenAI / local
│   │   ├── rag/
│   │   │   ├── indexer.py
│   │   │   ├── retriever.py
│   │   │   └── chunker.py
│   │   ├── responder.py           # orquestra: detector → classifier → RAG → LLM
│   │   └── summarizer.py          # gera sumário no fim da reunião
│   ├── persistence/
│   │   └── session_writer.py      # salva transcript/sumario/audio + autosave
│   ├── ui/
│   │   ├── live_window.py
│   │   ├── suggestion_card.py
│   │   ├── transcript_view.py
│   │   └── invisibility.py        # SetWindowDisplayAffinity wrapper
│   └── meeting_config.yaml
├── knowledge/                 # NOVO — base de conhecimento do usuário
│   ├── perfil.md
│   ├── cv.pdf (opcional)
│   ├── projetos/ (opcional)
│   └── tecnico/ (opcional)
└── reunioes/                  # NOVO — saídas (gitignored)
    └── {YYYY-MM-DD_HH-MM}/
        ├── transcript.txt
        ├── sumario.md
        └── audio.wav
```

### 5.2 Pipelines

**Pipeline de captura/transcrição (dois canais paralelos):**

```
[ Mic ]    ─►  buffer 30s  ─►  VAD  ─►  fila "Você"  ─┐
                                                       ├─►  Transcriber pool (2 workers, modelo small)
[ Loopback ] ─►  buffer 30s  ─►  VAD  ─►  fila "Eles" ─┘
                                                              │
                                                              ▼
                                                  [ Turn{speaker, start, end, text} ]
                                                              │
                                              ┌───────────────┴───────────────┐
                                              ▼                               ▼
                                  [ live_window: render ]         [ persistence: append ]
                                              │
                                              ▼
                                  [ question_detector (apenas "Eles") ]
                                              │
                                              ▼
                                       [ responder (async) ]
                                              │
                                              ▼
                                  [ live_window: suggestion_card ]
```

Cada chunk de áudio é fechado quando o VAD detecta silêncio de 800ms OU quando atinge 30s contínuos (proteção contra falar ininterrupto).

**Pipeline de resposta (modo entrevista):**

```
Turno "Eles" finalizado
        │
        ▼
question_detector.is_question(text, audio_tail)
   │
   └─ heurísticas: termina com '?' / palavras-chave / tom interrogativo
        │
        ▼ (se sim)
classifier.classify(question, recent_context)  ─► A | B | C
        │
        ▼
┌───────┴──────────┬───────────────────┐
A: pessoal      B: técnica         C: híbrida
│                  │                   │
RAG no perfil   sem RAG          RAG no perfil
        │                  │                   │
        └─────────┬─────────┴─────────┬─────────┘
                  ▼                   ▼
        prompt + contexto recente da reunião
                  │
                  ▼
         llm_client.complete(prompt)
                  │
                  ▼
   live_window.show_suggestion(text, kind=A|B|C)
```

### 5.3 Componentes (responsabilidades)

| Componente | Responsabilidade | Depende de |
|---|---|---|
| `MeetingController` | Liga/desliga capturers, gerencia estado, coordena UI | audio.*, transcribe.*, intelligence.*, ui.live_window |
| `SystemCapture` | WASAPI loopback contínuo, expõe stream 16kHz mono | pyaudiowpatch |
| `MicCapture` | Mic contínuo, expõe stream 16kHz mono | sounddevice (compartilha device com ditado) |
| `VAD` | Recebe stream, emite eventos `turn_started`/`turn_ended` | silero-vad |
| `TranscribePipeline` | Filas + workers, transcreve chunks, emite `Turn` | faster-whisper |
| `QuestionDetector` | Decide se um turno é pergunta (heurísticas) | — (puro Python) |
| `Classifier` | Chama LLM rápido pra classificar A/B/C | llm_client |
| `RagIndexer` | Lê knowledge/, gera embeddings, salva .index.npz | sentence-transformers, pypdf |
| `RagRetriever` | Cosine similarity em memória, top-k chunks | numpy |
| `Responder` | Orquestra detector → classifier → RAG → LLM → emit suggestion | todos os intelligence/* |
| `Summarizer` | Recebe transcript completo, pede sumário ao LLM | llm_client |
| `LlmClient` | Abstração sobre Groq/Anthropic/OpenAI/local | groq, anthropic, openai, llama-cpp-python |
| `LiveWindow` | Renderiza turnos + card de sugestão; invisível pra captura | PySide6 |
| `SessionWriter` | Salva artefatos no fim + autosave a cada 30s | — |

### 5.4 Detecção de pergunta — heurísticas

`QuestionDetector` recebe `(text: str, audio_tail: bytes)` e retorna `bool`. Decisão é "2 de 3":

1. **Pontuação:** `text.endswith('?')` (Whisper coloca pontuação automaticamente em pt-BR).
2. **Palavras-chave:** lista pt-BR — `como`, `por que`, `qual`, `quando`, `onde`, `quem`, `o que`, `cadê`, `me conta`, `me fala`, `você`, `pra você`, `na sua opinião`, `experiência`, `já trabalhou`, `entende de`, `sabe`, `saberia`, `consegue`. Match em qualquer posição da frase.
3. **Tom interrogativo:** energia RMS dos últimos 300ms do áudio é >= 1.3× a média da frase (heurística de pitch subindo). Se não tiver áudio disponível, ignora.

## 6. Configuração

`meeting/meeting_config.yaml`:

```yaml
audio:
  system_loopback: true
  microphone: true
  save_raw_wav: false
  vad_silence_ms: 800

transcribe:
  model: small
  language: pt
  parallel_workers: 2

llm:
  provider: groq                # groq | local | anthropic | openai
  model: llama-3.3-70b-versatile
  api_key_env: GROQ_API_KEY
  classifier_model: llama-3.1-8b-instant

  local:
    model_path: models/llm/qwen2.5-7b-instruct-q4_k_m.gguf
    n_ctx: 8192
    n_threads: 8

rag:
  knowledge_dir: knowledge
  embedding_model: paraphrase-multilingual-MiniLM-L12-v2
  chunk_size: 500
  chunk_overlap: 50
  top_k: 5

intelligence:
  question_detection: true
  auto_suggest: true
  context_window_minutes: 2     # últimos N minutos de transcrição (ambos canais, ordenados por timestamp) injetados como contexto no prompt do LLM
  suggestion_ttl_seconds: 90

ui:
  invisible_to_capture: true
  opacity: 0.92
  always_on_top: true

storage:
  output_dir: reunioes
```

API keys ficam em variável de ambiente, **nunca no yaml**. O config aponta o nome da env var.

## 7. UI da janela ao vivo

```
┌─────────────────────────────────────────────────────────┐
│ Sussurro Meeting   🛡️ Invisível  [⏸ Pausar] [⏹ Parar] │
├─────────────────────────────────────────────────────────┤
│ ╔════════════════════════════════════════════════════╗  │
│ ║ 💡 SUGESTÃO  🔀 Híbrida           [✓ Usar] [✕]    ║  │
│ ║ Sim, já trabalhei com Python por 8 anos. (...)    ║  │
│ ╚════════════════════════════════════════════════════╝  │
│                                                         │
│ 14:32:01 [Eles]   Olá pessoal, vamos começar.          │
│ 14:32:08 [Você]   Bom dia, tudo certo aqui.            │
│ 14:32:15 [Eles]   Conta um pouco sobre sua experiência │
│                   com Python e processamento de áudio? │
│                                                         │
│ ▼ rolagem automática                                    │
│                                                         │
│ [🔁 Forçar sugestão]                                    │
└─────────────────────────────────────────────────────────┘
```

- **Invisibilidade:** flag `WDA_EXCLUDEFROMCAPTURE` aplicada na criação da janela e quando o handle muda.
- **Sempre on top + arrastável + redimensionável.**
- **Posição/tamanho** persistidos em `meeting/.window_state.json`.
- **Card de sugestão** com cor por tipo (amarelo `🧠 Pessoal`, azul `📚 Técnica`, roxo `🔀 Híbrida`); some em `suggestion_ttl_seconds` ou quando outra sugestão chega.
- **Atalhos** com janela em foco: `Esc` descarta; `Enter` copia; `Ctrl+P` pausa/retoma; `Ctrl+Q` para reunião.

## 8. Erros e degradação

| Cenário | Comportamento |
|---|---|
| API LLM fora / sem key | Card "⚠ LLM offline · ative fallback local". Transcrição segue. |
| WASAPI loopback indisponível | Modal explicativo, botão "Continuar só com mic" |
| Microfone bloqueado | Avisa, segue só com canal "Eles" |
| `knowledge/` vazia | Sugestões pessoais ficam genéricas (LLM responde sem RAG) |
| Limite Groq excedido | Cai pro local se baixado; senão "limite excedido" no card |
| Crash da janela | Capture+transcribe seguem; janela reabre sem perder turnos (turnos vão pro `SessionWriter` independente de UI) |
| App fecha durante reunião | `SessionWriter` faz autosave a cada 30s em `reunioes/{ts}/.partial`. Próxima abertura oferece "Recuperar?" |

## 9. Privacidade

- **Default Groq:** transcrição + perfil + contexto recente saem do PC pra Groq via HTTPS. Política da Groq: não treinam em dados de API. Zero retenção quando ativada na config da conta.
- **Provider local (opt-in):** tudo fica no PC. Latência maior (5-8s vs 0.5-1s).
- **Config por reunião:** menu de contexto da bolinha tem submenu "Provider" pra alternar antes de iniciar.
- **`reunioes/` é gitignored.** Audio bruto também só se `save_raw_wav: true`.
- **API keys**: só em env vars. Nunca em yaml, nunca no commit.

## 10. Custos

Com Groq grátis (default):

- Reunião de 1h gera ~15-25 perguntas detectadas.
- Cada pergunta dispara: 1 classificador (~50 tokens) + 1 resposta (~300 tokens contexto + 150 saída).
- Total por reunião: ~50 requests, ~30k tokens.
- Free tier: 6.000 requests/dia, ~14.4M tokens/dia.
- **Custo: $0** dentro do free tier (>100 reuniões/dia caberiam).

Se exceder, fallback automático pro local (se baixado) ou aviso "limite excedido". Tier pago Groq: ~$0.59/M tokens (~$0.02 por reunião).

## 11. Disco

| Item | Tamanho |
|---|---|
| Existente: Whisper small | 464 MB |
| Novo: silero-vad | 2 MB |
| Novo: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | 120 MB |
| Novo (opt-in): Qwen 2.5 7B GGUF Q4_K_M | 4.5 GB |
| **Total com Groq default** | ~590 MB |
| **Total com fallback local** | ~5.1 GB |

## 12. Build do exe

`Sussurro.spec` ganha em `hiddenimports`/`datas`:

- `pyaudiowpatch`, `silero_vad`, `sentence_transformers`, `groq`, `pypdf`
- Excluir do `excludes`: nenhum dos novos (todos necessários)
- Tamanho do `dist/Sussurro/` esperado: 285 MB → ~360 MB

Na primeira execução do modo reunião, baixa silero-vad + embeddings (~125 MB) se não estiverem em `models/`.

## 13. Coexistência com ditado existente

- `src/app.py` ganha:
  - Item de menu de contexto na bolinha: **"Iniciar reunião"** (toggle).
  - Quando ativo, instancia `meeting.controller.MeetingController()`.
  - `PressToTalk` continua funcionando: hotkey `Ctrl+Win` segue ditando como hoje.
- **Mic compartilhado:** ambos abrem `sounddevice.InputStream` no mesmo device — Windows permite múltiplos consumers do mesmo mic. Validado no comportamento atual do Windows 10/11.
- **Conflito visual:** durante reunião, a bolinha vira `REC` vermelho contínuo. Ditado dispara em paralelo, mas a bolinha não muda visual (prioriza modo REC).
- **Recursos:** quando ditado dispara durante reunião, ele só usa o **buffer próprio** dele; não interfere nos buffers da reunião. Saídas independentes (ditado cola via clipboard como hoje; reunião só registra).

## 14. Critérios de sucesso (testes manuais)

1. Iniciar reunião do Teams com 1 outra pessoa. Captura inicia.
2. Outra pessoa fala: aparece como `[Eles]` na janela em <3s.
3. Você fala: aparece como `[Você]` na janela em <3s.
4. Outra pessoa pergunta "qual sua experiência com X?": card de sugestão aparece em <2s, classificado como Pessoal/Híbrida.
5. Outra pessoa pergunta "como funciona Y técnico?": card aparece, classificado como Técnica.
6. Compartilhar tela do Teams mostrando essa janela: outros participantes **não veem** a janela na tela compartilhada.
7. Parar reunião: arquivos `transcript.txt` + `sumario.md` salvos com conteúdo correto.
8. Ditado por `Ctrl+Win` em outro app durante a reunião continua funcionando.
9. Desligar internet: app cai pro local (se ativado) OU mostra "LLM offline" mantendo transcrição.

## 15. Roadmap fora desta v1

- Edição inline da transcrição na janela ao vivo
- Speaker diarization (múltiplas vozes do canal "Eles")
- Tradução em tempo real (en→pt, pt→en)
- Integração com Linear/Notion pra exportar action items do sumário
- Modo mobile (transcrição de reunião gravada por celular)
- Detecção de quem falou primeiro (turn-taking de quem fala em cima do outro)

## 16. Dependências novas

```
pyaudiowpatch>=0.2.12
silero-vad>=5.1
sentence-transformers>=3
groq>=0.13
pypdf>=5
llama-cpp-python>=0.3   # opt-in
pywin32>=308            # SetWindowDisplayAffinity
anthropic>=0.40         # opt-in (provider alternativo)
openai>=1.50            # opt-in (provider alternativo)
```
