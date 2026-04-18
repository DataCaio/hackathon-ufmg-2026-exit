# Setup do Zero

Este projeto tem duas partes:

- backend Python em `src/policy/` e `src/utils/`
- frontend React + Vite em `src/interface/interface-front/`

O fluxo correto é:

1. preparar ambiente do sistema
2. instalar backend Python
3. instalar frontend
4. configurar `.env`
5. garantir os dados em `data/`
6. gerar `data/data.csv`
7. rodar `python src/policy/app.py`
8. subir a interface

## 1. Pré-requisitos do Sistema

Você precisa ter instalado:

- `git`
- `python3`
- `python3-venv`
- `python3-pip`
- `node`
- `npm`
- `pdftotext`
- `google-chrome` ou `chromium`
- `libreoffice`

Versões recomendadas:

- Python `3.13.x`
- Node `20+`
- npm `10+`

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y git curl wget python3 python3-venv python3-pip poppler-utils libreoffice
```

Para instalar o Google Chrome:

```bash
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
rm -f google-chrome-stable_current_amd64.deb
```

Se preferir Chromium, tudo bem, desde que o binário esteja no `PATH`.

## 2. Clonar o Projeto

```bash
git clone <url-do-repositorio>
cd hackathon-ufmg-2026-exit
```

## 3. Configurar o Backend Python

Na raiz do projeto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Dependências Python usadas

O `requirements.txt` contém as bibliotecas Python usadas pelo backend:

- `joblib`
- `numpy`
- `pandas`
- `pypdf`
- `python-dateutil`
- `scikit-learn`
- `scipy`
- `six`
- `threadpoolctl`
- `xgboost`

Observação:

- a integração com OpenAI usa `urllib` da biblioteca padrão, então não precisa instalar `openai`

## 4. Configurar o Frontend

```bash
cd src/interface/interface-front
npm ci
cd ../../..
```

Observações:

- a interface que roda de verdade está em `src/interface/interface-front`
- o `src/interface/package.json` não é o app principal

## 5. Configurar Variáveis de Ambiente

Crie um arquivo `.env` na raiz:

```env
OPENAI_API_KEY=sua_chave_aqui
OPENAI_MODEL=gpt-5.4
```

Depois carregue:

```bash
set -a
source .env
set +a
```

## 6. Preparar os Dados

Garanta estes arquivos e diretórios:

- `data/sentencas.csv`
- `data/processos_exemplo/<numero_processo>/autos/`
- `data/processos_exemplo/<numero_processo>/subsidios/`

O sistema assume que:

- cada pasta em `data/processos_exemplo/` tem o nome do número do processo
- o `data/data.csv` corresponde exatamente a esses processos

## 7. Gerar o `data/data.csv`

Com a venv ativada e `.env` carregado:

```bash
python src/utils/gerador_data_csv.py
```

Isso gera ou sobrescreve:

```text
data/data.csv
```

## 8. Rodar o Backend Completo

Com a venv ativada e `.env` carregado:

```bash
python src/policy/app.py
```

Esse comando:

- extrai contatos dos autos
- carrega ou treina os modelos
- decide entre acordo e defesa
- gera `Acordo.json` ou `Defesa.pdf`
- sincroniza a base consumida pela interface

Comandos úteis:

```bash
python src/policy/app.py --pretty
python src/policy/app.py --force-retrain
python src/policy/app.py --processo-id 0654321-09.2024.8.04.0001
python src/utils/gerador_data_csv.py
```

## 9. O Que o Backend Gera

Por processo:

- `data/processos_exemplo/<processo>/Contato.json`
- `data/processos_exemplo/<processo>/Acordo.json`, quando o caso cai em acordo
- `data/processos_exemplo/<processo>/Defesa.pdf`, quando o caso cai em defesa

Artefatos gerais:

- `data/policy_artifacts/politica_decisao.joblib`
- `data/policy_artifacts/politica_acordo.joblib`
- `data/policy_artifacts/politica_decisao_metricas.json`
- `data/policy_artifacts/politica_acordo_metricas.json`

Sincronização para a interface:

- `src/interface/interface-front/public/generated/base_processos.json`
- `src/interface/interface-front/public/generated/modelo_decisao_metricas.json`
- `src/interface/interface-front/public/generated/processos/<processo>/...`

O backend também copia para a interface:

- `autos/*.pdf`
- `subsidios/*`
- `Contato.json`
- `Acordo.json`, quando houver
- `Defesa.pdf`, quando houver

## 10. Rodar a Interface

Em outro terminal:

```bash
cd src/interface/interface-front
npm run dev
```

Normalmente ela sobe em:

```text
http://localhost:5173
```

## 11. Credenciais Demo da Interface

- Escritório: `advogado.demo` / `EnterOS2026`
- Organização: `staff.enter` / `HackathonUFMG`

## 12. Build da Interface

```bash
cd src/interface/interface-front
npm run build
```

Saída:

```text
src/interface/interface-front/dist/
```

## 13. Roteiro Curto em Máquina Nova

```bash
git clone <url-do-repositorio>
cd hackathon-ufmg-2026-exit

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cd src/interface/interface-front
npm ci
cd ../../..

# criar e preencher .env
set -a
source .env
set +a

python src/utils/gerador_data_csv.py
python src/policy/app.py

cd src/interface/interface-front
npm run dev
```

## Estrutura do Projeto

```text
├── src/
│   ├── policy/
│   ├── utils/
│   └── interface/interface-front/
├── data/
├── requirements.txt
├── .env.example
├── SETUP.md
└── README.md
```
