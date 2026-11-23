"use strict";

/* ==========================================================================
   Tela de detalhe do frete
   Lê os dados embutidos pelo Flask (#fd-data) e monta a página via JS.

   Ciclo de vida do frete:
   em_preparacao → em_oferta → negociacao → cotacao_aceita → concluido
                                                           ↘ cancelado
   ========================================================================== */


/* --------------------------------------------------------------------------
   1. DADOS INICIAIS (boot)
   -------------------------------------------------------------------------- */

const boot = JSON.parse(document.getElementById("fd-data").textContent);

const frete = boot.frete || {};
const registro = boot.registro || {};
const propostas = Array.isArray(boot.propostas) ? boot.propostas : [];
const fechamento = boot.fechamento || null;
const recomendacao = frete.recomendacao || {};
const negotiationCarriers = Array.isArray(
    boot.transportadoras_negociacao
)
    ? boot.transportadoras_negociacao
    : [];

const FRETE_ID = Number(registro.id || frete.db_id);
// Remember the last carrier added to this freight.
const carrierStorageKey = `freight:${FRETE_ID}:selected-carrier`;

const lastSelectedCarrier =
    sessionStorage.getItem(carrierStorageKey);
const STATUS = registro.status || frete.status_db || "em_preparacao";

// Transportadora sugerida automaticamente ("—" significa "sem sugestão")
const sugestao = recomendacao.transportadora || null;
const sugestaoValida = sugestao && sugestao !== "—" ? sugestao : null;

// Transportadora atual: a escolhida (se houver) ou, na falta dela, a sugestão
const transportadora =
  registro.transportadora_escolhida ||
  registro.transportadora ||
  frete.transportadora_escolhida ||
  sugestaoValida;

const ROTULOS_STATUS = {
  em_preparacao: "Em preparação",
  em_oferta: "Em oferta",
  negociacao: "Em negociação",
  cotacao_aceita: "Cotação aceita",
  concluido: "Concluído",
  cancelado: "Cancelado",
  disponivel: "Em preparação",
};


/* --------------------------------------------------------------------------
   2. FLAGS DE ESTADO
   -------------------------------------------------------------------------- */

const propostaAceita = (p) => p.aceita === 1 || p.aceita === true;

const aceitaAtual = propostas.find(propostaAceita);
const temAceita = Boolean(aceitaAtual);

const podeEditar = STATUS === "em_preparacao" || STATUS === "disponivel";
const podeSelecionarTransportadora = [
    "em_preparacao",
    "disponivel",
    "em_oferta",
    "negociacao"
].includes(STATUS) && !temAceita && !fechamento;
const podeRegistrarProposta = STATUS === "negociacao" && !temAceita && !fechamento;
const podeAceitarProposta = STATUS === "negociacao" && !temAceita && !fechamento;
const encerrado = STATUS === "concluido" || STATUS === "cancelado";


/* --------------------------------------------------------------------------
   3. HELPERS GERAIS
   -------------------------------------------------------------------------- */

const $ = (id) => document.getElementById(id);

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escapa HTML para evitar XSS ao montar templates. */
const esc = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);

const vazio = (x) => x === null || x === undefined || x === "" || !Number.isFinite(Number(x));

/** Formata moeda BRL, ou "—" se o valor for vazio/inválido. */
const valor = (x) =>
  vazio(x) ? "—" : Number(x).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** Formata número pt-BR, ou "—" se o valor for vazio/inválido. */
const num = (x) => (vazio(x) ? "—" : Number(x).toLocaleString("pt-BR"));

/** Bloco "rótulo + valor". */
const campo = (nome, x) =>
  `<div class="fd-field"><small>${esc(nome)}</small><strong>${esc(x ?? "—")}</strong></div>`;

/** Bloco "rótulo + valor em reais". */
const moneyCampo = (nome, x) => campo(nome, valor(x));

