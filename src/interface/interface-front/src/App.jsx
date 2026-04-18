import { useState, useRef, useEffect } from 'react';
import { CursorReactiveBackground } from './CursorReactiveBackground';
import { validarDemoLogin } from './demoAuth';
import './App.css';

const PERFIS_LOGIN = [
  { value: '', label: 'Selecione o perfil…' },
  { value: 'advogado', label: 'Escritório — análise de processo' },
  { value: 'organizacao', label: 'Banco UFMG — indicadores e aderência' }
];

const nomesSubsidios = {
  contrato: 'Contrato',
  extrato: 'Extrato',
  comprovanteCredito: 'Comprovante de Crédito',
  dossie: 'Dossiê',
  demonstrativoDivida: 'Evolução da Dívida',
  laudoReferenciado: 'Laudo Referenciado'
};

// MÁGICA DE CONVERSÃO DE MOEDA (Ex: "R$ 12.400,00" -> 12400.00)
const extrairValorNumerico = (str) => {
  if (!str) return 0;
  const numStr = String(str).replace(/[^\d,.-]/g, '').replace(/\./g, '').replace(',', '.');
  return parseFloat(numStr) || 0;
};

// FORMATAÇÃO PARA REAIS NA TELA
const formatarMoeda = (valor) => {
  return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

function App() {
  const [perfilSelecionado, setPerfilSelecionado] = useState('');
  const [usuario, setUsuario] = useState('');
  const [senha, setSenha] = useState('');
  const [logado, setLogado] = useState(false);

  // BASE DE DADOS
  const [baseProcessos, setBaseProcessos] = useState(null);
  const [statusCarregamentoBD, setStatusCarregamentoBD] = useState('Aguardando sincronização com IA...');

  // MEMÓRIA EM TEMPO REAL PARA O DASHBOARD (Aderência)
  const [historicoDecisoes, setHistoricoDecisoes] = useState([]);

  const [processoIdBusca, setProcessoIdBusca] = useState('');
  const [processoAtual, setProcessoAtual] = useState(null);
  const [statusBusca, setStatusBusca] = useState('Informe o ID do processo para consultar a base.');
  const [decisaoAdvogado, setDecisaoAdvogado] = useState('');
  const [subsidiosLidos, setSubsidiosLidos] = useState(new Set());
  
  const [menuPerfilAberto, setMenuPerfilAberto] = useState(false);
  const [erroLogin, setErroLogin] = useState('');
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const perfilMenuRef = useRef(null);

  useEffect(() => {
    fetch('/base_processos.json')
      .then(response => {
        if (!response.ok) throw new Error("Base não encontrada");
        return response.json();
      })
      .then(data => {
        setBaseProcessos(data);
        const tamanhoBase = Array.isArray(data) ? data.length : Object.keys(data).length;
        setStatusCarregamentoBD(`Base IA conectada: ${tamanhoBase} processos disponíveis.`);
      })
      .catch(err => {
        console.error("Erro ao ler JSON:", err);
        setStatusCarregamentoBD("Aviso: Arquivo base_processos.json não encontrado na pasta public.");
      });
  }, []);

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

  const labelPerfilAtual = PERFIS_LOGIN.find((p) => p.value === perfilSelecionado)?.label ?? PERFIS_LOGIN[0].label;

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
      setStatusBusca('Informe um ID válido.');
      setProcessoAtual(null);
      return;
    }

    if (!baseProcessos) {
      setStatusBusca('A base de dados ainda não foi carregada.');
      return;
    }

    setStatusBusca('Consultando registros na base EnterOS...');
    setTimeout(() => {
      let encontradoBruto = null;
      if (Array.isArray(baseProcessos)) {
        encontradoBruto = baseProcessos.find(p => {
            const pid = p.id || p.id_processo || p.numero_processo || p.Processo;
            return pid && String(pid).trim().toUpperCase() === idNormalizado;
        });
      } else {
        encontradoBruto = baseProcessos[idNormalizado];
      }
      
      if (!encontradoBruto) {
        setStatusBusca('Processo não encontrado na base de dados.');
        setProcessoAtual(null);
        setDecisaoAdvogado('');
        return;
      }

      const processoAdaptado = {
        id: encontradoBruto.id || encontradoBruto.id_processo || idNormalizado,
        autor: encontradoBruto.autor || encontradoBruto.Autor || 'Não informado',
        valorCausa: encontradoBruto.valorCausa || encontradoBruto.valor_causa || 'Não informado',
        chanceAcordo: encontradoBruto.chanceAcordo || encontradoBruto.chance_acordo || 0,
        valorSugeridoAcordo: encontradoBruto.valorSugeridoAcordo || encontradoBruto.valor_sugerido || '-',
        recomendacao: encontradoBruto.recomendacao || encontradoBruto.Recomendacao || 'INDEFINIDA',
        justificativa: encontradoBruto.justificativa || encontradoBruto.Justificativa || 'Sem justificativa detalhada.',
        subsidios: encontradoBruto.subsidios || {
            contrato: Number(encontradoBruto.contrato) || 0,
            extrato: Number(encontradoBruto.extrato) || 0,
            comprovanteCredito: Number(encontradoBruto.comprovanteCredito || encontradoBruto.comprovante) || 0,
            dossie: Number(encontradoBruto.dossie) || 0,
            demonstrativoDivida: Number(encontradoBruto.demonstrativoDivida || encontradoBruto.demonstrativo) || 0,
            laudoReferenciado: Number(encontradoBruto.laudoReferenciado || encontradoBruto.laudo) || 0
        },
        // REMOVIDO O CAMPO DE TELEFONE
        contatoOposicao: encontradoBruto.contatoOposicao || (encontradoBruto.nome_advogado ? {
            nome: encontradoBruto.nome_advogado,
            oab: encontradoBruto.oab || 'Não informada',
            email: encontradoBruto.email_advogado || 'Sem e-mail'
        } : null)
      };

      setProcessoAtual(processoAdaptado);
      setDecisaoAdvogado('');
      setSubsidiosLidos(new Set()); 
      setStatusBusca(`Processo ${processoAdaptado.id} carregado.`);
    }, 400);
  };

  const abrirSubsidio = (chave) => {
    setSubsidiosLidos(prev => new Set(prev).add(chave));
    alert(`Simulador ExitOS: Abrindo a documentação do [${nomesSubsidios[chave] || chave}] para leitura.`);
  };

  const registrarDecisao = (decisao) => {
    if (!processoAtual) return;
    setDecisaoAdvogado(decisao);

    // SALVA A DECISÃO NO HISTÓRICO EM TEMPO REAL PARA O DASHBOARD
    setHistoricoDecisoes(prev => {
      // Evita duplicar se o advogado clicar várias vezes no mesmo processo
      const jaExiste = prev.find(h => h.idProcesso === processoAtual.id);
      if (jaExiste) return prev.map(h => h.idProcesso === processoAtual.id ? { ...h, decisaoTomada: decisao } : h);
      return [...prev, { idProcesso: processoAtual.id, recomendacaoIA: processoAtual.recomendacao, decisaoTomada: decisao }];
    });

    const logRegistro = {
      idProcesso: processoAtual.id,
      advogadoLogado: usuario,
      decisaoTomada: decisao,
      recomendacaoIA: processoAtual.recomendacao,
      documentosLidosParaEmbasamento: Array.from(subsidiosLidos).map(k => nomesSubsidios[k] || k),
      timestampAgendamento: new Date().toISOString()
    };

    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(logRegistro, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", `auditoria_ExitOS_${processoAtual.id}.json`);
    document.body.appendChild(downloadAnchorNode); 
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
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
    setSubsidiosLidos(new Set());
    setStatusBusca('Informe o ID do processo para consultar a base.');
  };

  // ==========================================
  // CÁLCULOS DINÂMICOS DO DASHBOARD BANCÁRIO
  // ==========================================
  let dashTotalIA = 0;
  let dashQtdAcordo = 0;
  let dashQtdDefesa = 0;
  let dashEconomiaGerada = 0;

  if (baseProcessos) {
    const listaProcessos = Array.isArray(baseProcessos) ? baseProcessos : Object.values(baseProcessos);
    dashTotalIA = listaProcessos.length;

    listaProcessos.forEach(p => {
      const rec = (p.recomendacao || p.Recomendacao || '').toUpperCase();
      if (rec === 'ACORDO') {
        dashQtdAcordo++;
        // Calcula o lucro (Valor da causa - Valor Sugerido de Acordo)
        const vCausa = extrairValorNumerico(p.valorCausa || p.valor_causa);
        const vSugerido = extrairValorNumerico(p.valorSugeridoAcordo || p.valor_sugerido);
        if (vCausa > vSugerido && vSugerido > 0) {
          dashEconomiaGerada += (vCausa - vSugerido);
        }
      } else if (rec === 'DEFESA') {
        dashQtdDefesa++;
      }
    });
  }

  const pctAcordo = dashTotalIA ? Math.round((dashQtdAcordo / dashTotalIA) * 100) : 0;
  const pctDefesa = dashTotalIA ? Math.round((dashQtdDefesa / dashTotalIA) * 100) : 0;

  // Calcula a Aderência Real baseada nos cliques do advogado
  const totalAnalisadosPelosAdvogados = historicoDecisoes.length;
  let casosAderentes = 0;
  historicoDecisoes.forEach(h => {
    if (h.recomendacaoIA === h.decisaoTomada) casosAderentes++;
  });
  const pctAderenciaReal = totalAnalisadosPelosAdvogados ? Math.round((casosAderentes / totalAnalisadosPelosAdvogados) * 100) : 100;

  return (
    <>
      <CursorReactiveBackground />
      <div className="app-shell" style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>

      <header className="app-shell-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div className="brand-header-cluster">
          <img src="/logo-exit.png" alt="EXIT — equipe" className="brand-logo-exit" width={260} height={82} />
          <div className="brand-header-divider">
            <h1 style={{ margin: 0, fontSize: '22px', background: 'linear-gradient(90deg, var(--color-primary), var(--color-accent))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>Exit.OS</h1>
            <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '13px' }}>Exit · Enterprise AI — Hackathon UFMG 2026</p>
          </div>
        </div>
        {logado && (
          <button type="button" onClick={sair} className="btn-enter-outline" style={{ padding: '10px 18px', borderRadius: '8px', cursor: 'pointer', fontWeight: 700 }}>Sair</button>
        )}
      </header>

      {/* TELA DE LOGIN */}
      {!logado && (
        <div style={{ maxWidth: '400px', margin: '0 auto', marginTop: '10vh', animation: 'fadeIn 0.5s ease' }}>
          <h2 style={{ marginBottom: '8px', textAlign: 'center', color: '#fff' }}>Entrar no ExitOS</h2>
          
          <div style={{ marginBottom: '20px', padding: '10px', background: 'rgba(250, 204, 21, 0.05)', borderRadius: '8px', border: '1px solid rgba(250, 204, 21, 0.15)', textAlign: 'center' }}>
            <p style={{ margin: 0, color: 'var(--color-primary)', fontSize: '12px', fontWeight: 'bold' }}>Status da Conexão IA</p>
            <p style={{ margin: '4px 0 0', color: 'var(--text-soft)', fontSize: '12px' }}>{statusCarregamentoBD}</p>
          </div>

          <section>
            <form onSubmit={fazerLogin}>
              <label id="label-perfil-login" style={{ display: 'block', marginBottom: '8px', color: 'var(--text-soft)' }}>Perfil de acesso</label>
              <div ref={perfilMenuRef} className="select-enter-custom" style={{ marginBottom: '20px' }}>
                <button type="button" className="select-enter-trigger" aria-haspopup="listbox" aria-expanded={menuPerfilAberto} onClick={() => { setMenuPerfilAberto((a) => !a); setErroLogin(''); }}>
                  <span className="select-enter-trigger-text">{labelPerfilAtual}</span>
                  <span className="select-enter-chevron" aria-hidden>{menuPerfilAberto ? '▲' : '▼'}</span>
                </button>
                {menuPerfilAberto && (
                  <ul className="select-enter-list" role="listbox">
                    {PERFIS_LOGIN.map((op) => (
                      <li key={op.value || 'empty'} role="presentation">
                        <button type="button" role="option" aria-selected={perfilSelecionado === op.value} className={perfilSelecionado === op.value ? 'select-enter-option select-enter-option-active' : 'select-enter-option'} onClick={() => { setPerfilSelecionado(op.value); setMenuPerfilAberto(false); setErroLogin(''); }}>
                          {op.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text-soft)' }}>Usuário corporativo</label>
              <input type="text" value={usuario} onChange={(e) => { setUsuario(e.target.value); setErroLogin(''); }} placeholder="usuário EnterOS" style={{ marginBottom: '20px' }} />

              <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text-soft)' }}>Senha</label>
              <input type={mostrarSenha ? 'text' : 'password'} value={senha} onChange={(e) => { setSenha(e.target.value); setErroLogin(''); }} placeholder="••••••••" style={{ marginBottom: '10px' }} />
              <label className="login-mostrar-senha">
                <input type="checkbox" checked={mostrarSenha} onChange={(e) => setMostrarSenha(e.target.checked)} /> Mostrar senha
              </label>

              {erroLogin && <p className="login-erro" role="alert">{erroLogin}</p>}

              <button type="submit" className="btn-enter-primary" style={{ width: '100%', padding: '14px', borderRadius: '10px', cursor: 'pointer', fontSize: '16px', marginTop: '8px' }}>Entrar</button>
            </form>
          </section>
        </div>
      )}

      {/* TELA DO ADVOGADO */}
      {logado && perfilSelecionado === 'advogado' && (
        <div style={{ animation: 'fadeIn 0.5s ease' }}>
          <h2 style={{ marginBottom: '8px', color: '#fff' }}>Portal do escritório</h2>
          <p style={{ margin: '0 0 24px', color: 'var(--text-soft)', fontSize: '15px' }}>Consulte o processo e siga a recomendação da política de acordos Exit</p>

          <section style={{ marginBottom: '24px' }}>
            <h3 style={{ color: 'var(--color-primary)' }}>1. Consultar Processo</h3>
            <form onSubmit={consultarProcesso} style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <input type="text" value={processoIdBusca} onChange={(e) => setProcessoIdBusca(e.target.value)} placeholder="Ex: PROC-1001" />
              <button type="submit" className="btn-enter-primary" style={{ padding: '12px 24px', borderRadius: '10px', cursor: 'pointer', fontWeight: 700, flexShrink: 0 }}>Analisar</button>
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

                <div style={{ gridColumn: '1 / -1', marginTop: '10px', paddingTop: '15px', borderTop: '1px solid var(--border-subtle)' }}>
                  <p style={{ margin: '0 0 10px' }}><strong style={{ color: 'var(--text-soft)', fontSize: '0.9rem' }}>Documentos Base da IA (Auditoria de Leitura):</strong></p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {Object.entries(processoAtual.subsidios || {}).filter(([chave, valorBinario]) => valorBinario === 1).map(([chave]) => {
                        const foiLido = subsidiosLidos.has(chave);
                        return (
                          <button key={chave} type="button" onClick={() => abrirSubsidio(chave)}
                            style={{ 
                              padding: '6px 12px', borderRadius: '6px', cursor: 'pointer',
                              background: foiLido ? 'var(--color-primary)' : 'rgba(250, 204, 21, 0.05)', 
                              border: `1px solid ${foiLido ? 'var(--color-primary)' : 'rgba(250, 204, 21, 0.4)'}`, 
                              color: foiLido ? '#000' : 'var(--color-primary)', 
                              fontSize: '0.85rem', display: 'inline-flex', alignItems: 'center', gap: '6px',
                              fontWeight: foiLido ? 'bold' : 'normal', transition: 'all 0.2s'
                            }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                              {foiLido ? <polyline points="20 6 9 17 4 12"></polyline> : <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>}
                            </svg>
                            {nomesSubsidios[chave] || chave}
                          </button>
                        );
                      })}
                    {Object.values(processoAtual.subsidios || {}).every(valor => valor === 0) && (
                      <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.85rem' }}>A IA não identificou subsídios.</span>
                    )}
                  </div>
                </div>

                {/* CONTATO (ACORDO) - REMOVIDO TELEFONE */}
                {processoAtual.recomendacao === 'ACORDO' && processoAtual.contatoOposicao && (
                  <div style={{ gridColumn: '1 / -1', marginTop: '5px', paddingTop: '15px', borderTop: '1px solid var(--border-subtle)' }}>
                    <p style={{ margin: '0 0 10px' }}><strong style={{ color: 'var(--text-soft)', fontSize: '0.9rem' }}>Contato para Negociação (Extraído via IA):</strong></p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px', background: 'rgba(250, 204, 21, 0.05)', padding: '14px', borderRadius: '8px', border: '1px solid rgba(250, 204, 21, 0.15)' }}>
                      <div><span style={{color: 'var(--text-soft)', fontSize: '0.8rem'}}>Advogado(a):</span><br/><strong style={{color: '#fff'}}>{processoAtual.contatoOposicao.nome} <br/><span style={{color: 'var(--color-accent)', fontSize: '0.85rem'}}>{processoAtual.contatoOposicao.oab}</span></strong></div>
                      <div><span style={{color: 'var(--text-soft)', fontSize: '0.8rem'}}>E-mail:</span><br/><strong style={{color: '#fff'}}>{processoAtual.contatoOposicao.email}</strong></div>
                    </div>
                  </div>
                )}

                {processoAtual.recomendacao === 'DEFESA' && (
                  <div style={{ gridColumn: '1 / -1', marginTop: '10px', padding: '15px', borderRadius: '10px', border: '1px solid rgba(250, 204, 21, 0.2)', background: 'linear-gradient(135deg, rgba(0,0,0,0.85) 0%, rgba(60, 30, 8, 0.35) 100%)' }}>
                    <p style={{ margin: 0 }}><strong style={{ color: 'var(--color-accent)' }}>Justificativa da IA para litígio:</strong> {processoAtual.justificativa}</p>
                  </div>
                )}
              </div>
            )}
          </section>

          <section>
            <h3 style={{ color: '#fff' }}>3. Decisão Final (Auditoria Exit)</h3>
            <p style={{ color: 'var(--text-soft)' }}>Registre a estratégia adotada.</p>
            <div style={{ display: 'flex', gap: '15px', marginBottom: '15px' }}>
              <button type="button" onClick={() => registrarDecisao('ACORDO')} disabled={!processoAtual} className="btn-enter-primary" style={{ flex: 1, padding: '14px', borderRadius: '10px', cursor: processoAtual ? 'pointer' : 'not-allowed', opacity: processoAtual ? 1 : 0.4 }}>Seguir com Acordo</button>
              <button type="button" onClick={() => registrarDecisao('DEFESA')} disabled={!processoAtual} className="btn-enter-outline" style={{ flex: 1, padding: '14px', borderRadius: '10px', cursor: processoAtual ? 'pointer' : 'not-allowed', opacity: processoAtual ? 1 : 0.4 }}>Seguir com Defesa</button>
            </div>
            {decisaoAdvogado && (
              <div style={{ padding: '15px', background: 'linear-gradient(90deg, rgba(250, 204, 21, 0.12), rgba(251, 146, 60, 0.06))', borderLeft: '4px solid var(--color-primary)', borderRadius: '0 10px 10px 0' }}>
                <p style={{ margin: 0 }}>Ação executada: <strong style={{ color: 'var(--color-primary)' }}>{decisaoAdvogado}</strong>.</p>
              </div>
            )}
          </section>
        </div>
      )}

      {/* DASHBOARD DA ORGANIZAÇÃO DINÂMICO */}
      {logado && perfilSelecionado === 'organizacao' && (
        <div style={{ animation: 'fadeIn 0.5s ease' }}>
          <h2 style={{ marginBottom: '8px', color: '#fff' }}>Painel EnterOS — Banco UFMG</h2>
          <p style={{ margin: '0 0 24px', color: 'var(--text-soft)', fontSize: '15px' }}>
            Dados reais extraídos dos <strong>{dashTotalIA} processos</strong> carregados pela IA.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
            
            {/* KPI 1 - Aderência Dinâmica */}
            <section style={{ borderTop: '4px solid var(--color-primary)' }}>
              <h3 style={{ color: 'var(--color-primary)' }}>Aderência Real (Ao vivo)</h3>
              <p style={{ color: 'var(--text-soft)', fontSize: '0.9rem' }}>Taxa de escritórios seguindo a IA nas operações atuais</p>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
                <h1 style={{ fontSize: 'clamp(32px, 5vw, 48px)', margin: '10px 0', color: '#fff', wordBreak: 'break-word' }}>{pctAderenciaReal}%</h1>
                {historicoDecisoes.length > 0 && <span style={{ color: 'var(--color-primary)', fontWeight: 'bold' }}>Em {historicoDecisoes.length} cliques</span>}
              </div>
              <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '0.85rem' }}>{casosAderentes} de {historicoDecisoes.length} decisões confirmadas seguiram a IA.</p>
            </section>

            {/* KPI 2 - Economia Calculada da Base COM CORREÇÃO DE OVERFLOW */}
            <section style={{ borderTop: '4px solid var(--color-accent)' }}>
              <h3 style={{ color: 'var(--color-accent)' }}>Economia Potencial</h3>
              <p style={{ color: 'var(--text-soft)', fontSize: '0.9rem' }}>Lucro projetado se todos os acordos forem fechados</p>
              <h1 style={{ fontSize: 'clamp(28px, 4.5vw, 48px)', margin: '10px 0', color: '#fff', wordBreak: 'break-word' }}>{formatarMoeda(dashEconomiaGerada)}</h1>
              <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '0.85rem' }}>Diferença entre Valores de Causa e Sugestões da IA.</p>
            </section>

            {/* KPI 3 - Distribuição Dinâmica */}
            <section>
              <h3 style={{ color: '#fff' }}>Distribuição das recomendações da IA</h3>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '30px', marginBottom: '10px' }}>
                <span style={{ color: 'var(--color-primary)', fontWeight: 'bold' }}>Acordo ({pctAcordo}%)</span>
                <span style={{ color: 'var(--color-accent)', fontWeight: 'bold' }}>Defesa ({pctDefesa}%)</span>
              </div>

              <div className="enter-gradient-bar" style={{ marginTop: '8px' }} aria-hidden>
                <span style={{ width: `${pctAcordo}%`, transition: 'width 0.5s' }} />
                <span style={{ width: `${pctDefesa}%`, transition: 'width 0.5s' }} />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '12px' }}>
                <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '0.9rem' }}>{dashQtdAcordo} processos</p>
                <p style={{ margin: 0, color: 'var(--text-soft)', fontSize: '0.9rem' }}>{dashQtdDefesa} processos</p>
              </div>
            </section>

            {/* KPI 4 - Funil Dinâmico */}
            <section>
              <h3 style={{ color: '#fff' }}>Funil de Inteligência ExitOS</h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', marginTop: '20px' }}>
                <div style={{ backgroundColor: '#000', padding: '15px', borderRadius: '8px', borderLeft: '4px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-soft)' }}>1. Documentos Inseridos</span>
                  <strong style={{ color: '#fff', fontSize: '1.2rem' }}>{dashTotalIA}</strong>
                </div>
                
                <div style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0.9), rgba(120, 53, 15, 0.2))', padding: '15px', borderRadius: '8px', borderLeft: '4px solid var(--color-accent)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-soft)' }}>2. Oportunidades de Acordo</span>
                  <strong style={{ color: 'var(--color-accent)', fontSize: '1.2rem' }}>{dashQtdAcordo}</strong>
                </div>

                <div style={{ backgroundColor: 'rgba(250, 204, 21, 0.05)', padding: '15px', borderRadius: '8px', borderLeft: '4px solid var(--color-primary)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-soft)' }}>3. Adotados pelos Advogados</span>
                  <strong style={{ color: 'var(--color-primary)', fontSize: '1.2rem' }}>{casosAderentes}</strong>
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