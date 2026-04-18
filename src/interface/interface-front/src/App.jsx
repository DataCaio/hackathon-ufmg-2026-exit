import { useState, useRef, useEffect } from 'react';
import { CursorReactiveBackground } from './CursorReactiveBackground';
import { validarDemoLogin } from './demoAuth';
import './App.css';

const PERFIS_LOGIN = [
  { value: '', label: 'Selecione o perfil…' },
  { value: 'advogado', label: 'Escritório — análise de processo' },
  { value: 'organizacao', label: 'Banco UFMG — indicadores e aderência' }
];

// MOCK ATUALIZADO: Incluindo os contatos da oposição para casos de ACORDO.
const processosMock = {
  'PROC-1001': {
    id: 'PROC-1001',
    autor: 'Maria da Silva',
    valorCausa: 'R$ 12.400,00',
    chanceAcordo: 82,
    riscoCondenacao: 71,
    valorSugeridoAcordo: 'R$ 3.500,00',
    recomendacao: 'ACORDO',
    justificativa:
      'Contrato sem assinatura biométrica e comprovante de crédito com inconsistência de timestamp.',
    subsidios: {
      contrato: 0,
      extrato: 0,
      comprovanteCredito: 0,
      dossie: 1,
      demonstrativoDivida: 1,
      laudoReferenciado: 1
    },
    contatoOposicao: {
      nome: 'Dr. Carlos Mendes',
      oab: 'OAB/MG 112.345',
      telefone: '(31) 98888-7777',
      email: 'carlos.mendes@adv.com.br'
    }
  },
  'PROC-1002': {
    id: 'PROC-1002',
    autor: 'João Ferreira',
    valorCausa: 'R$ 7.200,00',
    chanceAcordo: 35,
    riscoCondenacao: 29,
    valorSugeridoAcordo: 'Não recomendado',
    recomendacao: 'DEFESA',
    justificativa:
      'Documentação robusta: contrato validado, comprovante BACEN presente e extrato compatível.',
    subsidios: {
      contrato: 1,
      extrato: 1,
      comprovanteCredito: 0,
      dossie: 1,
      demonstrativoDivida: 1,
      laudoReferenciado: 1
    },
    contatoOposicao: null // Não exibe contato para defesa
  },
  'PROC-1003': {
    id: 'PROC-1003',
    autor: 'Ana Beatriz Souza',
    valorCausa: 'R$ 20.000,00',
    chanceAcordo: 76,
    riscoCondenacao: 68,
    valorSugeridoAcordo: 'R$ 6.200,00',
    recomendacao: 'ACORDO',
    justificativa:
      'Dossiê aponta divergência de assinatura e histórico de decisões semelhantes favoráveis ao autor.',
    subsidios: {
      contrato: 0,
      extrato: 1,
      comprovanteCredito: 1,
      dossie: 1,
      demonstrativoDivida: 1,
      laudoReferenciado: 0
    },
    contatoOposicao: {
      nome: 'Dra. Fernanda Lima',
      oab: 'OAB/MG 98.765',
      telefone: '(31) 97777-8888',
      email: 'fernanda.lima@adv.com.br'
    }
  }
};

// Dicionário para traduzir a chave do JSON para o nome legível na interface
const nomesSubsidios = {
  contrato: 'Contrato',
  extrato: 'Extrato',
  comprovanteCredito: 'Comprovante de Crédito',
  dossie: 'Dossiê',
  demonstrativoDivida: 'Evolução da Dívida',
  laudoReferenciado: 'Laudo Referenciado'
};