/** Mostra uma mensagem de aviso (ou erro) no topo da tela. */
function avisar(msg, erro = false) {
  const el = $("fd-notice");
  el.textContent = msg;
  el.hidden = false;
  el.classList.toggle("error", erro);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/** Executa uma ação assíncrona e mostra qualquer erro na tela. */
async function executar(fn) {
  try {
    await fn();
  } catch (e) {
    console.error(e);
    avisar(e.message, true);
  }
}


function formatPostalCode(value) {
    const digits = String(value ?? "").replace(/\D/g, "");

    if (digits.length !== 8) {
        return value || "—";
    }

    return `${digits.slice(0, 5)}-${digits.slice(5)}`;
}

function formatDate(value) {
    if (!value) return "—";

    const date = String(value).slice(0, 10);

    const match = date.match(
        /^(\d{4})-(\d{2})-(\d{2})$/
    );

    if (!match) return String(value);

    const [, year, month, day] = match;

    return `${day}/${month}/${year}`;
}



/* --------------------------------------------------------------------------
   4. CHAMADAS AO SERVIDOR
   -------------------------------------------------------------------------- */

/** fetch que espera JSON e lança erro se a resposta indicar falha. */
async function api(url, options = {}) {
  const r = await fetch(url, options);
  const tipo = r.headers.get("content-type") || "";

  if (!tipo.includes("application/json")) {
    throw Error(`Resposta inesperada do servidor (HTTP ${r.status}).`);
  }

  const d = await r.json();
  if (!r.ok || d.sucesso === false) {
    throw Error(d.mensagem || d.erro || `Erro HTTP ${r.status}`);
  }
  return d;
}

/** POST AJAX (com formulário opcional) em rota que responde JSON.
 *  O cabeçalho X-Requested-With faz o Flask responder JSON em vez de redirect. */
const postAjax = (url, formData) =>
  api(url, {
    method: "POST",
    headers: { "X-Requested-With": "XMLHttpRequest" },
    body: formData,
  });

/** POST JSON simples. */
const postJson = (url, body) =>
  api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

const recarregar = () => location.reload();


/* --------------------------------------------------------------------------
   5. RENDER PRINCIPAL
   -------------------------------------------------------------------------- */

function render() {
  const origem = frete.origem || frete.planta?.cidade || registro.origem || "—";
  const destino = frete.destino?.cidade || frete.destino || registro.destino || "—";

  $("fd-status").textContent = ROTULOS_STATUS[STATUS] || STATUS;
  $("fd-subtitle").textContent = `${origem} → ${destino}`;

  renderMetricas();
  renderCarga(origem, destino);
  renderPercurso(origem, destino);
  renderTransportadora();
  renderNegociacao();
  renderFechamento();
  renderActions();
  renderEdicao();
}


/* --------------------------------------------------------------------------
   6. MÉTRICAS E DADOS DA CARGA
   -------------------------------------------------------------------------- */

function renderMetricas() {
  const calc = frete.calculo || {};

  const metricas = [
    ["Peso operacional", `${num(frete.peso_kg ?? registro.peso)} kg`],
    ["Custo ANTT", valor(calc.antt)],
    ["Custo mercado", valor(calc.mercado ?? registro.valor)],
    ["Data da carga", esc(formatDate(frete.data_carga || registro.coleta))],
  ];

  $("fd-metrics").innerHTML = metricas
    .map(
      ([nome, v]) =>
        `<div class="fd-metric"><small>${esc(nome)}</small><strong>${v}</strong></div>`
    )
    .join("");
}

function renderCarga(origem, destino) {
  const pedidos = Array.isArray(frete.pedidos) ? frete.pedidos.join(", ") : frete.pedido || "—";

  const clientes = Array.isArray(frete.clientes)
    ? frete.clientes
        .map((c) => c.customer_name || c.customer_id || "")
        .filter(Boolean)
        .join(", ")
    : frete.customer || "—";

  $("fd-carga").innerHTML = `
    <div class="fd-grid">
      ${campo("Número do frete", frete.num || registro.num || registro.numero_frete)}
      ${campo("Pedido(s)", pedidos)}
      ${campo("Cliente(s)", clientes)}
      ${campo("Planta", frete.planta?.nome || origem)}
      ${campo("Destino", destino)}
      ${campo("UF", frete.uf)}
      ${campo("CEP de destino", formatPostalCode(frete.cep))}
      ${campo("Tipo de rota", frete.tipo || "Direta")}
      ${campo("Tipo de carga", frete.tipo_carga === "paletizada" ? "Paletizada" : "Batida")}
    </div>`;
}


/* --------------------------------------------------------------------------
   7. PERCURSO
   -------------------------------------------------------------------------- */

function renderPercurso(origem, destino) {
  const calc = frete.calculo || {};
  const veiculo = recomendacao.caminhao || frete.caminhao || {};

  const stops =
    Array.isArray(frete.stops) && frete.stops.length
      ? frete.stops
      : [origem, ...(frete.transfer ? [frete.transfer] : []), destino];

  const nomeParada = (s) => (typeof s === "string" ? s : s.cidade || s.nome || "—");

  const rota = stops
    .map((s, i) => `${i ? "<span>→</span>" : ""}<span class="fd-stop">${esc(nomeParada(s))}</span>`)
    .join("");

  let textoVeiculo = "Não definido";
  if (veiculo.excede) {
    textoVeiculo = "Excede a capacidade máxima";
  } else if (veiculo.tipo) {
    textoVeiculo = `${veiculo.tipo} · ${veiculo.eixos || "—"} eixos`;
  }

  // Rotas diretas trazem "trechos"; múltiplas paradas trazem "km_trechos"
  let qtdTrechos = "—";
  if (Array.isArray(frete.trechos)) {
    qtdTrechos = frete.trechos.length;
  } else if (Array.isArray(frete.km_trechos)) {
    qtdTrechos = frete.km_trechos.length;
  } else if (stops.length > 1) {
    qtdTrechos = stops.length - 1;
  }

  $("fd-percurso").innerHTML = `
    <div class="fd-route">${rota}</div>
    <div class="fd-grid">
      ${campo("Distância total", `${num(calc.distancia_total_km ?? frete.km_estimado)} km`)}
      ${campo("Combustível estimado", `${num(calc.litros_totais)} L`)}
      ${moneyCampo("Custo combustível", calc.custo_combustivel)}
      ${campo("Veículo recomendado", textoVeiculo)}
      ${campo("Trechos", qtdTrechos)}
      ${campo("Transbordo", frete.transfer || "Não")}
    </div>`;
}


/* --------------------------------------------------------------------------
   8. TRANSPORTADORA (recomendação e seleção)
   -------------------------------------------------------------------------- */

/** Lista (sem repetição) de transportadoras que aparecem no select. */
function opcoesTransportadoras() {
  const itens = [];

  if (sugestaoValida) itens.push(sugestaoValida);

  for (const a of recomendacao.alternativas || []) {
    if (a.nome) itens.push(a.nome);
  }
  for (const nome of recomendacao.outras_transportadoras || []) {
    if (nome) itens.push(nome);
  }
  if (transportadora) itens.push(transportadora);

  return [...new Set(itens)];
}

function htmlResumoRecomendacao() {
  const avisos = (recomendacao.avisos || [])
    .map((a) => `<div class="fd-warnings">${esc(a)}</div>`)
    .join("");

  return `
    <div class="fd-grid">
      ${campo("Sugestão automática", sugestaoValida || "Sem sugestão")}
      ${campo(
      "Transportadora escolhida",
      aceitaAtual?.transportadora ||
      (fechamento ? registro.transportadora_escolhida : null) ||
      "Aguardando escolha"
    )}
      ${campo("Confiança", recomendacao.confianca || "—")}
      ${campo("SLA", recomendacao.sla || "—")}
      ${campo("Viagens da transportadora", recomendacao.viagens_transportadora ?? "—")}
      ${moneyCampo("Média paga por viagem", recomendacao.custo_medio_frete)}
    </div>
    ${recomendacao.detalhe ? `<p class="fd-hint">${esc(recomendacao.detalhe)}</p>` : ""}
    ${avisos}`;
}


function htmlSelecaoTransportadora() {
    if (!podeSelecionarTransportadora) {
        return `
            <p class="fd-hint">
                Seleção bloqueada para o status atual.
            </p>
        `;
    }

    const isNegotiating = STATUS === "negociacao";

    const existingCarriers = new Set(
        negotiationCarriers.map(
            item => item.transportadora.trim().toUpperCase()
        )
    );

    const options = opcoesTransportadoras()
        .filter(name => !existingCarriers.has(
            name.trim().toUpperCase()
        ))
        .map(name => `
            <option value="${esc(name)}"
                ${!isNegotiating && name === sugestaoValida
                    ? "selected"
                    : ""}>
                ${esc(name)}
            </option>
        `)
        .join("");

    return `
        <div class="fd-choice">
            <select id="fd-carrier">
                <option value="">
                    Selecione uma transportadora
                </option>
                ${options}
            </select>

            <button
                type="button"
                class="fd-btn fd-primary"
                id="fd-start">
                ${isNegotiating
                    ? "Adicionar à negociação"
                    : "Iniciar negociação"}
            </button>
        </div>

        <label>
            Outra transportadora (se não estiver na lista)

            <input
                id="fd-custom-carrier"
                type="text"
                maxlength="200"
                placeholder="Nome da transportadora">
        </label>
    `;
}


function htmlAlternativas() {
    const alternatives = recomendacao.alternativas || [];

    if (!alternatives.length) return "";

    const items = alternatives.map(alt => `
        <div class="fd-item">
            <div>
                <strong>${esc(alt.nome)}</strong>
                <small>
                    SLA ${esc(alt.sla || "—")}
                    · ${num(alt.viagens)} viagens
                    · ${valor(alt.media_paga)}
                </small>
            </div>

            ${podeSelecionarTransportadora ? `
                <button
                    type="button"
                    class="fd-btn fd-pick"
                    data-carrier="${esc(alt.nome)}">
                    Selecionar
                </button>
            ` : ""}
        </div>
    `).join("");

    return `
        <details class="fd-alternatives">
            <summary>
                <span>
                    Alternativas recomendadas
                    <small>${alternatives.length} opções disponíveis</small>
                </span>
                <span class="fd-chevron">⌄</span>
            </summary>

            <div class="fd-list">
                ${items}
            </div>
        </details>
    `;
}


function renderTransportadora() {
$("fd-recomendacao").innerHTML = `
    ${htmlResumoRecomendacao()}

    <div class="fd-line"></div>

    <h3>Escolher transportadora</h3>

    <p class="fd-muted">
        Adicione transportadoras para receber e comparar propostas.
        A escolha final acontece na aceitação da proposta.
    </p>

    ${htmlSelecaoTransportadora()}

    <div class="fd-line"></div>

    ${htmlAlternativas()}
  `;

  // Botão "Confirmar transportadora": inicia a negociação

  $("fd-start")?.addEventListener("click", () =>
      executar(async () => {
          const nome =
              $("fd-custom-carrier").value.trim() ||
              $("fd-carrier").value.trim();

          if (!nome) {
              throw Error("Selecione uma transportadora.");
          }

          const message = STATUS === "negociacao"
              ? `Adicionar ${nome} à negociação?`
              : `Iniciar negociação com ${nome}?`;

          if (!confirm(message)) return;

          await postJson(
              `/api/nova-carga/fretes/${FRETE_ID}/negociacao`,
              { transportadora: nome }
          );

          // Select this carrier in the proposal form after reload.
          sessionStorage.setItem(carrierStorageKey, nome);

          recarregar();
      })
  );


  // Botões "Selecionar" das alternativas: só preenchem o select
  document.querySelectorAll(".fd-pick").forEach(botao =>
    botao.addEventListener("click", () => {
        const select = $("fd-carrier");

        if (!select) return;

        const name = botao.dataset.carrier;

        const available = [...select.options].some(
            option => option.value === name
        );

        if (!available) {
            avisar("Esta transportadora já está em negociação.");
            return;
        }

        select.value = name;
        $("fd-custom-carrier").value = "";

        select.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    })
  );
}


/* --------------------------------------------------------------------------
   9. NEGOCIAÇÃO (propostas)
   -------------------------------------------------------------------------- */

function htmlFormProposta() {
  if (!podeRegistrarProposta) return "";

  if (!negotiationCarriers.length) {
    return `
        <p class="fd-hint">
            Adicione uma transportadora à negociação
            antes de registrar uma proposta.
        </p>
    `;
  }
  const selectedCarrier =
    negotiationCarriers.find(carrier =>
        carrier.transportadora.trim().toUpperCase() ===
        String(lastSelectedCarrier || "").trim().toUpperCase()
    )?.transportadora ||

    (negotiationCarriers.length === 1
        ? negotiationCarriers[0].transportadora
        : "");

  return `
    <form id="fd-proposal-form">

      <label>Transportadora
          <select name="transportadora" required>

              <option value="">
                  Selecione a transportadora da proposta
              </option>

              ${negotiationCarriers.map(carrier => `
                  <option
                      value="${esc(carrier.transportadora)}"
                      ${carrier.transportadora === selectedCarrier
                          ? "selected"
                          : ""}>
                      ${esc(carrier.transportadora)}
                  </option>
              `).join("")}

          </select>
      </label>

      <div class="fd-form-grid">
        <label>Valor negociado (R$)
          <input name="valor" type="number" min="0.01" step="0.01" required>
        </label>
        <label>Prazo (dias)
          <input name="prazo_dias" type="number" min="0" max="365">
        </label>
      </div>
      <label>Observações
        <textarea name="observacoes" rows="3" placeholder="Condições da negociação"></textarea>
      </label>
      <button class="fd-btn fd-primary" type="submit">Registrar proposta</button>
    </form>
    <div class="fd-line"></div>`;
}

function htmlItemProposta(p) {
  const detalhes =
    `${valor(p.valor)} · Prazo: ${esc(p.prazo_dias ?? "—")} dias` +
    (p.observacoes ? ` · ${esc(p.observacoes)}` : "");

  let acao = "";
  if (propostaAceita(p)) {
    acao = '<span class="fd-tag">✓ Aceita</span>';
  } else if (podeAceitarProposta) {
    acao = `<button type="button" class="fd-btn fd-accept" data-id="${Number(p.id)}">Aceitar proposta</button>`;
  }

  return `
    <div class="fd-item">
      <div>
        <strong>${esc(p.transportadora)}</strong>
        <small>${detalhes}</small>
      </div>
      ${acao}
    </div>`;
}

function htmlHistoricoPropostas() {
  if (!propostas.length) {
    return '<p class="fd-hint">Nenhuma proposta registrada até o momento.</p>';
  }
  return `<div class="fd-list">${propostas.map(htmlItemProposta).join("")}</div>`;
}

function renderNegociacao() {
  $("fd-negociacao").innerHTML = `
    ${htmlFormProposta()}
    <h3>Histórico de propostas</h3>
    ${htmlHistoricoPropostas()}`;

  // Registrar nova proposta
  $("fd-proposal-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const form = e.currentTarget;

    executar(async () => {
      const botao = form.querySelector("button");
      botao.disabled = true;
      try {
        await api(`/nova-carga/fretes/${FRETE_ID}/propostas`, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        body: new FormData(form),
    });

    // Release the automatic selection for the next proposal.
    sessionStorage.removeItem(carrierStorageKey);

    recarregar();
      } finally {
        botao.disabled = false;
      }
    });
  });

  // Aceitar uma proposta
  document.querySelectorAll(".fd-accept").forEach((botao) =>
    botao.addEventListener("click", () =>
      executar(async () => {
        if (!confirm("Aceitar esta proposta?")) return;
        await postAjax(`/nova-carga/fretes/${FRETE_ID}/propostas/${botao.dataset.id}/aceitar`);
        recarregar();
      })
    )
  );
}


