import pandas as pd

resultados_dos_processos = 'data/Hackaton_Enter_Base_Candidatos_Resultados_dos_processos.csv'
df_resultados_dos_processos = pd.read_csv(resultados_dos_processos)
subsidios_disponibilizados = 'data/Hackaton_Enter_Base_Candidatos_Subsídios_disponibilizados.csv'
df_subsidios_disponibilizados = pd.read_csv(subsidios_disponibilizados, header = 1)

#Unificação do Banco de Dados
df_unificado = df_resultados_dos_processos.merge(
    df_subsidios_disponibilizados,
    on='Número do processo',
    how='left'  # ou 'inner', dependendo do caso
)

df_unificado["Resultado macro"]  = df_unificado["Resultado macro"].map({"Não Êxito": 0, "Êxito": 1})
df_unificado = df_unificado[df_unificado['Resultado micro'] != 'Extinção']

df_unificado.to_csv('data/Hackaton_Enter_Banco_unificado.csv', index=False)

