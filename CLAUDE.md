# Sussurro — Instruções pro Claude

## Antes de responder sobre comportamento do sistema

**Sempre leia [ARCHITECTURE.md](ARCHITECTURE.md) primeiro.** É a referência viva de cada função:
- Mapa de quem chama quem
- O que cada método faz
- Caminhos exatos `arquivo:linha`
- Lifecycle de "Iniciar reunião" → "Parar reunião"

Não invente comportamento de memória. Se a resposta não está no ARCHITECTURE, abre o código no caminho indicado, confirma, e atualiza o ARCHITECTURE.

## Quando alterar código

Se você mudar o comportamento de uma função listada em `ARCHITECTURE.md`, atualize a entrada correspondente no mesmo commit. Documentação que mente é pior do que documentação ausente.

## Pra debugar problemas no exe

1. `dist/Sussurro/sussurro.log` é o arquivo de log rotativo. Sempre olhe lá antes de chutar.
2. `src/logger.py` é o setup; `log = sussurro_logger.get("nome")` em qualquer módulo.
3. Bugs do exe que não aparecem rodando `python main.py` geralmente são de empacotamento:
   - PyInstaller põe data files em `_internal/` — código tem que ter fallback.
   - Modelos pesados (`models/`) ficam ao lado do exe, copiados por `scripts/finalize_dist.py`.

## Estrutura mínima esperada do `dist/Sussurro/` após build

```
dist/Sussurro/
├── Sussurro.exe
├── config.yaml                ← finalize_dist.py copia
├── models/                    ← finalize_dist.py copia
├── _internal/
│   └── meeting/
│       └── meeting_config.yaml   ← spec inclui
└── (criados em runtime)
    ├── sussurro.log
    ├── knowledge/             ← criado no 1º "Iniciar reunião"
    └── reunioes/<ts>/
```