/* --------------------------------------------------------------------------
   10. FECHAMENTO (confirmação SAP e conclusão)
   -------------------------------------------------------------------------- */

function htmlFechamento() {
  // Contratação já confirmada no SAP
  if (fechamento) {
    return `
      <div class="fd-hint">
        <strong>✓ Contratação confirmada</strong>
        <p>Referência SAP: ${esc(fechamento.referencia_sap || "—")}</p>
      </div>
      ${
        STATUS === "cotacao_aceita"
          ? '<button type="button" class="fd-btn fd-primary" id="fd-complete">Concluir frete</button>'
          : ""
      }`;
  }

  // Proposta aceita, falta confirmar no SAP
  if (aceitaAtual) {
    return `
      <p class="fd-hint">Proposta aceita. Aguardando confirmação da contratação no SAP.</p>
      <form id="fd-sap-form">
        <label>Referência do frete no SAP
          <input name="referencia_sap" type="text" required placeholder="Número ou referência SAP">
        </label>
        <button type="submit" class="fd-btn fd-primary">Confirmar contratação SAP</button>
      </form>`;
  }

  // Ainda sem proposta aceita
  return `<p class="fd-hint">A confirmação SAP ficará disponível após aceitar uma proposta.</p>`;
}

function renderFechamento() {
  $("fd-fechamento").innerHTML = htmlFechamento();

  // Confirmar contratação no SAP
  $("fd-sap-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const form = e.currentTarget;

    executar(async () => {
      await postAjax(`/nova-carga/fretes/${FRETE_ID}/confirmar-sap`, new FormData(form));
      recarregar();
    });
  });

  // Concluir o frete
  $("fd-complete")?.addEventListener("click", () =>
    executar(async () => {
      if (!confirm("Confirma que a operação deste frete foi concluída?")) return;
      await api(`/api/nova-carga/fretes/${FRETE_ID}/concluir`, { method: "POST" });
      recarregar();
    })
  );
}


