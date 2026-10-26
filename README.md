# 📈 Agente de Oportunidades de Investimento (abertura + fechamento)

Agente automatizado em **Python** que roda **duas vezes por dia** no mercado de ações dos EUA e envia tudo para um **canal do Telegram**:

1. **Na ABERTURA** 🔔 — analisa o mercado, seleciona as melhores oportunidades do dia e coloca cada uma **em acompanhamento** (registra o preço de entrada).
2. **No FECHAMENTO** 📊 — pega as indicações em acompanhamento e mostra a **evolução em %** (quanto valorizou ou desvalorizou), tanto no dia quanto desde a indicação, com um resumo de desempenho.

Além disso, **durante o pregão** 🚨 ele monitora as posições a cada 30 minutos e dispara um **alerta intradiário** no Telegram assim que um ativo bate o **stop** ou o **alvo** — sem esperar o fechamento. E todo **sábado** 📅 envia um **relatório semanal consolidado** de desempenho.

Assim você acompanha cada indicação por alguns dias e avalia, com números reais, se a estratégia está sendo rentável. Tudo roda sozinho e **de graça** no seu GitHub via **GitHub Actions**.

> ⚠️ **Aviso importante:** ferramenta de **análise técnica automatizada**, para estudo do mercado. **Não é recomendação de investimento.** Nenhum indicador acerta sempre. Faça sua própria pesquisa e gerencie o risco. As decisões são suas.

---

## 🔁 Como funciona o acompanhamento

- Quando um ativo é indicado na abertura, ele entra no arquivo `data/portfolio.json` com o preço de entrada e a data.
- A cada fechamento, o agente recalcula o desempenho de **todas** as indicações ativas e registra um snapshot em `data/history.csv`.
- Depois de **7 dias corridos** (ajustável), a indicação é **encerrada** automaticamente e arquivada no histórico — é o período que você tem para avaliar se valeu a pena.
- Esses arquivos são gravados de volta no repositório pelo próprio workflow (por isso ele tem permissão de escrita).

### O que chega no Telegram

**Abertura:** lista das oportunidades do dia com score, preço de entrada, RSI, tendência, alvo e stop. 🆕 marca nova indicação, 🔁 marca uma já em acompanhamento.

**Fechamento:** cada indicação com **% desde a indicação**, variação do dia, preço de entrada → preço atual e há quantos dias está sendo acompanhada. No fim, um **resumo**: número de indicações, quantas estão no positivo (taxa de acerto), retorno médio, melhor e pior.

### 🎯 Análise de quando vender / sair da operação

No fechamento, além da evolução, o agente reavalia cada indicação e envia uma **recomendação de ação** (nesta ordem de prioridade):

- 🛑 **VENDER agora — stop atingido**: o preço tocou o stop; corte a perda.
- 🎯 **VENDER agora — alvo atingido**: o preço alcançou o alvo; realize o lucro.
- ⚠️ **AVALIAR SAIDA — tendência enfraquecendo**: 2+ sinais contrários (EMA9 cruzou abaixo da EMA21, MACD virou, perdeu a média de 20, RSI caindo).
- 🔒 **PROTEGER lucro**: está ganhando mas surgiu um alerta — ele sugere **subir o stop** (trailing stop) para travar parte do ganho.
- ✅ **MANTER**: tendência ainda a favor, siga na operação.

Quando a recomendação é vender/sair (stop, alvo ou reversão), a posição é **encerrada automaticamente** e arquivada no histórico — sem precisar esperar o prazo dos 7 dias.

### 🚨 Alertas intradiários (durante o pregão)

A cada **30 minutos** enquanto o mercado está aberto, o agente consulta o preço atual de cada indicação em acompanhamento e:

- 🎯 dispara **ALVO atingido — realize o lucro** quando o preço alcança o alvo;
- 🛑 dispara **STOP atingido — corte a perda** quando o preço toca o stop.

O alerta chega na hora, com preço atual, nível atingido, preço de entrada e o % de resultado. Cada disparo acontece **uma única vez por dia** por ativo (não enche o canal de mensagens repetidas); os alertas são zerados a cada nova abertura. Fora os disparos, o monitoramento é silencioso.

### 📅 Relatório semanal consolidado

Todo **sábado de manhã** o agente envia um resumo da semana (últimos 7 dias):

- **Operações encerradas na semana** (resultado realizado): total, vencedoras, **taxa de acerto**, retorno médio por operação, **resultado acumulado**, melhor e pior, e a quebra por motivo de saída (🎯 alvo · 🛑 stop · ⚠️ reversão · ⏳ fim do prazo), com o detalhe de cada uma.
- **Ainda em acompanhamento** (resultado em aberto): quantas estão abertas, quantas no lucro, resultado médio atual e a lista.

É o retrato que mostra, semana a semana, se a estratégia está realmente sendo rentável.

---

## 🧠 Como as oportunidades são escolhidas

