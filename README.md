# Censo Previdenciário MVP

API simples, legível e funcional para recenseamento previdenciário, desenvolvida em FastAPI com SQLite local.

## Visão geral

Este MVP inclui:
- autenticação com JWT
- cadastro, edição, exclusão, busca e paginação de pessoas
- validação e mascaramento de CPF
- histórico de status do recenseamento
- upload e visualização autenticada de imagens JPG/PNG
- registro de simulações de validação facial (sem reconhecimento biométrico real)
- área administrativa para usuários e auditoria
- dashboard com estatísticas por status, sexo e faixa etária
- exportação de CSV e impressão em PDF pelo navegador
- terminal administrativo com comandos permitidos, modo escuro e bloqueio por inatividade
- sessões Redis opcionais, com renovação por atividade e expiração por inatividade

## Estrutura do projeto

- `app/`: aplicação FastAPI
  - `main.py`: criação da app e roteadores
  - `config.py`: leitura de variáveis de ambiente
  - `database.py`: engine e sessão do SQLite
  - `models.py`: tabelas principais
  - `schemas.py`: modelos Pydantic
  - `auth.py`: segurança, hash de senha e JWT
  - `cpf.py`: validação, cifragem, hash e máscara do CPF
  - `estatisticas.py`: cálculo de estatísticas
  - `routers/`: endpoints organizados por módulo
  - `services/`: regras de negócio
  - `repositories/`: consultas e persistência de pessoas
  - `sessions.py`: integração opcional com Redis para sessões
  - `web/`: frontend simples (neste projeto, servido via `frontend/`)
- `frontend/`: páginas de login e painel web
- `tests/`: testes do backend
- `tests_e2e/`: testes Playwright para frontend (requer instalado `playwright`)
- `.env.example`: exemplo de configuração de ambiente

## Configuração do ambiente

1. Crie o arquivo `.env` a partir do exemplo:

```bash
cp .env.example .env
```

2. Ajuste os valores de acordo com o ambiente local, especialmente:
- `JWT_SECRET_KEY`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

## Como rodar

1. Instale as dependências:

```bash
pip install -r requirements.txt
```

2. Inicie a API:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Para habilitar sessões compartilhadas, invalidação de sessão e cache de estatísticas, inicie Redis
e configure `REDIS_URL` no `.env` (o exemplo usa `redis://localhost:6379/0`). Sem `REDIS_URL`, o app mantém
compatibilidade de desenvolvimento sem sessão Redis; em produção, configure Redis e uma chave JWT
forte. `SESSION_IDLE_MINUTES` define o tempo de inatividade no servidor. A tela do navegador pode
ser configurada para bloquear em 1, 5, 10 ou 15 minutos e exige nova autenticação.

3. Acesse a documentação OpenAPI em:

```text
http://localhost:8000/docs
```

4. Frontend:
- Login: `http://localhost:8000/login`
- Painel: `http://localhost:8000/painel`

O painel tem o terminal restrito aos comandos documentados em `ajuda`; ele não executa comandos de
shell. A ação de validação facial é deliberadamente uma simulação auditada e não deve ser usada como
decisão biométrica ou mecanismo de autenticação. O botão “Exportar PDF” usa a função de impressão
do navegador. O CSS utilitário Tailwind é compilado localmente, sem CDN:

```bash
npm install
npm run build:css
```

## Usuário administrativo padrão

O projeto cria automaticamente um usuário admin ao iniciar, com base no `.env`:

- e-mail: `ADMIN_EMAIL`
- senha: `ADMIN_PASSWORD`

Exemplo padrão:

- e-mail: `admin@local.test`
- senha: `admin123456`

## Fluxo básico de teste

### 1) Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@local.test","password":"admin123456"}'
```

Resposta esperada:

```json
{"access_token":"...","token_type":"bearer"}
```

### 2) Criar pessoa

```bash
curl -X POST http://localhost:8000/pessoas \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "nome":"Maria Silva",
    "cpf":"12345678909",
    "sexo":"FEMININO",
    "data_nascimento":"1990-01-01"
  }'
```

### 3) Buscar pessoa por nome

```bash
curl "http://localhost:8000/pessoas/search?nome=maria" \
  -H "Authorization: Bearer <TOKEN>"
```

### 4) Ver estatísticas

```bash
curl http://localhost:8000/resumo \
  -H "Authorization: Bearer <TOKEN>"
```

### Endpoints adicionais do painel

- `GET /pessoas/paginado?q=<nome-ou-cpf>&status_filtro=<status>&page=1&page_size=10`
- `DELETE /pessoas/{id}`
- `GET /pessoas/{id}/foto` e `POST /pessoas/{id}/documentos`
- `POST /pessoas/{id}/validacao-facial` com `{"correspondencia_simulada": true|false}`
- `GET /relatorios/pessoas.csv?q=<nome>&status_filtro=<status>`
- `GET /auth/config` para obter o limite de inatividade configurado no servidor

Os CSV/PDF contêm somente CPF mascarado. A foto de perfil usa o último documento JPG/PNG enviado.

## Testes automatizados

Para rodar a suíte do backend:

```bash
pytest -q tests
```

Os testes E2E usam Playwright e mocks de API. Instale `requirements-e2e.txt` e os navegadores do
Playwright para executá-los:

```bash
pip install -r requirements-e2e.txt
playwright install chromium
pytest -q tests_e2e
```

Se quiser rodar apenas os testes de um módulo:

```bash
pytest -q tests/test_auth.py
pytest -q tests/test_pessoas.py
pytest -q tests/test_status.py
pytest -q tests/test_web.py
```

## Observações

- O banco é SQLite local (`censo.db`), conforme escopo do MVP.
- O projeto prioriza simplicidade, clareza e manutenção fácil.
- Regras avançadas e itens do fase 2 continuam fora do escopo do MVP atual.