/* --------------------------------------------------------------------------
   11. AÇÕES (publicar / retirar oferta)
   -------------------------------------------------------------------------- */

function renderActions() {
  const itens = [];

  if (podeEditar) {
    itens.push('<button id="fd-publish" class="fd-btn fd-primary">Publicar oferta</button>');
  }
  if (STATUS === "em_oferta") {
    itens.push('<button id="fd-withdraw" class="fd-btn fd-danger">Retirar oferta</button>');
  }
  if (encerrado) {
    itens.push('<p class="fd-hint">Frete encerrado. Operações bloqueadas.</p>');
  }
  if (!itens.length) {
    itens.push('<p class="fd-hint">Acompanhe a negociação nas seções ao lado.</p>');
  }

  $("fd-actions").innerHTML = itens.join("");

  $("fd-publish")?.addEventListener("click", () =>
    executar(async () => {
      if (!confirm("Publicar este frete para oferta?")) return;
      await api(`/mesa/fretes/${FRETE_ID}/publicar`, { method: "POST" });
      recarregar();
    })
  );

  $("fd-withdraw")?.addEventListener("click", () =>
    executar(async () => {
      if (!confirm("Retirar oferta e voltar à preparação?")) return;
      await api(`/mesa/fretes/${FRETE_ID}/retirar-oferta`, { method: "POST" });
      recarregar();
    })
  );
}