function App() {
  const [perfilSelecionado, setPerfilSelecionado] = useState('');
  const [usuario, setUsuario] = useState('');
  const [senha, setSenha] = useState('');
  const [logado, setLogado] = useState(false);

  const [processoIdBusca, setProcessoIdBusca] = useState('');
  const [processoAtual, setProcessoAtual] = useState(null);
  const [statusBusca, setStatusBusca] = useState('Informe o ID do processo para carregar a recomendação EnterOS.');
  const [decisaoAdvogado, setDecisaoAdvogado] = useState('');
  const [menuPerfilAberto, setMenuPerfilAberto] = useState(false);
  const [erroLogin, setErroLogin] = useState('');
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const perfilMenuRef = useRef(null);

  useEffect(() => {
    if (!menuPerfilAberto) return;
    const fechar = (e) => {
      if (perfilMenuRef.current && !perfilMenuRef.current.contains(e.target)) {
        setMenuPerfilAberto(false);
      }
    };
    document.addEventListener('mousedown', fechar);
    return () => document.removeEventListener('mousedown', fechar);
  }, [menuPerfilAberto]);

  const labelPerfilAtual =
    PERFIS_LOGIN.find((p) => p.value === perfilSelecionado)?.label ?? PERFIS_LOGIN[0].label;

  const fazerLogin = (evento) => {
    evento.preventDefault();
    const resultado = validarDemoLogin(perfilSelecionado, usuario, senha);
    if (!resultado.ok) {
      setErroLogin(resultado.mensagem);
      return;
    }
    setErroLogin('');
    setLogado(true);
  };

  const consultarProcesso = (evento) => {
    evento.preventDefault();
    const idNormalizado = processoIdBusca.trim().toUpperCase();
    if (!idNormalizado) {
      setStatusBusca('Informe um ID válido. Exemplo: PROC-1001');
      setProcessoAtual(null);
      return;
    }

    setStatusBusca('Buscando nos registros...');
    setTimeout(() => {
      const encontrado = processosMock[idNormalizado];
      if (!encontrado) {
        setStatusBusca('Processo não encontrado. Tente PROC-1001, PROC-1002 ou PROC-1003.');
        setProcessoAtual(null);
        setDecisaoAdvogado('');
        return;
      }
      setProcessoAtual(encontrado);
      setDecisaoAdvogado('');
      setStatusBusca(`Processo ${encontrado.id} carregado com sucesso.`);
    }, 600);
  };

  const registrarDecisao = (decisao) => {
    if (!processoAtual) return;
    setDecisaoAdvogado(decisao);
  };

  const sair = () => {
    setLogado(false);
    setUsuario('');
    setSenha('');
    setPerfilSelecionado('');
    setMenuPerfilAberto(false);
    setErroLogin('');
    setMostrarSenha(false);
    setProcessoIdBusca('');
    setProcessoAtual(null);
    setDecisaoAdvogado('');
    setStatusBusca('Informe o ID do processo para carregar a recomendação EnterOS.');
  };

  return (
    <>
      <CursorReactiveBackground />
      <div className="app-shell" style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>

      <header
        className="app-shell-header"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}
      >
        <div className="brand-header-cluster">
          <img
            src="/logo-exit.png"
            alt="EXIT — equipe"
            className="brand-logo-exit"
            width={260}
            height={82}
          />

          <div className="brand-header-divider">
            <h1 style={{ margin: 0, fontSize: '22px', background: 'linear-gradient(90deg, var(--color-primary), var(--color-accent))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
              Exit.OS
            </h1>
            <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '13px' }}>
              Exit · Enterprise AI — Hackathon UFMG 2026
            </p>
          </div>
        </div>

        {logado && (
          <button type="button" onClick={sair} className="btn-enter-outline" style={{ padding: '10px 18px', borderRadius: '8px', cursor: 'pointer', fontWeight: 700 }}>
            Sair
          </button>
        )}
      </header>

      {/* TELA DE LOGIN */}
      {!logado && (
        <div style={{ maxWidth: '400px', margin: '0 auto', marginTop: '10vh', animation: 'fadeIn 0.5s ease' }}>
          <h2 style={{ marginBottom: '8px', textAlign: 'center', color: '#fff' }}>Entrar no ExitOS</h2>
          <p style={{ margin: '0 0 20px', textAlign: 'center', color: 'var(--text-soft)', fontSize: '14px' }}>
            Plataforma Exit para política de acordos e monitoramento
          </p>

          <section>
            <form onSubmit={fazerLogin}>
              <label id="label-perfil-login" style={{ display: 'block', marginBottom: '8px', color: 'var(--text-soft)' }}>
                Perfil de acesso
              </label>
              <div ref={perfilMenuRef} className="select-enter-custom" style={{ marginBottom: '20px' }}>
                <button
                  type="button"
                  className="select-enter-trigger"
                  aria-haspopup="listbox"
                  aria-expanded={menuPerfilAberto}
                  aria-labelledby="label-perfil-login"
                  onClick={() => {
                    setMenuPerfilAberto((a) => !a);
                    setErroLogin('');
                  }}
                >
                  <span className="select-enter-trigger-text">{labelPerfilAtual}</span>
                  <span className="select-enter-chevron" aria-hidden>
                    {menuPerfilAberto ? '▲' : '▼'}
                  </span>
                </button>
                {menuPerfilAberto && (
                  <ul className="select-enter-list" role="listbox">
                    {PERFIS_LOGIN.map((op) => (
                      <li key={op.value || 'empty'} role="presentation">
                        <button
                          type="button"
                          role="option"
                          aria-selected={perfilSelecionado === op.value}
                          className={
                            perfilSelecionado === op.value
                              ? 'select-enter-option select-enter-option-active'
                              : 'select-enter-option'
                          }
                          onClick={() => {
                            setPerfilSelecionado(op.value);
                            setMenuPerfilAberto(false);
                            setErroLogin('');
                          }}
                        >
                          {op.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text-soft)' }}>Usuário corporativo</label>
              <input
                type="text"
                value={usuario}
                onChange={(e) => {
                  setUsuario(e.target.value);
                  setErroLogin('');
                }}
                placeholder="usuário ExitOS"
                autoComplete="username"
                style={{ marginBottom: '20px' }}
              />

              <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text-soft)' }}>Senha</label>
              <input
                type={mostrarSenha ? 'text' : 'password'}
                value={senha}
                onChange={(e) => {
                  setSenha(e.target.value);
                  setErroLogin('');
                }}
                placeholder="••••••••"
                autoComplete="current-password"
                style={{ marginBottom: '10px' }}
              />
              <label className="login-mostrar-senha">
                <input
                  type="checkbox"
                  checked={mostrarSenha}
                  onChange={(e) => setMostrarSenha(e.target.checked)}
                />
                Mostrar senha
              </label>

              {erroLogin && (
                <p className="login-erro" role="alert">
                  {erroLogin}
                </p>
              )}

              <button type="submit" className="btn-enter-primary" style={{ width: '100%', padding: '14px', borderRadius: '10px', cursor: 'pointer', fontSize: '16px', marginTop: '8px' }}>
                Entrar
              </button>
            </form>
          </section>
        </div>
      )}

      {/* TELA DO ADVOGADO */}
      {logado && perfilSelecionado === 'advogado' && (
        <div style={{ animation: 'fadeIn 0.5s ease' }}>
          <h2 style={{ marginBottom: '8px', color: '#fff' }}>Portal do escritório</h2>
          <p style={{ margin: '0 0 24px', color: 'var(--text-soft)', fontSize: '15px' }}>
            Consulte o processo e siga a recomendação da política de acordos Exit
          </p>

          <section style={{ marginBottom: '24px' }}>
            <h3 style={{ color: 'var(--color-primary)' }}>1. Consultar Processo</h3>
            <p style={{ color: 'var(--text-soft)' }}>Busque pelo ID na base ExitOS para exibir acordo ou defesa sugeridos pela IA.</p>
            <form onSubmit={consultarProcesso} style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <input
                type="text"
                value={processoIdBusca}
                onChange={(e) => setProcessoIdBusca(e.target.value)}
                placeholder="Ex: PROC-1001"
              />
              <button type="submit" className="btn-enter-primary" style={{ padding: '12px 24px', borderRadius: '10px', cursor: 'pointer', fontWeight: 700, flexShrink: 0 }}>
                Consultar
              </button>
            </form>
            <p style={{ marginTop: '12px', marginBottom: 0, color: 'var(--text-soft)', fontSize: '14px' }}>{statusBusca}</p>
          </section>

          <section style={{ marginBottom: '24px', border: processoAtual ? '1px solid var(--color-primary)' : '1px solid var(--border-subtle)', boxShadow: processoAtual ? 'var(--shadow-yellow)' : 'none' }}>
            <h3 style={{ color: processoAtual ? 'var(--color-primary)' : '#fff' }}>2. Recomendação Exit (IA)</h3>
            {!processoAtual && <p style={{ margin: 0, color: 'var(--text-soft)' }}>Aguardando consulta...</p>}
            {processoAtual && (
              <div className="process-detail-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
                <div className="process-detail-col-left" style={{ borderRight: '1px solid var(--border-subtle)', paddingRight: '15px' }}>
                  <p style={{ margin: '0 0 8px' }}><strong style={{ color: 'var(--text-soft)' }}>ID:</strong> {processoAtual.id}</p>
                  <p style={{ margin: '0 0 8px' }}><strong style={{ color: 'var(--text-soft)' }}>Autor:</strong> {processoAtual.autor}</p>
                  <p style={{ margin: '0 0 8px' }}><strong style={{ color: 'var(--text-soft)' }}>Valor da causa:</strong> {processoAtual.valorCausa}</p>
                </div>
                <div>
                  <p style={{ margin: '0 0 8px', color: processoAtual.recomendacao === 'ACORDO' ? 'var(--color-primary)' : '#fff' }}>
                    <strong style={{ color: 'var(--text-soft)' }}>Recomendação:</strong> {processoAtual.recomendacao}
                  </p>
                  <p style={{ margin: '0 0 8px' }}><strong style={{ color: 'var(--text-soft)' }}>Chance de Acordo:</strong> {processoAtual.chanceAcordo}%</p>
                  <p style={{ margin: '0 0 8px' }}><strong style={{ color: 'var(--text-soft)' }}>Valor Sugerido:</strong> {processoAtual.valorSugeridoAcordo}</p>
                </div>

                {/* SUBSÍDIOS DISPONÍVEIS */}
                <div style={{ gridColumn: '1 / -1', marginTop: '10px', paddingTop: '15px', borderTop: '1px solid var(--border-subtle)' }}>
                  <p style={{ margin: '0 0 10px' }}><strong style={{ color: 'var(--text-soft)', fontSize: '0.9rem' }}>Subsídios validados pela IA na base de dados:</strong></p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    
                    {Object.entries(processoAtual.subsidios || {})
                      .filter(([chave, valorBinario]) => valorBinario === 1)
                      .map(([chave]) => (
                        <span key={chave} style={{ padding: '4px 10px', borderRadius: '6px', background: 'rgba(250, 204, 21, 0.1)', border: '1px solid rgba(250, 204, 21, 0.2)', color: 'var(--color-primary)', fontSize: '0.85rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                          {nomesSubsidios[chave] || chave}
                        </span>
                      ))}
                      
                    {Object.values(processoAtual.subsidios || {}).every(valor => valor === 0) && (
                      <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.85rem' }}>Nenhum subsídio fornecido.</span>
                    )}
                  </div>
                </div>

                {/* --- NOVA SEÇÃO: CONTATO DA OPOSIÇÃO (APENAS PARA ACORDO) --- */}
                {processoAtual.recomendacao === 'ACORDO' && processoAtual.contatoOposicao && (
                  <div style={{ gridColumn: '1 / -1', marginTop: '5px', paddingTop: '15px', borderTop: '1px solid var(--border-subtle)' }}>
                    <p style={{ margin: '0 0 10px' }}><strong style={{ color: 'var(--text-soft)', fontSize: '0.9rem' }}>Contato para Negociação (Parte Contrária):</strong></p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px', background: 'rgba(250, 204, 21, 0.05)', padding: '14px', borderRadius: '8px', border: '1px solid rgba(250, 204, 21, 0.15)' }}>
                      <div>
                        <span style={{color: 'var(--text-soft)', fontSize: '0.8rem'}}>Advogado(a):</span><br/>
                        <strong style={{color: '#fff'}}>{processoAtual.contatoOposicao.nome} <br/><span style={{color: 'var(--color-accent)', fontSize: '0.85rem'}}>{processoAtual.contatoOposicao.oab}</span></strong>
                      </div>
                      <div>
                        <span style={{color: 'var(--text-soft)', fontSize: '0.8rem'}}>Telefone:</span><br/>
                        <strong style={{color: '#fff'}}>{processoAtual.contatoOposicao.telefone}</strong>
                      </div>
                      <div>
                        <span style={{color: 'var(--text-soft)', fontSize: '0.8rem'}}>E-mail:</span><br/>
                        <strong style={{color: '#fff'}}>{processoAtual.contatoOposicao.email}</strong>
                      </div>
                    </div>
                  </div>
                )}
                {/* --- FIM DA NOVA SEÇÃO --- */}

                <div
                  style={{
                    gridColumn: '1 / -1',
                    marginTop: '10px',
                    padding: '15px',
                    borderRadius: '10px',
                    border: '1px solid rgba(250, 204, 21, 0.2)',
                    background: 'linear-gradient(135deg, rgba(0,0,0,0.85) 0%, rgba(60, 30, 8, 0.35) 100%)'
                  }}
                >
                  <p style={{ margin: 0 }}>
                    <strong style={{ color: 'var(--color-accent)' }}>Justificativa da política:</strong> {processoAtual.justificativa}
                  </p>
                </div>
              </div>
            )}
          </section>

          <section>
            <h3 style={{ color: '#fff' }}>3. Decisão Final</h3>
            <p style={{ color: 'var(--text-soft)' }}>Registre se o escritório adere à recomendação ExitOS neste caso.</p>
            <div style={{ display: 'flex', gap: '15px', marginBottom: '15px' }}>
              <button
                type="button"
                onClick={() => registrarDecisao('ACORDO')}
                disabled={!processoAtual}
                className="btn-enter-primary"
                style={{ flex: 1, padding: '14px', borderRadius: '10px', cursor: processoAtual ? 'pointer' : 'not-allowed', opacity: processoAtual ? 1 : 0.4 }}
              >
                Acordo 
              </button>
              <button
                type="button"
                onClick={() => registrarDecisao('DEFESA')}
                disabled={!processoAtual}
                className="btn-enter-outline"
                style={{ flex: 1, padding: '14px', borderRadius: '10px', cursor: processoAtual ? 'pointer' : 'not-allowed', opacity: processoAtual ? 1 : 0.4 }}
              >
                Defesa judicial
              </button>
            </div>

            {decisaoAdvogado && (
              <div
                style={{
                  padding: '15px',
                  background: 'linear-gradient(90deg, rgba(250, 204, 21, 0.12), rgba(251, 146, 60, 0.06))',
                  borderLeft: '4px solid var(--color-primary)',
                  borderRadius: '0 10px 10px 0'
                }}
              >
                <p style={{ margin: 0 }}>
                  Decisão registrada no ExitOS: <strong style={{ color: 'var(--color-primary)' }}>{decisaoAdvogado}</strong> — processo {processoAtual.id}.
                </p>
              </div>
            )}
          </section>
        </div>
      )}

      {/* DASHBOARD DA ORGANIZAÇÃO */}
      {logado && perfilSelecionado === 'organizacao' && (
        <div style={{ animation: 'fadeIn 0.5s ease' }}>
          <h2 style={{ marginBottom: '8px', color: '#fff' }}>Painel ExitOS — Banco UFMG</h2>
          <p style={{ margin: '0 0 24px', color: 'var(--text-soft)', fontSize: '15px' }}>
            Aderência dos escritórios à IA e impacto da política de acordos
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
            
            {/* KPI 1 - Aderência */}
            <section style={{ borderTop: '4px solid var(--color-primary)' }}>
              <h3 style={{ color: 'var(--color-primary)' }}>Aderência à recomendação Exit</h3>
              <p style={{ color: 'var(--text-soft)', fontSize: '0.9rem' }}>Alinhamento dos advogados à política sugerida pela IA</p>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
                <h1 style={{ fontSize: '48px', margin: '10px 0', color: '#fff' }}>84%</h1>
                <span style={{ color: 'var(--color-primary)', fontWeight: 'bold' }}>+5% este mês</span>
              </div>
              <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '0.85rem' }}>4.284 de 5.100 casos seguiram o direcionamento.</p>
            </section>

            {/* KPI 2 - Efetividade */}
            <section style={{ borderTop: '4px solid var(--color-accent)' }}>
              <h3 style={{ color: 'var(--color-accent)' }}>Efetividade financeira</h3>
              <p style={{ color: 'var(--text-soft)', fontSize: '0.9rem' }}>Economia estimada com acordos e redução de risco</p>
              <h1 style={{ fontSize: '48px', margin: '10px 0', color: '#fff' }}>R$ 450k</h1>
              <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '0.85rem' }}>Economia em condenações e custas evitadas.</p>
            </section>

            {/* KPI 3 - Distribuição */}
            <section>
              <h3 style={{ color: '#fff' }}>Distribuição das recomendações IA</h3>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '30px', marginBottom: '10px' }}>
                <span style={{ color: 'var(--color-primary)', fontWeight: 'bold' }}>Acordo (58%)</span>
                <span style={{ color: 'var(--color-accent)', fontWeight: 'bold' }}>Defesa (42%)</span>
              </div>

              <div className="enter-gradient-bar" style={{ marginTop: '8px' }} aria-hidden>
                <span style={{ width: '58%' }} />
                <span style={{ width: '42%' }} />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '12px' }}>
                <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '0.9rem' }}>2.970 processos</p>
                <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '0.9rem' }}>2.130 processos</p>
              </div>
            </section>

            {/* KPI 4 - Funil */}
            <section>
              <h3 style={{ color: '#fff' }}>Funil de aderência ExitOS</h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', marginTop: '20px' }}>
                <div style={{ backgroundColor: '#000', padding: '15px', borderRadius: '8px', borderLeft: '4px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-soft)' }}>1. Total Analisado</span>
                  <strong style={{ color: '#fff', fontSize: '1.2rem' }}>5.100</strong>
                </div>
                
                <div style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0.9), rgba(120, 53, 15, 0.2))', padding: '15px', borderRadius: '8px', borderLeft: '4px solid var(--color-accent)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-soft)' }}>2. Recomendação IA emitida</span>
                  <strong style={{ color: 'var(--color-accent)', fontSize: '1.2rem' }}>5.100</strong>
                </div>

                <div style={{ backgroundColor: 'rgba(250, 204, 21, 0.05)', padding: '15px', borderRadius: '8px', borderLeft: '4px solid var(--color-primary)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-soft)' }}>3. Aderência Real</span>
                  <strong style={{ color: 'var(--color-primary)', fontSize: '1.2rem' }}>4.284</strong>
                </div>
              </div>
            </section>
            
          </div>
        </div>
      )}
      </div>
    </>
  );
}

export default App;