import os
import json
import pandas as pd
from pypdf import PdfReader
from openai import OpenAI

# Inicializa o cliente da OpenAI
client = OpenAI()

# --- AJUSTE: Agora o arquivo de saída é .json ---
CAMINHO_SAIDA = "dados_advogados_extraidos.json"
CAMINHOS_PDF = [
    "/home/gabriel/Desktop/Hackathon/hackathon-ufmg-2026-exit/data/data/processos_exemplo/0654321-09.2024.8.04.0001/autos/01_Autos_Processo_0654321-09-2024-8-04-0001.pdf",
    "/home/gabriel/Desktop/Hackathon/hackathon-ufmg-2026-exit/data/data/processos_exemplo/0801234-56.2024.8.10.0001/autos/01_Autos_Processo_0801234-56-2024-8-10-0001.pdf"
]

def extrair_texto_pdf(caminho_pdf: str, max_paginas: int = 10) -> str:
    try:
        reader = PdfReader(caminho_pdf)
        texto = ""
        paginas_para_ler = min(len(reader.pages), max_paginas)
        for i in range(paginas_para_ler):
            texto += reader.pages[i].extract_text() + "\n"
        return texto
    except Exception as e:
        print(f"Erro ao ler o PDF {caminho_pdf}: {e}")
        return ""

def processar_texto_com_openai(texto: str) -> dict:
    prompt_sistema = (
        "Você é um assistente paralegal especialista em extração de dados.\n"
        "Extraia do texto:\n"
        "1. 'nome_advogado': Nome completo do advogado da parte autora.\n"
        "2. 'oab': Número da OAB.\n"
        "3. 'email_advogado': E-mail de contato DO ADVOGADO (prioridade total).\n\n"
        "Retorne APENAS JSON. Se não encontrar, use 'Não encontrado'."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": texto[:20000]}
            ],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Erro na API: {e}")
        return {"nome_advogado": "Erro", "oab": "Erro", "email_advogado": "Erro"}

def main():
    # --- LÓGICA DE SOBRESCREVER ---
    if os.path.exists(CAMINHO_SAIDA):
        os.remove(CAMINHO_SAIDA)
        print(f"Arquivo antigo {CAMINHO_SAIDA} removido.")

    resultados = []

    for caminho in CAMINHOS_PDF:
        print(f"Processando: {os.path.basename(caminho)}...")
        
        if not os.path.exists(caminho):
            print(f"Arquivo não encontrado: {caminho}")
            continue
            
        texto_pdf = extrair_texto_pdf(caminho)
        
        if texto_pdf:
            dados = processar_texto_com_openai(texto_pdf)
            dados["arquivo_origem"] = os.path.basename(caminho)
            resultados.append(dados)
            print(f"  -> Dados extraídos: {dados}")
            
    if resultados:
        df = pd.DataFrame(resultados)
        
        # --- AJUSTE: Exportação para JSON ---
        # orient='records' cria uma lista de objetos [{...}, {...}]
        # indent=4 deixa o arquivo legível para humanos
        # force_ascii=False garante que acentos e caracteres especiais fiquem corretos
        df.to_json(CAMINHO_SAIDA, orient='records', indent=4, force_ascii=False)
        
        print(f"\nSucesso! Novo arquivo JSON gerado em: {os.path.abspath(CAMINHO_SAIDA)}")
    else:
        print("Nenhum dado extraído.")

if __name__ == "__main__":
    main()