/* --------------------------------------------------------------------------
   12. EDIÇÃO DOS DADOS DA CARGA
   -------------------------------------------------------------------------- */

/** Converte "" em null; caso contrário, em número. */
const numeroOuNull = (v) => (v === "" ? null : Number(v));

/** Lê o formulário de edição e valida os campos numéricos. */
function lerPayloadEdicao(form) {
  const d = new FormData(form);

  const payload = {
    tipo_carga: d.get("tipo_carga"),
    peso_liquido_kg: numeroOuNull(d.get("peso_liquido_kg")),
    valor_inicial_negociacao: numeroOuNull(d.get("valor_inicial_negociacao")),
    comentarios_carga: d.get("comentarios_carga"),
  };

  const peso = payload.peso_liquido_kg;
  if (peso !== null && (!Number.isFinite(peso) || peso <= 0)) {
    throw Error("Informe um peso líquido positivo.");
  }

  const inicial = payload.valor_inicial_negociacao;
  if (inicial !== null && (!Number.isFinite(inicial) || inicial < 0)) {
    throw Error("Informe um valor inicial válido.");
  }

  return payload;
}

function renderEdicao() {
  const form = $("fd-edit-form");

  // Preenche o formulário com os valores atuais
  form.elements.tipo_carga.value = frete.tipo_carga || "batida";
  form.elements.peso_liquido_kg.value = frete.peso_liquido_kg ?? "";
  form.elements.valor_inicial_negociacao.value = frete.valor_inicial_negociacao ?? "";
  form.elements.comentarios_carga.value = frete.comentarios_carga ?? "";

  // Só é editável em preparação
  for (const el of form.elements) el.disabled = !podeEditar;

  $("fd-edit-hint").textContent = podeEditar
    ? "O peso líquido é informativo e não altera o peso operacional ou o custo."
    : "Para editar, o frete precisa estar em preparação.";

  form.addEventListener("submit", (e) => {
    e.preventDefault();

    executar(async () => {
      if (!podeEditar) return;

      const payload = lerPayloadEdicao(form);
      await api(`/nova-carga/fretes/${FRETE_ID}/dados`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      recarregar();
    });
  });
}


/* --------------------------------------------------------------------------
   13. INICIALIZAÇÃO
   -------------------------------------------------------------------------- */

if (!Number.isInteger(FRETE_ID) || FRETE_ID <= 0) {
  avisar("ID do frete inválido. Verifique os dados enviados pelo Flask.", true);
} else {
  render();
}