Confluência de sinais (score de 0 a 100): tendência (médias de 20/50/200), momentum (EMA 9/21 + MACD), RSI em zona saudável, volume acima da média e rompimento de máxima recente. Alvo e stop são calculados por ATR, com relação risco/retorno ~1:2.

Classificação: 🟢 FORTE (80+) · 🔵 BOA (65+) · 🟡 NEUTRA (50+).

---

## 🚀 Passo a passo para colocar no ar

### 1. Criar o repositório
Crie um repositório (pode ser privado) e suba todos os arquivos desta pasta.

### 2. Criar o bot do Telegram
No **@BotFather**, envie `/newbot`, siga as instruções e guarde o **TOKEN**.

### 3. Criar o canal e pegar o ID
1. Crie um **novo canal** no Telegram (pode ser privado).
2. Adicione o seu bot como **administrador** do canal.
3. ID do canal:
   - **Público:** use `@nome_do_canal`.
   - **Privado:** poste algo no canal e acesse `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`; pegue o `"chat":{"id":-100XXXXXXXXXX}` (com o `-100`).

### 4. Guardar os segredos no GitHub
**Settings → Secrets and variables → Actions → New repository secret**:

| Nome | Valor |
|------|-------|
| `TELEGRAM_BOT_TOKEN` | o token do BotFather |
| `TELEGRAM_CHAT_ID` | `@seu_canal` ou `-100...` |

### 5. Liberar escrita para o workflow
**Settings → Actions → General → Workflow permissions** → marque **Read and write permissions** (para o agente poder salvar o acompanhamento no repositório). O workflow já pede `contents: write`, mas essa opção precisa estar habilitada.

### 6. Ligar e testar
- Aba **Actions** → habilite os workflows.
- O agente já está agendado: **abertura ~09:35 ET**, **monitoramento a cada 30 min durante o pregão**, **fechamento ~16:10 ET** e **relatório semanal no sábado**, de segunda a sexta.
- Para testar agora: Actions → **Agente de Mercado** → **Run workflow** → escolha `open`, `watch`, `close` ou `weekly`.

Sugestão: rode `open` uma vez, confira a mensagem no canal, e depois rode `close` para ver o acompanhamento.

---

## 🕒 Sobre os horários (importante)

O `cron` do GitHub é sempre em **UTC** e **não se ajusta** ao horário de verão dos EUA. Os horários do workflow estão calibrados para o **horário de verão (EDT, mar–nov)**:

- Abertura: `35 13 * * 1-5` (≈ 09:35 ET)
- Fechamento: `10 20 * * 1-5` (≈ 16:10 ET)

No **inverno dos EUA (nov–março, EST)**, some **+1h** nos dois: `35 14` e `10 21`. Edite em `.github/workflows/market-agent.yml`.

---

## ⚙️ Personalizar

- **Ativos:** edite `tickers.txt`. Ações dos EUA usam o ticker normal (ex.: `AAPL`); ações da bolsa brasileira (B3) usam o sufixo `.SA` (ex.: `PETR4.SA`, `VALE3.SA`). O agente separa automaticamente EUA 🇺🇸 e Brasil 🇧🇷 na mensagem.
- **Rigor do filtro:** `MIN_SCORE` no workflow (maior = mais seletivo).
- **Dias de acompanhamento:** `HOLD_DAYS` no workflow (padrão 7).
- **Quantidade por dia:** variável `TOP_N` (padrão 10 **por mercado**).

---

## 💻 Rodar localmente (para testar)

```bash
pip install -r requirements.txt
cp .env.example .env     # preencha token e chat_id
python -m src.main open  # simula a abertura
python -m src.main watch # checa stop/alvo agora (alerta intradiario)
python -m src.main close # simula o fechamento
python -m src.main weekly # gera o relatorio semanal consolidado
```

---

## 📁 Estrutura

```
investment-agent/
├─ .github/workflows/market-agent.yml   # automacao: abertura + fechamento
├─ src/
│  ├─ main.py              # modos open / close
│  ├─ config.py            # variaveis de ambiente / .env
│  ├─ data_fetcher.py      # baixa dados (yfinance)
│  ├─ indicators.py        # RSI, MACD, medias, ATR
│  ├─ analyzer.py          # score de oportunidade
│  ├─ storage.py           # portfolio.json + history.csv
│  └─ telegram_notifier.py # mensagens de abertura e fechamento
├─ data/                   # acompanhamento (gerado automaticamente)
├─ tickers.txt             # sua watchlist
├─ requirements.txt
├─ .env.example
└─ README.md
```

---

## 📌 Bom senso

- Dados do Yahoo Finance podem ter pequeno atraso e falhas pontuais.
- Análise técnica indica **probabilidade**, nunca **certeza**. Use stop e dimensione a posição.
- Acompanhe no "papel" por algumas semanas antes de usar dinheiro real — é exatamente para isso que o resumo de desempenho serve.
