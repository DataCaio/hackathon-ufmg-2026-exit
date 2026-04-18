/**
 * Dados de demonstração — EnterOS (Hackathon UFMG 2026).
 * Contas de exemplo apenas; não usar em produção.
 *
 * Credenciais para documentação / SETUP (não expostas na UI):
 * - Escritório: advogado.demo / EnterOS2026
 * - Organização: staff.enter / HackathonUFMG
 *   (também aceita "HackatonUFMG" sem o segundo "h", erro comum de digitação)
 */

export const CONTAS_DEMO_VALIDAS = [
  {
    usuario: 'staff.enter',
    senhasAceitas: ['HackathonUFMG', 'HackatonUFMG'],
    perfil: 'organizacao'
  },
  { usuario: 'advogado.demo', senhasAceitas: ['EnterOS2026'], perfil: 'advogado' }
];

const MSG_PERFIL_OBRIGATORIO = 'Selecione o perfil de acesso.';
const MSG_CAMPOS_OBRIGATORIOS = 'Informe usuário e senha.';
/** Mesma mensagem para credencial inválida, perfil incompatível ou usuário inexistente (sem vazamento de informação). */
const MSG_AUTENTICACAO_FALHOU = 'Não foi possível entrar. Verifique perfil, usuário e senha.';

function senhaConfere(conta, senhaDigitada) {
  return conta.senhasAceitas.some((s) => s === senhaDigitada);
}

/**
 * @param {string} perfilSelecionado - 'advogado' | 'organizacao' | ''
 * @param {string} usuario
 * @param {string} senha
 * @returns {{ ok: true, conta: object } | { ok: false, mensagem: string }}
 */
export function validarDemoLogin(perfilSelecionado, usuario, senha) {
  const u = usuario.trim().toLowerCase();
  const s = senha;

  if (!perfilSelecionado) {
    return { ok: false, mensagem: MSG_PERFIL_OBRIGATORIO };
  }
  if (!u || !s) {
    return { ok: false, mensagem: MSG_CAMPOS_OBRIGATORIOS };
  }

  const conta = CONTAS_DEMO_VALIDAS.find(
    (c) =>
      c.usuario.toLowerCase() === u &&
      senhaConfere(c, s) &&
      c.perfil === perfilSelecionado
  );

  if (!conta) {
    return { ok: false, mensagem: MSG_AUTENTICACAO_FALHOU };
  }

  return { ok: true, conta };
}
