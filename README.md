# Telegram Promo Bot

Bot de monitoramento de promoções no Telegram. Escuta grupos via MTProto (Telethon),
filtra por keywords e preço, e envia notificações no seu chat pessoal via Bot API.

## Arquitetura resumida

```
Grupos → Telethon listener → Processor (preço + normalização)
       → FilterEngine (keywords + preço + dedup) → Notifier → você
```

Comandos `/add /remove /list /price /addgroup /removegroup /listgroups /quiet /history /stats /status` são recebidos por long polling na Bot API.

---

## Pré-requisitos

- Python 3.11+
- Conta no Telegram
- Bot criado no [@BotFather](https://t.me/BotFather) (gera o `BOT_TOKEN`)
- Credenciais MTProto obtidas em [my.telegram.org](https://my.telegram.org) (`API_ID`, `API_HASH`)
- Seu chat_id pessoal (envie qualquer mensagem para [@userinfobot](https://t.me/userinfobot))

---

## Instalação

```bash
git clone <url>
cd telegram-promo-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Para desenvolvimento e testes:

```bash
pip install -r requirements-dev.txt
```

---

## Configuração

Copie o template e edite:

```bash
cp .env.example .env
```

### Como obter cada variável

| Variável | Como obter |
|---|---|
| `TELEGRAM_API_ID` | [my.telegram.org](https://my.telegram.org) → API development tools |
| `TELEGRAM_API_HASH` | Mesma página acima (32 caracteres hex) |
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` |
| `OWNER_CHAT_ID` | [@userinfobot](https://t.me/userinfobot) → ele responde com seu ID |
| `MONITORED_GROUPS` | IDs (`-1001234567890`) ou usernames (`promosdobrasil`), separados por vírgula |
| `DEFAULT_MAX_PRICE` | Preço máximo padrão. `0` desativa o filtro global |
| `DATABASE_PATH` | Caminho do SQLite (default `promo_bot.db`) |
| `SESSION_NAME` | Nome do arquivo de sessão do Telethon |

⚠️ **Importante:** sua conta Telegram precisa já ser membro dos grupos monitorados.

---

## Primeira execução

```bash
python main.py
```

Na primeira vez o Telethon pedirá no terminal o seu número de telefone e o código de
verificação enviado pelo Telegram. Após autenticar, ele cria um arquivo
`<SESSION_NAME>.session` que será reutilizado nas próximas execuções (não commite esse
arquivo).

Você verá no log:

```
Banco de dados inicializado em promo_bot.db
Telethon conectado.
Monitorando grupo: promosdobrasil
Bot iniciado. Aguardando promoções...
```

Encerre com `Ctrl+C` — o shutdown é gracioso.

---

## Comandos

Envie mensagens diretamente ao **seu bot** (não nos grupos monitorados).
Apenas o `OWNER_CHAT_ID` é respondido — qualquer outro remetente é ignorado.

### `/add <keyword> [preço_máximo]`

Adiciona uma keyword. O último token vira preço se for numérico.

```
/add monitor             → sem filtro de preço
/add monitor 1500        → keyword "monitor", até R$ 1.500,00
/add monitor gamer 2000  → keyword "monitor gamer", até R$ 2.000,00
```

### `/remove <keyword>`

```
/remove monitor gamer
```

### `/list`

Lista todas as keywords com seus filtros de preço.

### `/price <keyword> <valor>`

Atualiza ou remove o filtro de preço (`0` remove).

```
/price monitor 1200   → define R$ 1.200
/price monitor 0      → remove o filtro
```

### `/addgroup <username_ou_id>` e `/removegroup <username_ou_id>`

Adiciona ou remove grupos monitorados em tempo real, sem editar o `.env` nem
reiniciar o processo. O grupo é validado via Telethon antes de ser salvo.

```
/addgroup Fraguas84Oficial
/addgroup -1001234567890
/removegroup cupomnarede
```

### `/listgroups`

Lista os grupos monitorados, separando os vindos do `.env` dos adicionados via bot.

### `/quiet <HH:MM HH:MM | off>`

Configura o horário silencioso (fuso de Brasília). Durante o período, nenhuma
notificação é enviada (a mensagem não é marcada como vista, então pode notificar
depois do período). Suporta intervalos que atravessam a meia-noite.

```
/quiet 23:00 07:00   → ativa das 23h às 7h
/quiet off           → desativa
/quiet               → mostra a configuração atual
```

### `/history [n]`

Mostra as últimas `n` promoções notificadas (padrão 5, máximo 20), com grupo,
keywords, preço e cupom.

### `/stats`

Exibe totais de mensagens processadas/notificadas, notificações de hoje e os
rankings de top keywords e top grupos.

### `/status`

Mostra grupos monitorados (do `.env` + via bot), número de keywords, preço padrão e uptime.

---

## Como funciona o filtro de preço

1. O processor tenta extrair um preço da mensagem (formato `R$ 1.299,99`, `R$800`, etc.).
   Quando há múltiplos preços, o **menor** vence (preço promocional).
2. Se a keyword tem `max_price`, a mensagem precisa ter preço extraído **e** `<= max_price`.
3. Se a keyword não tem `max_price` mas há `DEFAULT_MAX_PRICE > 0`, ele é usado.
4. Caso contrário, a keyword passa sem filtro de preço.
5. Cada `(message_id, group_id)` é marcado como visto após o primeiro match — sem duplicatas.

O processor também extrai cupons (entre crases `` `CODIGO` `` ou após palavras-chave como
`cupom:`/`código:`), que aparecem na notificação como `🎟️ Cupom: CODIGO`.

---

## Testes

```bash
pytest tests/ -v
```

---

## Variáveis de ambiente

| Nome | Obrigatório | Default | Descrição |
|---|---|---|---|
| `TELEGRAM_API_ID` | ✅ | — | API ID do my.telegram.org |
| `TELEGRAM_API_HASH` | ✅ | — | API hash (32 chars) |
| `BOT_TOKEN` | ✅ | — | Token do @BotFather |
| `OWNER_CHAT_ID` | ✅ | — | Seu chat_id pessoal |
| `MONITORED_GROUPS` | ✅ | — | CSV de IDs/usernames |
| `DEFAULT_MAX_PRICE` | ❌ | `0.0` | Preço máximo global (0 desativa) |
| `DATABASE_PATH` | ❌ | `promo_bot.db` | Caminho do SQLite |
| `SESSION_NAME` | ❌ | `promo_bot_session` | Nome do `.session` |

---

## Deploy gratuito (Oracle Cloud Free Tier)

Resumo do passo a passo para subir 24/7:

1. Crie uma conta em [oracle.com/cloud/free](https://www.oracle.com/cloud/free/).
2. Provisione uma instância **VM.Standard.A1.Flex** (ARM, Always Free): Ubuntu 22.04,
   1 OCPU, 6 GB RAM.
3. Abra a porta SSH (default) e gere/baixe o par de chaves.
4. SSH na VM:
   ```bash
   ssh ubuntu@<ip>
   sudo apt update && sudo apt install -y python3.11 python3.11-venv git
   git clone <seu-repo>
   cd telegram-promo-bot
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
5. Crie o `.env` com seus valores.
6. Faça a primeira execução **interativa** (`python main.py`) para gerar o `.session`.
7. Pare (`Ctrl+C`) e crie o serviço systemd `/etc/systemd/system/promo-bot.service`:
   ```ini
   [Unit]
   Description=Telegram Promo Bot
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/telegram-promo-bot
   ExecStart=/home/ubuntu/telegram-promo-bot/.venv/bin/python main.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
8. Ative:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now promo-bot
   sudo systemctl status promo-bot
   journalctl -u promo-bot -f
   ```

Pronto — o bot vai reiniciar automaticamente e roda 24/7 sem custo.

---

## Estrutura

```
telegram-promo-bot/
├── src/
│   ├── client.py          # listener MTProto
│   ├── bot.py             # long polling Bot API
│   ├── processor.py       # normalização + extração de preço
│   ├── filter_engine.py   # keywords + preço + dedup
│   ├── repository.py      # SQLite async
│   ├── notifier.py        # envio formatado
│   ├── commands.py        # /add /remove /list /price /addgroup /quiet /history /stats ...
│   └── models.py          # dataclasses tipadas
├── tests/
├── main.py
├── config.py
└── .env.example
```
