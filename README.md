# 📊 AssessorHub — Atualização Automática Diária

Painel do assessor de investimentos com atualização automática às **06h (Brasília)**, de segunda a sexta.

---

## ✅ Como configurar (passo a passo)

### 1. Criar conta no GitHub (se ainda não tiver)
Acesse [github.com](https://github.com) e crie uma conta gratuita.

---

### 2. Criar o repositório
1. Clique em **"New repository"**
2. Nome: `assessor-hub`
3. Marque **"Public"** (necessário para GitHub Pages grátis)
4. Clique em **"Create repository"**

---

### 3. Fazer upload dos arquivos
Faça upload dos 3 arquivos para o repositório:
- `update_hub.py`
- `.github/workflows/update.yml`
- `index.html` (o hub atual — será substituído automaticamente todo dia)

> Dica: arraste os arquivos diretamente na página do repositório.

---

### 4. Obter as chaves de API gratuitas

#### 🔑 BRAPI (cotações B3, dólar)
1. Acesse [brapi.dev](https://brapi.dev)
2. Clique em **"Começar grátis"**
3. Crie sua conta
4. Copie o **token** gerado no painel

#### 🔑 NewsData.io (notícias financeiras)
1. Acesse [newsdata.io](https://newsdata.io)
2. Clique em **"Register"**
3. Crie sua conta gratuita
4. Copie a **API Key** do painel

---

### 5. Adicionar as chaves no GitHub (Secrets)
1. No repositório, vá em **Settings → Secrets and variables → Actions**
2. Clique em **"New repository secret"**
3. Adicione:
   - Nome: `BRAPI_TOKEN` → Valor: *(seu token brapi)*
   - Nome: `NEWS_API_KEY` → Valor: *(sua chave newsdata.io)*

---

### 6. Ativar o GitHub Pages
1. No repositório, vá em **Settings → Pages**
2. Em **"Branch"**, selecione `main` e pasta `/root`
3. Clique em **"Save"**
4. Aguarde ~1 minuto
5. Seu hub estará disponível em:
   ```
   https://SEU_USUARIO.github.io/assessor-hub/
   ```

---

### 7. Testar manualmente
1. Vá em **Actions** no repositório
2. Clique em **"🔄 Atualizar AssessorHub"**
3. Clique em **"Run workflow"**
4. Aguarde ~30 segundos
5. Acesse o link do GitHub Pages — o hub estará atualizado!

---

## 🕕 Horário de atualização
O hub atualiza automaticamente:
- **De segunda a sexta**
- **Às 06h00 (horário de Brasília)**

Para alterar o horário, edite a linha `cron` no arquivo `.github/workflows/update.yml`:
```yaml
- cron: '0 9 * * 1-5'   # 09:00 UTC = 06:00 BRT
```

---

## 📦 APIs utilizadas (todas gratuitas)
| API | O que busca | Limite grátis |
|-----|-------------|---------------|
| [brapi.dev](https://brapi.dev) | Ibovespa, ações B3, Dólar | 1.000 req/mês |
| [newsdata.io](https://newsdata.io) | Notícias financeiras BR | 200 req/dia |
| [api.bcb.gov.br](https://api.bcb.gov.br) | Selic oficial (Banco Central) | Sem limite |

---

## ❓ Dúvidas frequentes

**O hub não atualizou hoje. O que fazer?**
→ Vá em *Actions*, clique no último workflow e veja os logs de erro.

**Posso rodar nos fins de semana também?**
→ Sim! Mude `1-5` para `*` no cron: `'0 9 * * *'`

**Posso adicionar mais ações na planilha?**
→ Sim, edite o array `sheetData` no final do `update_hub.py`.
