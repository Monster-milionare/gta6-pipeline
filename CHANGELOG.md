# Histórico de atualizações do GTA VI Brasil (pipeline)

Cada grande mudança ganha número e nome. Versão maior (X.0) = mudança de jeito de trabalhar;
versão menor (X.1, X.2) = ajuste fino em cima dela.

## Atualização 2.0 — "Pegada Nova" (16/11/2026)

**Por que:** os Shorts caíram de centenas de views (10–12/11) para quase zero (a partir de 13/11).
Os melhores vídeos eram curiosidades específicas; os piores eram genéricos ou todos com a mesma cara.

**O que mudou**
- **7 estilos de edição que rotacionam** (`estilos.py`): padrão, turbo (cortes de ~1s, glitch, 1 palavra por vez),
  neon, jornal (faixa URGENTE rolando), cinema (lento/fixo), limpo (fixo, sem efeitos) e leak (VHS + faixa
  "NÃO CONFIRMADO"). Dois vídeos vizinhos nunca usam o mesmo estilo.
- **8 pegadas de roteiro** (número chocante, pergunta, alerta, A ou B, lista de 3, mito/verdade, detalhe que
  ninguém notou, contagem regressiva) — cada short do dia nasce com uma pegada obrigatória diferente.
- **Shorts de vazamento (1–2 por dia):** o radar busca relatos de vazamento/rumor (inclusive os que citam perfis
  como Cyberleaks) em veículos conhecidos. O roteiro é obrigado a citar o veículo, dizer que a Rockstar **não
  confirmou** e usar só o que a manchete diz. Sem relato novo, o vídeo usa contexto histórico público.
  Nunca usamos imagem/vídeo vazado (só material oficial) para não tomar strike.
- **Roteiro de short mais enxuto:** 75–105 palavras, frases de 4–9 palavras, virada a cada duas frases, fecho em A ou B.
- **Placar de métricas** (`metricas.py` + workflow "Placar de metricas"): lê as views, compara cada estilo/pegada/tipo
  com a média e grava `state/pesos.json` e `state/placar.md`. O que rende mais é sorteado mais vezes (peso máx. 2,5);
  o que rende menos aparece menos, mas nunca some (peso mín. 0,4).
- Cada vídeo publicado fica registrado em `state/videos.json` (id, estilo, pegada, tipo).

## Atualização 1.0 — "Base" (até 15/11/2026)

Motor de vídeo "motion" (HUD, legenda palavra a palavra, carimbos, mascote), radar de notícias com trava de fontes,
trava de qualidade e de repetição, publicação agendada e Reels no Instagram, títulos virais.
