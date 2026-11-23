
"use strict";

// =====================================
// STATUS
// =====================================

const statusLabels = {
    em_preparacao: "Em preparação",
    em_oferta: "Em oferta",
    negociacao: "Em negociação",
    cotacao_aceita: "Cotação aceita",
    concluido: "Concluído",
    cancelado: "Cancelado"
};

// Compatibilidade com os fretes antigos
function normalizarStatus(status) {
    if (!status || status === "disponivel") {
        return "em_preparacao";
    }

    return status;
}

// Mantemos os dados recebidos do Flask
const dadosKanban = (typeof fretes !== "undefined" && Array.isArray(fretes))
    ? fretes.map(f => ({
        ...f,
        status: normalizarStatus(f.status_db || f.status)
    }))
    : [];

// =====================================
// FORMATAÇÃO
// =====================================

function moeda(valor) {
    if (valor === null || valor === undefined || valor === "") {
        return "—";
    }

    const numero = Number(valor);

    if (!Number.isFinite(numero)) {
        return "—";
    }

    return numero.toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL"
    });
}

function numero(valor) {
    const n = Number(valor);

    return Number.isFinite(n)
        ? n.toLocaleString("pt-BR")
        : "—";
}

// =====================================
// CRIAR CARD
// =====================================

function criarCard(frete) {
    const card = document.createElement("article");

    card.className = "kanban-card";
    card.dataset.id = String(frete.id);
    card.draggable = false;

    const codigo = document.createElement("div");
    codigo.className = "kanban-card-code";
    codigo.textContent = `Frete #${frete.id}`;

    const rota = document.createElement("h3");
    rota.textContent =
        `${frete.origem || "Origem não informada"} → ${frete.destino || "Destino não informado"}`;

    const info = document.createElement("div");
    info.className = "kanban-card-info";

    const peso = frete.peso ?? frete.peso_kg;
    const coleta = frete.coleta ?? frete.data_carga ?? "—";

    info.textContent =
        `${numero(peso)} kg · Coleta: ${coleta}`;

    const footer = document.createElement("div");
    footer.className = "kanban-card-footer";

    const valor = document.createElement("strong");
    valor.textContent = moeda(
        frete.valor ?? frete.calculo?.mercado
    );


    footer.append(valor);

    card.append(codigo, rota, info, footer);

    const detalhes = document.createElement("a");

    const idNegociacao = frete.db_id ?? frete.id;

    detalhes.href =
        `/fretes/${encodeURIComponent(idNegociacao)}`;

    detalhes.textContent = "Abrir negociação →";
    detalhes.className = "kanban-card-link";
    detalhes.draggable = false;

    card.appendChild(detalhes);

    return card;
}

// =====================================
// RENDERIZAR KANBAN
// =====================================

function renderKanban() {
    const campoBusca = document.getElementById("kanban-search");

    const busca = (campoBusca?.value || "")
        .toLocaleLowerCase("pt-BR")
        .trim();

    const filtrados = dadosKanban.filter(frete => {
        const texto = [
            frete.id,
            frete.db_id,
            frete.origem,
            frete.destino
        ].join(" ").toLocaleLowerCase("pt-BR");

        return texto.includes(busca);
    });

    document.querySelectorAll(".kanban-column")
        .forEach(coluna => {
            const status = coluna.dataset.status;
            const container = coluna.querySelector(".kanban-items");

            if (!container) return;

            container.replaceChildren();

            const itens = filtrados.filter(
                f => f.status === status
            );

            itens.forEach(frete => {
                container.appendChild(criarCard(frete));
            });

            const contador = coluna.querySelector(".column-count");

            if (contador) {
                contador.textContent = itens.length;
            }
        });

    atualizarKPIs();
}

// =====================================
// KPIs
// =====================================

function atualizarKPIs() {
    const contar = status =>
        dadosKanban.filter(f => f.status === status).length;

    const atualizar = (id, valor) => {
        const elemento = document.getElementById(id);

        if (elemento) {
            elemento.textContent = valor;
        }
    };

    atualizar("kpi-total", dadosKanban.length);

    // ID antigo mantido para não quebrar o HTML
    atualizar(
        "kpi-disponiveis",
        contar("em_preparacao")
    );

    atualizar(
        "kpi-negociacao",
        contar("negociacao")
    );

    atualizar(
        "kpi-cotacao_aceita",
        contar("cotacao_aceita")
    );

    // IDs opcionais para novos KPIs
    atualizar(
        "kpi-em_oferta",
        contar("em_oferta")
    );

    atualizar(
        "kpi-concluido",
        contar("concluido")
    );
}

// =====================================
// INICIALIZAÇÃO
// =====================================

document.getElementById("kanban-search")
    ?.addEventListener("input", renderKanban);

renderKanban();
